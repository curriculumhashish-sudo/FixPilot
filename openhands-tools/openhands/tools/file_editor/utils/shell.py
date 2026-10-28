import os
import subprocess
import time

from openhands.sdk.utils import sanitized_env
from openhands.sdk.utils.truncate import maybe_truncate
from openhands.tools.file_editor.utils.constants import (
    CONTENT_TRUNCATED_NOTICE,
    MAX_RESPONSE_LEN_CHAR,
)


def run_shell_cmd(
    cmd: str,
    timeout: float | None = 120.0,  # 秒
    truncate_after: int | None = MAX_RESPONSE_LEN_CHAR,
    truncate_notice: str = CONTENT_TRUNCATED_NOTICE,
) -> tuple[int, str, str]:
    """使用超时同步运行 shell 命令。

    Args:
        cmd: 要运行的 shell 命令。
        timeout: 等待命令完成的最长时间。
        truncate_after: stdout 返回的最大字符数
            和标准错误。

    Returns:
        包含返回码、stdout 和 stderr 的元组。
    """

    start_time = time.time()

    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=sanitized_env(),
        )

        stdout, stderr = process.communicate(timeout=timeout)

        return (
            process.returncode or 0,
            maybe_truncate(
                stdout, truncate_after=truncate_after, truncate_notice=truncate_notice
            ),
            maybe_truncate(
                stderr,
                truncate_after=truncate_after,
                truncate_notice=CONTENT_TRUNCATED_NOTICE,
            ),  # 使用 stderr 的通用通知
        )
    except subprocess.TimeoutExpired:
        if process:
            process.kill()
        elapsed_time = time.time() - start_time
        raise TimeoutError(
            f"Command '{cmd}' timed out after {elapsed_time:.2f} seconds"
        )


def check_tool_installed(tool_name: str) -> bool:
    """检查是否安装了工具。"""
    try:
        subprocess.run(
            [tool_name, "--version"],
            check=True,
            cwd=os.getcwd(),
            capture_output=True,
            env=sanitized_env(),
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
