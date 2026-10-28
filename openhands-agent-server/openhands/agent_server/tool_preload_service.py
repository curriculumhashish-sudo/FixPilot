"""预加载 Chromium 的服务。"""

from __future__ import annotations

from openhands.agent_server.config import get_default_config
from openhands.sdk.logger import get_logger
from openhands.sdk.tool.schema import Action
from openhands.sdk.tool.tool import create_action_type_with_risk
from openhands.sdk.utils.models import get_known_concrete_subclasses


_logger = get_logger(__name__)


class ToolPreloadService:
    """预加载工具/铬的服务减少了时间
    开始第一次对话"""

    running: bool = False

    async def start(self) -> bool:
        """预加载工具"""

        # 如果已经运行则跳过
        if self.running:
            return True

        self.running = True
        try:
            from openhands.tools.browser_use.impl import BrowserToolExecutor

            # 在这里创建一个实例来预加载 chomium
            BrowserToolExecutor()

            # 预先创建所有这些类可以防止在第一次对话调用时每个工具花费大量时间的处理。
            #
            for action_type in get_known_concrete_subclasses(Action):
                create_action_type_with_risk(action_type)

            _logger.debug(f"Loaded {BrowserToolExecutor}")
            return True
        except Exception:
            _logger.exception("Error preloading chromium")
            return False

    async def stop(self) -> None:
        """停止工具预加载过程。"""
        self.running = False

    def is_running(self) -> bool:
        """检查工具预加载是否正在运行。"""
        return self.running


_tool_preload_service: ToolPreloadService | None = None


def get_tool_preload_service() -> ToolPreloadService | None:
    """如果启用了预加载，则获取工具预加载服务实例。"""
    global _tool_preload_service
    config = get_default_config()

    if not config.preload_tools:
        _logger.info("Tool preload is disabled in configuration")
        return None

    if _tool_preload_service is None:
        _tool_preload_service = ToolPreloadService()
    return _tool_preload_service
