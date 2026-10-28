"""异步 OpenHands SDK 的实用程序。

该模块提供了用于在上下文或同步对话处理中使用异步回调的实用程序。
"""

import asyncio
import threading
from collections.abc import Callable, Coroutine
from concurrent.futures import Future
from typing import Any

from openhands.sdk.event.base import Event


AsyncConversationCallback = Callable[[Event], Coroutine[Any, Any, None]]


class AsyncCallbackWrapper:
    """在不同的线程的事件循环中执行异步回调的包装器。

    该类实现 ConversationCallbackType 接口 (同步)，但在内部执行在不同线程中运行的事件
    循环中的异步回调。 这允许异步回调在同步对话上下文中使
    用。

    跟踪待处理的 future 以允许等待所有回调完成。
    """

    async_callback: AsyncConversationCallback
    loop: asyncio.AbstractEventLoop
    _pending_futures: list[Future]
    _lock: threading.Lock

    def __init__(
        self,
        async_callback: AsyncConversationCallback,
        loop: asyncio.AbstractEventLoop,
    ):
        self.async_callback = async_callback
        self.loop = loop
        self._pending_futures = []
        self._lock = threading.Lock()

    def __call__(self, event: Event):
        if self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.async_callback(event), self.loop
            )
            with self._lock:
                # 清理已完成的 future 以避免内存无限增长
                self._pending_futures = [
                    f for f in self._pending_futures if not f.done()
                ]
                self._pending_futures.append(future)

    def wait_for_pending(self, timeout: float | None = None) -> None:
        """等待所有待处理的回调完成。

        Args:
            timeout: 最长时间等待（以秒为单位）。 None表示无限期等待。

        Raises:
            TimeoutError: 如果等待时超过超时。
        """
        with self._lock:
            futures = list(self._pending_futures)

        for future in futures:
            try:
                future.result(timeout=timeout)
            except Exception:
                # 回调中的异常已记录，此处忽略
                pass
