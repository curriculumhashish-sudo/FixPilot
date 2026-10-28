import asyncio
import bisect
import importlib
import json
import os
import threading
import time
import uuid
from collections.abc import Callable, Mapping
from queue import Empty, Queue
from typing import TYPE_CHECKING, Final, Self, SupportsIndex, overload
from urllib.parse import urlparse

import httpx
import websockets
from litellm.types.utils import Delta, ModelResponseStream, StreamingChoices
from websockets.exceptions import ConnectionClosed

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation.base import BaseConversation, ConversationStateProtocol


if TYPE_CHECKING:
    from openhands.sdk.conversation.request import StartConversationRequest
    from openhands.sdk.tool.schema import Action, Observation
from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.events_list_base import EventsListBase
from openhands.sdk.conversation.exceptions import (
    ConversationRunError,
    WebSocketConnectionError,
)
from openhands.sdk.conversation.secret_registry import (
    SecretRegistry,
    SecretValue,
)
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.conversation.title_utils import generate_conversation_title
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationID,
    ConversationTokenCallbackType,
    StuckDetectionThresholds,
    TraceMetadataValue,
)
from openhands.sdk.conversation.visualizer import (
    ConversationVisualizerBase,
    DefaultConversationVisualizer,
)
from openhands.sdk.event.acp_tool_call import ACPToolCallEvent
from openhands.sdk.event.base import Event
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.conversation_state import (
    FULL_STATE_KEY,
    ConversationStateUpdateEvent,
)
from openhands.sdk.event.llm_completion_log import LLMCompletionLogEvent
from openhands.sdk.event.streaming_delta import StreamingDeltaEvent
from openhands.sdk.event.types import EventID
from openhands.sdk.hooks import HookConfig
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.logger import DEBUG, get_logger
from openhands.sdk.observability.laminar import (
    OPERATION_METADATA_KEY,
    default_observability_span_name_from_env,
    merge_observability_metadata,
    observability_parent_span_context_from_env,
    observe,
)
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.confirmation_policy import (
    ConfirmationPolicyBase,
)
from openhands.sdk.tool.client_tool import ClientTool, ClientToolSpec
from openhands.sdk.utils.redact import http_error_log_content
from openhands.sdk.workspace import LocalWorkspace, RemoteWorkspace


logger = get_logger(__name__)

CONVERSATIONS_PATH = "/api/conversations"
FATAL_WS_CLOSE_CODES = frozenset({4001, 4004})
_WEBSOCKET_AUTH_TYPE: Final = "auth"
_WEBSOCKET_SESSION_API_KEY_FIELD: Final = "session_api_key"


def _agent_kind_mismatch_message(conversation_id: ConversationID) -> str:
    return (
        f"Conversation {conversation_id} was started with a different agent kind. "
        "Attach with a matching agent type."
    )


def _validate_remote_agent(agent_data: dict) -> AgentBase:
    if agent_data.get("kind") == "ACPAgent":
        from openhands.sdk.agent.acp_agent import ACPAgent

        return ACPAgent.model_validate(agent_data)
    return AgentBase.model_validate(agent_data)


def _token_delta_callback(
    token_callbacks: list[ConversationTokenCallbackType],
) -> ConversationCallbackType:
    """将每个流式增量从事件套接字传递到 token 回调。"""
    on_token = BaseConversation.compose_callbacks(token_callbacks)

    def callback(event: Event) -> None:
        if isinstance(event, StreamingDeltaEvent):
            delta = Delta(
                content=event.content, reasoning_content=event.reasoning_content
            )
            on_token(
                ModelResponseStream(
                    id=event.id, choices=[StreamingChoices(index=0, delta=delta)]
                )
            )

    return callback


def _restore_tool_registrations(tool_module_qualnames: Mapping[str, str]) -> None:
    """通过远程对话导入工具模块已持久化。"""
    for tool_name, module_qualname in tool_module_qualnames.items():
        try:
            importlib.import_module(module_qualname)
        except ImportError as exc:
            raise ImportError(
                f"Cannot attach to a conversation that uses tool {tool_name!r}: "
                f"failed to import module {module_qualname!r}: {exc}"
            ) from exc


def _websocket_close_code(exc: ConnectionClosed) -> int | None:
    for close_frame in (exc.rcvd, exc.sent):
        if close_frame is not None:
            return close_frame.code
    return None


def _is_fatal_websocket_close(
    exc: ConnectionClosed,
) -> bool:
    return _websocket_close_code(exc) in FATAL_WS_CLOSE_CODES


def _send_request(
    client: httpx.Client,
    method: str,
    url: str,
    acceptable_status_codes: set[int] | None = None,
    **kwargs,
) -> httpx.Response:
    try:
        response = client.request(method, url, **kwargs)
        if acceptable_status_codes and response.status_code in acceptable_status_codes:
            return response
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as e:
        content = http_error_log_content(e.response)
        logger.error(
            "HTTP request failed (%d %s): %s",
            e.response.status_code,
            e.response.reason_phrase,
            content,
            exc_info=True,
        )
        raise e
    except httpx.RequestError as e:
        logger.error(f"Request failed: {e}", exc_info=DEBUG)
        raise e


class WebSocketCallbackClient:
    """最小 WS 客户端：连接、转发事件、出现错误时重试。"""

    host: str
    conversation_id: str
    callback: ConversationCallbackType
    on_reconnect: Callable[[], object] | None
    api_key: str | None
    _thread: threading.Thread | None
    _stop: threading.Event
    _ready: threading.Event

    def __init__(
        self,
        host: str,
        conversation_id: str,
        callback: ConversationCallbackType,
        api_key: str | None = None,
        on_reconnect: Callable[[], object] | None = None,
    ):
        self.host = host
        self.conversation_id = conversation_id
        self.callback = callback
        self.api_key = api_key
        self.on_reconnect = on_reconnect
        self._thread = None
        self._stop = threading.Event()
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._thread:
            return
        self._stop.set()
        self._thread.join(timeout=5)
        self._thread = None

    def wait_until_ready(self, timeout: float | None = None) -> bool:
        """等待 WebSocket 订阅完成。

        订阅完成后，服务器立即发送 ConversationStateUpdateEvent。 此方法会阻塞，直到
        收到该事件、客户端停止或超时过期。

        Args:
            timeout: 最长时间等待（以秒为单位）。 None 表示永远等待。

        Returns:
            True 如果 WebSocket 已准备好，False 如果已停止或超时已过期。
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            # 计算剩余超时
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait_timeout = min(0.05, remaining)
            else:
                wait_timeout = 0.05

            # 使用 Event.wait() 而不是睡眠来有效等待
            if self._ready.wait(timeout=wait_timeout):
                return True

            # 检查是否停止
            if self._stop.is_set():
                return False

    def _run(self) -> None:
        try:
            asyncio.run(self._client_loop())
        except RuntimeError:
            # 回退方案在罕见环境中已经运行循环的情况
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._client_loop())
            loop.close()

    async def _client_loop(self) -> None:
        parsed = urlparse(self.host)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        base = f"{ws_scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
        ws_url = f"{base}/sockets/events/{self.conversation_id}"

        delay = 1.0
        has_connected = False
        while not self._stop.is_set():
            try:
                async with websockets.connect(ws_url) as ws:
                    if self.api_key:
                        await ws.send(
                            json.dumps(
                                {
                                    "type": _WEBSOCKET_AUTH_TYPE,
                                    _WEBSOCKET_SESSION_API_KEY_FIELD: self.api_key,
                                }
                            )
                        )
                    delay = 1.0
                    connection_ready = False
                    async for message in ws:
                        if self._stop.is_set():
                            break
                        try:
                            event = Event.model_validate(json.loads(message))

                            # 在第一个 ConversationStateUpdateEvent 上设置就绪服务器在订
                            # 阅后立即发送此消息
                            #
                            if (
                                isinstance(event, ConversationStateUpdateEvent)
                                and not connection_ready
                            ):
                                connection_ready = True
                                if has_connected:
                                    await self._handle_reconnect()
                                else:
                                    has_connected = True
                                    self._ready.set()

                            self.callback(event)
                        except Exception:
                            logger.exception(
                                "ws_event_processing_error", stack_info=True
                            )
            except ConnectionClosed as exc:
                if _is_fatal_websocket_close(exc):
                    logger.debug("ws_connection_closed_fatal", exc_info=True)
                    self._stop.set()
                    break
                logger.debug("ws_connection_closed_retry", exc_info=True)
                await self._sleep_before_retry(delay)
                delay = min(delay * 2, 30.0)
            except Exception:
                logger.debug("ws_connect_retry", exc_info=True)
                await self._sleep_before_retry(delay)
                delay = min(delay * 2, 30.0)

    async def _handle_reconnect(self) -> None:
        if not self.on_reconnect:
            return
        try:
            await asyncio.to_thread(self.on_reconnect)
        except Exception:
            logger.exception("ws_reconnect_callback_error", stack_info=True)

    async def _sleep_before_retry(self, delay: float) -> None:
        deadline = time.monotonic() + delay
        while not self._stop.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.1, remaining))


class RemoteEventsList(EventsListBase):
    """远程对话事件的类似列表的只读视图。

    第一次访问时，它从服务器获取现有事件。 之后，它依赖 WebSocket 流来增量追加新事件
    。
    """

    _client: httpx.Client
    _conversation_id: str
    _events_base_path: str
    _cached_events: list[Event]
    _cached_event_ids: set[str]
    _lock: threading.RLock

    def __init__(
        self,
        client: httpx.Client,
        conversation_id: str,
        events_base_path: str = CONVERSATIONS_PATH,
    ):
        self._client = client
        self._conversation_id = conversation_id
        self._events_base_path = events_base_path
        self._cached_events: list[Event] = []
        self._cached_event_ids: set[str] = set()
        self._acp_tool_call_id_to_event_id: dict[str, str] = {}
        self._lock = threading.RLock()
        # 初始获取同步个现有事件
        self._do_full_sync()

    def _do_full_sync(self) -> None:
        """使用遥控器 API 执行完整的同步。"""
        logger.debug(f"Performing full sync for conversation {self._conversation_id}")

        events = []
        page_id = None

        while True:
            params = {"limit": 100}
            if page_id:
                params["page_id"] = page_id

            resp = _send_request(
                self._client,
                "GET",
                f"{self._events_base_path}/{self._conversation_id}/events/search",
                params=params,
            )
            data = resp.json()

            events.extend([Event.model_validate(item) for item in data["items"]])

            if not data.get("next_page_id"):
                break
            page_id = data["next_page_id"]

        self._cached_events = events
        self._cached_event_ids.update(e.id for e in events)
        logger.debug(f"Full sync completed, {len(events)} events cached")

    def reconcile(self) -> int:
        """通过获取和合并事件来协调本地缓存与服务器。

        此方法从服务器获取所有事件并将它们与本地缓存合并，并按事件 ID 进行重复数据删
        除。 这可确保不会因 REST、同步和 WebSocket 订阅之间的竞态条
        件而错过任何事件。

        Returns:
            调节期间添加的新事件数。
        """
        logger.debug(
            f"Performing reconciliation sync for conversation {self._conversation_id}"
        )

        events = []
        page_id = None

        while True:
            params = {"limit": 100}
            if page_id:
                params["page_id"] = page_id

            try:
                resp = _send_request(
                    self._client,
                    "GET",
                    f"{self._events_base_path}/{self._conversation_id}/events/search",
                    params=params,
                )
                data = resp.json()
            except Exception as e:
                logger.warning(f"Failed to fetch events during reconciliation: {e}")
                break  # 返回部分结果而不是完全失败

            events.extend([Event.model_validate(item) for item in data["items"]])

            if not data.get("next_page_id"):
                break
            page_id = data["next_page_id"]

        # 将事件合并到缓存中，所有事件获取一次锁
        added_count = 0
        with self._lock:
            for event in events:
                if event.id not in self._cached_event_ids:
                    self._add_event_unsafe(event)
                    added_count += 1

        logger.debug(
            f"Reconciliation completed, {added_count} new events added "
            f"(total: {len(self._cached_events)})"
        )
        return added_count

    def _add_event_unsafe(self, event: Event) -> None:
        """将事件添加到缓存而不获取锁（调用者必须持有锁）。"""
        # ACP emits two ACPToolCallEvents 按次收费 ``started`` 事件和一个终端（
        # ``completed`` / ``failed``) event — the action->观测结果 pair for a 工具调用。
        #  合并 tool_call_id替换  ``started`` 将终端端点替换为入参，这样单张卡片从运行状
        # 态更新到结果状态，与一个的端点更新方式相同 ObservationEvent 取代其 ActionEvent
        # . (源不再按累积输出帧数分发一个帧 ToolCallProgress所以这是一个 O(1) 两个事件合
        # 并，不是 O(n²) dedup.)
        #
        if isinstance(event, ACPToolCallEvent):
            existing_id = self._acp_tool_call_id_to_event_id.get(event.tool_call_id)
            if existing_id is not None:
                for i, e in enumerate(self._cached_events):
                    if e.id == existing_id:
                        self._cached_events[i] = event
                        self._cached_event_ids.discard(existing_id)
                        self._cached_event_ids.add(event.id)
                        self._acp_tool_call_id_to_event_id[event.tool_call_id] = (
                            event.id
                        )
                        logger.debug(
                            f"Replaced ACP tool call event {existing_id} -> {event.id} "
                            f"(tool_call_id={event.tool_call_id})"
                        )
                        return
                # Index指向的事件不再在_cached_events中； 清理过时的条目，这样我们就不会
                # 继续使用它。
                #
                logger.warning(
                    "Stale ACP tool-call index entry: "
                    f"tool_call_id={event.tool_call_id} "
                    f"pointed to event {existing_id} "
                    "not found in _cached_events; removing stale entry."
                )
                self._cached_event_ids.discard(existing_id)
                del self._acp_tool_call_id_to_event_id[event.tool_call_id]

        # 使用带有 key 函数的 bisect 进行 O(log N) 插入这可确保事件始终正确排序，即使
        # WebSocket 传递的事件顺序不正确
        #
        insert_pos = bisect.bisect_right(
            self._cached_events, event.timestamp, key=lambda e: e.timestamp
        )
        self._cached_events.insert(insert_pos, event)
        self._cached_event_ids.add(event.id)
        if isinstance(event, ACPToolCallEvent):
            self._acp_tool_call_id_to_event_id[event.tool_call_id] = event.id
        logger.debug(f"Added event {event.id} to local cache at position {insert_pos}")

    def add_event(self, event: Event) -> None:
        """将新事件添加到本地缓存（由WebSocket 回调调用）。

        事件按时间戳按排序顺序插入，以保持正确的时间顺序，而不管 WebSocket 传递顺序如
        何。
        """
        with self._lock:
            # 检查事件是否已存在以避免重复
            if event.id not in self._cached_event_ids:
                self._add_event_unsafe(event)

    def append(self, event: Event) -> int:
        """将新事件添加到列表中（为了与 EventLog 接口兼容）。

        不像``EventLog``，这个缓存是按事件时间戳排序的（而不是按调用顺序），并且在内
        存中合并了一些ACP对，因此无法返回每个事件的序列号。 返回写入后缓
        存的长度，仅满足``EventsListBase``。
        """
        self.add_event(event)
        return len(self._cached_events) - 1

    def create_default_callback(self) -> ConversationCallbackType:
        """创建一个默认回调，将事件添加到此列表。

        流的 ``StreamingDeltaEvent`` 帧是临时的：服务器永远不会存储它们，因此它们到达
        对方回调但不要将自己列入这个列表，这个列表会匹配服务器
        的日志。
        """

        def callback(event: Event) -> None:
            if isinstance(event, StreamingDeltaEvent):
                return
            self.add_event(event)

        return callback

    def __len__(self) -> int:
        return len(self._cached_events)

    @overload
    def __getitem__(self, index: int) -> Event: ...

    @overload
    def __getitem__(self, index: slice) -> list[Event]: ...

    def __getitem__(self, index: SupportsIndex | slice) -> Event | list[Event]:
        with self._lock:
            return self._cached_events[index]

    def __iter__(self):
        with self._lock:
            return iter(self._cached_events)


class RemoteState(ConversationStateProtocol):
    """用于访问远程会话状态的类似状态的接口。"""

    _client: httpx.Client
    _conversation_id: str
    _conversation_info_base_path: str
    _events: RemoteEventsList
    _cached_state: dict | None
    _lock: threading.RLock

    def __init__(
        self,
        client: httpx.Client,
        conversation_id: str,
        conversation_info_base_path: str = CONVERSATIONS_PATH,
        events_base_path: str = CONVERSATIONS_PATH,
    ):
        self._client = client
        self._conversation_id = conversation_id
        self._conversation_info_base_path = conversation_info_base_path
        self._events = RemoteEventsList(client, conversation_id, events_base_path)

        # 缓存状态信息以避免 REST 调用
        self._cached_state = None
        self._lock = threading.RLock()

    def _get_conversation_info(self) -> dict:
        """从远程获取最新的对话信息 API。"""
        with self._lock:
            # 返回缓存状态（如果可用）
            if self._cached_state is not None:
                return self._cached_state

            # 如果没有缓存状态，则回退方案到 REST API
            return self.refresh_from_server()

    def refresh_from_server(self) -> dict:
        """获取并缓存最新的权威对话状态。"""
        resp = _send_request(
            self._client,
            "GET",
            f"{self._conversation_info_base_path}/{self._conversation_id}",
        )
        state = resp.json()
        with self._lock:
            self._cached_state = state
            return state

    def update_state_from_event(self, event: ConversationStateUpdateEvent) -> None:
        """从 ConversationStateUpdateEvent 更新缓存状态。"""
        with self._lock:
            # 处理全状态快照
            if event.key == FULL_STATE_KEY:
                # 使用完整快照更新缓存状态
                if self._cached_state is None:
                    self._cached_state = {}
                self._cached_state.update(event.value)
            else:
                # 处理各个字段更新
                if self._cached_state is None:
                    self._cached_state = {}
                self._cached_state[event.key] = event.value

    def create_state_update_callback(self) -> ConversationCallbackType:
        """创建一个回调来更新 ConversationStateUpdateEvent 的状态。"""

        def callback(event: Event) -> None:
            if isinstance(event, ConversationStateUpdateEvent):
                self.update_state_from_event(event)

        return callback

    @property
    def events(self) -> RemoteEventsList:
        """访问事件列表。"""
        return self._events

    @property
    def id(self) -> ConversationID:
        """对话 ID。"""
        return uuid.UUID(self._conversation_id)

    @property
    def execution_status(self) -> ConversationExecutionStatus:
        """当前会话执行状态。"""
        info = self._get_conversation_info()
        status_str = info.get("execution_status")
        if status_str is None:
            raise RuntimeError(
                "execution_status missing in conversation info: " + str(info)
            )
        return ConversationExecutionStatus(status_str)

    @property
    def confirmation_policy(self) -> ConfirmationPolicyBase:
        """确认政策。"""
        info = self._get_conversation_info()
        policy_data = info.get("confirmation_policy")
        if policy_data is None:
            raise RuntimeError(
                "confirmation_policy missing in conversation info: " + str(info)
            )
        return ConfirmationPolicyBase.model_validate(policy_data)

    @property
    def security_analyzer(self) -> SecurityAnalyzerBase | None:
        """安全分析器。"""
        info = self._get_conversation_info()
        analyzer_data = info.get("security_analyzer")
        if analyzer_data:
            return SecurityAnalyzerBase.model_validate(analyzer_data)

        return None

    @property
    def activated_knowledge_skills(self) -> list[str]:
        """激活的知识技能列表。"""
        info = self._get_conversation_info()
        return info.get("activated_knowledge_skills", [])

    @property
    def invoked_skills(self) -> list[str]:
        """明确调用的渐进式披露技能的名称。"""
        info = self._get_conversation_info()
        return info.get("invoked_skills", [])

    @property
    def agent(self):
        """智能体配置（从远程获取）。"""
        info = self._get_conversation_info()
        agent_data = info.get("agent")
        if agent_data is None:
            raise RuntimeError("agent missing in conversation info: " + str(info))
        return _validate_remote_agent(agent_data)

    @property
    def workspace(self):
        """工作目录（从远程获取）。"""
        info = self._get_conversation_info()
        workspace = info.get("workspace")
        if workspace is None:
            raise RuntimeError("workspace missing in conversation info: " + str(info))
        return workspace

    @property
    def persistence_dir(self):
        """持久化目录（从远程获取）。"""
        info = self._get_conversation_info()
        persistence_dir = info.get("persistence_dir")
        if persistence_dir is None:
            raise RuntimeError(
                "persistence_dir missing in conversation info: " + str(info)
            )
        return persistence_dir

    @property
    def stats(self) -> ConversationStats:
        """获取对话统计信息（从远程获取）。"""
        info = self._get_conversation_info()
        stats_data = info.get("stats", {})
        return ConversationStats.model_validate(stats_data)

    @property
    def hook_config(self) -> HookConfig | None:
        """获取钩子配置（从远程获取）。"""
        info = self._get_conversation_info()
        hook_config_data = info.get("hook_config")
        if hook_config_data is not None:
            return HookConfig.model_validate(hook_config_data)
        return None

    @property
    def secret_registry(self) -> SecretRegistry:
        """此对话的机密注册表。"""
        info = self._get_conversation_info()
        secret_registry_data = info.get("secret_registry")
        if secret_registry_data is not None:
            return SecretRegistry.model_validate(secret_registry_data)
        return SecretRegistry()

    def model_dump(self, **_kwargs):
        """获取远程状态的字典表示。"""
        info = self._get_conversation_info()
        return info

    def model_dump_json(self, **kwargs):
        """获取远程状态的 JSON 表示。"""
        return json.dumps(self.model_dump(**kwargs))

    # 上下文管理器与 ConversationState 兼容的方法
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class RemoteConversation(BaseConversation):
    _id: uuid.UUID
    _state: "RemoteState"
    _visualizer: ConversationVisualizerBase | None
    _ws_client: "WebSocketCallbackClient | None"
    agent: AgentBase
    _callbacks: list[ConversationCallbackType]
    max_iteration_per_run: int
    workspace: RemoteWorkspace
    _client: httpx.Client
    _cleanup_initiated: bool
    _terminal_status_queue: Queue[str]
    _run_armed: threading.Event
    delete_on_close: bool = False

    def __init__(
        self,
        agent: AgentBase,
        workspace: RemoteWorkspace,
        plugins: list | None = None,
        conversation_id: ConversationID | None = None,
        callbacks: list[ConversationCallbackType] | None = None,
        max_iteration_per_run: int = 500,
        stuck_detection: bool = True,
        stuck_detection_thresholds: (
            StuckDetectionThresholds | Mapping[str, int] | None
        ) = None,
        hook_config: HookConfig | None = None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ) = DefaultConversationVisualizer,
        secrets: Mapping[str, SecretValue] | None = None,
        delete_on_close: bool = False,
        tags: dict[str, str] | None = None,
        user_id: str | None = None,
        client_tools: list[ClientToolSpec] | None = None,
        observability_metadata: dict[str, TraceMetadataValue] | None = None,
        observability_tags: list[str] | None = None,
        observability_span_name: str = "conversation",
        observability_parent_span_context: str | None = None,
        token_callbacks: list[ConversationTokenCallbackType] | None = None,
        **_: object,
    ) -> None:
        """与 Agent Server 对话的远程对话代理。

        Args:
            agent: 智能体配置（将发送到服务器）
            workspace: 工作目录用于智能体操作和工具执行。
            plugins: 要在服务器上加载的可选插件列表。 每个插件
                    是一个 PluginSource，指定来源、参考和 repo_path。
            conversation_id: 要附加到的可选现有对话 ID
            callbacks: 可选回调用于接收事件（尚未流式传输）
            max_iteration_per_run: 服务器上配置的最大迭代次数
            stuck_detection: 是否启用服务器卡顿检测
            stuck_detection_thresholds: 卡住检测的可选配置
                      阈值。 可以是 StuckDetectionThresholds 实例或带有键的字典：“
                      action_observation”、
                      “action_error”、“monologue”、“alternating_pattern”。 值是表示触
                      发前重复次数的整数
                      。
            hook_config: 发送到服务器的可选钩子配置。
                      所有钩子都在服务器端执行。
            visualizer: 可视化配置。 可以是：
                       - ConversationVisualizerBase 子类：要实例化的类（默认值：
                       ConversationVisualizer）
                       - ConversationVisualizerBase 实例：使用自定义可视化工具
                       - None: 无可视化
            secrets: 可选机密用于初始化对话
            tags: 对话的可选键值标签。 钥匙必须是
                  小写字母数字，值最多 256 个字符。
            user_id: 与可观察性跟踪关联的可选用户 ID
            client_tools: 客户定义的工具规格的可选列表。 这些工具
                      没有服务器端执行器 - 当智能体调用它们时，会通过 WebSocket 发出
                      ActionEvent，并且客户端通过回调处理执行
                      。
            observability_metadata: 可观察性后端的可选跟踪元数据。
            observability_tags: 用于可观察性后端的可选根跨度标签。
            observability_span_name: 用于可观察性的可选子跨度名称
                      后端。 根跨度仍命名为“conversation”。
            token_callbacks: 每个流式传输 token 都会调用可选回调
                      服务器发送的增量（智能体 LLM 和 ``stream=True``）。
        """
        super().__init__()
        observability_metadata = merge_observability_metadata(observability_metadata)
        observability_parent_span_context = (
            observability_parent_span_context
            or observability_parent_span_context_from_env()
        )
        default_span_name = default_observability_span_name_from_env()
        if default_span_name and observability_span_name == "conversation":
            observability_span_name = default_span_name

        # 客户端工具规范服务器已具有用于此对话的已持久化（在重新附加到现有对话时填充）。
        #  这些必须在初始事件同步之前在本地注册，以便已持久化 ``ClientAction_*`` 事件可
        # 以是已反序列化。
        #
        attached_client_tools: list[ClientToolSpec] = []
        # 工具模块已持久化与现有的对话。 导入它们会注册已持久化事件引用的动态操作类型，
        # 因此这必须在 ``_initialize_connection`` 同步事件之前发生。
        #
        attached_tool_module_qualnames: Mapping[str, str] = {}

        should_create = conversation_id is None
        if conversation_id is not None:
            # 尝试附加到现有对话
            resp = _send_request(
                workspace.client,
                "GET",
                f"{CONVERSATIONS_PATH}/{conversation_id}",
                acceptable_status_codes={404},
            )
            if resp.status_code == 404:
                # 对话不存在，我们将创建它
                should_create = True
            else:
                info = resp.json()
                agent_payload = info.get("agent")
                if agent_payload is not None:
                    remote_agent = _validate_remote_agent(agent_payload)
                    if remote_agent.agent_kind != agent.agent_kind:
                        raise ValueError(_agent_kind_mismatch_message(conversation_id))
                # 捕获已持久化客户端工具规范，以便我们可以在 RemoteState 同步事件之前注
                # 册其动态操作类型。
                #
                for raw_spec in info.get("client_tools") or []:
                    attached_client_tools.append(
                        ClientToolSpec.model_validate(raw_spec)
                    )
                attached_tool_module_qualnames = info.get("tool_module_qualnames") or {}

        if should_create:
            # 在这里导入以避免循环导入
            from openhands.sdk.subagent.registry import get_registered_agent_definitions
            from openhands.sdk.tool.registry import get_tool_module_qualnames

            tool_qualnames = get_tool_module_qualnames()
            logger.debug(f"Sending tool_module_qualnames to server: {tool_qualnames}")

            agent_defs = get_registered_agent_definitions()
            serialized_defs = [d.model_dump(mode="json") for d in agent_defs]
            logger.debug(f"Sending {len(serialized_defs)} agent_definitions to server")

            payload = {
                "agent": agent.model_dump(
                    mode="json", context={"expose_secrets": True}
                ),
                "initial_message": None,
                "max_iterations": max_iteration_per_run,
                "stuck_detection": stuck_detection,
                # 我们需要将RemoteWorkspace转换为LocalWorkspace以供服务器使用
                "workspace": LocalWorkspace(
                    working_dir=workspace.working_dir
                ).model_dump(),
                # 包括用于在服务器上动态注册的工具模块限定名
                "tool_module_qualnames": tool_qualnames,
                # 包括服务器上子智能体注册的智能体定义
                "agent_definitions": serialized_defs,
                # 包括要在服务器上加载的插件
                "plugins": [p.model_dump() for p in plugins] if plugins else None,
                # 包含 hook_config 用于服务器端挂钩
                "hook_config": hook_config.model_dump() if hook_config else None,
                # 包括客户端定义的工具规范（无服务器端执行器）
                "client_tools": (
                    [s.model_dump(mode="json") for s in client_tools]
                    if client_tools
                    else []
                ),
                # 包括标签和可观察性元数据（如果提供）
                "tags": tags if tags is not None else {},
                "observability_metadata": observability_metadata
                if observability_metadata is not None
                else {},
                "observability_tags": observability_tags
                if observability_tags is not None
                else [],
                "observability_span_name": observability_span_name,
                "observability_parent_span_context": observability_parent_span_context,
                "user_id": user_id,
            }
            if user_id:
                payload["user_id"] = user_id
            if stuck_detection_thresholds is not None:
                # 如果是 dict 则转换为 StuckDetectionThresholds，则转换为序列化
                if isinstance(stuck_detection_thresholds, Mapping):
                    threshold_config = StuckDetectionThresholds(
                        **stuck_detection_thresholds
                    )
                else:
                    threshold_config = stuck_detection_thresholds
                payload["stuck_detection_thresholds"] = threshold_config.model_dump()
            # 如果提供，请包含 conversation_id（用于使用特定 ID 创建）
            if conversation_id is not None:
                payload["conversation_id"] = str(conversation_id)
            resp = _send_request(
                workspace.client,
                "POST",
                CONVERSATIONS_PATH,
                json=payload,
            )
            data = resp.json()
            # 期待 ConversationInfo
            cid = data.get("id") or data.get("conversation_id")
            if not cid:
                raise RuntimeError(
                    "Invalid response from server: missing conversation id"
                )
            conversation_id = uuid.UUID(cid)

            workspace.register_conversation(str(conversation_id))

        assert conversation_id is not None
        # 连接前注册已持久化工具，以便 ``_initialize_connection`` 期间同步的事件可以是已
        # 反序列化。 ``_from_info`` 对 ``attach``/``create``入口执行相同的操作。
        #
        _restore_tool_registrations(attached_tool_module_qualnames)
        self._initialize_connection(
            agent=agent,
            workspace=workspace,
            conversation_id=conversation_id,
            callbacks=callbacks,
            token_callbacks=token_callbacks,
            max_iteration_per_run=max_iteration_per_run,
            client_tools=[*(client_tools or []), *attached_client_tools],
            visualizer=visualizer,
        )

        # 初始化机密（如果提供）
        if secrets:
            # 将 dict[str, str] 转换为 dict[str, SecretValue]
            secret_values: dict[str, SecretValue] = {k: v for k, v in secrets.items()}
            self.update_secrets(secret_values)

        self._start_observability_span(
            str(self._id),
            span_name=observability_span_name,
            user_id=user_id,
            metadata=observability_metadata,
            tags=observability_tags,
            conversation_tags=tags,
            parent_span_context=observability_parent_span_context,
        )
        # 所有钩子（包括SessionStart/SessionEnd）都在服务器端执行。 hook_config 在创作载
        # 荷中发送。
        #
        self.delete_on_close = delete_on_close

    @classmethod
    def create(
        cls,
        workspace: RemoteWorkspace,
        request: "StartConversationRequest",
        *,
        callbacks: list[ConversationCallbackType] | None = None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ) = DefaultConversationVisualizer,
    ) -> Self:
        """提交创建请求并连接到返回的对话。

        该请求选择智能体源（``agent``、``agent_settings`` 或已保存的
        ``agent_profile_id``）和所有服务器选项。 提供
        的会话 ID 遵循服务器的幂等性契约； 此方法不会探测现有对话。
        """
        updates: dict[str, object] = {
            "observability_metadata": merge_observability_metadata(
                request.observability_metadata
            ),
        }
        default_span_name = default_observability_span_name_from_env()
        if default_span_name and request.observability_span_name == "conversation":
            updates["observability_span_name"] = default_span_name
        parent_span_context = (
            request.observability_parent_span_context
            or observability_parent_span_context_from_env()
        )
        if parent_span_context:
            updates["observability_parent_span_context"] = parent_span_context
        request = request.model_copy(update=updates)

        response = _send_request(
            workspace.client,
            "POST",
            CONVERSATIONS_PATH,
            json=request.model_dump(
                mode="json", exclude_none=True, context={"expose_secrets": True}
            ),
        )
        info = response.json()
        workspace.register_conversation(info["id"])
        conversation = cls._from_info(workspace, info, callbacks, visualizer)
        conversation._start_observability_span(
            str(conversation.id),
            span_name=request.observability_span_name,
            user_id=request.user_id,
            metadata=request.observability_metadata,
            tags=request.observability_tags,
            conversation_tags=request.tags,
            parent_span_context=request.observability_parent_span_context,
        )
        return conversation

    @classmethod
    def attach(
        cls,
        workspace: RemoteWorkspace,
        conversation_id: ConversationID,
        *,
        callbacks: list[ConversationCallbackType] | None = None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ) = DefaultConversationVisualizer,
    ) -> Self:
        """使用保存的智能体连接； 切勿创建或更新对话。

        丢失或无法访问的对话会引发 HTTP 错误。
        """
        response = _send_request(
            workspace.client, "GET", f"{CONVERSATIONS_PATH}/{conversation_id}"
        )
        conversation = cls._from_info(workspace, response.json(), callbacks, visualizer)
        conversation._start_observability_span(str(conversation.id))
        return conversation

    @classmethod
    def _from_info(
        cls,
        workspace: RemoteWorkspace,
        info: dict,
        callbacks: list[ConversationCallbackType] | None,
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ),
    ) -> Self:
        _restore_tool_registrations(info.get("tool_module_qualnames") or {})
        conversation = cls.__new__(cls)
        conversation._initialize_connection(
            agent=_validate_remote_agent(info["agent"]),
            workspace=workspace,
            conversation_id=uuid.UUID(info["id"]),
            callbacks=callbacks,
            max_iteration_per_run=info["max_iterations"],
            client_tools=[
                ClientToolSpec.model_validate(spec)
                for spec in info.get("client_tools") or []
            ],
            visualizer=visualizer,
        )
        return conversation

    def _initialize_connection(
        self,
        *,
        agent: AgentBase,
        workspace: RemoteWorkspace,
        conversation_id: ConversationID,
        callbacks: list[ConversationCallbackType] | None,
        max_iteration_per_run: int,
        client_tools: list[ClientToolSpec],
        visualizer: (
            type[ConversationVisualizerBase] | ConversationVisualizerBase | None
        ),
        token_callbacks: list[ConversationTokenCallbackType] | None = None,
    ) -> None:
        super().__init__()  # 使用跨度跟踪初始化基类
        self.agent = agent
        self._callbacks = callbacks or []
        if token_callbacks:
            self._callbacks.append(_token_delta_callback(token_callbacks))
        self.max_iteration_per_run = max_iteration_per_run
        self.workspace = workspace
        self._client = workspace.client
        self._cleanup_initiated = False
        self._terminal_status_queue: Queue[str] = Queue()
        self._run_armed = threading.Event()

        self._id = conversation_id
        # 在本地注册客户端工具操作类型，因此 WebSocket/具有 ClientAction_* action_type
        # 的持久事件可以是已反序列化到事件循环。 这必须涵盖调用者传递的规格和服务器原有
        # 的规格已持久化（在重新连接时），因此 conversation_id 的简单重新连接仍然同步已
        # 持久化事件。
        #
        seen_client_tool_names: set[str] = set()
        for spec in client_tools:
            if spec.name in seen_client_tool_names:
                continue
            seen_client_tool_names.add(spec.name)
            ClientTool.from_spec(spec)

        # 初始化远程状态
        self._state = RemoteState(self._client, str(self._id))

        # 添加默认值回调以维护本地事件状态
        default_callback = self._state.events.create_default_callback()
        self._callbacks.append(default_callback)

        # 添加回调以更新 WebSocket 事件的状态
        state_update_callback = self._state.create_state_update_callback()
        self._callbacks.append(state_update_callback)

        # 添加回调来处理 LLM 完成日志如果任何 LLM 启用了 log_completions，则注册回调
        #
        if any(llm.log_completions for llm in agent.get_all_llms()):
            llm_log_callback = self._create_llm_completion_log_callback()
            self._callbacks.append(llm_log_callback)

        # 处理可视化配置
        if isinstance(visualizer, ConversationVisualizerBase):
            # 使用自定义可视化工具实例
            self._visualizer = visualizer
            # 使用对话状态初始化可视化工具
            self._visualizer.initialize(self._state)
            self._callbacks.append(self._visualizer.on_event)
        elif isinstance(visualizer, type) and issubclass(
            visualizer, ConversationVisualizerBase
        ):
            # 使用适当的参数实例化可视化工具类
            self._visualizer = visualizer()
            # 用状态初始化
            self._visualizer.initialize(self._state)
            self._callbacks.append(self._visualizer.on_event)
        else:
            # 无可视化（可视化工具为 None）
            self._visualizer = None

        # 添加回调，当运行完成时通过 WebSocket 发出信号。 服务器的运行后完整状态快照是唯
        # 一权威的WebSocket成功信号。 每个字段 FINISHED 是一个提示，因为停止挂钩仍然可以
        # 恢复它； 每个字段 ERROR/STUCK 保持立即。
        #
        def run_complete_callback(event: Event) -> None:
            if not isinstance(event, ConversationStateUpdateEvent):
                return

            if event.key == "execution_status":
                try:
                    status = ConversationExecutionStatus(event.value)
                except ValueError:
                    return
                if status in (
                    ConversationExecutionStatus.ERROR,
                    ConversationExecutionStatus.STUCK,
                ):
                    self._terminal_status_queue.put(status.value)
                return

            if event.key != FULL_STATE_KEY:
                return

            # 仅当运行实际正在进行时才接受全状态快照作为运行完成信号。 WS 订阅在
            # connect() 期间交付初始全状态快照； 如果该快照具有非 RUNNING 状态 (e.g. “
            # idle”），它可以被 _wait_for_run_completion() 拾取作为完成信号
            # *next* run() 调用，导致blocking=True 在
            # 服务器实际上已经完成了。
            if not self._run_armed.is_set():
                return

            raw_status = event.value.get("execution_status")
            try:
                status = ConversationExecutionStatus(raw_status)
            except ValueError:
                return

            if status != ConversationExecutionStatus.RUNNING:
                self._terminal_status_queue.put(status.value)

        # 将所有回调组合成一个回调
        all_callbacks = self._callbacks + [run_complete_callback]
        composed_callback = BaseConversation.compose_callbacks(all_callbacks)

        # 跟踪哪些事件回调已经看到，以便记录在重连期间服务器记录的事件（这些事件仅通过缓
        # 存到达） REST [reconciliation) 可以被重播一次，而不会让活的 socket 为他们发送
        # 第二次。
        #
        delivered_ids: set[str] = set()
        replayed_ids: set[str] = set()

        def socket_callback(event: Event) -> None:
            if event.id in replayed_ids:
                replayed_ids.discard(event.id)
                return
            delivered_ids.add(event.id)
            composed_callback(event)

        def replay_missed_events() -> None:
            self._state.events.reconcile()
            replayed_ids.clear()
            for event in self._state.events[:]:
                if event.id in delivered_ids:
                    continue
                delivered_ids.add(event.id)
                replayed_ids.add(event.id)
                try:
                    composed_callback(event)
                except Exception:
                    logger.exception("ws_replay_callback_error", stack_info=True)

        # 为回调初始化 WebSocket 客户端
        self._ws_client = WebSocketCallbackClient(
            host=self.workspace.host,
            conversation_id=str(self._id),
            callback=socket_callback,
            api_key=self.workspace.api_key,
            on_reconnect=replay_missed_events,
        )
        self._ws_client.start()

        # 在允许操作之前等待 WebSocket 订阅完成。 这确保了 send_message() 期间发出的事件
        # 不会被错过。 订阅后服务器发送ConversationStateUpdateEvent。
        #
        ws_timeout = float(os.getenv("OPENHANDS_REMOTE_WS_READY_TIMEOUT", "30"))
        if not self._ws_client.wait_until_ready(timeout=ws_timeout):
            if os.getenv("OPENHANDS_REMOTE_WS_READY_REQUIRED", "true").lower() in (
                "0",
                "false",
                "no",
            ):
                logger.warning(
                    "WebSocket subscription did not become ready within %.1f "
                    "seconds for conversation %s; continuing after REST "
                    "reconciliation because OPENHANDS_REMOTE_WS_READY_REQUIRED "
                    "is false.",
                    ws_timeout,
                    self._id,
                )
            else:
                try:
                    self._ws_client.stop()
                except Exception:
                    pass
                finally:
                    self._ws_client = None
                raise WebSocketConnectionError(
                    conversation_id=self._id,
                    timeout=ws_timeout,
                )

        # 在 WebSocket 准备好捕获初始 REST 同步和 WebSocket 订阅之间发出的任何事件后协调
        # 事件。 这是订阅握手的“和解”部分。
        #
        self._state.events.reconcile()
        # 回调不重播历史记录：只有在此点之后记录的事件以及套接字错过的事件才会在重新连接
        # 时重播。
        #
        delivered_ids.update(event.id for event in self._state.events[:])

    def _create_llm_completion_log_callback(self) -> ConversationCallbackType:
        """创建一个将 LLM 完成日志写入客户端文件系统的回调。"""

        def callback(event: Event) -> None:
            if not isinstance(event, LLMCompletionLogEvent):
                return

            # 查找与 usage_id 匹配的 LLM
            target_llm = None
            for llm in self.agent.get_all_llms():
                if llm.usage_id == event.usage_id:
                    target_llm = llm
                    break

            if not target_llm or not target_llm.log_completions:
                logger.debug(
                    f"No LLM with log_completions enabled found "
                    f"for usage_id={event.usage_id}"
                )
                return

            try:
                log_dir = target_llm.log_completions_folder
                os.makedirs(log_dir, exist_ok=True)
                log_path = os.path.join(log_dir, event.filename)
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write(event.log_data)
                logger.debug(f"Wrote LLM completion log to {log_path}")
            except Exception as e:
                logger.warning(f"Failed to write LLM completion log: {e}")

        return callback

    @property
    def id(self) -> ConversationID:
        return self._id

    @property
    def state(self) -> RemoteState:
        """访问远程会话状态。"""
        return self._state

    @property
    def conversation_stats(self):
        return self._state.stats

    @property
    def stuck_detector(self):
        """卡住检测器以实现兼容性。
        未实现远程对话。"""
        raise NotImplementedError(
            "For remote conversations, stuck detection is not available"
            " since it would be handled server-side."
        )

    @observe(name="conversation.send_message")
    def send_message(self, message: str | Message, sender: str | None = None) -> None:
        if isinstance(message, str):
            message = Message(role="user", content=[TextContent(text=message)])
        assert message.role == "user", (
            "Only user messages are allowed to be sent to the agent."
        )
        payload = {
            "role": message.role,
            "content": [c.model_dump() for c in message.content],
            "run": False,  # 镜像局部语义； 必须调用显式 run()
        }
        if sender is not None:
            payload["sender"] = sender
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/events",
            json=payload,
        )

    @observe(name="conversation.run")
    def run(
        self,
        blocking: bool = True,
        poll_interval: float = 1.0,
        timeout: float = 3600.0,
    ) -> None:
        """在服务器上触发运行。

        Args:
            blocking: 如果True（默认），则通过轮询等待运行完成
                服务器。 如果False，则触发运行后立即返回。
            poll_interval: 状态轮询之间的时间（以秒为单位）（仅在以下情况下使用）
                blocking=True). Default is 1.0 second.
            timeout: 等待运行完成的最长时间（以秒为单位）
                （仅当阻塞=True时使用）。 默认值为 3600 秒。

        Raises:
            ConversationRunError: 如果运行失败或超时。
        """
        # 在准备新的运行之前，请解除并清除之前运行中的任何过时的终端状态事件。
        # _run_armed门run_complete_callback中的全状态WS快照； 此处清除它可以防止初始 WS
        # 订阅快照被误认为是运行后快照。
        #
        self._run_armed.clear()
        self._drain_terminal_status_queue()
        run_start_event_count = len(self._state.events)

        # 使用专用运行端点在服务器上触发运行。 让服务器告诉我们它是否已经在运行 (409)，
        # 避免额外的 GET。
        #
        try:
            resp = _send_request(
                self._client,
                "POST",
                f"{CONVERSATIONS_PATH}/{self._id}/run",
                acceptable_status_codes={200, 201, 204, 409},
                timeout=30,  # 短超时表示触发请求
            )
        except Exception as e:  # _send_request 已记录 httpx 错误
            # Surface 对话 ID 可帮助恢复
            raise ConversationRunError(self._id, e) from e

        if resp.status_code == 409:
            logger.info("Conversation is already running; skipping run trigger")
        else:
            logger.info(f"run() triggered successfully: {resp}")

        if blocking:
            # 在 POST 之后进行 Arm，以便仅将触发运行后到达的 WS 全状态快照视为运行完成信
            # 号。
            #
            self._run_armed.set()
            try:
                self._wait_for_run_completion(
                    poll_interval, timeout, run_start_event_count
                )
            finally:
                self._run_armed.clear()

    def _wait_for_run_completion(
        self,
        poll_interval: float = 1.0,
        timeout: float = 1800.0,
        since: int = 0,
    ) -> None:
        """等待对话运行完成。

        该方法通过WebSocket监听终端状态事件来等待运行完成。 这确保所有事件在返回之前
        被交付，避免了竞态条件中轮询看到“完成”状态而WebSocket在交付
        最终事件之前就看到的情况。

        与回退方案一样，它也会定期轮询服务器。 如果 WebSocket 延迟或断开，轮询仍会立
        即出现 ERROR/STUCK。 仅 REST 的 FINISHED
         状态并不具有权威性，因为在服务器端运行任务退出之前，停止挂钩仍然可以将其恢复
         为 RUNNING。

        Args:
            poll_interval: 状态轮询之间的时间（以秒为单位）(回退方案)。
            timeout: 等待的最长时间（以秒为单位）。

        Raises:
            ConversationRunError: 如果运行失败，对话就会消失，
                或者等待超时。 重试瞬时网络错误、429 和 5xx 响应，直到超时。
        """
        start_time = time.monotonic()
        terminal_poll_count = 0
        # 在没有运行后 WS 快照的情况下进行如此多次连续的 REST 终端轮询后记录警告。 这是
        # 一个健康信号，而不是返回路径——立即返回 REST FINISHED 将重新引入停钩比赛。
        #
        TERMINAL_POLL_WARNING_THRESHOLD = 3
        # 时间戳硬回退方案：在服务器报告终端至少 REST 秒内没有运行后 WS 拍照的情况下，接
        # 受终端状态。 停止钩子速度快（秒）；无论poll_interval如何，30 秒都是一个安全范
        # 围。 这可以防止在 WS 快照从未传递时无限期挂起（e.g.，在服务器上运行完成后套接
        # 字被丢弃）。
        #
        TERMINAL_HARD_FALLBACK_SECS = 30.0
        terminal_first_seen_at: float | None = None

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > timeout:
                raise ConversationRunError(
                    self._id,
                    TimeoutError(
                        f"Run timed out after {timeout} seconds. "
                        "The conversation may still be running on the server."
                    ),
                )

            # 等待：
            # 1. WebSocket 发出运行完成信号
            # 2. 轮询间隔到期（下降到 REST 轮询）
            try:
                ws_status = self._terminal_status_queue.get(timeout=poll_interval)
                # 在 ERROR/STUCK 上加注 ConversationRunError； 否则不进行任何操作。
                self._handle_conversation_status(ws_status, since)
                logger.info(
                    "Run completed via post-run WebSocket state update "
                    "(status: %s, elapsed: %.1fs)",
                    ws_status,
                    elapsed,
                )
                # 服务器发布完整 ConversationStateUpdateEvent 之后 conversation.run()
                # /arun() 退出和待处理事件被刷新，因此，该快照中的非运行状态是权威的完成
                # 信号。
                #
                self._state.events.reconcile()
                return
            except Empty:
                pass  # Queue.get() 超时，进入 REST 轮询

            # 轮询服务器的状态作为健康检查和回退方案。 这捕获需要立即关注的 ERROR/STUCK
            # 状态，并在 WebSocket 延迟/断开连接时提供回退方案。
            #
            try:
                status = self._poll_status_once()
            except Exception as exc:
                self._handle_poll_exception(exc)
                # 错误重置：我们无法确认轮询失败后服务器是否仍处于终端状态，因此保守地重
                # 新启动硬回退方案计时器。 在轮询在终止和异常之间交替的退化情况下，30 秒
                # 的阈值会滑动； 这是有意为之的——我们更喜欢False负等待而不是False正提前
                # 返回。
                #
                terminal_poll_count = 0
                terminal_first_seen_at = None
            else:
                # 针对 ERROR/STUCK 状态提高 ConversationRunError
                self._handle_conversation_status(status, since)

                if status and ConversationExecutionStatus(status).is_terminal():
                    # ERROR/STUCK上面已经处理过了。 REST 中的 FINISHED 是建议性的，因为
                    # stop hooks 仍然可以否决它； 更喜欢等待服务器的运行后 WebSocket 状
                    # 态更新。
                    #
                    terminal_poll_count += 1
                    now = time.monotonic()
                    if terminal_first_seen_at is None:
                        terminal_first_seen_at = now
                    if terminal_poll_count == TERMINAL_POLL_WARNING_THRESHOLD:
                        logger.warning(
                            "REST has reported terminal status %s for %d polls "
                            "without a post-run WebSocket snapshot; continuing "
                            "to wait for the authoritative snapshot "
                            "(elapsed: %.1fs)",
                            status,
                            terminal_poll_count,
                            elapsed,
                        )
                    terminal_secs = now - terminal_first_seen_at
                    if terminal_secs >= TERMINAL_HARD_FALLBACK_SECS:
                        logger.warning(
                            "REST has reported terminal status %s for %.0fs "
                            "with no post-run WebSocket snapshot; accepting as "
                            "final to avoid an indefinite hang (elapsed: %.1fs). "
                            "This may indicate a WebSocket delivery issue.",
                            status,
                            terminal_secs,
                            elapsed,
                        )
                        self._state.refresh_from_server()
                        self._state.events.reconcile()
                        return
                else:
                    terminal_poll_count = 0
                    terminal_first_seen_at = None

    def _drain_terminal_status_queue(self) -> None:
        """清空 WS 终端状态提示队列。

        在 run() 开始时（启动前）调用，以丢弃上一次运行调用留下的任何陈旧信号。
        """
        while True:
            try:
                self._terminal_status_queue.get_nowait()
            except Empty:
                break

    def _poll_status_once(self) -> str | None:
        """从远程会话中获取当前执行状态。"""
        resp = _send_request(
            self._client,
            "GET",
            f"{CONVERSATIONS_PATH}/{self._id}",
            timeout=30,
        )
        info = resp.json()
        return info.get("execution_status")

    def _handle_conversation_status(self, status: str | None, since: int = 0) -> bool:
        """处理非运行状态； 如果运行完成则返回 True。"""
        if status == ConversationExecutionStatus.RUNNING.value:
            return False
        if status == ConversationExecutionStatus.ERROR.value:
            self._state.events.reconcile()
            error = self._get_last_conversation_error(since)
            detail = (
                f"{error.code}: {error.detail}".strip(": ")
                if error
                else "Remote conversation ended with error"
            )
            raise ConversationRunError(
                self._id, RuntimeError(detail), conversation_error=error
            )
        if status == ConversationExecutionStatus.STUCK.value:
            raise ConversationRunError(
                self._id,
                RuntimeError("Remote conversation got stuck"),
            )
        return True

    def _handle_poll_exception(self, exc: Exception) -> None:
        """将轮询异常分为可重试失败和终端失败。"""
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code
            reason = exc.response.reason_phrase
            if status_code == 404:
                raise ConversationRunError(
                    self._id,
                    RuntimeError(
                        "Remote conversation not found (404). "
                        "The runtime may have been deleted."
                    ),
                ) from exc
            if 400 <= status_code < 500 and status_code != 429:
                raise ConversationRunError(
                    self._id,
                    RuntimeError(f"Polling failed with HTTP {status_code} {reason}"),
                ) from exc
            logger.warning(
                "Error polling status (will retry): HTTP %d %s",
                status_code,
                reason,
            )
            return
        if isinstance(exc, httpx.RequestError):
            logger.warning(f"Error polling status (will retry): {exc}")
            return
        raise ConversationRunError(self._id, exc) from exc

    def _get_last_conversation_error(
        self, since: int = 0
    ) -> ConversationErrorEvent | None:
        """返回最近的结构化对话错误（如果有）。"""
        events = self._state.events
        for idx in range(len(events) - 1, since - 1, -1):
            event = events[idx]
            if isinstance(event, ConversationErrorEvent):
                return event
        return None

    def set_confirmation_policy(self, policy: ConfirmationPolicyBase) -> None:
        payload = {"policy": policy.model_dump()}
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/confirmation_policy",
            json=payload,
        )

    def set_security_analyzer(self, analyzer: SecurityAnalyzerBase | None) -> None:
        """设置远程会话的安全分析器。"""
        payload = {
            "security_analyzer": analyzer.model_dump(mode="json")
            if analyzer
            else analyzer
        }
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/security_analyzer",
            json=payload,
        )

    def reject_pending_actions(self, reason: str = "User rejected the action") -> None:
        # 相当于拒绝确认：暂停
        _send_request(
            self._client,
            "POST",
            (f"{CONVERSATIONS_PATH}/{self._id}/events/respond_to_confirmation"),
            json={"accept": False, "reason": reason},
        )

    def pause(self) -> None:
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/pause",
        )

    def interrupt(self) -> None:
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/interrupt",
        )

    def load_plugin(self, plugin_ref: str) -> None:
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/load_plugin",
            json={"plugin_ref": plugin_ref},
        )

    def update_secrets(self, secrets: Mapping[str, SecretValue]) -> None:
        from openhands.sdk.secret.secrets import SecretSource

        serializable_secrets: dict[str, str | dict] = {}
        for key, value in secrets.items():
            if isinstance(value, SecretSource):
                # Pydantic 模型→带有服务器“种类”鉴别器的字典。
                # expose_secrets=True prevents SecretStr fields (e.g. header
                # 值）在序列化期间不再为已脱敏。
                serializable_secrets[key] = value.model_dump(
                    mode="json", context={"expose_secrets": True}
                )
            elif callable(value):
                serializable_secrets[key] = value()
            else:
                serializable_secrets[key] = value

        payload = {"secrets": serializable_secrets}
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/secrets",
            json=payload,
        )

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
        # 对于远程对话，委托给服务器端点
        payload = {"question": question}

        resp = _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/ask_agent",
            json=payload,
        )
        data = resp.json()
        return data["response"]

    def set_title(self, title: str) -> None:
        """设置已持久化显示标题而不运行智能体。"""
        _send_request(
            self._client,
            "PATCH",
            f"{CONVERSATIONS_PATH}/{self._id}",
            json={"title": title},
        )

    @observe(
        name="conversation.generate_title",
        ignore_inputs=["llm"],
        metadata={OPERATION_METADATA_KEY: "title_generation"},
    )
    def generate_title(self, llm: LLM | None = None, max_length: int = 50) -> str:
        """根据第一条用户消息生成对话标题。

        Args:
            llm: 可选 LLM 用于标题生成。 如果没有提供，
                 使用智能体的 LLM。
            max_length: 生成的标题的最大长度。

        Returns:
            为对话生成的标题。
        """
        # 在读取状态之前进行协调，以便最近发布的用户消息可见，即使它们是在上次同步和此调
        # 用之间到达的。
        #
        self._state.events.reconcile()

        effective_llm = llm if llm is not None else self.agent.llm
        return generate_conversation_title(
            events=self._state.events, llm=effective_llm, max_length=max_length
        )

    def condense(self) -> None:
        """强制对话历史记录上下文压缩。

        此方法向远程 Agent Server 发送上下文压缩请求。 如果配置了上下文压缩器并处理上
        下文压缩请求，服务器将使用现有的上下文压缩请求模式来触发上下文压
        缩。

        上下文压缩将应用于服务器端，并将通过向历史记录添加上下文压缩事件来修改对话状
        态。

        Raises:
            HTTPError: 如果服务器返回错误（e.g.，未配置上下文压缩器）。
        """
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/condense",
        )

    def fork(
        self,
        *,
        conversation_id: "ConversationID | None" = None,
        agent: "AgentBase | None" = None,
        title: str | None = None,
        tags: dict[str, str] | None = None,
        reset_metrics: bool = True,
        from_event_id: EventID | None = None,
    ) -> "RemoteConversation":
        """在远程 Agent Server 上分叉此对话。

        向服务器发送一个分叉请求，深度复制事件和状态。 返回一个指向叉子的新
        ``RemoteConversation``。

        Args:
            conversation_id: 分叉对话的 ID（自动生成
                如果 ``None``，则在服务器上）。
            agent: **不支持远程对话。**通过一个
                非 ``None`` 值提高 ``NotImplementedError``。 使用
                ``LocalConversation.fork(agent=...)`` 用于智能体替换。
            title: 分叉对话的可选标题。
            tags: 分叉对话的可选标签。
            reset_metrics: 如果 ``True``（默认），成本/代币统计开始
                新鲜的在叉子上。
            from_event_id: 如果设置，则仅分叉直到并包括该分支的分支
                事件（``path_to_root``）并在那里设置叉子的HEAD。 如果
                ``None``（默认），复制整个对话。

        Returns:
            由分叉的服务器端对话支持的新 ``RemoteConversation``。

        Raises:
            NotImplementedError: 如果提供``agent``。
            httpx.HTTPStatusError：如果服务器拒绝请求（e.g.404
                对于未知的``from_event_id``）。
        """
        if agent is not None:
            raise NotImplementedError(
                "Agent replacement is not supported for remote conversation "
                "forks. Use LocalConversation.fork(agent=...) instead."
            )

        body: dict[str, object] = {"reset_metrics": reset_metrics}
        if conversation_id is not None:
            body["id"] = str(conversation_id)
        if title is not None:
            body["title"] = title
        if tags is not None:
            body["tags"] = tags
        if from_event_id is not None:
            body["from_event_id"] = from_event_id

        resp = _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/fork",
            json=body,
        )
        fork_info = resp.json()
        fork_uuid = uuid.UUID(fork_info["id"])

        agent_cls = type(self.agent)
        fork_agent = agent_cls.model_validate(
            self.agent.model_dump(context={"expose_secrets": True}),
        )

        server_tags: dict[str, str] | None = fork_info.get("tags") or None

        return RemoteConversation(
            agent=fork_agent,
            workspace=self.workspace,
            conversation_id=fork_uuid,
            max_iteration_per_run=self.max_iteration_per_run,
            delete_on_close=self.delete_on_close,
            tags=server_tags,
        )

    def navigate_to(self, event_id: EventID | None) -> None:
        """将对话 HEAD 移至远程服务器上的现有事件。

        发布到服务器的 ``/navigate`` 路由，这将活动分支重新定位到位（没有新对话）。
        缓存的状态被刷新，因此后续的 ``state`` 读取反映了新的
         HEAD - ``leaf_event_id`` 不会通过 WebSocket 广播。

        Args:
            event_id: 为空树创建新的 HEAD 或 ``None`` 的事件。

        Raises:
            httpx.HTTPStatusError：如果服务器拒绝事件ID（e.g。404
                对于未知事件）。
        """
        _send_request(
            self._client,
            "POST",
            f"{CONVERSATIONS_PATH}/{self._id}/navigate",
            json={"event_id": event_id},
        )
        self._state.refresh_from_server()

    def execute_tool(self, tool_name: str, action: "Action") -> "Observation":
        """直接执行工具，无需经过智能体循环。

        Note: RemoteConversation 尚不支持此方法。
        在正常的智能体循环期间，远程对话的工具执行发生在服务器端。

        Args:
            tool_name: 要执行的工具的名称
            action: 传递给工具执行器的操作

        Raises:
            NotImplementedError: 始终如此，因为尚不支持此功能
                for remote conversations.
        """
        raise NotImplementedError(
            "execute_tool is not yet supported for RemoteConversation. "
            "Tool execution for remote conversations happens on the server side "
            "during the normal agent loop. Use LocalConversation for direct "
            "tool execution."
        )

    def close(self) -> None:
        """关闭对话并清理资源。

        Note: 我们在这里不关闭 self._client，因为它与工作区共享。
        工作区拥有该客户端，并将在其自己的清理过程中关闭它。 在此处关闭它会阻止工作区
        进行清理 API 调用。
        """
        if self._cleanup_complete:
            return
        first_attempt = not self._cleanup_initiated
        if first_attempt:
            self._cleanup_initiated = True

            # 尽力而为：将累积的 LLM 成本交给工作区，以便将其包含在自动化完成回调中。 仅
            # 读取缓存状态 - close() 也在故障路径上运行，其中实时获取可能会阻塞，直到超
            # 时针对已经消失的 Agent Server。 缓存记录了这次运行：Agent Server流在每次
            # LLM响应后更新“统计”信息（EventService._setup_stats_streaming），因此即使在
            # 失败路径上也持有运行的花费，run()在运行结束后从每字段ERROR/STUCK更新中唤醒
            # 。
            #
            try:
                cached = self._state._cached_state
                # 需要一个实际的“统计”条目：仅根据部分字段更新构建的缓存 - e.g。 对于没
                # 有实时对话的服务，订阅时间推送将产生 0.0 并记录为免费，而其实际成本只
                # 是未知。
                #
                if cached is not None and "stats" in cached:
                    cost = self._state.stats.get_combined_metrics().accumulated_cost
                    self.workspace.register_cost(cost)
            except Exception as e:
                logger.debug(f"Could not register accumulated cost: {e}")

            # SessionEnd 挂钩在服务器端执行（通过载荷中的 hook_config）。
            try:
                # 停止 WebSocket 客户端（如果存在）
                if self._ws_client:
                    self._ws_client.stop()
                    self._ws_client = None
            except Exception:
                pass

            self._end_observability_span()
            if self.delete_on_close:
                try:
                    # 触发服务器端delete_conversation释放资源，如tmux会话
                    #
                    _send_request(
                        self._client,
                        "DELETE",
                        f"{CONVERSATIONS_PATH}/{self.id}",
                    )
                except Exception:
                    pass
        self._cleanup_complete = True

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
