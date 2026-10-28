"""Windows 特定的终端中断行为测试。"""

import platform
import time

import psutil
import pytest

from openhands.tools.terminal.definition import TerminalAction
from openhands.tools.terminal.terminal import create_terminal_session
from openhands.tools.terminal.terminal.terminal_session import TerminalCommandStatus


pytestmark = pytest.mark.skipif(
    platform.system() != "Windows",
    reason="Windows CTRL_BREAK/PowerShell process behavior only applies on Windows",
)


def _wait_for_child_exit(pid: int, timeout: float = 5.0) -> bool:
    """等待进程退出，如果在超时中幸存下来，则返回 False。"""
    try:
        process = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return True  # 已经走了
    try:
        process.wait(timeout=timeout)
        return True
    except psutil.TimeoutExpired:
        return False
    except psutil.NoSuchProcess:
        return True


def _wait_for_pid_file(pid_path, timeout: float = 15.0) -> bool:
    """等待脚本写入其子 pid 文件。

    ``execute`` 在 1 秒后返回，无变化超时，但在加载的运行器上 PowerShell 可能尚未启动
    脚本（并写入文件）； 此时该命令仍在会话中运行。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pid_path.exists():
            return True
        time.sleep(0.1)
    return pid_path.exists()


def _stop_powershell_process(pid: int) -> None:
    try:
        psutil.Process(pid).kill()
    except psutil.NoSuchProcess:
        pass


@pytest.mark.timeout(45)
def test_windows_ctrl_c_interrupt_kills_child_process(tmp_path) -> None:
    """在超时之后按 Ctrl-C 会停止使命令保持活动状态的子进程。

    该断言仅涵盖直接生成的子进程，而不是完整的 Windows 进程树； 泄露的孙子不会通过这
    个测试。
    """
    pid_path = tmp_path / "child.pid"
    script_path = tmp_path / "wait_on_child.ps1"
    # 使用 PowerShell 的本机路径（str() 在 Windows 上提供 Windows 样式）
    pid_path_str = str(pid_path)
    script_path_str = str(script_path)
    script_path.write_text(
        "\n".join(
            [
                f"$pidPath = '{pid_path_str}'",
                "$child = Start-Process -FilePath powershell.exe "
                "-ArgumentList '-NoLogo','-NoProfile','-Command',"
                "'Start-Sleep -Seconds 120' -PassThru",
                "Set-Content -LiteralPath $pidPath -Value $child.Id",
                "Wait-Process -Id $child.Id",
            ]
        ),
        encoding="utf-8",
    )

    session = create_terminal_session(
        work_dir=str(tmp_path),
        terminal_type="powershell",
        no_change_timeout_seconds=1,
    )
    child_pid: int | None = None
    child_exited = False
    try:
        session.initialize()

        obs = session.execute(TerminalAction(command=f"& '{script_path_str}'"))

        assert obs.metadata.exit_code == -1
        assert session.prev_status == TerminalCommandStatus.NO_CHANGE_TIMEOUT
        assert _wait_for_pid_file(pid_path), "child pid file was never written"
        child_pid = int(pid_path.read_text(encoding="utf-8").strip())
        assert psutil.pid_exists(child_pid)

        session.execute(TerminalAction(command="C-c", is_input=True, timeout=3))

        child_exited = _wait_for_child_exit(child_pid)
    finally:
        if child_pid is not None:
            _stop_powershell_process(child_pid)
        session.close()

    assert child_exited, (
        "Windows Ctrl-C reported through the terminal did not terminate the "
        "child process that kept the timed-out command alive."
    )
