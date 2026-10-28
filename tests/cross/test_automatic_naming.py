"""测试自动工具命名功能。"""


def test_camel_to_snake_conversion():
    """测试 _camel_to_snake 效用函数。"""
    from openhands.sdk.tool.tool import _camel_to_snake

    # 测试基本转换
    assert _camel_to_snake("TerminalTool") == "terminal_tool"
    assert _camel_to_snake("FileEditorTool") == "file_editor_tool"
    assert _camel_to_snake("GrepTool") == "grep_tool"
    assert _camel_to_snake("PlanningFileEditorTool") == "planning_file_editor_tool"
    assert _camel_to_snake("BrowserToolSet") == "browser_tool_set"
    assert _camel_to_snake("TaskTrackerTool") == "task_tracker_tool"
    assert _camel_to_snake("GlobTool") == "glob_tool"

    # 测试边缘情况
    assert _camel_to_snake("Tool") == "tool"
    assert _camel_to_snake("A") == "a"
    assert _camel_to_snake("AB") == "ab"  # 全部大写，无需分隔
    assert _camel_to_snake("ABC") == "abc"  # 全部大写，无需分隔
    assert _camel_to_snake("XMLParser") == "xml_parser"
    assert _camel_to_snake("HTTPClient") == "http_client"


def test_real_tools_have_correct_names():
    """测试真实工具是否具有预期的自动名称。"""
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.glob import GlobTool
    from openhands.tools.grep import GrepTool
    from openhands.tools.planning_file_editor import PlanningFileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    # 验证所有工具具有正确的自动名称
    assert TerminalTool.name == "terminal"
    assert FileEditorTool.name == "file_editor"
    assert GrepTool.name == "grep"
    assert PlanningFileEditorTool.name == "planning_file_editor"
    assert TaskTrackerTool.name == "task_tracker"
    assert GlobTool.name == "glob"


def test_tool_name_consistency():
    """测试工具名称在导入过程中是否一致。"""
    # 多次导入同一个工具以确保一致性
    from openhands.tools.terminal import (
        TerminalTool as TerminalTool1,
        TerminalTool as TerminalTool2,
    )

    assert TerminalTool1.name == TerminalTool2.name == "terminal"

    # 使用不同的工具进行测试
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.grep import GrepTool

    assert FileEditorTool.name == "file_editor"
    assert GrepTool.name == "grep"
    assert FileEditorTool.name != GrepTool.name
