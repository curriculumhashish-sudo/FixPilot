import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar, TypeVar
from uuid import UUID, uuid4

from openhands.sdk.event import StreamingDeltaEvent
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

T = TypeVar("T")


class Subscriber[T](ABC):
    # Delta 以 token 速率到达； 消费者选择接受而不是继承它们。
    receives_streaming_deltas: ClassVar[bool] = False

    @abstractmethod
    async def __call__(self, event: T):
        """调用该订阅者"""

    async def close(self):
        """清理该订阅者"""


class MaxSubscribersError(Exception):
    """当 PubSub 实例达到其订阅者限制时引发。"""


@dataclass
class PubSub[T]:
    """扩展 ConversationCallbackType 功能的订阅服务。
    该类维护了一个 UUIDs 到 ConversationCallbackType 实例的字典，并提供订阅/取消订阅
    回调的方法。 当调用时，它会调用所有注册的回调并进
    行适当错误处理。
    """

    _subscribers: dict[UUID, Subscriber[T]] = field(default_factory=dict)
    max_subscribers: int | None = None

    def subscribe(self, subscriber: Subscriber[T]) -> UUID:
        """订阅订阅者并返回其 UUID 以供以后取消订阅。
        Args:
            subscriber: 注册的回调函数
        Returns:
            UUID: UUID 可用于取消订阅此回调
        Raises:
            MaxSubscribersError: 如果已达到订阅者限制。
        """
        if (
            self.max_subscribers is not None
            and len(self._subscribers) >= self.max_subscribers
        ):
            raise MaxSubscribersError(
                f"Subscriber limit reached ({self.max_subscribers})"
            )
        subscriber_id = uuid4()
        self._subscribers[subscriber_id] = subscriber
        logger.debug(f"Subscribed subscriber with ID: {subscriber_id}")
        return subscriber_id

    def unsubscribe(self, subscriber_id: UUID) -> bool:
        """通过 UUID 取消订阅订阅者。
        Args:
            subscriber_id: subscribe() 返回的 UUID
        Returns:
            bool: True 如果订阅者被发现并被删除，False 否则
        """
        if subscriber_id in self._subscribers:
            del self._subscribers[subscriber_id]
            logger.debug(f"Unsubscribed subscriber with ID: {subscriber_id}")
            return True
        else:
            logger.warning(
                f"Attempted to unsubscribe unknown subscriber ID: {subscriber_id}"
            )
            return False

    def subscriber_ids(self) -> set[UUID]:
        """返回所有当前注册订阅者的 ID。"""
        return set(self._subscribers.keys())

    async def __call__(self, event: T) -> None:
        """使用给定事件调用所有已注册的回调。
        订阅者会同时收到通知，因此速度较慢的客户端无法阻止向其他客户端的传送。 每个回
        调都在自己的错误处理包装器中运行以保持故障隔离。
        Args:
            event: 传递给所有人的事件回调
        """
        subscribers = list(self._subscribers.items())
        if isinstance(event, StreamingDeltaEvent):
            subscribers = [s for s in subscribers if s[1].receives_streaming_deltas]
        if not subscribers:
            return

        async def _notify(subscriber_id: UUID, subscriber: Subscriber[T]):
            try:
                await subscriber(event)
            except Exception as e:
                logger.error(
                    f"Error in subscriber {subscriber_id}: {e}",
                    exc_info=True,
                )

        await asyncio.gather(*[_notify(sid, sub) for sid, sub in subscribers])

    async def close(self):
        await asyncio.gather(
            *[subscriber.close() for subscriber in self._subscribers.values()]
        )
        self._subscribers.clear()
