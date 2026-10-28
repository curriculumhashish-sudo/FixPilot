"""测试 TerminalTool 自动检测功能。"""

import platform
import tempfile
import uuid
from unittest.mock import patch

import pytest
from pydantic import SecretStr


if platform.system() == "Windows":
    pytest.skip(
        "TerminalTool auto-detection currently has only Unix terminal backends",
        allow_module_level=True,
    )

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.terminal import TerminalTool
from openhands.tools.terminal.definition import TerminalAction
from openhands.tools.terminal.impl import TerminalExecutor
from openhands.tools.terminal.terminal import (
    SubprocessTerminal,
    TerminalSession,
)


def _create_conv_state(working_dir: str) -> ConversationState:
    """帮助程序创建 ConversationState 用于测试。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return ConversationState.create(
        id=uuid.uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=working_dir),
    )


def test_default_auto_detection():
    """测试 TerminalTool 是否自动检测适当的会话类型。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        # TerminalTool 总是有一个执行者
        assert tool.executor is not None
        executor = tool.executor
        assert isinstance(executor, TerminalExecutor)

        # 在池模式下，没有单一会话属性； 在单会话模式下有。
        #
        if executor.is_pooled:
            assert executor._pool is not None
            assert executor._pool.max_panes >= 1
        else:
            assert isinstance(executor.session, TerminalSession)
            terminal_type = type(executor.session.terminal).__name__
            assert terminal_type in ["TmuxTerminal", "SubprocessTerminal"]

        # 测试它是否有效
        action = TerminalAction(command="echo 'Auto-detection test'")
        obs = executor(action)
        assert "Auto-detection test" in obs.text


def test_forced_terminal_types():
    """测试强制特定会话类型。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 测试强制子进程会话
        tools = TerminalTool.create(
            _create_conv_state(temp_dir), terminal_type="subprocess"
        )
        tool = tools[0]
        assert tool.executor is not None
        executor = tool.executor
        assert isinstance(executor, TerminalExecutor)
        assert isinstance(executor.session, TerminalSession)
        assert isinstance(executor.session.terminal, SubprocessTerminal)

        # 测试基本功能
        action = TerminalAction(command="echo 'Subprocess test'")
        obs = tool.executor(action)
        assert obs.metadata.exit_code == 0


@patch("platform.system")
def test_unix_auto_detection(mock_system):
    """在类 Unix 系统上测试自动检测行为。"""
    mock_system.return_value = "Linux"

    with tempfile.TemporaryDirectory() as temp_dir:
        # 模拟对象 tmux 可用 → 池模式
        with patch(
            "openhands.tools.terminal.terminal.factory._is_tmux_available",
            return_value=True,
        ):
            tools = TerminalTool.create(_create_conv_state(temp_dir))
            tool = tools[0]
            assert tool.executor is not None
            executor = tool.executor
            assert isinstance(executor, TerminalExecutor)
            # 池模式：无单个会话，池处于活动状态
            assert executor.is_pooled

        # 模拟对象 tmux 不可用 → 单会话/子进程模式
        with (
            patch(
                "openhands.tools.terminal.terminal.factory._is_tmux_available",
                return_value=False,
            ),
            patch(
                "openhands.tools.terminal.impl._is_tmux_available",
                return_value=False,
            ),
        ):
            tools = TerminalTool.create(_create_conv_state(temp_dir))
            tool = tools[0]
            assert tool.executor is not None
            executor = tool.executor
            assert isinstance(executor, TerminalExecutor)
            assert isinstance(executor.session, TerminalSession)
            assert isinstance(executor.session.terminal, SubprocessTerminal)


def test_session_parameters():
    """测试会话参数是否正确传递。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(
            _create_conv_state(temp_dir),
            username="testuser",
            no_change_timeout_seconds=60,
            terminal_type="subprocess",
        )
        tool = tools[0]

        assert tool.executor is not None
        executor = tool.executor
        assert isinstance(executor, TerminalExecutor)
        session = executor.session
        assert session.work_dir == temp_dir
        assert session.username == "testuser"
        assert session.no_change_timeout_seconds == 60


def test_backward_compatibility():
    """测试简化的 API 是否仍然有效。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 这应该像以前一样工作
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        assert tool.executor is not None
        action = TerminalAction(command="echo 'Backward compatibility test'")
        obs = tool.executor(action)
        assert "Backward compatibility test" in obs.text
        assert obs.metadata.exit_code == 0


def test_tool_metadata():
    """测试工具元数据是否被保留。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(_create_conv_state(temp_dir))
        tool = tools[0]

        assert tool.name == "terminal"
        assert tool.description is not None
        assert tool.action_type == TerminalAction
        assert hasattr(tool, "annotations")


def test_session_lifecycle():
    """测试会话生命周期管理。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tools = TerminalTool.create(
            _create_conv_state(temp_dir), terminal_type="subprocess"
        )
        tool = tools[0]

        # 会话应该被初始化
        assert tool.executor is not None
        executor = tool.executor
        assert isinstance(executor, TerminalExecutor)
        assert executor.session._initialized

        # 应该能够执行命令
        action = TerminalAction(command="echo 'Lifecycle test'")
        obs = executor(action)
        assert obs.metadata.exit_code == 0

        # 手动清理应该有效
        executor.session.close()
        assert executor.session._closed
