"""动态技能上下文注入的命令执行。

支持技能内容中的内联 !`command` 语法。 命令在渲染时执行，其输出替换占位符。

安全规则：
- 受保护的 (```) and inline (`) 代码块将被保留，从不执行。
- 未封闭的围栏块（奇数 ```）延伸到 EOF，保护任何尾随内容免遭意外执行。
- 使用 \\!`cmd` 生成文字文本 !`cmd` 而不执行。

**安全警告**：命令是通过完整进程的 shell 执行的
特权。 仅与值得信赖的技能来源一起使用。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Final

from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

# 每个命令输出 50KB
MAX_OUTPUT_SIZE: Final[int] = 50 * 1024

# 每个命令的默认值超时（以秒为单位）
DEFAULT_TIMEOUT: Final[float] = 10.0

# 单遍匹配受保护的代码块、转义命令、内联代码或 !`command`。
# 顺序很重要：较早的分支优先。
#
# 1. 围栏代码块（``` ... ```）。未闭合的围栏（``` 数量为奇数）
#    会一直匹配到字符串末尾，避免最后一个 ``` 后面的内容被意外执行。
# 2. 转义命令（\!`...`）：移除反斜杠，其余内容保留为字面量 !`...`，
#    让作者能够记录该语法本身。
# 3. 不以 `!` 开头的内联代码（`...`）。
# 4. 可执行命令（!`...`）。
_COMBINED_PATTERN: re.Pattern[str] = re.compile(
    r"(?P<fenced>```[\s\S]*?(?:```|$))"  # 受防护的代码块（未封闭 → EOF）
    r"|(?P<escaped>\\!`[^`]+`)"  # 转义 \!`command` → 文字
    r"|(?P<inline>(?<!!)`[^`]+`)"  # 内联代码（前面没有！）
    r"|!`(?P<cmd>[^`]+)`"  # !`command`
)


def _execute_inline_command(
    command: str,
    working_dir: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """执行单个内联 shell 命令并返回其输出。

    当*working_dir*为None时，该命令继承当前进程的cwd。 智能体执行期间的调用者渲染技能
    应显式传递工作区路径，以便工作区相关命令 (e.g.
    ``git status``) 正确解析。
    """
    cwd = str(working_dir) if working_dir else None
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            message = (
                f"Command `{command}` exited with "
                f"code {result.returncode}: {result.stderr}"
            )
            logger.warning("Skill command failed: %s", message)
            return f"[Error: {message}]"

        output = result.stdout.strip()
        if len(output.encode()) > MAX_OUTPUT_SIZE:
            output = output.encode()[:MAX_OUTPUT_SIZE].decode("utf-8", errors="ignore")
            output += "\n... [output truncated]"
        return output

    except subprocess.TimeoutExpired:
        message = f"Command `{command}` timed out after {timeout}s"
        logger.warning("Skill command failed: %s", message)
        return f"[Error: {message}]"
    except Exception as e:
        message = f"Failed to execute command `{command}`: {e}"
        logger.warning("Skill command failed: %s", message)
        return f"[Error: {message}]"


def render_content_with_commands(
    content: str,
    working_dir: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """在内容中执行内联 !`command` 模式并替换为输出。

    代码块（围栏 ``` and inline `）被保留并且不被执行。 未关闭的围栏块（奇数个
    ```) are treated as extending to EOF so that trailing content is never accidentally executed. Use \\!`
    cmd` to produce the literal text !`cmd` 未执行。
    """  # noqa: E501

    def _replace(match: re.Match[str]) -> str:
        if match.group("fenced") or match.group("inline"):
            return match.group(0)
        if match.group("escaped"):
            # 去掉前导反斜杠：\!`cmd` → !`cmd`
            return match.group("escaped")[1:]
        return _execute_inline_command(match.group("cmd"), working_dir, timeout)

    return _COMBINED_PATTERN.sub(_replace, content)
