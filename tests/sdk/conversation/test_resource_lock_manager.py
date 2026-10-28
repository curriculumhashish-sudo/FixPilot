"""测试 ResourceLockManager。"""

import threading

import pytest

from openhands.sdk.conversation.resource_lock_manager import (
    ResourceLockManager,
    ResourceLockTimeout,
)


def test_basic_lock_and_release():
    mgr = ResourceLockManager()
    with mgr.lock("file:/a.py"):
        pass  # 不应该提高


def test_no_keys_is_noop():
    mgr = ResourceLockManager()
    with mgr.lock():
        pass  # 零键 → 未获取锁，无错误


def test_serializes_same_resource():
    """锁定同一资源的两个线程不得重叠。"""
    mgr = ResourceLockManager()

    # 使用事件来证明严格序列化，无需睡眠
    inside = threading.Event()
    first_done = threading.Event()
    second_entered = threading.Event()
    violation = threading.Event()

    def first() -> None:
        with mgr.lock("file:/shared.py"):
            inside.set()
            # 等到第二个线程 *尝试*获取（给它一点时间来到达锁调用）
            #
            first_done.wait(timeout=5)

    def second() -> None:
        inside.wait(timeout=5)  # 确保第一个在里面
        with mgr.lock("file:/shared.py"):
            if not first_done.is_set():
                violation.set()  # 意味着重叠
            second_entered.set()

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    t2.start()

    inside.wait(timeout=5)
    first_done.set()  # let first release
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert second_entered.is_set()
    assert not violation.is_set()


def test_parallel_different_resources():
    """两个线程锁定不同的资源应该重叠。"""
    mgr = ResourceLockManager()
    barrier = threading.Barrier(2, timeout=5)
    reached_barrier = [False, False]

    def worker(idx: int, key: str) -> None:
        with mgr.lock(key):
            reached_barrier[idx] = True
            barrier.wait()  # 两者必须同时到达这里

    t1 = threading.Thread(target=worker, args=(0, "file:/a.py"))
    t2 = threading.Thread(target=worker, args=(1, "file:/b.py"))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert all(reached_barrier)


def test_sorted_order_prevents_deadlock():
    """排序获取可防止死锁顺序相反。"""
    mgr = ResourceLockManager()
    results: list[str] = []

    def worker(name: str, k1: str, k2: str) -> None:
        with mgr.lock(k1, k2):
            results.append(name)

    t1 = threading.Thread(target=worker, args=("A", "r:1", "r:2"))
    t2 = threading.Thread(target=worker, args=("B", "r:2", "r:1"))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert set(results) == {"A", "B"}


def test_timeout_raises_custom_exception():
    mgr = ResourceLockManager(timeouts={"file": 0.05})

    held = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with mgr.lock("file:/x"):
            held.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    held.wait()

    with pytest.raises(ResourceLockTimeout, match="file:/x"):
        with mgr.lock("file:/x"):
            pass

    release.set()
    t.join()


def test_timeout_is_subclass_of_timeout_error():
    """ResourceLockTimeout 应该可以像 TimeoutError 一样被捕获。"""
    assert issubclass(ResourceLockTimeout, TimeoutError)


def test_duplicate_keys_deduplicated():
    """多次传递相同的密钥不应死锁。"""
    mgr = ResourceLockManager()
    with mgr.lock("file:/a.py", "file:/a.py"):
        pass


def test_default_timeouts():
    mgr = ResourceLockManager()
    assert mgr._get_timeout("file:/foo") == 30.0
    assert mgr._get_timeout("terminal:session") == 300.0
    assert mgr._get_timeout("browser:session") == 300.0
    assert mgr._get_timeout("mcp:server") == 300.0
    assert mgr._get_timeout("tool:my_tool") == 60.0
    assert mgr._get_timeout("unknown:key") == 30.0


def test_release_on_exception():
    """即使身体抬起，锁也必须释放。"""
    mgr = ResourceLockManager()
    with pytest.raises(RuntimeError):
        with mgr.lock("file:/a.py"):
            raise RuntimeError("boom")

    # 应该可以立即重新获得
    with mgr.lock("file:/a.py"):
        pass


def test_partial_release_on_timeout():
    """如果第二个锁超时，则必须释放第一个。"""
    mgr = ResourceLockManager(timeouts={"r": 0.05})

    held = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with mgr.lock("r:b"):
            held.set()
            release.wait(timeout=5)

    t = threading.Thread(target=holder)
    t.start()
    held.wait()

    with pytest.raises(ResourceLockTimeout):
        with mgr.lock("r:a", "r:b"):
            pass  # r:a 已获取，r:b 超时

    # 尽管 r:b 上有超时，但 r:a 应该已被释放
    acquired = threading.Event()

    def check() -> None:
        with mgr.lock("r:a"):
            acquired.set()

    checker = threading.Thread(target=check)
    checker.start()
    checker.join(timeout=2)
    assert acquired.is_set()

    release.set()
    t.join()


def test_cleanup_removes_unused_locks():
    """所有支架释放后，应清理内部锁。"""
    mgr = ResourceLockManager()
    with mgr.lock("file:/tmp.py"):
        assert "file:/tmp.py" in mgr._locks

    # 释放+清理后，锁条目应该消失
    assert "file:/tmp.py" not in mgr._locks


def test_cleanup_preserves_contended_locks():
    """仍由另一个线程等待的锁不得被清除。"""
    mgr = ResourceLockManager()
    held = threading.Event()
    second_waiting = threading.Event()
    release = threading.Event()

    def first() -> None:
        with mgr.lock("file:/x"):
            held.set()
            release.wait(timeout=5)
        # 第一个版本发布后，清理运行 - 但第二个版本仍然引用锁，因此它必须生存。
        #

    def second() -> None:
        held.wait(timeout=5)
        second_waiting.set()
        with mgr.lock("file:/x"):
            pass  # 首次发布后应该会成功

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start()
    t2.start()

    held.wait(timeout=5)
    second_waiting.wait(timeout=5)
    # 这里有一个小竞赛：second_waiting.set() 在 _get_lock() 增加引用计数之前触发。 我们
    # 无法在生产代码中观察到这个递增，所以我们睡一会儿，以确保在我们发布第一个之前，第二
    # 个线程已经进入_get_lock()。
    #
    import time

    time.sleep(0.1)
    release.set()

    t1.join(timeout=5)
    t2.join(timeout=5)

    # 两者均顺利完成 — 锁未被过早删除
    assert t1.is_alive() is False
    assert t2.is_alive() is False
