import json
from contextlib import AbstractAsyncContextManager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from openhands.agent_server.docker_runtime.provisioning import RuntimeProvisioningStore
from openhands.agent_server.storage import StoredRuntime


if TYPE_CHECKING:
    from openhands.agent_server.docker_runtime.registry import (
        DockerConversationRegistry,
    )


@dataclass(frozen=True, slots=True)
class DockerRuntimeStorage:
    """``runtime-data/<id>/``：沙箱主页，通常是它的工作区。"""

    registry: "DockerConversationRegistry"

    @property
    def provisioning(self) -> RuntimeProvisioningStore:
        return self.registry.provisioning

    @property
    def root(self) -> Path:
        return self.provisioning.data_root

    def runtime(self, conversation_id: UUID) -> StoredRuntime | None:
        runtime_dir = self.provisioning.runtime_dir(conversation_id)
        if runtime_dir.is_symlink() or not runtime_dir.is_dir():
            return None
        state = self.registry.conversation_dir(conversation_id) / "base_state.json"
        try:
            last_active = state.stat().st_mtime
        except OSError:
            try:
                last_active = runtime_dir.stat().st_mtime
            except OSError:
                # 自上述检查后已删除； 没有什么可以收回的。
                return None
        try:
            home = self.provisioning.direct_child(runtime_dir, "persistence")
        except ValueError:
            home = None
        workspace = self._owned_workspace(conversation_id, runtime_dir)
        return StoredRuntime(
            conversation_id,
            last_active,
            home=home,
            workspaces=(workspace,) if workspace else (),
        )

    def _owned_workspace(self, conversation_id: UUID, runtime_dir: Path) -> Path | None:
        """运行时的工作区，如果服务器在运行时数据内创建它。"""
        try:
            identity = self.provisioning.load_optional(conversation_id)
        except Exception:
            return None
        if identity is None or identity.workspace_path.is_symlink():
            return None
        workspace = identity.workspace_path.resolve()
        # 调用者提供的工作区是某人的结帐，而不是我们要修剪的。
        return workspace if workspace.is_relative_to(runtime_dir.resolve()) else None

    def runtimes(self) -> list[StoredRuntime]:
        runtimes = [
            runtime
            for runtime_dir in self.root.iterdir()
            if (conversation_id := _parse_id(runtime_dir.name))
            and (runtime := self.runtime(conversation_id))
        ]
        return sorted(runtimes, key=lambda runtime: runtime.last_active)

    def idle(self, conversation_id: UUID) -> AbstractAsyncContextManager[bool]:
        return self.registry.runtime_idle(conversation_id)

    def archive(self, conversation_id: UUID) -> list[Path]:
        # 标记优先：如果移动从未发生，则下一次通过重试它。
        self.registry.archived_marker(conversation_id).write_text(
            json.dumps({"archived_at": datetime.now(UTC).isoformat()})
        )
        return [self.provisioning.runtime_dir(conversation_id)]

    async def on_archived(self, conversation_id: UUID) -> None:
        await self.registry.refresh_conversation(conversation_id)


def _parse_id(name: str) -> UUID | None:
    with suppress(ValueError):
        return UUID(hex=name)
    return None
