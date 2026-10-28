"""有界的异步传递永远不会阻止对话或使对话失败。

承载决策是：meth:`TelemetrySink.emit`是**同步**。
``PubSub.__call__`` *等待其订阅者在*中。因此，``asyncio.gather``中每个子会话的订阅者
在执行内联网络I/O时，都会导致事件扇出。
``emit`` 因此附加到内存中的双端队列并在单个事件循环步骤中返回； 所有 I/O 都发生在单独
的长期耗尽任务上。

失败策略故意与``WebhookSubscriber``不同：

* 队列通过 ``deque(maxlen=…)`` 限制在摄取 ** 上的 **，而不是仅限制在重试路径上，因此
楔形导出器无法无限制地增加内存；
* 一个耗尽其重试的批次会被**丢弃，而不是重新排队**——重新排队会将下游的中断转换为无限
的内存和一个永久满的旧事件队列。
* 撤销**丢弃**队列而不是耗尽它。
"""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Final, Protocol

from openhands.agent_server.telemetry.models import DiagnosticEvent
from openhands.agent_server.telemetry.policy import TelemetryDecision
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)

# ：同意缓存TTL。 撤销并不等待； 端点推动。
CONSENT_REFRESH_SECONDS: Final[float] = 5.0

# ：限制最终冲洗，因此挂起的端点无法延长关闭时间。
SHUTDOWN_FLUSH_TIMEOUT_SECONDS: Final[float] = 5.0

_MAX_BACKOFF_SECONDS: Final[float] = 60.0


class TelemetryExporter(Protocol):
    """将一批货物运送到某个地方。 唯一的供应商意识接缝。"""

    async def send(self, events: list[DiagnosticEvent]) -> None: ...

    async def aclose(self) -> None: ...


class TelemetrySink(Protocol):
    """服务器的REST取决于什么。 绝不特定于供应商。"""

    @property
    def enabled(self) -> bool: ...

    def emit(self, event: DiagnosticEvent) -> None:
        """接受一个事件。 必须是非阻塞的并且绝不能引发。"""
        ...

    def on_decision_changed(self, decision: TelemetryDecision) -> None:
        """立即应用重新解决的同意决定。"""
        ...

    async def aclose(self) -> None: ...


class NoOpTelemetrySink:
    """默认。 廉价地丢弃一切。"""

    @property
    def enabled(self) -> bool:
        return False

    # 忽略参数； 名称与关键字调用者的协议相匹配。
    def emit(self, event: DiagnosticEvent) -> None:  # noqa: ARG002
        return None

    def on_decision_changed(self, decision: TelemetryDecision) -> None:  # noqa: ARG002
        return None

    async def aclose(self) -> None:
        return None


class BufferedTelemetrySink:
    """具有有限内存和隔离故障的队列和排放接收器。"""

    def __init__(
        self,
        exporter: TelemetryExporter,
        *,
        decision: TelemetryDecision,
        decision_reader: Callable[[], Awaitable[TelemetryDecision]] | None = None,
        max_queue_size: int = 1000,
        event_buffer_size: int = 20,
        flush_delay: float = 30.0,
        num_retries: int = 2,
        retry_delay: float = 5.0,
        shutdown_flush_timeout: float = SHUTDOWN_FLUSH_TIMEOUT_SECONDS,
    ) -> None:
        self._exporter = exporter
        self._shutdown_flush_timeout = shutdown_flush_timeout
        self._decision: TelemetryDecision = decision
        self._decision_reader = decision_reader
        self._event_buffer_size = max(1, event_buffer_size)
        self._flush_delay = max(0.1, flush_delay)
        self._num_retries = max(0, num_retries)
        self._retry_delay = max(0.0, retry_delay)

        self._queue: deque[DiagnosticEvent] = deque(maxlen=max(1, max_queue_size))
        self._wake = asyncio.Event()
        self._closed = False
        self._dropped_count = 0
        self._failure_streak = 0
        self._consent_checked_at: float | None = None
        self._drain_task: asyncio.Task | None = None

    def start(self) -> None:
        """产生排水任务。 保留在实例上，从未成为孤儿。"""
        if self._drain_task is None:
            self._drain_task = asyncio.create_task(
                self._drain_loop(), name="telemetry-drain"
            )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._wake.set()

        if self._drain_task is not None:
            self._drain_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._drain_task
            self._drain_task = None

        if self._decision.enabled and self._queue:
            batch = list(self._queue)
            self._queue.clear()
            with suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(
                    self._exporter.send(batch),
                    timeout=self._shutdown_flush_timeout,
                )

        self._queue.clear()
        # 还封顶了。 对于 PostHog，这是真正的网络 I/O 发生的地方：capture() 仅排队，因此
        #  aclose() -> client.shutdown() 是 flush() + join()，posthog 的消费者默认为重试
        # =10
        #
        # timeout=15 per batch. Unbounded, an unreachable endpoint blocks the
        # uvicorn的寿命在这里只有几分钟。
        with suppress(Exception, asyncio.CancelledError):
            await asyncio.wait_for(
                self._exporter.aclose(), timeout=self._shutdown_flush_timeout
            )

    @property
    def enabled(self) -> bool:
        return self._decision.enabled and not self._closed

    @property
    def decision(self) -> TelemetryDecision:
        return self._decision

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def on_decision_changed(self, decision: TelemetryDecision) -> None:
        """立即应用重新解决的决定。

        从设置更新路径同步调用，因此撤销无需等待刷新间隔即可生效。 撤销时，队列被 **
        丢弃而不是刷新 ** — 与
        ``WebhookSubscriber.close()``. 根据已撤回的同意收集的活动不得进行。
        """
        self._apply_decision(decision)

    def _apply_decision(self, decision: TelemetryDecision) -> None:
        was_enabled = self._decision.enabled
        self._decision = decision
        if was_enabled and not decision.enabled:
            discarded = len(self._queue)
            self._queue.clear()
            logger.info(
                "Telemetry disabled (%s); discarded %d queued event(s)",
                decision.reason,
                discarded,
            )

    async def _refresh_consent_if_stale(self) -> None:
        """重新阅读已持久化对排水任务的同意，切勿内联。

        设置存储是读取的文件，因此它不能发生在：meth:`emit` 中的热路径上。
        """
        if self._decision_reader is None:
            return

        loop = asyncio.get_running_loop()
        now = loop.time()
        if (
            self._consent_checked_at is not None
            and now - self._consent_checked_at < CONSENT_REFRESH_SECONDS
        ):
            return
        self._consent_checked_at = now

        try:
            decision = await self._decision_reader()
        except Exception as exc:
            logger.debug("Telemetry consent refresh failed: %s", type(exc).__name__)
            return

        if decision != self._decision:
            self._apply_decision(decision)

    def emit(self, event: DiagnosticEvent) -> None:
        """对事件进行排队。 同步，非阻塞，从不引发。

        A ``deque`` 与 ``maxlen`` 在溢出时丢弃最旧的元素 O(1) 并且无法抛出异常，因此
        没有回传到会话执行中的失败模式。
        """
        if not self.enabled:
            return
        try:
            if len(self._queue) == self._queue.maxlen:
                self._dropped_count += 1
            self._queue.append(event)
            self._wake.set()
        except Exception:  # pragma: no cover - defensive, deque cannot raise
            logger.debug("Telemetry emit failed", exc_info=True)

    async def _drain_loop(self) -> None:
        while not self._closed:
            try:
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout=self._flush_delay)
                self._wake.clear()

                await self._refresh_consent_if_stale()

                if not self._decision.enabled:
                    self._queue.clear()
                    continue

                batch = self._take_batch()
                if batch:
                    await self._dispatch(batch)
                    if self._queue:
                        # 继续排水； 不要等待每批次 flush_delay。
                        self._wake.set()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Telemetry drain iteration failed", exc_info=True)
                await asyncio.sleep(self._retry_delay)

    def _take_batch(self) -> list[DiagnosticEvent]:
        batch: list[DiagnosticEvent] = []
        while self._queue and len(batch) < self._event_buffer_size:
            batch.append(self._queue.popleft())
        return batch

    async def _dispatch(self, batch: list[DiagnosticEvent]) -> None:
        for attempt in range(self._num_retries + 1):
            # 重新检查：撤销可能已在重试中期生效。
            if not self._decision.enabled:
                return
            try:
                await self._exporter.send(batch)
                self._failure_streak = 0
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if attempt < self._num_retries:
                    await asyncio.sleep(self._retry_delay)
                    continue
                self._failure_streak += 1
                # 每次连续发出一个警告，因此中断不会淹没日志。
                if self._failure_streak == 1:
                    logger.warning(
                        "Telemetry export failing (%s); dropping %d event(s). "
                        "Further failures logged at debug level.",
                        type(exc).__name__,
                        len(batch),
                    )
                else:
                    logger.debug(
                        "Telemetry export failure #%d (%s)",
                        self._failure_streak,
                        type(exc).__name__,
                    )
                self._dropped_count += len(batch)
                # 上限：这会在排水任务上休眠。
                backoff = min(
                    self._retry_delay * (2 ** min(self._failure_streak, 4)),
                    _MAX_BACKOFF_SECONDS,
                )
                await asyncio.sleep(backoff)
                return
