"""测试工具是否使用标准化工作目录。

此测试验证问题 #211 已解决：“标准化 OpenHands 工具的输入参数”

TerminalTool (BashTool) 和 FileEditorTool (StrReplaceEditorTool) 都应使用相同的工作目
录来源：
conv_state.workspace.working_dir
"""

import os
import tempfile
from uuid import uuid4

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.file_editor import FileEditorAction, FileEditorTool
from openhands.tools.terminal import TerminalAction, TerminalTool


pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="TerminalTool currently uses Unix terminal backends",
)


def _create_test_conv_state(temp_dir: str) -> ConversationState:
    """创建测试对话状态的帮助程序。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return ConversationState.create(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=temp_dir),
    )


def test_terminal_and_file_editor_use_same_working_dir():
    """测试 TerminalTool 和 FileEditorTool 使用相同的工作目录。

    这是针对问题 #211 的回归测试，以确保两个工具都从 conv_state.workspace.working_dir
     获取工作目录。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)

        # 从同一个 conv_state 创建两个工具
        terminal_tools = TerminalTool.create(conv_state)
        file_editor_tools = FileEditorTool.create(conv_state)

        terminal_tool = terminal_tools[0]
        file_editor_tool = file_editor_tools[0]

        # 验证终端工具使用正确的工作目录
        pwd_action = TerminalAction(command="pwd")
        pwd_result = terminal_tool(pwd_action)
        assert temp_dir in pwd_result.text, (
            f"TerminalTool should use working_dir from conv_state.workspace. "
            f"Expected {temp_dir} in output, got: {pwd_result.text}"
        )

        # 通过检查描述是否包含工作目录来验证文件编辑器工具使用正确的工作目录
        #
        assert temp_dir in file_editor_tool.description, (
            f"FileEditorTool should include working_dir in description. "
            f"Expected {temp_dir} in description."
        )

        # 验证文件编辑器可以在工作目录中创建文件
        test_file = f"{temp_dir}/test_standardization.txt"
        create_action = FileEditorAction(
            command="create",
            path=test_file,
            file_text="Test content",
        )
        create_result = file_editor_tool(create_action)
        assert not create_result.is_error, (
            f"FileEditorTool should be able to create files in working_dir. "
            f"Error: {create_result.text}"
        )


def test_tools_do_not_require_params_for_working_dir():
    """测试工具不再需要 params={'working_dir': ...} 。

    这验证了通过参数传递 working_dir 的旧模式已被删除，工具现在从
    conv_state.workspace.working_dir 获取它。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)

        # 这两个工具都应该可以在没有 working_dir 参数的情况下创建 create() 方法仅需要
        # conv_state （以及可选的工具特定参数）
        #
        terminal_tools = TerminalTool.create(conv_state)
        file_editor_tools = FileEditorTool.create(conv_state)

        # 验证工具已成功创建
        assert len(terminal_tools) == 1
        assert len(file_editor_tools) == 1

        # 验证工具有执行者
        assert terminal_tools[0].executor is not None
        assert file_editor_tools[0].executor is not None
