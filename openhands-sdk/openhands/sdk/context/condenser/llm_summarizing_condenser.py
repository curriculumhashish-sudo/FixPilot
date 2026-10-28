import os
from collections.abc import Sequence
from enum import Enum
from typing import Final

from pydantic import Field, model_validator

from openhands.sdk.context.condenser.base import (
    CondensationRequirement,
    NoCondensationAvailableException,
    RollingCondenser,
)
from openhands.sdk.context.condenser.utils import (
    get_suffix_length_for_token_reduction,
    get_total_token_count,
)
from openhands.sdk.context.prompts import render_template
from openhands.sdk.context.view import View
from openhands.sdk.event.base import LLMConvertibleEvent
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.event.llm_convertible import SystemPromptEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.logger import get_logger
from openhands.sdk.observability.laminar import observe
from openhands.sdk.utils import maybe_truncate


logger = get_logger(__name__)


def _leading_system_prompt_index(events: Sequence[LLMConvertibleEvent]) -> int | None:
    """``events`` 或 ``None`` 中第一个 ``SystemPromptEvent`` 的索引。

    智能体循环确保 ``SystemPromptEvent`` 总是位于视图的头部（索引 0），因此上下文压缩
    必须记住这一点——否则压缩视图将以非系统消息打开，并违反全
    局“系统在第一个用户之前” 不变量的规定。 当不存在系统提示词时返回 ``None`` (e.g.
    无需构建单元测试视图）。
    """
    for i, event in enumerate(events):
        if isinstance(event, SystemPromptEvent):
            return i
    return None


class Reason(Enum):
    """原因上下文压缩。"""

    REQUEST = "request"
    TOKENS = "tokens"
    EVENTS = "events"


class LLMSummarizingCondenser(RollingCondenser):
    """基于 LLM 的上下文压缩器总结了被遗忘的事件。

    使用独立的 LLM（存储在 `llm` 属性中）来生成遗忘事件的摘要。 传递给 condense() 的
    可选 `agent_llm` 参数是智能体用于 token
    计数目的 LLM，你应该不假设它与定义于此上下文压缩器中的参数相同。
    """

    llm: LLM
    max_size: int = Field(default=240, gt=0)
    max_tokens: int | None = None

    keep_first: int = Field(default=2, ge=0)
    """视图开始时要保留的最小事件数。 第一个
    `keep_first` 对话中的事件永远不会被浓缩或总结。
    """

    minimum_progress: float = Field(default=0.1, gt=0.0, lt=1.0)
    """必须压缩的事件的最小分数 (0.0-1.0)。 如果少于
    这部分事件将被遗忘，上下文压缩被视为错误。 默认值 0.1 表示至少 10% 的事件必须压缩
    。
    """
    """要压缩的视图的最小比例。 低于此阈值的凝结
    被视为错误。
    """

    hard_context_reset_max_retries: int = Field(default=5, gt=0)
    """在引发错误之前尝试执行硬上下文重置的次数。"""

    hard_context_reset_context_scaling: float = Field(default=0.8, gt=0.0, lt=1.0)
    """执行硬上下文复位时，如果汇总失败，则减少max
    每个事件字符串的大小由该因子和重试决定。
    """

    @model_validator(mode="after")
    def validate_keep_first_vs_max_size(self):
        events_from_tail = self.max_size // 2 - self.keep_first - 1
        if events_from_tail <= 0:
            raise ValueError(
                "keep_first must be less than max_size // 2 to leave room for "
                "condensation"
            )
        return self

    @model_validator(mode="after")
    def _disable_streaming_for_summary(self):
        # 摘要被整个消耗，没有 on_token 回调，而流式传输 LLM 需要。 禁用流式传输一次，以
        # 便覆盖每个摘要路径。 model_copy 是非变异的并且共享 usage_id/指标，因此摘要
        # token 仍归因于对话。 要求流式传输的提供者可以豁免：法典 API 要求
        #
        # stream=True, and the responses() method drains the stream internally
        # 没有 on_token 回调。
        if self.llm.stream and not self.llm.requires_streaming:
            self.llm = self.llm.model_copy(update={"stream": False})
        return self

    def handles_condensation_requests(self) -> bool:
        return True

    def get_llm(self) -> LLM | None:
        """上下文压缩器使用的 LLM（如果有）。"""
        return self.llm

    def _effective_max_tokens(self, agent_llm: LLM | None) -> int | None:
        """返回触发基于 token 的上下文压缩的有效 token 上限。

        采取更严格的(i.e. 上下文压缩器配置的较小）
        ``max_tokens``和智能体LLM的有效输入限制。 ``agent_llm`` 在公共 API 中是可选的
         -- 只评估请求/事件压力的调用者可以传
        递 ``None`` -- 在这种情况下，只有上下文压缩器's own ``max_tokens`` 适用。

        未配置限制时返回 ``None``。
        """
        limits = [
            limit
            for limit in (
                self.max_tokens,
                agent_llm.effective_max_input_tokens if agent_llm is not None else None,
            )
            if limit is not None
        ]
        return min(limits) if limits else None

    def get_condensation_reasons(
        self, view: View, agent_llm: LLM | None = None
    ) -> set[Reason]:
        """确定应该压缩视图的原因。

        Args:
            view: 目前的观点来评价。
            agent_llm: 智能体使用 LLM。 如果需要 token 计数，则为必需。

        Returns:
            一组原因枚举，指示为什么需要上下文压缩。
        """
        reasons = set()

        # 原因 1：未处理的上下文压缩请求。 该视图在处理事件流时处理这些请求的检测。
        #
        if view.unhandled_condensation_request:
            reasons.add(Reason.REQUEST)

        # 原因 2：提供了 token 限制并超出了限制。
        max_tokens = self._effective_max_tokens(agent_llm)
        if max_tokens is not None and agent_llm is not None:
            total_tokens = get_total_token_count(view.events, agent_llm)
            if total_tokens > max_tokens:
                logger.info(
                    "Condenser token limit exceeded: total_tokens=%d max_tokens=%d "
                    "events=%d",
                    total_tokens,
                    max_tokens,
                    len(view),
                )
                reasons.add(Reason.TOKENS)

        # 原因 3：视图超过事件数量的最大大小。
        if len(view) > self.max_size:
            reasons.add(Reason.EVENTS)

        return reasons

    def condensation_requirement(
        self, view: View, agent_llm: LLM | None = None
    ) -> CondensationRequirement | None:
        reasons = self.get_condensation_reasons(view, agent_llm)

        # 没有理由 => 不需要上下文压缩。
        if reasons == set():
            return None

        # token 压力是硬性要求基准测试使用固定本地模型运行的脚本上下文发送下一个请求可能
        # 会在恢复路径有机会运行之前就失败。 将事件计数压力视为软压力，因为该阈值只是历
        # 史管理启发式的。
        #
        if Reason.TOKENS in reasons:
            return CondensationRequirement.HARD

        # 如果剩下的原因是资源限制，我们可以将它们视为软需求。 我们希望尽可能压缩，但上
        # 下文窗口中仍然有空间，否则我们也会看到 Reason.REQUEST。
        #
        resource_reasons = {Reason.EVENTS}
        if reasons.issubset(resource_reasons):
            return CondensationRequirement.SOFT

        # 请求——无论它们来自用户还是智能体——始终是硬性要求。 我们现在需要压缩，因为：
        # 1. 用户期望它
        # 2. 智能体在上下文窗口中没有更多空间，无法继续
        if Reason.REQUEST in reasons:
            return CondensationRequirement.HARD

    def _build_summary_messages(self, event_strings: Sequence[str]) -> list[Message]:
        """构建发送到摘要 LLM 的消息。

        总结指令以发送 ``system`` 消息和总结事件的 ``user`` message. 将角色拆分后，控
        制指令留在提供者的手中
        ``instructions``/``system`` 槽和事件载荷在 ``input``/``user`` 槽，是 Chat
        Completions 和
        Responses 的标准形状 APIs.
        """
        prompt_dir = os.path.join(os.path.dirname(__file__), "prompts")
        system_prompt = render_template(prompt_dir, "summarizing_system.j2")
        events_prompt = render_template(
            prompt_dir, "summarizing_events.j2", events=event_strings
        )
        return [
            Message(role="system", content=[TextContent(text=system_prompt)]),
            Message(role="user", content=[TextContent(text=events_prompt)]),
        ]

    def _generate_condensation(
        self,
        forgotten_events: Sequence[LLMConvertibleEvent],
        summary_offset: int,
        max_event_str_length: int | None = None,
    ) -> Condensation:
        """利用上下文压缩器的LLM生成上下文压缩来总结遗忘
        事件。

        Args:
            forgotten_events: 要总结的事件列表。
            summary_offset: 应插入摘要事件的索引。
            max_event_str_length: 每个事件字符串的可选最大长度。 如果
                如果事件字符串长于此，则将被截断。

        Returns:
            Condensation: 生成的上下文压缩对象。

        Raises:
            ValueError: 如果 forgotten_events 为空（0个事件合并）。
        """
        assert len(forgotten_events) > 0, "No events to condense."

        # 将事件转换为模板的字符串
        event_strings = [
            maybe_truncate(str(forgotten_event), truncate_after=max_event_str_length)
            for forgotten_event in forgotten_events
        ]

        messages = self._build_summary_messages(event_strings)

        # 不要显式传递 extra_body。 仅当LLM非空时才处理转发litellm_extra_body。
        #
        try:
            llm_response = self.llm.generate(messages=messages, store=False)
        except Exception as e:
            raise NoCondensationAvailableException(
                f"Summarization LLM call failed: {e}"
            ) from e

        # 从LLMResponse消息中提取摘要
        summary = None
        if llm_response.message.content:
            first_content = llm_response.message.content[0]
            if isinstance(first_content, TextContent):
                summary = first_content.text

        return Condensation(
            forgotten_event_ids={event.id for event in forgotten_events},
            summary=summary,
            summary_offset=summary_offset,
            llm_response_id=llm_response.id,
        )

    def _get_forgotten_events(
        self, view: View, agent_llm: LLM | None = None
    ) -> tuple[Sequence[LLMConvertibleEvent], int]:
        """确定要忘记的事件和摘要偏移。

        依靠上下文压缩原因来确定我们需要删除为了多少事件来维持我们的资源限制。 使用操
        作索引来确保遗忘范围尊重原子单元边界。

        Args:
            view: 从中识别被遗忘事件的当前视图。
            agent_llm: 智能体使用的 LLM，是基于 token 的计算所需的。

        Returns:
            一个元组（要忘记的事件，summary_offset）。
        """
        reasons = self.get_condensation_reasons(view, agent_llm=agent_llm)
        assert reasons != set(), "No condensation reasons found."

        suffix_events_to_keep: set[int] = set()

        if Reason.REQUEST in reasons:
            target_size = len(view) // 2
            suffix_events_to_keep.add(target_size - self.keep_first - 1)

        if Reason.EVENTS in reasons:
            target_size = self.max_size // 2
            suffix_events_to_keep.add(target_size - self.keep_first - 1)

        if Reason.TOKENS in reasons:
            # 计算我们需要消除的 token 数量，使其低于有效 max_tokens 值的一半。 我们知道
            # 两者都不在这里 None，因为没有它们我们就不可能拥有 Reason.TOKENS。
            #
            max_tokens = self._effective_max_tokens(agent_llm)
            assert max_tokens is not None
            assert agent_llm is not None

            total_tokens = get_total_token_count(view.events, agent_llm)
            tokens_to_reduce = total_tokens - (max_tokens // 2)

            suffix_events_to_keep.add(
                get_suffix_length_for_token_reduction(
                    events=view.events[self.keep_first :],
                    llm=agent_llm,
                    token_reduction=tokens_to_reduce,
                    base_events=view.events[: self.keep_first],
                )
            )

        # 我们可能有多种压缩原因，因此选择最严格的上下文压缩以确保满足所有资源限制。
        #
        events_from_tail = min(suffix_events_to_keep)

        # 计算朴素遗忘终点（不考虑原子边界）
        naive_end = len(view) - events_from_tail

        # 决不能忘记前导 SystemPromptEvent，否则压缩视图将打开并显示非系统消息。 将遗忘
        # 范围的起点放在刚刚过去的位置（这也涵盖 keep_first=0）。
        #
        protected_prefix = self.keep_first
        system_idx = _leading_system_prompt_index(view.events)
        if system_idx is not None:
            protected_prefix = max(protected_prefix, system_idx + 1)

        # 查找实际forgetting_start：最小操纵索引>=protected_prefix
        forgetting_start = view.manipulation_indices.find_next(protected_prefix)

        # 查找实际forgetting_end：最小操纵索引>=naive_end
        forgetting_end = view.manipulation_indices.find_next(naive_end)

        # 使用边界感知索引提取要忘记的事件
        forgotten_events = view[forgetting_start:forgetting_end]

        # 摘要偏移量与 forgetting_start 相同
        return forgotten_events, forgetting_start

    @observe(ignore_inputs=["view", "agent_llm"])
    def hard_context_reset(
        self,
        view: View,
        agent_llm: LLM | None = None,  # noqa: ARG002
    ) -> Condensation | None:
        """通过汇总视图中的所有事件来执行硬上下文重置。

        根据硬上下文重置的触发方式，这可能会失败（e.g.，如果视图太大而汇总 LLM 无法处
        理）。 在这种情况下，我们会不断删减内容，直到生成摘要。
        """
        # 保留前导 SystemPromptEvent：它必须保留在视图的头部，以便请求仍然以系统消息打开
        # 。 总结*之后*的事件，并将摘要插入到其后面。
        #
        system_idx = _leading_system_prompt_index(view.events)
        preserve = (system_idx + 1) if system_idx is not None else 0
        forgotten_events = view.events[preserve:]
        summary_offset = preserve

        max_event_str_length: int | None = None
        attempts_remaining: int = self.hard_context_reset_max_retries

        while attempts_remaining > 0:
            try:
                return self._generate_condensation(
                    forgotten_events=forgotten_events,
                    summary_offset=summary_offset,
                    max_event_str_length=max_event_str_length,
                )
            except Exception as e:
                # 如果我们还没有设置 max_event_str_length，请将其设置为最大事件字符串长
                # 度。
                #
                if max_event_str_length is None:
                    max_event_str_length = max(len(str(event)) for event in view.events)

                # 由于汇总失败，将max_event_str_length减少20%
                assert max_event_str_length is not None
                max_event_str_length = int(
                    max_event_str_length * self.hard_context_reset_context_scaling
                )

                # 记录异常，以便我们可以跟踪这些故障
                logger.warning(
                    f"Hard context reset summarization failed with exception: {e}. "
                    f"Reducing max event size to {max_event_str_length} and retrying."
                )

            attempts_remaining -= 1

        logger.error("Hard context reset summarization failed after multiple attempts.")
        return None

    @observe(ignore_inputs=["view", "agent_llm"])
    def get_condensation(
        self, view: View, agent_llm: LLM | None = None
    ) -> Condensation:
        # 上下文压缩取决于我们要删除的事件和之前的摘要。 如果我们未能找到一组适当的事件
        # 来忘记引发异常，以便对话可以继续进行，直到情况发生变化。
        #
        try:
            forgotten_events, summary_offset = self._get_forgotten_events(
                view, agent_llm=agent_llm
            )
        except ValueError as e:
            raise NoCondensationAvailableException(
                "Unable to compute forgotten events"
            ) from e

        if not forgotten_events:
            raise NoCondensationAvailableException(
                "Cannot condense 0 events. This typically occurs when a tool loop "
                "spans almost the entire view, leaving no valid range for forgetting "
                "events. Consider adjusting keep_first or max_size parameters."
            )

        if len(forgotten_events) < len(view) * self.minimum_progress:
            raise NoCondensationAvailableException(
                "Cannot apply condensation: events forgotten below minimum progress "
                "threshold."
            )

        return self._generate_condensation(
            forgotten_events=forgotten_events,
            summary_offset=summary_offset,
        )

    # ------------------------------------------------------------------
    # 异步变种
    # ------------------------------------------------------------------

    async def _agenerate_condensation(
        self,
        forgotten_events: Sequence[LLMConvertibleEvent],
        summary_offset: int,
        max_event_str_length: int | None = None,
    ) -> Condensation:
        """异步：meth:`_generate_condensation` 的变体。"""
        assert len(forgotten_events) > 0, "No events to condense."

        event_strings = [
            maybe_truncate(str(fe), truncate_after=max_event_str_length)
            for fe in forgotten_events
        ]

        messages = self._build_summary_messages(event_strings)

        try:
            llm_response = await self.llm.agenerate(messages=messages, store=False)
        except Exception as e:
            raise NoCondensationAvailableException(
                f"Summarization LLM call failed: {e}"
            ) from e

        summary = None
        if llm_response.message.content:
            first_content = llm_response.message.content[0]
            if isinstance(first_content, TextContent):
                summary = first_content.text

        return Condensation(
            forgotten_event_ids={event.id for event in forgotten_events},
            summary=summary,
            summary_offset=summary_offset,
            llm_response_id=llm_response.id,
        )

    async def aget_condensation(
        self, view: View, agent_llm: LLM | None = None
    ) -> Condensation:
        """异步：meth:`get_condensation` 的变体。"""
        try:
            forgotten_events, summary_offset = self._get_forgotten_events(
                view, agent_llm=agent_llm
            )
        except ValueError as e:
            raise NoCondensationAvailableException(
                "Unable to compute forgotten events"
            ) from e

        if not forgotten_events:
            raise NoCondensationAvailableException(
                "Cannot condense 0 events. This typically occurs when a tool loop "
                "spans almost the entire view, leaving no valid range for "
                "forgetting events. Consider adjusting keep_first or max_size "
                "parameters."
            )

        if len(forgotten_events) < len(view) * self.minimum_progress:
            raise NoCondensationAvailableException(
                "Cannot apply condensation: events forgotten below minimum "
                "progress threshold."
            )

        return await self._agenerate_condensation(
            forgotten_events=forgotten_events,
            summary_offset=summary_offset,
        )

    async def ahard_context_reset(
        self,
        view: View,
        agent_llm: LLM | None = None,  # noqa: ARG002
    ) -> Condensation | None:
        """异步：meth:`hard_context_reset` 的变体。"""
        # 保留前导 SystemPromptEvent（参见 hard_context_reset）。
        system_idx = _leading_system_prompt_index(view.events)
        preserve = (system_idx + 1) if system_idx is not None else 0
        forgotten_events = view.events[preserve:]
        summary_offset = preserve

        max_event_str_length: int | None = None
        attempts_remaining: int = self.hard_context_reset_max_retries

        while attempts_remaining > 0:
            try:
                return await self._agenerate_condensation(
                    forgotten_events=forgotten_events,
                    summary_offset=summary_offset,
                    max_event_str_length=max_event_str_length,
                )
            except Exception as e:
                if max_event_str_length is None:
                    max_event_str_length = max(len(str(ev)) for ev in view.events)
                assert max_event_str_length is not None
                max_event_str_length = int(
                    max_event_str_length * self.hard_context_reset_context_scaling
                )
                logger.warning(
                    f"Hard context reset summarization failed: {e}. "
                    f"Reducing max event size to {max_event_str_length}."
                )
            attempts_remaining -= 1

        logger.error("Hard context reset summarization failed after multiple attempts.")
        return None


# 标准总结的尺寸调整上下文压缩器。 保留在这里，以便默认的智能体和生成的子智能体保留在同
# 步中。
#
_DEFAULT_MAX_SIZE: Final[int] = 80
_DEFAULT_KEEP_FIRST: Final[int] = 4


def default_condenser(llm: LLM) -> LLMSummarizingCondenser:
    """默认使用智能体和子智能体的标准汇总上下文压缩器。"""
    return LLMSummarizingCondenser(
        llm=llm, max_size=_DEFAULT_MAX_SIZE, keep_first=_DEFAULT_KEEP_FIRST
    )
