from typing import Any

from cachetools import LRUCache

from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class MemoryLRUCache(LRUCache):
    """LRU 缓存具有条目计数和内存大小限制。

    此缓存强制执行两个限制：
    1. 最大条目数 (maxsize)
    2. 最大内存使用量（以字节为单位）(max_memory)

    当超过任一限制时，最近最少使用的项目将被逐出。

    Note: 为了简单性和准确性，内存跟踪基于字符串长度。
    对于非字符串值，sys.getsizeof 用作粗略近似值。
    """

    def __init__(self, max_memory: int, max_size: int, *args, **kwargs):
        # 确保最大大小至少为1，以避免LRUCache问题
        maxsize = max(1, max_size)
        super().__init__(maxsize=maxsize, *args, **kwargs)
        self.max_memory = max_memory
        self.current_memory = 0

    def _get_size(self, value: Any) -> int:
        """计算内存跟踪值的大小。

        对于字符串（FileStore 中的常见情况），我们使用 len()，它可以提供准确的字符计
        数。 对于其他类型，我们使用 sys.getsizeof() 作
        为粗略近似。
        """
        if isinstance(value, str):
            # 对于字符串，len() 给出我们关心的字符计数，对于我们的用例来说，这比
            # sys.getsizeof 准确得多
            #
            return len(value)
        elif isinstance(value, bytes):
            return len(value)
        else:
            # 对于其他类型，回退到 sys.getsizeof 这主要用于边缘情况，对于嵌套结构来说不
            # 准确，但总比没有好
            #
            try:
                import sys

                return sys.getsizeof(value)
            except Exception:
                return 0

    def __setitem__(self, key: Any, value: Any) -> None:
        new_size = self._get_size(value)

        # 不要缓存大于 max_memory 的项目，这可以防止缓存抖动，即一个巨大的项目驱逐所有内
        # 容
        #
        if new_size > self.max_memory:
            logger.debug(
                f"Item too large for cache ({new_size} bytes > "
                f"{self.max_memory} bytes), skipping cache"
            )
            return

        # 如果 key 存在则更新内存统计
        if key in self:
            old_value = self[key]
            self.current_memory -= self._get_size(old_value)

        self.current_memory += new_size

        # 逐出项目，直到低于内存限制
        while self.current_memory > self.max_memory and len(self) > 0:
            self.popitem()

        super().__setitem__(key, value)

    def __delitem__(self, key: Any) -> None:
        if key in self:
            old_value = self[key]
            self.current_memory -= self._get_size(old_value)

        super().__delitem__(key)
