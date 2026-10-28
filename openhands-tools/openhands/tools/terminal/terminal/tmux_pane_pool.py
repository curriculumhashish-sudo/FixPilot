"""用于并行终端命令执行的 tmux 窗格池。

在单个 tmux 会话中维护固定大小的 TmuxTerminal 实例池，从而支持跨窗格执行并发命令。
"""

from __future__ import annotations

import shlex
import threading
import time
import uuid
from collections import deque
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Final

import libtmux

from openhands.sdk.logger import get_logger
from openhands.tools.terminal.constants import (
    HISTORY_LIMIT,
    TMUX_SESSION_HEIGHT,
    TMUX_SESSION_WIDTH,
)
from openhands.tools.terminal.env import (
    build_terminal_env,
    normalize_terminal_env,
)
from openhands.tools.terminal.terminal.process_priority import (
    process_priority_prefix,
)
from openhands.tools.terminal.terminal.tmux_terminal import (
    TmuxTerminal,
    _new_owned_session,
)


logger = get_logger(__name__)

DEFAULT_MAX_PANES: Final[int] = 4


class PooledTmuxTerminal(TmuxTerminal):
    """在窗格池中使用的 TmuxTerminal 变体。

    覆盖 ``close()`` 以仅终止此终端的窗口而不是整个共享 tmux 会话。 这很关键，因为
    ``TerminalSessionBase.__del__`` 调用 ``close()``，以及缓存的 GC
    ``TerminalSession`` 包装器否则会破坏所有其他池窗格所依赖的会话。
    """

    def close(self) -> None:
        if not self._closed:
            with suppress(Exception):
                self.window.kill()
            self._closed = True


@dataclass(slots=True)
class PaneHandle:
    """一个可修改的检查出的窗格的引用，用于上下文管理器目标。"""

    terminal: PooledTmuxTerminal


@dataclass(slots=True)
class TmuxPanePool:
    """用于并行终端执行的线程安全 tmux 窗格池。

    每个窗格都是完全配置的 TmuxTerminal，共享单个 tmux 会话。 调用者签出一个窗格，运
    行命令，然后将其重新签入。 信号量将并发限制为
    ``max_panes``。

    用途：

        pool = TmuxPanePool("/workspace", max_panes=4)
        pool.initialize()

        terminal = pool.checkout()
        terminal.send_keys("echo hello")
        output = terminal.read_screen()
        pool.checkin(terminal)

        pool.close()
    """

    work_dir: str
    username: str | None = None
    env: Mapping[str, str] | None = None
    max_panes: int = DEFAULT_MAX_PANES

    # tmux 手柄
    _server: libtmux.Server | None = field(default=None, init=False, repr=False)
    _session: libtmux.Session | None = field(default=None, init=False, repr=False)

    # 池状态 — 由 _lock 保护
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )
    _available: deque[PooledTmuxTerminal] = field(
        default_factory=deque, init=False, repr=False
    )
    _all_panes: list[PooledTmuxTerminal] = field(
        default_factory=list, init=False, repr=False
    )
    _semaphore: threading.Semaphore = field(init=False, repr=False)

    _initialized: bool = field(default=False, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _initial_window: libtmux.Window | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_panes < 1:
            raise ValueError(f"max_panes must be >= 1, but got {self.max_panes}.")
        self.env = normalize_terminal_env(self.env)
        self._semaphore = threading.Semaphore(self.max_panes)

    def initialize(self) -> None:
        """创建 tmux 会话（在结帐时延迟添加窗格）。"""
        if self._initialized:
            return

        env = build_terminal_env(self.env)
        session_name = f"openhands-pool-{self.username}-{uuid.uuid4()}"
        # tmux 重新启动后，陈旧句柄不得到达另一个池。
        self._server, self._session = _new_owned_session(
            env,
            session_name=session_name,
            start_directory=self.work_dir,
            x=TMUX_SESSION_WIDTH,
            y=TMUX_SESSION_HEIGHT,
        )
        for k, v in env.items():
            self._session.set_environment(k, v)
        self._session.set_option("history-limit", str(HISTORY_LIMIT))

        # 保留默认窗口的引用，以便在第一个真正的平铺窗口创建后杀死它(tmux至少需要一个窗
        # 口才能保持会话的存活）。
        #
        self._initial_window = self._session.active_window

        self._initialized = True
        logger.info(
            "TmuxPanePool initialized: "
            f"session={session_name}, max_panes={self.max_panes}"
        )

    def close(self) -> None:
        """销毁所有窗格和 tmux 会话。"""
        if self._closed:
            return
        self._closed = True

        with self._lock:
            for terminal in self._all_panes:
                terminal._closed = True
            self._all_panes.clear()
            self._available.clear()

        # 终止整个 tmux 会话（立即销毁所有窗口/窗格）。 我们故意跳过每个终端 close()，因
        # 为它也会调用 session.kill() 并且会在第二个窗格上失败。
        #
        try:
            if self._session is not None:
                self._session.kill()
        except Exception as e:
            logger.warning(f"Error killing pool session: {e}")

    def _create_pane(self) -> PooledTmuxTerminal:
        """在共享会话中创建一个新的 PooledTmuxTerminal。"""
        assert self._session is not None

        shell_command = ["/bin/bash"]
        if self.username in ["root", "openhands"]:
            shell_command = ["su", self.username, "-"]
        priority_prefix = process_priority_prefix(build_terminal_env(self.env))

        window = self._session.new_window(
            window_name=f"pane-{len(self._all_panes)}",
            window_shell=shlex.join([*priority_prefix, *shell_command]),
            start_directory=self.work_dir,
        )
        active_pane = window.active_pane
        assert active_pane is not None

        # 既然存在真实窗口，则终止默认窗口。
        if self._initial_window is not None:
            with suppress(Exception):
                self._initial_window.kill()
            self._initial_window = None

        # 使用 PooledTmuxTerminal 覆盖 close()，仅终止此终端的窗口，而不是整个共享的
        # tmux 会话。
        #
        terminal = PooledTmuxTerminal(
            work_dir=self.work_dir,
            username=self.username,
            env=self.env,
        )
        terminal.server = self._server  # type: ignore[assignment]
        terminal.session = self._session
        terminal.window = window
        terminal.pane = active_pane

        # 配置PS1（与TmuxTerminal.initialize相同）
        ps1 = terminal.PS1
        active_pane.send_keys(
            f'set +H; export PROMPT_COMMAND=\'export PS1="{ps1}"\'; export PS2=""'
        )
        time.sleep(0.1)
        terminal._initialized = True
        terminal.clear_screen()

        logger.debug(f"Created pooled pane #{len(self._all_panes)}: {active_pane}")
        return terminal

    def checkout(self, timeout: float | None = None) -> PooledTmuxTerminal:
        """从池中检查一个窗格，如果全部都忙则阻塞。

        Args:
            timeout: 等待的最大秒数。 None 表示永远等待。

        Returns:
            A PooledTmuxTerminal 可供使用。

        Raises:
            RuntimeError: 如果池已关闭或未初始化。
            TimeoutError: 如果 *超时* 在窗格可用之前过期。
        """
        if not self._initialized or self._closed:
            raise RuntimeError("TmuxPanePool is not initialized or already closed")

        if timeout is None:
            self._semaphore.acquire()
        elif not self._semaphore.acquire(timeout=timeout):
            raise TimeoutError(
                f"No pane available within {timeout}s (pool size {self.max_panes})"
            )

        with self._lock:
            if self._available:
                terminal = self._available.popleft()
                logger.debug(f"Checked out existing pane: {terminal.pane}")
                return terminal

            # 创建一个新窗格（由于信号量，仍在 max_panes 下）
            terminal = self._create_pane()
            self._all_panes.append(terminal)
            logger.debug(f"Checked out new pane: {terminal.pane}")
            return terminal

    def checkin(self, terminal: PooledTmuxTerminal) -> None:
        """将一块窗格放回池中。"""
        with self._lock:
            if terminal not in self._all_panes:
                logger.warning("Attempted to checkin a pane not from this pool")
                return
            if not self._closed:
                self._available.append(terminal)

        self._semaphore.release()
        logger.debug(f"Checked in pane: {terminal.pane}")

    def replace(self, old_terminal: PooledTmuxTerminal) -> PooledTmuxTerminal:
        """将已签出的窗格替换为新的窗格。

        当前，调用者必须持有 *old_terminal* (i.e. 已签出但尚未签入）。 旧终端关闭并从
        池中移除，返回一个全新窗口 **在它的位置上** — 信
        号量计数保持不变，因为我们是一对一地交换。
        """
        with self._lock:
            # 创建替换窗格之前来终止旧窗口，因为 tmux 在最后一个窗口终止时会销毁会话。
            #
            new_terminal = self._create_pane()
            self._all_panes.append(new_terminal)

            if old_terminal in self._all_panes:
                self._all_panes.remove(old_terminal)
            if old_terminal in self._available:
                self._available.remove(old_terminal)

        # 在杀死之前捕获 ID（杀死后 repr 将失败）。
        old_pane_id = old_terminal.pane.pane_id
        new_pane_id = new_terminal.pane.pane_id

        # 仅销毁旧终端的窗口 - 不 terminal.close()，这将杀死整个共享的 tmux 会话。
        #
        try:
            old_terminal.window.kill()
        except Exception as e:
            logger.debug(f"Error killing replaced pane window: {e}")
        old_terminal._closed = True

        logger.debug(f"Replaced pane {old_pane_id} -> {new_pane_id}")
        return new_terminal

    @contextmanager
    def pane(self, timeout: float | None = None) -> Iterator[PaneHandle]:
        """上下文管理器：签出窗格，产生句柄，退出时签入。

        产生的：class:`PaneHandle` 是可变的——调用者
        :meth:`replace` 应该将新终端分配回
        ``handle.terminal`` 以便签入正确的窗格。
        """
        handle = PaneHandle(self.checkout(timeout=timeout))
        try:
            yield handle
        finally:
            self.checkin(handle.terminal)
