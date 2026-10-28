from abc import ABC, abstractmethod
from enum import Enum
from logging import getLogger

from openhands.sdk.context.view import View
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.llm import LLM
from openhands.sdk.utils.models import (
    DiscriminatedUnionMixin,
)


logger = getLogger(__name__)


class CondenserBase(DiscriminatedUnionMixin, ABC):
    """摘要上下文压缩器接口。

    上下文压缩器获取 `Event` 个对象的列表，并将它们缩减为可能更小的列表。

    智能体可以使用上下文压缩器来减少他们在决定采取哪个操作时需要考虑的事件数量。 要使
    用上下文压缩器、智能体可以调用
    `condensed_history` 方法基于当前 `State` 正在考虑并使用结果而不是完整历史记录。

    如果上下文压缩器返回 `Condensation` 而不是 `View`，则智能体应该返回
    `Condensation.action` 而不是产生自己的操作。 在下
    一个智能体步骤中，上下文压缩器将使用该上下文压缩事件来生成新的 `View`。
    """

    def get_llm(self) -> LLM | None:
        """上下文压缩器使用的 LLM（如果有）。"""
        return None

    @abstractmethod
    def condense(self, view: View, agent_llm: LLM | None = None) -> View | Condensation:
        """将事件序列压缩为可能更小的列表。

        新的上下文压缩器策略应该重写此方法以实现它们自己的上下文压缩逻辑。 在实现中调
        用 `self.add_metadata` 来记录任何相关的 per-上下文压
        缩诊断信息。

        Args:
            view: 包含所有应该浓缩的事件的历史视图。
                **实现必须将此视图视为只读。**视图可能是
                ``ConversationState`` 拥有的缓存投影，对其进行适当修改会破坏该缓存。
                返回一个新的 ``View`` (e.g.
                ``View(events=view.events[k:])``) 或 ``Condensation`` 代替。
            agent_llm: 智能体使用的 LLM 实例。 上下文压缩器将其用于 token
                counting purposes. 默认为 None。

        Returns:
            | 上下文压缩：简要事件视图或表示历史已被压缩的事件。
        """

    async def acondense(
        self, view: View, agent_llm: LLM | None = None
    ) -> View | Condensation:
        """异步：meth:`condense` 的变体。

        默认实现委托给同步``condense()``。 执行异步 I/O 的子类 (e.g. LLM 调用）应该覆
        盖它。
        """
        return self.condense(view, agent_llm=agent_llm)

    def handles_condensation_requests(self) -> bool:
        """此上下文压缩器是否处理显式上下文压缩请求。

        如果返回 True，则只要将 CondensationRequest 事件添加到历史记录中，智能体就会
        触发上下文压缩器。 如果是False，则只有当智能体自
        己的逻辑决定这样做时才会触发上下文压缩器（e.g. 上下文窗口超出）。

        Returns:
            bool: True 如果上下文压缩器处理显式上下文压缩请求，False
            否则。
        """
        return False


class PipelinableCondenserBase(CondenserBase):
    """可以流水线化的抽象上下文压缩器接口。 （由于管道
    上下文压缩器不应嵌套另一个管道上下文压缩器）"""


class NoCondensationAvailableException(Exception):
    """当要求上下文压缩器提供上下文压缩但 None 可用时引发。

    如果上下文压缩器的 `should_condense` 方法返回 True，但由​​于 API 的限制，无法生成
    上下文压缩，就会发生这种情况。

    当滚动上下文压缩器的 `get_condensation` 方法引发此异常时，智能体将回退到使用未压
    缩视图进行下一个智能体步骤。
    """


class CondensationRequirement(Enum):
    """滚动上下文压缩器所需的上下文压缩类型。"""

    HARD = "hard"
    """表示现在需要上下文压缩，智能体无法继续
    没有它。
    """

    SOFT = "soft"
    """表示需要上下文压缩，但不严格要求。"""


class RollingCondenser(PipelinableCondenserBase, ABC):
    """专门的上下文压缩器策略的基类，该策略将上下文压缩应用于
    滚动的历史。

    `View.from_events` 生成滚动历史，它分析历史中的所有事件并生成一个表示将要发送到
    LLM 的 `View` 对象。

    如果 `condensation_requirement` 这么说，则上下文压缩器负责从 `View` 对象生成
    `Condensation` 对象。 这将被添加到
    事件历史记录中，当给`get_view`时，事件历史记录应该生成压缩的
    `View` 被传递到 LLM。
    """

    def hard_context_reset(
        self,
        view: View,  # noqa: ARG002
        agent_llm: LLM | None = None,  # noqa: ARG002
    ) -> Condensation | None:
        """如果上下文压缩器支持，请执行硬上下文重置。

        默认情况下，滚动上下文压缩器不支持硬上下文重置。 重写此方法以通过返回
        `Condensation` 对象来实现硬上下文重置逻辑。

        该方法在以下情况下被调用：
        - 触发 HARD 上下文压缩要求（e.g.，由用户请求）
        - 但是上下文压缩器引发了 NoCondensationAvailableException 错误
        """
        return None

    @abstractmethod
    def condensation_requirement(
        self, view: View, agent_llm: LLM | None = None
    ) -> CondensationRequirement | None:
        """确定应如何压缩视图。

        Args:
            view: 对话历史记录的当前视图。
            agent_llm: 智能体使用的 LLM 实例。 上下文压缩器将其用于 token
                counting purposes. 默认为 None。

        Returns:
            CondensationRequirement  |  None类型是上下文压缩必需的，或 None 如果无上
            下文压缩是必需的。
        """

    @abstractmethod
    def get_condensation(
        self, view: View, agent_llm: LLM | None = None
    ) -> Condensation:
        """从视图中获取上下文压缩。"""

    def condense(self, view: View, agent_llm: LLM | None = None) -> View | Condensation:
        # 如果我们触发上下文压缩器特定的上下文压缩阈值，则计算并
        # return the condensation.
        request = self.condensation_requirement(view, agent_llm=agent_llm)
        if request is not None:
            try:
                return self.get_condensation(view, agent_llm=agent_llm)

            except NoCondensationAvailableException as e:
                logger.debug(f"No condensation available: {e}")

                if request == CondensationRequirement.SOFT:
                    # 对于软请求，我们可以只返回未压缩的视图。 该请求最终将得到处理，但
                    # 我们是否立即处理并不重要。
                    #
                    return view

                elif request == CondensationRequirement.HARD:
                    # 的智能体它发现自己处于无法继续下去的境地上下文压缩，但是…… 上下文
                    # 压缩器无法提供。 我们会
                    #
                    # try to recover from this situation by performing a hard context
                    # 如果上下文压缩器支持，则重置。
                    try:
                        hard_reset_condensation = self.hard_context_reset(
                            view, agent_llm=agent_llm
                        )
                        if hard_reset_condensation is not None:
                            return hard_reset_condensation

                    # 如果硬重置出现问题，请确保我们将这两个错误都保留在堆栈中
                    #
                    except Exception as hard_reset_exception:
                        raise hard_reset_exception from e

                # 在所有其他情况下重新引发异常。
                raise e

        # 否则我们就可以安全地返回视图。
        else:
            return view

    async def acondense(
        self, view: View, agent_llm: LLM | None = None
    ) -> View | Condensation:
        """异步：meth:`condense` 的变体。

        当需要上下文压缩时委托给：meth:`aget_condensation`，允许执行异步 LLM 调用的子
        类仅覆盖
        ``aget_condensation``.
        """
        request = self.condensation_requirement(view, agent_llm=agent_llm)
        if request is not None:
            try:
                return await self.aget_condensation(view, agent_llm=agent_llm)

            except NoCondensationAvailableException as e:
                logger.debug(f"No condensation available: {e}")

                if request == CondensationRequirement.SOFT:
                    return view

                elif request == CondensationRequirement.HARD:
                    try:
                        hard_reset_condensation = await self.ahard_context_reset(
                            view, agent_llm=agent_llm
                        )
                        if hard_reset_condensation is not None:
                            return hard_reset_condensation
                    except Exception as hard_reset_exception:
                        raise hard_reset_exception from e

                raise e

        return view

    async def aget_condensation(
        self, view: View, agent_llm: LLM | None = None
    ) -> Condensation:
        """异步：meth:`get_condensation` 的变体。

        默认委托给同步版本。
        """
        return self.get_condensation(view, agent_llm=agent_llm)

    async def ahard_context_reset(
        self,
        view: View,
        agent_llm: LLM | None = None,
    ) -> Condensation | None:
        """异步：meth:`hard_context_reset` 的变体。

        默认委托给同步版本。
        """
        return self.hard_context_reset(view, agent_llm=agent_llm)
