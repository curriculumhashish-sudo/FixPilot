"""测试会话工厂和自动检测逻辑。"""

import platform
import tempfile
import warnings
from unittest.mock import patch

import pytest


if platform.system() == "Windows":
    pytest.skip(
        "Terminal session factory currently has only Unix terminal backends",
        allow_module_level=True,
    )

from openhands.tools.terminal.terminal import (
    SubprocessTerminal,
    TerminalSession,
    TmuxTerminal,
)
from openhands.tools.terminal.terminal.factory import (
    _is_tmux_available,
    create_terminal_session,
)


def test_tmux_detection():
    """测试tmux可用性检测。"""
    # 这取决于测试环境
    result = _is_tmux_available()
    assert isinstance(result, bool)


def test_forced_terminal_types():
    """测试强制特定会话类型。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 测试强制子进程会话
        session = create_terminal_session(work_dir=temp_dir, terminal_type="subprocess")
        assert isinstance(session, TerminalSession)
        assert isinstance(session.terminal, SubprocessTerminal)
        session.close()

        # 测试强制 tmux 会话（如果可用）
        if _is_tmux_available():
            session = create_terminal_session(work_dir=temp_dir, terminal_type="tmux")
            assert isinstance(session, TerminalSession)
            assert isinstance(session.terminal, TmuxTerminal)
            session.close()


def test_invalid_terminal_type():
    """测试无效会话类型的错误处理。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        with pytest.raises(ValueError, match="Unknown session type"):
            create_terminal_session(work_dir=temp_dir, terminal_type="invalid")  # type: ignore


def test_unavailable_terminal_type():
    """当请求的会话类型不可用时测试错误处理。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 模拟对象 tmux 不可用
        with patch(
            "openhands.tools.terminal.terminal.factory._is_tmux_available",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="Tmux is not available"):
                create_terminal_session(work_dir=temp_dir, terminal_type="tmux")


@patch("platform.system")
def test_auto_detection_unix(mock_system):
    """在类 Unix 系统上测试自动检测。"""
    mock_system.return_value = "Linux"

    with tempfile.TemporaryDirectory() as temp_dir:
        # 模拟对象 tmux 可用
        with patch(
            "openhands.tools.terminal.terminal.factory._is_tmux_available",
            return_value=True,
        ):
            session = create_terminal_session(work_dir=temp_dir)
            assert isinstance(session, TerminalSession)
            assert isinstance(session.terminal, TmuxTerminal)
            session.close()

        # 模拟对象 tmux 不可用
        with patch(
            "openhands.tools.terminal.terminal.factory._is_tmux_available",
            return_value=False,
        ):
            session = create_terminal_session(work_dir=temp_dir)
            assert isinstance(session, TerminalSession)
            assert isinstance(session.terminal, SubprocessTerminal)
            session.close()


@patch("platform.system")
def test_warning_when_tmux_not_available(mock_system):
    """测试未安装 tmux 时发出警告。"""
    mock_system.return_value = "Linux"

    with tempfile.TemporaryDirectory() as temp_dir:
        with patch(
            "openhands.tools.terminal.terminal.factory._is_tmux_available",
            return_value=False,
        ):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                session = create_terminal_session(work_dir=temp_dir)
                session.close()

            assert len(w) == 1
            assert "tmux is not installed" in str(w[0].message)
            assert "install tmux" in str(w[0].message)


def test_session_parameters_passed():
    """测试会话参数是否正确传递。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        session = create_terminal_session(
            work_dir=temp_dir,
            username="testuser",
            no_change_timeout_seconds=60,
            terminal_type="subprocess",
        )

        assert isinstance(session, TerminalSession)
        assert session.work_dir == temp_dir
        assert session.username == "testuser"
        assert session.no_change_timeout_seconds == 60
        # 也检查终端参数
        assert session.terminal.work_dir == temp_dir
        assert session.terminal.username == "testuser"
        session.close()
