"""交付保证：非阻塞、有界、安全可撤销。"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import pytest

from openhands.agent_server.telemetry import models as m
from openhands.agent_server.telemetry.policy import (
    TelemetryConsent,
    TelemetryDecision,
)
from openhands.agent_server.telemetry.sink import (
    BufferedTelemetrySink,
    NoOpTelemetrySink,
)


def make_event(index: int = 0) -> m.DiagnosticEvent:
    return m.DiagnosticEvent(
        event_name=m.EventName.CONVERSATION_STARTED,
        occurred_at=datetime.now(UTC),
        distinct_id=f"user-{index}",
        runtime=m.RuntimeProperties(
            server_version="1.36.1",
            sdk_version="1.36.1",
            tools_version="1.36.1",
            build_git_sha="unknown",
            build_git_ref="unknown",
            python_version="3.13",
            platform="darwin",
            deferred_init=False,
        ),
        properties=m.ConversationStartedProperties(
            conversation_ref="a" * 32,
            llm_model_family="anthropic",
            agent_kind="agent",
            tool_count=index,
            is_fork=False,
            has_agent_profile=False,
            workspace_kind="localworkspace",
            confirmation_policy="neverconfirm",
        ),
    )


class RecordingExporter:
    def __init__(self):
        self.batches: list[list[m.DiagnosticEvent]] = []
        self.closed = False

    async def send(self, events):
        self.batches.append(list(events))

    async def aclose(self):
        self.closed = True

    @property
    def sent(self) -> list[m.DiagnosticEvent]:
        return [e for batch in self.batches for e in batch]


class HangingExporter:
    def __init__(self):
        self.calls = 0

    async def send(self, events):
        self.calls += 1
        await asyncio.sleep(3600)

    async def aclose(self):
        pass


class FailingExporter:
    def __init__(self):
        self.calls = 0

    async def send(self, events):
        self.calls += 1
        raise RuntimeError("downstream is down")

    async def aclose(self):
        pass


def granted(**kw) -> TelemetryDecision:
    kw.setdefault("consent", "granted")
    kw.setdefault("enabled", kw["consent"] == "granted")
    kw.setdefault("reason", "settings")
    return TelemetryDecision(**kw)


def denied() -> TelemetryDecision:
    return TelemetryDecision(
        consent=TelemetryConsent.DENIED, enabled=False, reason="settings"
    )


def build_sink(exporter, **kwargs: Any) -> BufferedTelemetrySink:
    defaults: dict[str, Any] = {
        "decision": granted(),
        "flush_delay": 0.05,
        "event_buffer_size": 10,
        "num_retries": 0,
        "retry_delay": 0.0,
        # 保持简短，因此只有 * 关于 * 关闭边界的测试才需要付费； 该测试将其覆盖回实际值
        # 。
        #
        "shutdown_flush_timeout": 0.1,
    }
    defaults.update(kwargs)
    return BufferedTelemetrySink(exporter, **defaults)


# ── 非阻塞──────────────────────────────────────────────────────────


async def test_emit_never_awaits_even_when_the_exporter_hangs():
    """核心保证：PubSub 扇出不会因遥测而停止。

    出口商睡了一个小时。 如果 ``emit`` 执行任何 I/O，或者根本等待导出器，则会超时而不
    是立即返回。
    """
    sink = build_sink(HangingExporter())
    sink.start()
    try:
        started = time.monotonic()
        for i in range(100):
            sink.emit(make_event(i))
        elapsed = time.monotonic() - started

        assert elapsed < 0.05, f"emit() blocked for {elapsed:.3f}s"
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)


async def test_emit_is_a_plain_sync_function():
    """这里的协程会在调用站点静默地重新引入阻塞。"""
    assert not asyncio.iscoroutinefunction(BufferedTelemetrySink.emit)
    assert not asyncio.iscoroutinefunction(NoOpTelemetrySink.emit)


# ── 有界队列──────────────────────────────────────────────────────────


async def test_queue_is_bounded_on_ingest_and_keeps_the_newest():
    exporter = HangingExporter()
    sink = build_sink(exporter, max_queue_size=5, flush_delay=3600)
    try:
        for i in range(50):
            sink.emit(make_event(i))

        assert len(sink._queue) == 5
        # 最旧的被删除，最新的被保留。
        retained = [e.distinct_id for e in sink._queue]
        assert retained == [f"user-{i}" for i in range(45, 50)]
        assert sink.dropped_count == 45
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)


async def test_a_backlog_drains_continuously_not_one_batch_per_flush():
    """Regression: 比一个批次更深的队列不得在批次之间停止。

    以前 ``_wake`` 在进行批次之前已被清除并且从未重新武装
    while the queue was still non-empty, so each remaining batch waited a full
    ``flush_delay``. 在生产默认设置（30秒延迟，20个事件批次）下，一个满的1000个事件队
    列需要大约25分钟才能清空，从而丢弃它本可以发送的事件。
    """
    exporter = RecordingExporter()
    sink = build_sink(exporter, flush_delay=0.5, event_buffer_size=10)
    sink.start()
    try:
        for i in range(50):
            sink.emit(make_event(i))

        # 远低于两个flush_delays：一个失速的排水管将提供〜10-20。
        await asyncio.sleep(0.7)

        assert len(exporter.sent) == 50, (
            f"only {len(exporter.sent)}/50 delivered in one flush cycle; "
            "the drain loop is waiting out flush_delay between batches"
        )
        assert len(sink._queue) == 0
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)


# ── 出口商失败────────────────────────────────────────────────────────


async def test_failing_exporter_does_not_kill_the_drain_task():
    exporter = FailingExporter()
    sink = build_sink(exporter, retry_delay=0.01)
    sink.start()
    try:
        sink.emit(make_event())
        await asyncio.sleep(0.3)

        assert exporter.calls >= 1
        assert sink._drain_task is not None
        assert not sink._drain_task.done(), "drain task died on exporter failure"
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)


async def test_failed_batches_are_dropped_not_requeued():
    """重新排队会将中断转变为无限制的内存增长。"""
    exporter = FailingExporter()
    sink = build_sink(exporter, retry_delay=0.01)
    sink.start()
    try:
        sink.emit(make_event())
        await asyncio.sleep(0.3)
        assert len(sink._queue) == 0
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)


async def test_shutdown_is_bounded_when_the_exporter_hangs():
    """楔入分析端点不得延长服务器关闭时间。"""
    sink = build_sink(HangingExporter(), flush_delay=3600, shutdown_flush_timeout=1.0)
    sink.start()
    sink.emit(make_event())

    started = time.monotonic()
    await asyncio.wait_for(sink.aclose(), timeout=15)
    elapsed = time.monotonic() - started

    # 上限为 shutdown_flush_timeout，而不是导出器的 3600 秒睡眠。
    assert 0.5 < elapsed < 4, f"shutdown took {elapsed:.1f}s"


async def test_healthy_shutdown_flushes_residual_events():
    exporter = RecordingExporter()
    sink = build_sink(exporter, flush_delay=3600)
    sink.start()
    sink.emit(make_event(1))
    sink.emit(make_event(2))

    await asyncio.wait_for(sink.aclose(), timeout=10)

    assert len(exporter.sent) == 2
    assert exporter.closed is True


# ── 同意────────────────────────────────────────────────────────────────


async def test_revocation_discards_the_queue_and_never_delivers():
    """自撤回同意后收集的事件不得发送。"""
    exporter = RecordingExporter()
    sink = build_sink(exporter, flush_delay=3600)
    sink.start()
    try:
        for i in range(5):
            sink.emit(make_event(i))
        assert len(sink._queue) == 5

        sink.on_decision_changed(denied())

        assert sink.enabled is False
        assert len(sink._queue) == 0

        await asyncio.sleep(0.2)
        assert exporter.batches == [], "revoked events were delivered"
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)
        assert exporter.batches == [], "revoked events were flushed on close"


async def test_emit_while_denied_is_dropped_and_cannot_leak_on_later_grant():
    """重新授予不得追溯性地发布预先同意的活动。"""
    exporter = RecordingExporter()
    sink = build_sink(exporter, decision=denied(), flush_delay=0.05)
    sink.start()
    try:
        assert sink.enabled is False
        for i in range(5):
            sink.emit(make_event(i))
        assert len(sink._queue) == 0

        sink.on_decision_changed(granted())
        await asyncio.sleep(0.2)

        assert exporter.sent == [], "pre-consent events leaked after grant"

        sink.emit(make_event(99))
        await asyncio.sleep(0.2)
        assert [e.distinct_id for e in exporter.sent] == ["user-99"]
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)


async def test_a_managed_decision_still_reports_as_locked():
    """云实施现在是一个种子 `managed` 标志，而不是一种模式。"""
    exporter = RecordingExporter()
    sink = build_sink(
        exporter,
        decision=TelemetryDecision(
            consent=TelemetryConsent.GRANTED,
            enabled=True,
            reason="settings",
            managed=True,
        ),
    )
    try:
        assert sink.enabled is True
        assert sink.decision.is_locked is True
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)


async def test_consent_is_refreshed_from_the_reader_on_the_drain_task():
    exporter = RecordingExporter()
    state = {"decision": granted()}

    async def reader():
        return state["decision"]

    sink = build_sink(exporter, decision=granted(), decision_reader=reader)
    sink.start()
    try:
        state["decision"] = denied()
        sink.emit(make_event())
        # 等待通过 CONSENT_REFRESH_SECONDS 门控的第一次检查。
        await asyncio.sleep(0.3)

        assert sink.enabled is False
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)


# ── 无操作──────────────────────────────────────────────────────────────────


async def test_noop_sink_is_inert():
    sink = NoOpTelemetrySink()
    assert sink.enabled is False
    sink.emit(make_event())
    await sink.aclose()


@pytest.mark.parametrize("mode", ["disabled"])
async def test_disabled_mode_never_enables(mode):
    sink = build_sink(RecordingExporter(), decision=denied())
    try:
        assert sink.enabled is False
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=10)
