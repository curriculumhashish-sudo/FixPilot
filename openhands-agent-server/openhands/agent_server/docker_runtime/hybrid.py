"""从一台服务器提供主机本地和 Docker 对话。

本地路由保留其公共路径。 Docker 路由再次挂载下
当对话具有 Docker 配置清单或启动请求选择 ``conversation_runtime="docker"`` 时，
``DOCKER_ROUTE_PREFIX`` 和
：class:`RuntimeDispatchMiddleware` 会重写对它们的请求。
"""

import json
import re
from typing import Any, Final
from uuid import UUID

from fastapi import APIRouter
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from openhands.agent_server.conversation_registry import ConversationRegistry
from openhands.agent_server.docker_runtime.registry import DockerConversationRegistry
from openhands.agent_server.models import ConversationRuntimeInfo


DOCKER_ROUTE_PREFIX: Final[str] = "/_docker"

_CONVERSATION_PATH = re.compile(r"^/api/conversations/([^/]+)(/.*)?$")
_SOCKET_PATH = re.compile(r"^/sockets/(?:events|session)/([^/]+)$")


class HybridConversationRegistry(DockerConversationRegistry):
    """注册表用于运行本地会话和 Docker 会话的服务器。

    与 Docker 配置清单的对话是 Docker 对话； 其他的都是本地的。 本地路由保留其路径，
    Docker 的路径再次挂载在
    ``DOCKER_ROUTE_PREFIX`` 下。
    """

    def is_docker(self, conversation_id: UUID) -> bool:
        return self.provisioning.manifest_path(conversation_id).is_file()

    def runtime_info(self, conversation_id: UUID) -> ConversationRuntimeInfo:
        if self.is_docker(conversation_id):
            return super().runtime_info(conversation_id)
        return ConversationRegistry.runtime_info(self, conversation_id)

    def serves_persisted_event_reads(self, conversation_id: UUID) -> bool:
        return self.is_docker(conversation_id)

    def add_execution_routes(self, router: APIRouter) -> None:
        ConversationRegistry.add_execution_routes(self, router)
        docker = APIRouter(prefix=DOCKER_ROUTE_PREFIX, include_in_schema=False)
        super().add_execution_routes(docker)
        router.include_router(docker)

    @property
    def workspace_router(self) -> APIRouter:
        from openhands.agent_server.workspace_router import workspace_router

        router = APIRouter()
        router.include_router(workspace_router)
        router.include_router(
            super().workspace_router,
            prefix=DOCKER_ROUTE_PREFIX,
            include_in_schema=False,
        )
        return router

    @property
    def sockets_router(self) -> APIRouter:
        from openhands.agent_server.docker_runtime.routers import (
            docker_session_sockets_router,
            docker_sockets_router,
        )
        from openhands.agent_server.session_socket import session_router
        from openhands.agent_server.sockets import (
            bash_sockets_router,
            conversation_sockets_router,
        )

        router = APIRouter()
        router.include_router(conversation_sockets_router)
        router.include_router(session_router)
        router.include_router(bash_sockets_router)
        for docker in (docker_sockets_router, docker_session_sockets_router):
            router.include_router(
                docker, prefix=DOCKER_ROUTE_PREFIX, include_in_schema=False
            )
        return router


class RuntimeDispatchMiddleware:
    """将每个对话的请求路由到拥有它的运行时。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        registry = scope["app"].state.conversation_registry if "app" in scope else None
        if scope["type"] not in ("http", "websocket") or not isinstance(
            registry, HybridConversationRegistry
        ):
            await self.app(scope, receive, send)
            return

        root_path = scope.get("root_path", "")
        path = scope["path"].removeprefix(root_path)
        method = scope.get("method")
        to_docker = False
        if scope["type"] == "websocket":
            match = _SOCKET_PATH.match(path)
            conversation_id = _conversation_id(match[1]) if match is not None else None
            to_docker = conversation_id is not None and registry.is_docker(
                conversation_id
            )
        elif path == "/api/conversations" and method == "POST":
            receive, body = await _buffer_body(receive)
            request = _json_object(body)
            # 现有 Docker 对话的开始将在 Docker 中恢复。
            existing = _conversation_id(request.get("conversation_id"))
            to_docker = (existing is not None and registry.is_docker(existing)) or (
                request.get("conversation_runtime")
                or registry.config.conversation_runtime
            ) == "docker"
        elif match := _CONVERSATION_PATH.match(path):
            # 会话本身的GET是共享目录记录。
            catalog_read = match[2] is None and method in ("GET", "HEAD")
            conversation_id = _conversation_id(match[1])
            to_docker = (
                conversation_id is not None
                and not catalog_read
                and registry.is_docker(conversation_id)
            )

        if to_docker:
            prefix = "/api" if path.startswith("/api/") else ""
            rewritten = prefix + DOCKER_ROUTE_PREFIX + path[len(prefix) :]
            full = root_path + rewritten
            scope = {**scope, "path": full, "raw_path": full.encode()}
        await self.app(scope, receive, send)


async def _buffer_body(receive: Receive) -> tuple[Receive, bytes]:
    messages: list[Message] = []
    body = b""
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] != "http.request":
            break
        body += message.get("body", b"")
        if not message.get("more_body"):
            break

    async def replay() -> Message:
        return messages.pop(0) if messages else await receive()

    return replay, body


def _json_object(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _conversation_id(value: Any) -> UUID | None:
    try:
        return UUID(value) if isinstance(value, str) else None
    except ValueError:
        return None
