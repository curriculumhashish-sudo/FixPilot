"""测试 shell 路径配置。"""

import os
import platform
import shutil
import tempfile
from unittest.mock import patch

import pytest


if platform.system() == "Windows":
    pytest.skip(
        "SubprocessTerminal shell path handling depends on Unix PTY support",
        allow_module_level=True,
    )

from openhands.tools.terminal.terminal import SubprocessTerminal
from openhands.tools.terminal.terminal.factory import create_terminal_session


def test_shell_path_explicit_parameter():
    """测试是否使用显式 shell_path 参数。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 使用系统bash
        bash_path = shutil.which("bash")
        if not bash_path:
            pytest.skip("bash not found in PATH")

        session = create_terminal_session(
            work_dir=temp_dir,
            terminal_type="subprocess",
            shell_path=bash_path,
        )

        assert isinstance(session.terminal, SubprocessTerminal)
        assert session.terminal.shell_path == bash_path
        session.close()


def test_shell_path_auto_detection():
    """使用 shutil.which 测试 shell 路径自动检测。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 不要设置 shell_path 或环境变量
        session = create_terminal_session(
            work_dir=temp_dir,
            terminal_type="subprocess",
        )

        # 应该使用自动检测的 bash
        assert isinstance(session.terminal, SubprocessTerminal)
        assert session.terminal.shell_path is None  # 初始化之前未设置
        session.initialize()
        assert session.terminal.shell_path is not None
        session.close()


def test_shell_path_validation_not_exists():
    """测试 shell 路径验证对于不存在的文件是否失败。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir,
            terminal_type="subprocess",
            shell_path="/nonexistent/bash",
        )

        with pytest.raises(RuntimeError, match="Shell binary not found"):
            session.initialize()

        session.close()


def test_shell_path_validation_not_executable():
    """测试 shell 路径验证对于不可执行文件是否失败。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建一个不可执行的文件
        fake_bash = os.path.join(temp_dir, "fake_bash")
        with open(fake_bash, "w") as f:
            f.write("#!/bin/bash\n")
        # 不要使其可执行

        session = create_terminal_session(
            work_dir=temp_dir,
            terminal_type="subprocess",
            shell_path=fake_bash,
        )

        with pytest.raises(RuntimeError, match="not executable"):
            session.initialize()

        session.close()


def test_shell_path_auto_detection_failure():
    """测试自动检测失败是否会引发明显错误。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 模拟对象shutil.which返回None（bash未找到）
        with patch("shutil.which", return_value=None):
            session = create_terminal_session(
                work_dir=temp_dir,
                terminal_type="subprocess",
            )

            with pytest.raises(RuntimeError, match="Could not find bash in PATH"):
                session.initialize()

            session.close()


def test_shell_path_with_tmux_terminal():
    """测试shell_path通过但不影响tmux终端。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        bash_path = shutil.which("bash")
        if not bash_path:
            pytest.skip("bash not found in PATH")

        try:
            session = create_terminal_session(
                work_dir=temp_dir,
                terminal_type="tmux",
                shell_path=bash_path,
            )
            # TmuxTerminal 不使用 shell_path，所以应该忽略它
            session.initialize()
            session.close()
        except RuntimeError as e:
            if "Tmux is not available" in str(e):
                pytest.skip("Tmux not available on this system")
            raise


def test_shell_path_reset_preserves_config():
    """测试终端重置是否保留 shell_path 配置。"""
    from openhands.tools.terminal.impl import TerminalExecutor

    with tempfile.TemporaryDirectory() as temp_dir:
        bash_path = shutil.which("bash")
        if not bash_path:
            pytest.skip("bash not found in PATH")

        executor = TerminalExecutor(
            working_dir=temp_dir,
            terminal_type="subprocess",
            shell_path=bash_path,
        )

        # 验证 shell_path 已存储
        assert executor.shell_path == bash_path

        # 重置终端
        executor.reset()

        # 验证重置后是否保留 shell_path
        assert executor.shell_path == bash_path

        executor.close()


def test_shell_path_precedence_explicit_over_auto():
    """测试显式 shell_path 优先于自动检测。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        bash_path = shutil.which("bash")
        if not bash_path:
            pytest.skip("bash not found in PATH")

        # 测试：显式参数胜过自动检测
        with patch("shutil.which", return_value="/other/bash"):
            session = create_terminal_session(
                work_dir=temp_dir,
                terminal_type="subprocess",
                shell_path=bash_path,
            )
            assert isinstance(session.terminal, SubprocessTerminal)
            assert session.terminal.shell_path == bash_path
            session.close()


def test_terminal_tool_shell_path_parameter():
    """测试 TerminalTool.create 接受并通过 shell_path。"""
    import uuid

    from pydantic import SecretStr

    from openhands.sdk.agent import Agent
    from openhands.sdk.conversation.state import ConversationState
    from openhands.sdk.llm import LLM
    from openhands.sdk.workspace import LocalWorkspace
    from openhands.tools.terminal.definition import TerminalTool

    with tempfile.TemporaryDirectory() as temp_dir:
        bash_path = shutil.which("bash")
        if not bash_path:
            pytest.skip("bash not found in PATH")

        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_state = ConversationState.create(
            id=uuid.uuid4(),
            agent=agent,
            workspace=LocalWorkspace(working_dir=temp_dir),
        )

        tools = TerminalTool.create(
            conv_state=conv_state,
            terminal_type="subprocess",
            shell_path=bash_path,
        )

        terminal = tools[0]
        # 验证执行者具有 shell_path
        from openhands.tools.terminal.impl import TerminalExecutor

        assert isinstance(terminal.executor, TerminalExecutor)
        assert terminal.executor.shell_path == bash_path

        terminal.executor.close()
