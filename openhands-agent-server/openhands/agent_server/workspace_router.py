"""用于对话的静态网络服务器工作区。

公开对话的工作区目录的内容
``/conversations/{conversation_id}/workspace/{file_path:path}``. 当
``api_router``将此路由器挂载在``/api``前缀下，公共URL变为
``/api/conversations/{conversation_id}/workspace/...``。

行为就像一个普通的静态文件服务器：
- 对文件的请求将返回带有推断的 ``Content-Type`` 的文件。
- 解析为目录的请求将提供 ``index.html``（如果存在），否则返回 404。
- 工作区之外的路径遍历被拒绝。
"""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.dependencies import get_conversation_service
from openhands.sdk.logger import get_logger
from openhands.sdk.workspace import LocalWorkspace


logger = get_logger(__name__)

workspace_router = APIRouter(prefix="/conversations", tags=["Workspace"])


def conversation_workspace_url_path(conversation_id: UUID | str) -> str:
    """返回服务于会话工作区的相对 URL 前缀。

    返回的路径始终以尾部斜杠结尾，因此调用者可以直接将其与相对文件路径连接起来。
    """
    return f"/api/conversations/{conversation_id}/workspace/"


async def _resolve_workspace_dir(
    conversation_id: UUID,
    conversation_service: ConversationService,
) -> Path:
    event_service = await conversation_service.get_event_service(conversation_id)
    if event_service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation not found: {conversation_id}",
        )
    workspace = event_service.stored.workspace
    if not isinstance(workspace, LocalWorkspace):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation workspace is not local; cannot be served",
        )
    workspace_dir = Path(workspace.working_dir).resolve()
    if not workspace_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace directory does not exist",
        )
    return workspace_dir


def _resolve_target(workspace_dir: Path, file_path: str) -> Path:
    """安全地解决 ``workspace_dir`` 下的 ``file_path``。

    拒绝解析后逃逸 ``workspace_dir`` 的任何路径。
    """
    candidate = (workspace_dir / file_path).resolve()
    if candidate != workspace_dir and not candidate.is_relative_to(workspace_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is outside the workspace",
        )
    return candidate


def _serve_path(workspace_dir: Path, file_path: str) -> FileResponse:
    target = _resolve_target(workspace_dir, file_path)

    if target.is_dir():
        index_file = target / "index.html"
        if not index_file.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No index.html in directory",
            )
        return FileResponse(path=index_file)

    if not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )
    return FileResponse(path=target)


@workspace_router.get(
    "/{conversation_id}/workspace",
    responses={404: {"description": "File or conversation not found"}},
)
async def serve_workspace_root(
    conversation_id: UUID,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> FileResponse:
    """从对话的工作区根服务 ``index.html``。"""
    workspace_dir = await _resolve_workspace_dir(conversation_id, conversation_service)
    return _serve_path(workspace_dir, "")


@workspace_router.get(
    "/{conversation_id}/workspace/{file_path:path}",
    responses={404: {"description": "File or conversation not found"}},
)
async def serve_workspace_file(
    conversation_id: UUID,
    file_path: str,
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> FileResponse:
    """从工作区提供文件（或目录 ``index.html``）。"""
    workspace_dir = await _resolve_workspace_dir(conversation_id, conversation_service)
    return _serve_path(workspace_dir, file_path)
