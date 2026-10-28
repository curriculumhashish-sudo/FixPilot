"""测试 get_planning_tools() plan_path 参数转发。"""

from openhands.tools.planning_file_editor import PlanningFileEditorTool
from openhands.tools.preset.planning import get_planning_tools


def test_get_planning_tools_without_plan_path_has_empty_params():
    """当未提供 plan_path 时，PlanningFileEditorTool 规格具有空参数。"""
    # 法案
    tools = get_planning_tools()

    # 断言
    planning_tool = next(t for t in tools if t.name == PlanningFileEditorTool.name)
    assert planning_tool.params == {}


def test_get_planning_tools_with_plan_path_passes_params():
    """当提供 plan_path 时，它会在 PlanningFileEditorTool 参数中传递。"""
    # 安排
    expected_path = "/workspace/project/.openhands/PLAN.md"

    # 法案
    tools = get_planning_tools(plan_path=expected_path)

    # 断言
    planning_tool = next(t for t in tools if t.name == PlanningFileEditorTool.name)
    assert planning_tool.params == {"plan_path": expected_path}
