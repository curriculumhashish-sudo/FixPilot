"""测试自动工具注册功能。"""

import sys

import pytest

from openhands.sdk.tool.registry import list_registered_tools


def test_bash_tool_automatic_registration():
    """测试导入时是否自动注册 TerminalTool。"""
    # 导入模块触发注册
    import openhands.tools.terminal.definition  # noqa: F401

    # 检查该工具是否已使用 snake_case 名称注册
    registered_tools = list_registered_tools()
    assert "terminal" in registered_tools


def test_file_editor_tool_automatic_registration():
    """测试导入时是否自动注册 FileEditorTool。"""
    # 导入模块触发注册
    import openhands.tools.file_editor.definition  # noqa: F401

    # 检查该工具是否已使用 snake_case 名称注册
    registered_tools = list_registered_tools()
    assert "file_editor" in registered_tools


def test_task_tracker_tool_automatic_registration():
    """测试导入时是否自动注册 TaskTrackerTool。"""
    # 导入模块触发注册
    import openhands.tools.task_tracker.definition  # noqa: F401

    # 检查该工具是否已使用 snake_case 名称注册
    registered_tools = list_registered_tools()
    assert "task_tracker" in registered_tools


def test_browser_tool_automatic_registration():
    """测试导入时是否自动注册 BrowserToolSet。"""
    # 导入模块触发注册
    import openhands.tools.browser_use.definition  # noqa: F401

    # 检查该工具是否已使用 snake_case 名称注册
    registered_tools = list_registered_tools()
    assert "browser_tool_set" in registered_tools


def test_browser_tool_usable_listing_respects_chromium_availability(
    monkeypatch: pytest.MonkeyPatch,
):
    """可用工具应遵循浏览器工具的 Chromium 可用性。"""
    import openhands.tools.browser_use.definition  # noqa: F401
    from openhands.sdk.tool.registry import list_usable_tools
    from openhands.tools.browser_use.definition import BrowserToolSet

    assert "browser_tool_set" in list_registered_tools()

    monkeypatch.setattr(
        BrowserToolSet,
        "is_usable",
        classmethod(lambda cls: False),
    )
    assert "browser_tool_set" not in list_usable_tools()

    monkeypatch.setattr(
        BrowserToolSet,
        "is_usable",
        classmethod(lambda cls: True),
    )
    assert "browser_tool_set" in list_usable_tools()


def test_grep_tool_automatic_registration():
    """测试导入时是否自动注册 GrepTool。"""
    # 导入模块触发注册
    import openhands.tools.grep.definition  # noqa: F401

    # 检查该工具是否已使用 snake_case 名称注册
    registered_tools = list_registered_tools()
    assert "grep" in registered_tools


def test_glob_tool_automatic_registration():
    """测试导入时是否自动注册 GlobTool。"""
    # 导入模块触发注册
    import openhands.tools.glob.definition  # noqa: F401

    # 检查该工具是否已使用 snake_case 名称注册
    registered_tools = list_registered_tools()
    assert "glob" in registered_tools


def test_planning_file_editor_tool_automatic_registration():
    """测试导入时是否自动注册 PlanningFileEditorTool。"""
    # 导入模块触发注册
    import openhands.tools.planning_file_editor.definition  # noqa: F401

    # 检查该工具是否已使用 snake_case 名称注册
    registered_tools = list_registered_tools()
    assert "planning_file_editor" in registered_tools


def test_import_from_init_triggers_registration():
    """测试从 __init__.py 导入也会触发注册。"""
    # 从 __init__.py 文件导入
    from openhands.tools.terminal import TerminalTool  # noqa: F401

    # 检查该工具是否已使用 snake_case 名称注册
    registered_tools = list_registered_tools()
    assert "terminal" in registered_tools


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="TerminalTool V1 backend is not supported on Windows.",
)
def test_tool_can_be_resolved_after_automatic_registration():
    """测试自动注册的工具是否可以解析并使用。"""
    from unittest.mock import MagicMock

    # 导入触发注册
    import openhands.tools.terminal.definition  # noqa: F401
    from openhands.sdk.conversation.state import ConversationState
    from openhands.sdk.tool.registry import resolve_tool
    from openhands.sdk.tool.spec import Tool

    # 创建模拟对象对话状态
    mock_conv_state = MagicMock(spec=ConversationState)
    mock_workspace = MagicMock()
    mock_workspace.working_dir = "/tmp"
    mock_conv_state.workspace = mock_workspace

    # 尝试使用 snake_case 名称解析该工具
    tool_spec = Tool(name="terminal")
    resolved_tools = resolve_tool(tool_spec, mock_conv_state)

    # 应该可以成功解决
    assert len(resolved_tools) == 1
    assert resolved_tools[0].name == "terminal"
