"""OpenHands Agent Server 的挂钩服务。

该模块包含从工作区加载钩子的业务逻辑，保持路由器干净并专注于 HTTP 关注点。

钩子来源：
- 项目挂钩：{工作区}/.openhands/hooks.json
- 用户挂钩：~/.openhands/hooks.json（未来）
"""

from pathlib import Path

from openhands.sdk.hooks import HookConfig
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


def load_hooks_from_workspace(project_dir: str | None = None) -> HookConfig | None:
    """从工作区 .openhands/hooks.json 文件加载钩子。

    如果项目存在，则此函数会读取项目 .openhands/hooks.json 文件中的钩子配置。

    Args:
        project_dir: 工作区项目挂钩的目录路径。

    Returns:
        如果 hooks.json 存在且有效，则为 HookConfig，否则为 None。
    """
    if not project_dir:
        logger.debug("No project_dir provided, skipping hooks loading")
        return None

    hooks_path = Path(project_dir) / ".openhands" / "hooks.json"

    if not hooks_path.exists():
        logger.debug(f"No hooks.json found at {hooks_path}")
        return None

    try:
        hook_config = HookConfig.load(path=hooks_path)

        if hook_config.is_empty():
            logger.debug(f"hooks.json at {hooks_path} is empty")
            return None

        logger.info(f"Loaded hooks from {hooks_path}")
        return hook_config

    except Exception as e:
        logger.warning(f"Failed to load hooks from {hooks_path}: {e}")
        return None
