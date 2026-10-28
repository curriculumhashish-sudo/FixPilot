import asyncio
import time
import traceback
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, suppress
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from pydantic import ValidationError

from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.conversation_lease import (
    DEFAULT_LEASE_TTL_SECONDS,
    ConversationLease,
    ConversationOwnershipLostError,
)
from openhands.agent_server.managed_llm_key import register_managed_llm_key_refresh
from openhands.agent_server.models import (
    ConfirmationResponseRequest,
    EventPage,
    EventSortOrder,
    StoredConversation,
)
from openhands.agent_server.pub_sub import PubSub, Subscriber
from openhands.agent_server.server_details_router import update_last_execution_time
from openhands.sdk import LLM, AgentBase, Event, Message, TextContent, get_logger
from openhands.sdk.agent import ACPAgent
from openhands.sdk.agent.acp_agent import ACTIVITY_SIGNAL_INTERVAL
from openhands.sdk.agent.acp_file_credentials import (
    CODEX_AUTH_SECRET_NAME,
    is_valid_codex_auth,
)
from openhands.sdk.agent.stream_context import StreamProgress
from openhands.sdk.conversation.base import BaseConversation
from openhands.sdk.conversation.event_store import EventLog
from openhands.sdk.conversation.events_list_base import EventsListBase
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.conversation.goal import (
    GoalController,
    GoalDone,
    GoalOutcome,
    GoalStatus,
    GoalStatusName,
    GoalStep,
    GoalVerdict,
)
from openhands.sdk.conversation.goal.prompts import RESUME_PROMPT
from openhands.sdk.conversation.impl.local_conversation import (
    ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID,
    ACP_SUPERSEDE_INFLIGHT_PROMPT,
    LocalConversation,
)
from openhands.sdk.conversation.persistence_const import BASE_STATE, EVENTS_DIR
from openhands.sdk.conversation.response_utils import get_agent_final_response
from openhands.sdk.conversation.secret_registry import SecretValue
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.conversation.types import ConversationCallbackType
from openhands.sdk.credential import (
    CredentialBindingError,
    CredentialNeedsReauthentication,
    HttpVersionedCredentialBinding,
    VersionedCredentialBinding,
)
from openhands.sdk.event import (
    AgentErrorEvent,
    ObservationBaseEvent,
    StreamingDeltaEvent,
)
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.event.error_classification import ErrorClassification, FailureKind
from openhands.sdk.event.llm_completion_log import LLMCompletionLogEvent
from openhands.sdk.git.exceptions import GitCommandError, GitRepositoryError
from openhands.sdk.git.utils import run_git_command, validate_git_repository
from openhands.sdk.io import LocalFileStore
from openhands.sdk.llm.streaming import LLMStreamChunk
from openhands.sdk.mcp.utils import MCPToolProvider
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.confirmation_policy import ConfirmationPolicyBase
from openhands.sdk.utils.async_utils import AsyncCallbackWrapper
from openhands.sdk.utils.cipher import Cipher
from openhands.sdk.utils.files import atomic_write_text
from openhands.sdk.workspace import LocalWorkspace


LEASE_RENEW_INTERVAL_SECONDS = 15.0
# 限制初始状态推送，因此 subscribe_to_events 不会在 __call__ 阻塞的订阅者上停滞 (e.g. WS
#  具有完整的 TCP 发送缓冲区）。
#
INITIAL_STATE_PUSH_TIMEOUT_SECONDS = 0.5


logger = get_logger(__name__)


class ConversationRunLimitExceeded(RuntimeError):
    """服务器无法启动另一个会话运行。"""


class CondensationUnavailable(ValueError):
    """对话的智能体没有处理请求的上下文压缩器。"""


class _RunPermit:
    """由一个准入会话的连锁运行共享的参考计数许可证。"""

    __slots__ = ("semaphore", "refs")

    def __init__(self, semaphore: asyncio.Semaphore | None) -> None:
        self.semaphore = semaphore
        self.refs = 0


class RunSlot:
    """运行许可证，在一次入场会话的链式运行中共享。

    对话中包含在*链*中：一个重新武装以处理在处理过程中搁置的输入的运行，每一轮的
    ``/goal``循环，以及在内部ACP超前中断后的替换运行。 每次分配一个新的许可，
    就会在竞争请求可以声称刚刚释放的许可之前留下一个间隙。因此，链式运行在它的前一个
    已经释放（或，对于ACP来说，已经调用者已经杀死在途的提示词）之后就会得到一个虚假的
    429。 共享一个许可解决了这一差距：token 原子信号返回只有在会话许可被释放后才返回
    一次。
    """

    def __init__(self, permit: _RunPermit) -> None:
        self._permit: _RunPermit | None = permit
        permit.refs += 1

    @classmethod
    async def acquire(
        cls, semaphore: asyncio.Semaphore | None, *, wait: bool = False
    ) -> "RunSlot":
        if semaphore is not None:
            if not wait:
                # 当容量可用时，acquire() 无法挂起，因此此检查和获取在服务器的事件循环上
                # 是原子的。
                #
                if semaphore.locked():
                    raise ConversationRunLimitExceeded(
                        "Conversation run limit reached. Retry the request later."
                    )
            # ``wait=True`` 表示调用者已被告知其消息已被接受的延续（重新武装运行）。 它
            # 会阻塞 token，而不是变成会浪费输入的虚假 429。
            #
            await semaphore.acquire()
        return cls(_RunPermit(semaphore))

    def share(self) -> "RunSlot":
        """返回同一许可证的另一个实时句柄（无新的 token）。"""
        permit = self._permit
        if permit is None:
            raise RuntimeError("run slot has already been released")
        return RunSlot(permit)

    @property
    def live_handles(self) -> int:
        """当前持有此许可证的句柄数量（释放后为 0）。"""
        permit = self._permit
        return permit.refs if permit is not None else 0

    def release(self) -> bool:
        """返回这个句柄。 True 前提是基础许可证已退回。"""
        permit = self._permit
        if permit is None:
            return False
        self._permit = None
        permit.refs -= 1
        if permit.refs <= 0 and permit.semaphore is not None:
            permit.semaphore.release()
            permit.semaphore = None
            return True
        return False

    def __enter__(self) -> "RunSlot":
        return self

    def __exit__(self, *_exc) -> None:
        self.release()


class CredentialBindingActivationTooLate(RuntimeError):
    pass


def _log_emit_failure(event_kind: str, future: "asyncio.Future[None]") -> None:
    """记录执行器内部失败的事件发射线程。"""
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        logger.error(
            "Failed to emit %s from thread: %s", event_kind, error, exc_info=error
        )


def _without_agent_context_secret(
    agent: AgentBase,
    secret_name: str,
) -> AgentBase:
    context = agent.agent_context
    if context is None or not context.secrets or secret_name not in context.secrets:
        return agent
    secrets = dict(context.secrets)
    secrets.pop(secret_name, None)
    return agent.model_copy(
        update={"agent_context": context.model_copy(update={"secrets": secrets})}
    )


@dataclass
class EventService:
    """
    用于本地运行的对话的事件服务，类似于 SDK 中的对话。 异步主要用于向前兼容性
    """

    stored: StoredConversation
    conversations_dir: Path
    # 智能体用于 NEW 对话。 meta.json (``stored``) 不再携带智能体 - base_state.json 是其
    # 唯一的事实来源 - 因此创建调用者将其传递到此处。 恢复时这是 ``None``，智能体已加载
    #
    # from base_state.json.
    agent: AgentBase | None = None
    cipher: Cipher | None = None
    mcp_tool_provider: MCPToolProvider | None = None
    credential_bindings: dict[str, VersionedCredentialBinding] = field(
        default_factory=dict
    )
    bash_event_service: BashEventService | None = field(default=None, init=False)
    owner_instance_id: str = field(default_factory=lambda: uuid4().hex)
    lease_ttl_seconds: float = DEFAULT_LEASE_TTL_SECONDS
    _conversation: LocalConversation | None = field(default=None, init=False)
    _persisted_events: EventLog | None = field(default=None, init=False)
    _pub_sub: PubSub[Event] = field(
        default_factory=lambda: PubSub[Event](max_subscribers=50), init=False
    )
    # 它自己的扇出，而不是事件总线：帧不是事件，只有会话套接字消耗它们。
    #
    _stream_pub_sub: PubSub[StreamProgress] = field(
        default_factory=lambda: PubSub[StreamProgress](max_subscribers=50), init=False
    )
    _run_task: asyncio.Task | None = field(default=None, init=False)
    # 当 send_message(run=True) 由于运行仍在结束而被拒绝时设置； 由 _run_and_publish 消
    # 耗以重新运行搁浅的消息。
    #
    _rerun_requested: bool = field(default=False, init=False)
    # 仅针对由新的 send_message(run=True) 触发的内部 ACP 中断/重启路径进行设置。 显式用
    # 户暂停/中断会清除它，因此用户停止意图胜过早期的自动重新启动请求。
    #
    _acp_internal_rerun_requested: bool = field(default=False, init=False)
    # 针对明确的用户暂停/中断请求而增加。 内部 ACP 优先级高于重启，重启后，此生成物的停
    # 止/暂停不能被自动重启覆盖。
    #
    _explicit_interrupt_generation: int = field(default=0, init=False)
    _closing: bool = field(default=False, init=False)
    _run_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _callback_wrapper: AsyncCallbackWrapper | None = field(default=None, init=False)
    _lease: ConversationLease | None = field(default=None, init=False)
    _lease_generation: int | None = field(default=None, init=False)
    _lease_task: asyncio.Task | None = field(default=None, init=False)
    _external_lease_renewal: bool = field(default=False, init=False)
    _run_executor: ThreadPoolExecutor | None = field(default=None, init=False)
    _run_semaphore: asyncio.Semaphore | None = field(default=None, init=False)
    # 允许此对话的当前入场会话。 整个链路的所有运行（初始运行，任何重新武装以处理断流输
    # 入的运行） ACP 取代重启，每次 /goal 因此，在前驱释放许可的间隙中，链式运行不能被拒
    # 绝。 当链结束时发布（见 ） _maybe_end_run_session).
    #
    _run_session_slot: RunSlot | None = field(default=None, init=False)
    # 计数器：即使没有当前活跃的任务，也必须保持会话许可的在途延续（一个活的/goal循环，
    # 或者中断旧的ACP和启动新任务之间的提示词窗口）。
    #
    _run_session_pins: int = field(default=0, init=False)
    # 在此对话中运行的 /goal 循环的后台任务。
    _goal_loop_task: asyncio.Task | None = field(default=None, init=False)
    _goal_loop_outcome: GoalOutcome | None = field(default=None, init=False)
    # 最后一个活动的单调时钟，用于空闲驱逐。
    _last_active_monotonic: float = field(default_factory=time.monotonic, init=False)
    # 最后一次节流流式传输心跳的单调时钟。
    _last_stream_activity_signal: float = field(default=float("-inf"), init=False)
    # 启动时附加的订阅者； 后来的（e.g. WebSocket) 是外部的。
    _internal_subscriber_ids: set[UUID] = field(default_factory=set, init=False)

    @property
    def conversation_dir(self):
        return self.conversations_dir / self.stored.id.hex

    async def load_meta(self):
        meta_file = self.conversation_dir / "meta.json"
        self.stored = StoredConversation.model_validate_json(
            meta_file.read_text(),
            context={
                "cipher": self.cipher,
            },
        )

    async def save_meta(self, stored: StoredConversation | None = None) -> None:
        """持久化 ``stored``（默认：当前元数据）到 ``meta.json``。

        只有写入成功后，新的``stored``才变为``self.stored``，因此拒绝写入(e.g. 失去租
        赁所有权）没有留下明显的变化。
        """
        new_stored = self.stored if stored is None else stored
        with self._write_guard():
            meta_file = self.conversation_dir / "meta.json"
            atomic_write_text(
                meta_file,
                new_stored.model_dump_json(
                    context={
                        "cipher": self.cipher,
                    }
                ),
            )
        self.stored = new_stored

    def _without_stored_secret(self, secret_name: str) -> StoredConversation:
        # meta.json (StoredConversation) 不再携带智能体，因此这里没有 agent_context 机密
        # 可以擦除——只有存储的机密映射。 智能体自己的机密清理发生在 base_state.json 上（
        # 参见 _scrub_persisted_credentials）。
        #
        secrets = dict(self.stored.secrets)
        secrets.pop(secret_name, None)
        return self.stored.model_copy(update={"secrets": secrets})

    async def _scrub_persisted_credentials(
        self,
        credential_bindings: Mapping[str, VersionedCredentialBinding] | None = None,
    ) -> None:
        bindings = (
            self.credential_bindings
            if credential_bindings is None
            else credential_bindings
        )
        if not bindings:
            return

        required_bindings = {
            name
            for name, binding in bindings.items()
            if isinstance(binding, HttpVersionedCredentialBinding)
        }
        if required_bindings:
            # 擦洗过的耐用凭据绝不能再次成为回退方案。
            self.stored = self.stored.model_copy(
                update={
                    "required_runtime_credential_bindings": (
                        self.stored.required_runtime_credential_bindings
                        | required_bindings
                    )
                }
            )

        context = {"cipher": self.cipher}
        base_state_file = self.conversation_dir / BASE_STATE
        meta_file = self.conversation_dir / "meta.json"
        legacy_auth_file = self.conversation_dir / "acp" / "codex" / "auth.json"
        codex_binding = bindings.get(CODEX_AUTH_SECRET_NAME)
        if codex_binding is not None and legacy_auth_file.exists():
            resolved = await codex_binding.load()
            if not is_valid_codex_auth(resolved.value):
                raise CredentialNeedsReauthentication(
                    "ChatGPT authentication is invalid. Please sign in again."
                )
        for secret_name in bindings:
            self.stored = self._without_stored_secret(secret_name)

        if (
            not base_state_file.exists()
            and not meta_file.exists()
            and not legacy_auth_file.exists()
        ):
            return

        with self._write_guard():
            if base_state_file.exists():
                state = ConversationState.model_validate_json(
                    base_state_file.read_text(),
                    context=context,
                )
                sources = dict(state.secret_registry.secret_sources)
                for secret_name in bindings:
                    sources.pop(secret_name, None)
                    state.agent = _without_agent_context_secret(
                        state.agent,
                        secret_name,
                    )
                state.secret_registry = state.secret_registry.model_copy(
                    update={"secret_sources": sources}
                )
                atomic_write_text(
                    base_state_file,
                    state.model_dump_json(exclude_none=True, context=context),
                )

            if meta_file.exists():
                atomic_write_text(
                    meta_file,
                    self.stored.model_dump_json(context=context),
                )
            if codex_binding is not None:
                legacy_auth_file.unlink(missing_ok=True)

    async def activate_credential_binding(
        self,
        secret_name: str,
        binding: VersionedCredentialBinding,
    ) -> None:
        existing = self.credential_bindings.get(secret_name)
        if isinstance(existing, HttpVersionedCredentialBinding) and isinstance(
            binding, HttpVersionedCredentialBinding
        ):
            if existing.url != binding.url:
                raise CredentialBindingActivationTooLate
            await self._scrub_persisted_credentials(
                {**self.credential_bindings, secret_name: binding}
            )
            existing.reauthorize(binding)
            return
        if existing is not None:
            raise CredentialBindingActivationTooLate

        conversation = self._conversation
        if conversation is None:
            raise CredentialBindingActivationTooLate

        state = conversation._state
        with state:
            if not isinstance(conversation.agent, ACPAgent):
                raise CredentialBindingActivationTooLate
            agent = cast(
                ACPAgent,
                _without_agent_context_secret(conversation.agent, secret_name),
            )
            try:
                agent.activate_file_credential_binding(secret_name, binding)
            except RuntimeError as exc:
                raise CredentialBindingActivationTooLate from exc

            self.credential_bindings[secret_name] = binding
            sources = dict(state.secret_registry.secret_sources)
            sources.pop(secret_name, None)
            state.secret_registry = state.secret_registry.model_copy(
                update={"secret_sources": sources}
            )
            state.agent = agent
            conversation.agent = agent
            self.stored = self._without_stored_secret(secret_name)
        await self._scrub_persisted_credentials()

    async def apply_resume_secrets(
        self,
        secrets: dict[str, SecretValue],
    ) -> None:
        conversation = self._conversation
        if conversation is None:
            raise ValueError("inactive_service")
        secrets = {
            name: value
            for name, value in secrets.items()
            if name not in self.credential_bindings
        }
        if not secrets:
            return

        def _update() -> None:
            state = conversation._state
            with state:
                registry = state.secret_registry.model_copy(
                    update={
                        "secret_sources": dict(state.secret_registry.secret_sources)
                    }
                )
                registry.update_secrets(secrets)
                state.secret_registry = registry
                agent = conversation.agent
                if isinstance(agent, ACPAgent):
                    agent.restart_for_updated_credentials(secrets)

        await asyncio.to_thread(_update)
        await self.save_meta(
            self.stored.model_copy(
                update={"secrets": {**self.stored.secrets, **secrets}}
            )
        )

    def _write_guard(self):
        if self._lease is None or self._lease_generation is None:
            return nullcontext()
        return self._lease.guarded_write(self._lease_generation)

    def renew_lease(self) -> None:
        """续订此服务的会话租约。

        由集中式更新循环（当 ``_external_lease_renewal`` 为 True 时）或由每个服务
        ``_renew_lease_loop`` 后
        台任务调用。
        """
        if self._lease is None or self._lease_generation is None:
            return
        try:
            self._lease.renew(self._lease_generation)
        except ConversationOwnershipLostError:
            logger.warning(
                "Conversation lease lost while renewing: %s",
                self.stored.id,
            )
        except Exception:
            logger.exception(
                "Failed to renew conversation lease for %s",
                self.stored.id,
            )

    async def _renew_lease_loop(self) -> None:
        if self._lease is None or self._lease_generation is None:
            return
        try:
            while True:
                await asyncio.sleep(LEASE_RENEW_INTERVAL_SECONDS)
                self.renew_lease()
        except asyncio.CancelledError:
            raise

    def get_conversation(self):
        if not self._conversation:
            raise ValueError("inactive_service")
        return self._conversation

    @classmethod
    def for_persisted_events(
        cls, stored: StoredConversation, conversations_dir: Path
    ) -> "EventService":
        """打开仅附加历史记录而不启动对话运行时。"""
        service = cls(stored=stored, conversations_dir=conversations_dir)
        conversation_dir = conversations_dir / stored.id.hex
        service._persisted_events = EventLog(
            LocalFileStore(str(conversation_dir)), dir_path=EVENTS_DIR
        )
        return service

    def _events_for_read(self) -> EventLog:
        if self._persisted_events is not None:
            return self._persisted_events
        if self._conversation is None:
            raise ValueError("inactive_service")
        return self._conversation._state.events

    def _get_event_sync(self, event_id: str) -> Event | None:
        """用于获取单个事件的私有同步函数。

        直接读取  EventLog 没有获取状态锁。 EventLog 读取操作无需  FIFOLock 因为事件
        是只追加的，一旦写入就不可更改。 退货 None
         对于未知的 id。
        """
        events = self._events_for_read()
        try:
            index = events.get_index(event_id)
        except KeyError:
            return None
        return events[index]

    async def get_event(self, event_id: str) -> Event | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_event_sync, event_id)

    def _event_matches_filters(
        self,
        event: Event,
        kind: str | None,
        source: str | None,
        body: str | None,
        timestamp_gte_str: str | None,
        timestamp_lt_str: str | None,
    ) -> bool:
        """如果 ``event`` 与所有提供的过滤器匹配，则返回 True。"""
        if kind is not None:
            # 接受裸类名称（线路 ``kind`` 值，如路由文档和 TypeScript 客户端使用）或完全
            # 限定路径。
            #
            cls = type(event)
            if kind != cls.__name__ and kind != f"{cls.__module__}.{cls.__name__}":
                return False
        if source is not None and event.source != source:
            return False
        if timestamp_gte_str is not None and event.timestamp < timestamp_gte_str:
            return False
        if timestamp_lt_str is not None and event.timestamp >= timestamp_lt_str:
            return False
        # ``body`` 是最昂贵的过滤器（反序列化消息内容），因此最后评估它。
        #
        if body is not None and not self._event_matches_body(event, body):
            return False
        return True

    def _get_searchable_event(self, events: EventsListBase, index: int) -> Event | None:
        try:
            return events[index]
        except (FileNotFoundError, UnicodeDecodeError, ValidationError) as exc:
            logger.warning(
                "Skipping unreadable event at index %d for conversation %s (%s)",
                index,
                self.stored.id,
                type(exc).__name__,
            )
            return None

    def _search_events_sync(
        self,
        page_id: str | None = None,
        limit: int = 100,
        kind: str | None = None,
        source: str | None = None,
        body: str | None = None,
        sort_order: EventSortOrder = EventSortOrder.TIMESTAMP,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
    ) -> EventPage:
        """用于搜索事件的私有同步函数。

        直接读取 EventLog，而不获取状态锁。 EventLog 读操作在FIFOLock的情况下是安全的
        ，因为事件一旦写入就是只读和不可变的。

        性能：
            事件按时间顺序附加并且从不重新排序，因此磁盘索引顺序与时间戳排序顺序匹配
            。 我们通过迭代底层 ``Sequence`` 的 TIMESTAMP（向前
            ）和 TIMESTAMP_DESC（向后）来实现这一点，直到找到 ``limit + 1`` 的过滤匹
            配为止。

            这将 ``search_events`` 的 O(N) 磁盘读 + O(N log N) 排序转换为
            O(limit + skipped) 读，而不
            是排序，这是“立即加载”和“秒级加载”的区别
            for long conversations.
        """
        events = self._events_for_read()
        total = len(events)

        # 将日期时间转换为 ISO 字符串进行比较（ISO 字符串具有可比性）
        timestamp_gte_str = timestamp__gte.isoformat() if timestamp__gte else None
        timestamp_lt_str = timestamp__lt.isoformat() if timestamp__lt else None

        reverse = sort_order == EventSortOrder.TIMESTAMP_DESC

        # 将 page_id 解析为起始索引。 更喜欢 EventLog 的 O(1) id-to-index 映射； 回退到
        # 简单序列的线性扫描（e.g。 在测试中）。 未知的 page_id 会退回到迭代顺序的自然开
        # 始，与先前的行为相匹配。
        #
        start_index: int | None = None
        if page_id:
            get_index = getattr(events, "get_index", None)
            if get_index is not None:
                try:
                    start_index = get_index(page_id)
                except KeyError:
                    start_index = None
            else:
                for i in range(total):
                    event = self._get_searchable_event(events, i)
                    if event is not None and event.id == page_id:
                        start_index = i
                        break
        if start_index is None:
            start_index = total - 1 if reverse else 0

        if reverse:
            indices: range = range(start_index, -1, -1)
        else:
            indices = range(start_index, total)

        items: list[Event] = []
        next_page_id: str | None = None
        for i in indices:
            event = self._get_searchable_event(events, i)
            if event is None:
                continue
            if not self._event_matches_filters(
                event, kind, source, body, timestamp_gte_str, timestamp_lt_str
            ):
                continue
            if len(items) >= limit:
                next_page_id = event.id
                break
            items.append(event)

        return EventPage(items=items, next_page_id=next_page_id)

    async def search_events(
        self,
        page_id: str | None = None,
        limit: int = 100,
        kind: str | None = None,
        source: str | None = None,
        body: str | None = None,
        sort_order: EventSortOrder = EventSortOrder.TIMESTAMP,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
    ) -> EventPage:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._search_events_sync,
            page_id,
            limit,
            kind,
            source,
            body,
            sort_order,
            timestamp__gte,
            timestamp__lt,
        )

    def _count_events_sync(
        self,
        kind: str | None = None,
        source: str | None = None,
        body: str | None = None,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
    ) -> int:
        """用于计数事件的私有同步函数。

        直接读取 EventLog，而不获取状态锁。 EventLog 读操作在FIFOLock的情况下是安全的
        ，因为事件一旦写入就是只读和不可变的。
        """
        events = self._events_for_read()

        # 快速路径：没有过滤器，计数只是序列长度，我们可以避免从磁盘读取任何事件载荷。
        #
        if (
            kind is None
            and source is None
            and body is None
            and timestamp__gte is None
            and timestamp__lt is None
        ):
            return len(events)

        # 将日期时间转换为 ISO 字符串进行比较（ISO 字符串具有可比性）
        timestamp_gte_str = timestamp__gte.isoformat() if timestamp__gte else None
        timestamp_lt_str = timestamp__lt.isoformat() if timestamp__lt else None

        count = 0
        for i in range(len(events)):
            event = self._get_searchable_event(events, i)
            if event is None:
                continue
            if self._event_matches_filters(
                event, kind, source, body, timestamp_gte_str, timestamp_lt_str
            ):
                count += 1
        return count

    async def count_events(
        self,
        kind: str | None = None,
        source: str | None = None,
        body: str | None = None,
        timestamp__gte: datetime | None = None,
        timestamp__lt: datetime | None = None,
    ) -> int:
        """计算与给定过滤器匹配的事件数。"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._count_events_sync,
            kind,
            source,
            body,
            timestamp__gte,
            timestamp__lt,
        )

    def _get_execution_status_sync(self) -> ConversationExecutionStatus:
        if not self._conversation:
            raise ValueError("inactive_service")
        with self._conversation._state as state:
            return state.execution_status

    async def _get_execution_status(self) -> ConversationExecutionStatus:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_execution_status_sync)

    def _mark_error_status_sync(self) -> None:
        """强制对话进入 ERROR 状态（幂等后备）。

        当在对话可以设置其自己的 ERROR 状态 - e.g 之前引发运行任务时调用。
        ``init_state`` 中的异常，在 ``run()``
        /``arun()``'s try 块之外执行（通过 ``_ensure_agent_ready()``）。 如果没有这个
        ，运行最终将发布一个陈旧的非错误状
        态（IDLE/RUNNING），并且失败看起来像是一个干净的停止。 一旦状态已经是ERROR，
        就无操作。 尽力而为：从不引发（调用者是错误处理程序）。
        """
        if not self._conversation:
            return
        with self._conversation._state as state:
            if state.execution_status != ConversationExecutionStatus.ERROR:
                state.execution_status = ConversationExecutionStatus.ERROR

    def _publish_error_event_sync(self, exc: BaseException) -> None:
        """发出 ConversationErrorEvent，以便 UI 看到失败详细信息。

        对于 LLM/运行时故障，否则只会到达日志 - 运行循环后停止和自动标题生成（问题＃
        16686）。 尽力而为：从不引发（调用者是错误处理程序）。
        """
        if not self._conversation:
            return
        try:
            error_event = ConversationErrorEvent(
                source="environment",
                code=type(exc).__name__,
                detail=str(exc),
            )
            with self._conversation._state:
                self._conversation._on_event(error_event)
        except Exception:
            logger.exception("Failed to publish backstop ConversationErrorEvent")

    def _create_state_update_event_sync(self) -> ConversationStateUpdateEvent:
        if not self._conversation:
            raise ValueError("inactive_service")
        state = self._conversation._state
        with state:
            return ConversationStateUpdateEvent.from_conversation_state(state)

    async def _create_state_update_event(self) -> ConversationStateUpdateEvent:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._create_state_update_event_sync)

    def _event_matches_body(self, event: Event, body: str) -> bool:
        """检查事件的消息内容是否与正文过滤器匹配（不区分大小写）。"""
        # 在这里导入以避免循环导入
        from openhands.sdk.event.llm_convertible.message import MessageEvent
        from openhands.sdk.llm.message import content_to_str

        # 仅检查 MessageEvent 个实例的正文内容
        if not isinstance(event, MessageEvent):
            return False

        # 从消息中提取文本内容
        text_parts = content_to_str(event.llm_message.content)

        # 还要检查扩展内容（如果存在）
        if event.extended_content:
            extended_text_parts = content_to_str(event.extended_content)
            text_parts.extend(extended_text_parts)

        # 还要检查推理内容（如果存在）
        if event.reasoning_content:
            text_parts.append(event.reasoning_content)

        # 合并所有文本内容并进行不区分大小写的子串匹配
        full_text = " ".join(text_parts).lower()
        return body.lower() in full_text

    async def batch_get_events(self, event_ids: list[str]) -> list[Event | None]:
        """给定 id 列表，获取事件（或者 None 表示未找到的事件）"""
        results = await asyncio.gather(
            *[self.get_event(event_id) for event_id in event_ids]
        )
        return results

    async def reserve_run_slot(self) -> RunSlot | None:
        """在保存必须在429之后结束的输入之前，检查Claim的运行容量。

        ``None``时，表示此对话已经持有运行许可，或正在处理一个运行任务：``run()``时，
        会重用该许可或重新启动，因此不需要新的容量。 将返回的槽传递给
        ``send_message(..., run_slot=...)`` 然后释放它。

        Raises:
            ConversationRunLimitExceeded: 如果所有服务器运行槽都被占用。
        """
        task = self._run_task
        if self._run_session_slot is not None or (task is not None and not task.done()):
            return None
        return await RunSlot.acquire(self._run_semaphore)

    async def send_message(
        self,
        message: Message,
        run: bool = False,
        _from_goal_loop: bool = False,
        *,
        run_slot: RunSlot | None = None,
    ):
        if not self._conversation:
            raise ValueError("inactive_service")
        # 普通用户消息将取代此对话中任何活动的 /goal 循环。 目标循环自己的消息传递
        # _from_goal_loop=True。
        #
        if not _from_goal_loop:
            await self.stop_goal_loop()
        explicit_interrupt_generation = self._explicit_interrupt_generation
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._conversation.send_message, message)
        if run:
            if self._explicit_interrupt_generation != explicit_interrupt_generation:
                return
            (
                did_mark_acp_prompt_superseded,
                active_acp_prompt_has_latest_message,
            ) = await self._mark_running_acp_prompt_superseded()
            if did_mark_acp_prompt_superseded:
                # 在*杀死正在进行的提示词之前固定会话许可*。 下面的中断使该运行在退出时
                # 产生其许可； 如果替换运行必须获得一个新的运行，那么在我们已经销毁了对
                # 话的工作运行之后，它可能会被拒绝（429）。 该引脚使传出运行的许可在整个
                # 取代窗口中保持活动状态。
                #
                self._pin_run_session()
                self._acp_internal_rerun_requested = True
                try:
                    await self.interrupt(internal_acp_rerun=True)
                    if (
                        self._explicit_interrupt_generation
                        != explicit_interrupt_generation
                    ):
                        return
                    await self.run(
                        acp_internal_rerun_generation=explicit_interrupt_generation,
                        run_slot=run_slot,
                    )
                    self._acp_internal_rerun_requested = False
                except ValueError as e:
                    # run() 拒绝。 如果一个运行仍在打包（其wait_for_pending尾部），我们
                    # 刚刚追加的消息不会被它接受，因此需要明确记录_run_and_publish的运行
                    # 意图，以确保该任务完成。 跟踪请求，而不是在 IDLE 状态中推断，这样
                    # 可以防止 False 追加或通过其他路径到达 IDLE 时触发意外的追加。 “
                    # inactive_service”已终止，不得重新布防。
                    #
                    if (
                        str(e) == "conversation_already_running"
                        and not active_acp_prompt_has_latest_message
                    ):
                        self._rerun_requested = True
                        self._acp_internal_rerun_requested = True
                finally:
                    self._unpin_run_session()
            else:
                try:
                    await self.run(
                        acp_internal_rerun_generation=explicit_interrupt_generation,
                        run_slot=run_slot,
                    )
                    self._acp_internal_rerun_requested = False
                except ConversationRunLimitExceeded as exc:
                    # 这里没有任何中断，因此容量拒绝是一个干净的背压信号。 该消息已保存
                    # ，因此请告诉呼叫者重试 /run，无需重新发送。
                    #
                    raise ConversationRunLimitExceeded(
                        "Message saved, but the conversation run limit was "
                        "reached. Retry POST /api/conversations/"
                        f"{self.stored.id}/run without resending the message."
                    ) from exc
                except ValueError as e:
                    if (
                        str(e) == "conversation_already_running"
                        and not active_acp_prompt_has_latest_message
                    ):
                        self._rerun_requested = True

    def _mark_running_acp_prompt_superseded_sync(self) -> tuple[bool, bool]:
        """如果需要，将当前运行的 ACP 提示词标记为已取代。

        该元组是 ``(did_mark_superseded, active_prompt_has_latest_message)``. 如果正
        在运行 ACP
        提示词已经提前进入新添加的用户消息中，中断它将取消替换提示词和隐藏在的消息已
        持久化 cursor.
        """
        if not self._conversation:
            return (False, False)
        if self._run_task is None or self._run_task.done():
            return (False, False)
        if not isinstance(self._conversation.agent, ACPAgent):
            return (False, False)
        with self._conversation._state as state:
            if state.execution_status != ConversationExecutionStatus.RUNNING:
                return (False, False)
            inflight_prompt_user_message_id = state.agent_state.get(
                ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID
            )
            last_user_message_id = state.last_user_message_id
            if inflight_prompt_user_message_id is None or last_user_message_id is None:
                return (False, False)
            active_prompt_has_latest_message = (
                inflight_prompt_user_message_id == last_user_message_id
            )
            if active_prompt_has_latest_message:
                return (False, True)
            state.agent_state = {
                **state.agent_state,
                ACP_SUPERSEDE_INFLIGHT_PROMPT: True,
            }
            return (True, False)

    async def _mark_running_acp_prompt_superseded(self) -> tuple[bool, bool]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._mark_running_acp_prompt_superseded_sync
        )

    async def subscribe_to_events(self, subscriber: Subscriber[Event]) -> UUID:
        subscriber_id = self._pub_sub.subscribe(subscriber)

        # 立即将当前状态发送给新订阅者。 快照在工作线程中创建线程所以正在等待对话同步
        # FIFOLock 无法阻止服务器事件循环。
        #
        if self._conversation:
            state_update_event = await self._create_state_update_event()
        else:
            state_update_event = ConversationStateUpdateEvent(
                key="execution_status",
                value=ConversationExecutionStatus.IDLE,
            )

        try:
            await asyncio.wait_for(
                subscriber(state_update_event),
                timeout=INITIAL_STATE_PUSH_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            # 订户保持注册状态； 仅丢弃初始状态推送。 后续发布将通过 pub_sub，并且如果订
            # 阅者仍然不参与，则可能仍会被阻止。
            #
            logger.warning(
                f"Initial state push to subscriber {subscriber_id} timed "
                f"out after {INITIAL_STATE_PUSH_TIMEOUT_SECONDS}s."
            )
        # 非超时错误传播到调用者 (e.g. Webhook 失败）。

        return subscriber_id

    async def unsubscribe_from_events(self, subscriber_id: UUID) -> bool:
        return self._pub_sub.unsubscribe(subscriber_id)

    async def subscribe_to_stream_progress(
        self, subscriber: Subscriber[StreamProgress]
    ) -> UUID:
        """注册流进度帧。

        没有初始推送，与：meth:`subscribe_to_events` 不同：中流连接的客户端获取带有持
        久事件的真实文本。
        """
        return self._stream_pub_sub.subscribe(subscriber)

    async def unsubscribe_from_stream_progress(self, subscriber_id: UUID) -> bool:
        return self._stream_pub_sub.unsubscribe(subscriber_id)

    def _emit_event_from_thread(self, event: Event) -> None:
        """从非异步上下文（e.g.、回调）安全发出事件的帮助程序。

        这会在 main 事件循环中安排事件发射，从而可以安全地调用
        from callbacks that may run in different threads. Events are emitted through
        对话的正常事件流以确保它们是已持久化。

        事件被重新标记一次锁被持有：只有在持有该步骤后才被追加锁它附加了自己的事件，
        并进行搜索和 ``resend_mode=since`` 依赖日志顺序与时间顺序
        一致。
        """
        main_loop = self._main_loop
        conversation = self._conversation
        if main_loop and main_loop.is_running() and conversation:
            # 将 _on_event 与锁获取包裹起来，以确保线程安全在并发操作期间访问对话状态和
            # 事件日志
            #
            def locked_on_event():
                with conversation._state:
                    conversation._on_event(
                        event.model_copy(
                            update={"timestamp": datetime.now().isoformat()}
                        )
                    )

            # 在执行器中运行锁定的回调，以确保事件既是已持久化又发送到 WebSocket 个订阅
            # 者。 未来需要一个 done-回调。否则，未读异常会收集数据，导致丢弃的统计或
            # LLM 日志事件没有信号，除了 GC 时间警告。
            #
            future = main_loop.run_in_executor(None, locked_on_event)
            # 从环线程连接。 这个辅助函数被调用自线程的外部代码，`add_done_callback` 用
            # 于一个已经完成的未来，这将使用普通的 `call_soon`，后者既不是线程安全也不是
            # 唤醒一个空闲循环——报告可能会因此而未触发，这正是回调试图防止的失败。
            #
            main_loop.call_soon_threadsafe(
                future.add_done_callback,
                partial(_log_emit_failure, type(event).__name__),
            )

    def _setup_llm_log_streaming(self, agent: AgentBase) -> None:
        """配置 LLM 日志回调以通过事件流式传输日志。"""
        for llm in agent.get_all_llms():
            if not llm.log_completions:
                continue

            # 捕获闭包变量
            usage_id = llm.usage_id
            model_name = llm.model

            def log_callback(
                filename: str, log_data: str, uid=usage_id, model=model_name
            ) -> None:
                """回调将 LLM 完成日志作为事件发出。"""
                try:
                    event = LLMCompletionLogEvent(
                        filename=filename,
                        log_data=log_data,
                        model_name=model,
                        usage_id=uid,
                    )
                    self._emit_event_from_thread(event)
                except Exception:
                    logger.exception("Failed to emit LLM completion log event")

            llm.telemetry.set_log_completions_callback(log_callback)

    def _setup_acp_activity_heartbeat(self, agent: AgentBase) -> None:
        """将 ACP 活动心跳连接到空闲计时器。

        ACP 智能体委托给外部子进程 (e.g. 双子座-CLI、克劳德-智能体-ACP）。 工具调用在
        子进程内部运行，并且永远不会到达智能体服务器的 HTTP
        端点，因此 update_last_execution_time() 在 conn.prompt() 期间永远不会被调用。
         如果没有心跳，runtime-
        API 就会看到增长 idle_time 并杀死 pod（约 20 分钟）。

        该方法检查智能体 is an ACPAgent 并且，如果那样的话，注入一个回调它会重置空闲
        计时器 ACP 桥接接收一个流式传输每30秒更新（由桥端拦截）。
        """
        from openhands.sdk.agent import ACPAgent

        if isinstance(agent, ACPAgent):
            agent._on_activity = update_last_execution_time

    def _signal_stream_activity(self) -> None:
        """当完成流时刷新运行时空闲计时器。

        增量永远不会是已持久化，因此调用 update_last_execution_time() 的持久事件路径
        对于流的长度是沉默的。 从生产者发出信号，以便它在
        离开共享总线的增量中幸存下来； 像 ACP 桥的 _maybe_signal_activity 一样受到节
        流。
        """
        now = time.monotonic()
        if now - self._last_stream_activity_signal < ACTIVITY_SIGNAL_INTERVAL:
            return
        self._last_stream_activity_signal = now
        update_last_execution_time()

    @staticmethod
    def _state_change_callback(
        conversation: LocalConversation,
    ) -> ConversationCallbackType:
        """发布状态更改，在新的智能体上重新连接托管密钥挂钩。

        ``switch_llm`` / ``switch_profile``（REST 端点和智能体的切换工具）安装一个新
        的 LLM 对象，而不使用刷新钩子
        ``start()`` 已注册 (#5890)。
        """

        def callback(event: Event) -> None:
            if isinstance(event, ConversationStateUpdateEvent) and event.key == "agent":
                register_managed_llm_key_refresh(conversation._state.agent)
            conversation._on_event(event)

        return callback

    def _setup_stats_streaming(self, agent: AgentBase) -> None:
        """配置统计数据更新回调以通过事件流式传输统计数据更改。"""

        def stats_callback() -> None:
            """回调发出统计更新。

            ``Telemetry.on_response``（常规智能体路径）和``ACPAgent._record_usage``（
            ACP路径）被同步调用，
            这两个路径都在``LocalConversation.run()``的``with self._state:``块中运行
            ，因此调用者已经拥有会话状态
            锁。

            DO 不重新获取状态锁这里 (``with state:``). 看起来是安全的 ``FIFOLock`` 它
            自我声明为可重入 — 但 on the
             ACP 代码路径它死锁 （沉默地）在  REST of ``step()`` 可以发出助手的
             FinishAction +
            ObservationEvent, 留下每个对话悬而未决
            ``running`` 状态永远。 下面的``_emit_event_from_thread``在持久化事件之前
            已经获取了执行器线程上的锁； 无论如
            何，这是唯一序列化需要锁的地方。
            """
            # 仅发布统计字段以避免发送整个状态
            if not self._conversation:
                return
            event = ConversationStateUpdateEvent(
                key="stats", value=self._conversation._state.stats
            )
            self._emit_event_from_thread(event)

        for llm in agent.get_all_llms():
            llm.telemetry.set_stats_update_callback(stats_callback)

    @staticmethod
    def _ensure_workspace_is_git_repo(working_dir: Path) -> None:
        """如果工作区还不是 git 存储库，请将其初始化。

        /api/git/changes 端点期望一个真实的存储库来计算更改； 如果没有这个，智能体创
        建的文件永远不会出现在“更改”选项卡中。 我们只运行
        `git init`（无提交）——空存储库由 `get_valid_ref()` 通过 GIT_EMPTY_TREE_HASH
        处理，未跟踪的文件通过
        `git ls-files --others` 出现。
        """
        try:
            validate_git_repository(working_dir)
            return  # 已经是一个回购协议
        except GitRepositoryError:
            logger.debug(
                "Workspace %s is not a git repository; running `git init`",
                working_dir,
            )

        try:
            run_git_command(["git", "init"], working_dir)
        except GitCommandError as e:
            # 如果 git 丢失或 init 失败，不要阻止对话启动 - git 路由器是防御性的，无论如
            # 何都会返回 []。
            #
            logger.warning(
                "Failed to initialize git repository at %s: %s", working_dir, e
            )

    async def start(self):
        # 存储主事件循环用于跨线程通信
        self._main_loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

        # self.stored 包含我们可以实例化的智能体配置
        self.conversation_dir.mkdir(parents=True, exist_ok=True)
        # lease_ttl_seconds=0 disables leasing for single-instance deployments
        # 否则共享存储过时的租约会阻止 Pod 重新启动。
        if self.lease_ttl_seconds > 0:
            self._lease = ConversationLease(
                conversation_dir=self.conversation_dir,
                owner_instance_id=self.owner_instance_id,
                ttl_seconds=self.lease_ttl_seconds,
            )
            lease_claim = self._lease.claim()
            self._lease_generation = lease_claim.generation
        await self._scrub_persisted_credentials()
        workspace = self.stored.workspace
        assert isinstance(workspace, LocalWorkspace)
        working_dir = Path(workspace.working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_workspace_is_git_repo(working_dir)
        # base_state.json 是智能体的唯一事实来源。 恢复时（base_state 存在）传递
        # ``agent=None``，因此 LocalConversation 保留已持久化智能体。 在新对话中，创建呼
        # 叫者通过 ``self.agent`` 提供智能体； 深度复制它（expose_secrets），因此运行的
        # 智能体独立于调用者的对象。
        #
        base_state_exists = await asyncio.to_thread(
            (self.conversation_dir / BASE_STATE).exists
        )
        if base_state_exists:
            agent: AgentBase | None = None
        else:
            if self.agent is None:
                raise ValueError(
                    "Cannot start a new conversation without an agent: no "
                    "base_state.json to resume and no agent was provided."
                )
            agent_cls = type(self.agent)
            agent = agent_cls.model_validate(
                self.agent.model_dump(context={"expose_secrets": True}),
            )

        # 使用插件创建 LocalConversation 和 hook_config。 插件在第一次 run()
        # /send_message() 调用时延迟加载。 钩子执行语义：OpenHands 按顺序运行钩子并提前
        # 退出块 (PreToolUse)，这与 Claude Code 的并行执行模型不同。
        #

        # 创建并存储回调包装器以允许刷新待处理事件
        self._callback_wrapper = AsyncCallbackWrapper(
            self._pub_sub, loop=asyncio.get_running_loop()
        )

        # token 流式传输仅连接到实际上可以发出 token 回调的智能体（SDK LLM 智能体，流 =
        # True 或 ACP 智能体）。 对于 NEW 对话，智能体在这里是已知的，所以现在决定。 在
        # RESUME 中，智能体是在构造期间从 base_state.json 加载的，因此将决定推迟到之后（
        # 请参阅下面的构造后块）。
        #
        def _agent_can_stream(a: AgentBase) -> bool:
            return isinstance(a, ACPAgent) or any(
                llm.stream for llm in a.get_all_llms()
            )

        streaming_enabled = _agent_can_stream(agent) if agent is not None else True
        streaming_decided = agent is not None

        def _publish_stream_delta(
            content: str | None = None,
            reasoning_content: str | None = None,
        ) -> None:
            # 直接发布到 _pub_sub（不通过 _callback_wrapper），因此增量到达订阅者，但范
            # 围是不已持久化到 ConversationState.events。 参见StreamingDeltaEvent文档字
            # 符串。
            #
            if not self._main_loop or not self._main_loop.is_running():
                return
            # 使用 `is not None` 而不是真实性：一些提供者在流边界处发出合法的空字符串块
            # （e.g. 在工具调用）之后我们仍然想转发。
            #
            if content is None and reasoning_content is None:
                return
            event = StreamingDeltaEvent(
                content=content,
                reasoning_content=reasoning_content,
            )
            self._signal_stream_activity()
            with suppress(RuntimeError):  # 主循环在拆卸期间已关闭
                asyncio.run_coroutine_threadsafe(self._pub_sub(event), self._main_loop)

        def _publish_stream_progress(frame: StreamProgress) -> None:
            # 与 _publish_stream_delta 相同的跨线程跃点：从运行线程或 ACP 门户线程调用。
            #
            if not self._main_loop or not self._main_loop.is_running():
                return
            with suppress(RuntimeError):  # 主循环在拆卸期间已关闭
                asyncio.run_coroutine_threadsafe(
                    self._stream_pub_sub(frame), self._main_loop
                )

        def _token_streaming_callback(chunk: LLMStreamChunk | str) -> None:
            if isinstance(chunk, str):
                _publish_stream_delta(content=chunk)
                return

            for choice in chunk.choices or ():
                delta = choice.delta
                if delta is None:
                    continue
                content = getattr(delta, "content", None)
                reasoning = getattr(delta, "reasoning_content", None)
                _publish_stream_delta(
                    content=content if isinstance(content, str) else None,
                    reasoning_content=reasoning if isinstance(reasoning, str) else None,
                )

        conversation = LocalConversation(
            agent=agent,
            workspace=workspace,
            plugins=self.stored.plugins,
            persistence_dir=str(self.conversations_dir),
            conversation_id=self.stored.id,
            callbacks=[self._callback_wrapper],
            token_callbacks=([_token_streaming_callback] if streaming_enabled else []),
            stream_callbacks=[_publish_stream_progress],
            max_iteration_per_run=self.stored.max_iterations,
            stuck_detection=self.stored.stuck_detection,
            visualizer=None,
            secrets=self.stored.secrets,
            cipher=self.cipher,
            hook_config=self.stored.hook_config,
            tags=self.stored.tags,
            user_id=self.stored.user_id,
            observability_metadata=self.stored.observability_metadata,
            observability_tags=self.stored.observability_tags,
            observability_span_name=self.stored.observability_span_name,
            observability_parent_span_context=self.stored.observability_parent_span_context,
            mcp_tool_provider=self.mcp_tool_provider,
        )

        conversation.set_confirmation_policy(self.stored.confirmation_policy)
        conversation.set_security_analyzer(self.stored.security_analyzer)
        # 在恢复时，智能体在构建时未知（从 base_state.json 加载），因此现在决定 token 流
        # 式传输，当智能体可以发出 token 回调时禁用它。
        #
        if not streaming_decided:
            streaming_enabled = _agent_can_stream(conversation.agent)
            logger.debug(
                "Token streaming: %s",
                "enabled" if streaming_enabled else "disabled (no LLM has stream=True)",
            )
            if not streaming_enabled:
                conversation.set_token_callbacks(None)
        self._conversation = conversation
        if isinstance(conversation.agent, ACPAgent):
            for secret_name, binding in self.credential_bindings.items():
                conversation.agent.activate_file_credential_binding(
                    secret_name,
                    binding,
                )
        self._conversation._state.set_write_guard(self._write_guard)

        # 除非部署选择加入（OH_LLM_API_KEY_REFRESH_URL 加
        # OH_LLM_API_KEY_REFRESH_BASE_URLS），否则处于惰性状态； 参见#5189。
        #
        register_managed_llm_key_refresh(self._conversation.agent)

        if not self._external_lease_renewal:
            self._lease_task = asyncio.create_task(self._renew_lease_loop())

        # 注册状态更改回调以自动发布更新
        self._conversation._state.set_on_state_change(
            self._state_change_callback(self._conversation)
        )

        # 设置LLM日志流式传输用于远程执行
        self._setup_llm_log_streaming(self._conversation.agent)

        # 设置远程执行的统计信息流式传输
        self._setup_stats_streaming(self._conversation.agent)

        # ACP ACP 活动心跳工具调用 (运行在子进程上，永远不会到达 HTTP 端点) 仍然重置智能
        # 体-服务器的空闲计时器，并防止长时间 conn.prompt() 调用期间 API 运行时终止 Pod
        # 。
        #
        self._setup_acp_activity_heartbeat(self._conversation.agent)

        # 从磁盘加载的状态为 RUNNING 的任何对话都是过时的。 通过租约声明本身，活跃的分裂
        # 大脑重启被阻止得更早，因此，如果已经走这么远，就没有活的主人，中断的工具调用应
        # 该被回传给智能体。
        #
        state = self._conversation.state
        if state.execution_status == ConversationExecutionStatus.RUNNING:
            state.execution_status = ConversationExecutionStatus.ERROR
            # 崩溃恢复扫描整个日志，而不是活动分支：进程可能在写入事件文件和持久化高级
            # HEAD之间死亡，因此叶子节点可能落后于磁盘事件。（远程分支不支持——#3749——所
            # 以这里根本就没有废弃的分支可以排除。）
            #
            unmatched_actions = ConversationState.get_unmatched_actions(state.events)
            if unmatched_actions:
                first_action = unmatched_actions[0]
                # 如果此 tool_call_id 已存在任何类似观测结果的事件，则跳过，以避免当观测
                # 结果与 tool_call_id 匹配但不与 action_id 匹配时重复观测结果。
                #
                already_observed = any(
                    isinstance(e, ObservationBaseEvent)
                    and e.tool_call_id == first_action.tool_call_id
                    for e in state.events
                )
                if not already_observed:
                    # 当写入事件文件之后但在自动保存之前 leaf_event_id 进程终止时，已持
                    # 久化 HEAD 可以滞后此操作。 明确地将恢复结果作为操作的父级； 否则，
                    # 正常的树戳操作将它附着到HEAD上，使操作和结果成为兄弟，并在活跃分支
                    # 上留下一个孤儿工具结果。
                    #
                    error_event = AgentErrorEvent(
                        parent_id=first_action.id,
                        tool_name=first_action.tool_name,
                        tool_call_id=first_action.tool_call_id,
                        error=(
                            "A restart occurred while this tool was in progress. "
                            "This may indicate a fatal memory error or system crash. "
                            "The tool execution was interrupted and did not complete."
                        ),
                        classification=ErrorClassification(
                            kind=FailureKind.INTERNAL, retryable=False
                        ),
                    )
                    self._conversation._on_event(error_event)

        # 同样，没有一个目标循环在重启后存活：在循环中中途关闭或崩溃时遗留了一个仍然活跃
        # 的目标状态(close()故意跳过这个状态)。 将其记录为已中断，以便读取为已停止并保持
        # 可恢复状态。
        #
        await asyncio.get_running_loop().run_in_executor(
            None, self._reconcile_stale_goal_status
        )

        # 发布初始状态更新
        await self._publish_state_update()

    def _pin_run_session(self) -> None:
        """在无运行的延续中保持会话许可处于活动状态。

        /goal 循环和 ACP 取代窗口都有没有运行任务处于活动状态但有明确再次运行意图的时
        刻。 Pinning填补了这些空白，使得他们所获得的许可不会被一个竞
        争请求重新申请，从而将续签本身的``run()``变成一个虚假的429。
        """
        self._run_session_pins += 1

    def _unpin_run_session(self) -> None:
        if self._run_session_pins > 0:
            self._run_session_pins -= 1
        self._maybe_end_run_session()

    def _maybe_end_run_session(self) -> None:
        """一旦没有链运行或 pin 仍然需要会话许可，则返回会话许可。"""
        owner = self._run_session_slot
        if owner is None:
            return
        if self._run_session_pins > 0:
            return
        task = self._run_task
        if task is not None and not task.done():
            # 从它自己的 ``finally`` 调用它的运行主体不是后继者。 将其视为一个将发布推迟
            # 到任务完成后回调、i.e。 直到``wait_for_pending``和最终状态发布之后。 一个
            # 已经终结的对话（其状态可以通过REST读取），因此仍然占用了一个运行槽，并且有
            # 一个竞争请求被拒绝了，因为这是虚假的ConversationRunLimitExceeded。
            #
            try:
                current = asyncio.current_task()
            except RuntimeError:  # 没有运行循环（同步调用者）
                current = None
            if task is not current:
                return
            # 在本运行结束时暂停输入重新武装时，必须保持许可：调用者已经被告知其消息已被
            # 接受，因此在这里拒绝它将使它滞留。
            #
            if self._rerun_requested or self._acp_internal_rerun_requested:
                return
        self._run_session_slot = None
        owner.release()

    async def run(
        self,
        acp_internal_rerun_generation: int | None = None,
        *,
        run_slot: RunSlot | None = None,
        wait_for_capacity: bool = False,
    ):
        """在后台异步运行对话。

        此方法启动后台任务中的对话，并立即返回。 如果可能的话，对话是通过其本机驱动的
        ``arun()`` 协程因此 LLM I/O 不会占用线程池工作线程。 对于不公开 ``arun()``（
        e.g.，自定义子类）或其智能体仅实现同步
        ``step()``（无
        ``astep()`` override），同步 ``run()`` 和以前一样在线程池中执行。

        Raises:
            ValueError: 如果服务处于非活动状态或对话已在运行。
            ConversationRunLimitExceeded: 如果所有服务器运行槽都被占用。
        """
        if not self._conversation or self._closing:
            raise ValueError("inactive_service")

        # 使用锁使检查和设置原子化，防止竞态条件
        async with self._run_lock:
            # 在任何拒绝之前，一个过期的内部 ACP 重试就被丢弃了：一个明确的停止在我们等
            # 待 _run_lock 时发生，必须获胜，而拒绝会让调用者重新启动重试。
            #
            if (
                acp_internal_rerun_generation is not None
                and self._explicit_interrupt_generation != acp_internal_rerun_generation
            ):
                return
            # _run_task 第一：一个实时运行会持有状态锁在其步骤之间（一个工具调用可以持续
            # 几分钟），因此读取执行状态会将其请求置于其后，而不是立即回答。
            #
            if (self._run_task is not None and not self._run_task.done()) or (
                await self._get_execution_status()
                == ConversationExecutionStatus.RUNNING
            ):
                raise ValueError("conversation_already_running")
            if self._closing:
                raise ValueError("inactive_service")
            # 重新检查：上面读取的状态也可能导致延迟停止。
            if (
                acp_internal_rerun_generation is not None
                and self._explicit_interrupt_generation != acp_internal_rerun_generation
            ):
                return

            # 捕获关闭的对话参考
            conversation = self._conversation

            # 开始在后台运行
            loop = asyncio.get_running_loop()

            # 一次运行可能属于一个链（重新准备搁浅的输入，ACP取代重新启动，一轮/goal循环
            # ）。 链式运行会重用此会话许可，而不是获取新的许可，因此在前一个会话许可被
            # 释放，后一个竞争者声称该许可的间隙中，它们不能被拒绝。 只有链的第一轮才能
            # 获得容量； 一旦整个链（加上任何引脚，e.g）返回许可证。 一个实时 /goal 循环
            # ）已完成。
            #
            owner = self._run_session_slot
            if owner is None:
                owner = (
                    run_slot.share()
                    if run_slot is not None
                    else await RunSlot.acquire(
                        self._run_semaphore, wait=wait_for_capacity
                    )
                )
                self._run_session_slot = owner
            elif run_slot is not None:
                # 在已经举行的会议之上提供的预订是多余的； 返回它，以免泄露。
                #
                run_slot.release()
            slot = owner.share()

            worker: asyncio.Future | None = None

            def settle(done: asyncio.Future | None = None) -> None:
                # asyncio 等待者的取消不会停止同步线程。
                if done is worker and worker is not None and not worker.cancelled():
                    # 即使等待者被取消，也会检索错误。
                    worker.exception()
                if worker is not None and not worker.done():
                    # 一个同步工人仍在执行； 一旦线程实际退出，它自己的完成回调就会释放
                    # 此句柄。
                    #
                    return
                slot.release()
                self._maybe_end_run_session()

            run_generation = self._explicit_interrupt_generation

            async def _run_and_publish():
                nonlocal worker
                try:
                    # 首选本机异步路径（如果可用），以便事件循环在 LLM I/O 期间空闲。 回
                    # 退到向后兼容性的线程池执行。
                    #
                    # 所有警卫都需要：
                    #  • iscoroutinefunction – 过滤掉非异步对象
                    #    (e.g. MagicMock 测试中）。
                    #  • 对话覆盖 – BaseConversation 默认值
                    #    ``arun()`` 委托给同步 ``run()``，所以我们需要一个
                    #    *实际*重写以避免运行仅同步的子类
                    #    在事件循环上。
                    #  • 智能体覆盖 – ``LocalConversation`` 始终覆盖
                    # ``arun()``，但没有 ``astep()`` 覆盖的智能体在工作器线程中运行同步
                    # ``step()``； 相反，将其路由到同步 ``run()``。
                    #
                    arun = getattr(conversation, "arun", None)
                    has_native_arun = (
                        arun is not None
                        and asyncio.iscoroutinefunction(arun)
                        and type(conversation).arun is not BaseConversation.arun
                        and type(conversation.agent).astep is not AgentBase.astep
                    )
                    if self._explicit_interrupt_generation != run_generation:
                        return
                    if has_native_arun:
                        await conversation.arun()
                    else:
                        worker = loop.run_in_executor(
                            self._run_executor, conversation.run
                        )
                        worker.add_done_callback(settle)
                        await asyncio.shield(worker)
                except Exception as exc:
                    # 将堆栈跟踪记录为纯文本，而不是通过 exc_info：默认的 Rich 控制台处
                    # 理器在该循环中渲染链式 LLM 错误需要几秒钟，从而阻塞每个请求、套接
                    # 字和运行时 (#5633)。
                    #
                    logger.error(
                        "Error during conversation run\n%s",
                        "".join(traceback.format_exception(exc)).rstrip(),
                    )
                    # Backstop：在达到自身错误之前引发的运行
                    # 处理 (e.g. init_state 中的 ACP 冷启动失败（在 run()/arun()'s try
                    # 块之外运行）可能会使状态保持在 IDLE/RUNNING。 强制ERROR，以便
                    # finally的_publish_state_update()显示失败而不是误导性的非错误状态。
                    #
                    # 还将详细信息呈现给 UI（问题＃16686）。 ConversationRunError 表示
                    # run()/arun() 已经发出了自己的事件，因此请跳过它以避免重复错误。
                    #
                    if not isinstance(exc, ConversationRunError):
                        await loop.run_in_executor(
                            None, self._publish_error_event_sync, exc
                        )
                    await loop.run_in_executor(None, self._mark_error_status_sync)
                finally:
                    settle()
                    # 在发布最终状态更新之前，等待所有待处理事件通过
                    # AsyncCallbackWrapper 发布。 这可以防止竞态条件在智能体事件（
                    # MessageEvent、ActionEvent 等）发布给 WebSocket 订阅者之前对话状态
                    # 变为 FINISHED。
                    #
                    if self._callback_wrapper:
                        await loop.run_in_executor(
                            None, self._callback_wrapper.wait_for_pending, 30.0
                        )

                    # 清除任务引用并发布状态更新
                    self._run_task = None
                    await self._publish_state_update()

                    # 在此任务结束时重新准备运行以应对搁置的输入。 在上面的
                    # wait_for_pending() 尾部期间到达的 send_message(run=True) 其 run()
                    # 被拒绝为“conversation_already_running”并被抑制，设置为
                    # _rerun_requested。 在IDLE（等待输入）或ACP-中断PAUSED（旧任务在替
                    # 换运行开始之前就完成了）时，尊重它。 显式用户暂停/中断会清除内部
                    # ACP 标志，因此用户停止意图胜过旧的自动重新启动请求。 如果运行循环
                    # 仍然存在，它已经吸收了消息，我们在这里FINISHED，所以守卫避免了冗余
                    # 运行。 一个故意的
                    #
                    # run=False append, or an IDLE reached via another path,
                    # 从不设置标志。
                    rerun_requested = self._rerun_requested
                    acp_internal_rerun_requested = self._acp_internal_rerun_requested
                    rerun_generation = self._explicit_interrupt_generation
                    self._rerun_requested = False
                    self._acp_internal_rerun_requested = False
                    if rerun_requested:
                        status = await self._get_execution_status()
                        rerun_generation_still_valid = (
                            self._explicit_interrupt_generation == rerun_generation
                        )
                        acp_internal_rerun_still_valid = (
                            acp_internal_rerun_requested
                            and rerun_generation_still_valid
                        )
                        should_restart = rerun_generation_still_valid and (
                            status == ConversationExecutionStatus.IDLE
                            or (
                                acp_internal_rerun_still_valid
                                and status == ConversationExecutionStatus.PAUSED
                                and isinstance(conversation.agent, ACPAgent)
                            )
                        )
                        if should_restart:
                            # 这重新武装使用了这里已经结束的会话许可，因此即使有其他竞争
                            # 请求声称了其他地方刚释放的许可，也不会拒绝容量。 这就是使
                            # 盲目停放请求安全的原因：停放的输入始终被此调用拾取。
                            #
                            try:
                                await self.run(
                                    acp_internal_rerun_generation=rerun_generation
                                    if acp_internal_rerun_still_valid
                                    else None,
                                    # 此重新装备接收到的消息已被接受 (200)，因此等待
                                    # token 会击败会搁浅它的 429。
                                    #
                                    wait_for_capacity=True,
                                )
                            except ValueError as e:
                                if str(e) == "conversation_already_running":
                                    self._rerun_requested = True
                                    self._acp_internal_rerun_requested = (
                                        acp_internal_rerun_requested
                                    )
                                else:
                                    raise

            # 创建任务但不等待它 - 在后台运行
            self._run_task = asyncio.create_task(_run_and_publish())
            # 最后，即使任务在其协程进入自己的 try/finally 之前被取消，也要释放。
            #
            self._run_task.add_done_callback(settle)

    async def wait_for_run_completion(
        self, timeout: float | None = None
    ) -> ConversationExecutionStatus:
        """等待活动的运行任务而不在超时上取消它。"""
        run_task = self._run_task
        if run_task is not None:
            done, _ = await asyncio.wait({run_task}, timeout=timeout)
            if not done:
                raise TimeoutError("Conversation run timed out")
        return await self._get_execution_status()

    async def start_goal_loop(
        self,
        objective: str,
        *,
        judge_llm: LLM | None = None,
        max_iterations: int = 10,
    ) -> None:
        """在此对话中启动 ``/goal`` 循环。

        发送目标，运行智能体，并在每次运行后判断完成情况，重新提示，直到目标完成或达
        到``max_iterations``。 所有工作都保留在该对话的事件历史记录和
        流中，就像正常运行一样； 这不会创建另一个对话。

        Args:
            objective: 追求和审计的目标。
            judge_llm: LLM 表示完成等级。 默认为智能体的 LLM。
            max_iterations: 放弃之前对审计轮次进行硬性限制。

        Raises:
            ValueError: 如果服务处于非活动状态，则目标循环已经存在
                运行时，没有可用的判断LLM，或者目标为空。
        """
        if not self._conversation or self._closing:
            raise ValueError("inactive_service")
        if judge_llm is None:
            judge_llm = getattr(self._conversation.agent, "llm", None)
        if judge_llm is None:
            raise ValueError("no_judge_llm")
        # GoalController 验证目标/max_iterations（提出 ValueError）。
        controller = GoalController(objective, judge_llm, max_iterations=max_iterations)
        # 在 _run_lock 下，自动拒绝并发目标循环或活动对话运行； 否则/goal可以判断一个不
        # 相关的转录本。
        #
        async with self._run_lock:
            if self._closing:
                raise ValueError("inactive_service")
            if self._goal_loop_task is not None and not self._goal_loop_task.done():
                raise ValueError("goal_already_running")
            # _run_task 首先：实时运行在其步骤中保持状态锁，因此读取执行状态将在其后面阻
            # 塞。
            #
            if (self._run_task is not None and not self._run_task.done()) or (
                await self._get_execution_status()
                == ConversationExecutionStatus.RUNNING
            ):
                raise ValueError("conversation_already_running")
            # close() 重新检查后：_run_lock 运行了，因此可能在 run() 的状态 _关闭检查后
            # 开始 teardown -- 避免启动任务 close() 也不会取消。
            #
            if self._closing:
                raise ValueError("inactive_service")
            self._goal_loop_outcome = None
            await self._schedule_goal_loop(controller)

    async def _schedule_goal_loop(
        self, controller: GoalController, *, resume: bool = False
    ) -> None:
        # 在循环启动之前预留容量，这样服务器在一开始就拒绝 /goal 请求（匹配 /run)，而不
        # 是接受请求并在循环中途失败）。
        #
        slot = await RunSlot.acquire(self._run_semaphore)
        if self._run_session_slot is None:
            self._run_session_slot = slot
        else:
            slot.release()
        # 在循环的整个生命周期中保留会话许可。 run() 每一轮都会重复使用它（没有新的获取
        # ），因此对手在比赛间歇期间无法在轮次之间窃取许可，从而将下一轮变成一个虚假的
        # 429。
        #
        self._pin_run_session()
        self._goal_loop_task = asyncio.create_task(
            self._run_goal_loop(controller, resume=resume)
        )

    async def _run_goal_loop(
        self,
        controller: GoalController,
        *,
        resume: bool = False,
    ) -> None:
        """在该对话中驱动一个活动的 ``/goal`` 循环。

        重用 SDK 的传输层不可知的 ``GoalController`` 进行决策； 该方法仅拥有 I/O：发
        送消息、等待每一步、根据事件循环判断，并发布目标状
        态更新。
        """
        conversation = self._conversation
        if conversation is None:
            return
        loop = asyncio.get_running_loop()

        def _snapshot_and_judge() -> GoalStep:
            # 会话锁下的快照事件，然后判断（LLM 调用）并释放锁 —— 两者都在此工作人员线程
            # 上。
            #
            with conversation._state:
                events = list(conversation._state.events)
            return controller.on_run_finished(events)

        def _user(text: str) -> Message:
            return Message(role="user", content=[TextContent(text=text)])

        async def _emit_status(
            *,
            active: bool,
            status: GoalStatusName,
            verdict: GoalVerdict | None = None,
        ) -> None:
            # 持久化 + 发布目标状态更新，以便 UI 可以渲染芯片。
            # ConversationStateUpdateEvent 不可转换为 LLM，因此它永远不会进入智能体或法
            # 官的上下文。
            #
            event = ConversationStateUpdateEvent(
                key="goal",
                value=GoalStatus(
                    active=active,
                    status=status,
                    iteration=controller.iteration,
                    max_iterations=controller.max_iterations,
                    objective=controller.objective,
                    verdict=verdict,
                ).model_dump(),
            )

            def _persist() -> None:
                with conversation._state:
                    conversation._on_event(event)

            await loop.run_in_executor(None, _persist)

        try:
            await _emit_status(active=True, status="running")
            nudge = RESUME_PROMPT if resume else controller.start()
            await self.send_message(_user(nudge), run=False, _from_goal_loop=True)
            while True:
                try:
                    await self.run()
                except ValueError as e:
                    if str(e) != "conversation_already_running":
                        raise
                run_task = self._run_task
                if run_task is not None:
                    await asyncio.wait({run_task})
                status = await self._get_execution_status()
                if status in (
                    ConversationExecutionStatus.PAUSED,
                    ConversationExecutionStatus.ERROR,
                ):
                    logger.info("Goal loop halted early: status=%s", status)
                    await _emit_status(active=False, status="interrupted")
                    return
                if status == ConversationExecutionStatus.STUCK:
                    # 卡住检测器是一种启发式方法，经常在合法迭代期间触发（重新运行测试、
                    # 重试编辑）。 目标循环已经有一个权威的裁判在每一轮都审计完成，所以
                    # STUCK次运行不是停止整个目标的理由——继续向裁判提交
                    #
                    # let it decide continue-vs-stop (sending a followup nudge
                    # 这使智能体脱离了任何真正的循环）。 只有PAUSED/ERROR（真正的停止信
                    # 号）终止目标。
                    #
                    logger.info("Goal loop continuing past stuck run")
                step = await loop.run_in_executor(None, _snapshot_and_judge)
                if isinstance(step, GoalDone):
                    self._goal_loop_outcome = step.outcome
                    await _emit_status(
                        active=False,
                        status=step.outcome.status,
                        verdict=step.outcome.verdict,
                    )
                    logger.info(
                        "Goal %s after %d round(s)",
                        step.outcome.status,
                        step.outcome.iterations,
                    )
                    return
                # 承载本轮的裁决，以便 UI 可以显示每轮裁判的反馈（得分 + 缺失的内容），
                # 而不仅仅是最终的反馈。
                #
                await _emit_status(active=True, status="running", verdict=step.verdict)
                await self.send_message(
                    _user(step.followup), run=False, _from_goal_loop=True
                )
        except asyncio.CancelledError:
            logger.info("Goal loop cancelled")
            # 显式停止或用户插入：记录可恢复的中断状态，服务拆卸期间除外。
            #
            if not self._closing:
                with suppress(Exception):
                    await _emit_status(active=False, status="interrupted")
            raise
        except Exception:
            logger.exception("Goal loop failed")
            # 意外失败（法官 LLM 错误、控制器 bug 等）导致循环死锁：记录一个中断状态（可
            # 恢复的），以免 UI 显示运行中。 在close()期间跳过，就像取消路径一样。
            #
            if not self._closing:
                with suppress(Exception):
                    await _emit_status(active=False, status="interrupted")
        finally:
            self._goal_loop_task = None
            # 释放循环整个生命周期内持有的许可证。 在_schedule_goal_loop中进行的保留（或
            # 继承的许可证
            #
            # from a round's run) is returned here.
            self._unpin_run_session()

    async def stop_goal_loop(self) -> bool:
        """取消此对话中的活动 ``/goal`` 循环。

        如果循环处于活动状态，则返回 True。 与 ``interrupt()`` 不同，它的目标是后台目
        标循环本身并记录 ``interrupted`` 状态，
        因此
        :meth:`resume_goal_loop` 稍后可以继续。
        """
        task = self._goal_loop_task
        if task is None or task.done():
            return False
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        return True

    def _last_goal_loop_status(self) -> dict | None:
        """返回最近的目标状态载荷，如果有 None，则返回 None。"""
        conversation = self._conversation
        if conversation is None:
            return None
        with conversation._state:
            events = conversation._state.events
            # 懒惰地向后走：最新的目标状态通常接近尾声，因此这可以避免从磁盘读取整个日志
            # 。
            #
            for i in range(len(events) - 1, -1, -1):
                event = events[i]
                if (
                    isinstance(event, ConversationStateUpdateEvent)
                    and event.key == "goal"
                ):
                    return event.value if isinstance(event.value, dict) else None
        return None

    def _reconcile_stale_goal_status(self) -> None:
        """将目标状态已持久化标记为活动，但没有循环，已中断。"""
        conversation = self._conversation
        try:
            last = self._last_goal_loop_status()
            if conversation is None or last is None or not last.get("active"):
                return
            stale = GoalStatus.model_validate(last)
        except Exception:
            # 尽最大努力：不可读的日志不能保留对话
            # from loading.
            logger.warning("Could not check the last goal status", exc_info=True)
            return
        event = ConversationStateUpdateEvent(
            key="goal",
            value=stale.model_copy(
                update={"active": False, "status": "interrupted", "verdict": None}
            ).model_dump(),
        )
        with conversation._state:
            conversation._on_event(event)

    async def resume_goal_loop(
        self, *, judge_llm: LLM | None = None, max_iterations: int | None = None
    ) -> None:
        """恢复此对话中最后一个中断的 ``/goal`` 循环。

        从最后一个已持久化目标状态事件重建循环，并从已达到的迭代继续。 这在会话内和服
        务器重新启动时有效，因为目标状态事件是已持久化。

        Raises:
            ValueError: 如果服务处于非活动状态，则目标循环已经存在
                正在运行，没有可用的判断 LLM，或者没有可恢复的目标循环，因为 None 已
                启动或已完成/上限。
        """
        if not self._conversation or self._closing:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        last = await loop.run_in_executor(None, self._last_goal_loop_status)
        if last is None or last.get("status") in ("complete", "capped"):
            raise ValueError("no_resumable_goal")
        if judge_llm is None:
            judge_llm = getattr(self._conversation.agent, "llm", None)
        if judge_llm is None:
            raise ValueError("no_judge_llm")
        controller = GoalController(
            last["objective"],
            judge_llm,
            max_iterations=max_iterations or int(last["max_iterations"]),
        )
        # 每份简历至少运行一轮审计，所以保留一轮：一个状态已持久化，计数已经达到上限（由
        # 较旧的服务器或较低的max_iterations超时）不能让已恢复的循环报告超过
        # max_iterations轮。
        #
        controller.iteration = min(
            int(last["iteration"]), controller.max_iterations - 1
        )
        # 与start_goal_loop相同的忙碌守卫：拒绝进球循环或主动跑动。
        async with self._run_lock:
            if self._closing:
                raise ValueError("inactive_service")
            if self._goal_loop_task is not None and not self._goal_loop_task.done():
                raise ValueError("goal_already_running")
            if (self._run_task is not None and not self._run_task.done()) or (
                await self._get_execution_status()
                == ConversationExecutionStatus.RUNNING
            ):
                raise ValueError("conversation_already_running")
            if self._closing:  # 请参阅start_goal_loop：close()可能已开始拆解
                raise ValueError("inactive_service")
            self._goal_loop_outcome = None
            await self._schedule_goal_loop(controller, resume=True)

    async def respond_to_confirmation(self, request: ConfirmationResponseRequest):
        if request.accept:
            try:
                await self.run()
            except ValueError as e:
                # 将“已经运行”视为无操作成功
                if str(e) == "conversation_already_running":
                    logger.debug(
                        "Confirmation accepted but conversation already running"
                    )
                else:
                    raise
        else:
            await self.reject_pending_actions(request.reason)

    async def reject_pending_actions(self, reason: str):
        """拒绝所有待处理的操作并发布更新的状态。"""
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._conversation.reject_pending_actions, reason
        )

    async def pause(self):
        if self._conversation:
            self._explicit_interrupt_generation += 1
            self._rerun_requested = False
            self._acp_internal_rerun_requested = False
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._conversation.pause)
            # 暂停后发布状态更新以确保更新统计数据
            await self._publish_state_update()

    async def interrupt(self, *, internal_acp_rerun: bool = False):
        """立即取消飞行中的异步 LLM 呼叫。

        委托给：meth:`LocalConversation.interrupt` 取消
        ``arun()`` 任务。 如果没有异步运行正在进行，则调用将回退到：meth:`pause`。
        """
        if self._conversation:
            if not internal_acp_rerun:
                self._explicit_interrupt_generation += 1
                self._rerun_requested = False
                self._acp_internal_rerun_requested = False
            self._conversation.interrupt()
            # 等待运行任务完成，以便我们可以干净地发布最终状态更新 (PAUSED +
            # InterruptEvent)。 该防护罩可防止 5s 超时强制取消仍需要耗尽其 ACP 提示/取消
            # 握手的清理。
            #
            if self._run_task is not None and not self._run_task.done():
                with suppress(Exception):
                    await asyncio.wait_for(asyncio.shield(self._run_task), timeout=5.0)
                # 仅当实际完成时才清除_run_task； 如果 wait_for 超时，任务可能仍在运行，
                # 并且提前清除将允许在第一个任务仍在进行时启动第二个 run()。
                #
                if self._run_task is not None and self._run_task.done():
                    self._run_task = None
            await self._publish_state_update()

    async def update_secrets(self, secrets: dict[str, SecretValue]):
        """更新对话中的机密。"""
        if not self._conversation:
            raise ValueError("inactive_service")
        profile = self.stored.launched_agent_profile
        if profile is not None:
            secrets = {
                name: value
                for name, value in secrets.items()
                if profile.allows_secret(name)
            }
        if CODEX_AUTH_SECRET_NAME in self.credential_bindings:
            secrets = dict(secrets)
            secrets.pop(CODEX_AUTH_SECRET_NAME, None)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._conversation.update_secrets, secrets)

    async def set_confirmation_policy(self, policy: ConfirmationPolicyBase):
        """设置对话的确认策略。"""
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._conversation.set_confirmation_policy, policy
        )

    async def set_security_analyzer(
        self, security_analyzer: SecurityAnalyzerBase | None
    ):
        """设置对话的安全分析器。"""
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, self._conversation.set_security_analyzer, security_analyzer
        )

    async def load_plugin(self, plugin_ref: str) -> None:
        """将市场插件加载到活动对话中。"""
        if self._conversation is None:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._conversation.load_plugin, plugin_ref)

    async def switch_acp_model(self, model: str) -> None:
        """在 ACP 对话中切换模型。

        对于已经开始的对话，在工作线程线程中运行（阻塞）协议级 ``session/set_model``
        往返； 对于尚未运行的一个，SDK 推迟切换（仅限持久化
        ）。 无论哪种方式，切换模型都是已持久化作为权威值
        ``base_state.json``：``LocalConversation.switch_acp_model``套
        ``state.agent`` 到包含新 ``acp_model`` 的智能体副本，自动保存路径将其写入
        base_state。 在恢复时，智能体是从
        base_state（单一事实来源）重建的，因此不需要 ``meta.json`` 镜像。
        """
        if self._conversation is None:
            # 匹配其他事件服务方法的非活动服务约定（会话路由器将其映射到 400）。 SDK 不
            # 再针对已创建但尚未运行的对话引发，因此首次运行前的切换是正常的 200 延迟，
            # 而不是错误。
            #
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._conversation.switch_acp_model, model)

    async def close(self):
        if self.bash_event_service is not None:
            await self.bash_event_service.close()
        self._closing = True
        self._explicit_interrupt_generation += 1
        self._rerun_requested = False
        self._acp_internal_rerun_requested = False
        # 放下正在拆除的替代窗口所持有的任何 pin，然后返回此对话的会话许可； close() 会
        # 取消原本会执行此操作的运行，并且泄露的许可证将永久缩减服务器容量。
        #
        self._run_session_pins = 0

        # 首先取消任何正在进行的 /goal 循环，这样它就无法开始新的运行
        # while we drain the current one below.
        if self._goal_loop_task is not None and not self._goal_loop_task.done():
            self._goal_loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._goal_loop_task
        self._goal_loop_task = None

        if self._lease_task is not None:
            self._lease_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._lease_task
            self._lease_task = None

        # 在拆卸前排空飞行中的运行，因此 MCP 关闭不会与工具调用中步竞争。
        #
        run_task = self._run_task
        if run_task is not None and not run_task.done():
            if self._conversation is not None:
                loop = asyncio.get_running_loop()
                try:
                    await loop.run_in_executor(None, self._conversation.pause)
                except Exception:
                    logger.warning(
                        "Failed to pause conversation during close", exc_info=True
                    )
            # 取消运行任务，以便 arun() 的 CancelledError 处理程序可以干净地转换到
            # PAUSED。 对于遗留的线程-池路径，底层线程继续运行，但包装器任务仍然稳定，从
            # 而解除下面的等待阻塞。
            #
            run_task.cancel()
            try:
                await asyncio.wait_for(run_task, timeout=10.0)
            except asyncio.CancelledError:
                pass  # 预计在 cancel() 之后
            except Exception as exc:
                logger.warning("Run task did not exit cleanly during close: %s", exc)
            self._run_task = None

        # 上面的run(s)已经产生了它们的链句柄； 既然拆解已丢失任何引脚，则返回会话许可。
        #
        self._maybe_end_run_session()

        await self._pub_sub.close()
        await self._stream_pub_sub.close()
        if self._conversation:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._conversation.close)
            self._conversation = None
        self.credential_bindings = {}

        if self._lease is not None and self._lease_generation is not None:
            self._lease.release(self._lease_generation)
        self._lease_generation = None
        self._lease = None

    async def generate_title(
        self, llm: "LLM | None" = None, max_length: int = 50
    ) -> str:
        """为对话生成标题。

        如果存在 usage_id，则通过对话的注册表解析提供的 LLM，并在需要时注册它。 然后
        委托给执行器中的LocalConversation以避免阻塞事件循
        环。
        """
        if not self._conversation:
            raise ValueError("inactive_service")

        resolved_llm = llm
        if llm is not None:
            usage_id = llm.usage_id
            try:
                resolved_llm = self._conversation.llm_registry.get(usage_id)
            except KeyError:
                self._conversation.llm_registry.add(llm)
                resolved_llm = llm

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._conversation.generate_title, resolved_llm, max_length
        )

    async def ask_agent(self, question: str) -> str:
        """向智能体询问一个简单的问题，而不影响对话状态。

        委托给执行器中的 LocalConversation 以避免阻塞事件循环。
        """
        if not self._conversation:
            raise ValueError("inactive_service")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._conversation.ask_agent, question)

    async def condense(self) -> None:
        """强制对话历史记录上下文压缩。

        委托给执行器中的 LocalConversation 以避免阻塞事件循环。
        """
        if not self._conversation:
            raise ValueError("inactive_service")

        # 缺少的或忽略请求的上下文压缩器是调用者的智能体配置，而不是服务器故障：报告为如
        # 此，而不是让 LocalConversation's ValueError 展现为 500。
        #
        condenser = self._conversation.agent.condenser
        if condenser is None:
            raise CondensationUnavailable(
                "Cannot condense conversation: No condenser configured"
            )
        if not condenser.handles_condensation_requests():
            raise CondensationUnavailable(
                f"Cannot condense conversation: Condenser "
                f"{type(condenser).__name__} does not handle condensation requests"
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._conversation.condense)

    async def navigate_to(self, event_id: str | None) -> None:
        """将对话 HEAD 移至现有事件（就地重新根）。

        委托给执行器中的 LocalConversation 以避免阻塞事件循环。

        Raises:
            ValueError: 如果 ``event_id`` 不是 ``None`` 并且不在对话中。
        """
        if not self._conversation:
            raise ValueError("inactive_service")

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._conversation.navigate_to, event_id
        )

    def _get_agent_final_response_sync(self) -> str:
        """从活动分支中提取智能体的最终响应。

        只有活动分支才算数：``navigate`` 移回 HEAD 后，废弃分支上的答案不是对话的响应
        。 直接读取 EventLog，而不获取状态锁。
        EventLog 读操作在FIFOLock不存在的情况下是安全的，因为事件一旦写入就是只读和不
        可变的。
        """
        if not self._conversation:
            raise ValueError("inactive_service")
        return get_agent_final_response(self._conversation._state.active_branch())

    async def get_agent_final_response(self) -> str:
        """从对话事件中提取智能体的最终响应。

        返回最后一个 FinishAction 或智能体 MessageEvent 中的文本，如果未找到最终响应
        ，则返回空字符串。
        """
        if not self._conversation:
            raise ValueError("inactive_service")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._get_agent_final_response_sync)

    async def get_state(self) -> ConversationState:
        if not self._conversation:
            raise ValueError("inactive_service")
        return self._conversation._state

    async def _publish_state_update(self):
        """发布具有当前状态的 ConversationStateUpdateEvent。"""
        if not self._conversation:
            return

        state_update_event = await self._create_state_update_event()
        # 注意：_pub_sub 按顺序迭代订阅者。 如果有任何订户
        # 速度慢，会延迟后续的订阅者。 对于高吞吐量场景，请考虑将来使用 asyncio.gather()
        #  进行并发通知。
        #
        await self._pub_sub(state_update_event)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        save_error: BaseException | None = None
        try:
            await self.save_meta()
        except ConversationOwnershipLostError:
            logger.info(
                "Skipping meta save after ownership loss for conversation %s",
                self.stored.id,
            )
        except BaseException as exc:
            save_error = exc
        close_error: BaseException | None = None
        try:
            await self.close()
        except BaseException as exc:
            close_error = exc
        if isinstance(close_error, CredentialBindingError):
            raise close_error
        if save_error is not None:
            if close_error is not None:
                logger.warning(
                    "Event service close also failed after meta save failure",
                    exc_info=(
                        type(close_error),
                        close_error,
                        close_error.__traceback__,
                    ),
                )
            raise save_error
        if close_error is not None:
            raise close_error

    def is_open(self) -> bool:
        return bool(self._conversation)

    def touch(self) -> None:
        """记录活动，以便空闲驱逐推迟此对话。"""
        self._last_active_monotonic = time.monotonic()

    def idle_seconds(self) -> float:
        """自上次记录活动以来的秒数。"""
        return time.monotonic() - self._last_active_monotonic

    def mark_subscription_baseline(self) -> None:
        """当前（内部）订阅者的快照； 后来的都是外在的。"""
        self._internal_subscriber_ids = self._pub_sub.subscriber_ids()

    def has_external_subscribers(self) -> bool:
        """True 如果是非内部订阅者 (e.g. 附有 WebSocket）。"""
        return bool(self._pub_sub.subscriber_ids() - self._internal_subscriber_ids)

    def is_idle_evictable(self) -> bool:
        """只有在没有正在进行的工作且没有外部订阅者的情况下才能安全驱逐。"""
        run_active = self._run_task is not None and not self._run_task.done()
        goal_active = (
            self._goal_loop_task is not None and not self._goal_loop_task.done()
        )
        if (
            self._closing
            or run_active
            or goal_active
            or self._rerun_requested
            or self._acp_internal_rerun_requested
            or self.has_external_subscribers()
        ):
            return False
        return True
