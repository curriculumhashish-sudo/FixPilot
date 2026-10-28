"""用于并行工具执行的资源级锁管理器。

提供按资源级别的锁定，以便在同一共享状态（文件、终端会话、浏览器会话等）上的工具可以
使用已序列化当工具接触时 *不同的* 资源可以并发运行。

锁按照排序顺序获取，以防止死锁并使用 FIFOLock 以实现公平（不饥饿）。
"""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Final

from openhands.sdk.conversation.fifo_lock import FIFOLock


DEFAULT_TIMEOUTS: Final[dict[str, float]] = {
    "file": 30.0,
    "terminal": 300.0,
    "browser": 300.0,
    "mcp": 300.0,
    "tool": 60.0,
}
_DEFAULT_TIMEOUT: Final[float] = 30.0


class ResourceLockTimeout(TimeoutError):
    """无法在允许的超时范围内获取锁。"""


class ResourceLockManager:
    """管理每个资源 FIFO 锁以执行并发工具。

    用法：:

        mgr = ResourceLockManager()
        with mgr.lock("file:/a.py", "file:/b.py"):
            # 对两个文件的独占访问
            ...
    """

    def __init__(
        self,
        timeouts: dict[str, float] | None = None,
    ) -> None:
        self._locks: dict[str, FIFOLock] = {}
        self._meta_lock = threading.Lock()
        self._refcounts: dict[str, int] = {}
        self._timeouts = timeouts or DEFAULT_TIMEOUTS

    def _get_lock(self, key: str) -> FIFOLock:
        """返回（或惰性创建） FIFOLock 为了 *key*.

        还会增加引用计数，以便在调用者仍然保留或等待锁时不会清除它。
        """
        with self._meta_lock:
            if key not in self._locks:
                self._locks[key] = FIFOLock()
            self._refcounts[key] = self._refcounts.get(key, 0) + 1
            return self._locks[key]

    def _release_lock(self, key: str) -> None:
        """释放 FIFOLock，并清理 *key* 未引用的部分。"""
        with self._meta_lock:
            lock = self._locks.get(key)
            if lock is None:
                return
            lock.release()
            self._refcounts[key] -= 1
            if self._refcounts[key] == 0 and not lock.locked():
                del self._locks[key]
                del self._refcounts[key]

    def _get_timeout(self, key: str) -> float:
        """根据资源键的前缀返回超时。"""
        prefix = key.split(":", 1)[0] if ":" in key else key
        return self._timeouts.get(prefix, _DEFAULT_TIMEOUT)

    @contextmanager
    def lock(self, *resource_keys: str) -> Generator[None]:
        """按排序顺序获取所有 *resource_keys* 的锁。

        当两个线程需要重叠的资源集时，排序获取会阻止死锁。

        Raises:
            ResourceLockTimeout: 如果无法在锁内获取
                它的超时。
        """
        sorted_keys = sorted(set(resource_keys))
        acquired: list[str] = []
        try:
            for key in sorted_keys:
                timeout = self._get_timeout(key)
                if not self._get_lock(key).acquire(timeout=timeout):
                    # _get_lock() 已经增加了该键的引用计数。 由于收购失败，这个键不会被
                    # 添加到被收购的[]中，最后块也不会清理它——所以，我们必须在这里撤销计
                    # 数器的增加。
                    #
                    with self._meta_lock:
                        self._refcounts[key] -= 1
                        if self._refcounts[key] == 0 and not self._locks[key].locked():
                            del self._locks[key]
                            del self._refcounts[key]
                    raise ResourceLockTimeout(
                        f"Could not acquire lock for '{key}' within {timeout}s"
                    )
                acquired.append(key)
            yield
        finally:
            for key in reversed(acquired):
                self._release_lock(key)
