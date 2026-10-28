"""为 OpenHands Agent Server 挂钩路由器。

该模块定义了钩子操作的HTTP API 端点。 业务逻辑委托给hooks_service.py。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from openhands.agent_server.hooks_service import load_hooks_from_workspace
from openhands.sdk.hooks import HookConfig


hooks_router = APIRouter(prefix="/hooks", tags=["Hooks"])


class HooksRequest(BaseModel):
    """加载钩子的请求主体。"""

    project_dir: str | None = Field(
        default=None, description="Workspace directory path for project hooks"
    )


class HooksResponse(BaseModel):
    """包含钩子配置的响应。"""

    hook_config: HookConfig | None = Field(
        default=None,
        description="Hook configuration loaded from the workspace, or None if not found",  # noqa: E501
    )


@hooks_router.post("", response_model=HooksResponse)
def get_hooks(request: HooksRequest) -> HooksResponse:
    """从工作区 .openhands/hooks.json 文件加载钩子。

    如果项目存在，则该端点从项目的openhands/hooks.json文件中读取钩子配置。

    Args:
        request: HooksRequest 包含项目目录路径。

    Returns:
        HooksResponse 包含钩子配置或 None。
    """
    hook_config = load_hooks_from_workspace(project_dir=request.project_dir)
    return HooksResponse(hook_config=hook_config)
