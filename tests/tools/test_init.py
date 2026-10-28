"""测试 openhands.tools 包初始化和导入处理。"""


def test_submodule_imports_work():
    """工具应通过显式子模块导入。"""
    from openhands.tools.browser_use import BrowserToolSet
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    assert TerminalTool is not None
    assert FileEditorTool is not None
    assert TaskTrackerTool is not None
    assert BrowserToolSet is not None


def test_tools_module_has_expected_top_level_exports():
    """通用工具/预设应该可以从顶级包导入。

    Note: BrowserToolSet 故意在顶层导出不以避免
    迫使下游消费者捆绑浏览器使用及其严重依赖。
    See: https://github.com/OpenHands/OpenHands-CLI/pull/527
    """

    import openhands.tools

    assert openhands.tools.TerminalTool is not None
    assert openhands.tools.FileEditorTool is not None
    assert openhands.tools.TaskTrackerTool is not None

    assert openhands.tools.get_default_agent is not None
    assert openhands.tools.get_default_tools is not None
    assert openhands.tools.register_default_tools is not None


def test_from_import_works():
    """`from openhands.tools import X` 应该适用于导出的符号。"""

    from openhands.tools import TerminalTool  # noqa: F401
