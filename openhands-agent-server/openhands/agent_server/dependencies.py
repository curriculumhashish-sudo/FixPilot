from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.security import APIKeyCookie, APIKeyHeader
from pydantic import TypeAdapter, ValidationError

from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.config import Config
from openhands.agent_server.conversation_registry import ConversationRegistry
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.event_service import EventService


# 用于验证工作区静态文件路由的 Cookie 名称。 故意与头部名称不同：cookie 仅被工作区路由器
# （因此如果帧/ <img> 可以加载工作区文件）接受，但被其他所有 API 端点拒绝。
#
WORKSPACE_SESSION_COOKIE_NAME = "oh_workspace_session_key"

_SESSION_API_KEY_HEADER = APIKeyHeader(name="X-Session-API-Key", auto_error=False)
_WORKSPACE_SESSION_COOKIE = APIKeyCookie(
    name=WORKSPACE_SESSION_COOKIE_NAME, auto_error=False
)


def check_session_api_key(
    request: Request,
    session_api_key: str | None = Depends(_SESSION_API_KEY_HEADER),
) -> None:
    """如果提供的密钥不在当前会话密钥中，则拒绝请求。

    在请求时从``request.app.state.config``读取``session_api_keys``，以便通过
    ``POST /api/init``传递的密
    钥立即生效，而无需重新启动服务器或重新注册路由。
    """
    config: Config = request.app.state.config
    if config.session_api_keys and session_api_key not in config.session_api_keys:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)


def check_workspace_session(
    request: Request,
    header_key: str | None = Depends(_SESSION_API_KEY_HEADER),
    cookie_key: str | None = Depends(_WORKSPACE_SESSION_COOKIE),
) -> None:
    """工作区静态文件路由的身份验证依赖项。

    接受 EITHER 标准 ``X-Session-API-Key`` 标头或
    ``oh_workspace_session_key`` cookie（由
    ``POST /api/auth/workspace-session``). cookie 是必需的，因为浏览器无法将自定义标
    头附加到
    ``<iframe src>`` 或 ``<img src>`` 请求，这就是画布前端嵌入工作区工件的方式。
    cookie 的作用域被特意限定为仅此路由器； 没有其
    他端点尊重它。
    """
    config: Config = request.app.state.config
    if not config.session_api_keys:
        return
    for candidate in (header_key, cookie_key):
        if candidate and candidate in config.session_api_keys:
            return
    raise HTTPException(status.HTTP_401_UNAUTHORIZED)


def get_conversation_service(request: Request) -> ConversationService:
    service = getattr(request.app.state, "conversation_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation service is not available",
        )
    return service


async def get_bash_event_service(request: Request) -> BashEventService:
    if "runtime_conversation_id" in request.path_params:
        event_service: EventService | None = getattr(
            request.state, "runtime_event_service", None
        )
        if event_service is None:
            # 当路由器依赖项 bind_local_conversation_runtime 失败验证时，FastAPI 仍然解
            # 决此依赖项，因此报告验证错误，而不是读取它从未设置的状态。
            #
            raw_id = request.path_params["runtime_conversation_id"]
            try:
                TypeAdapter(UUID).validate_python(raw_id)
            except ValidationError as exc:
                raise RequestValidationError(
                    [
                        {**error, "loc": ("path", "runtime_conversation_id")}
                        for error in exc.errors(include_url=False)
                    ]
                ) from exc
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "Conversation runtime is not bound",
            )
        if event_service.bash_event_service is None:
            event_service.bash_event_service = BashEventService(
                bash_events_dir=event_service.conversation_dir / "bash_events",
                default_cwd=event_service.get_conversation().workspace.working_dir,
            )
        return event_service.bash_event_service
    service = getattr(request.app.state, "bash_event_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bash event service is not available",
        )
    return service


async def get_event_service(
    conversation_id: UUID,
    request: Request,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> EventService:
    registry = getattr(request.app.state, "conversation_registry", None)
    if isinstance(
        registry, ConversationRegistry
    ) and registry.serves_persisted_event_reads(conversation_id):
        event_service = await conversation_service.get_persisted_event_service(
            conversation_id
        )
    else:
        event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found: {conversation_id}",
        )
    return event_service
