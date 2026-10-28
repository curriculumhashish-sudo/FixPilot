from abc import ABC, abstractmethod
from collections.abc import Sequence

from openhands.sdk.event import Event


class EventsListBase(Sequence[Event], ABC):
    """可附加的事件列表的抽象基类。

    这为本地 EventLog 和远程 RemoteEventsList 实现提供了一个通用接口，避免了协议中的
    循环导入。
    """

    @abstractmethod
    def append(self, event: Event) -> int:
        """将新事件添加到列表中，并返回为其分配的序列号。"""
        ...
