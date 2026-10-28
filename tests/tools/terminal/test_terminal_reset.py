"""测试 bash 终端重置功能。"""

import tempfile
import uuid

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.terminal import (
    TerminalAction,
    TerminalObservation,
    TerminalTool,
)


def _create_conv_state(working_dir: str) -> ConversationState:
    """帮助程序创建 ConversationState 用于测试。"""

    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return ConversationState.create(
        id=uuid.uuid4(), agent=agent, workspace=LocalWorkspace(working_dir=working_dir)
    )


def test_bash_reset_basic():
    """测试基本重置功能。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        # 执行命令设置环境变量
        action = TerminalAction(command="export TEST_VAR=hello")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert result.metadata.exit_code == 0

        # 验证变量是否已设置
        action = TerminalAction(command="echo $TEST_VAR")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert "hello" in result.text

        # 重置终端
        reset_action = TerminalAction(command="", reset=True)
        reset_result = tool(reset_action)
        assert isinstance(reset_result, TerminalObservation)
        assert "Terminal session has been reset" in reset_result.text
        assert reset_result.command == "[RESET]"

        # 验证重置后不再设置变量
        action = TerminalAction(command="echo $TEST_VAR")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        # 重置后该变量应为空
        assert result.text.strip() == ""


def test_bash_reset_with_command():
    """测试reset复位后是否执行命令。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        # 设置环境变量
        action = TerminalAction(command="export TEST_VAR=world")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert result.metadata.exit_code == 0

        # 使用命令重置（应重置然后执行命令）
        reset_action = TerminalAction(
            command="echo 'hello from fresh terminal'", reset=True
        )
        reset_result = tool(reset_action)
        assert isinstance(reset_result, TerminalObservation)
        assert "Terminal session has been reset" in reset_result.text
        assert "hello from fresh terminal" in reset_result.text
        assert reset_result.command == "[RESET] echo 'hello from fresh terminal'"

        # 验证变量不再设置（确认重置有效）
        action = TerminalAction(command="echo $TEST_VAR")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert result.text.strip() == ""


def test_bash_reset_working_directory():
    """测试重置是否保留工作目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        # 检查初始工作目录
        action = TerminalAction(command="pwd")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert temp_dir in result.text

        # 更改目录
        action = TerminalAction(command="cd /home")
        result = tool(action)
        assert isinstance(result, TerminalObservation)

        # 验证目录已更改
        action = TerminalAction(command="pwd")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert "/home" in result.text

        # 重置终端
        reset_action = TerminalAction(command="", reset=True)
        reset_result = tool(reset_action)
        assert isinstance(reset_result, TerminalObservation)
        assert "Terminal session has been reset" in reset_result.text

        # 验证工作目录恢复为原始状态
        action = TerminalAction(command="pwd")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert temp_dir in result.text


def test_bash_reset_multiple_times():
    """测试reset可以被多次调用。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        # 第一次重置
        reset_action = TerminalAction(command="", reset=True)
        reset_result = tool(reset_action)
        assert isinstance(reset_result, TerminalObservation)
        assert "Terminal session has been reset" in reset_result.text

        # 第一次重置后执行命令
        action = TerminalAction(command="echo 'after first reset'")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert "after first reset" in result.text

        # 第二次重置
        reset_action = TerminalAction(command="", reset=True)
        reset_result = tool(reset_action)
        assert isinstance(reset_result, TerminalObservation)
        assert "Terminal session has been reset" in reset_result.text

        # 第二次复位后执行命令
        action = TerminalAction(command="echo 'after second reset'")
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert "after second reset" in result.text


def test_bash_reset_with_timeout():
    """测试重置是否与超时参数一起工作。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        # 使用超时重置（应忽略超时）
        reset_action = TerminalAction(command="", reset=True, timeout=5.0)
        reset_result = tool(reset_action)
        assert isinstance(reset_result, TerminalObservation)
        assert "Terminal session has been reset" in reset_result.text
        assert reset_result.command == "[RESET]"


def test_bash_reset_with_is_input_validation():
    """测试 Reset=True 和 is_input=True 会引发验证错误。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        # 创建具有无效组合的操作
        action = TerminalAction(command="", reset=True, is_input=True)

        # 执行时应该引发错误
        with pytest.raises(
            ValueError, match="Cannot use reset=True with is_input=True"
        ):
            tool(action)


def test_bash_reset_only_with_empty_command():
    """使用空命令测试重置（仅重置）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        # 用空命令重置
        reset_action = TerminalAction(command="", reset=True)
        reset_result = tool(reset_action)
        assert isinstance(reset_result, TerminalObservation)
        assert "Terminal session has been reset" in reset_result.text
        assert reset_result.command == "[RESET]"
