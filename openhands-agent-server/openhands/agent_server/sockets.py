"""
WebSocket 端点代表 OpenHands SDK。

这些端点与主 API 路由分开，以处理 WebSocket 特定的身份验证。 支持三种身份验证方法（优
先级从高到低）：

1. **First-message auth**（推荐）：客户端发送
   ``{"type": "auth", "session_api_key": "..."}`` 作为连接打开后的第一个 WebSocket 帧
   。 这样就把 token
   从 URLs 中排除，因此也排除了反向代理/负载均衡访问日志。
2. 查询参数 ``session_api_key`` — 已弃用，保留用于向后兼容。
3. ``X-Session-API-Key`` 标头 — 适用于非浏览器客户端。
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from starlette.websockets import WebSocketState

from openhands.agent_server.bash_service import (
    BashEventService,
    get_default_bash_event_service,
)
from openhands.agent_server.config import Config, get_default_config
from openhands.agent_server.conversation_service import (
    ConversationService,
    CredentialBindingActivationRequired,
    get_default_conversation_service,
)
from openhands.agent_server.event_router import normalize_datetime_to_server_timezone
from openhands.agent_server.models import (
    BashError,
    BashEventBase,
    BashOutput,
    ExecuteBashRequest,
    ServerErrorEvent,
)
from openhands.agent_server.pub_sub import MaxSubscribersError, Subscriber
from openhands.sdk import Event, Message
from openhands.sdk.utils.paging import page_iterator


conversation_sockets_router = APIRouter(prefix="/sockets", tags=["WebSockets"])
bash_sockets_router = APIRouter(prefix="/sockets", tags=["WebSockets"])
conversation_service = get_default_conversation_service()
bash_event_service = get_default_bash_event_service()
logger = logging.getLogger(__name__)


def _get_config(websocket: WebSocket) -> Config:
    """返回与此 FastAPI 应用程序实例关联的配置。

    这确保了 WebSocket auth遵循与身份验证相同的配置 REST  API when the Agent Server
    被用作库（）e.g., 测试或被 m
    ount 到另一个上 FastAPI 而不是总是读取环境默认值。
    """
    config = getattr(websocket.app.state, "config", None)
    if isinstance(config, Config):
        return config
    return get_default_config()


def _get_conversation_service(websocket: WebSocket) -> ConversationService:
    """返回此 FastAPI 应用程序实例的 ConversationService。

    在请求时查找 ``app.state.conversation_service``，以便使用 ``POST /api/init``（延
    迟初始化/休眠模式）提供的服务
    ，而不是导入时捕获的模块级默认值。 当
    ``app.state`` 未配置（e.g. 当 sockets.py 作为库导入而没有生命周期时，会回退到模块
    级别的单例，该单例保持现有测试对模块级别变量的pat
    ch行为。
    """
    service = getattr(websocket.app.state, "conversation_service", None)
    if isinstance(service, ConversationService):
        return service
    return conversation_service


def _get_bash_event_service(websocket: WebSocket) -> BashEventService:
    """返回此 FastAPI 应用程序实例的 BashEventService。

    在请求时查找 ``app.state.bash_event_service``，以便使用 ``POST /api/init``（延迟
    初始化/休眠模式）提供的服务，而
    不是导入时捕获的模块级默认值。 当
    ``app.state`` 未配置（e.g. 当sockets.py作为没有生命周期的库导入时），回退到模块级
    单例。
    """
    service = getattr(websocket.app.state, "bash_event_service", None)
    if isinstance(service, BashEventService):
        return service
    return bash_event_service


def _resolve_websocket_session_api_key(
    websocket: WebSocket,
    session_api_key: str | None,
) -> str | None:
    """解析来自多个源的会话 API 密钥。

    优先顺序（从高到低）：
    1. 查询参数 (session_api_key) - 用于浏览器兼容性
    2. X-Session-API-Key 标头 - 用于非浏览器客户端

    如果任何源中均未提供密钥，则返回 None。
    """
    if session_api_key is not None:
        return session_api_key

    header_key = websocket.headers.get("x-session-api-key")
    if header_key is not None:
        return header_key

    return None


# 连接打开后，给客户端 10 秒的时间发送身份验证帧。 这可以在安全性（不要无限期地保持连接
# ）与适应慢速网络和客户端启动时间之间取得平衡。
#
_FIRST_MESSAGE_AUTH_TIMEOUT_SECONDS = 10


async def _accept_authenticated_websocket(
    websocket: WebSocket,
    session_api_key: str | None,
) -> bool:
    """验证并接受套接字，或因验证错误而关闭。

    按以下顺序尝试身份验证：

    1. 查询参数/标头（旧版，已弃用）。
    2. 第一条消息身份验证 — 客户端发送
       ``{"type": "auth", "session_api_key": "..."}`` 作为第一帧。

    在尝试第一条消息身份验证之前，WebSocket 始终被 * 接受 *，因为在读取任何帧之前，原
    始 WebSocket 需要 ``accept()``。
    """
    config = _get_config(websocket)
    resolved_key = _resolve_websocket_session_api_key(websocket, session_api_key)

    # 未配置身份验证 - 无条件接受。
    if not config.session_api_keys:
        await websocket.accept()
        return True

    # 旧路径：通过查询参数或标头提供的密钥。
    if resolved_key is not None:
        if resolved_key and resolved_key in config.session_api_keys:
            logger.warning(
                "session_api_key passed via query param or header is deprecated. "
                "Use first-message auth instead."
            )
            await websocket.accept()
            return True
        logger.warning("WebSocket authentication failed: invalid API key")
        await websocket.close(code=4001, reason="Authentication failed")
        return False

    # 首次认证：我们必须 accept() 在读取帧之前 WebSocket 协议要求握手先完成。 上述老路径
    # 可以拒绝 *之前* 接受（对未接受的套接字发送） HTTP 403风格的响应，但我们需要读取一
    # 个帧。
    #
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=_FIRST_MESSAGE_AUTH_TIMEOUT_SECONDS,
        )
        data = json.loads(raw)
    except TimeoutError:
        logger.warning(
            "WebSocket first-message auth failed: timeout waiting for auth frame"
        )
        await _safe_close_websocket(
            websocket, code=4001, reason="Authentication failed"
        )
        return False
    except json.JSONDecodeError:
        logger.warning("WebSocket first-message auth failed: malformed JSON")
        await _safe_close_websocket(
            websocket, code=4001, reason="Authentication failed"
        )
        return False
    except WebSocketDisconnect:
        logger.warning("WebSocket first-message auth failed: client disconnected")
        await _safe_close_websocket(
            websocket, code=4001, reason="Authentication failed"
        )
        return False

    if not isinstance(data, dict):
        logger.warning(
            "WebSocket first-message auth failed: payload is not a JSON object"
        )
        await _safe_close_websocket(
            websocket, code=4001, reason="Authentication failed"
        )
        return False
    if data.get("type") != "auth":
        logger.warning("WebSocket first-message auth failed: wrong message type")
        await _safe_close_websocket(
            websocket, code=4001, reason="Authentication failed"
        )
        return False
    presented_key = data.get("session_api_key")
    if not presented_key or presented_key not in config.session_api_keys:
        logger.warning("WebSocket first-message auth failed: invalid API key")
        await _safe_close_websocket(
            websocket, code=4001, reason="Authentication failed"
        )
        return False

    logger.info("WebSocket authenticated via first-message auth")
    return True


@conversation_sockets_router.websocket("/events/{conversation_id}")
async def events_socket(
    conversation_id: UUID,
    websocket: WebSocket,
    session_api_key: Annotated[str | None, Query(alias="session_api_key")] = None,
    resend_mode: Annotated[
        Literal["all", "since"] | None,
        Query(
            description=(
                "Mode for resending historical events on connect. "
                "'all' sends all events, 'since' sends events after 'after_timestamp'."
            )
        ),
    ] = None,
    after_timestamp: Annotated[
        datetime | None,
        Query(
            description=(
                "Required when resend_mode='since'. Events with timestamp >= this "
                "value will be sent. Accepts ISO 8601 format. Timezone-aware "
                "datetimes are converted to server local time; naive datetimes "
                "assumed in server timezone."
            )
        ),
    ] = None,
    # 已弃用参数 - 保留为向后兼容性
    resend_all: Annotated[
        bool,
        Query(
            include_in_schema=False,
            deprecated=True,
        ),
    ] = False,
):
    """WebSocket 端点用于对话事件。

    Args:
        conversation_id: 要订阅的对话 ID。
        websocket: WebSocket 连接。
        session_api_key: 身份验证的可选 API 键。
        resend_mode: 连接时重新发送历史事件的模式。
            - 'all'：重新发送所有现有事件
            - 'since'：在“after_timestamp”之后重新发送事件（需要 after_timestamp）
            - None: 不重新发送，仅订阅新事件
        after_timestamp: 当 resend_mode='since' 时为必填项。 活动与
            时间戳 >= 将发送该值。 时间戳以服务器本地时间解释。 时区感知的日期时间将
            转换为服务器时区。 实现高效的双向加载，其中 REST 获取历史事件，
            WebSocket 处理特定点之后的事件。
        resend_all: DEPRECATED. 使用 resend_mode='all' 代替。 保留用于
            向后兼容性 - 如果 True 且 resend_mode 为 None，则表现为 resend_mode='all'
            。
    """
    if not await _accept_authenticated_websocket(websocket, session_api_key):
        return

    logger.info(f"Event Websocket Connected: {conversation_id}")
    conv_service = _get_conversation_service(websocket)
    try:
        event_service = await conv_service.get_event_service(conversation_id)
    except CredentialBindingActivationRequired:
        await websocket.close(
            code=1013,
            reason="credential_binding_activation_required",
        )
        return
    if event_service is None:
        logger.warning(f"Converation not found: {conversation_id}")
        await websocket.close(code=4004, reason="Conversation not found")
        return

    try:
        subscriber_id = await event_service.subscribe_to_events(
            _WebSocketSubscriber(websocket)
        )
    except MaxSubscribersError:
        logger.warning(f"Subscriber limit reached for conversation {conversation_id}")
        await websocket.close(
            code=1013, reason="Too many connections for this conversation"
        )
        return

    # 确定有效重发模式（句柄已弃用resend_all）
    effective_mode = resend_mode
    if effective_mode is None and resend_all:
        logger.warning(
            "resend_all is deprecated, use resend_mode='all' instead: "
            f"{conversation_id}"
        )
        effective_mode = "all"

    # 将时区感知的日期时间标准化为服务器时区
    normalized_after_timestamp = (
        normalize_datetime_to_server_timezone(after_timestamp)
        if after_timestamp
        else None
    )

    try:
        # 根据模式重新发送现有事件
        if effective_mode == "all":
            logger.info(f"Resending all events: {conversation_id}")
            async for event in page_iterator(event_service.search_events):
                await _send_event(event, websocket)
        elif effective_mode == "since":
            if not normalized_after_timestamp:
                logger.warning(
                    f"resend_mode='since' requires after_timestamp, "
                    f"no events will be resent: {conversation_id}"
                )
            else:
                logger.info(
                    f"Resending events since {normalized_after_timestamp}: "
                    f"{conversation_id}"
                )
                async for event in page_iterator(
                    event_service.search_events,
                    timestamp__gte=normalized_after_timestamp,
                ):
                    await _send_event(event, websocket)

        # 通过套接字监听消息
        while True:
            try:
                data = await websocket.receive_json()
                if _is_auth_control_message(data):
                    logger.debug(
                        "ignoring redundant auth control frame: %s",
                        conversation_id,
                    )
                    continue
                logger.info(f"Received message: {conversation_id}")
                message = Message.model_validate(data)
                await event_service.send_message(message, True)
            except WebSocketDisconnect:
                logger.info("Event websocket disconnected")
                return
            except Exception as e:
                # 出了问题 - 告诉客户以便他们处理
                try:
                    error_event = ServerErrorEvent(
                        source="environment",
                        code=e.__class__.__name__,
                        detail=str(e),
                    )
                    dumped = error_event.model_dump(mode="json", exclude_none=True)
                    await websocket.send_json(dumped)
                    # 之后记录 - 如果发送事件引发错误，记录将在 except 块中处理
                    #
                    logger.exception("error_in_subscription")
                except Exception:
                    # 发送错误事件失败 - 可能是关闭的套接字
                    logger.info("Event websocket disconnected")
                    logger.debug("error_sending_error")
                    await _safe_close_websocket(websocket)
                    return
    finally:
        await event_service.unsubscribe_from_events(subscriber_id)


@bash_sockets_router.websocket("/bash-events")
async def bash_events_socket(
    websocket: WebSocket,
    session_api_key: Annotated[str | None, Query(alias="session_api_key")] = None,
    resend_mode: Annotated[
        Literal["all"] | None,
        Query(
            description=(
                "Mode for resending historical events on connect. "
                "'all' sends all events."
            )
        ),
    ] = None,
    # 已弃用参数 - 保留为向后兼容性
    resend_all: Annotated[
        bool,
        Query(
            include_in_schema=False,
            deprecated=True,
        ),
    ] = False,
):
    """WebSocket 端点用于 bash 事件。

    Args:
        websocket: WebSocket 连接。
        session_api_key: 身份验证的可选 API 键。
        resend_mode: 连接时重新发送历史事件的模式。
            - 'all'：重新发送所有现有的 bash 事件
            - None: 不重新发送，仅订阅新事件
        resend_all: DEPRECATED. 使用 resend_mode='all' 代替。
    """
    if not await _accept_authenticated_websocket(websocket, session_api_key):
        return

    bash_service = _get_bash_event_service(websocket)
    logger.info("Bash Websocket Connected")
    try:
        subscriber_id = await bash_service.subscribe_to_events(
            _BashWebSocketSubscriber(websocket)
        )
    except MaxSubscribersError:
        logger.warning("Subscriber limit reached for bash events")
        await websocket.close(code=1013, reason="Too many bash event connections")
        return

    # 确定有效重发模式（句柄已弃用resend_all）
    effective_mode = resend_mode
    if effective_mode is None and resend_all:
        logger.warning("resend_all is deprecated, use resend_mode='all' instead")
        effective_mode = "all"

    try:
        # 如果需要，重新发送所有现有事件
        if effective_mode == "all":
            logger.info("Resending bash events")
            async for event in page_iterator(bash_service.search_bash_events):
                await _send_bash_event(event, websocket)

        while True:
            try:
                # 保持连接处于活动状态并处理任何传入消息
                data = await websocket.receive_json()
                if _is_auth_control_message(data):
                    continue
                logger.info("Received bash request")
                request = ExecuteBashRequest.model_validate(data)
                await bash_service.start_bash_command(request)
            except WebSocketDisconnect:
                logger.info("Bash websocket disconnected")
                return
            except Exception as e:
                try:
                    error_event = BashError(
                        code=e.__class__.__name__,
                        detail=str(e),
                    )
                    dumped = error_event.model_dump(mode="json")
                    await websocket.send_json(dumped)
                    logger.error(
                        "error_in_bash_event_subscription (error_type=%s)",
                        type(e).__name__,
                    )
                except Exception as send_error:
                    logger.info("Bash websocket disconnected")
                    logger.debug(
                        "error_sending_bash_error (error_type=%s, send_error_type=%s)",
                        type(e).__name__,
                        type(send_error).__name__,
                    )
                    await _safe_close_websocket(websocket)
                    return
    finally:
        await bash_service.unsubscribe_from_events(subscriber_id)


async def _send_event(event: Event, websocket: WebSocket):
    if not _is_websocket_connected(websocket):
        # 客户端已断开连接； pub/sub 回调正在进行清理工作。 避免由于 starlette 拒绝发送
        # 而产生的嘈杂回溯。
        #
        logger.debug("skip_sending_event_socket_disconnected: %r", event)
        return
    try:
        await websocket.send_json(event.model_dump(mode="json", exclude_none=True))
    except (RuntimeError, WebSocketDisconnect) as e:
        # 预期的竞争：客户端在我们的状态检查和发送之间断开连接。
        logger.debug("error_sending_event_disconnected: %r (%s)", event, e)
    except Exception:
        logger.exception("error_sending_event: %r", event, stack_info=True)


def _is_auth_control_message(data: object) -> bool:
    """匹配遗留身份验证后未读的冗余身份验证帧。"""
    return (
        isinstance(data, dict)
        and data.get("type") == "auth"
        and set(data) <= {"type", "session_api_key"}
    )


async def _safe_close_websocket(
    websocket: WebSocket,
    code: int = 1000,
    reason: str = "Connection closed",
):
    try:
        await websocket.close(code=code, reason=reason)
    except Exception:
        # WebSocket 可能已经关闭或处于不一致状态
        logger.debug("WebSocket close failed (may already be closed)")


def _is_websocket_connected(websocket: WebSocket) -> bool:
    """尽力检查 WebSocket 是否仍处于 CONNECTED 状态。

    如果我们尝试在 ``application_state`` 为 ``DISCONNECTED`` 的套接字上发送，
    Starlette 会引发
    ``RuntimeError('Cannot call "send" once a close message has been sent.')``。 当对
    等点离开
    后发布/订阅回调触发时，预检查可以避免嘈杂的回溯。

    当状态未知时返回 ``True`` (e.g. 使用 ``MagicMock`` 进行测试），因此调用者仍然尝试
    发送并获取原始行为。
    """
    app_state = getattr(websocket, "application_state", None)
    client_state = getattr(websocket, "client_state", None)
    if app_state is WebSocketState.DISCONNECTED:
        return False
    if client_state is WebSocketState.DISCONNECTED:
        return False
    return True


@dataclass
class _WebSocketSubscriber(Subscriber):
    """WebSocket 对话事件的订阅者。"""

    # 实时套接字就是 token 流式传输的用途。
    receives_streaming_deltas = True

    websocket: WebSocket

    async def __call__(self, event: Event):
        await _send_event(event, self.websocket)


async def _send_bash_event(event: BashEventBase, websocket: WebSocket):
    metadata: dict[str, str | int | None] = {
        "kind": event.kind,
        "event_id": str(event.id),
        "command_id": None,
        "order": None,
        "exit_code": None,
    }
    if isinstance(event, BashOutput):
        metadata.update(
            command_id=str(event.command_id),
            order=event.order,
            exit_code=event.exit_code,
        )

    if not _is_websocket_connected(websocket):
        logger.debug("skip_sending_bash_event_socket_disconnected: %s", metadata)
        return
    try:
        dumped = event.model_dump(mode="json")
        await websocket.send_json(dumped)
    except (RuntimeError, WebSocketDisconnect) as e:
        logger.debug(
            "error_sending_bash_event_disconnected: %s (error_type=%s)",
            metadata,
            type(e).__name__,
        )
    except Exception as e:
        logger.error(
            "error_sending_bash_event: %s (error_type=%s)",
            metadata,
            type(e).__name__,
            stack_info=True,
        )


@dataclass
class _BashWebSocketSubscriber(Subscriber[BashEventBase]):
    """WebSocket bash 事件的订阅者。"""

    websocket: WebSocket

    async def __call__(self, event: BashEventBase):
        await _send_bash_event(event, self.websocket)
