"""测试 TmuxPanePool。"""

import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from openhands.tools.terminal.constants import (
    TMUX_SESSION_HEIGHT,
    TMUX_SESSION_WIDTH,
)
from openhands.tools.terminal.terminal.tmux_pane_pool import TmuxPanePool
from openhands.tools.terminal.terminal.tmux_terminal import TmuxTerminal


def test_tmux_session_viewport_is_bounded():
    assert TMUX_SESSION_WIDTH <= 256
    assert TMUX_SESSION_HEIGHT <= 200


@pytest.fixture
def pool():
    """创建并初始化一个池，测试后关闭它。"""
    with tempfile.TemporaryDirectory() as work_dir:
        p = TmuxPanePool(work_dir=work_dir, max_panes=3)
        p.initialize()
        yield p
        p.close()


# -- 初始化 -------------------------------------------------------------------


@pytest.mark.parametrize("max_panes", [0, -1, -10])
def test_rejects_invalid_max_panes(max_panes):
    with pytest.raises(ValueError, match="max_panes must be >= 1"):
        TmuxPanePool(work_dir="/tmp", max_panes=max_panes)


def test_initialize_idempotent():
    with tempfile.TemporaryDirectory() as d:
        p = TmuxPanePool(work_dir=d, max_panes=1)
        p.initialize()
        p.initialize()  # 不应该提高
        p.close()


# -- 结帐/签入 ------------------------------------------------------------------


def test_checkout_returns_initialized_terminal(pool):
    terminal = pool.checkout()
    assert terminal is not None
    assert terminal._initialized
    pool.checkin(terminal)


def test_checkout_creates_panes_lazily(pool):
    assert len(pool._all_panes) == 0
    t1 = pool.checkout()
    assert len(pool._all_panes) == 1
    t2 = pool.checkout()
    assert len(pool._all_panes) == 2
    pool.checkin(t1)
    pool.checkin(t2)


def test_checkin_reuses_panes(pool):
    t1 = pool.checkout()
    pool.checkin(t1)
    t2 = pool.checkout()
    assert t2 is t1
    pool.checkin(t2)


def test_checkout_blocks_when_full(pool):
    panes = [pool.checkout() for _ in range(3)]
    assert len(pool._all_panes) == 3

    with pytest.raises(TimeoutError):
        pool.checkout(timeout=0.2)

    for p in panes:
        pool.checkin(p)


def test_checkout_unblocks_after_checkin(pool):
    panes = [pool.checkout() for _ in range(3)]

    def delayed_checkin():
        time.sleep(0.1)
        pool.checkin(panes[0])

    t = threading.Thread(target=delayed_checkin)
    t.start()

    terminal = pool.checkout(timeout=2.0)
    t.join()

    assert terminal is panes[0]
    pool.checkin(terminal)
    for p in panes[1:]:
        pool.checkin(p)


# -- 替换-------------------------------------------------------------------------------
# -


def test_replace_returns_new_terminal(pool):
    old = pool.checkout()
    new = pool.replace(old)
    assert new is not old
    assert new._initialized
    pool.checkin(new)


def test_replace_preserves_semaphore(pool):
    """替换不消耗额外的信号量槽。"""
    t1 = pool.checkout()
    t2 = pool.checkout()
    t3 = pool.checkout()

    new_t1 = pool.replace(t1)

    with pytest.raises(TimeoutError):
        pool.checkout(timeout=0.2)

    pool.checkin(new_t1)
    pool.checkin(t2)
    pool.checkin(t3)


def test_replace_closes_old_pane(pool):
    old = pool.checkout()
    pool.replace(old)
    assert old._closed


def test_replace_does_not_affect_other_panes(pool):
    """其他签出的窗格在更换后继续工作。"""
    t1 = pool.checkout()
    t2 = pool.checkout()

    new_t1 = pool.replace(t1)
    t2.send_keys("echo still_alive")
    time.sleep(0.3)
    assert "still_alive" in t2.read_screen()

    pool.checkin(new_t1)
    pool.checkin(t2)


@pytest.mark.parametrize("cmd", ["echo fresh", "pwd"])
def test_replace_fresh_pane_runs_commands(pool, cmd):
    old = pool.checkout()
    new = pool.replace(old)
    new.send_keys(cmd)
    time.sleep(0.3)
    output = new.read_screen()
    assert output.strip()  # 非空输出
    pool.checkin(new)


# -- 并发执行 ---------------------------------------------------


@pytest.mark.parametrize(
    "labels_and_cmds",
    [
        [("a", "echo AAA"), ("b", "echo BBB")],
        [("x", "echo X1"), ("y", "echo Y2"), ("z", "echo Z3")],
    ],
    ids=["two_threads", "three_threads"],
)
def test_parallel_commands(pool, labels_and_cmds):
    """在单独的窗格上并行运行命令。"""
    results = {}
    barrier = threading.Barrier(len(labels_and_cmds))

    def run_cmd(label, cmd):
        terminal = pool.checkout()
        try:
            barrier.wait(timeout=5)
            terminal.send_keys(cmd)
            time.sleep(0.5)
            results[label] = terminal.read_screen()
        finally:
            pool.checkin(terminal)

    threads = [
        threading.Thread(target=run_cmd, args=(label, cmd))
        for label, cmd in labels_and_cmds
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    for label, cmd in labels_and_cmds:
        expected = cmd.split()[-1]  # e.g. “回声 AAA”中的“AAA”
        assert expected in results[label]


def test_concurrent_replace_does_not_corrupt_pool(pool):
    """从多个线程替换窗格是安全的。"""
    errors = []

    def replace_cycle():
        try:
            t = pool.checkout(timeout=5)
            new = pool.replace(t)
            new.send_keys("echo ok")
            time.sleep(0.2)
            pool.checkin(new)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=replace_cycle) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"Errors during concurrent replace: {errors}"


# -- 初始窗口清理------------------------------------------------


def test_initial_window_killed_after_first_pane(pool):
    """默认的 tmux 窗口在第一次结帐时会被清理。"""
    assert pool._initial_window is not None
    t = pool.checkout()
    assert pool._initial_window is None
    pool.checkin(t)


# -- 关闭 ------------------------------------------------------------------------------
# ----


def test_close_idempotent(pool):
    pool.close()
    pool.close()  # 不应该提高


def test_checkout_after_close_raises(pool):
    pool.close()
    with pytest.raises(RuntimeError):
        pool.checkout()


def test_checkin_foreign_pane_is_ignored(pool):
    """忽略不来自该池的窗格的签入。"""
    from openhands.tools.terminal.terminal.tmux_terminal import TmuxTerminal

    fake = TmuxTerminal.__new__(TmuxTerminal)
    pool.checkin(fake)  # 应该记录警告，而不是崩溃


@pytest.mark.skipif(os.name != "posix", reason="tmux requires Unix sockets")
@pytest.mark.parametrize("terminal_type", [TmuxTerminal, TmuxPanePool])
def test_overlong_tmux_tmpdir_uses_short_socket_path(
    tmp_path, monkeypatch, terminal_type
):
    socket_dir = tmp_path / ("deep-" + "x" * 80)
    socket_dir.mkdir()
    monkeypatch.setenv("TMUX_TMPDIR", str(socket_dir))
    terminal = terminal_type(str(tmp_path))
    try:
        terminal.initialize()
        server = (
            terminal._server if isinstance(terminal, TmuxPanePool) else terminal.server
        )
        assert server is not None
        assert server.socket_path is not None
        assert Path(server.socket_path).is_relative_to("/tmp")
        assert os.environ["TMUX_TMPDIR"] == str(socket_dir)
    finally:
        terminal.close()


@pytest.mark.parametrize("pooled", [True, False])
@pytest.mark.parametrize("operation", ["read", "write", "close"])
def test_stale_terminal_cannot_access_restarted_server(
    tmp_path, monkeypatch, pooled, operation
):
    # 仅重定向套接字命名空间； 所有终端/tmux 操作都是真实的。
    with tempfile.TemporaryDirectory(prefix="oh-tmux-") as socket_dir:
        monkeypatch.setenv("TMUX_TMPDIR", socket_dir)
        first = TmuxPanePool(str(tmp_path)) if pooled else TmuxTerminal(str(tmp_path))
        second = TmuxPanePool(str(tmp_path)) if pooled else TmuxTerminal(str(tmp_path))
        try:
            first.initialize()
            stale = first.checkout() if isinstance(first, TmuxPanePool) else first
            stale.server.cmd("kill-server")
            second.initialize()
            current = second.checkout() if isinstance(second, TmuxPanePool) else second
            current.send_keys("printf 'SECOND_%s\\n' CONVERSATION_MARKER")
            deadline = time.monotonic() + 5
            while "SECOND_CONVERSATION_MARKER" not in current.read_screen():
                assert time.monotonic() < deadline
                time.sleep(0.05)

            if operation == "read":
                assert "SECOND_CONVERSATION_MARKER" not in stale.read_screen()
            elif operation == "write":
                marker = tmp_path / "wrong-conversation"
                stale.send_keys(f"touch {marker}")
                current.send_keys("printf 'WRITE_%s\\n' BARRIER")
                deadline = time.monotonic() + 5
                while "WRITE_BARRIER" not in current.read_screen():
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
                assert not marker.exists()
            else:
                first.close()
                assert "SECOND_CONVERSATION_MARKER" in current.read_screen()
        finally:
            first.close()
            second.close()
