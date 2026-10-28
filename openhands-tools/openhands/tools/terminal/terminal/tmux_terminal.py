"""tmux基于终端后端的实现。"""

import logging
import os
import shlex
import sys
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from pathlib import Path

import libtmux
from filelock import FileLock

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.redact import redact_api_key_literals
from openhands.tools.terminal.constants import (
    HISTORY_LIMIT,
    TMUX_SESSION_HEIGHT,
    TMUX_SESSION_WIDTH,
    TMUX_SOCKET_CREATION_LOCK,
    TMUX_SOCKET_NAME,
    TMUX_SOCKET_OWNER_OPTION,
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


class _SecretRedactFilter(logging.Filter):
    """从 libtmux 日志记录中编辑 API 个关键文字。"""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg and isinstance(record.msg, str):
            record.msg = redact_api_key_literals(record.msg)
        if record.args:
            if isinstance(record.args, Mapping):
                record.args = {
                    k: redact_api_key_literals(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_api_key_literals(a) if isinstance(a, str) else a
                    for a in record.args
                )
        tmux_cmd = getattr(record, "tmux_cmd", None)
        if tmux_cmd and isinstance(tmux_cmd, str):
            record.tmux_cmd = redact_api_key_literals(tmux_cmd)
        return True


def _install_libtmux_redaction_filter() -> None:
    logger_names = [
        "libtmux",
        *(
            name
            for name, candidate in logging.Logger.manager.loggerDict.items()
            if name.startswith("libtmux.") and isinstance(candidate, logging.Logger)
        ),
    ]
    for logger_name in logger_names:
        libtmux_logger = logging.getLogger(logger_name)
        if not any(
            isinstance(log_filter, _SecretRedactFilter)
            for log_filter in libtmux_logger.filters
        ):
            libtmux_logger.addFilter(_SecretRedactFilter())


@contextmanager
def _socket_creation_lock(socket_dir: Path | None = None) -> Iterator[None]:
    """序列化套接字创建与智能体-服务器的启动清理。

    tmux 套接字存在于 ``new-session`` 和其所有者选项记录之间。 在兄弟智能体服务器的启
    动清理中，处理没有所有者的套接字，因此如果没有这个锁，可以杀
    死一个没有完成初始化的活套接字。 锁文件位于 tmux 服务端目录，这是所有共享
    ``TMUX_TMPDIR`` 的进程都同意的路径，即使 tmux 也没有创建任何
    套接字。
    """
    if socket_dir is None:
        socket_dir = Path(os.environ.get("TMUX_TMPDIR", "/tmp")) / f"tmux-{os.getuid()}"
    # tmux 拒绝组/世界可访问的套接字目录，而 FileLock 将使用默认 umask 创建它，因此首先
    # 创建它 0700。
    #
    socket_dir.mkdir(parents=True, exist_ok=True)
    with suppress(OSError):
        socket_dir.chmod(0o700)
    with FileLock(socket_dir / TMUX_SOCKET_CREATION_LOCK):
        yield


def mark_socket_owner(server: libtmux.Server) -> None:
    """将此进程记录为 *server* 套接字的所有者。

    当共享 ``TMUX_TMPDIR`` 正在使用时，智能体-服务器的启动清理会读取此信息以区分活动
    同级套接字和过时套接字。 尽力而为：这里的失败只会丢失所有权提示，
    因此它绝不能破坏终端设置。
    """
    with suppress(Exception):
        server.set_option(
            TMUX_SOCKET_OWNER_OPTION, str(os.getpid()), global_=True, scope=None
        )


def _new_owned_session(
    env: Mapping[str, str],
    *,
    session_name: str,
    start_directory: str,
    x: int,
    y: int,
) -> tuple[libtmux.Server, libtmux.Session]:
    """在此进程拥有的新套接字上创建 tmux 会话。

    只有在会话创建后，套接字才开始存在，因此会话被创建并记录其所有者，同时保持跨进程
    创建锁。 另一个进程中的启动清理采用相同的锁，因此在套接字所有者发布之前它永远无法
    观
    察到套接字。
    """
    socket_name = f"{TMUX_SOCKET_NAME}-{uuid.uuid4().hex}"
    socket_dir = Path(os.environ.get("TMUX_TMPDIR", "/tmp")) / f"tmux-{os.getuid()}"
    socket_path = socket_dir / socket_name
    # sun_path包含NUL字节； Linux 上的限制为 108，macOS/BSD 上的限制为 104。
    max_socket_path = 107 if sys.platform.startswith("linux") else 103
    fallback = (
        os.name == "posix"
        and len(os.fsencode(os.path.realpath(socket_path))) > max_socket_path
    )
    if fallback:
        socket_dir = Path("/tmp") / f"tmux-{os.getuid()}"
        # libtmux 使用进程范围 TMUX_TMPDIR 解析 socket_name，因此使用显式路径而不更改其
        # 他会话的环境。
        #
        logger.warning("tmux socket path is too long; using %s", socket_dir)

    with _socket_creation_lock(socket_dir):
        server = libtmux.Server(
            socket_name=None if fallback else socket_name,
            socket_path=str(socket_dir / socket_name) if fallback else None,
        )
        session = server.new_session(
            session_name=session_name,
            start_directory=start_directory,
            kill_session=True,
            x=x,
            y=y,
        )
        mark_socket_owner(server)
    # tmux 服务器以此进程的环境而不是 *env* 启动，并且新窗口会继承它，因此请取消设置删除
    # 的清理内容。
    #
    for key in os.environ.keys() - env.keys():
        server.unset_environment(key)
    return server, session


# 将规范化的特殊键名称映射到 tmux 键名称。
_TMUX_SPECIALS: dict[str, str] = {
    "ENTER": "Enter",
    "TAB": "Tab",
    "BS": "BSpace",
    "ESC": "Escape",
    "UP": "Up",
    "DOWN": "Down",
    "LEFT": "Left",
    "RIGHT": "Right",
    "HOME": "Home",
    "END": "End",
    "PGUP": "PPage",
    "PGDN": "NPage",
    "C-L": "C-l",
    "C-D": "C-d",
    "C-C": "C-c",
}


class TmuxTerminal(TerminalInterface):
    """基于tmux的终端后端。

    该后端使用 tmux 提供具有全屏捕获和历史管理功能的持久终端会话。
    """

    PS1: str
    server: libtmux.Server
    session: libtmux.Session
    window: libtmux.Window
    pane: libtmux.Pane

    def __init__(
        self,
        work_dir: str,
        username: str | None = None,
        env: Mapping[str, str] | None = None,
    ):
        super().__init__(work_dir, username)
        _install_libtmux_redaction_filter()
        self.PS1 = CmdOutputMetadata.to_ps1_prompt()
        self._env = normalize_terminal_env(env)

    def initialize(self) -> None:
        """初始化 tmux 终端会话。"""
        if self._initialized:
            return

        env = build_terminal_env(self._env)
        # 禁用交互式寻呼机（git、man、systemctl...），以便在 TTY 上自动启动 `less` 的命
        # 令不会捕获窗格并楔入会话。
        #
        env.setdefault("GIT_PAGER", "cat")
        env.setdefault("PAGER", "cat")
        shell_command = ["/bin/bash"]
        if self.username in ["root", "openhands"]:
            # 这将为给定用户启动一个非登录（新）shell
            shell_command = ["su", self.username, "-"]

        window_command = shlex.join([*process_priority_prefix(env), *shell_command])

        logger.debug(f"Initializing tmux terminal with command: {window_command}")
        # 切勿重用套接字：tmux 数字 ID 在服务器退出后从零重新启动。
        session_name = f"openhands-{self.username}-{uuid.uuid4()}"
        self.server, self.session = _new_owned_session(
            env,
            session_name=session_name,
            start_directory=self.work_dir,
            x=TMUX_SESSION_WIDTH,
            y=TMUX_SESSION_HEIGHT,
        )
        for k, v in env.items():
            self.session.set_environment(k, v)

        # 将历史记录限制设置为较大的数字以避免丢失历史记录
        # https://unix.stackexchange.com/questions/43414/unlimited-history-in-tmux
        self.session.set_option("history-limit", str(HISTORY_LIMIT))
        self.session.history_limit = str(HISTORY_LIMIT)

        # 创建一个新窗格，因为初始窗格的历史记录限制为（默认）2000
        _initial_window = self.session.active_window
        self.window = self.session.new_window(
            window_name="terminal",
            window_shell=window_command,
            start_directory=self.work_dir,
        )
        active_pane = self.window.active_pane
        assert active_pane is not None, "Window should have an active pane"
        self.pane = active_pane
        logger.debug(f"pane: {self.pane}; history_limit: {self.session.history_limit}")
        _initial_window.kill()

        # 配置 bash 使用 simple PS1 并禁用 PS2 禁用历史扩展以避免！ 损坏
        #
        self.pane.send_keys(
            f'set +H; export PROMPT_COMMAND=\'export PS1="{self.PS1}"\'; export PS2=""'
        )
        time.sleep(0.1)  # 等待命令生效

        logger.debug(f"Tmux terminal initialized with work dir: {self.work_dir}")
        self._initialized: bool = True
        self.clear_screen()

    def close(self) -> None:
        """清理 tmux 会话。"""
        if self._closed:
            return
        try:
            if hasattr(self, "session"):
                self.session.kill()
        except Exception as e:
            # 会话可能已经在外部死亡/终止（e.g。，来自 tmux 的“找不到会话”错误）还在
            # Python 关闭期间处理 ImportError
            #
            logger.debug(f"Error closing tmux session (may already be dead): {e}")
        self._closed: bool = True

    def send_keys(self, text: str, enter: bool = True) -> None:
        """将文本/按键发送到 tmux 窗格。

        支持：
          - 纯文本（使用文字粘贴； 保留空格/换行符）
          - 命名特价：ENTER、TAB、BS、ESC、UP、DOWN、LEFT、RIGHT、HOME、END、PGUP、
          PGDN、C-L、C-D、C-C
          - 通用 Ctrl 序列：C-a..C-z、CTRL-x、CTRL+x

        Args:
            text: 要发送的文本或按键序列
            enter: 是否在文本后发送回车键。
                   忽略特殊/ctrl 键。
        """
        if not self._initialized or not isinstance(self.pane, libtmux.Pane):
            raise RuntimeError("Tmux terminal is not initialized")

        # 将规范化名称映射到 tmux 键名称
        upper = text.strip().upper()

        # 1) 指定特价商品
        if upper in _TMUX_SPECIALS:
            self.pane.send_keys(_TMUX_SPECIALS[upper], enter=False)
            return

        # 2) 通用 Ctrl-<letter>
        ctrl = parse_ctrl_key(text)
        if ctrl is not None:
            self.pane.send_keys(ctrl, enter=False)
            return

        # 3) 纯文本 — 使用literal=True，这样 tmux 不会在空格上分割或解释特殊的 token。
        #
        self.pane.send_keys(text, enter=False, literal=True)
        if enter and not text.endswith("\n"):
            self.pane.send_keys("Enter", enter=False)

    def read_screen(self) -> str:
        """读取当前 tmux 窗格内容。

        Returns:
            tmux 窗格的当前可见内容
        """
        if not self._initialized or not isinstance(self.pane, libtmux.Pane):
            raise RuntimeError("Tmux terminal is not initialized")

        content = "\n".join(
            map(
                # 避免双换行
                lambda line: line.rstrip(),
                self.pane.cmd("capture-pane", "-J", "-pS", "-").stdout,
            )
        )
        return content

    def clear_screen(self) -> None:
        """清除 tmux 窗格屏幕和历史记录。

        我们有意避免发送 ``C-l``（Ctrl+L），因为控制字符 ``^L``（form-feed control
        character）可能会泄露到 SSH
        连接的 shell 输入缓冲区中。

        相反，我们运行 ``clear`` 命令来清除可见屏幕，然后使用 tmux 的
        ``clear-history`` 来删除回滚缓冲区。
        """
        if not self._initialized or not isinstance(self.pane, libtmux.Pane):
            raise RuntimeError("Tmux terminal is not initialized")

        self.pane.send_keys("clear", enter=True)
        time.sleep(0.1)
        self.pane.cmd("clear-history")

    def interrupt(self) -> bool:
        """发送中断信号(Ctrl+C)到tmux窗格。

        Returns:
            True 如果中断发送成功，False 否则
        """
        if not self._initialized or not isinstance(self.pane, libtmux.Pane):
            return False
        try:
            self.pane.send_keys("C-c", enter=False)
            return True
        except Exception as e:
            logger.error(f"Failed to interrupt command: {e}", exc_info=True)
            return False

    def is_running(self) -> bool:
        """检查命令当前是否正在运行。

        对于 tmux，我们通过检查终端是否准备好接受新命令（以提示词结尾）来确定这一点。
        """
        if not self._initialized:
            return False

        try:
            content = self.read_screen()
            # 如果屏幕以我们的 PS1 提示词结尾，则没有命令正在运行
            from openhands.tools.terminal.constants import CMD_OUTPUT_PS1_END

            return not content.rstrip().endswith(CMD_OUTPUT_PS1_END.rstrip())
        except Exception:
            return False
