"""CORS中间件为Agent Server。

``CORSDispatcher`` 根据路径将请求路由到两个 CORS 配置之一：

* 工作区 cookie 端点（``/api/auth/workspace-session`` 和
  ``/api/conversations/{id}/workspace/*``) — 通配符 CORS，在每个响应上回显请求来源。
  这些是唯一通过环境 (cookie)
   进行身份验证的路由凭据。
* 其他一切 - ``LocalhostCORSMiddleware``，尊重操作员的 ``allow_cors_origins`` /
``allow_cors_origin_regex`` 并始终允许 localhost 和 ``DOCKER_HOST_ADDR``（匹配
OpenHands/
OpenHands#4624 意图）。
"""

import os
import re
from urllib.parse import urlparse

from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send


_WORKSPACE_SESSION_PATH = "/api/auth/workspace-session"
_WORKSPACE_STATIC_RE = re.compile(r"^/api/conversations/[^/]+/workspace(/|$)")


def _is_workspace_cookie_path(path: str) -> bool:
    if path == _WORKSPACE_SESSION_PATH:
        return True
    return bool(_WORKSPACE_STATIC_RE.match(path))


class LocalhostCORSMiddleware(CORSMiddleware):
    """``CORSMiddleware`` 始终允许 localhost 和 ``DOCKER_HOST_ADDR``。"""

    def __init__(
        self,
        app: ASGIApp,
        allow_origins: list[str],
        allow_origin_regex: str | None = None,
    ) -> None:
        super().__init__(
            app,
            allow_origins=allow_origins,
            allow_origin_regex=allow_origin_regex,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def is_allowed_origin(self, origin: str) -> bool:
        if origin:
            hostname = urlparse(origin).hostname or ""
            if hostname in ("localhost", "127.0.0.1"):
                return True
            docker_host_addr = os.environ.get("DOCKER_HOST_ADDR")
            if docker_host_addr and hostname == docker_host_addr:
                return True
        return bool(super().is_allowed_origin(origin))


class CORSDispatcher:
    """将每个请求分派到工作区或默认 CORS 中间件。

    工作区分支使用 ``allow_origin_regex=r"https?://.+"`` 而不是
    ``allow_origins=["*"]`` 有两个原因：

    1. Starlette 在简单响应时发出文字 ``*``
       设置了 ``allow_all_origins`` 并且请求没有 ``Cookie`` 标头 — 浏览器会拒绝该标头
       ``Access-Control-Allow-Credentials: true``. 正则表达式路径始终与请求 Origin 相
       呼应（带有
       ``Vary: Origin``）。
    2. ``http(s)://``锚定排除了``Origin: null``（如果沙盒化，``data:`` / ``blob:``
    URLs）这些没有定义CHIP
    S分区键的非法客户端。
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allow_origins: list[str],
        allow_origin_regex: str | None = None,
    ) -> None:
        self._default_cors = LocalhostCORSMiddleware(
            app,
            allow_origins=list(allow_origins),
            allow_origin_regex=allow_origin_regex,
        )
        self._workspace_cors = CORSMiddleware(
            app,
            allow_origin_regex=r"https?://.+",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "http":
            # 剥离 FastAPI ``root_path``，以便调度在安装在子路径下的反向代理后面工作。
            #
            root_path = scope.get("root_path", "")
            path = scope.get("path", "/")
            route_path = path.removeprefix(root_path) if root_path else path
            if _is_workspace_cookie_path(route_path or "/"):
                await self._workspace_cors(scope, receive, send)
                return
        await self._default_cors(scope, receive, send)
