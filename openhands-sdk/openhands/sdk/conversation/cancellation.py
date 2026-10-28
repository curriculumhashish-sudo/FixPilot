"""用于工具执行的协作取消 token。

``CancellationToken`` 是一个线程安全标志，它传播
``interrupt()`` 信号降至飞行中工具调用。 token 是为每个 ``run()`` / ``arun()`` 调用新
鲜创建的，并存储在：class:
`LocalConversation` 上，以便：

* ``interrupt()``可以立即设置，
* :class:`ParallelToolExecutor` 可以跳过待处理的工具，并且
* 个别工具可以检查它是否提前退出。

token 故意是 ** 而不是 ** ``asyncio`` 原语——它必须可以从事件循环线程和线程池工作线程
中使用。
"""

from __future__ import annotations

import threading


class CancellationToken:
    """线程安全取消标志。

    >>> token = CancellationToken()
    >>> token.is_cancelled
    False
    >>> token.cancel()
    >>> token.is_cancelled
    True
    """

    __slots__ = ("_event",)

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """信号取消。 幂等。"""
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()
