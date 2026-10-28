# state.py
import json
import threading
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from enum import Enum
from pathlib import Path
from typing import Any, Self, cast

from pydantic import Field, PrivateAttr

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.context.view import View
from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.event_store import ROOT_PARENT_ID, EventLog
from openhands.sdk.conversation.fifo_lock import FIFOLock
from openhands.sdk.conversation.persistence_const import BASE_STATE, EVENTS_DIR
from openhands.sdk.conversation.secret_registry import SecretRegistry
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationID,
    ConversationTags,
)
from openhands.sdk.event import (
    ActionEvent,
    AgentErrorEvent,
    ObservationEvent,
    UserRejectObservation,
)
from openhands.sdk.event.base import Event
from openhands.sdk.event.types import EventID
from openhands.sdk.hooks import HookConfig
from openhands.sdk.io import FileStore, InMemoryFileStore, LocalFileStore
from openhands.sdk.logger import get_logger
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
    NeverConfirm,
)
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.utils.models import OpenHandsModel
from openhands.sdk.workspace.base import BaseWorkspace


logger = get_logger(__name__)


class ConversationExecutionStatus(str, Enum):
    """枚举代表会话当前的执行状态。"""

    IDLE = "idle"  # 对话已准备好接收任务
    RUNNING = "running"  # 正在积极处理对话
    PAUSED = "paused"  # 会话执行被用户暂停
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"  # 对话正在等待用户确认
    FINISHED = "finished"  # 对话已完成当前任务
    ERROR = "error"  # 对话遇到错误（可选以供将来使用）
    STUCK = "stuck"  # 对话陷入循环或无法继续
    DELETING = "deleting"  # 对话正在删除中

    def is_terminal(self) -> bool:
        """检查该状态是否代表最终状态。

        终端状态指示运行已完成并且智能体不再主动处理。 它们是：FINISHED、ERROR、STUCK
        。

        Note: IDLE 是不终止状态 - 这是对话的初始状态
        在任何跑步开始之前。 当 WebSocket 在连接期间传递初始状态更新时，包含 IDLE 将
        导致 False 积极。

        Returns:
            如果这是终端状态，则为 True，否则为 False。
        """
        return self in (
            ConversationExecutionStatus.FINISHED,
            ConversationExecutionStatus.ERROR,
            ConversationExecutionStatus.STUCK,
        )


class ConversationState(OpenHandsModel):
    # ===== 公共、经过验证的字段 =====
    id: ConversationID = Field(description="Unique conversation ID")

    agent: AgentBase = Field(
        ...,
        description=(
            "The agent running in the conversation. "
            "This is persisted to allow resuming conversations and "
            "check agent configuration to handle e.g., tool changes, "
            "LLM changes, etc."
        ),
    )
    workspace: BaseWorkspace = Field(
        ...,
        description=(
            "Workspace used by the agent to execute commands and read/write files. "
            "Not the process working directory."
        ),
    )
    persistence_dir: str | None = Field(
        default="workspace/conversations",
        description="Directory for persisting conversation state and events. "
        "If None, conversation will not be persisted.",
    )

    max_iterations: int = Field(
        default=500,
        gt=0,
        description="Maximum number of iterations the agent can "
        "perform in a single run.",
    )
    stuck_detection: bool = Field(
        default=True,
        description="Whether to enable stuck detection for the agent.",
    )

    # 基于枚举的状态管理
    execution_status: ConversationExecutionStatus = Field(
        default=ConversationExecutionStatus.IDLE
    )
    confirmation_policy: ConfirmationPolicyBase = NeverConfirm()
    security_analyzer: SecurityAnalyzerBase | None = Field(
        default=None,
        description="Optional security analyzer to evaluate action risks.",
    )

    activated_knowledge_skills: list[str] = Field(
        default_factory=list,
        description="List of activated knowledge skills name",
    )

    activated_path_rules: list[str] = Field(
        default_factory=list,
        description=(
            "Names of path-scoped rules already injected on file-touch. "
            "Mirrors activated_knowledge_skills to dedup rule injection "
            "once per conversation."
        ),
    )

    invoked_skills: list[str] = Field(
        default_factory=list,
        description=(
            "Names of progressive-disclosure skills explicitly invoked via the "
            "`invoke_skill` tool. Parallel to `activated_knowledge_skills`, "
            "which tracks trigger-based activations."
        ),
    )

    # 钩子阻止的操作：action_id -> 阻止原因
    blocked_actions: dict[str, str] = Field(
        default_factory=dict,
        description="Actions blocked by PreToolUse hooks, keyed by action ID",
    )

    # 钩子阻止的消息：message_id -> 阻止原因
    blocked_messages: dict[str, str] = Field(
        default_factory=dict,
        description="Messages blocked by UserPromptSubmit hooks, keyed by message ID",
    )

    # 跟踪最新的用户 MessageEvent ID 以避免事件日志扫描。
    last_user_message_id: EventID | None = Field(
        default=None,
        description=(
            "Most recent user MessageEvent id for hook block checks. "
            "Updated when user messages are emitted so Agent.step can pop "
            "blocked_messages without scanning the event log. If None, "
            "hook-blocked checks are skipped (legacy conversations)."
        ),
    )

    # 对话树的可移动HEAD。
    leaf_event_id: EventID | None = Field(
        default=None,
        description=(
            "HEAD of the conversation tree: the parent of the next appended "
            "event. None means an empty tree (or, pre-feature, the linear tail; "
            "see _resolve_active_leaf). Moving it re-roots the active branch."
        ),
    )

    # 区分有意为空的 HEAD (navigate_to(None)) 和未设置的
    # ``leaf_event_id``，这会触发旧版向后兼容。 没有它，清空单根树与树前对话没有什么区别
    # 。 已持久化因此空的 HEAD 在保存/重新加载后仍然存在。 参见_resolve_active_leaf。
    #
    head_is_empty: bool = Field(default=False)

    # LLM 使用情况跟踪的对话统计信息
    stats: ConversationStats = Field(
        default_factory=ConversationStats,
        description="Conversation statistics for tracking LLM metrics",
    )

    # 机密注册表用于处理敏感数据
    secret_registry: SecretRegistry = Field(
        default_factory=SecretRegistry,
        description="Registry for handling secrets and sensitive data",
    )

    # 用户定义的标签（键值元数据）
    tags: ConversationTags = Field(
        default_factory=dict,
        description="User-defined key-value tags for the conversation. "
        "Keys must be lowercase alphanumeric. Values are arbitrary strings "
        "up to 256 characters.",
    )

    # 智能体特定的运行时状态（简单的字典以实现灵活性）
    agent_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary for agent-specific runtime state that persists across "
        "iterations. Agents can store feature-specific state using string keys. "
        "To trigger autosave, always reassign: "
        "state.agent_state = {**state.agent_state, key: value}. "
        "See https://docs.openhands.dev/sdk/guides/convo-persistence#how-state-persistence-works",
    )

    # 对话的钩子配置
    hook_config: HookConfig | None = Field(
        default=None,
        description=(
            "Hook configuration for this conversation. Includes definitions for "
            "PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, SessionEnd, "
            "and Stop hooks. When set, these hooks are executed at the appropriate "
            "points during conversation execution."
        ),
    )

    # ===== 私有属性（不字段）=====
    _fs: FileStore = PrivateAttr(default=cast(Any, None))  # 持久化的文件存储
    _events: EventLog = PrivateAttr()  # 现在是事件的存储
    # *活动分支*的`_events`的缓存投影，在读取时延迟更新。 派生状态——从不已持久化。
    # `_view_branch_leaf` 是缓存反映的已解析叶子：等于活动叶子 -> 重用； 祖先 -> 用尾巴
    # 延伸； 否则 -> 重建（分支切换）。 参见
    # https://github.com/OpenHands/software-agent-sdk/issues/3053.
    #
    _view: View = PrivateAttr(default_factory=View)
    _view_branch_leaf: EventID | None = PrivateAttr(default=None)
    _view_lock: threading.RLock = PrivateAttr(default_factory=threading.RLock)
    _cipher: Cipher | None = PrivateAttr(default=None)  # 机密加密的密码
    _autosave_enabled: bool = PrivateAttr(default=False)  # 以避免 init 期间的递归
    _on_state_change: ConversationCallbackType | None = PrivateAttr(
        default=None
    )  # 回调用于状态更改
    _write_guard: Callable[[], AbstractContextManager[None]] | None = PrivateAttr(
        default=None
    )
    _lock: FIFOLock = PrivateAttr(default_factory=FIFOLock)  # FIFO 锁为线程安全
    _save_depth: int = PrivateAttr(default=0)  # 上下文-管理器嵌套深度
    _dirty: bool = PrivateAttr(default=False)  # 待处理的未保存字段更改

    @property
    def events(self) -> EventLog:
        return self._events

    def _resolve_active_leaf(self) -> EventID | None:
        """有效HEAD，按谱系解析``None````leaf_event_id``。

        设置的叶子按原样返回。 ``head_is_empty`` 标记故意为空的 HEAD (
        ``navigate_to(None)``) -> 没有活动分支。
        否则，``None`` 叶（功能前对话）会回退到最后一个 *real* 事件，因此遗留历史记录
        将不分支加载。

        尾随非树工件 - ``ConversationStateUpdateEvent`` 或
        ``ConversationErrorEvent`` 一个新服务器在中断启动期间可能写入了遗留尾部 -- 被
        跳过：它们不是树节点（见
        ``append_event``），因此将一个视为叶子节点会同时使它成为下一个事件的父节点，
        并且因为它携带 ``parent_id``，会切断遗留线性回退方
        案并打断所有先前的历史（#4057）。
        """
        if self.leaf_event_id is not None:
            return self.leaf_event_id
        if self.head_is_empty:
            return None
        if len(self._events) == 0:
            return None
        from openhands.sdk.event.conversation_error import ConversationErrorEvent
        from openhands.sdk.event.conversation_state import (
            ConversationStateUpdateEvent,
        )

        artifacts = (ConversationStateUpdateEvent, ConversationErrorEvent)
        for i in range(len(self._events) - 1, -1, -1):
            if not isinstance(self._events[i], artifacts):
                return self._events.get_id(i)
        return None

    def active_branch(self, limit: int | None = None) -> list[Event]:
        """活动分支 (``path_to_root(leaf)``) 上的原始事件，根优先。

        排除废弃的分支，因此消费者对 *当前* 对话（卡住检测、待处理操作）进行推理时只
        能看到实时路径。
        ``limit`` 仅返回最后 ``limit`` 个事件，保留 O(limit)。
        """
        return self._events.path_to_root(self._resolve_active_leaf(), limit=limit)

    def _stamp_parent_id(self, event: Event) -> Event:
        """如果未设置，则返回 ``event``，并将 ``parent_id`` 设置为活动叶。"""
        if event.parent_id is not None:
            return event
        parent = self._resolve_active_leaf()
        # 在非空日志上清空 HEAD = 有意的新根 (navigate_to(None))； 对其进行标记，以免将
        # 其误读为与其邻居相关的遗留事件。
        #
        if parent is None and len(self._events) > 0:
            parent = ROOT_PARENT_ID
        return event.model_copy(update={"parent_id": parent})

    def append_event(self, event: Event) -> int:
        """单一存储瓶颈：标记parent_id、追加、前进HEAD。

        此处的标记（不仅在发出回调处）可确保没有事件进入未标记的日志，即使是下游的钩
        子交换也是如此。 ``fork`` 复制预先标记的事件并设置 HEAD 本身，因
        此它绕过了这一点。

        Returns:
            分配给附加事件的序列号 ``EventLog``。
        """
        event = self._stamp_parent_id(event)
        seq = self._events.append(event)
        # ConversationStateUpdateEvent 是状态同步工件，而不是树节点； 前进 HEAD 因为它会
        # 递归（移动 HEAD 会重新发出一个）。
        #
        from openhands.sdk.event.conversation_state import (
            ConversationStateUpdateEvent,
        )

        if not isinstance(event, ConversationStateUpdateEvent):
            self.leaf_event_id = event.id
            if self.head_is_empty:  # HEAD现在再次指向真实事件
                self.head_is_empty = False
        return seq

    @property
    def view(self) -> View:
        """活动分支 (``path_to_root(leaf)``) 的延迟维护 ``View``。

        废弃的分支（来自导航/分叉）被排除在外。 线性追加仅重播新的尾部 - O(k)，保留增
        量优化（#3053）； 分支交换机重建一次，O(n)。
        ``enforce_properties`` 仅在重建 (``rebuild_view()``) 时运行。

        返回的视图为只读，被``rebuild_view()``失效； 重建后重新阅读 ``state.view``。
        """
        with self._view_lock:
            leaf = self._resolve_active_leaf()
            if leaf == self._view_branch_leaf:
                return self._view

            # 快速路径：缓存的叶子是新叶子的祖先（线性追加）→仅重播尾部。 还涵盖了第一个
            # 填充（缓存叶 None，缓存视图为空），避免了 enforce_properties 传递。
            #
            try:
                tail: list[Event] = []
                cur_id: EventID | None = leaf
                while cur_id is not None and cur_id != self._view_branch_leaf:
                    idx = self._events.get_index(cur_id)
                    evt = self._events[idx]
                    tail.append(evt)
                    cur_id = self._events._effective_parent_id(idx, evt)
                if cur_id == self._view_branch_leaf:
                    for evt in reversed(tail):
                        self._view.append_event(evt)
                    self._view_branch_leaf = leaf
                    return self._view
            except Exception:
                logger.warning(
                    "Incremental view append failed for leaf %s; "
                    "rebuilding from the active branch.",
                    leaf,
                    exc_info=True,
                )

            # 分叉分支（导航/分叉），首先填充，或恢复
            # from the failure above → full rebuild from the active branch.
            self._view = View.from_events(self._events.path_to_root(leaf))
            self._view_branch_leaf = leaf
            return self._view

    def enforced_view_snapshot(self) -> View:
        """返回一个隔离视图，其中删除了不完整的工具调用批次。"""
        with self._view_lock:
            events = list(self.view.events)
            return View.from_events(events)

    def rebuild_view(self) -> None:
        """从活动分支重新派生缓存视图，并完全强制执行。

        在 ``path_to_root(leaf)`` 上运行 ``View.from_events``。 调用冷加载、分叉、导
        航和错误恢复。 使之前的任何内容都
        无效
        ``state.view`` 参考。 如果 ``View.from_events`` 引发，则缓存保持不变并且异常
        传播。
        """
        with self._view_lock:
            leaf = self._resolve_active_leaf()
            branch = self._events.path_to_root(leaf)
            self._view = View.from_events(branch)
            self._view_branch_leaf = leaf

    @property
    def env_observation_persistence_dir(self) -> str | None:
        """持久环境观测结果文件的目录。"""
        if self.persistence_dir is None:
            return None
        return str(Path(self.persistence_dir) / "observations")

    def set_on_state_change(self, callback: ConversationCallbackType | None) -> None:
        """设置状态改变时调用的回调。

        Args:
            callback: 接受事件 (ConversationStateUpdateEvent) 的函数
                     或 None 删除回调
        """
        self._on_state_change = callback

    def set_write_guard(
        self,
        write_guard: Callable[[], AbstractContextManager[None]] | None,
    ) -> None:
        self._write_guard = write_guard
        self._events.set_write_guard(write_guard)

    # ===== 基本快照助手（与您的 FileStore 用法相同）=====
    def _save_base_state(self, fs: FileStore) -> None:
        """
        持久化基本状态快照（无事件； 事件由文件支持）。

        如果配置了密码，机密将被加密。 否则，它们将为已脱敏（已序列化为“**********”）
        。
        """
        context = {"cipher": self._cipher} if self._cipher else None
        # 如果机密存在但未配置密码则发出警告
        if not self._cipher and self.secret_registry.secret_sources:
            logger.warning(
                f"Saving conversation state without cipher - "
                f"{len(self.secret_registry.secret_sources)} secret(s) will be "
                "redacted and lost on restore. Consider providing a cipher to "
                "preserve secrets."
            )
        payload = self.model_dump_json(exclude_none=True, context=context)
        if self._write_guard is None:
            fs.write(BASE_STATE, payload)
        else:
            with self._write_guard():
                fs.write(BASE_STATE, payload)

    # ===== 工厂：打开或创建（无需加载/保存方法）=====
    @classmethod
    def create(
        cls: type["ConversationState"],
        id: ConversationID,
        agent: AgentBase | None,
        workspace: BaseWorkspace,
        persistence_dir: str | None = None,
        max_iterations: int = 500,
        stuck_detection: bool = True,
        cipher: Cipher | None = None,
        tags: dict[str, str] | None = None,
        file_store: FileStore | None = None,
    ) -> "ConversationState":
        """创建新的对话状态或从持久化恢复。

        该工厂方法处理新对话的创建和恢复
        from persisted state.

        **新对话：**
        直接使用提供的智能体。 Pydantic 验证通过 cls() 构造函数发生。

        **恢复的对话：**
        使用 agent.load() 针对已持久化智能体验证提供的智能体。 工具必须匹配（它们可能
        在对话历史中使用过），但其他配置可以自由更改：LLM、
        agent_context、上下文压缩器、系统提示词等。

        Args:
            id: 唯一的对话标识符
            agent: 要使用的智能体（恢复时工具必须与已持久化匹配）
            workspace: 工作目录用于智能体操作
            persistence_dir: 保存状态和事件的目录
                未提供file_store。 当提供 file_store 时，该值仍存储在状态中并用于环境
                观测结果路径。
            max_iterations: 每次运行的最大迭代次数
            stuck_detection: 是否启用卡顿检测
            cipher: 用于加密/解密机密的可选密码
                    已持久化状态。 如果提供，机密在保存时加密，在加载时解密。 如果未
                    提供，机密将在序列化上为已脱敏（丢失）。
            tags: 对话的可选键值标签。 钥匙必须是
                  小写字母数字，值最多 256 个字符。
            file_store: 可选 FileStore 用于状态和 EventLog
                持久化。 如果提供，则其优先于状态 persistence_dir 和存储 EventLog。

        Returns:
            ConversationState 可供使用

        Raises:
            ValueError: 如果恢复时对话 ID 或工具不匹配
            ValidationError: 如果智能体或其他字段失败 Pydantic 验证
        """
        if file_store is None:
            if persistence_dir:
                file_store = LocalFileStore(
                    persistence_dir, cache_limit_size=max_iterations
                )
            else:
                logger.warning(
                    "No persistence_dir provided; falling back to InMemoryFileStore. "
                    "EventLog data will not persist across requests."
                )
                file_store = InMemoryFileStore()

        try:
            base_text = file_store.read(BASE_STATE)
        except FileNotFoundError:
            base_text = None

        # ---- 恢复路径 ----
        if base_text:
            # 使用密码上下文解密机密（如果提供）
            context = {"cipher": cipher} if cipher else None
            state = cls.model_validate(json.loads(base_text), context=context)

            # 恢复同id的对话
            if state.id != id:
                raise ValueError(
                    f"Conversation ID mismatch: provided {id}, "
                    f"but persisted state has {state.id}"
                )

            # 尽早附加事件日志，以便我们可以读取历史记录以进行工具验证
            state._fs = file_store
            state._events = EventLog(file_store, dir_path=EVENTS_DIR)
            state._cipher = cipher

            # 冷加载：通过完整的属性强制重建缓存视图 - 已持久化事件可能来自较旧的代码版
            # 本或已损坏。
            #
            state.rebuild_view()

            # 提交运行时提供的值（可以自动保存）
            state._autosave_enabled = True
            # 智能体：base_state.json 是唯一的事实来源。 当
            # 调用者不提供智能体 (``agent is None``)，保持已持久化不变——这就是让已持久化
            #  switch_llm 在空闲驱逐重载中幸存下来的原因。 当调用者 * 确实 * 提供智能体
            # （遗留行为）时，验证工具兼容性并
            #
            # let it override, so existing callers that reconfigure on resume
            # 继续工作。
            if agent is not None:
                agent.verify(state.agent, events=state._events)
                state.agent = agent
            state.workspace = workspace
            state.max_iterations = max_iterations

            # 注意：统计数据已经是上面 base_state.json 的已反序列化。
            # 请不在此处重置统计数据 - 这将丢失累积的指标。

            logger.info("Resumed conversation %s from persistent storage", state.id)
            return state

        # ----新鲜之路----
        if agent is None:
            raise ValueError(
                "agent is required when initializing a new ConversationState"
            )

        state = cls(
            id=id,
            agent=agent,
            workspace=workspace,
            persistence_dir=persistence_dir,
            max_iterations=max_iterations,
            stuck_detection=stuck_detection,
            tags=tags or {},
        )
        state._fs = file_store
        state._events = EventLog(file_store, dir_path=EVENTS_DIR)
        state._cipher = cipher
        state.stats = ConversationStats()

        state._save_base_state(file_store)  # 初始快照
        state._autosave_enabled = True
        logger.info("Created new conversation %s", state.id)
        return state

    # ===== 自动持久化基于公共字段更改 =====
    def __setattr__(self, name, value):
        # 仅在以下情况下自动保存：
        # - 自动保存已启用（设置后初始化）
        # - 该属性是 * 公共字段 *（不是 PrivateAttr）
        # - 我们有一个要写入的文件存储
        _sentinel = object()
        old = getattr(self, name, _sentinel)
        super().__setattr__(name, value)

        is_field = name in self.__class__.model_fields
        autosave_enabled = self._autosave_enabled
        fs = self._fs

        if not (autosave_enabled and is_field and fs is not None):
            return

        if old is _sentinel or old != value:
            # 在上下文-manager 块内，将保存推迟到 __exit__，以便多个字段突变产生单个 I/O
            #  写入。
            #
            if self._save_depth > 0:
                self._dirty = True
            else:
                try:
                    self._save_base_state(fs)
                except Exception as e:
                    logger.exception("Auto-persist base_state failed", exc_info=True)
                    raise e

            # 如果设置，则调用状态更改回调。 leaf_event_id/head_is_empty 是
            # 跳过：它们是内部 HEAD 簿记（leaf_event_id 更改
            # 每个事件，因此广播它将使已持久化日志加倍）并且 HEAD 可以从刚刚附加的事件中
            # 恢复。
            #
            callback = self._on_state_change
            if (
                callback is not None
                and old is not _sentinel
                and name not in ("leaf_event_id", "head_is_empty")
            ):
                try:
                    # 在这里导入以避免循环导入
                    from openhands.sdk.event.conversation_state import (
                        ConversationStateUpdateEvent,
                    )

                    # 使用更改的字段创建 ConversationStateUpdateEvent
                    state_update_event = ConversationStateUpdateEvent(
                        key=name, value=value
                    )
                    callback(state_update_event)
                except Exception:
                    logger.exception(
                        f"State change callback failed for field {name}", exc_info=True
                    )

    def block_action(self, action_id: str, reason: str) -> None:
        """持久记录钩子被阻挡的动作。"""
        self.blocked_actions = {**self.blocked_actions, action_id: reason}

    def pop_blocked_action(self, action_id: str) -> str | None:
        """删除并返回钩子阻止操作原因（如果存在）。"""
        if action_id not in self.blocked_actions:
            return None
        updated = dict(self.blocked_actions)
        reason = updated.pop(action_id)
        self.blocked_actions = updated
        return reason

    def block_message(self, message_id: str, reason: str) -> None:
        """持久记录钩子阻塞的用户消息。"""
        self.blocked_messages = {**self.blocked_messages, message_id: reason}

    def pop_blocked_message(self, message_id: str) -> str | None:
        """删除并返回钩子阻止消息原因（如果存在）。"""
        if message_id not in self.blocked_messages:
            return None
        updated = dict(self.blocked_messages)
        reason = updated.pop(message_id)
        self.blocked_messages = updated
        return reason

    @staticmethod
    def get_unmatched_actions(events: Sequence[Event]) -> list[ActionEvent]:
        """查找事件历史记录中没有匹配观测结果的操作。

        该方法识别 ActionEvents 与 ObservationEvents、UserRejectObservations 或
        AgentErrorEvents 无对应关系，这通常表示需要确认或执行的动作。

        Note: AgentErrorEvent 与 tool_call_id 匹配，而不是 action_id
        它没有 action_id 字段。 这对于服务器重新启动后发出错误事件的崩溃恢复场景非常
        重要。

        Args:
            events: 要搜索的事件列表

        Returns:
            没有对应观测结果的 ActionEvent 对象列表，按时间顺序排列
        """
        observed_action_ids: set[EventID] = set()
        observed_tool_call_ids: set[str] = set()
        unmatched_actions = []
        # 反向搜索 - 最近发生的事件更有可能是无法匹配的
        for event in reversed(events):
            if isinstance(event, (ObservationEvent, UserRejectObservation)):
                observed_action_ids.add(event.action_id)
            elif isinstance(event, AgentErrorEvent):
                # AgentErrorEvent 没有 action_id，匹配 tool_call_id
                observed_tool_call_ids.add(event.tool_call_id)
            elif isinstance(event, ActionEvent):
                # 仅可执行操作（已验证）被视为待处理检查 action_id 和 tool_call_id 是否
                # 匹配
                #
                if (
                    event.action is not None
                    and event.id not in observed_action_ids
                    and event.tool_call_id not in observed_tool_call_ids
                ):
                    # 在开头插入以维持结果中的时间顺序
                    unmatched_actions.insert(0, event)

        return unmatched_actions

    # ===== FIFOLock 授权方法 =====
    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """
        获取锁。

        Args:
            blocking: 如果True，则阻塞直到获取锁。 如果False，则返回
                     立即。
            timeout: 等待锁的最长时间（如果阻塞=False，则忽略）。
                    -1 表示无限期等待。

        Returns:
            如果获取了锁，则为 True，否则为 False。
        """
        return self._lock.acquire(blocking=blocking, timeout=timeout)

    def release(self) -> None:
        """
        释放锁。

        Raises:
            RuntimeError: 如果当前的线程不拥有锁。
        """
        self._lock.release()

    def __enter__(self: Self) -> Self:
        """上下文管理器条目。

        ``with`` 块内的字段突变是批处理的：状态最多为已持久化一次，在退出时，而不是每
        次分配时。
        """
        self._lock.acquire()
        self._save_depth += 1
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """上下文管理器 exit — 刷新任何延迟保存。"""
        try:
            self._save_depth -= 1
            if self._save_depth == 0 and self._dirty:
                fs = self._fs
                autosave_enabled = self._autosave_enabled
                if autosave_enabled and fs is not None:
                    self._save_base_state(fs)
                self._dirty = False
        finally:
            self._lock.release()

    def locked(self) -> bool:
        """
        如果锁当前被任意线程持有，则返回 True。
        """
        return self._lock.locked()

    def owned(self) -> bool:
        """
        如果锁当前由调用方线程持有，则返回 True。
        """
        return self._lock.owned()
