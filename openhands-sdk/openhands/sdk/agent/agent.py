from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import Field, PrivateAttr, ValidationError, model_validator

import openhands.sdk.security.analyzer as analyzer
import openhands.sdk.security.risk as risk
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.agent.critic_mixin import CriticMixin
from openhands.sdk.agent.parallel_executor import ParallelToolExecutor
from openhands.sdk.agent.response_dispatch import (
    LLMResponseType,
    ResponseDispatchMixin,
    classify_response,
)
from openhands.sdk.agent.stream_context import StreamContext
from openhands.sdk.agent.utils import (
    aprepare_llm_messages,
    fix_malformed_tool_arguments,
    normalize_tool_call,
    parse_tool_call_arguments,
    prepare_llm_messages,
)
from openhands.sdk.context.prompts.presets import PromptPreset, create_registry
from openhands.sdk.conversation import (
    CancellationToken,
    ConversationCallbackType,
    ConversationState,
    ConversationTokenCallbackType,
    LocalConversation,
)
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    Event,
    MessageEvent,
    ObservationEvent,
    SystemPromptEvent,
    TokenEvent,
    UserRejectObservation,
)
from openhands.sdk.event.condenser import (
    Condensation,
    CondensationRequest,
)
from openhands.sdk.event.error_classification import AGENT_OUTCOME
from openhands.sdk.event.security import SecurityAnalysisEvent
from openhands.sdk.llm import (
    LLM,
    ImageContent,
    LLMResponse,
    Message,
    MessageToolCall,
    ReasoningItemModel,
    RedactedThinkingBlock,
    TextContent,
    ThinkingBlock,
)
from openhands.sdk.llm.call_context import llm_call_context_scope
from openhands.sdk.llm.exceptions import (
    FunctionCallValidationError,
    LLMContentPolicyViolationError,
    LLMContextWindowExceedError,
    LLMMalformedConversationHistoryError,
)
from openhands.sdk.llm.router.base import RouterLLM
from openhands.sdk.logger import get_logger
from openhands.sdk.observability.laminar import (
    maybe_init_laminar,
    observe,
    record_tool_result,
    should_enable_observability,
)
from openhands.sdk.observability.utils import extract_action_name
from openhands.sdk.tool import (
    Action,
    Observation,
)


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLMCallContext
    from openhands.sdk.tool import ToolDefinition
from openhands.sdk.mcp.tool import MCPToolDefinition
from openhands.sdk.tool.builtins import (
    FinishAction,
    FinishTool,
    ThinkAction,
)
from openhands.sdk.tool.builtins.vision_inspect import VISION_INSPECT_TOOL_NAME


logger = get_logger(__name__)
maybe_init_laminar()


def _tool_has_summary_param(tool: ToolDefinition) -> bool:
    """如果工具自己的模式将 ``summary`` 声明为参数，则返回 True。

    检查常规工具 action_type model_fields 和 MCP 工具 inputSchema，以便
    ``_extract_summary`` 可以避免在
    属于该工具时弹出该字段 (e.g. Jira 的票证标题）。
    """
    if "summary" in tool.action_type.model_fields:
        return True
    if isinstance(tool, MCPToolDefinition):
        props = tool.mcp_tool.inputSchema.get("properties", {})
        if "summary" in props:
            return True
    return False


# init_state 防御检查期间要扫描的最大事件数。 SystemPromptEvent 必须出现在此前缀内（索引
#  0 或 1）。
#
INIT_STATE_PREFIX_SCAN_WINDOW = 3


def _latest_user_message_contains_image(messages: list[Message]) -> bool:
    """检查最近的用户消息是否包含图片内容。

    逆序扫描消息列表，查找最新的用户消息，并检查是否包含图片附件。

    Args:
        messages: 要搜索的对话消息列表。

    Returns:
        如果最近的用户消息包含图像，则为 True，否则为 False。 如果未找到用户消息，则
        返回 False。
    """
    for message in reversed(messages):
        if message.role == "user":
            return message.contains_image
    return False


def _non_multimodal_image_message(model: str) -> Message:
    """当图像发送到非视觉模型时创建错误消息。

    构建一个用户友好的助手消息，解释当前模型不支持图像理解，并建议用户切换到多模态模
    型。

    Args:
        model: 当前不支持视觉的模型名称。

    Returns:
        包含带有错误解释的助理响应的消息对象。
    """
    return Message(
        role="assistant",
        content=[
            TextContent(
                text=(
                    "I received your image, but the currently selected model "
                    f"({model}) does not support image understanding. Please "
                    "switch to a multimodal model to analyze the image."
                )
            )
        ],
    )


def _replace_latest_user_images_with_references(
    messages: list[Message],
) -> list[Message]:
    """替换最近包含图像的用户消息中的图像。

    向后搜索，跳过没有图像的用户消息。 每个图像 URL 都成为对
    inspect_image_with_vision 工具的文本引用，并在所选消息中具有从零开始的图像
    索引。

    Args:
        messages: 要处理的对话消息列表。

    Returns:
        复制所选消息并替换其图像的新列表。 其他消息和非图像内容不变。 如果没有用户消
        息包含图像，则返回原始列表的浅表副本。
    """
    rewritten = list(messages)
    for index in range(len(rewritten) - 1, -1, -1):
        message = rewritten[index]
        if message.role != "user" or not message.contains_image:
            continue

        image_index = 0
        content: list[TextContent | ImageContent] = []
        for item in message.content:
            if isinstance(item, ImageContent):
                for _ in item.image_urls:
                    content.append(
                        TextContent(
                            text=(
                                f"[Image {image_index} is attached to the latest "
                                "user message. Use the inspect_image_with_vision "
                                f"tool with image_index={image_index} to inspect it.]"
                            )
                        )
                    )
                    image_index += 1
            else:
                content.append(item)

        rewritten[index] = message.model_copy(update={"content": content})
        break
    return rewritten


def _should_handle_non_multimodal_image_input(
    llm: LLM, messages: list[Message]
) -> bool:
    if isinstance(llm, RouterLLM):
        return False
    return _latest_user_message_contains_image(messages) and not llm.vision_is_active()


@dataclass(frozen=True, slots=True)
class _ActionBatch:
    """准备执行一批操作的不可变结果。

    拥有工具调用批次的整个生命周期：准备（截断、阻塞动作分区、执行），事件发布，以及
    批次之后的状态转换。 智能体特定逻辑（迭代细化、状态突变）通过可调用注入，因此批处
    理
    与智能体类保持解耦。
    """

    action_events: list[ActionEvent]
    has_finish: bool
    blocked_reasons: dict[str, str] = field(default_factory=dict)
    results_by_id: dict[str, list[Event]] = field(default_factory=dict)

    @staticmethod
    def _truncate_at_finish(
        action_events: list[ActionEvent],
    ) -> tuple[list[ActionEvent], bool]:
        """
        返回 (events[:finish+1], True) 或 (events, False)。 丢弃并记录 FinishTool 之
        后的所有调用。
        """
        finish_idx = next(
            (
                i
                for i, ae in enumerate(action_events)
                if ae.tool_name == FinishTool.name
            ),
            None,
        )
        if finish_idx is None:
            return action_events, False

        discarded = action_events[finish_idx + 1 :]
        if discarded:
            names = [ae.tool_name for ae in discarded]
            logger.warning(
                f"Discarding {len(discarded)} tool call(s) "
                f"after FinishTool: {', '.join(names)}"
            )
        return action_events[: finish_idx + 1], True

    @classmethod
    def prepare(
        cls,
        action_events: list[ActionEvent],
        state: ConversationState,
        executor: ParallelToolExecutor,
        tool_runner: Callable[[ActionEvent], list[Event]],
        tools: dict[str, ToolDefinition] | None = None,
        cancel_token: CancellationToken | None = None,
        span_owner: object | None = None,
    ) -> _ActionBatch:
        """截断、分区阻塞操作，执行REST，返回批处理。"""
        action_events, has_finish = cls._truncate_at_finish(action_events)

        blocked_reasons: dict[str, str] = {}
        executable: list[ActionEvent] = []
        for ae in action_events:
            reason = state.pop_blocked_action(ae.id)
            if reason is not None:
                blocked_reasons[ae.id] = reason
            else:
                executable.append(ae)

        executed_results = executor.execute_batch(
            executable,
            tool_runner,
            tools,
            cancel_token,
            span_owner=span_owner,
        )
        results_by_id = dict(zip([ae.id for ae in executable], executed_results))

        return cls(
            action_events=action_events,
            has_finish=has_finish,
            blocked_reasons=blocked_reasons,
            results_by_id=results_by_id,
        )

    @classmethod
    async def aprepare(
        cls,
        action_events: list[ActionEvent],
        state: ConversationState,
        executor: ParallelToolExecutor,
        tool_runner: Callable[[ActionEvent], list[Event]],
        tools: dict[str, ToolDefinition] | None = None,
        cancel_token: CancellationToken | None = None,
        span_owner: object | None = None,
    ) -> _ActionBatch:
        """异步：meth:`prepare` 的变体。

        使用：meth:`ParallelToolExecutor.aexecute_batch` 以便每个工具调用在其自己的线
        程中运行，并且通过：func:
        `asyncio.gather` 同时调度多个调用。
        """
        action_events, has_finish = cls._truncate_at_finish(action_events)

        blocked_reasons: dict[str, str] = {}
        executable: list[ActionEvent] = []
        for ae in action_events:
            reason = state.pop_blocked_action(ae.id)
            if reason is not None:
                blocked_reasons[ae.id] = reason
            else:
                executable.append(ae)

        executed_results = await executor.aexecute_batch(
            executable,
            tool_runner,
            tools,
            cancel_token,
            span_owner=span_owner,
        )
        results_by_id = dict(zip([ae.id for ae in executable], executed_results))

        return cls(
            action_events=action_events,
            has_finish=has_finish,
            blocked_reasons=blocked_reasons,
            results_by_id=results_by_id,
        )

    def emit(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
    ) -> None:
        """按原始操作顺序发出所有事件。"""
        for ae in self.action_events:
            reason = self.blocked_reasons.get(ae.id)
            if reason is not None:
                logger.info(f"Action '{ae.tool_name}' blocked by hook: {reason}")
                rejection = UserRejectObservation(
                    action_id=ae.id,
                    tool_name=ae.tool_name,
                    tool_call_id=ae.tool_call_id,
                    rejection_reason=reason,
                    rejection_source="hook",
                )
                record_tool_result(
                    conversation,
                    name=extract_action_name(ae),
                    tool_call_id=ae.tool_call_id,
                    tool_input=ae.action,
                    tool_output=rejection.to_llm_message(),
                )
                on_event(rejection)
            else:
                for event in self.results_by_id[ae.id]:
                    on_event(event)

    def finalize(
        self,
        on_event: ConversationCallbackType,
        check_iterative_refinement: Callable[[ActionEvent], tuple[bool, str | None]],
        mark_finished: Callable[[], None],
    ) -> None:
        """FinishTool 之后的过渡状态，或注入迭代细化后续操作。

        Args:
            on_event: 回调用于发出事件。
            check_iterative_refinement: 返回（should_continue，后续）
                对于 FinishTool 动作事件。
            mark_finished: 调用设置会话执行状态
                当智能体完成时，到 FINISHED。
        """
        # 没有什么可以确定的：没有FinishTool，或者它被钩子挡住了。
        if not self.has_finish or self.action_events[-1].id in self.blocked_reasons:
            return

        should_continue, followup = check_iterative_refinement(self.action_events[-1])
        if should_continue and followup:
            on_event(
                MessageEvent(
                    source="user",
                    llm_message=Message(
                        role="user",
                        content=[TextContent(text=followup)],
                    ),
                )
            )
        else:
            mark_finished()


class Agent(CriticMixin, ResponseDispatchMixin, AgentBase):
    """OpenHands 的主要智能体实现。

    智能体类提供运行 AI 智能体的核心功能，可以与工具交互、处理消息和执行操作。 它继承
    自AgentBase并实现了智能体执行逻辑。 CriticMixin 提供了与
    评论家相关的功能。

    Attributes:
        llm: 用于推理的语言模型实例。
        tools: 智能体可用的工具列表。
        system_prompt: 内联系统提示词字符串。 当提供智能体时
            逐字使用此文本而不是从模板渲染。 与非默认 ``system_prompt_filename`` 互斥
            。
            **不推荐**，除非您知道自己在做什么（e.g。
            为完全不同的任务定制智能体行为）——这将覆盖 OpenHands 的内置系统指令。
        system_prompt_filename: Jinja2 模板文件名相对于解析
            智能体的提示词目录，或绝对路径。 默认为
            ``"system_prompt.j2"``.
        system_prompt_kwargs: 额外的 kwargs 转发到 Jinja2 模板。

    Example:
        ```python
        from openhands.sdk import LLM, Agent, Tool
        from pydantic import SecretStr

        llm = LLM(model="gpt-5.6", api_key=SecretStr("key"))
        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        agent = Agent(llm=llm, tools=tools)
        ```

        要完全覆盖系统提示词：

            agent = Agent(
                llm=llm,
                tools=tools,
                system_prompt="You are a helpful coding assistant.",
            )
    """

    persona: str | None = Field(
        default=None,
        description=(
            "Persona text that replaces OpenHands' built-in persona and "
            "coding-workflow sections of the system prompt. Capability and policy "
            "sections (memory, security policy, risk assessment, browser, external "
            "services, process management, model-specific guidance) and the dynamic "
            "context still apply. Ignored when `system_prompt` is set; a custom "
            "template receives it as the `persona` kwarg."
        ),
    )
    _parallel_executor: ParallelToolExecutor = PrivateAttr(
        default_factory=ParallelToolExecutor
    )

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        self._parallel_executor = ParallelToolExecutor(
            max_workers=self.tool_concurrency_limit
        )

    def _resolved_template_kwargs(self) -> dict[str, object]:
        template_kwargs = super()._resolved_template_kwargs()
        if self.persona is not None:
            template_kwargs["persona"] = self.persona
        return template_kwargs

    @model_validator(mode="before")
    @classmethod
    def _add_security_prompt_as_default(cls, data):
        """确保在初始化之前始终设置 llm_security_analyzer=True。"""
        if not isinstance(data, dict):
            return data

        kwargs = data.get("system_prompt_kwargs") or {}
        if not isinstance(kwargs, dict):
            kwargs = {}

        kwargs.setdefault("llm_security_analyzer", True)
        data["system_prompt_kwargs"] = kwargs
        return data

    def init_state(
        self,
        state: ConversationState,
        on_event: ConversationCallbackType,
    ) -> None:
        """初始化对话状态。

        不变量通过此方法强制执行：
        - 如果 SystemPromptEvent 已经存在，则它必须在前 3 个事件内（实际上是索引 0 或
         1； 索引 2 包含在扫描窗口中，用于检测系统之前
        出现的用户消息提示词)。
        - 用户 MessageEvent 不应出现在 SystemPromptEvent 之前。

        这些不变量保持下游组件（如上下文压缩器，UI 等）的事件顺序可预测，并且防止在初
        始化过程中意外地生成整个事件历史。
        """
        self._initialize(state)

        # 防御性检查：分析状态以检测意外的初始化场景。这些检查有助于诊断与懒加载和事件顺
        # 序相关的问题
        # 请参阅： https://github.com/OpenHands/software-agent-sdk/issues/1785
        #
        # 注意：len() 是 EventLog 的 O(1)（文件支持的实现）。
        event_count = len(state.events)

        # 注意：state.events 故意是 EventsListBase （类似序列），而不是
        # 一个简单的列表。 避免通过此处的 list(state.events) 实现完整历史记录（对话可以
        # 达到 30k+ 事件）。
        #
        # 不变量：当调用init_state时，SystemPromptEvent（如果存在）必须是
        # 在索引 0 或 1 处。
        #
        # 理由：
        # - 本地对话开始为空，init_state 负责将 SystemPromptEvent 添加为第一个事件。
        # - 远程对话可能会收到初始 ConversationStateUpdateEvent
        #   from the agent-server immediately after subscription. In a typical remote
        #   您可能会看到会话前缀：
        #     [ConversationStateUpdateEvent, SystemPromptEvent, MessageEvent, ...]
        #
        # 我们有意只检查前几个事件（对于本地和远程来说都很便宜）来强制执行此不变量。
        #
        prefix_events = state.events[:INIT_STATE_PREFIX_SCAN_WINDOW]

        has_system_prompt = any(isinstance(e, SystemPromptEvent) for e in prefix_events)
        has_user_message = any(
            isinstance(e, MessageEvent) and e.source == "user" for e in prefix_events
        )
        # 用于调试初始化顺序问题的日志状态
        logger.debug(
            f"init_state called: conversation_id={state.id}, "
            f"event_count={event_count}, "
            f"has_system_prompt={has_system_prompt}, "
            f"has_user_message={has_user_message}"
        )

        if has_system_prompt:
            # 恢复/恢复对话是正常的：系统提示词已存在意味着此对话之前已初始化。
            #
            logger.debug(
                "init_state: SystemPromptEvent already present; skipping init. "
                f"conversation_id={state.id}, event_count={event_count}."
            )
            return

        # 断言：用户消息不应出现在系统提示词之前。
        #
        # 注意：这是仅基于前几个事件的尽力检查。
        # 远程对话可以在开头附近包含 ConversationStateUpdateEvent，因此我们扫描一个小的
        # 前缀窗口。
        #
        if has_user_message:
            event_types = [type(e).__name__ for e in prefix_events]
            logger.error(
                f"init_state: User message found in prefix before SystemPromptEvent! "
                f"conversation_id={state.id}, prefix_events={event_types}"
            )
            raise AssertionError(
                "Unexpected state: user message exists before SystemPromptEvent. "
                f"conversation_id={state.id}, event_count={event_count}, "
                f"prefix_event_types={event_types}."
            )

        # 准备具有单独的静态和动态内容的系统消息。 的 dynamic_context 作为系统消息中的第
        # 二部分内容块（不带缓存标记），以实现跨对话功能提示词静态系统的缓存提示词。
        #
        # 智能体从对话的 secret_registry 中提取机密，将其包含在动态上下文中。 这可确保机
        # 密名称和描述出现在系统提示词中。
        #
        dynamic_context = self.get_dynamic_context(state)
        event = SystemPromptEvent(
            source="agent",
            system_prompt=TextContent(text=self.static_system_message),
            # 工具存储为 ToolDefinition 对象，并在 LLM 完成期间使用 security_risk 参数转
            # 换为 OpenAI 格式。 智能体调用总是会暴露工具模式中的安全风险预测。
            #
            tools=list(self.tools_map.values()),
            dynamic_context=TextContent(text=dynamic_context)
            if dynamic_context
            else None,
        )
        on_event(event)

    def get_dynamic_context(self, state: ConversationState) -> str | None:
        """获取系统提示词的动态上下文，包括状态中的机密。

        该方法从会话的secret_registry中拉取机密，并与agent_context合并，构建系统提示
        词的动态部分，该部分由默认的注册表中的动态层级组成。
         ``_build_prompt_context`` 再现遗产 no-agent_context
        path: 没有 agent_context 但存在注册表机密，它解决了
        默认 ``AgentContext()``，因此机密（及其日期时间）仍然呈现。

        Args:
            state: 包含secret_registry的对话状态。

        Returns:
            动态上下文字符串，如果未配置上下文，则为 None。
        """
        # 从对话的 secret_registry 获取机密信息
        secret_infos = state.secret_registry.get_secret_infos()

        ctx = self._build_prompt_context(additional_secret_infos=secret_infos)
        # 动态层与预设无关； 像以前一样，回退到自定义 Jinja 模板的默认层（预设 None）。
        #
        preset = self._prompt_preset or PromptPreset.DEFAULT
        return create_registry(preset).build(ctx).dynamic

    @staticmethod
    def _mark_conversation_finished(state: ConversationState) -> None:
        state.execution_status = ConversationExecutionStatus.FINISHED

    def _execute_actions(
        self,
        conversation: LocalConversation,
        action_events: list[ActionEvent],
        on_event: ConversationCallbackType,
    ) -> None:
        """准备批次、发出结果并处理完成。"""
        state = conversation.state
        batch = _ActionBatch.prepare(
            action_events,
            state=state,
            executor=self._parallel_executor,
            tool_runner=lambda ae: self._execute_action_event(conversation, ae),
            tools=self.tools_map,
            cancel_token=conversation.cancel_token,
            span_owner=conversation,
        )
        batch.emit(conversation, on_event)
        batch.finalize(
            on_event=on_event,
            check_iterative_refinement=lambda ae: (
                self._check_iterative_refinement(conversation, ae)
            ),
            mark_finished=lambda: self._mark_conversation_finished(state),
        )

    async def _aexecute_actions(
        self,
        conversation: LocalConversation,
        action_events: list[ActionEvent],
        on_event: ConversationCallbackType,
    ) -> None:
        """异步：meth:`_execute_actions` 的变体。

        每个工具调用在其自己的线程中运行
        :meth:`ParallelToolExecutor.aexecute_batch`，给出事件
        在每个工具调用之间循环一个 ``await`` 边界。
        """
        state = conversation.state
        batch = await _ActionBatch.aprepare(
            action_events,
            state=state,
            executor=self._parallel_executor,
            tool_runner=lambda ae: self._execute_action_event(conversation, ae),
            tools=self.tools_map,
            cancel_token=conversation.cancel_token,
            span_owner=conversation,
        )
        batch.emit(conversation, on_event)
        batch.finalize(
            on_event=on_event,
            check_iterative_refinement=lambda ae: (
                self._check_iterative_refinement(conversation, ae)
            ),
            mark_finished=lambda: self._mark_conversation_finished(state),
        )

    @observe(name="agent.step", ignore_inputs=["state", "on_event"])
    def step(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        call_context = conversation.get_llm_call_context()
        with (
            llm_call_context_scope(call_context),
            StreamContext.open(conversation, on_token) as stream,
        ):
            self._step(conversation, on_event, stream)

    def _step(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        stream: StreamContext,
    ) -> None:
        state = conversation.state
        # 检查待处理的操作（隐式确认）并在对新操作进行采样之前执行它们。
        #
        pending_actions = ConversationState.get_unmatched_actions(state.active_branch())
        if pending_actions:
            logger.info(
                "Confirmation mode: Executing %d pending action(s)",
                len(pending_actions),
            )
            self._execute_actions(conversation, pending_actions, on_event)
            return

        # 检查最后一条用户消息是否被 UserPromptSubmit 挂钩阻止如果是，则跳过处理并将对话
        # 标记为已完成
        #
        if state.last_user_message_id is not None:
            reason = state.pop_blocked_message(state.last_user_message_id)
            if reason is not None:
                logger.info(f"User message blocked by hook: {reason}")
                state.execution_status = ConversationExecutionStatus.FINISHED
                return
        elif state.blocked_messages:
            logger.debug(
                "Blocked messages exist but last_user_message_id is None; "
                "skipping hook check for legacy conversation state."
            )

        # 构建每个对话上下文一次，并通过此步骤中的所有 LLM 调用构建线程（避免 LLM 上共享
        # 可变状态）。
        #
        call_context: LLMCallContext = conversation.get_llm_call_context()

        # 在上下文压缩器决定 token 门限之前，先建立基于路由的运行时元数据（缓存，命中时
        # 不进行 I/O），这样路由模型的实际端点限制驱动上下文压缩的第一步。
        #
        self.llm.resolve_runtime_metadata()

        # 从缓存的增量维护视图中准备 LLM 条消息。 参见
        # https://github.com/OpenHands/software-agent-sdk/issues/3053.
        #
        _messages_or_condensation = prepare_llm_messages(
            state.view, condenser=self.condenser, llm=self.llm
        )

        # 在智能体采样另一个操作之前处理上下文压缩事件
        if isinstance(_messages_or_condensation, Condensation):
            on_event(_messages_or_condensation)
            return

        _messages = _messages_or_condensation

        if _should_handle_non_multimodal_image_input(self.llm, _messages):
            if VISION_INSPECT_TOOL_NAME in self.tools_map:
                logger.info(
                    "Image input received by non-vision model %s; exposing "
                    "image references and vision inspection tool",
                    self.llm.model,
                )
                _messages = _replace_latest_user_images_with_references(_messages)
            else:
                logger.info(
                    "Image input received while selected model does not support "
                    "vision: %s",
                    self.llm.model,
                )
                on_event(
                    MessageEvent(
                        source="agent",
                        llm_message=_non_multimodal_image_message(self.llm.model),
                    )
                )
                state.execution_status = ConversationExecutionStatus.FINISHED
                return

        logger.debug(
            "Sending messages to LLM: "
            f"{json.dumps([m.model_dump() for m in _messages[1:]], indent=2)}"
        )

        try:
            llm_response = self.llm.generate(
                messages=_messages,
                tools=list(self.tools_map.values()),
                store=False,
                add_security_risk_prediction=True,
                on_token=stream.token_callback,
                call_context=call_context,
            )
        except FunctionCallValidationError as e:
            logger.warning(f"LLM generated malformed function call: {e}")
            error_message = MessageEvent(
                source="user",
                llm_message=Message(
                    role="user",
                    content=[TextContent(text=str(e))],
                ),
            )
            on_event(error_message)
            return
        except LLMContentPolicyViolationError as e:
            # 内容策略块是确定性的； 轻推模型并让运行循环继续，而不是发出致命错误。
            #
            logger.warning(f"LLM output blocked by content filter: {e}")
            on_event(
                MessageEvent(
                    source="user",
                    llm_message=Message(
                        role="user",
                        content=[
                            TextContent(
                                text=(
                                    "Your previous response was blocked by the "
                                    "model's content filter. Please continue, "
                                    "rephrasing to avoid the flagged content."
                                )
                            )
                        ],
                    ),
                )
            )
            return
        except LLMMalformedConversationHistoryError as e:
            # 提供程序拒绝当前消息历史记录，因为其结构无效（例如，tool_use/tool_result
            # 配对损坏）。 将其路由到上下文压缩恢复，但保持日志与 True 上下文窗口耗尽不
            # 同，以便上游事件流错误保持可见。
            #
            if (
                self.condenser is not None
                and self.condenser.handles_condensation_requests()
            ):
                logger.warning(
                    "LLM raised malformed conversation history error, "
                    "triggering condensation retry with condensed history: "
                    f"{e}"
                )
                # 增量视图本身可能就是畸形历史的根源。 完全执行重新推导，以便上下文压缩
                # 器在干净的视图上运行。
                #
                state.rebuild_view()
                on_event(CondensationRequest())
                return
            logger.warning(
                "LLM raised malformed conversation history error but no "
                "condenser can handle condensation requests. This usually "
                "indicates an upstream event-stream or resume bug: "
                f"{e}"
            )
            raise e
        except LLMContextWindowExceedError as e:
            # 如果上下文压缩器可用并处理请求，则触发上下文压缩
            if (
                self.condenser is not None
                and self.condenser.handles_condensation_requests()
            ):
                logger.warning(
                    "LLM raised context window exceeded error, triggering condensation"
                )
                on_event(CondensationRequest())
                return
            # 没有可用的上下文压缩器或不处理请求； 记录有用的警告
            self._log_context_window_exceeded_warning()
            raise e

        # LLMResponse 已经包含了转换后的消息和指标快照
        message: Message = llm_response.message
        response_type = classify_response(message)

        match response_type:
            case LLMResponseType.TOOL_CALLS:
                self._handle_tool_calls(
                    message, llm_response, conversation, state, on_event, stream
                )
            case LLMResponseType.CONTENT:
                self._handle_content_response(
                    message, llm_response, conversation, state, on_event, stream
                )
            case LLMResponseType.REASONING_ONLY | LLMResponseType.EMPTY:
                self._handle_no_content_response(
                    message,
                    llm_response,
                    conversation,
                    state,
                    on_event,
                    stream,
                    response_type=response_type,
                )

    @observe(name="agent.astep", ignore_inputs=["state", "on_event"])
    async def astep(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ) -> None:
        """异步：meth:`step` 的变体。

        LLM 完成是通过异步执行的
        ：方法：`LLM.agenerate`。 工具调度用途
        :meth:`_aexecute_actions` 单独运行每个工具调用
        线程通过：func:`asyncio.loop.run_in_executor` 并使用：func:`asyncio.gather`
        安排并行调用，在阻塞工
        具 I/O 期间保持事件循环响应。
        """
        call_context = conversation.get_llm_call_context()
        with (
            llm_call_context_scope(call_context),
            StreamContext.open(conversation, on_token) as stream,
        ):
            await self._astep(conversation, on_event, stream)

    async def _astep(
        self,
        conversation: LocalConversation,
        on_event: ConversationCallbackType,
        stream: StreamContext,
    ) -> None:
        state = conversation.state
        # 检查待处理的操作（隐式确认）
        pending_actions = ConversationState.get_unmatched_actions(state.active_branch())
        if pending_actions:
            logger.info(
                "Confirmation mode: Executing %d pending action(s)",
                len(pending_actions),
            )
            await self._aexecute_actions(conversation, pending_actions, on_event)
            return

        if state.last_user_message_id is not None:
            reason = state.pop_blocked_message(state.last_user_message_id)
            if reason is not None:
                logger.info(f"User message blocked by hook: {reason}")
                state.execution_status = ConversationExecutionStatus.FINISHED
                return
        elif state.blocked_messages:
            logger.debug(
                "Blocked messages exist but last_user_message_id is None; "
                "skipping hook check for legacy conversation state."
            )

        call_context: LLMCallContext = conversation.get_llm_call_context()

        # 在上下文压缩器决定 token 门限之前，先建立基于路由的运行时元数据（缓存，命中时
        # 不进行 I/O），这样路由模型的实际端点限制驱动上下文压缩的第一步。
        #
        await self.llm.aresolve_runtime_metadata()

        # 从缓存的增量维护视图中准备 LLM 条消息。 参见
        # https://github.com/OpenHands/software-agent-sdk/issues/3053.
        #
        _messages_or_condensation = await aprepare_llm_messages(
            state.view, condenser=self.condenser, llm=self.llm
        )

        if isinstance(_messages_or_condensation, Condensation):
            on_event(_messages_or_condensation)
            return

        _messages = _messages_or_condensation

        if _should_handle_non_multimodal_image_input(self.llm, _messages):
            if VISION_INSPECT_TOOL_NAME in self.tools_map:
                logger.info(
                    "Image input received by non-vision model %s; exposing "
                    "image references and vision inspection tool",
                    self.llm.model,
                )
                _messages = _replace_latest_user_images_with_references(_messages)
            else:
                logger.info(
                    "Image input received while selected model does not support "
                    "vision: %s",
                    self.llm.model,
                )
                on_event(
                    MessageEvent(
                        source="agent",
                        llm_message=_non_multimodal_image_message(self.llm.model),
                    )
                )
                state.execution_status = ConversationExecutionStatus.FINISHED
                return

        logger.debug(
            "Sending messages to LLM: "
            f"{json.dumps([m.model_dump() for m in _messages[1:]], indent=2)}"
        )

        try:
            # 仅在网络等待期间释放状态锁，因此 send_message() 和状态快照不会在整个响应期
            # 间被阻止。 除非运行循环持有锁 (e.g. 直接在测试中astep()）。
            #
            async with conversation._released_state_lock_during_io():
                llm_response = await self.llm.agenerate(
                    messages=_messages,
                    tools=list(self.tools_map.values()),
                    store=False,
                    add_security_risk_prediction=True,
                    on_token=stream.token_callback,
                    call_context=call_context,
                )
        except FunctionCallValidationError as e:
            logger.warning(f"LLM generated malformed function call: {e}")
            error_message = MessageEvent(
                source="user",
                llm_message=Message(
                    role="user",
                    content=[TextContent(text=str(e))],
                ),
            )
            on_event(error_message)
            return
        except LLMContentPolicyViolationError as e:
            # 内容策略块是确定性的； 轻推模型并让运行循环继续，而不是发出致命错误。
            #
            logger.warning(f"LLM output blocked by content filter: {e}")
            on_event(
                MessageEvent(
                    source="user",
                    llm_message=Message(
                        role="user",
                        content=[
                            TextContent(
                                text=(
                                    "Your previous response was blocked by the "
                                    "model's content filter. Please continue, "
                                    "rephrasing to avoid the flagged content."
                                )
                            )
                        ],
                    ),
                )
            )
            return
        except LLMMalformedConversationHistoryError as e:
            # 提供程序拒绝当前消息历史记录，因为其结构无效（例如，tool_use/tool_result
            # 配对损坏）。 将其路由到上下文压缩恢复，但保持日志与 True 上下文窗口耗尽不
            # 同，以便上游事件流错误保持可见。
            #
            if (
                self.condenser is not None
                and self.condenser.handles_condensation_requests()
            ):
                logger.warning(
                    "LLM raised malformed conversation history error, "
                    "triggering condensation retry with condensed "
                    "history: %s",
                    e,
                )
                # step()：重新导出缓存视图，并在上下文压缩重试之前进行完全执行。
                #
                state.rebuild_view()
                on_event(CondensationRequest())
                return
            logger.warning(
                "LLM raised malformed conversation history error but "
                "no condenser can handle condensation requests. This "
                "usually indicates an upstream event-stream or resume "
                "bug: %s",
                e,
            )
            raise e
        except LLMContextWindowExceedError as e:
            # 如果上下文压缩器可用并处理请求，则触发上下文压缩
            #
            if (
                self.condenser is not None
                and self.condenser.handles_condensation_requests()
            ):
                logger.warning(
                    "LLM raised context window exceeded error, triggering condensation"
                )
                on_event(CondensationRequest())
                return
            # 没有上下文压缩器可用； 记录有用的警告
            self._log_context_window_exceeded_warning()
            raise e

        message: Message = llm_response.message
        response_type = classify_response(message)
        if response_type is not LLMResponseType.TOOL_CALLS:
            # 解决事件循环之外的问题并陈述锁。 查找可能会调用此服务器，并且
            # update_secrets() 可能会在我们等待时注册另一个源。 重复此操作，直至注册表在
            # 锁下方稳定。
            #
            while True:
                sources = dict(state.secret_registry.secret_sources)
                async with conversation._released_state_lock_during_io():
                    message = await asyncio.to_thread(
                        self._mask_secrets, message, conversation
                    )
                if sources == state.secret_registry.secret_sources:
                    break

        match response_type:
            case LLMResponseType.TOOL_CALLS:
                await self._ahandle_tool_calls(
                    message, llm_response, conversation, state, on_event, stream
                )
            case LLMResponseType.CONTENT:
                self._handle_content_response(
                    message,
                    llm_response,
                    conversation,
                    state,
                    on_event,
                    stream,
                    mask_secrets=False,
                )
            case LLMResponseType.REASONING_ONLY | LLMResponseType.EMPTY:
                self._handle_no_content_response(
                    message,
                    llm_response,
                    conversation,
                    state,
                    on_event,
                    stream,
                    response_type=response_type,
                    mask_secrets=False,
                )

    def _requires_user_confirmation(
        self,
        state: ConversationState,
        action_events: list[ActionEvent],
        on_event: ConversationCallbackType | None = None,
    ) -> bool:
        """在应用策略之前分析操作并记录结论。"""
        risks, event = self._analyze_for_confirmation(state, action_events)
        if event is not None and on_event is not None:
            on_event(state.secret_registry.mask_secrets_in_model(event))
        return self._set_confirmation_status(state, risks)

    async def _arequires_user_confirmation(
        self,
        conversation: LocalConversation,
        state: ConversationState,
        action_events: list[ActionEvent],
        on_event: ConversationCallbackType,
    ) -> bool:
        """解决审核机密，而不阻塞循环或保持状态。"""
        risks, event = self._analyze_for_confirmation(state, action_events)
        if event is not None:
            while True:
                sources = dict(state.secret_registry.secret_sources)
                async with conversation._released_state_lock_during_io():
                    event = await asyncio.to_thread(
                        state.secret_registry.mask_secrets_in_model, event
                    )
                if sources == state.secret_registry.secret_sources:
                    break
            on_event(event)
        return self._set_confirmation_status(state, risks)

    def _analyze_for_confirmation(
        self, state: ConversationState, action_events: list[ActionEvent]
    ) -> tuple[list[risk.SecurityRisk], SecurityAnalysisEvent | None]:
        # 单个 `FinishAction` 或 `ThinkAction` 不需要确认
        if len(action_events) == 1 and isinstance(
            action_events[0].action, (FinishAction, ThinkAction)
        ):
            return [], None

        if not action_events:
            return [], None

        if state.security_analyzer is None:
            return [risk.SecurityRisk.UNKNOWN] * len(action_events), None

        analyses = state.security_analyzer.analyze_actions(action_events)
        event = SecurityAnalysisEvent(
            analyzer=state.security_analyzer.__class__.__name__,
            policy=state.confirmation_policy.__class__.__name__,
            risks={action.id: analysis.risk for action, analysis in analyses},
            details={
                action.id: analysis.details
                for action, analysis in analyses
                if analysis.details is not None
            },
        )
        return [analysis.risk for _, analysis in analyses], event

    @staticmethod
    def _set_confirmation_status(
        state: ConversationState, risks: list[risk.SecurityRisk]
    ) -> bool:
        if any(state.confirmation_policy.should_confirm(risk) for risk in risks):
            state.execution_status = (
                ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
            )
            return True

        return False

    def _extract_security_risk(
        self,
        arguments: dict,
        read_only_tool: bool,
        security_analyzer: analyzer.SecurityAnalyzerBase | None = None,
    ) -> risk.SecurityRisk:
        raw = arguments.pop("security_risk", None)

        # 操作事件 Tool 的默认风险值标记为只读，因此可以忽略安全风险
        #
        if read_only_tool:
            return risk.SecurityRisk.UNKNOWN

        # 当没有配置安全分析器时，忽略任何security_risk字段
        # from LLM and return UNKNOWN. This ensures that security_risk is only
        # 当显式设置安全分析器时进行评估。
        if security_analyzer is None:
            return risk.SecurityRisk.UNKNOWN

        # security_risk是可选的：如果LLM省略，则默认为UNKNOWN。
        if raw is None:
            return risk.SecurityRisk.UNKNOWN

        # 如果无效风险枚举通过 LLM，则会引发异常
        security_risk = risk.SecurityRisk(raw)
        return security_risk

    def _extract_summary(
        self,
        tool_name: str,
        arguments: dict,
        tool: ToolDefinition | None = None,
    ) -> str:
        """从工具参数中提取并验证汇总字段。

        摘要字段总是请求的，但可选的 - 如果 LLM 不提供它或提供无效数据，我们将使用工
        具名称和参数生成默认摘要。

        当工具自己的模式将 ``summary`` 声明为实参数时 (e.g. Jira 的工单标题），该值为
         ** 已读取但未删除 **，因此
        ``action_from_arguments`` 验证仍然会成功。 该工具自己的 ``summary`` 值被重用
        为事件级摘要，因为它通常是描述性的 (
        e.g. Jira 票证标题）。

        Args:
            tool_name: 被调用的工具名称
            arguments: 来自 LLM 的工具参数字典
            tool: 工具定义（用于检查“summary”是否为
                工具的声明参数模式)

        Returns:
            摘要字符串 - 来自 LLM 或默认生成的字符串
        """
        if tool is not None and _tool_has_summary_param(tool):
            # “摘要”属于工具——阅读它但不要弹出它。 重用工具自身的值作为事件摘要 (e.g.
            # Jira 票证标题是对操作的合理描述）。
            #
            summary = arguments.get("summary")
            if isinstance(summary, str) and summary.strip():
                return summary.strip()
            args_str = json.dumps(arguments)
            return f"{tool_name}: {args_str}"

        summary = arguments.pop("summary", None)

        # 如果 LLM 提供了有效的摘要，请使用它
        if summary is not None and isinstance(summary, str) and summary.strip():
            return summary

        # 生成默认摘要：{tool_name}：{arguments}
        args_str = json.dumps(arguments)
        return f"{tool_name}: {args_str}"

    def _emit_tool_error(
        self,
        *,
        error: str,
        tool_name: str,
        span_name: str,
        conversation: LocalConversation,
        tool_call: MessageToolCall,
        llm_response_id: str,
        on_event: ConversationCallbackType,
        thought: list[TextContent] | None = None,
        reasoning_content: str | None = None,
        thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] | None = None,
        responses_reasoning_item: ReasoningItemModel | None = None,
        stream: StreamContext | None = None,
    ) -> None:
        try:
            json.loads(tool_call.arguments)
        except json.JSONDecodeError:
            tool_call = tool_call.model_copy(
                update={
                    "arguments": json.dumps(
                        {
                            "_openhands_malformed_tool_call": True,
                            "error": error,
                        }
                    )
                }
            )

        minted: dict[str, Any] = {}
        if stream is not None and (item_id := stream.claim()):
            minted["id"] = item_id
        tc_event = ActionEvent(
            **minted,
            source="agent",
            thought=thought or [],
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks or [],
            responses_reasoning_item=responses_reasoning_item,
            tool_call=tool_call,
            tool_name=tool_call.name,
            tool_call_id=tool_call.id,
            llm_response_id=llm_response_id,
            action=None,
        )
        on_event(tc_event)
        if stream is not None and minted:
            stream.commit()
        error_event = AgentErrorEvent(
            error=error,
            tool_name=tool_name,
            tool_call_id=tool_call.id,
            classification=AGENT_OUTCOME,
        )
        record_tool_result(
            conversation,
            name=span_name,
            tool_call_id=tool_call.id,
            tool_input=tool_call,
            tool_output=error_event.to_llm_message(),
        )
        on_event(error_event)

    def _get_action_event(
        self,
        tool_call: MessageToolCall,
        conversation: LocalConversation,
        llm_response_id: str,
        on_event: ConversationCallbackType,
        security_analyzer: analyzer.SecurityAnalyzerBase | None = None,
        thought: list[TextContent] | None = None,
        reasoning_content: str | None = None,
        thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] | None = None,
        responses_reasoning_item: ReasoningItemModel | None = None,
        stream: StreamContext | None = None,
    ) -> ActionEvent | None:
        """将工具调用转换为 ActionEvent，验证参数。

        NOTE: 状态将就地突变。
        """
        # 当找不到工具或验证失败时，跟踪最初请求的工具名称（规范化之前）以获取错误消息。
        #
        requested_tool_name = tool_call.name
        tool: ToolDefinition | None = None
        # 将标准化的工具调用到持久化正确名称/参数存储在事件中。
        normalized_tool_call = tool_call
        arguments: dict[str, object] | None = None

        security_risk: risk.SecurityRisk = risk.SecurityRisk.UNKNOWN
        try:
            # 在 try 块中解析参数，以便 JSONDecodeError 被捕获。
            arguments = parse_tool_call_arguments(tool_call.arguments)

            # 规范化工具调用（处理别名、终端回退方案等）
            tool_name, arguments = normalize_tool_call(
                requested_tool_name,
                arguments,
                self.tools_map.keys(),
            )

            tool = self.tools_map.get(tool_name, None)
            if tool is None:
                available = list(self.tools_map.keys())
                err = f"Tool '{tool_name}' not found. Available: {available}"
                logger.error(err)
                self._emit_tool_error(
                    error=err,
                    tool_name=tool_name,
                    span_name="InvalidToolCall",
                    conversation=conversation,
                    tool_call=tool_call,
                    llm_response_id=llm_response_id,
                    on_event=on_event,
                    thought=thought,
                    reasoning_content=reasoning_content,
                    thinking_blocks=thinking_blocks,
                    responses_reasoning_item=responses_reasoning_item,
                    stream=stream,
                )
                return

            arguments = fix_malformed_tool_arguments(arguments, tool.action_type)
            if tool.response_schema is not None:
                arguments = fix_malformed_tool_arguments(
                    arguments, tool.response_schema
                )
            normalized_tool_call = tool_call.model_copy(
                update={
                    "name": tool_name,
                    "arguments": json.dumps(arguments),
                }
            )
            security_risk = self._extract_security_risk(
                arguments,
                tool.annotations.readOnlyHint if tool.annotations else False,
                security_analyzer,
            )
            assert "security_risk" not in arguments, (
                "Unexpected 'security_risk' key found in tool arguments"
            )

            summary = self._extract_summary(tool.name, arguments, tool=tool)

            action: Action = tool.action_from_arguments(arguments)

        except (ValueError, json.JSONDecodeError, ValidationError) as e:
            # normalize_tool_call 或 Pydantic 验证出现错误。 仅使用参数名称（而不是值）
            # 构建简洁的错误消息。 尝试提取错误消息的键，但通过显示“无法解析JSON”来优雅
            # 地处理真正无法解析的JSON。
            #

            # 当 normalize_tool_call 引发 file_editor“无法推断”时，错误消息包含别名目标
            # (e.g. “file_editor”），不是原始工具名称。 提取它以便错误消息匹配。
            #
            err_str = str(e)
            display_tool_name = requested_tool_name
            if "Cannot infer" in err_str:
                match = re.search(r"for tool '([^']+)'", err_str)
                if match:
                    display_tool_name = match.group(1)

            keys = list(arguments.keys()) if isinstance(arguments, dict) else None
            params = (
                f"Parameters provided: {keys}"
                if keys is not None
                else "Arguments: unparseable JSON"
            )
            err = f"Error validating tool '{display_tool_name}': {e}. {params}"
            self._emit_tool_error(
                error=err,
                tool_name=display_tool_name,
                span_name=(tool.action_type.__name__ if tool else "InvalidToolCall"),
                conversation=conversation,
                tool_call=tool_call,
                llm_response_id=llm_response_id,
                on_event=on_event,
                thought=thought,
                reasoning_content=reasoning_content,
                thinking_blocks=thinking_blocks,
                responses_reasoning_item=responses_reasoning_item,
                stream=stream,
            )
            return

        # 创建初始操作事件。 在此声明而不是在调用站点声明，因此永远不会构建此事件的错误
        # 路径会在 StreamContext.__exit__ 中为中止保留开放的插槽。
        #
        minted: dict[str, Any] = {}
        if stream is not None and (item_id := stream.claim()):
            minted["id"] = item_id

        action_event = ActionEvent(
            **minted,
            action=action,
            thought=thought or [],
            reasoning_content=reasoning_content,
            thinking_blocks=thinking_blocks or [],
            responses_reasoning_item=responses_reasoning_item,
            tool_name=tool.name,
            tool_call_id=normalized_tool_call.id,
            tool_call=normalized_tool_call,
            llm_response_id=llm_response_id,
            security_risk=security_risk,
            summary=summary,
        )

        # 如果已配置，则运行批评家评估
        if self._should_evaluate_with_critic(action):
            critic_result = self._evaluate_with_critic(conversation, action_event)
            if critic_result is not None:
                # 使用评论结果创建新事件
                action_event = action_event.model_copy(
                    update={"critic_result": critic_result}
                )

        on_event(action_event)
        if stream is not None and minted:
            stream.commit()
        return action_event

    def _execute_action_event(
        self,
        conversation: LocalConversation,
        action_event: ActionEvent,
    ) -> list[Event]:
        """执行单个工具并返回结果事件。

        由 _execute_actions 从并行线程调用。 此方法不得改变共享对话状态 (
        blocked_actions, execution_status)
        — 这些转换由主线程上的调用者处理。

        Note: 该工具本身接收 ``conversation`` 并可能会改变它
        (e.g. 文件系统，工作目录）。 线程安全个别工具的责任是工具的责任。

        返回事件列表（观测结果或错误）。 事件在此处发出不 — 调用者负责按顺序发出它们
        。
        """
        tool = self.tools_map.get(action_event.tool_name, None)
        if tool is None:
            raise RuntimeError(
                f"Tool '{action_event.tool_name}' not found. This should not happen "
                "as it was checked earlier."
            )

        # 执行行动！
        try:
            if should_enable_observability():
                tool_name = extract_action_name(action_event)
                observation: Observation = observe(
                    name=tool_name,
                    span_type="TOOL",
                    # 仅输入动作； 对话将序列化作为携带内存地址的裸对象 repr。
                    #
                    ignore_inputs=["conversation"],
                    metadata={"tool_call_id": action_event.tool_call.id},
                )(tool)(action_event.action, conversation)
            else:
                observation = tool(action_event.action, conversation)
            assert isinstance(observation, Observation), (
                f"Tool '{tool.name}' executor must return an Observation"
            )
        except ValueError as e:
            # 工具执行引发 ValueError（e.g.，无效参数组合）转换为 AgentErrorEvent，以便
            # 智能体可以自行更正
            #
            err = f"Error executing tool '{tool.name}': {e}"
            logger.warning(err)
            error_event = AgentErrorEvent(
                error=err,
                tool_name=tool.name,
                tool_call_id=action_event.tool_call.id,
                classification=AGENT_OUTCOME,
            )
            return [error_event]

        obs_event = ObservationEvent(
            observation=observation,
            action_id=action_event.id,
            tool_name=tool.name,
            tool_call_id=action_event.tool_call.id,
        )
        return [obs_event]

    def _maybe_emit_vllm_tokens(
        self, llm_response: LLMResponse, on_event: ConversationCallbackType
    ) -> None:
        if (
            "return_token_ids" in self.llm.litellm_extra_body
        ) and self.llm.litellm_extra_body["return_token_ids"]:
            token_event = TokenEvent(
                source="agent",
                prompt_token_ids=llm_response.raw_response["prompt_token_ids"],
                response_token_ids=llm_response.raw_response["choices"][0][
                    "provider_specific_fields"
                ]["token_ids"],
            )
            on_event(token_event)

    def _log_context_window_exceeded_warning(self) -> None:
        """当超出上下文窗口而没有上下文压缩器时，记录有用的警告。"""
        if self.condenser is None:
            situation = (
                "The LLM's context window has been exceeded, but no condenser is "
                "configured."
            )
            config = f"  • Condenser: None\n  • LLM Model: {self.llm.model}"
            advice = (
                "To prevent this error, configure a condenser to automatically "
                "summarize\n"
                "conversation history when it gets too long."
            )
        else:
            condenser_type = type(self.condenser).__name__
            handles_requests = self.condenser.handles_condensation_requests()
            condenser_config = self.condenser.model_dump(
                exclude={"llm"}, exclude_none=True
            )
            condenser_llm_obj = self.condenser.get_llm()
            condenser_llm = (
                condenser_llm_obj.model if condenser_llm_obj is not None else "N/A"
            )

            situation = "The LLM's context window has been exceeded."
            config = (
                f"  • Condenser Type: {condenser_type}\n"
                f"  • Handles Condensation Requests: {handles_requests}\n"
                f"  • Condenser LLM: {condenser_llm}\n"
                f"  • Agent LLM Model: {self.llm.model}\n"
                f"  • Condenser Config: {json.dumps(condenser_config, indent=4)}"
            )
            advice = (
                "Your condenser is configured but does not handle condensation "
                "requests\n"
                "(handles_condensation_requests() returned False).\n"
                "\n"
                "To fix this:\n"
                "  1. Use LLMSummarizingCondenser which handles condensation "
                "requests, OR\n"
                "  2. Implement handles_condensation_requests() in your custom "
                "condenser"
            )

        logger.warning(
            "\n"
            "=" * 80 + "\n"
            "⚠️  CONTEXT WINDOW EXCEEDED ERROR\n"
            "=" * 80 + "\n"
            "\n"
            f"{situation}\n"
            "\n"
            "Current configuration:\n"
            f"{config}\n"
            "\n"
            f"{advice}\n"
            "\n"
            "Example configuration:\n"
            "\n"
            "  from openhands.sdk import Agent, LLM\n"
            "  from openhands.sdk.context.condenser import "
            "LLMSummarizingCondenser\n"
            "\n"
            "  agent = Agent(\n"
            "      llm=LLM(model='your-model'),\n"
            "      condenser=LLMSummarizingCondenser(\n"
            "          llm=LLM(model='your-model'),\n"
            "          max_size=240,\n"
            "          keep_first=2\n"
            "      )\n"
            "  )\n"
            "\n"
            "For more information, see: "
            "https://docs.openhands.dev/sdk/guides/context-condenser\n"
            "=" * 80
        )
