from __future__ import annotations

from openhands.sdk.event.base import LLMConvertibleEvent


class ManipulationIndices(set[int]):
    """可以安全地操纵事件的一组索引。

    当我们说事件列表 `events` 可以被“操纵”时，我们主要有两个意思：

    1. 如果`i`是一个操作索引，我们可以将任何事件插入到`events`的`i`处。
    2. 如果`i, j`是操纵索引，则可以删除`events[i:j]`。

    扩展 set[int] 以提供用于查找下一个有效操作索引和构建公共索引集的实用方法。
    """

    def find_next(self, threshold: int) -> int:
        """找到大于或等于阈值的最小操纵指数。

        这是上下文压缩逻辑的辅助方法，需要找到遗忘事件的安全边界。

        Args:
            threshold: 要比较的阈值。

        Returns:
            大于或等于阈值的最小操纵指数。

        Raises:
            ValueError: 如果不存在超过阈值的有效操纵指数。
        """
        valid_indices = {idx for idx in self if idx >= threshold}

        if not valid_indices:
            raise ValueError(f"No manipulation index found >= {threshold}.")

        return min(valid_indices)

    @staticmethod
    def complete(events: list[LLMConvertibleEvent]) -> ManipulationIndices:
        """返回事件序列的完整操作索引集。

        这相当于说可以在序列内的任何位置进行操作而不会出现问题。
        """
        manipulation_indices = ManipulationIndices()

        manipulation_indices.update(range(0, len(events)))
        manipulation_indices.add(len(events))

        return manipulation_indices
