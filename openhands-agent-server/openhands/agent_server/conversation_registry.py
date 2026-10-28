"""选择并管理配置的对话运行时。"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter

from openhands.agent_server.config import Config
from openhands.agent_server.models import (
    ConversationRuntimeInfo,
    ConversationRuntimeStatus,
)


if TYPE_CHECKING:
    from openhands.agent_server.conversation_service import ConversationService


class ConversationRegistry:
    """用于主机本地对话的路由和生命周期适配器。"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def configure_service(self, service: ConversationService) -> None:
        """将运行时特定的持久化连接到共享目录。"""

    def runtime_info(self, _conversation_id: UUID) -> ConversationRuntimeInfo:
        """描述目录会话是否具有可执行运行时。"""
        return ConversationRuntimeInfo(
            runtime_status=ConversationRuntimeStatus.AVAILABLE,
            can_resume=True,
        )

    def serves_persisted_event_reads(self, _conversation_id: UUID) -> bool:
        """只读事件路由是否应使用共享已持久化存储。"""
        return False

    async def start(self) -> None:
        """启动此注册表拥有的资源。"""

    async def shutdown(self) -> None:
        """停止此注册表拥有的资源。"""

    def add_execution_routes(self, router: APIRouter) -> None:
        from openhands.agent_server.event_router import event_router
        from openhands.agent_server.runtime_router import create_runtime_router

        router.include_router(create_runtime_router())
        router.include_router(event_router)

    @property
    def workspace_router(self) -> APIRouter:
        from openhands.agent_server.workspace_router import workspace_router

        return workspace_router

    @property
    def conversation_sockets_router(self) -> APIRouter:
        from openhands.agent_server.sockets import conversation_sockets_router

        return conversation_sockets_router

    @property
    def session_sockets_router(self) -> APIRouter:
        from openhands.agent_server.session_socket import session_router

        return session_router

    @property
    def sockets_router(self) -> APIRouter:
        from openhands.agent_server.sockets import bash_sockets_router

        router = APIRouter()
        router.include_router(self.conversation_sockets_router)
        router.include_router(self.session_sockets_router)
        router.include_router(bash_sockets_router)
        return router


def create_conversation_registry(config: Config) -> ConversationRegistry:
    if config.conversation_runtime_selectable:
        from openhands.agent_server.docker_runtime.hybrid import (
            HybridConversationRegistry,
        )

        return HybridConversationRegistry(config)
    if config.conversation_runtime == "docker":
        from openhands.agent_server.docker_runtime.registry import (
            DockerConversationRegistry,
        )

        return DockerConversationRegistry(config)
    return ConversationRegistry(config)
