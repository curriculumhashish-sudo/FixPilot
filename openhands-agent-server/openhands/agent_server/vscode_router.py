"""VSCode Agent Server API 端点。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from openhands.agent_server.vscode_service import get_vscode_service
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

vscode_router = APIRouter(prefix="/vscode", tags=["VSCode"])


class VSCodeUrlResponse(BaseModel):
    """VSCode URL 的响应模型。"""

    url: str | None


@vscode_router.get("/url", response_model=VSCodeUrlResponse)
async def get_vscode_url(
    base_url: str | None = None, workspace_dir: str = "workspace"
) -> VSCodeUrlResponse:
    """获取 VSCode URL 身份验证 token。

    Args:
        base_url: URL 基础 VSCode 服务器。 当省略时，URL 是
            由实际配置的 VSCode 端口 (``http://localhost:{vscode_port}``) 构建而成，
            因此，不知道部署拓扑的调用者会
            收到一个 URL，而不是硬编码的 ``:8001``。
        workspace_dir: 工作区目录的路径

    Returns:
        对于 VSCode URL，可用时使用 token，否则使用 None
    """
    vscode_service = get_vscode_service()
    if vscode_service is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "VSCode is disabled in configuration. Set enable_vscode=true to enable."
            ),
        )

    try:
        url = vscode_service.get_vscode_url(base_url, workspace_dir)
        return VSCodeUrlResponse(url=url)
    except Exception as e:
        logger.error(f"Error getting VSCode URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to get VSCode URL")


@vscode_router.get("/status")
async def get_vscode_status() -> dict[str, bool | str]:
    """获取 VSCode 服务器状态。

    Returns:
        具有运行状态和启用状态的字典
    """
    vscode_service = get_vscode_service()
    if vscode_service is None:
        return {
            "running": False,
            "enabled": False,
            "message": "VSCode is disabled in configuration",
        }

    try:
        return {"running": vscode_service.is_running(), "enabled": True}
    except Exception as e:
        logger.error(f"Error getting VSCode status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get VSCode status")
