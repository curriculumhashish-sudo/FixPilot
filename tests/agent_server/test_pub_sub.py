"""
独立单元测试用于 PubSub 类功能。

此测试文件重新创建 PubSub 类逻辑来测试它，而不依赖于 openhands.sdk 模块。
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest


# 模拟对象事件类
class MockEvent:
    """模拟对象用于测试目的的事件类。"""

    def __init__(self, event_type="test_event", data="test_data"):
        self.type: str = event_type
        self.data: str = data

    def model_dump(self):
        return {"type": self.type, "data": self.data}


# 模拟对象记录器
class MockLogger:
    """模拟对象用于测试目的的记录器。"""

    def __init__(self):
        self.debug_calls: list[Any] = []
        self.warning_calls: list[Any] = []
        self.error_calls: list[Any] = []

    def debug(self, message):
        self.debug_calls.append(message)

    def warning(self, message):
        self.warning_calls.append(message)

    def error(self, message, exc_info=False):
        self.error_calls.append((message, exc_info))


# 重新创建订阅者 ABC 以进行测试
class SubscriberForTesting(ABC):
    @abstractmethod
    async def __call__(self, event):
        """调用该订阅者"""

    async def close(self):
        """清理该订阅者"""


# 重新创建 PubSub 进行测试
@dataclass
class PubSubForTesting:
    """PubSub 的可测试版本，无需外部依赖。"""

    _subscribers: dict[UUID, SubscriberForTesting] = field(default_factory=dict)
    _logger: MockLogger = field(default_factory=MockLogger)

    def subscribe(self, subscriber: SubscriberForTesting) -> UUID:
        """订阅订阅者并返回其 UUID 以供以后取消订阅。"""
        subscriber_id = uuid4()
        self._subscribers[subscriber_id] = subscriber
        self._logger.debug(f"Subscribed subscriber with ID: {subscriber_id}")
        return subscriber_id

    def unsubscribe(self, subscriber_id: UUID) -> bool:
        """通过 UUID 取消订阅订阅者。"""
        if subscriber_id in self._subscribers:
            del self._subscribers[subscriber_id]
            self._logger.debug(f"Unsubscribed subscriber with ID: {subscriber_id}")
            return True
        else:
            self._logger.warning(
                f"Attempted to unsubscribe unknown subscriber ID: {subscriber_id}"
            )
            return False

    async def __call__(self, event) -> None:
        """使用给定事件调用所有已注册的回调。"""
        subscribers = list(self._subscribers.items())
        if not subscribers:
            return

        async def _notify(subscriber_id, subscriber):
            try:
                await subscriber(event)
            except Exception as e:
                self._logger.error(
                    f"Error in subscriber {subscriber_id}: {e}",
                    exc_info=True,
                )

        await asyncio.gather(*[_notify(sid, sub) for sid, sub in subscribers])

    async def close(self):
        await asyncio.gather(
            *[subscriber.close() for subscriber in self._subscribers.values()],
            return_exceptions=True,
        )
        self._subscribers.clear()


# 模拟对象用于测试的订阅者类别
class MockSubscriber(SubscriberForTesting):
    """模拟对象用于测试目的的订阅者。"""

    def __init__(self, name="test_subscriber"):
        self.name: str = name
        self.call_count: int = 0
        self.received_events: list[Any] = []
        self.close_called: bool = False
        self.should_raise_error: bool = False
        self.error_to_raise: Exception | None = None

    async def __call__(self, event):
        """调用该订阅者"""
        self.call_count += 1
        self.received_events.append(event)

        if self.should_raise_error:
            raise self.error_to_raise or Exception(f"Error in {self.name}")

    async def close(self):
        """清理该订阅者"""
        self.close_called: bool = True


@pytest.fixture
def pubsub():
    """创建一个 PubSub 实例用于测试。"""
    return PubSubForTesting()


@pytest.fixture
def sample_event():
    """创建一个示例事件以进行测试。"""
    return MockEvent("test_event", "test_data")


@pytest.fixture
def sample_events():
    """创建多个示例事件以进行测试。"""
    events = []
    for i in range(3):
        events.append(MockEvent(f"test_event_{i}", f"test_data_{i}"))
    return events


@pytest.fixture
def mock_subscriber():
    """创建模拟对象订阅者进行测试。"""
    return MockSubscriber("subscriber_1")


@pytest.fixture
def mock_subscribers():
    """创建多个模拟对象订阅者进行测试。"""
    return [
        MockSubscriber("subscriber_1"),
        MockSubscriber("subscriber_2"),
        MockSubscriber("subscriber_3"),
    ]


class TestPubSubSubscribe:
    """测试用例代表 PubSub.subscribe 方法。"""

    def test_subscribe_single_subscriber(self, pubsub, mock_subscriber):
        """测试订阅单个订阅者。"""
        subscriber_id = pubsub.subscribe(mock_subscriber)

        # 应该返回 UUID
        assert isinstance(subscriber_id, UUID)

        # 订阅者应该在内部字典中
        assert subscriber_id in pubsub._subscribers
        assert pubsub._subscribers[subscriber_id] == mock_subscriber

        # 应该只有一个订阅者
        assert len(pubsub._subscribers) == 1

        # 应该记录订阅
        assert len(pubsub._logger.debug_calls) == 1
        assert "Subscribed subscriber with ID" in pubsub._logger.debug_calls[0]

    def test_subscribe_multiple_subscribers(self, pubsub, mock_subscribers):
        """测试订阅多个订阅者。"""
        subscriber_ids = []

        for subscriber in mock_subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

            # 每个应该返回一个唯一的 UUID
            assert isinstance(subscriber_id, UUID)
            assert subscriber_id not in subscriber_ids[:-1]  # 与之前的 ID 不同

        # 所有订阅者都应该在字典中
        assert len(pubsub._subscribers) == len(mock_subscribers)

        for i, subscriber_id in enumerate(subscriber_ids):
            assert pubsub._subscribers[subscriber_id] == mock_subscribers[i]

    def test_subscribe_same_subscriber_multiple_times(self, pubsub, mock_subscriber):
        """测试多次订阅同一订阅者实例。"""
        subscriber_id_1 = pubsub.subscribe(mock_subscriber)
        subscriber_id_2 = pubsub.subscribe(mock_subscriber)

        # 应该得到不同的 UUIDs
        assert subscriber_id_1 != subscriber_id_2

        # 两者都应该在字典中
        assert len(pubsub._subscribers) == 2
        assert pubsub._subscribers[subscriber_id_1] == mock_subscriber
        assert pubsub._subscribers[subscriber_id_2] == mock_subscriber

    def test_subscribe_returns_unique_uuids(self, pubsub):
        """测试订阅总是返回唯一的 UUIDs。"""
        subscribers = [MockSubscriber(f"subscriber_{i}") for i in range(10)]
        subscriber_ids = []

        for subscriber in subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

        # 所有 ID 都应该是唯一的
        assert len(set(subscriber_ids)) == len(subscriber_ids)


class TestPubSubUnsubscribe:
    """测试用例代表 PubSub.unsubscribe 方法。"""

    def test_unsubscribe_existing_subscriber(self, pubsub, mock_subscriber):
        """测试取消订阅现有订阅者。"""
        subscriber_id = pubsub.subscribe(mock_subscriber)

        # 取消订阅应返回 True
        result = pubsub.unsubscribe(subscriber_id)
        assert result is True

        # 订阅者应该从字典中删除
        assert subscriber_id not in pubsub._subscribers
        assert len(pubsub._subscribers) == 0

        # 应该记录取消订阅
        assert len(pubsub._logger.debug_calls) == 2  # 订阅+取消订阅
        assert "Unsubscribed subscriber with ID" in pubsub._logger.debug_calls[1]

    def test_unsubscribe_nonexistent_subscriber(self, pubsub):
        """测试取消订阅不存在的订阅者。"""
        fake_id = uuid4()

        # 取消订阅应返回 False
        result = pubsub.unsubscribe(fake_id)
        assert result is False

        # 字典应保持为空
        assert len(pubsub._subscribers) == 0

        # 应该记录警告
        assert len(pubsub._logger.warning_calls) == 1
        assert (
            "Attempted to unsubscribe unknown subscriber ID"
            in pubsub._logger.warning_calls[0]
        )

    def test_unsubscribe_multiple_subscribers(self, pubsub, mock_subscribers):
        """测试取消多个订阅者的订阅。"""
        subscriber_ids = []

        # 全部订阅
        for subscriber in mock_subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

        assert len(pubsub._subscribers) == len(mock_subscribers)

        # 取消订阅第一个订阅者
        result = pubsub.unsubscribe(subscriber_ids[0])
        assert result is True
        assert len(pubsub._subscribers) == len(mock_subscribers) - 1
        assert subscriber_ids[0] not in pubsub._subscribers

        # 其他订阅者应该仍然存在
        for i in range(1, len(subscriber_ids)):
            assert subscriber_ids[i] in pubsub._subscribers

    def test_unsubscribe_already_unsubscribed(self, pubsub, mock_subscriber):
        """测试取消订阅已取消订阅的订阅者。"""
        subscriber_id = pubsub.subscribe(mock_subscriber)

        # 首先取消订阅应该成功
        result1 = pubsub.unsubscribe(subscriber_id)
        assert result1 is True

        # 第二次取消订阅应该会失败
        result2 = pubsub.unsubscribe(subscriber_id)
        assert result2 is False

    def test_unsubscribe_partial_removal(self, pubsub, mock_subscribers):
        """测试取消一位订阅者的订阅不会影响其他订阅者。"""
        subscriber_ids = []

        # 全部订阅
        for subscriber in mock_subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

        # 取消订阅中间订阅者
        middle_index = len(subscriber_ids) // 2
        result = pubsub.unsubscribe(subscriber_ids[middle_index])
        assert result is True

        # 检查是否仅删除了中间订阅者
        assert len(pubsub._subscribers) == len(mock_subscribers) - 1
        assert subscriber_ids[middle_index] not in pubsub._subscribers

        # 所有其他订阅者应该仍然存在
        for i, subscriber_id in enumerate(subscriber_ids):
            if i != middle_index:
                assert subscriber_id in pubsub._subscribers
                assert pubsub._subscribers[subscriber_id] == mock_subscribers[i]


class TestPubSubCall:
    """测试用例用于PubSub.__call__方法（事件分发）。"""

    @pytest.mark.asyncio
    async def test_call_with_no_subscribers(self, pubsub, sample_event):
        """在没有订阅者的情况下测试呼叫 PubSub。"""
        # 不应引发任何错误
        await pubsub(sample_event)

    @pytest.mark.asyncio
    async def test_call_with_single_subscriber(
        self, pubsub, mock_subscriber, sample_event
    ):
        """测试使用单个订阅者呼叫 PubSub。"""
        pubsub.subscribe(mock_subscriber)

        await pubsub(sample_event)

        # 订阅者应该已收到该事件
        assert mock_subscriber.call_count == 1
        assert len(mock_subscriber.received_events) == 1
        assert mock_subscriber.received_events[0] == sample_event

    @pytest.mark.asyncio
    async def test_call_with_multiple_subscribers(
        self, pubsub, mock_subscribers, sample_event
    ):
        """测试与多个订阅者的呼叫 PubSub。"""
        # 全部订阅
        for subscriber in mock_subscribers:
            pubsub.subscribe(subscriber)

        await pubsub(sample_event)

        # 所有订阅者都应该已收到该事件
        for subscriber in mock_subscribers:
            assert subscriber.call_count == 1
            assert len(subscriber.received_events) == 1
            assert subscriber.received_events[0] == sample_event

    @pytest.mark.asyncio
    async def test_call_with_multiple_events(
        self, pubsub, mock_subscriber, sample_events
    ):
        """测试使用不同事件多次调用 PubSub。"""
        pubsub.subscribe(mock_subscriber)

        for event in sample_events:
            await pubsub(event)

        # 订阅者应该已收到所有事件
        assert mock_subscriber.call_count == len(sample_events)
        assert len(mock_subscriber.received_events) == len(sample_events)
        assert mock_subscriber.received_events == sample_events

    @pytest.mark.asyncio
    async def test_call_distributes_to_all_current_subscribers(
        self, pubsub, mock_subscribers, sample_event
    ):
        """测试事件是否分发给所有当前订阅者。"""
        subscriber_ids = []

        # 全部订阅
        for subscriber in mock_subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

        await pubsub(sample_event)

        # 所有人都应该收到该事件
        for subscriber in mock_subscribers:
            assert subscriber.call_count == 1
            assert sample_event in subscriber.received_events

    @pytest.mark.asyncio
    async def test_call_with_subscriber_error_isolation(
        self, pubsub, mock_subscribers, sample_event
    ):
        """测试一个订阅者的错误不会影响其他订阅者。"""
        # 全部订阅
        for subscriber in mock_subscribers:
            pubsub.subscribe(subscriber)

        # 让中间订阅者抛出错误
        middle_subscriber = mock_subscribers[len(mock_subscribers) // 2]
        middle_subscriber.should_raise_error = True
        middle_subscriber.error_to_raise = ValueError("Test error")

        # 不应引发异常
        await pubsub(sample_event)

        # 所有订阅者都应该被呼叫（包括失败的订阅者）
        for subscriber in mock_subscribers:
            assert subscriber.call_count == 1
            assert sample_event in subscriber.received_events

        # 应记录错误
        assert len(pubsub._logger.error_calls) == 1
        assert "Error in subscriber" in pubsub._logger.error_calls[0][0]
        assert pubsub._logger.error_calls[0][1] is True  # exc_info=True


class _TimedSubscriber(SubscriberForTesting):
    """订阅者在人为延迟后记录传送墙时间。"""

    def __init__(self, name: str, delay: float, log: list[tuple[str, float]]):
        self.name = name
        self.delay = delay
        self.log = log

    async def __call__(self, event):
        start = asyncio.get_event_loop().time()
        await asyncio.sleep(self.delay)
        self.log.append((self.name, asyncio.get_event_loop().time() - start))


class TestPubSubConcurrentDispatch:
    """测试 __call__ 是否同时分派给订阅者。"""

    @pytest.mark.asyncio
    async def test_slow_subscriber_does_not_block_others(self, pubsub):
        """速度较慢的订阅者不得延迟向较快的订阅者交付。"""
        delivery_log: list[tuple[str, float]] = []

        pubsub.subscribe(_TimedSubscriber("slow", 0.2, delivery_log))
        pubsub.subscribe(_TimedSubscriber("fast", 0.0, delivery_log))

        start = asyncio.get_event_loop().time()
        await pubsub(MockEvent())
        elapsed = asyncio.get_event_loop().time() - start

        # 两个订阅者都被称为
        assert len(delivery_log) == 2
        # 壁时间 ≈ 0.2s (并发)，而不是 ≈ 0.2s+（顺序）
        assert elapsed < 0.3


class TestPubSubEventIsolation:
    """测试用例确保已删除的订阅者不会收到事件。"""

    @pytest.mark.asyncio
    async def test_unsubscribed_subscriber_no_events(
        self, pubsub, mock_subscribers, sample_event
    ):
        """测试未订阅的订阅者不会收到事件。"""
        subscriber_ids = []

        # 全部订阅
        for subscriber in mock_subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

        # 取消订阅第一个订阅者
        pubsub.unsubscribe(subscriber_ids[0])

        await pubsub(sample_event)

        # 第一个订阅者不应收到该事件
        assert mock_subscribers[0].call_count == 0
        assert len(mock_subscribers[0].received_events) == 0

        # 其他订阅者应该已经收到该事件
        for i in range(1, len(mock_subscribers)):
            assert mock_subscribers[i].call_count == 1
            assert sample_event in mock_subscribers[i].received_events

    @pytest.mark.asyncio
    async def test_unsubscribe_during_event_processing(
        self, pubsub, mock_subscribers, sample_events
    ):
        """测试事件之间的取消订阅。"""
        subscriber_ids = []

        # 全部订阅
        for subscriber in mock_subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

        # 发送第一个事件
        await pubsub(sample_events[0])

        # 所有人都应该收到第一个事件
        for subscriber in mock_subscribers:
            assert subscriber.call_count == 1
            assert sample_events[0] in subscriber.received_events

        # 取消订阅中间订阅者
        middle_index = len(subscriber_ids) // 2
        pubsub.unsubscribe(subscriber_ids[middle_index])

        # 发送第二个事件
        await pubsub(sample_events[1])

        # 中间订阅者不应收到第二个事件
        middle_subscriber = mock_subscribers[middle_index]
        assert middle_subscriber.call_count == 1  # 仅第一个活动
        assert len(middle_subscriber.received_events) == 1
        assert sample_events[1] not in middle_subscriber.received_events

        # 其他订阅者应该已收到这两个事件
        for i, subscriber in enumerate(mock_subscribers):
            if i != middle_index:
                assert subscriber.call_count == 2
                assert sample_events[0] in subscriber.received_events
                assert sample_events[1] in subscriber.received_events

    @pytest.mark.asyncio
    async def test_resubscribe_after_unsubscribe(
        self, pubsub, mock_subscriber, sample_events
    ):
        """测试取消订阅后重新订阅订阅者。"""
        # 订阅
        subscriber_id_1 = pubsub.subscribe(mock_subscriber)

        # 发送第一个事件
        await pubsub(sample_events[0])
        assert mock_subscriber.call_count == 1

        # 退订
        pubsub.unsubscribe(subscriber_id_1)

        # 发送第二个事件（不应接收）
        await pubsub(sample_events[1])
        assert mock_subscriber.call_count == 1  # 仍然 1

        # 使用新 ID 重新订阅
        subscriber_id_2 = pubsub.subscribe(mock_subscriber)
        assert subscriber_id_2 != subscriber_id_1  # 不同的ID

        # 发送第三个事件（应该收到）
        await pubsub(sample_events[2])
        assert mock_subscriber.call_count == 2  # 现在 2


class TestPubSubClose:
    """测试用例代表 PubSub.close 方法。"""

    @pytest.mark.asyncio
    async def test_close_with_no_subscribers(self, pubsub):
        """在没有订阅者的情况下测试关闭 PubSub。"""
        # 不应引发任何错误
        await pubsub.close()
        assert len(pubsub._subscribers) == 0

    @pytest.mark.asyncio
    async def test_close_with_single_subscriber(self, pubsub, mock_subscriber):
        """测试用单个订阅者关闭 PubSub。"""
        pubsub.subscribe(mock_subscriber)

        await pubsub.close()

        # 应该调用订阅者的 close 方法
        assert mock_subscriber.close_called is True

        # 应清除订阅者字典
        assert len(pubsub._subscribers) == 0

    @pytest.mark.asyncio
    async def test_close_with_multiple_subscribers(self, pubsub, mock_subscribers):
        """测试关闭多个订阅者的 PubSub。"""
        # 全部订阅
        for subscriber in mock_subscribers:
            pubsub.subscribe(subscriber)

        await pubsub.close()

        # 应该调用所有订阅者的 close 方法
        for subscriber in mock_subscribers:
            assert subscriber.close_called is True

        # 应清除订阅者字典
        assert len(pubsub._subscribers) == 0

    @pytest.mark.asyncio
    async def test_close_only_calls_current_subscribers(self, pubsub, mock_subscribers):
        """测试关闭仅调用关闭当前订阅者，
        不是取消订阅的。"""
        subscriber_ids = []

        # 全部订阅
        for subscriber in mock_subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

        # 取消订阅第一个订阅者
        pubsub.unsubscribe(subscriber_ids[0])

        await pubsub.close()

        # 第一个订阅者的关闭应该不已被调用
        assert mock_subscribers[0].close_called is False

        # 应该调用其他订阅者的 close 方法
        for i in range(1, len(mock_subscribers)):
            assert mock_subscribers[i].close_called is True

        # 应清除订阅者字典
        assert len(pubsub._subscribers) == 0

    @pytest.mark.asyncio
    async def test_close_handles_subscriber_close_errors(
        self, pubsub, mock_subscribers
    ):
        """测试关闭是否处理订户关闭方法中的错误。"""
        # 全部订阅
        for subscriber in mock_subscribers:
            pubsub.subscribe(subscriber)

        # 使一个订阅者的 close 方法引发错误
        async def failing_close():
            raise ValueError("Close error")

        mock_subscribers[1].close = failing_close

        # 不应引发异常（asyncio.gather 处理它）
        await pubsub.close()

        # 其他订阅者应该仍然有他们的侥幸心理
        assert mock_subscribers[0].close_called is True
        assert mock_subscribers[2].close_called is True

        # 应清除订阅者字典
        assert len(pubsub._subscribers) == 0

    @pytest.mark.asyncio
    async def test_close_concurrent_execution(self, pubsub):
        """测试 close 同时调用所有订阅者关闭方法。"""
        # 使用异步跟踪计时的 close 方法创建订阅者
        close_times = []

        async def timed_close(subscriber_id):
            await asyncio.sleep(0.1)  # 模拟一些工作
            close_times.append(subscriber_id)

        subscribers = []
        for i in range(3):
            subscriber = MockSubscriber(f"subscriber_{i}")
            subscriber.close = lambda sid=i: timed_close(sid)
            subscribers.append(subscriber)
            pubsub.subscribe(subscriber)

        start_time = asyncio.get_event_loop().time()
        await pubsub.close()
        end_time = asyncio.get_event_loop().time()

        # 应在大约 0.1 秒 (并发) 内完成，而不是 0.3 秒（顺序）
        #
        elapsed_time = end_time - start_time
        assert elapsed_time < 0.2  # 为测试执行开销留出一些余量

        # 应该调用所有 close 方法
        assert len(close_times) == 3


class TestPubSubErrorHandling:
    """测试用例用于 PubSub 中的错误处理。"""

    @pytest.mark.asyncio
    async def test_subscriber_exception_isolation(
        self, pubsub, mock_subscribers, sample_event
    ):
        """测试一个订阅者中的异常不会影响其他订阅者。"""
        # 全部订阅
        for subscriber in mock_subscribers:
            pubsub.subscribe(subscriber)

        # 让多个订阅者引发不同的错误
        mock_subscribers[0].should_raise_error = True
        mock_subscribers[0].error_to_raise = ValueError("First error")

        mock_subscribers[2].should_raise_error = True
        mock_subscribers[2].error_to_raise = RuntimeError("Third error")

        # 不应引发异常
        await pubsub(sample_event)

        # 所有订阅者都应该被调用
        for subscriber in mock_subscribers:
            assert subscriber.call_count == 1
            assert sample_event in subscriber.received_events

        # 应该记录这两个错误
        assert len(pubsub._logger.error_calls) == 2

    @pytest.mark.asyncio
    async def test_multiple_events_with_errors(
        self, pubsub, mock_subscriber, sample_events
    ):
        """测试一个事件中的错误不会阻止处理
        的后续事件。"""
        pubsub.subscribe(mock_subscriber)

        # 仅通过设置错误标志使订阅者在第二个事件上失败这样 PubSub 中的错误处理将捕获它
        #

        # 处理所有事件
        for i, event in enumerate(sample_events):
            if i == 1:  # 第二个事件应该导致错误
                mock_subscriber.should_raise_error = True
                mock_subscriber.error_to_raise = ValueError("Second event error")
            else:
                mock_subscriber.should_raise_error = False
                mock_subscriber.error_to_raise = None

            await pubsub(event)

        # 所有事件都应该已被处理
        assert len(mock_subscriber.received_events) == len(sample_events)
        assert mock_subscriber.received_events == sample_events

        # 应记录一个错误
        assert len(pubsub._logger.error_calls) == 1


class TestPubSubIntegration:
    """PubSub 的集成测试个案例。"""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, pubsub, sample_events):
        """测试完整的 PubSub 生命周期：订阅、事件、取消订阅、关闭。"""
        subscribers = [MockSubscriber(f"subscriber_{i}") for i in range(3)]
        subscriber_ids = []

        # 全部订阅
        for subscriber in subscribers:
            subscriber_id = pubsub.subscribe(subscriber)
            subscriber_ids.append(subscriber_id)

        # 向所有人发送第一个事件
        await pubsub(sample_events[0])

        # 所有人都应该收到第一个事件
        for subscriber in subscribers:
            assert subscriber.call_count == 1
            assert sample_events[0] in subscriber.received_events

        # 取消订阅中间订阅者
        pubsub.unsubscribe(subscriber_ids[1])

        # 发送第二个事件
        await pubsub(sample_events[1])

        # 只有第一个和第三个应该接收第二个事件
        assert subscribers[0].call_count == 2
        assert subscribers[1].call_count == 1  # 仍然 1
        assert subscribers[2].call_count == 2

        # 关闭 PubSub
        await pubsub.close()

        # 只有当前订阅者才应该有千钧一发的机会
        assert subscribers[0].close_called is True
        assert subscribers[1].close_called is False  # 已取消订阅
        assert subscribers[2].close_called is True

        # 字典应为空
        assert len(pubsub._subscribers) == 0

    @pytest.mark.asyncio
    async def test_concurrent_subscribe_unsubscribe(self, pubsub, sample_event):
        """测试并发订阅/取消订阅操作。"""
        subscribers = [MockSubscriber(f"subscriber_{i}") for i in range(10)]

        # 同时订阅全部
        subscribe_tasks = [
            asyncio.create_task(asyncio.to_thread(pubsub.subscribe, subscriber))
            for subscriber in subscribers
        ]
        subscriber_ids = await asyncio.gather(*subscribe_tasks)

        # 全部都应该订阅
        assert len(pubsub._subscribers) == len(subscribers)

        # 发送事件
        await pubsub(sample_event)

        # 所有人都应该收到事件
        for subscriber in subscribers:
            assert subscriber.call_count == 1

        # 同时退订一半
        unsubscribe_tasks = [
            asyncio.create_task(
                asyncio.to_thread(pubsub.unsubscribe, subscriber_ids[i])
            )
            for i in range(0, len(subscriber_ids), 2)
        ]
        results = await asyncio.gather(*unsubscribe_tasks)

        # 所有取消订阅操作都应该成功
        assert all(results)

        # 一半应保持订阅状态
        assert len(pubsub._subscribers) == len(subscribers) // 2

    @pytest.mark.asyncio
    async def test_stress_test_many_subscribers(self, pubsub, sample_event):
        """压力测试有很多订阅者。"""
        num_subscribers = 100
        subscribers = [
            MockSubscriber(f"subscriber_{i}") for i in range(num_subscribers)
        ]

        # 全部订阅
        for subscriber in subscribers:
            pubsub.subscribe(subscriber)

        # 发送事件
        await pubsub(sample_event)

        # 所有人都应该收到事件
        for subscriber in subscribers:
            assert subscriber.call_count == 1
            assert sample_event in subscriber.received_events

        # Close 应该处理所有订阅者
        await pubsub.close()

        # 一切都应该千钧一发
        for subscriber in subscribers:
            assert subscriber.close_called is True

        assert len(pubsub._subscribers) == 0


class TestPubSubMaxSubscribers:
    """使用真实的 PubSub 类测试 max_subscribers 限制。"""

    async def test_subscribe_rejected_at_limit(self):
        from openhands.agent_server.pub_sub import (
            MaxSubscribersError,
            PubSub,
            Subscriber,
        )

        class _Sub(Subscriber[str]):
            async def __call__(self, event: str) -> None:
                pass

        pubsub: PubSub[str] = PubSub(max_subscribers=2)
        pubsub.subscribe(_Sub())
        pubsub.subscribe(_Sub())

        with pytest.raises(MaxSubscribersError):
            pubsub.subscribe(_Sub())

    async def test_subscribe_allowed_after_unsubscribe(self):
        from openhands.agent_server.pub_sub import PubSub, Subscriber

        class _Sub(Subscriber[str]):
            async def __call__(self, event: str) -> None:
                pass

        pubsub: PubSub[str] = PubSub(max_subscribers=2)
        id_a = pubsub.subscribe(_Sub())
        pubsub.subscribe(_Sub())
        pubsub.unsubscribe(id_a)

        # 插槽已释放——应该会成功
        pubsub.subscribe(_Sub())
        assert len(pubsub._subscribers) == 2

    async def test_no_limit_when_none(self):
        from openhands.agent_server.pub_sub import PubSub, Subscriber

        class _Sub(Subscriber[str]):
            async def __call__(self, event: str) -> None:
                pass

        pubsub: PubSub[str] = PubSub(max_subscribers=None)
        for _ in range(100):
            pubsub.subscribe(_Sub())
        assert len(pubsub._subscribers) == 100
