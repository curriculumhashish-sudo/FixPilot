"""HTTP 和 WebSocket 拥有 Canvas 应用程序后端的入口。"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, WebSocket

from openhands.agent_server.canvas_extensions.bridge import (
    AppBackendSessionResponse,
    create_app_backend_session,
    delete_app_backend_session,
    proxy_app_backend_http,
    proxy_app_backend_websocket,
)
from openhands.agent_server.canvas_extensions_router import (
    CANVAS_EXTENSION_NAME_PATTERN,
)
from openhands.agent_server.dependencies import check_session_api_key


app_backend_bridge_router = APIRouter(tags=["Canvas App Backends"])
AppBackendNamePath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=255,
        pattern=CANVAS_EXTENSION_NAME_PATTERN,
        description="Installed Canvas App name",
    ),
]


@app_backend_bridge_router.post(
    "/app-backends/{extension_name}/session",
    response_model=AppBackendSessionResponse,
    dependencies=[Depends(check_session_api_key)],
    responses={
        401: {"description": "Missing or invalid X-Session-API-Key header"},
        403: {"description": "Origin is not allowed"},
        409: {"description": "Ingress does not use a separate browser origin"},
        503: {"description": "Backend is unavailable or ingress is not configured"},
    },
)
async def create_app_backend_session_endpoint(
    extension_name: AppBackendNamePath,
    request: Request,
    response: Response,
) -> AppBackendSessionResponse:
    """为一个就绪的应用程序后端发出一个短暂的 HttpOnly 会话。

    使用正常的方式在配置的应用程序入口源上调用此端点
    ``X-Session-API-Key`` 控制标头和 Canvas 页面的 ``Origin``。 返回的入口 URL 不包含
    凭据。 调用者必须保留cookies
    （``credentials: include``）； 第三方 iframe 部署需要 HTTPS 和浏览器对分区 cookie
     的支持。
    """
    return await create_app_backend_session(request, response, extension_name)


@app_backend_bridge_router.delete(
    "/app-backends/{extension_name}/session",
    status_code=204,
    dependencies=[Depends(check_session_api_key)],
    responses={
        204: {"description": "Browser session revoked and cookie cleared"},
        401: {"description": "Missing or invalid X-Session-API-Key header"},
        403: {"description": "Origin is not allowed"},
    },
)
async def delete_app_backend_session_endpoint(
    extension_name: AppBackendNamePath,
    request: Request,
    response: Response,
) -> Response:
    """撤销当前应用程序范围的浏览器会话。"""
    await delete_app_backend_session(request, response, extension_name)
    response.status_code = 204
    return response


# 根路由没有 ``{path}`` 段，因此它们不采用 ``path`` 参数：FastAPI 将从 ``?path=`` 查询参
# 数绑定它。
#
@app_backend_bridge_router.api_route(
    "/app-backends/{extension_name}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy_app_backend_http_root_endpoint(
    extension_name: AppBackendNamePath,
    request: Request,
) -> Response:
    return await proxy_app_backend_http(request, extension_name, "")


@app_backend_bridge_router.api_route(
    "/app-backends/{extension_name}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def proxy_app_backend_http_endpoint(
    extension_name: AppBackendNamePath,
    request: Request,
    path: str,
) -> Response:
    return await proxy_app_backend_http(request, extension_name, path)


@app_backend_bridge_router.websocket("/app-backends/{extension_name}")
async def proxy_app_backend_websocket_root_endpoint(
    extension_name: AppBackendNamePath,
    websocket: WebSocket,
) -> None:
    await proxy_app_backend_websocket(websocket, extension_name, "")


@app_backend_bridge_router.websocket("/app-backends/{extension_name}/{path:path}")
async def proxy_app_backend_websocket_endpoint(
    extension_name: AppBackendNamePath,
    websocket: WebSocket,
    path: str,
) -> None:
    await proxy_app_backend_websocket(websocket, extension_name, path)
