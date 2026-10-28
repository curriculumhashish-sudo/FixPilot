"""基于 PTY 的终端后端实现（取代基于管道的子进程）。"""

import os
import platform
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Mapping


if platform.system() == "Windows":
    raise ImportError(
        "SubprocessTerminal is not supported on Windows "
        "(requires Unix-only modules: fcntl, pty, select)"
    )

import fcntl
import pty
import select

from openhands.sdk.logger import get_logger
from openhands.tools.terminal.constants import (
    CMD_OUTPUT_PS1_BEGIN,
    CMD_OUTPUT_PS1_END,
    HISTORY_LIMIT,
)
from openhands.tools.terminal.env import (
    build_terminal_env,
    normalize_terminal_env,
)
from openhands.tools.terminal.metadata import CmdOutputMetadata
from openhands.tools.terminal.terminal import TerminalInterface
from openhands.tools.terminal.terminal.interface import parse_ctrl_key
from openhands.tools.terminal.terminal.process_priority import (
    process_priority_prefix,
)


logger = get_logger(__name__)

ENTER = b"\n"

# 将规范化的特殊键名称映射到 PTY 的 ANSI 转义字节。
_SUBPROCESS_SPECIALS: dict[str, bytes] = {
    "ENTER": ENTER,
    "TAB": b"\t",
    "BS": b"\x7f",  # 退格键 (DEL)
    "ESC": b"\x1b",
    "UP": b"\x1b[A",
    "DOWN": b"\x1b[B",
    "RIGHT": b"\x1b[C",
    "LEFT": b"\x1b[D",
    "HOME": b"\x1b[H",
    "END": b"\x1b[F",
    "PGUP": b"\x1b[5~",
    "PGDN": b"\x1b[6~",
    "C-L": b"\x0c",  # Ctrl+L
    "C-D": b"\x04",  # Ctrl+D (EOF)
    "C-C": b"\x03",  # Ctrl+C (SIGINT)
}


def _normalize_eols(raw: bytes) -> bytes:
    # CRLF/LF/CR -> CR，因此每个逻辑行都以 TTY 的 \r 结尾
    raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return ENTER.join(raw.split(b"\n"))


class SubprocessTerminal(TerminalInterface):
    """PTY-支持的终端后端。

    在伪终端 (PTY) 中创建交互式 bash，因此程序的行为就像连接到真实终端一样。 初始化使
    用基于哨兵值的握手和提示词检测，而不是盲目睡眠。
    """

    PS1: str
    process: subprocess.Popen | None
    _pty_master_fd: int | None
    output_buffer: deque[str]
    output_lock: threading.Lock
    reader_thread: threading.Thread | None
    _current_command_running: bool

    def __init__(
        self,
        work_dir: str,
        username: str | None = None,
        shell_path: str | None = None,
        env: Mapping[str, str] | None = None,
    ):
        super().__init__(work_dir, username)
        self.PS1 = CmdOutputMetadata.to_ps1_prompt()
        self.process = None
        self._pty_master_fd = None
        # 使用稍大的缓冲区来匹配 tmux 行为，这似乎保持
        # 大约 10,001 行，而不是正好 10,000 行
        self.output_buffer = deque(maxlen=HISTORY_LIMIT + 50)  # 圆形缓冲器
        self.output_lock = threading.Lock()
        self.reader_thread = None
        self._current_command_running = False
        self.shell_path = shell_path
        self._env = normalize_terminal_env(env)

    # -------------------------- 生命周期------------------------

    def initialize(self) -> None:
        """初始化 PTY 终端会话。"""
        if self._initialized:
            return

        # 优先解析 shell 路径：
        # 1. 显式 shell_path 参数
        # 2. 通过 shutil.which("bash") 自动检测（像 `env bash` 一样搜索 PATH）
        resolved_shell_path: str | None
        if self.shell_path:
            resolved_shell_path = self.shell_path
        else:
            resolved_shell_path = shutil.which("bash")
            if resolved_shell_path is None:
                raise RuntimeError(
                    "Could not find bash in PATH. "
                    "Please provide an explicit shell_path parameter "
                    "when creating the terminal."
                )

        # 验证 shell 路径存在且可执行
        if not os.path.isfile(resolved_shell_path):
            raise RuntimeError(
                f"Shell binary not found at: {resolved_shell_path}. "
                "Please provide a valid shell_path parameter."
            )
        if not os.access(resolved_shell_path, os.X_OK):
            raise RuntimeError(
                f"Shell binary is not executable: {resolved_shell_path}. "
                "Please check file permissions."
            )

        # 存储解析的 shell 路径以供以后访问
        self.shell_path = resolved_shell_path
        logger.info(f"Using shell: {resolved_shell_path}")

        # 从父进程继承环境变量
        env = build_terminal_env(self._env)
        # 禁用交互式寻呼机（git、man、systemctl...），以便在 TTY 上自动启动 `less` 的命
        # 令不会捕获 PTY 并楔入会话。
        #
        env.setdefault("GIT_PAGER", "cat")
        env.setdefault("PAGER", "cat")
        env["PS1"] = self.PS1
        env["PS2"] = ""
        env["TERM"] = "xterm-256color"

        bash_cmd = [*process_priority_prefix(env), resolved_shell_path, "-i"]

        # 创建一个PTY； 把奴隶交给孩子，留下主人
        master_fd, slave_fd = pty.openpty()

        logger.debug("Initializing PTY terminal with: %s", " ".join(bash_cmd))
        try:
            self.process = subprocess.Popen(
                bash_cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=self.work_dir,
                env=env,
                text=False,  # 字节输入/输出
                bufsize=0,
                preexec_fn=os.setsid,  # 用于信号处理的新进程组
                close_fds=True,
            )
        finally:
            # 父级必须关闭其从属 FD 的副本
            try:
                os.close(slave_fd)
            except Exception:
                pass

        self._pty_master_fd = master_fd

        # 设置master FD非阻塞
        flags = fcntl.fcntl(self._pty_master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self._pty_master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # 启动输出阅读器线程
        self.reader_thread = threading.Thread(
            target=self._read_output_continuously_pty, daemon=True
        )
        self.reader_thread.start()
        self._initialized: bool = True

        # 配置bash：禁用历史扩展，设置PS1/PS2提示词
        init_cmd = (
            f'set +H; export PROMPT_COMMAND=\'export PS1="{self.PS1}"\'; export PS2=""'
        ).encode("utf-8", "ignore")

        self._write_pty(init_cmd + ENTER)
        time.sleep(1.0)  # 等待命令生效

        self.clear_screen()

        logger.debug("PTY terminal initialized with work dir: %s", self.work_dir)

    def close(self) -> None:
        """清理 PTY 终端。"""
        if self._closed:
            return

        try:
            if self.process:
                # 尝试优雅退出
                try:
                    self._write_pty(b"exit\n")
                except Exception:
                    pass
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # 升级
                    try:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                        self.process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
        except Exception as e:
            logger.error(f"Error closing PTY terminal: {e}", exc_info=True)
        finally:
            # 读卡器线程停止：关闭主控FD； 线程因读取错误而退出/EOF
            try:
                if self._pty_master_fd is not None:
                    os.close(self._pty_master_fd)
            except Exception:
                pass
            self._pty_master_fd = None

            if self.reader_thread and self.reader_thread.is_alive():
                self.reader_thread.join(timeout=1)

            self.process = None
            self._closed: bool = True

    # ------------------------- I/O 核心 -------------------------

    def _write_pty(self, data: bytes) -> None:
        if not self._initialized and self._pty_master_fd is None:
            # 允许在 _initialized 翻转之前调用 init 路径
            raise RuntimeError("PTY master FD not ready")
        if self._pty_master_fd is None:
            raise RuntimeError("PTY terminal is not initialized")
        try:
            logger.debug("Wrote to subprocess PTY (byte_count=%s)", len(data))
            os.write(self._pty_master_fd, data)
        except Exception as e:
            logger.error(f"Failed to write to PTY: {e}", exc_info=True)
            raise

    def _read_output_continuously_pty(self) -> None:
        """在单独的线程中连续读取 PTY 主站的输出。"""
        fd = self._pty_master_fd
        if fd is None:
            return

        try:
            while True:
                # 如果进程死亡则提前退出
                if self.process and self.process.poll() is not None:
                    break

                # 使用 select 避免繁忙旋转
                r, _, _ = select.select([fd], [], [], 0.1)
                if not r:
                    continue

                try:
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break  # EOF
                    # 规范化换行符； PTY 通常已使用 \n
                    text = chunk.decode("utf-8", errors="replace")
                    with self.output_lock:
                        # 每个缓冲区项存储一行以使双端队列截断起作用
                        self._add_text_to_buffer(text)
                except OSError:
                    # 会阻塞或FD关闭
                    continue
                except Exception as e:
                    logger.debug(f"Error reading PTY output: {e}")
                    break
        except Exception as e:
            logger.error(f"PTY reader thread error: {e}", exc_info=True)

    def _add_text_to_buffer(self, text: str) -> None:
        """将文本添加到缓冲区，确保每个缓冲区项目一行。"""
        # 如果最后一个缓冲区项中有部分行，则与新文本合并
        if self.output_buffer and not self.output_buffer[-1].endswith("\n"):
            combined_text = self.output_buffer[-1] + text
            self.output_buffer.pop()  # 去掉部分线
        else:
            combined_text = text

        # 分成几行并将每行添加为单独的缓冲区项
        lines = combined_text.split("\n")

        # 添加所有完整的行（除了最后一行之外的所有行，这可能是部分的）
        for line in lines[:-1]:
            self.output_buffer.append(line + "\n")

        # 添加最后一部分（可能是部分行）
        if lines[-1]:  # 仅在不为空时添加
            self.output_buffer.append(lines[-1])

    # ------------------------- 准备助手 -------------------------

    def _wait_for_output(self, pattern: str | re.Pattern, timeout: float = 5.0) -> bool:
        """等待输出缓冲区包含模式（正则表达式或文字）。"""
        deadline = time.time() + timeout
        is_regex = hasattr(pattern, "search")
        while time.time() < deadline:
            # 快速吸引读者线程
            if self._pty_master_fd is not None:
                select.select([], [], [], 0.02)
            with self.output_lock:
                data = "".join(self.output_buffer)
            if is_regex:
                assert isinstance(pattern, re.Pattern)
                if pattern.search(data):
                    return True
            else:
                assert isinstance(pattern, str)
                if pattern in data:
                    return True
        return False

    def _wait_for_prompt(self, timeout: float = 5.0) -> bool:
        """等待屏幕以我们的 PS1 结束标记结束（提示词可见）。"""
        pat = re.compile(re.escape(CMD_OUTPUT_PS1_END.rstrip()) + r"\s*$")
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.output_lock:
                tail = "".join(self.output_buffer)[-4096:]
            if pat.search(tail):
                return True
            time.sleep(0.05)
        return False

    # ------------------------- 公共 API -------------------------

    # 需要流控发送的多行命令的阈值。 行数多于此的命令使用按节奏逐行发送，以避免压垮
    # shell 的输入处理（请参阅 GitHub 问题 #2181）。 根据经验测试选择的值：shell 输入溢
    # 出通常发生在 macOS 中的 50 多行左右，因此 20 提供了安全裕度。
    #
    _MULTILINE_THRESHOLD: int = 20

    # 当等待 PTY 可写时，超时代表 select()（秒）。
    _SELECT_WRITE_TIMEOUT: float = 0.05

    # 节奏之间的小延迟（秒）。 这种延迟是故意的，不能单独用 select() 代替：select() 仅检
    # 查内核缓冲区可用性，但 PTY 几乎总是可写的。 实际的瓶颈是 shell 的线路规则，它无法
    # 足够快地处理输入。 如果没有这个延迟，长的heredocs仍然会挂在macOS上
    #
    # select() reports the fd as writable. (See GitHub issue #2181)
    _LINE_PACING_DELAY: float = 0.002

    def send_keys(self, text: str, enter: bool = True) -> None:
        """将击键发送到 PTY。

        支持：
          - 纯文本
          - Ctrl 序列：'C-a'..'C-z'（Ctrl+C 发送 ^C 字节）
          - 特殊名称：'ENTER'、'TAB'、'BS'、'ESC'、'UP'、'DOWN'、'LEFT'、'RIGHT'、'
          HOME'、'END'、'
          PGUP'、'PGDN'、'C-L'、'C-D'、'C-C'

        对于超过 _MULTILINE_THRESHOLD 行的多行命令，以分段方式发送，以防止对 shell 的
        输入处理造成过度（修复了 macOS 的 here
        doc 挂起问题，详见 #2181）。
        """
        if not self._initialized:
            raise RuntimeError("PTY terminal is not initialized")

        upper = text.upper().strip()
        payload: bytes | None = None

        # 指定特价商品
        if upper in _SUBPROCESS_SPECIALS:
            payload = _SUBPROCESS_SPECIALS[upper]
            # 执行不自动附加另一个 EOL； 当需要时特殊已经包含它。
            append_eol = False
        # 通用 Ctrl-<letter>
        elif (ctrl := parse_ctrl_key(text)) is not None:
            # ctrl 是“C-x”——提取字母
            key_char = ctrl[-1].upper()
            payload = bytes([ord(key_char) & 0x1F])
            append_eol = False  # Ctrl 组合是“即时”的
        else:
            # 检查这是否是一个长的多行命令，需要分块发送
            input_lines = text.split("\n")
            if len(input_lines) > self._MULTILINE_THRESHOLD:
                self._send_multiline_with_flow_control(input_lines, enter)
                return

            raw = text.encode("utf-8", "ignore")
            payload = _normalize_eols(raw) if enter else raw
            append_eol = enter and not payload.endswith(ENTER)

        if append_eol:
            payload += ENTER

        self._write_pty(payload)
        self._current_command_running = self._current_command_running or (
            append_eol or payload.endswith(ENTER)
        )

    def _wait_for_pty_writable(self, timeout: float) -> bool:
        """等待 PTY 准备好使用 select() 进行写入。

        如果 PTY 可写，则返回 True；如果超时发生，则返回 False。
        """
        if self._pty_master_fd is None:
            return False
        _, writable, _ = select.select([], [self._pty_master_fd], [], timeout)
        return len(writable) > 0

    def _send_multiline_with_flow_control(self, lines: list[str], enter: bool) -> None:
        """发送具有流量控制和节奏的多行命令。

        使用 select() 确保 PTY 可写，并加上一个小的行间延迟来调整节奏。 延迟是必要的
        ，因为select()只检查内核缓冲区空间，而不检查shell输
        入处理能力。
        """
        for i, line in enumerate(lines):
            is_last = i == len(lines) - 1
            payload = line.encode("utf-8", "ignore")

            # 在行与行之间添加换行符，如果输入=True则在末尾添加换行符
            if not is_last or enter:
                payload += ENTER

            # 等待 PTY 可写（处理内核缓冲区背压）
            self._wait_for_pty_writable(self._SELECT_WRITE_TIMEOUT)

            self._write_pty(payload)

            # 在行之间添加小的节奏延迟（处理 shell 处理）
            if not is_last:
                time.sleep(self._LINE_PACING_DELAY)

        self._current_command_running = True

    def read_screen(self) -> str:
        """读取当前终端屏幕内容。

        我们返回的内容应该不包含回车符（CR，\r）。
        """
        if not self._initialized:
            raise RuntimeError("PTY terminal is not initialized")

        # 给读者线程一点时间来捕获任何待处理的输出这在发送命令后尤其重要
        #
        time.sleep(0.01)

        with self.output_lock:
            content = "".join(self.output_buffer)
            lines = content.split("\n")
            content = "\n".join(lines).replace("\r", "")
            logger.debug("Read from subprocess PTY (content_length=%s)", len(content))
            return content

    def clear_screen(self) -> None:
        """将缓冲输出删除到最近的 PS1 块； 不发出 ^L。"""
        if not self._initialized:
            return

        need_prompt_nudge = False
        with self.output_lock:
            if not self.output_buffer:
                need_prompt_nudge = True
            else:
                data = "".join(self.output_buffer)
                start_idx = data.rfind(CMD_OUTPUT_PS1_BEGIN)
                end_idx = data.rfind(CMD_OUTPUT_PS1_END)
                if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
                    tail = data[start_idx:]
                    self.output_buffer.clear()
                    self.output_buffer.append(tail)
                else:
                    self.output_buffer.clear()
                    need_prompt_nudge = True

        if need_prompt_nudge:
            try:
                self._write_pty(ENTER)  # 要求 bash 渲染提示词，没有屏幕清晰
            except Exception:
                pass

    def interrupt(self) -> bool:
        """将 SIGINT 发送到 PTY 进程组（回退方案发送到基于信号的中断）。"""
        if not self._initialized or not self.process:
            return False

        try:
            os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
            self._current_command_running = False
            return True
        except Exception as e:
            logger.error(f"Failed to interrupt subprocess: {e}", exc_info=True)
            return False

    def is_running(self) -> bool:
        """Heuristic: 如果不在 PS1 提示词并且进程处于活动状态，则命令运行。"""
        if not self._initialized or not self.process:
            return False

        # 检查进程是否还活着
        if self.process.poll() is not None:
            return False

        try:
            content = self.read_screen()
            # 如果屏幕以提示词结束，则没有命令正在运行
            return not content.rstrip().endswith(CMD_OUTPUT_PS1_END.rstrip())
        except Exception:
            return self._current_command_running
