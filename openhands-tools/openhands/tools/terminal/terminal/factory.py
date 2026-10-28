"""用于根据系统功能创建适当的终端会话的工厂。"""

import platform
import subprocess
import warnings
from collections.abc import Mapping
from typing import Literal

from openhands.sdk.logger import get_logger
from openhands.sdk.utils import sanitized_env
from openhands.tools.terminal.terminal.terminal_session import TerminalSession


logger = get_logger(__name__)


def _is_tmux_available() -> bool:
    """检查系统上是否可用 tmux。"""
    try:
        result = subprocess.run(
            ["tmux", "-V"],
            capture_output=True,
            text=True,
            timeout=5.0,
            env=sanitized_env(),
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _get_powershell_command(explicit_shell_path: str | None = None) -> str | None:
    """返回当前平台可用的 PowerShell 可执行文件。"""
    candidates = [explicit_shell_path] if explicit_shell_path else []
    if platform.system() == "Windows":
        candidates.extend(["pwsh.exe", "pwsh", "powershell.exe", "powershell"])
    else:
        candidates.extend(["pwsh"])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            result = subprocess.run(
                [candidate, "-Command", "Write-Host 'PowerShell Available'"],
                capture_output=True,
                text=True,
                timeout=5.0,
                env=sanitized_env(),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError, OSError):
            continue
        if result.returncode == 0:
            return candidate
    return None


def _is_powershell_available() -> bool:
    """检查系统上是否可用 PowerShell。"""
    return _get_powershell_command() is not None


def _create_windows_terminal(
    work_dir: str,
    username: str | None,
    no_change_timeout_seconds: int | None,
    shell_path: str | None,
    env: Mapping[str, str] | None,
) -> TerminalSession:
    from openhands.tools.terminal.terminal.windows_terminal import WindowsTerminal

    resolved_shell_path = _get_powershell_command(shell_path)
    if resolved_shell_path is None:
        raise RuntimeError("PowerShell is not available on this system")

    terminal = WindowsTerminal(
        work_dir,
        username,
        shell_path=resolved_shell_path,
        env=env,
    )
    return TerminalSession(terminal, no_change_timeout_seconds)


def create_terminal_session(
    work_dir: str,
    username: str | None = None,
    no_change_timeout_seconds: int | None = None,
    terminal_type: Literal["tmux", "subprocess", "powershell"] | None = None,
    shell_path: str | None = None,
    env: Mapping[str, str] | None = None,
) -> TerminalSession:
    """根据系统功能创建适当的终端会话。

    Args:
        work_dir: 工作目录会议
        username: 会话的可选用户名
        no_change_timeout_seconds: 超时表示无输出变化
        terminal_type: 强制指定特定会话类型（'tmux'、'子进程'、
            或“powershell”）。 如果为 None，则根据系统功能自动检测。
        shell_path: shell 二进制文件的路径。 在 Unix 上，这用于
            子进程后端； 在 Windows 上，它可以指向 PowerShell 二进制文件。
        env: 添加到终端会话的额外环境变量。

    Returns:
        TerminalSession 实例

    Raises:
        RuntimeError: 如果请求的会话类型不可用
    """
    if terminal_type:
        if terminal_type == "tmux":
            if not _is_tmux_available():
                raise RuntimeError("Tmux is not available on this system")
            from openhands.tools.terminal.terminal.tmux_terminal import TmuxTerminal

            logger.info("Using forced TmuxTerminal")
            terminal = TmuxTerminal(work_dir, username, env=env)
            return TerminalSession(terminal, no_change_timeout_seconds)

        if terminal_type == "powershell":
            logger.info("Using forced WindowsTerminal")
            return _create_windows_terminal(
                work_dir,
                username,
                no_change_timeout_seconds,
                shell_path,
                env,
            )

        if terminal_type == "subprocess":
            if platform.system() == "Windows":
                warnings.warn(
                    "The 'subprocess' terminal type is not supported on Windows. "
                    "Using the PowerShell (WindowsTerminal) backend instead.",
                    stacklevel=2,
                )
                return _create_windows_terminal(
                    work_dir,
                    username,
                    no_change_timeout_seconds,
                    shell_path,
                    env,
                )
            from openhands.tools.terminal.terminal.subprocess_terminal import (
                SubprocessTerminal,
            )

            logger.info("Using forced SubprocessTerminal")
            terminal = SubprocessTerminal(work_dir, username, shell_path, env=env)
            return TerminalSession(terminal, no_change_timeout_seconds)

        raise ValueError(f"Unknown session type: {terminal_type}")

    if platform.system() == "Windows":
        logger.info("Auto-detected: Using WindowsTerminal (PowerShell backend)")
        return _create_windows_terminal(
            work_dir,
            username,
            no_change_timeout_seconds,
            shell_path,
            env,
        )

    if _is_tmux_available():
        from openhands.tools.terminal.terminal.tmux_terminal import TmuxTerminal

        logger.info("Auto-detected: Using TmuxTerminal (tmux available)")
        terminal = TmuxTerminal(work_dir, username, env=env)
        return TerminalSession(terminal, no_change_timeout_seconds)

    from openhands.tools.terminal.terminal.subprocess_terminal import (
        SubprocessTerminal,
    )

    _tmux_warning = (
        "tmux is not installed. Falling back to subprocess-based terminal, "
        "which may be less stable. For best agent performance, install tmux "
        "(e.g. `apt-get install tmux` or `brew install tmux`)."
    )
    logger.warning(_tmux_warning)
    warnings.warn(_tmux_warning, stacklevel=2)
    terminal = SubprocessTerminal(work_dir, username, shell_path, env=env)
    return TerminalSession(terminal, no_change_timeout_seconds)
