"""在持久终端会话中执行 shell 命令。"""

import os
import platform
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState
from rich.text import Text

from openhands.sdk.llm import ImageContent, TextContent
from openhands.sdk.tool import (
    Action,
    DeclaredResources,
    Observation,
    ToolAnnotations,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)
from openhands.sdk.utils import maybe_truncate
from openhands.tools.terminal.constants import (
    MAX_CMD_OUTPUT_SIZE,
    NO_CHANGE_TIMEOUT_SECONDS,
)
from openhands.tools.terminal.descriptions import (
    UNIX_TOOL_DESCRIPTION,
    WINDOWS_TOOL_DESCRIPTION,
)
from openhands.tools.terminal.metadata import CmdOutputMetadata


_LITERAL_ARG_HINT_TEMPLATE = (
    "[Tool-argument error] The `command` argument looks like a Python/JSON "
    "{literal_kind}, not a shell command. It starts with: {head!r}\n\n"
    "The `terminal` tool runs exactly ONE shell command at a time. To pass "
    "structured data or multi-line code:\n"
    "  - Write a script first with `file_editor` "
    '(command="create", path="/tmp/run.py", ...), then invoke it: '
    "`python /tmp/run.py`.\n"
    "  - Or use a heredoc inline, e.g.:\n"
    "        python - <<'EOF'\n"
    "        DATABASES = {{'default': {{...}}}}\n"
    "        # your code here\n"
    "        EOF\n\n"
    "Do not put a Python list/dict literal into the `command` field; the shell "
    "cannot interpret it."
)


def looks_like_python_literal_argument(command: str) -> str | None:
    """检测工具调用何时将结构化数据打包到 `command` 中。

    如果 ``command`` 看起来是 Python/JSON 文字而不是 shell 命令，则返回短原因字符串（
    ``"list literal"``、
    ``"nested list literal"`` 或 ``"dict literal"``），否则返回 ``None``。

    仔细区分 ``[`` 和 ``[[``（后面总是跟有空格）的合法 bash 使用与 Python 样式文字。
    请参阅随附的完整矩阵测试。
    """
    stripped = command.lstrip()
    if len(stripped) < 2:
        return None
    a, b = stripped[0], stripped[1]
    # 顶级列表文字：[{...}]、["..."]、['...']
    if a == "[" and b in ("{", '"', "'"):
        return "list literal"
    # 嵌套列表文字：[[...]] — 但 bash `[[ -f x ]]` 后面跟着一个空格字符，所以我们只标记
    # `[[` 后面跟着非空格。
    #
    if a == "[" and b == "[":
        if len(stripped) >= 3 and stripped[2] not in (" ", "\t"):
            return "nested list literal"
        return None
    # 顶级字典文字：{"key": ...} 或 {'key': ...}。 Bash 组命令 `{ ls; }` 在 `{` 之后始终
    # 有一个空格。
    #
    if a == "{" and b in ('"', "'"):
        return "dict literal"
    return None


class TerminalAction(Action):
    """模式用于终端命令执行。"""

    command: str = Field(
        description=(
            "The shell command to execute. Can be empty string to view"
            " additional logs when the previous exit code is `-1`. Can be a"
            " special key name when `is_input` is True: `C-c` (Ctrl+C),"
            " `C-d` (Ctrl+D/EOF), `C-z` (Ctrl+Z), or any `C-<letter>`"
            " for Ctrl sequences; navigation keys `UP`, `DOWN`, `LEFT`,"
            " `RIGHT`, `HOME`, `END`, `PGUP`, `PGDN`; and `TAB`, `ESC`,"
            " `BS` (Backspace), `ENTER`. You can only execute one command"
            " at a time. Use the platform-appropriate shell syntax described"
            " in the tool description when chaining commands."
        )
    )
    is_input: bool = Field(
        default=False,
        description="If True, the command is an input to the running process. If False, the command is executed in the terminal session. Default is False.",  # noqa
    )
    timeout: float | None = Field(
        default=None,
        ge=0,
        description=f"Optional. Sets a maximum time limit (in seconds) for running the command. If the command takes longer than this limit, you’ll be asked whether to continue or stop it. If you don’t set a value, the command will instead pause and ask for confirmation when it produces no new output for {NO_CHANGE_TIMEOUT_SECONDS} seconds. Use a higher value if the command is expected to take a long time (like installation or testing), or if it has a known fixed duration (like sleep).",  # noqa
    )
    reset: bool = Field(
        default=False,
        description="If True, reset the terminal by creating a new session. Use this only when the terminal becomes unresponsive. Note that all previously set environment variables and session state will be lost after reset. Cannot be used with is_input=True.",  # noqa
    )

    @property
    def visualize(self) -> Text:
        """返回具有 shell 样式的富文本表示形式提示词。"""
        content = Text()

        # 创建 PS1 样式提示词
        content.append("$ ", style="bold green")

        # 添加带有语法高亮的命令
        if self.command:
            content.append(self.command, style="white")
        else:
            content.append("[empty command]", style="italic")

        # 添加元数据（如果存在）
        if self.is_input:
            content.append(" ", style="white")
            content.append("(input to running process)", style="yellow")

        if self.timeout is not None:
            content.append(" ", style="white")
            content.append(f"[timeout: {self.timeout}s]", style="cyan")

        if self.reset:
            content.append(" ", style="white")
            content.append("[reset terminal]", style="red bold")

        return content


class TerminalObservation(Observation):
    """可以呈现为 CLI 输出的 ToolResult。"""

    command: str | None = Field(
        description="The shell command that was executed. Can be empty string if the observation is from a previous command that hit soft timeout and is not yet finished.",  # noqa
    )
    exit_code: int | None = Field(
        default=None,
        description="The exit code of the command. -1 indicates the process hit the soft timeout and is not yet finished.",  # noqa
    )
    timeout: bool = Field(
        default=False, description="Whether the command execution timed out."
    )
    metadata: CmdOutputMetadata = Field(
        default_factory=CmdOutputMetadata,
        description="Additional metadata captured from PS1 after command execution.",
    )
    full_output_save_dir: str | None = Field(
        default=None,
        description="Directory where full output files are saved",
    )

    @property
    def command_id(self) -> int | None:
        """从元数据中获取命令 ID。"""
        return self.metadata.pid

    @property
    def to_llm_content(self) -> Sequence[TextContent | ImageContent]:
        llm_content: list[TextContent | ImageContent] = []

        # 如果 is_error 为 True，则添加错误消息
        if self.is_error:
            llm_content.append(TextContent(text=self.ERROR_MESSAGE_HEADER))

        # TerminalObservation 始终将内容作为单个内容 TextContent
        content_text = self.text

        ret = f"{self.metadata.prefix}{content_text}{self.metadata.suffix}"
        if self.metadata.working_dir:
            ret += f"\n[Current working directory: {self.metadata.working_dir}]"
        if self.metadata.py_interpreter_path:
            ret += f"\n[Python interpreter: {self.metadata.py_interpreter_path}]"
        if self.metadata.exit_code != -1:
            ret += f"\n[Command finished with exit code {self.metadata.exit_code}]"

        # 如果工作目录可用，则使用增强截断和文件保存
        truncated_text = maybe_truncate(
            content=ret,
            truncate_after=MAX_CMD_OUTPUT_SIZE,
            save_dir=self.full_output_save_dir,
            tool_prefix="terminal",
        )
        llm_content.append(TextContent(text=truncated_text))

        return llm_content

    @property
    def visualize(self) -> Text:
        """返回具有终端样式输出格式的富文本表示形式。"""
        text = Text()

        if self.is_error:
            text.append("❌ ", style="red bold")
            text.append(self.ERROR_MESSAGE_HEADER, style="bold red")

        # TerminalObservation 始终将内容作为单个内容 TextContent
        content_text = self.text

        if content_text:
            # 根据内容设置输出样式
            output_lines = content_text.split("\n")
            for line in output_lines:
                if line.strip():
                    # 错误线的颜色不同
                    if any(
                        keyword in line.lower()
                        for keyword in ["error", "failed", "exception", "traceback"]
                    ):
                        text.append(line, style="red")
                    elif any(
                        keyword in line.lower() for keyword in ["warning", "warn"]
                    ):
                        text.append(line, style="yellow")
                    elif line.startswith("+ "):  # bash -x 输出
                        text.append(line, style="cyan")
                    else:
                        text.append(line, style="white")
                text.append("\n")

        # 添加带有样式的元数据
        if hasattr(self, "metadata") and self.metadata:
            if self.metadata.working_dir:
                text.append("\n📁 ", style="blue")
                text.append(
                    f"Working directory: {self.metadata.working_dir}", style="blue"
                )

            if self.metadata.py_interpreter_path:
                text.append("\n🐍 ", style="green")
                text.append(
                    f"Python interpreter: {self.metadata.py_interpreter_path}",
                    style="green",
                )

            if (
                hasattr(self.metadata, "exit_code")
                and self.metadata.exit_code is not None
            ):
                if self.metadata.exit_code == 0:
                    text.append("\n✅ ", style="green")
                    text.append(f"Exit code: {self.metadata.exit_code}", style="green")
                elif self.metadata.exit_code == -1:
                    text.append("\n⏳ ", style="yellow")
                    text.append("Process still running (soft timeout)", style="yellow")
                else:
                    text.append("\n❌ ", style="red")
                    text.append(f"Exit code: {self.metadata.exit_code}", style="red")

        return text


class TerminalTool(ToolDefinition[TerminalAction, TerminalObservation]):
    """通过自动检测自动初始化 TerminalExecutor 的 ToolDefinition 子类。"""  # noqa: E501

    catalog_description: ClassVar[str] = (
        "Run shell commands in a persistent terminal session."
    )

    def declared_resources(self, action: Action) -> DeclaredResources:  # noqa: ARG002
        # 在使用中， tmux backend TmuxPanePool handles 并发通过 pane 级别隔离 —— 选择不
        # 使用框架序列化所以并行调用是允许的。 在使用中， 子进程后端只有一个会话，所以我
        # 们要声明一个资源键序列化终端之间互相调用，不阻塞无关工具。
        #
        if getattr(self.executor, "is_pooled", False):
            return DeclaredResources(keys=(), declared=True)
        return DeclaredResources(keys=("terminal:session",), declared=True)

    @classmethod
    def create(
        cls,
        conv_state: "ConversationState",
        username: str | None = None,
        no_change_timeout_seconds: int | None = None,
        terminal_type: Literal["tmux", "subprocess", "powershell"] | None = None,
        shell_path: str | None = None,
        executor: ToolExecutor | None = None,
        *,
        env: Mapping[str, str] | None = None,
    ) -> Sequence["TerminalTool"]:
        """使用执行器参数初始化 TerminalTool。

        Args:
            conv_state: 要从中获取工作目录的对话状态。
                         如果提供，working_dir 将从 conv_state.workspace 中获取
            username: shell 会话的可选用户名
            no_change_timeout_seconds: 超时表示无输出变化
            terminal_type: 强制指定特定会话类型：
                         （“tmux”、“子进程”或“powershell”）。 如果None，则根据系统功
                         能自动检测：
                         - 在 Windows 上：PowerShell 支持的后端
                         - 在类 Unix 系统上：tmux（如果可用），否则子进程
            shell_path: shell 二进制文件的路径。 在 Unix 上这适用于
                       子进程后端； 在 Windows 上，它可以指向 PowerShell 可执行文件。
            env: 添加到终端会话的额外环境变量。
                 这些是客户端控制的会话设置，不是面向 LLM 的 TerminalAction 模式的一
                 部分。
        """
        # 在这里导入以避免循环导入
        from openhands.tools.terminal.impl import TerminalExecutor

        working_dir = conv_state.workspace.working_dir
        if not os.path.isdir(working_dir):
            raise ValueError(f"working_dir '{working_dir}' is not a valid directory")

        # 初始化执行器
        if executor is None:
            executor = TerminalExecutor(
                working_dir=working_dir,
                username=username,
                no_change_timeout_seconds=no_change_timeout_seconds,
                terminal_type=terminal_type,
                shell_path=shell_path,
                env=env,
                full_output_save_dir=conv_state.env_observation_persistence_dir,
            )

        tool_description = (
            WINDOWS_TOOL_DESCRIPTION
            if platform.system() == "Windows"
            else UNIX_TOOL_DESCRIPTION
        )

        # 使用执行器初始化父级ToolDefinition
        return [
            cls(
                action_type=TerminalAction,
                observation_type=TerminalObservation,
                description=tool_description,
                annotations=ToolAnnotations(
                    title="terminal",
                    readOnlyHint=False,
                    destructiveHint=True,
                    idempotentHint=False,
                    openWorldHint=True,
                ),
                executor=executor,
            )
        ]


# 导入此模块时自动注册该工具
register_tool(TerminalTool.name, TerminalTool)
