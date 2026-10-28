"""使用 TerminalInterface 后端的统一终端会话。"""

import re
import time
import uuid
from enum import Enum

from openhands.sdk.logger import get_logger
from openhands.sdk.utils import maybe_truncate
from openhands.tools.terminal.constants import (
    CMD_OUTPUT_PS1_END,
    MAX_CMD_OUTPUT_SIZE,
    MIN_POLL_INTERVAL,
    NO_CHANGE_TIMEOUT_SECONDS,
    POLL_INTERVAL,
    TIMEOUT_MESSAGE_TEMPLATE,
)
from openhands.tools.terminal.definition import (
    TerminalAction,
    TerminalObservation,
)
from openhands.tools.terminal.metadata import CmdOutputMetadata
from openhands.tools.terminal.terminal.interface import (
    TerminalInterface,
    TerminalSessionBase,
)
from openhands.tools.terminal.timeout_policy import foreground_timeout_rejection_for
from openhands.tools.terminal.utils.command import (
    escape_bash_special_chars,
    needs_heredoc_completion_boundary,
    split_bash_commands,
)
from openhands.tools.terminal.utils.escape_filter import TerminalQueryFilter


logger = get_logger(__name__)


class TerminalCommandStatus(Enum):
    """终端命令执行的状态。"""

    CONTINUE = "continue"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    NO_CHANGE_TIMEOUT = "no_change_timeout"
    HARD_TIMEOUT = "hard_timeout"


def _normalize_echo_line(line: str) -> str:
    """折叠回显行以与发送的内容进行比较。

    不同的后端会改变回显：readline 删除前导制表符 (tmux) 或用 BEL 替换每个制表符 (子
    进程)。 忽略空格和控制字符，以便比较仍然可以识别回声。
    """
    return re.sub(r"[\x00-\x1f\x7f]", "", line).strip()


def _remove_command_prefix(command_output: str, command: str) -> str:
    """从输出的前面去除终端的 `command` 回显。

    readline 在回显一行时会消耗或重写前导制表符，因此回显可能与仅由空格发送的文本不同
    。 然后进行精确前缀匹配，失败了，整个包装（包括完成标记的两半）会泄露到观
    测结果，因此需要逐行比较，控制字符和空白字符都进行标准化。
    """
    stripped = command_output.lstrip()
    cmd = command.lstrip()
    if stripped.startswith(cmd):
        return stripped[len(cmd) :].lstrip()

    if not cmd:
        return stripped
    out_lines = stripped.split("\n")
    cmd_lines = cmd.split("\n")
    for index, cmd_line in enumerate(cmd_lines):
        if index >= len(out_lines) or _normalize_echo_line(
            out_lines[index]
        ) != _normalize_echo_line(cmd_line):
            # 不是此命令的回显； 保持输出不变。
            return stripped
    return "\n".join(out_lines[len(cmd_lines) :]).lstrip()


def _remove_echoed_line(command_output: str, command: str) -> str:
    """删除一个生成的命令回显，无论它出现在输出中的何处。"""
    target = _normalize_echo_line(command)
    return "".join(
        line
        for line in command_output.splitlines(keepends=True)
        if _normalize_echo_line(line) != target
    )


def _remove_powershell_echo(command_output: str, command: str) -> str:
    command_output = command_output.lstrip()
    command = command.lstrip()
    first_line = command_output.splitlines()[0] if command_output else ""
    if command and command in first_line:
        _, separator, rest = command_output.partition("\n")
        command_output = rest if separator else ""
    return re.sub(r"(?:\r?\n)?PS [^\r\n]*>\s*$", "", command_output).lstrip()


class TerminalSession(TerminalSessionBase):
    """适用于任何 TerminalInterface 后端的统一 bash 会话。

    此类包含所有会话控制器逻辑（超时、命令解析、输出处理），同时将终端操作委托给
    TerminalInterface。
    """

    terminal: TerminalInterface
    prev_status: TerminalCommandStatus | None
    prev_output: str

    def __init__(
        self,
        terminal: TerminalInterface,
        no_change_timeout_seconds: int | None = None,
    ):
        """使用终端后端初始化统一会话。

        Args:
            terminal: 要使用的终端后端
            no_change_timeout_seconds: 超时表示无输出变化
        """
        super().__init__(
            terminal.work_dir,
            terminal.username,
            no_change_timeout_seconds,
        )
        self.terminal = terminal
        self.no_change_timeout_seconds: int = (
            no_change_timeout_seconds or NO_CHANGE_TIMEOUT_SECONDS
        )
        # 存储交互式输入处理的最后一个命令
        self.prev_status = None
        self.prev_output = ""
        # Heredoc 脚本的完成后缀。 将其保留在会话中，以便超时或后续民意调查也可以识别并
        # 删除它。
        #
        self._boundary_marker: re.Pattern[str] | None = None
        self._boundary_echo: str | None = None
        self._wrapper_echo: str | None = None
        # 终端查询序列的状态过滤器（处理分割序列）
        self._query_filter = TerminalQueryFilter()

    @classmethod
    def attach_to_existing(
        cls,
        terminal: TerminalInterface,
        no_change_timeout_seconds: int | None = None,
    ) -> "TerminalSession":
        """为已初始化的终端创建一个 TerminalSession。

        当终端已设置时，请使用此选项代替 ``__init__`` + ``initialize()`` (e.g. 通过窗
        格池）并再次调用
        ``initialize()`` 将创建重复的会话。
        """
        session = cls(terminal, no_change_timeout_seconds)
        session._initialized = True
        return session

    def initialize(self) -> None:
        """初始化终端后端。"""
        self.terminal.initialize()
        self._initialized: bool = True
        logger.debug(f"Unified session initialized with {type(self.terminal).__name__}")

    def close(self) -> None:
        """清理终端后端。"""
        if self._closed:
            return
        self.terminal.close()
        self._closed: bool = True

    def interrupt(self) -> bool:
        """中断当前正在运行的命令（相当于Ctrl+C）。"""
        return self.terminal.interrupt()

    def is_running(self) -> bool:
        """检查命令当前是否正在运行。"""
        if not self._initialized:
            return False
        return self.prev_status in {
            TerminalCommandStatus.CONTINUE,
            TerminalCommandStatus.NO_CHANGE_TIMEOUT,
            TerminalCommandStatus.HARD_TIMEOUT,
        }

    def _is_special_key(self, command: str) -> bool:
        """检查命令是否是特殊键。"""
        # 特殊键的形式为 C-<key>
        _command = command.strip()
        return _command.startswith("C-") and len(_command) == 3

    def _get_command_output(
        self,
        command: str,
        raw_command_output: str,
        metadata: CmdOutputMetadata,
        continue_prefix: str = "",
        is_final: bool = False,
    ) -> str:
        """获取删除了先前命令输出的命令输出。

        还过滤显示输出时可能导致可见转义代码垃圾的终端查询序列。 使用状态过滤来处理可
        能跨增量输出拆分的转义序列。
        See: https://github.com/OpenHands/software-agent-sdk/issues/2244

        Args:
            command: 正在执行的命令
            raw_command_output: 终端的原始输出
            metadata: 输出要填充的元数据
            continue_prefix: 继续输出的前缀
            is_final: 如果 True，则刷新任何挂起的过滤器状态（命令已完成）
        """
        # 从新输出中删除先前的命令输出（如果有）
        if self.prev_output:
            command_output = raw_command_output.removeprefix(self.prev_output)
            metadata.prefix = continue_prefix
        else:
            command_output = raw_command_output
        self.prev_output = raw_command_output  # 无论如何更新当前命令输出
        if self.terminal.is_powershell():
            command_output = _remove_powershell_echo(command_output, command)
        else:
            command_output = _remove_command_prefix(command_output, command)

        # 过滤终端查询序列，这些序列会导致终端在显示时做出响应，从而产生可见的垃圾。 过
        # 滤器是有状态的，可以处理跨块分割的序列。
        #
        command_output = self._query_filter.filter(command_output)
        if is_final:
            # 命令完成时刷新所有挂起的字节
            command_output += self._query_filter.flush()

        return command_output.rstrip()

    def _handle_completed_command(
        self,
        command: str,
        terminal_content: str,
        ps1_matches: list[re.Match],
        echoed_command: str | None = None,
        boundary_exit_code: int | None = None,
    ) -> TerminalObservation:
        """处理已完成的命令。"""
        is_special_key = self._is_special_key(command)
        output_command = echoed_command or command

        # 当 PS1 元数据标记丢失时（e.g.、被 TUI/ANSI 输出损坏或滚动到屏幕外），请优雅地
        # 回退而不是崩溃。 该命令可能已完成，但我们无法提取退出代码或工作目录。
        #
        if len(ps1_matches) == 0 and boundary_exit_code is None:
            logger.warning(
                "No PS1 metadata found in terminal output. "
                "Command output may have overwritten the markers "
                "(e.g., TUI rendering, large output)."
            )
            metadata = CmdOutputMetadata(exit_code=-1, working_dir=self._cwd)
            metadata.suffix = (
                "\n[The command completed but the exit code could not "
                "be determined. Terminal output may have corrupted the "
                "PS1 metadata markers.]"
            )
            command_output = self._get_command_output(
                output_command,
                terminal_content,
                metadata,
                is_final=True,
            )
            command_output = maybe_truncate(
                command_output, truncate_after=MAX_CMD_OUTPUT_SIZE
            )
            self.prev_status = TerminalCommandStatus.COMPLETED
            self.prev_output = ""
            self._query_filter.reset()
            self._ready_for_next_command()
            return TerminalObservation.from_text(
                command=command,
                text=command_output,
                metadata=metadata,
                exit_code=metadata.exit_code,
            )

        if boundary_exit_code is not None:
            metadata = CmdOutputMetadata(
                exit_code=boundary_exit_code, working_dir=self._cwd
            )
            get_content_before_last_match = False
            raw_command_output = self._combine_outputs_between_matches(
                terminal_content, ps1_matches
            )
        else:
            metadata = CmdOutputMetadata.from_ps1_match(ps1_matches[-1])
            get_content_before_last_match = bool(len(ps1_matches) == 1)
            if metadata.working_dir != self._cwd and metadata.working_dir:
                self._cwd = metadata.working_dir
            raw_command_output = self._combine_outputs_between_matches(
                terminal_content,
                ps1_matches,
                get_content_before_last_match=get_content_before_last_match,
            )
            if get_content_before_last_match:
                num_lines = len(raw_command_output.splitlines())
                metadata.prefix = (
                    f"[Previous command outputs are truncated. "
                    f"Showing the last {num_lines} lines of the output below.]\n"
                )

        logger.debug(
            "Parsed terminal output (previous_ps1_not_matched=%s, content_length=%s)",
            get_content_before_last_match,
            len(terminal_content),
        )

        metadata.suffix = (
            f"\n[The command completed with exit code {metadata.exit_code}.]"
            if not is_special_key
            else (
                f"\n[The command completed with exit code {metadata.exit_code}. "
                f"CTRL+{command[-1].upper()} was sent.]"
            )
        )
        command_output = self._get_command_output(
            output_command,
            raw_command_output,
            metadata,
            is_final=True,  # 命令完成，刷新过滤器状态
        )
        command_output = maybe_truncate(
            command_output, truncate_after=MAX_CMD_OUTPUT_SIZE
        )

        self.prev_status = TerminalCommandStatus.COMPLETED
        self.prev_output = ""  # 重置之前的命令输出
        self._query_filter.reset()  # 重置下一个命令的过滤器
        self._ready_for_next_command()
        return TerminalObservation.from_text(
            command=command,
            text=command_output,
            metadata=metadata,
            exit_code=metadata.exit_code,
        )

    def _handle_nochange_timeout_command(
        self,
        command: str,
        terminal_content: str,
        ps1_matches: list[re.Match],
        echoed_command: str | None = None,
    ) -> TerminalObservation:
        """处理由于没有输出更改而超时的命令。"""
        self.prev_status = TerminalCommandStatus.NO_CHANGE_TIMEOUT
        if len(ps1_matches) != 1:
            logger.warning(
                "Expected exactly one PS1 metadata block before command execution, "
                "but got %s (content_length=%s)",
                len(ps1_matches),
                len(terminal_content),
            )
        raw_command_output = self._combine_outputs_between_matches(
            terminal_content, ps1_matches
        )
        metadata = CmdOutputMetadata()  # 没有可用的元数据
        metadata.suffix = (
            f"\n[The command has no new output after "
            f"{self.no_change_timeout_seconds} seconds. {TIMEOUT_MESSAGE_TEMPLATE}]"
        )
        command_output = self._get_command_output(
            echoed_command or command,
            raw_command_output,
            metadata,
            continue_prefix="[Below is the output of the previous command.]\n",
        )
        command_output = maybe_truncate(
            command_output, truncate_after=MAX_CMD_OUTPUT_SIZE
        )
        return TerminalObservation.from_text(
            command=command,
            text=command_output,
            metadata=metadata,
            exit_code=metadata.exit_code,
        )

    def _handle_hard_timeout_command(
        self,
        command: str,
        terminal_content: str,
        ps1_matches: list[re.Match],
        timeout: float,
        echoed_command: str | None = None,
    ) -> TerminalObservation:
        """处理由于硬超时而超时的命令。"""
        self.prev_status = TerminalCommandStatus.HARD_TIMEOUT
        if len(ps1_matches) != 1:
            logger.warning(
                "Expected exactly one PS1 metadata block before command execution, "
                "but got %s (content_length=%s)",
                len(ps1_matches),
                len(terminal_content),
            )
        raw_command_output = self._combine_outputs_between_matches(
            terminal_content, ps1_matches
        )
        metadata = CmdOutputMetadata()  # 没有可用的元数据
        metadata.suffix = (
            f"\n[The command timed out after {timeout} seconds. "
            f"{TIMEOUT_MESSAGE_TEMPLATE}]"
        )
        command_output = self._get_command_output(
            echoed_command or command,
            raw_command_output,
            metadata,
            continue_prefix="[Below is the output of the previous command.]\n",
        )
        command_output = maybe_truncate(
            command_output, truncate_after=MAX_CMD_OUTPUT_SIZE
        )
        return TerminalObservation.from_text(
            command=command,
            exit_code=metadata.exit_code,
            text=command_output,
            metadata=metadata,
        )

    def _ready_for_next_command(self) -> None:
        """重置新命令的内容缓冲区。"""
        # 清除当前内容
        self.terminal.clear_screen()

    def _strip_boundary_wrapper(self, terminal_content: str) -> str:
        """从原始屏幕读取中删除heredoc完成后缀。"""
        if self._boundary_marker is not None:
            terminal_content = self._boundary_marker.sub("", terminal_content)
            terminal_content = terminal_content.replace("\x1b[?2004l", "").replace(
                "\x1b[?2004h", ""
            )
        if self._boundary_echo:
            terminal_content = terminal_content.replace(self._boundary_echo, "")
            terminal_content = _remove_echoed_line(
                terminal_content, self._boundary_echo
            )
        if self._wrapper_echo:
            terminal_content = _remove_command_prefix(
                terminal_content, self._wrapper_echo
            )
        return terminal_content

    def _combine_outputs_between_matches(
        self,
        terminal_content: str,
        ps1_matches: list[re.Match],
        get_content_before_last_match: bool = False,
    ) -> str:
        """合并 PS1 个匹配之间的所有输出。"""
        if len(ps1_matches) == 1:
            if get_content_before_last_match:
                # 命令输出为最后一个PS1提示词之前的内容
                return terminal_content[: ps1_matches[0].start()]
            else:
                # 命令输出为最后一个PS1提示词之后的内容
                return terminal_content[ps1_matches[0].end() + 1 :]
        elif len(ps1_matches) == 0:
            return terminal_content
        combined_output = ""
        for i in range(len(ps1_matches) - 1):
            # 提取当前和下一个 PS1 提示词之间的内容
            output_segment = terminal_content[
                ps1_matches[i].end() + 1 : ps1_matches[i + 1].start()
            ]
            combined_output += output_segment + "\n"
        # 添加最后一个PS1提示词后面的内容
        combined_output += terminal_content[ps1_matches[-1].end() + 1 :]
        logger.debug(
            "Combined terminal output (content_length=%s)", len(combined_output)
        )
        return combined_output

    def execute(self, action: TerminalAction) -> TerminalObservation:
        """使用终端后端执行命令。"""
        if not self._initialized:
            raise RuntimeError("Unified session is not initialized")

        # 去除命令中的任何前导/尾随空格
        logger.debug(
            "Received terminal action (is_input=%s, command_length=%s)",
            action.is_input,
            len(action.command),
        )
        command = action.command.strip()
        is_input: bool = action.is_input

        rejection = foreground_timeout_rejection_for(
            command=command,
            is_input=is_input,
            timeout=action.timeout,
        )
        if rejection is not None:
            return TerminalObservation.from_text(
                text=rejection,
                command=command,
                is_error=True,
            )

        # 如果前面的命令没有完成，我们需要检查命令是否为空
        #
        if self.prev_status not in {
            TerminalCommandStatus.CONTINUE,
            TerminalCommandStatus.NO_CHANGE_TIMEOUT,
            TerminalCommandStatus.HARD_TIMEOUT,
        }:
            if command == "":
                return TerminalObservation.from_text(
                    text="No previous running command to retrieve logs from.",
                    command=command,
                    is_error=True,
                )
            if is_input:
                return TerminalObservation.from_text(
                    text="No previous running command to interact with.",
                    command=command,
                    is_error=True,
                )

        # 检查命令是单个命令还是多个命令
        splited_commands = split_bash_commands(command)
        if len(splited_commands) > 1:
            commands_list = "\n".join(
                f"({i + 1}) {cmd}" for i, cmd in enumerate(splited_commands)
            )
            return TerminalObservation.from_text(
                text=(
                    "Cannot execute multiple commands at once.\n"
                    "Please run each command separately OR chain them into a single "
                    f"command via && or ;\nProvided commands:\n{commands_list}"
                ),
                command=command,
                is_error=True,
            )

        # 发送命令前获取初始状态
        initial_terminal_output = self.terminal.read_screen()
        initial_ps1_matches = CmdOutputMetadata.matches_ps1_metadata(
            initial_terminal_output
        )
        initial_ps1_count = len(initial_ps1_matches)
        logger.debug(f"Initial PS1 count: {initial_ps1_count}")
        logger.debug(
            "Initial terminal output (content_length=%s)",
            len(initial_terminal_output),
        )

        start_time = time.time()
        last_change_time = start_time
        last_terminal_output = initial_terminal_output

        # 当上一个命令仍在运行，并且我们正在尝试发送新命令时
        if (
            self.prev_status
            in {
                TerminalCommandStatus.HARD_TIMEOUT,
                TerminalCommandStatus.NO_CHANGE_TIMEOUT,
            }
            and not last_terminal_output.rstrip().endswith(CMD_OUTPUT_PS1_END.rstrip())
            and not is_input
            and command != ""
        ):
            last_terminal_output = self._strip_boundary_wrapper(last_terminal_output)
            _ps1_matches = CmdOutputMetadata.matches_ps1_metadata(last_terminal_output)
            # 如果 _ps1_matches 为空，则使用 initial_ps1_matches，否则使用 _ps1_matches
            # 。 这处理了提示词可能滚动到屏幕之外但之前就存在的情况
            #
            current_matches_for_output = (
                _ps1_matches if _ps1_matches else initial_ps1_matches
            )
            raw_command_output = self._combine_outputs_between_matches(
                last_terminal_output, current_matches_for_output
            )
            metadata = CmdOutputMetadata()  # 没有可用的元数据
            metadata.suffix = (
                f'\n[Your command "{command}" is NOT executed. The previous command '
                f"is still running - You CANNOT send new commands until the previous "
                f"command is completed. By setting `is_input` to `true`, you can "
                f"interact with the current process: {TIMEOUT_MESSAGE_TEMPLATE}]"
            )
            logger.debug(
                "Previous command output (content_length=%s)",
                len(raw_command_output),
            )
            command_output = self._get_command_output(
                command,
                raw_command_output,
                metadata,
                continue_prefix="[Below is the output of the previous command.]\n",
            )
            command_output = maybe_truncate(
                command_output, truncate_after=MAX_CMD_OUTPUT_SIZE
            )
            obs = TerminalObservation.from_text(
                command=command,
                text=command_output,
                metadata=metadata,
                exit_code=metadata.exit_code,
                is_error=True,
            )
            return obs

        command_to_send = command
        boundary_command: str | None = None
        command_boundary_marker: re.Pattern[str] | None = None
        if command and not is_input:
            self._boundary_marker = None
            self._boundary_echo = None
            self._wrapper_echo = None
        if command and not is_input and not self.terminal.is_powershell():
            if needs_heredoc_completion_boundary(command_to_send):
                marker_id = uuid.uuid4().hex
                marker_start = f"__OH_COMMAND_FINISHED_{marker_id}_"
                marker_end = "__"
                command_boundary_marker = re.compile(
                    rf"{re.escape(marker_start)}(?P<exit_code>\d+){marker_end}"
                )
                boundary_command = (
                    "(__openhands_status=$?; printf '\\n%s%s%s\\n' "
                    f"'{marker_start}' \"$__openhands_status\" '{marker_end}' "
                    '> /dev/tty; exit "$__openhands_status")'
                )
                self._boundary_marker = command_boundary_marker
            command_to_send = escape_bash_special_chars(command_to_send)
            if boundary_command is not None:
                self._boundary_echo = boundary_command
                self._wrapper_echo = command_to_send

        # 将实际命令/输入发送到终端
        sent_command = command != ""
        if command != "":
            is_special_key = self._is_special_key(command)
            if is_input:
                logger.debug(
                    "Sending input to running process (input_length=%s)", len(command)
                )
                self.terminal.send_keys(
                    command,
                    enter=not is_special_key,
                )
            else:
                logger.debug(
                    "Sending command (command_length=%s)", len(command_to_send)
                )
                self.terminal.send_keys(
                    command_to_send,
                    enter=not is_special_key,
                )
                if boundary_command is not None:
                    self.terminal.send_keys(boundary_command)

        # 循环直到命令完成或超时
        while True:
            # 关闭的终端永远不会显示命令完成，并且带有超时的命令会跳过无更改超时，因此请
            # 停止在此处等待。
            #
            if self._closed or self.terminal.closed:
                return TerminalObservation.from_text(
                    text="[The terminal was closed while the command was running.]",
                    command=command,
                    exit_code=-1,
                    is_error=True,
                )
            _start_time = time.time()
            logger.debug(f"GETTING TERMINAL CONTENT at {_start_time}")
            cur_terminal_output = self.terminal.read_screen()
            logger.debug(
                f"TERMINAL CONTENT GOT after {time.time() - _start_time:.2f} seconds"
            )
            logger.debug(
                "Terminal content read (content_length=%s)", len(cur_terminal_output)
            )
            ps1_matches = CmdOutputMetadata.matches_ps1_metadata(cur_terminal_output)
            current_ps1_count = len(ps1_matches)
            output_changed_since_command = (
                cur_terminal_output != initial_terminal_output
            )
            active_boundary_marker = command_boundary_marker or self._boundary_marker
            boundary_match = (
                active_boundary_marker.search(cur_terminal_output)
                if active_boundary_marker is not None
                else None
            )
            command_reached_boundary = (
                active_boundary_marker is None or boundary_match is not None
            )

            if cur_terminal_output != last_terminal_output:
                last_terminal_output = cur_terminal_output
                last_change_time = time.time()
                logger.debug(f"CONTENT UPDATED DETECTED at {last_change_time}")

            # 1) 当出现提示词或heredoc时执行完成
            # stdout 重定向后，后缀到达其 tty 边界。
            prompt_reached = current_ps1_count > initial_ps1_count or (
                cur_terminal_output.rstrip().endswith(CMD_OUTPUT_PS1_END.rstrip())
            )
            if (
                command_reached_boundary
                and (not sent_command or output_changed_since_command)
                and (prompt_reached or boundary_match is not None)
            ):
                completed_terminal_output = cur_terminal_output
                boundary_exit_code = None
                if active_boundary_marker is not None:
                    completed_terminal_output = self._strip_boundary_wrapper(
                        completed_terminal_output
                    )
                    if not prompt_reached and boundary_match is not None:
                        boundary_exit_code = int(boundary_match.group("exit_code"))
                completed_ps1_matches = CmdOutputMetadata.matches_ps1_metadata(
                    completed_terminal_output
                )
                obs = self._handle_completed_command(
                    command,
                    terminal_content=completed_terminal_output,
                    ps1_matches=completed_ps1_matches,
                    boundary_exit_code=boundary_exit_code,
                )
                return obs

            # 仅当新的提示词尚未出现时才应触发超时检查。

            # 2) 由于输出没有变化，执行超时
            # 一段时间 (NO_CHANGE_TIMEOUT_SECONDS) 如果命令是 * 阻塞 *，我们会忽略它
            #
            time_since_last_change = time.time() - last_change_time
            is_blocking = action.timeout is not None
            logger.debug(
                f"CHECKING NO CHANGE TIMEOUT ({self.no_change_timeout_seconds}s): "
                f"elapsed {time_since_last_change}. Action blocking: {is_blocking}"
            )
            if (
                not is_blocking
                and self.no_change_timeout_seconds is not None
                and time_since_last_change >= self.no_change_timeout_seconds
            ):
                stripped_output = self._strip_boundary_wrapper(cur_terminal_output)
                obs = self._handle_nochange_timeout_command(
                    command,
                    terminal_content=stripped_output,
                    ps1_matches=CmdOutputMetadata.matches_ps1_metadata(stripped_output),
                    echoed_command=(
                        command_to_send if command_boundary_marker is not None else None
                    ),
                )
                return obs

            # 3) 由于命令运行时间过长，执行超时
            # （硬超时）
            elapsed_time = time.time() - start_time
            logger.debug(
                f"CHECKING HARD TIMEOUT ({action.timeout}s): elapsed {elapsed_time:.2f}"
            )
            if action.timeout is not None:
                time_since_start = time.time() - start_time
                if time_since_start >= action.timeout:
                    stripped_output = self._strip_boundary_wrapper(cur_terminal_output)
                    obs = self._handle_hard_timeout_command(
                        command,
                        terminal_content=stripped_output,
                        ps1_matches=CmdOutputMetadata.matches_ps1_metadata(
                            stripped_output
                        ),
                        timeout=action.timeout,
                        echoed_command=(
                            command_to_send
                            if command_boundary_marker is not None
                            else None
                        ),
                    )
                    return obs

            # 与命令的运行时间成比例进行轮询，以便在几毫秒内注意到短命令，而不是在下一个
            #  POLL_INTERVAL 刻度处。
            #
            time.sleep(min(POLL_INTERVAL, max(MIN_POLL_INTERVAL, elapsed_time / 4)))
