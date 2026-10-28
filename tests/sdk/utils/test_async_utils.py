"""测试 OpenHands SDK 中的异步实用程序。"""

import asyncio
import threading
import time

from openhands.sdk.event import Event
from openhands.sdk.event.types import SourceType
from openhands.sdk.utils.async_utils import (
    AsyncCallbackWrapper,
    AsyncConversationCallback,
)


class AsyncUtilsMockEvent(Event):
    """模拟对象测试事件。"""

    data: str = "test"
    source: SourceType = "agent"


def test_async_conversation_callback_type():
    """测试 AsyncConversationCallback 类型是否已正确定义。"""

    async def sample_callback(event: Event) -> None:
        pass

    # 这不应该引发任何类型错误
    callback: AsyncConversationCallback = sample_callback
    assert callable(callback)


def test_async_callback_wrapper_basic():
    """测试AsyncCallbackWrapper的基本功能。"""
    events_processed = []

    async def async_callback(event: Event) -> None:
        events_processed.append(f"processed: {event.source}")

    async def run_test():
        # 为异步回调创建事件循环
        loop = asyncio.get_running_loop()

        # 使用循环创建包装器
        wrapper = AsyncCallbackWrapper(async_callback, loop)

        # 创建并处理事件
        event = AsyncUtilsMockEvent()
        wrapper(event)

        # 稍等一下回调执行
        await asyncio.sleep(0.1)

    asyncio.run(run_test())

    assert len(events_processed) == 1
    assert events_processed[0] == "processed: agent"


def test_async_callback_wrapper_multiple_events():
    """使用多个事件测试 AsyncCallbackWrapper。"""
    events_processed = []

    async def async_callback(event: Event) -> None:
        events_processed.append(event.id)

    async def run_test():
        loop = asyncio.get_running_loop()
        wrapper = AsyncCallbackWrapper(async_callback, loop)

        events = [AsyncUtilsMockEvent() for _ in range(3)]

        for event in events:
            wrapper(event)

        # 等待所有回调完成
        await asyncio.sleep(0.1)

        return events

    events = asyncio.run(run_test())

    assert len(events_processed) == 3
    assert all(event.id in events_processed for event in events)


def test_async_callback_wrapper_with_stopped_loop():
    """测试循环未运行时的 AsyncCallbackWrapper 行为。"""
    events_processed = []

    async def async_callback(event: Event) -> None:
        events_processed.append("processed")

    # 创建循环但不运行它
    loop = asyncio.new_event_loop()
    wrapper = AsyncCallbackWrapper(async_callback, loop)

    event = AsyncUtilsMockEvent()

    # 由于循环未运行，因此不应执行回调
    wrapper(event)

    # 稍等一下
    time.sleep(0.1)

    # 由于循环未运行，不应处理任何事件
    assert len(events_processed) == 0

    loop.close()


def test_async_callback_wrapper_exception_handling():
    """测试异步回调中的异常不会使包装器崩溃。"""

    async def failing_callback(event: Event) -> None:
        raise ValueError("Test exception")

    async def run_test():
        loop = asyncio.get_running_loop()
        wrapper = AsyncCallbackWrapper(failing_callback, loop)

        event = AsyncUtilsMockEvent()

        # 这不应在调用线程时引发异常
        wrapper(event)

        # 等待回调执行（并失败）
        await asyncio.sleep(0.1)

    # 不应引发异常
    asyncio.run(run_test())


def test_async_callback_wrapper_concurrent_execution():
    """测试 AsyncCallbackWrapper 是否可以处理并发事件。"""
    events_processed = []

    async def async_callback(event: Event) -> None:
        await asyncio.sleep(0.05)  # 模拟异步工作
        events_processed.append(
            {
                "id": event.id,
                "source": event.source,
            }
        )

    async def run_test():
        loop = asyncio.get_running_loop()
        wrapper = AsyncCallbackWrapper(async_callback, loop)

        events = [AsyncUtilsMockEvent() for _ in range(5)]

        # 快速提交所有事件
        for event in events:
            wrapper(event)

        # 等待所有回调完成
        await asyncio.sleep(0.3)

        return events

    events = asyncio.run(run_test())

    assert len(events_processed) == 5

    # 检查所有事件是否已处理
    processed_ids = {entry["id"] for entry in events_processed}
    expected_ids = {event.id for event in events}
    assert processed_ids == expected_ids

    # 全部应该有相同的来源
    sources = {entry["source"] for entry in events_processed}
    assert sources == {"agent"}


def test_async_callback_wrapper_from_different_thread():
    """当从不同的线程调用时测试 AsyncCallbackWrapper。"""
    events_processed = []
    exception_caught = None

    async def async_callback(event: Event) -> None:
        events_processed.append(f"processed: {event.source}")

    def thread_function(wrapper):
        """函数在单独的线程中运行。"""
        try:
            event = AsyncUtilsMockEvent()
            wrapper(event)
        except Exception as e:
            nonlocal exception_caught
            exception_caught = e

    async def run_test():
        loop = asyncio.get_running_loop()
        wrapper = AsyncCallbackWrapper(async_callback, loop)

        # 启动一个将调用包装器的线程
        thread = threading.Thread(target=thread_function, args=(wrapper,))
        thread.start()

        # 等待线程和回调
        thread.join()
        await asyncio.sleep(0.1)

    asyncio.run(run_test())

    # 不应该引发异常
    assert exception_caught is None
    assert len(events_processed) == 1
    assert events_processed[0] == "processed: agent"


def test_async_callback_wrapper_performance():
    """测试包装器不会增加显着的开销。"""

    async def simple_callback(event: Event) -> None:
        pass  # 什么都不做

    async def run_test():
        loop = asyncio.get_running_loop()
        wrapper = AsyncCallbackWrapper(simple_callback, loop)

        events = [AsyncUtilsMockEvent() for _ in range(100)]

        start_time = time.time()
        for event in events:
            wrapper(event)

        # 给予处理时间
        await asyncio.sleep(0.1)

        end_time = time.time()
        total_time = end_time - start_time

        return total_time

    total_time = asyncio.run(run_test())

    # 应相当快地处理 100 个事件（少于 1 秒）
    assert total_time < 1.0
