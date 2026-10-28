"""
测试 FIFO 锁实施的公平性和正确性。
"""

import threading
import time
from collections import deque

import pytest

from openhands.sdk.conversation.fifo_lock import FIFOLock


def test_fifo_lock_basic_functionality():
    """测试基本锁功能 - 获取、释放、可重入性。"""
    lock = FIFOLock()

    # 测试初始状态
    assert not lock.locked()
    assert not lock.owned()

    # 测试获取/释放
    lock.acquire()
    assert lock.locked()
    assert lock.owned()

    # 测试可重入性
    lock.acquire()
    assert lock.locked()
    assert lock.owned()

    lock.release()
    assert lock.locked()  # 由于可重入性仍处于锁定状态
    assert lock.owned()

    lock.release()
    assert not lock.locked()
    assert not lock.owned()


def test_fifo_lock_context_manager():
    """测试上下文管理器功能。"""
    lock = FIFOLock()

    with lock:
        assert lock.locked()
        assert lock.owned()

        # 使用上下文管理器测试可重入性
        with lock:
            assert lock.locked()
            assert lock.owned()

    assert not lock.locked()
    assert not lock.owned()


def test_fifo_lock_non_blocking():
    """测试非阻塞获取行为。"""
    lock = FIFOLock()

    # 空闲时应立即获取
    assert lock.acquire(blocking=False)
    assert lock.locked()

    # 当已被另一个线程拥有时应该失败
    def try_acquire():
        return lock.acquire(blocking=False)

    result = []
    thread = threading.Thread(target=lambda: result.append(try_acquire()))
    thread.start()
    thread.join()

    assert result[0] is False  # 应该无法获取

    lock.release()
    assert not lock.locked()


def test_fifo_lock_timeout():
    """测试超时行为。"""
    lock = FIFOLock()
    lock.acquire()

    def try_acquire_with_timeout():
        start_time = time.time()
        result = lock.acquire(blocking=True, timeout=0.1)
        end_time = time.time()
        return result, end_time - start_time

    result = []
    thread = threading.Thread(target=lambda: result.append(try_acquire_with_timeout()))
    thread.start()
    thread.join()

    acquired, duration = result[0]
    assert not acquired  # 应该超时
    assert 0.09 <= duration <= 0.2  # 应接近超时值

    lock.release()


def _wait_for_waiter_count(lock: FIFOLock, expected: int) -> None:
    """阻塞直到 ``expected`` 线程在 ``lock`` 上排队。

    Signalling 线程在固定睡眠的竞态中，操作系统调度器：一个信号线程不得调用
    ``acquire()`` 在下一个信号被触发之前，因此加载机器上的队列顺序不再
    匹配信号顺序。 相反，轮询队列使入队顺序具有确定性。
    """
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with lock._mutex:
            if len(lock._waiters) >= expected:
                return
        time.sleep(0.0005)
    raise AssertionError(f"Timed out waiting for {expected} queued threads")


def test_fifo_lock_fairness():
    """测试锁是否提供 FIFO 排序。"""
    lock = FIFOLock()
    acquisition_order = deque()
    threads = []

    def worker(thread_id: int):
        with lock:
            acquisition_order.append(thread_id)

    # 持有锁，这样每个工作人员都必须排队而不是立即获取。
    lock.acquire()
    try:
        for i in range(10):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
            # 仅当下一个工作程序实际排队时才启动下一个工作程序，因此队列顺序正是创建顺序
            # 。
            #
            _wait_for_waiter_count(lock, i + 1)
    finally:
        lock.release()

    # 等待全部完成
    for thread in threads:
        thread.join()

    # 检查获取顺序是否与创建顺序匹配 (FIFO)
    expected_order = list(range(10))
    actual_order = list(acquisition_order)

    assert actual_order == expected_order, (
        f"Expected FIFO order {expected_order}, got {actual_order}"
    )


def test_fifo_lock_error_handling():
    """测试错误条件。"""
    lock = FIFOLock()

    # 释放无主锁时应引发错误
    with pytest.raises(RuntimeError, match="Cannot release lock not owned"):
        lock.release()

    # 从错误的线程释放时应该引发错误
    lock.acquire()

    def try_release():
        try:
            lock.release()
            return "success"
        except RuntimeError as e:
            return str(e)

    result = []
    thread = threading.Thread(target=lambda: result.append(try_release()))
    thread.start()
    thread.join()

    assert "Cannot release lock not owned" in result[0]

    lock.release()  # 清理


def test_fifo_lock_stress_test():
    """压力测试与许多线程一起验证负载下的公平性。"""
    lock = FIFOLock()
    acquisition_order = deque()
    num_threads = 20
    threads = []

    def worker(thread_id: int):
        # 随机延迟以创建更真实的争用
        time.sleep(0.001 * (thread_id % 5))
        with lock:
            acquisition_order.append(thread_id)
            # 模拟一些工作
            time.sleep(0.001)

    # 创建并启动线程
    for i in range(num_threads):
        thread = threading.Thread(target=worker, args=(i,))
        threads.append(thread)
        thread.start()

    # 等待完成
    for thread in threads:
        thread.join()

    # 验证所有线程均已获得锁
    assert len(acquisition_order) == num_threads

    # 验证没有重复项（每个线程只获取一次）
    assert len(set(acquisition_order)) == num_threads

    # 注意：由于时间变化，我们在这里不检查确切的 FIFO 顺序，
    # 但上面的主要公平性测试验证了 FIFO 行为


def run_fairness_test_multiple(num_runs: int = 100) -> list[bool]:
    """
    连续多次运行公平性测试以验证一致性。

    Args:
        num_runs: 连续测试运行次数

    Returns:
        布尔结果列表（True = FIFO 顺序保持）
    """
    results = []

    def run_single_test():
        try:
            lock = FIFOLock()
            acquisition_order = deque()
            worker_threads = []

            # 使用单独的事件来控制每个线程的 acquire() 调用
            thread_events = [threading.Event() for _ in range(10)]

            def worker(thread_id: int):
                # 等待这个特定的线程的信号
                thread_events[thread_id].wait()

                with lock:
                    acquisition_order.append(thread_id)
                    time.sleep(0.001)

            # 创建工人线程
            for i in range(10):
                thread = threading.Thread(target=worker, args=(i,))
                worker_threads.append(thread)

            # 启动所有worker 线程
            for thread in worker_threads:
                thread.start()

            # 给线程一点时间来开始并等待他们的事件
            time.sleep(0.01)

            # 信号线程按照我们想要的顺序调用 acquire()
            for i in range(10):
                thread_events[i].set()
                time.sleep(0.002)  # 延迟小，确保订购

            # 等待完成
            for thread in worker_threads:
                thread.join()

            # 检查FIFO订单
            expected = list(range(10))
            actual = list(acquisition_order)
            return actual == expected

        except Exception:
            return False

    # 按顺序运行测试以避免过多的线程争用
    for i in range(num_runs):
        if i % 20 == 0 and i > 0:
            print(f"  Completed {i}/{num_runs} tests...")
        result = run_single_test()
        results.append(result)

    return results


def test_release_all_drops_all_reentrant_levels_and_returns_depth():
    """release_all() 完全释放可重入持有的锁并报告深度。"""
    lock = FIFOLock()
    lock.acquire()
    lock.acquire()
    lock.acquire()
    assert lock.owned()

    depth = lock.release_all()

    assert depth == 3
    assert not lock.locked()
    assert not lock.owned()


def test_release_all_requires_ownership():
    """release_all() 从非拥有的线程中加注，如 release()。"""
    lock = FIFOLock()

    def _grab_and_hold(started: threading.Event, release: threading.Event):
        lock.acquire()
        started.set()
        release.wait()
        lock.release()

    started, release = threading.Event(), threading.Event()
    holder = threading.Thread(target=_grab_and_hold, args=(started, release))
    holder.start()
    started.wait()
    try:
        with pytest.raises(RuntimeError):
            lock.release_all()
    finally:
        release.set()
        holder.join()


def test_reacquire_restores_reentrancy_depth():
    """reacquire(depth) 恢复计数器，从而释放平衡。"""
    lock = FIFOLock()
    lock.acquire()
    lock.acquire()
    depth = lock.release_all()
    assert depth == 2

    lock.reacquire(depth)
    assert lock.owned()

    # 恰好 `depth` 释放将使锁完全释放。
    lock.release()
    assert lock.owned()  # 仍然举行（原为可重入）
    lock.release()
    assert not lock.owned()


def test_reacquire_zero_depth_is_noop():
    lock = FIFOLock()
    lock.reacquire(0)
    assert not lock.owned()


def test_release_all_then_reacquire_hands_off_to_waiter_first():
    """在释放窗口期间等待的线程在释放窗口之前获取锁
    释放者重新获取（FIFO在切换过程中保持公平性）。"""
    lock = FIFOLock()
    lock.acquire()

    order: list[str] = []
    waiter_ready = threading.Event()

    def _waiter():
        waiter_ready.set()
        with lock:
            order.append("waiter")

    t = threading.Thread(target=_waiter)
    t.start()
    waiter_ready.wait()
    # 给等待者一点时间来实际在锁上排队。
    time.sleep(0.05)

    depth = lock.release_all()
    # 等待者现在应该可以接受了； 重新获取其后面的队列。
    lock.reacquire(depth)
    order.append("releaser")
    lock.release()
    t.join()

    assert order == ["waiter", "releaser"]


if __name__ == "__main__":
    print("Running FIFO lock fairness test 100 times sequentially...")

    results = run_fairness_test_multiple(100)

    success_count = sum(results)
    total_count = len(results)
    success_rate = success_count / total_count * 100

    print(f"Results: {success_count}/{total_count} tests maintained FIFO order")
    print(f"Success rate: {success_rate:.1f}%")

    if success_rate == 100.0:
        print("✅ FIFO lock provides perfect fairness!")
    elif success_rate >= 95.0:
        print("✅ FIFO lock provides excellent fairness (>95%)")
    elif success_rate >= 80.0:
        print("⚠️  FIFO lock provides good fairness (>80%)")
    else:
        print("❌ FIFO lock fairness is insufficient (<80%)")

    # 还运行常规测试
    print("\nRunning regular test suite...")
    pytest.main([__file__, "-v"])
