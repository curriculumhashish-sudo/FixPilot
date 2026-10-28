"""跨包测试将 SDK_TOOL_EXPERIENCE_MAP 固定到真实的注册表。

``openhands.sdk.security.toolshield_helpers`` 中的地图通过
``ToolDefinition.__init_subclass__`` 派生的 REGISTERED 工具名称来键体验文件（删除
snake_case、``_tool``
 后缀）。 tests/sdk 必须不允许导入
``openhands.tools``，因此，对实际工具类的断言和默认预设在这里生效——如果工具被重命名或
映射键漂移，这些断言会失败，而不是作为无声的无操作（在PR #29
11的审查中指出的）进行（具体失败模式）。
"""

from openhands.sdk.security.toolshield_helpers import (
    SDK_TOOL_EXPERIENCE_MAP,
    mcp_tools_from_config,
)
from openhands.tools.browser_use import BrowserToolSet
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.planning_file_editor import PlanningFileEditorTool
from openhands.tools.preset.default import get_default_tools
from openhands.tools.terminal import TerminalTool


def test_map_keys_match_registered_tool_names():
    """每个映射的内置工具的真实 ``.name`` 必须是映射键。"""
    for tool_cls, experience in [
        (FileEditorTool, "filesystem-mcp"),
        (PlanningFileEditorTool, "filesystem-mcp"),
        (TerminalTool, "terminal-mcp"),
        (BrowserToolSet, "playwright-mcp"),
    ]:
        assert SDK_TOOL_EXPERIENCE_MAP.get(tool_cls.name) == experience, (
            f"{tool_cls.__name__}.name == {tool_cls.name!r} is not mapped to "
            f"{experience!r}; SDK_TOOL_EXPERIENCE_MAP keys have drifted from "
            "the registered tool names"
        )


def test_default_preset_tool_names_map_to_experiences():
    """记录的模式 ``tool_names=[t.name for t in agent.tools]``
    必须映射默认预设：文件系统和剧作家体验都会出现。
    """
    names = [t.name for t in get_default_tools()]
    result = mcp_tools_from_config({}, tool_names=names)
    assert "filesystem-mcp" in result
    assert "playwright-mcp" in result
    assert "terminal-mcp" in result
