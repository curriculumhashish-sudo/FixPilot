"""使用可选的 plan_path 测试 PlanningFileEditorTool create() 行为。"""

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.planning_file_editor import PlanningFileEditorTool
from openhands.tools.planning_file_editor.definition import PlanningFileEditorAction


def _create_conv_state(working_dir: str) -> ConversationState:
    """创建用于测试的最小对话状态。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return ConversationState.create(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=working_dir),
    )


def test_create_without_plan_path_uses_agents_tmp_directory():
    """如果未提供 plan_path，则会在 .agents_tmp 的工作区处创建 PLAN.md
    根。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        conv_state = _create_conv_state(temp_dir)
        expected_path = Path(temp_dir).resolve() / ".agents_tmp" / "PLAN.md"

        # 法案
        tools = PlanningFileEditorTool.create(conv_state)
        tool = tools[0]

        # 断言
        assert len(tools) == 1
        assert tool.executor is not None
        assert issubclass(tool.action_type, PlanningFileEditorAction)
        assert expected_path.exists()
        assert str(expected_path) in tool.description


def test_create_with_plan_path_uses_given_path():
    """当提供 plan_path 时，将在该路径创建 PLAN.md。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        conv_state = _create_conv_state(temp_dir)
        custom_path = str(Path(temp_dir) / ".agents_tmp" / "PLAN.md")

        # 法案
        tools = PlanningFileEditorTool.create(conv_state, plan_path=custom_path)
        tool = tools[0]

        # 断言
        assert Path(custom_path).exists()
        assert custom_path in tool.description


def test_create_with_plan_path_creates_parent_directory():
    """当 plan_path 位于不存在的子目录中时，将创建父目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        conv_state = _create_conv_state(temp_dir)
        custom_path = str(Path(temp_dir) / "config" / "nested" / "PLAN.md")
        assert not Path(custom_path).parent.exists()

        # 法案
        PlanningFileEditorTool.create(conv_state, plan_path=custom_path)

        # 断言
        assert Path(custom_path).parent.exists()
        assert Path(custom_path).exists()


def test_create_without_plan_path_uses_legacy_location_if_exists():
    """当旧版 PLAN.md 存在于工作区根时，它用于向后兼容性。"""  # noqa: E501
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        conv_state = _create_conv_state(temp_dir)
        legacy_path = Path(temp_dir).resolve() / "PLAN.md"
        new_path = Path(temp_dir).resolve() / ".agents_tmp" / "PLAN.md"

        # 在工作区根目录创建旧版 PLAN.md
        legacy_path.write_text("# Legacy Plan Content")

        # 法案
        tools = PlanningFileEditorTool.create(conv_state)
        tool = tools[0]

        # 断言 - 工具使用旧路径
        assert str(legacy_path) in tool.description
        assert legacy_path.exists()
        # 不应创建新位置
        assert not new_path.exists()


def test_create_with_relative_path_raises_value_error():
    """当plan_path是相对的时，ValueError被提升。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        conv_state = _create_conv_state(temp_dir)
        relative_path = "relative/path/PLAN.md"

        # 行动与断言
        with pytest.raises(
            ValueError, match="plan_path must be an absolute path, got: relative"
        ):
            PlanningFileEditorTool.create(conv_state, plan_path=relative_path)
