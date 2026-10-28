"""SDK-不与环境交互的驻留工具。

`BUILT_IN_TOOLS` 包含每个智能体附带的工具。 `BUILT_IN_TOOL_CLASSES` 还包括可选的 SDK
工具，这些工具通过智能体设置中的名称进行
解析。

需要与环境交互的工具属于`openhands-tools`。
"""

from openhands.sdk.tool.builtins.classify_and_switch_llm import (
    ClassifyAndSwitchLLMAction,
    ClassifyAndSwitchLLMExecutor,
    ClassifyAndSwitchLLMObservation,
    ClassifyAndSwitchLLMTool,
)
from openhands.sdk.tool.builtins.finish import (
    FinishAction,
    FinishExecutor,
    FinishObservation,
    FinishTool,
)
from openhands.sdk.tool.builtins.invoke_skill import (
    InvokeSkillAction,
    InvokeSkillExecutor,
    InvokeSkillObservation,
    InvokeSkillTool,
)
from openhands.sdk.tool.builtins.switch_llm import (
    SwitchLLMAction,
    SwitchLLMExecutor,
    SwitchLLMObservation,
    SwitchLLMTool,
)
from openhands.sdk.tool.builtins.think import (
    ThinkAction,
    ThinkExecutor,
    ThinkObservation,
    ThinkTool,
)
from openhands.sdk.tool.builtins.vision_inspect import (
    VisionInspectAction,
    VisionInspectExecutor,
    VisionInspectObservation,
    VisionInspectTool,
)
from openhands.sdk.tool.tool import ToolDefinition


# 默认情况下，工具附加到每个智能体。 `InvokeSkillTool` 是故意的
# *不* 这里：是自动连接的 `Agent._initialize` 只有当
# AgentSkills-格式技能已加载（参见下面的BUILT_IN_TOOL_CLASSES）。
BUILT_IN_TOOLS = [FinishTool, ThinkTool]

# 内置工具类名称与其类的映射。 包括可选的内置函数，因此可以通过 `include_default_tools`
# 中的名称和 `Agent._initialize` 中的条件接线来解析它们。
#
BUILT_IN_TOOL_CLASSES = {
    **{tool.__name__: tool for tool in BUILT_IN_TOOLS},
    InvokeSkillTool.__name__: InvokeSkillTool,
    SwitchLLMTool.__name__: SwitchLLMTool,
    VisionInspectTool.__name__: VisionInspectTool,
    ClassifyAndSwitchLLMTool.__name__: ClassifyAndSwitchLLMTool,
}

BUILT_IN_TOOLS_WITH_PARAMS = frozenset({ClassifyAndSwitchLLMTool.__name__})


def builtin_tool_class(name: str) -> type[ToolDefinition] | None:
    """返回以其类名或工具名命名的内置工具类。"""
    if name in BUILT_IN_TOOL_CLASSES:
        return BUILT_IN_TOOL_CLASSES[name]
    return next(
        (tool for tool in BUILT_IN_TOOL_CLASSES.values() if tool.name == name), None
    )


__all__ = [
    "BUILT_IN_TOOLS",
    "BUILT_IN_TOOL_CLASSES",
    "BUILT_IN_TOOLS_WITH_PARAMS",
    "builtin_tool_class",
    "ClassifyAndSwitchLLMTool",
    "ClassifyAndSwitchLLMAction",
    "ClassifyAndSwitchLLMObservation",
    "ClassifyAndSwitchLLMExecutor",
    "FinishTool",
    "FinishAction",
    "FinishObservation",
    "FinishExecutor",
    "InvokeSkillTool",
    "InvokeSkillAction",
    "InvokeSkillObservation",
    "InvokeSkillExecutor",
    "SwitchLLMTool",
    "SwitchLLMAction",
    "SwitchLLMObservation",
    "SwitchLLMExecutor",
    "ThinkTool",
    "ThinkAction",
    "ThinkObservation",
    "ThinkExecutor",
    "VisionInspectTool",
    "VisionInspectAction",
    "VisionInspectObservation",
    "VisionInspectExecutor",
]
