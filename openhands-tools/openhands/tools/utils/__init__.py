"""共享公用设施。"""

import shutil
import subprocess
from collections.abc import Sequence

from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


def _check_command_available(
    command: str,
    probe_args: Sequence[str] | None = ("--version",),
) -> bool:
    """检查命令是否可用并可选择响应探测。"""

    try:
        if shutil.which(command) is None:
            return False
        if probe_args is None:
            return True
        result = subprocess.run(
            [command, *probe_args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_ripgrep_available() -> bool:
    """检查系统上是否有 ripgrep (rg)。"""

    return _check_command_available("rg")


def _check_grep_available() -> bool:
    """检查系统上是否有 grep 可用。"""

    return _check_command_available("grep", probe_args=None)


def _log_ripgrep_fallback_warning(tool_name: str, fallback_method: str) -> None:
    """记录有关从 ripgrep 回退到替代方法的警告。

    Args:
        tool_name: 工具名称（e.g.、“glob”、“grep”）
        fallback_method: 正在使用的回退方案方法的描述
    """
    logger.warning(
        f"{tool_name}: ripgrep (rg) not available. "
        f"Falling back to {fallback_method}. "
        f"For better performance, consider installing ripgrep: "
        f"https://github.com/BurntSushi/ripgrep#installation"
    )
