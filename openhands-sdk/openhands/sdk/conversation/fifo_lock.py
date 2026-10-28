"""
FIFO 锁保证先进先出访问顺序的实现。

这提供了公平的锁访问，其中线程按照其请求的确切顺序获取锁，从而防止标准 RLock 可能发生
的饥饿情况。
"""

import threading
import time
from collections import deque
from typing import Any, Self


class FIFOLock:
    """
    保证 FIFO (先进先出) 访问顺序的可重入锁。

    不同于Python的默认RLock，这个锁确保了线程按照他们请求的顺序获取锁，提供公平性并防
    止锁饥饿。

    特点：
    - Reentrant: 相同的线程可以多次获取
    - FIFO 排序：线程按请求顺序获取锁
    - 上下文管理器支持：与 'with' 语句一起使用
    - 线程安全：并发访问安全

    Note: 可重入性由 OS 线程 id 键入，而不是由 asyncio 任务键入，因此
    锁在同一个事件循环线程上执行不序列化并发协程 - 每个都重新进入它。 仅当线程上没有
    其他任务可以获取它时，才将其跨过 ``await``。
    """

    _mutex: threading.Lock
    _count: int

    def __init__(self) -> None:
        self._mutex = threading.Lock()  # 保护内部状态
        self._waiters: deque[threading.Condition] = deque()  # FIFO 等待队列线程
        self._owner: int | None = None  # 当前锁所有者线程 ID
        self._count = 0  # 可重入性计数器

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """
        获取锁。

        Args:
            blocking: 如果True，则阻塞直到获取锁。 如果False，则返回
                     立即。
            timeout: 等待锁的最长时间（如果阻塞=False，则忽略）。
                    -1 表示无限期等待。

        Returns:
            如果获取了锁，则为 True，否则为 False。
        """
        ident = threading.get_ident()
        start = time.monotonic()

        with self._mutex:
            # 可重入案例
            if self._owner == ident:
                self._count += 1
                return True

            if self._owner is None and not self._waiters:
                self._owner = ident
                self._count = 1
                return True

            if not blocking:
                # 立即放弃
                return False

            # 添加到等待队列
            me = threading.Condition(self._mutex)
            self._waiters.append(me)

            while True:
                # 如果我排在队列的前面并且没有人拥有它 → 获取
                if self._waiters[0] is me and self._owner is None:
                    self._waiters.popleft()
                    self._owner = ident
                    self._count = 1
                    return True

                if timeout >= 0:
                    remaining = timeout - (time.monotonic() - start)
                    if remaining <= 0:
                        self._waiters.remove(me)
                        return False
                    me.wait(remaining)
                else:
                    me.wait()

    def release(self) -> None:
        """
        释放锁。

        Raises:
            RuntimeError: 如果当前的线程不拥有锁。
        """
        ident = threading.get_ident()
        with self._mutex:
            if self._owner != ident:
                raise RuntimeError("Cannot release lock not owned by current thread")
            assert self._count >= 1, (
                "When releasing the resource, the count must be >= 1"
            )
            self._count -= 1
            if self._count == 0:
                self._owner = None
                if self._waiters:
                    self._waiters[0].notify()

    def release_all(self) -> int:
        """立即删除所有可重入级别，返回之前的深度。

        将锁交给下一个 FIFO 等待者，以便稍后可以恢复
        ：方法：`reacquire`。 如果不属于当前线程，则引发 RuntimeError。
        """
        ident = threading.get_ident()
        with self._mutex:
            if self._owner != ident:
                raise RuntimeError("Cannot release lock not owned by current thread")
            depth = self._count
            self._count = 0
            self._owner = None
            if self._waiters:
                self._waiters[0].notify()
        return depth

    def reacquire(self, depth: int) -> None:
        """重新获取(FIFO-公平)并从release_all()恢复``depth``。"""
        if depth <= 0:
            return
        self.acquire()
        with self._mutex:
            self._count = depth

    def __enter__(self: Self) -> Self:
        """上下文管理器条目。"""
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """上下文管理器退出。"""
        self.release()

    def locked(self) -> bool:
        """
        如果锁当前被任意线程持有，则返回 True。
        """
        with self._mutex:
            return self._owner is not None

    def owned(self) -> bool:
        """
        如果锁当前由调用方线程持有，则返回 True。
        """
        with self._mutex:
            return self._owner == threading.get_ident()
