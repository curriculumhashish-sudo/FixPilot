import contextlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.events_list_base import EventsListBase
from openhands.sdk.conversation.secret_registry import SecretValue
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationID,
    ConversationTokenCallbackType,
    TraceMetadataValue,
)
from openhands.sdk.event.types import EventID
from openhands.sdk.llm.llm import LLM
from openhands.sdk.llm.message import Message
from openhands.sdk.observability.laminar import (
    RootSpan,
    default_observability_span_name_from_env,
    end_root_span,
    merge_observability_metadata,
    observability_parent_span_context_from_env,
    should_enable_observability,
    start_child_span,
    start_root_span,
)
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
    NeverConfirm,
)
from openhands.sdk.tool.schema import Action, Observation
from openhands.sdk.workspace.base import BaseWorkspace


def _conversation_tag_attributes(
    tags: Mapping[str, str] | None,
) -> dict[str, str] | None:
    if not tags:
        return None
    return {f"conversation.tags.{key}": value for key, value in tags.items()}


if TYPE_CHECKING:
    from openhands.sdk.agent.base import AgentBase
    from openhands.sdk.conversation.secret_registry import SecretRegistry
    from openhands.sdk.conversation.state import ConversationExecutionStatus
    from openhands.sdk.hooks import HookConfig


CallbackType = TypeVar(
    "CallbackType",
    ConversationCallbackType,
    ConversationTokenCallbackType,
)


class ConversationStateProtocol(Protocol):
    """定义会话状态对象接口的协议。"""

    @property
    def id(self) -> ConversationID:
        """对话 ID。"""
        ...

    @property
    def events(self) -> EventsListBase:
        """访问事件列表。"""
        ...

    @property
    def execution_status(self) -> "ConversationExecutionStatus":
        """当前会话执行状态。"""
        ...

    @property
    def confirmation_policy(self) -> ConfirmationPolicyBase:
        """确认政策。"""
        ...

    @property
    def security_analyzer(self) -> SecurityAnalyzerBase | None:
        """安全分析器。"""
        ...

    @property
    def activated_knowledge_skills(self) -> list[str]:
        """激活的知识技能列表。"""
        ...

    @property
    def invoked_skills(self) -> list[str]:
        """明确调用的渐进式披露技能的名称。"""
        ...

    @property
    def workspace(self) -> BaseWorkspace:
        """工作区用于智能体操作和工具执行。"""
        ...

    @property
    def persistence_dir(self) -> str | None:
        """FileStore 的持久化目录。

        如果为None，则表示对话不是已持久化。
        """
        ...

    @property
    def agent(self) -> "AgentBase":
        """对话中运行的智能体。"""
        ...

    @property
    def stats(self) -> ConversationStats:
        """会话统计。"""
        ...

    @property
    def hook_config(self) -> "HookConfig | None":
        """此对话的挂钩配置。"""
        ...

    @property
    def secret_registry(self) -> "SecretRegistry":
        """此对话的机密注册表。"""
        ...


class BaseConversation(ABC):
    """对话实现的抽象基类。

    此类定义了所有对话实现必须遵循的接口。 对话管理用户和智能体之间的交互，处理消息交
    换、执行控制和状态管理。
    """

    _cleanup_initiated: bool = False
    _cleanup_complete: bool = False
    _hook_processor: Any = None

    def __init__(self) -> None:
        """使用跨度跟踪初始化基本对话。"""
        self._span_ended = False
        self._cleanup_initiated = False
        self._cleanup_complete = False
        self._hook_processor = None
        # 拥有根跨度。 的 ``observe`` 装饰器查找这个属性（通过名称）
        # ``_observability_root_span``) on ``self`` 在每一步入口并重新附上它
        # ``Laminar.use_span`` 以便嵌套的 span 正确地将会话跟踪连接起来，即使方法在不同
        # 的 asyncio 任务中被调用时也是如此线程比构建对话的那个。
        #
        self._observability_root_span: RootSpan | None = None

    @property
    def cleanup_initiated(self) -> bool:
        """对话清理是否已开始。"""
        return self._cleanup_initiated

    @property
    def cleanup_complete(self) -> bool:
        """对话清理是否已完成。"""
        return self._cleanup_complete

    @property
    def hook_processor(self) -> Any:
        """对话的活动挂钩处理器（如果已配置）。"""
        return self._hook_processor

    def _start_observability_span(
        self,
        session_id: str,
        span_name: str = "conversation",
        user_id: str | None = None,
        metadata: dict[str, TraceMetadataValue] | None = None,
        tags: list[str] | None = None,
        conversation_tags: Mapping[str, str] | None = None,
        parent_span_context: str | None = None,
    ) -> None:
        """启动每个对话的可观察性根跨度。

        Args:
            session_id: 与跟踪关联的会话 ID
            span_name: 在对话根下发出的可选子范围名称。
            user_id: 与跟踪关联的可选用户 ID
            metadata: 附加到可观察性后端的可选跟踪级元数据
            tags: 用于附加到对话根范围的可选范围标签
            conversation_tags: 添加为根跨度属性的可选对话标签
        """
        if not should_enable_observability():
            return
        if self._observability_root_span is not None:
            # 幂等：永远不要为一次对话启动两个根。
            return
        default_span_name = default_observability_span_name_from_env()
        if default_span_name and span_name == "conversation":
            span_name = default_span_name

        metadata = merge_observability_metadata(metadata)
        attributes: dict[str, TraceMetadataValue] = dict(metadata)
        tag_attributes = _conversation_tag_attributes(conversation_tags)
        if tag_attributes:
            attributes.update(tag_attributes)
        self._observability_root_span = start_root_span(
            "conversation",
            session_id=session_id,
            user_id=user_id,
            metadata=metadata,
            tags=tags,
            attributes=attributes,
            parent_span_context=parent_span_context
            or observability_parent_span_context_from_env(),
        )
        if span_name != "conversation":
            start_child_span(self._observability_root_span, span_name, tags=tags)

    def _end_observability_span(self) -> None:
        """如果可观察性跨度尚未结束，则结束它。"""
        if self._span_ended:
            return
        if self._observability_root_span is not None:
            end_root_span(self._observability_root_span)
        self._observability_root_span = None
        self._span_ended = True

    @property
    @abstractmethod
    def id(self) -> ConversationID: ...

    @property
    @abstractmethod
    def state(self) -> ConversationStateProtocol: ...

    @property
    @abstractmethod
    def conversation_stats(self) -> ConversationStats: ...

    @abstractmethod
    def send_message(self, message: str | Message, sender: str | None = None) -> None:
        """发送消息至智能体。

        Args:
            message: 一个字符串（将被转换为用户消息）
                    或消息对象
            sender: 发件人的可选标识符。 可用于追踪
                   多智能体场景中的消息来源。 例如，当一个智能体委托给另一个时，可以
                   将发送者设置为识别哪个智能体正在发送消息。
        """
        ...

    @abstractmethod
    def run(self) -> None:
        """执行智能体来处理消息并执行操作。

        此方法运行智能体，直到完成当前消息的处理或达到最大迭代限制。
        """
        ...

    async def arun(self) -> None:
        """异步：meth:`run` 的变体。

        默认实现委托给同步``run()``。 子类 (e.g., :class:`LocalConversation`) 应重写
        此设置，以使用异步智能体个步骤进行
        非阻塞 LLM I/O。
        """
        self.run()

    @contextlib.asynccontextmanager
    async def _released_state_lock_during_io(self) -> AsyncIterator[None]:
        """在等待的 LLM 调用中释放任何运行循环状态锁。

        默认无操作； :class:`LocalConversation` 覆盖它。
        """
        yield

    @abstractmethod
    def set_confirmation_policy(self, policy: ConfirmationPolicyBase) -> None:
        """设置对话的确认策略。"""
        ...

    @abstractmethod
    def set_security_analyzer(self, analyzer: SecurityAnalyzerBase | None) -> None:
        """设置对话的安全分析器。"""
        ...

    @property
    def confirmation_policy_active(self) -> bool:
        return not isinstance(self.state.confirmation_policy, NeverConfirm)

    @property
    def is_confirmation_mode_active(self) -> bool:
        """检查确认模式是否处于活动状态。

        如果满足 BOTH 条件，则返回 True：
        1. 会话状态有安全分析器集（不是None）
        2. 确认政策已生效

        """
        return (
            self.state.security_analyzer is not None and self.confirmation_policy_active
        )

    @abstractmethod
    def reject_pending_actions(
        self, reason: str = "User rejected the action"
    ) -> None: ...

    @abstractmethod
    def pause(self) -> None: ...

    def interrupt(self) -> None:
        """立即取消飞行中的 ``arun()`` LLM 通话。

        与：meth:`pause` 不同，它等待当前 LLM 请求完成，``interrupt()`` 取消正在驱动
        的 asyncio 任务
        ``arun()``，所以取消在下一个生效
        ``await`` 边界 — 通常在流式传输 HTTP 读取范围内。

        如果没有异步运行正在进行中 (e.g. 同步 ``run()`` 处于活动状态），调用会默默地
        退回到：meth:`pause`。

        在中断后，会话状态被设置为 ``PAUSED``，并发出
        `~openhands.sdk.event.InterruptEvent` 类的事件，因此可以使用
        后续的 ``run()`` 或 ``arun()`` 调用来恢复会话。
        """
        # 默认值：对于不覆盖的子类，回退到暂停。
        self.pause()

    @abstractmethod
    def update_secrets(self, secrets: Mapping[str, SecretValue]) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def generate_title(self, llm: LLM | None = None, max_length: int = 50) -> str:
        """根据第一条用户消息生成对话标题。

        Args:
            llm: 可选 LLM 用于标题生成。 如果没有提供，
                 使用智能体的 LLM。
            max_length: 生成的标题的最大长度。

        Returns:
            为对话生成的标题。

        Raises:
            ValueError: 如果在对话中没有找到用户消息。
        """
        ...

    @staticmethod
    def get_persistence_dir(
        persistence_base_dir: str | Path, conversation_id: ConversationID
    ) -> str:
        """获取对话的持久化目录。

        Args:
            persistence_base_dir: 持久化的基目录。 可以是字符串
                路径或路径对象。
            conversation_id: 唯一的对话 ID。

        Returns:
            特定于会话的持久化目录的字符串路径。 即使提供了 Path，也始终返回规范化的
            字符串路径。
        """
        return str(Path(persistence_base_dir) / conversation_id.hex)

    @abstractmethod
    def ask_agent(self, question: str) -> str:
        """向智能体提出一个简单的、无状态的问题，并获得直接的 LLM 响应。

        这绕过了正常的对话流程，并且 ** 不 ** 修改持久化或成为对话状态的一部分。 主程
        序智能体不会记住该请求，不会记录任何事件，并且执行状态不变。 它也是线
        程安全，并且可以在 `conversation.run()` 在另一个线程中执行时被调用。

        Args:
            question: 一个简单的字符串问题要问智能体

        Returns:
            来自智能体的字符串响应
        """
        ...

    @abstractmethod
    def condense(self) -> None:
        """强制对话历史记录上下文压缩。

        此方法使用现有的上下文压缩请求模式来触发上下文压缩。 它将 CondensationRequest
         事件添加到对话中，并强制智能体采取单个步骤来处理它。

        上下文压缩将立即应用，并将通过向历史记录添加上下文压缩事件来修改对话状态。

        Raises:
            ValueError: 如果没有配置上下文压缩器或者没有配置上下文压缩器
                       处理上下文压缩个请求。
        """
        ...

    @abstractmethod
    def execute_tool(self, tool_name: str, action: Action) -> Observation:
        """直接执行工具，无需经过智能体循环。

        此方法允许在正常 conversation.run() 流程之前或之外执行工具。 它自动处理智能体
        初始化，因此可以在第一次 run() 调用之前执行工具。

        Note: 该方法绕过智能体循环，包括确认
        策略和安全分析器检查。 调用者有责任在执行潜在破坏性工具之前应用任何保护措施。

        这对于：
        - 预运行设置操作（e.g.，索引存储库）
        - 用于环境设置的手动工具执行
        - 测试智能体循环之外的工具行为

        Args:
            tool_name: 要执行的工具的名称（e.g.，“sleeptime_compute”）
            action: 传递给工具执行器的操作

        Returns:
            工具执行返回的观测结果

        Raises:
            KeyError: 如果在智能体的工具中没有找到该工具
            NotImplementedError: 如果该工具没有执行器
        """
        ...

    def load_plugin(self, plugin_ref: str) -> None:
        """从注册市场加载插件。

        支持市场注册插件的实现将参考对话智能体的注册市场，并将插件的技能、钩子和 MCP
        配置合并到智能体。

        Args:
            plugin_ref: 插件参考，``plugin-name`` 或
                ``plugin-name@marketplace-name``.
        """
        raise NotImplementedError("This conversation does not support loading plugins")

    @abstractmethod
    def fork(
        self,
        *,
        conversation_id: ConversationID | None = None,
        agent: "AgentBase | None" = None,
        title: str | None = None,
        tags: dict[str, str] | None = None,
        reset_metrics: bool = True,
        from_event_id: EventID | None = None,
    ) -> "BaseConversation":
        """使用新 ID 深度复制此对话。

        事件被复制，因此源保持不变。 分叉从``execution_status='idle'``开始； 调用
        ``run()`` 从复制状态恢复 — 这意味着智能
        体具有源的完整事件内存。

        Args:
            conversation_id: 分叉对话的 ID（自动生成
                if ``None``).
            agent: 智能体为叉子。 默认为深层复制
                来源智能体。
            title: 自 1.54.0 起 ``LocalConversation`` 上的已弃用 — 没有
                在那里起作用并发出 ``DeprecationWarning``。 仍然受到
                ``RemoteConversation`` 的尊重（传递给
                Agent Server，将其存储在 ``StoredConversation`` 上）。
            tags: 分叉对话的可选标签。
            reset_metrics: 如果 ``True``（默认），成本/代币统计开始
                新鲜的在叉子上。
            from_event_id: 如果设置，则仅复制到此事件的分支并设置
                叉子就在那里HEAD。 如果 ``None``（默认），则完整副本。

        Returns:
            一个新的对话，共享相同的事件历史，但有自己的身份和独立的状态。
        """
        ...

    @abstractmethod
    def navigate_to(self, event_id: EventID | None) -> None:
        """将对话 HEAD 移至该对话中的现有事件。

        将活动分支重新定位到位：智能体的下一个上下文变为
        ``path_to_root(event_id)``. 所有分支都保留在磁盘上； 不像
        :meth:`fork`，没有创建新对话。

        Args:
            event_id: 为空树创建新的 HEAD 或 ``None`` 的事件。

        Raises:
            ValueError: 如果 ``event_id`` 不是 ``None`` 并且不在其中
                谈话。
        """
        ...

    @staticmethod
    def compose_callbacks(callbacks: Iterable[CallbackType]) -> CallbackType:
        """将多个回调组合成一个回调函数。

        Args:
            callbacks: 回调函数的迭代

        Returns:
            调用所有提供的回调的单个回调函数
        """

        def composed(event) -> None:
            for cb in callbacks:
                if cb:
                    cb(event)

        return cast(CallbackType, composed)
