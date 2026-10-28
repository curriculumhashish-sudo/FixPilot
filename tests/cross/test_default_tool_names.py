"""SDK 的规范默认工具名称和 OpenHands 工具之间的奇偶性。

``openhands.sdk.tool.defaults`` 拥有默认工具 *names* 作为数据（SDK 无法导入
``openhands-tools``）； 实施和
历史
``get_default_tools`` 构造函数位于 ``openhands-tools`` 中。 这些测试将两者固定在一起
，因此工具重命名不能默默地漂移 SDK 端默
认值（#3968 上的审查问题，已根据 #3978 解决）。
"""

from openhands.sdk.tool.defaults import (
    BROWSER_TOOL_NAME,
    DEFAULT_EXEC_TOOL_NAMES,
    SUB_AGENT_TOOL_NAME,
    default_tool_specs,
)


def test_default_exec_names_match_tool_classes() -> None:
    from openhands.tools.file_editor import FileEditorTool
    from openhands.tools.task_tracker import TaskTrackerTool
    from openhands.tools.terminal import TerminalTool

    assert DEFAULT_EXEC_TOOL_NAMES == (
        TerminalTool.name,
        FileEditorTool.name,
        TaskTrackerTool.name,
    )


def test_sub_agent_name_matches_task_tool_set() -> None:
    from openhands.tools.task import TaskToolSet

    assert SUB_AGENT_TOOL_NAME == TaskToolSet.name


def test_browser_name_matches_browser_tool_set() -> None:
    from openhands.tools.browser_use import BrowserToolSet

    assert BROWSER_TOOL_NAME == BrowserToolSet.name


def test_default_tool_specs_parity_with_get_default_tools() -> None:
    from openhands.tools.preset.default import get_default_tools

    for enable_browser in (False, True):
        for enable_sub_agents in (False, True):
            sdk_names = [
                t.name
                for t in default_tool_specs(
                    enable_browser=enable_browser,
                    enable_sub_agents=enable_sub_agents,
                )
            ]
            preset_names = [
                t.name
                for t in get_default_tools(
                    enable_browser=enable_browser,
                    enable_sub_agents=enable_sub_agents,
                )
            ]
            assert sdk_names == preset_names


def test_delegation_names_are_the_tools_that_take_a_sub_agent_scope() -> None:
    import inspect

    import openhands.tools  # noqa: F401
    from openhands.sdk.subagent.scope import DELEGATION_TOOL_NAMES
    from openhands.sdk.tool.registry import list_registered_tools, registered_tool_class

    scoped = set()
    for name in list_registered_tools():
        tool_class = registered_tool_class(name)
        if tool_class is not None and "sub_agent_scope" in (
            inspect.signature(tool_class.create).parameters
        ):
            scoped.add(name)

    assert scoped == set(DELEGATION_TOOL_NAMES)
