"""测试终端会话中的关闭处理。

该模块测试关闭处理逻辑，当终端会话被清理时，该逻辑可在 Python 关闭期间防止
ImportError。
"""

from unittest.mock import Mock

from openhands.tools.terminal.terminal.tmux_terminal import TmuxTerminal


def test_tmux_terminal_close_normal_operation():
    """测试 TmuxTerminal.close() 是否正常工作。"""
    terminal = TmuxTerminal("/tmp")

    # 手动设置模拟对象会话以避免复杂的初始化
    mock_session = Mock()
    terminal.session = mock_session

    # 正常关闭应该调用 session.kill()
    terminal.close()

    mock_session.kill.assert_called_once()
    assert terminal.closed


def test_tmux_terminal_close_during_shutdown():
    """测试 TmuxTerminal.close() 在关闭期间处理 ImportError。"""
    terminal = TmuxTerminal("/tmp")

    # 手动设置模拟对象会话以避免复杂的初始化
    mock_session = Mock()
    mock_session.kill.side_effect = ImportError(
        "sys.meta_path is None, Python is likely shutting down"
    )
    terminal.session = mock_session

    # close() 应该优雅地处理 ImportError
    terminal.close()  # 不应引发异常

    # session.kill() 应该被调用但引发了 ImportError
    mock_session.kill.assert_called_once()
    assert terminal.closed


def test_tmux_terminal_close_multiple_calls():
    """测试多个 close() 调用是否安全。"""
    terminal = TmuxTerminal("/tmp")

    # 手动设置模拟对象会话以避免复杂的初始化
    mock_session = Mock()
    terminal.session = mock_session

    # 第一次收盘
    terminal.close()
    mock_session.kill.assert_called_once()

    # 第二次关闭应该是安全的，不会再次调用 kill()
    terminal.close()
    mock_session.kill.assert_called_once()  # 还是只打过一次电话


def test_tmux_terminal_close_when_session_already_dead():
    """测试 TmuxTerminal.close() 处理已经在外部死亡/终止的会话。"""
    terminal = TmuxTerminal("/tmp")

    # 手动设置模拟对象会话以避免复杂的初始化
    mock_session = Mock()
    # 模拟 tmux 中的“找不到会话”错误
    mock_session.kill.side_effect = Exception("can't find session: $2")
    terminal.session = mock_session

    # close()应该优雅地处理异常
    terminal.close()  # 不应引发异常

    # session.kill() 应该被调用但引发了异常
    mock_session.kill.assert_called_once()
    assert terminal.closed
