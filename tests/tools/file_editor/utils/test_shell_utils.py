import subprocess
from unittest.mock import MagicMock, patch

import pytest

from openhands.tools.file_editor.utils.config import (
    MAX_RESPONSE_LEN_CHAR,
)
from openhands.tools.file_editor.utils.constants import (
    CONTENT_TRUNCATED_NOTICE,
)
from openhands.tools.file_editor.utils.shell import (
    check_tool_installed,
    run_shell_cmd,
)


def test_run_shell_cmd_success():
    """测试运行成功的 shell 命令。"""
    cmd = "echo Hello, World!"
    returncode, stdout, stderr = run_shell_cmd(cmd)

    assert returncode == 0
    assert stdout.strip() == "Hello, World!"
    assert stderr == ""


@patch("subprocess.Popen")
def test_run_shell_cmd_timeout(mock_popen):
    """测试命令超时时是否引发 TimeoutError。"""
    mock_process = MagicMock()
    mock_process.communicate.side_effect = subprocess.TimeoutExpired(
        cmd="sleep 2", timeout=1
    )
    mock_popen.return_value = mock_process

    with pytest.raises(TimeoutError, match="Command 'sleep 2' timed out"):
        run_shell_cmd("sleep 2", timeout=1)


@patch("subprocess.Popen")
def test_run_shell_cmd_truncation(mock_popen):
    """测试 stdout 和 stderr 是否正确截断。"""
    long_output = "a" * (MAX_RESPONSE_LEN_CHAR + 10)
    mock_process = MagicMock()
    mock_process.communicate.return_value = (long_output, long_output)
    mock_process.returncode = 0
    mock_popen.return_value = mock_process

    returncode, stdout, stderr = run_shell_cmd("echo long_output")

    assert returncode == 0
    assert len(stdout) <= MAX_RESPONSE_LEN_CHAR + len(CONTENT_TRUNCATED_NOTICE)
    assert len(stderr) <= MAX_RESPONSE_LEN_CHAR + len(CONTENT_TRUNCATED_NOTICE)


def test_check_tool_installed_python():
    """对于已安装的工具 (Python)，测试 check_tool_installed 返回 True。"""
    # 如果安装了 Python，则“Python”通常可用
    assert check_tool_installed("python") is True


def test_check_tool_installed_nonexistent_tool():
    """对于不存在的工具，测试 check_tool_installed 返回 False。"""
    # 使用不太可能存在的虚构工具名称
    assert check_tool_installed("nonexistent_tool_xyz") is False
