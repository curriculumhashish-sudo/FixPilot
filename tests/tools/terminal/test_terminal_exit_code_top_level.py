import os

import pytest

from openhands.tools.terminal.definition import TerminalAction
from openhands.tools.terminal.terminal import create_terminal_session


@pytest.mark.parametrize("terminal_type", ["tmux", "subprocess"])
def test_exit_code_top_level_completed(terminal_type):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()
    try:
        obs = session.execute(TerminalAction(command="echo top-level"))
        assert obs.metadata.exit_code == 0
        assert obs.exit_code == 0
        assert obs.exit_code == obs.metadata.exit_code
    finally:
        session.close()


@pytest.mark.parametrize("terminal_type", ["tmux", "subprocess"])
def test_exit_code_top_level_soft_timeout(terminal_type):
    session = create_terminal_session(
        work_dir=os.getcwd(), no_change_timeout_seconds=1, terminal_type=terminal_type
    )
    session.initialize()
    try:
        # 命令不产生输出，应该触发 no-change 超时
        obs = session.execute(TerminalAction(command="sleep 2"))
        assert obs.metadata.exit_code == -1
        assert obs.exit_code == -1
        assert obs.exit_code == obs.metadata.exit_code
    finally:
        session.close()


@pytest.mark.parametrize("terminal_type", ["tmux", "subprocess"])
def test_exit_code_top_level_hard_timeout(terminal_type):
    session = create_terminal_session(work_dir=os.getcwd(), terminal_type=terminal_type)
    session.initialize()
    try:
        # Hard 超时应根据模式文档将 exit_code 设置为 -1
        obs = session.execute(TerminalAction(command="sleep 10", timeout=1.0))
        assert obs.metadata.exit_code == -1
        assert obs.exit_code == -1
        assert obs.exit_code == obs.metadata.exit_code
    finally:
        session.close()
