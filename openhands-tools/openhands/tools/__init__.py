"""运行时工具包。

这是已发布的 ``openhands-tools`` 分布的主要导入表面。

大多数工具实现都位于显式子模块中（e.g.
``openhands.tools.terminal``). 但是，我们还为最常见的工具和预设提供了一小部分方便的重
新导出。

策划的公共表面通过 ``__all__`` 进行跟踪，因此 CI 可以检测到不兼容变更。

Note: BrowserToolSet 是故意在此处重新导出的不，以避免强制
下游消费者（e.g.，OpenHands-CLI）捆绑浏览器使用包及其严重依赖项。 需要浏览器工具的用
户直接导入
from ``openhands.tools.browser_use``.
"""

from importlib.metadata import PackageNotFoundError, version

from openhands.tools.ask_oracle import AskOracleTool
from openhands.tools.delegate import DelegationVisualizer
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.preset.default import (
    get_default_agent,
    get_default_tools,
    register_builtins_agents,
    register_default_tools,
)
from openhands.tools.task import TaskToolSet
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool
from openhands.tools.workflow import WorkflowToolSet


try:
    __version__ = version("openhands-tools")
except PackageNotFoundError:
    __version__ = "0.0.0"  # 回退方案用于可编辑/未构建的环境


__all__ = [
    "__version__",
    "AskOracleTool",
    "DelegationVisualizer",
    "FileEditorTool",
    "TaskToolSet",
    "TaskTrackerTool",
    "TerminalTool",
    "WorkflowToolSet",
    "get_default_agent",
    "get_default_tools",
    "register_default_tools",
    "register_builtins_agents",
]
