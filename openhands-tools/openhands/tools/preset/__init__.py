"""
智能体预设为 OpenHands SDK。

该软件包提供预定义的智能体配置（工具包），可以开箱即用。 预设旨在作为常见用例的起点，
例如默认生产环境智能体、远程 shell 访问、文件编辑、任务跟踪以及选定 MCP 的
集成。

用途：
    from openhands.tools.preset.default import default_tools

    tools = default_tools()

Notes:
- 预设是工具和配置的简单集合，而不是自定义智能体的替代品。
- 它们是稳定的入口，旨在减少典型设置的样板文件。
"""

from .default import (
    discover_builtin_agents,
    get_default_agent,
    register_builtins_agents,
)
from .gemini import get_gemini_agent, get_gemini_tools
from .gpt5 import get_gpt5_agent
from .planning import get_planning_agent
from .task_outcome import (
    TaskOutcome,
    TaskOutcomeStatus,
)


__all__ = [
    "discover_builtin_agents",
    "get_default_agent",
    "get_gemini_agent",
    "get_gemini_tools",
    "get_gpt5_agent",
    "get_planning_agent",
    "register_builtins_agents",
    "TaskOutcome",
    "TaskOutcomeStatus",
]
