"""HTTP 端点用于管理用户已保存的工作区。

工作区本地目录是 GUI 它表面工作区 picker. 他们已持久化在智能体-server (file-backed
JSON而不是在每个浏览器中 localStorage
 以便所有连接到同一端点的客户端都能使用智能体服务器看到相同的列表。
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from openhands.agent_server._secrets_exposure import get_config
from openhands.agent_server.persistence import (
    PersistedWorkspaces,
    WorkspaceItem,
    WorkspaceParentItem,
    get_workspaces_store,
)
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

workspaces_router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


class WorkspacesListResponse(BaseModel):
    workspaces: list[WorkspaceItem] = Field(default_factory=list)
    workspace_parents: list[WorkspaceParentItem] = Field(
        default_factory=list, alias="workspaceParents"
    )
    model_config = ConfigDict(populate_by_name=True)


class AddWorkspacesRequest(BaseModel):
    workspaces: list[WorkspaceItem]


class AddWorkspaceParentsRequest(BaseModel):
    parents: list[WorkspaceParentItem]


class DeleteResponse(BaseModel):
    deleted: bool = True


def _to_response(persisted: PersistedWorkspaces) -> WorkspacesListResponse:
    return WorkspacesListResponse.model_validate(
        {
            "workspaces": list(persisted.workspaces),
            "workspace_parents": list(persisted.workspace_parents),
        }
    )


@workspaces_router.get(
    "",
    response_model=WorkspacesListResponse,
    response_model_exclude_none=True,
)
async def list_workspaces(request: Request) -> WorkspacesListResponse:
    """返回保存的工作区和工作区父母。"""
    config = get_config(request)
    store = get_workspaces_store(config)
    try:
        persisted = store.load()
    except (OSError, PermissionError):
        logger.error("Workspaces list failed - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to read workspaces")
    if persisted is None:
        # ``load()`` 将“文件丢失”和“文件存在但不可读/损坏/未来-模式”折叠到相同的
        # ``None`` 中。 对于第二种情况返回空列表将隐藏用户的数据，并让后续的 POST 使用默
        # 认值覆盖仍在磁盘上的文件。
        #
        if store._path.exists():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workspaces file is corrupted",
            )
        persisted = PersistedWorkspaces()
    return _to_response(persisted)


@workspaces_router.post(
    "",
    response_model=WorkspacesListResponse,
    response_model_exclude_none=True,
)
async def add_workspaces(
    request: Request, payload: AddWorkspacesRequest
) -> WorkspacesListResponse:
    """将工作区附加到已保存的列表。 幂等 — 按 ``path`` 进行重复数据删除。"""
    config = get_config(request)
    store = get_workspaces_store(config)

    def apply(current: PersistedWorkspaces) -> PersistedWorkspaces:
        # 对传入载荷中的现有列表 AND 进行重复数据删除，否则像
        # ``[{"path": "/a"}, {"path": "/a"}]`` 这样的主体将持久化两个条目，尽管有端点合
        # 同。
        #
        seen_paths = {w.path for w in current.workspaces}
        new_items: list[WorkspaceItem] = []
        for w in payload.workspaces:
            if w.path in seen_paths:
                continue
            seen_paths.add(w.path)
            new_items.append(w)
        if not new_items:
            return current
        return current.model_copy(
            update={"workspaces": [*current.workspaces, *new_items]}
        )

    try:
        updated = store.update(apply)
    except RuntimeError as e:
        logger.error(f"Workspaces add blocked: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspaces file is corrupted",
        )
    except (OSError, PermissionError):
        logger.error("Workspaces add failed - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to save workspaces")

    return _to_response(updated)


@workspaces_router.delete("", response_model=DeleteResponse)
async def delete_workspace(
    request: Request,
    path: Annotated[str, Query(description="Absolute workspace path to remove")],
) -> DeleteResponse:
    """通过绝对路径删除工作区。"""
    config = get_config(request)
    store = get_workspaces_store(config)

    removed = False

    def apply(current: PersistedWorkspaces) -> PersistedWorkspaces:
        nonlocal removed
        remaining = [w for w in current.workspaces if w.path != path]
        if len(remaining) == len(current.workspaces):
            return current
        removed = True
        return current.model_copy(update={"workspaces": remaining})

    try:
        store.update(apply)
    except RuntimeError as e:
        logger.error(f"Workspaces delete blocked: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspaces file is corrupted",
        )
    except (OSError, PermissionError):
        logger.error("Workspaces delete failed - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to update workspaces")

    if not removed:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return DeleteResponse()


@workspaces_router.post(
    "/parents",
    response_model=WorkspacesListResponse,
    response_model_exclude_none=True,
)
async def add_workspace_parents(
    request: Request, payload: AddWorkspaceParentsRequest
) -> WorkspacesListResponse:
    """附上工作区父母。 幂等 — 按 ``path`` 进行重复数据删除。"""
    config = get_config(request)
    store = get_workspaces_store(config)

    def apply(current: PersistedWorkspaces) -> PersistedWorkspaces:
        # 针对传入载荷内的现有列表 AND 进行重复数据删除 — 请参阅上面的
        # ``add_workspaces`` 以了解相同的原理。
        #
        seen_paths = {p.path for p in current.workspace_parents}
        new_items: list[WorkspaceParentItem] = []
        for p in payload.parents:
            if p.path in seen_paths:
                continue
            seen_paths.add(p.path)
            new_items.append(p)
        if not new_items:
            return current
        return current.model_copy(
            update={
                "workspace_parents": [*current.workspace_parents, *new_items],
            }
        )

    try:
        updated = store.update(apply)
    except RuntimeError as e:
        logger.error(f"Workspace parents add blocked: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspaces file is corrupted",
        )
    except (OSError, PermissionError):
        logger.error("Workspace parents add failed - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to save workspaces")

    return _to_response(updated)


@workspaces_router.delete("/parents", response_model=DeleteResponse)
async def delete_workspace_parent(
    request: Request,
    path: Annotated[str, Query(description="Absolute workspace parent path to remove")],
) -> DeleteResponse:
    """通过绝对路径删除工作区父级。"""
    config = get_config(request)
    store = get_workspaces_store(config)

    removed = False

    def apply(current: PersistedWorkspaces) -> PersistedWorkspaces:
        nonlocal removed
        remaining = [p for p in current.workspace_parents if p.path != path]
        if len(remaining) == len(current.workspace_parents):
            return current
        removed = True
        return current.model_copy(update={"workspace_parents": remaining})

    try:
        store.update(apply)
    except RuntimeError as e:
        logger.error(f"Workspace parents delete blocked: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Workspaces file is corrupted",
        )
    except (OSError, PermissionError):
        logger.error("Workspace parents delete failed - file I/O error")
        raise HTTPException(status_code=500, detail="Failed to update workspaces")

    if not removed:
        raise HTTPException(status_code=404, detail="Workspace parent not found")
    return DeleteResponse()
