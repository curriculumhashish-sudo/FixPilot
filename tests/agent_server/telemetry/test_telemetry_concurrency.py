"""死锁、取消和并发保证。

这里的每个测试都包含在硬 ``asyncio.wait_for`` 中：引入挂起的回归作为超时失败，而不是
永远阻塞 CI。

为什么要测试这些特定形状的背景：

* ``emit()`` 在 ``PubSub`` 的事件循环上运行； 漏任务在同一个循环上同时运行；
``on_consent_changed``同步调用
  from a request handler. All three touch ``_queue`` and ``_decision``.
* ``_read_consent`` 通过 ``asyncio.to_thread`` 在工作线程线程上运行。 取消等待
``to_thread`` 的任务不会停止线程，
因此 shutdown 不能等待它。
* ``FileSettingsStore.update()`` 在新的 fd 上采用阻塞 ``fcntl.flock``，这是 ** 而不是
 ** 可重入 — 来自同一进
程的嵌套更新将对其自身进行死锁。
"""

import asyncio

from tests.agent_server.telemetry.test_telemetry_sink import (
    RecordingExporter,
    build_sink,
    denied,
    granted,
    make_event,
)


TIMEOUT = 10.0


# ── 取消 / 关机────────────────────────────────────────────────


async def test_shutdown_while_consent_reader_is_blocked_in_a_thread():
    """取消等待 to_thread 的任务不得等待线程。

    读取器阻塞在永远不会释放的线程原语上，因此如果 aclose() 等待工作器线程，则这将挂
    起。
    """
    release = asyncio.Event()  # 故意不设置

    async def blocking_reader():
        await release.wait()
        return granted()

    sink = build_sink(
        RecordingExporter(), decision_reader=blocking_reader, flush_delay=0.01
    )
    sink.start()
    sink.emit(make_event())
    await asyncio.sleep(0.1)  # let the drain task enter the reader

    await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)


async def test_shutdown_while_dispatch_is_in_flight():
    """aclose() 不得等待正在发送的导出器。"""

    class SlowExporter:
        async def send(self, events):
            await asyncio.sleep(3600)

        async def aclose(self):
            pass

    sink = build_sink(SlowExporter(), flush_delay=0.01, shutdown_flush_timeout=0.2)
    sink.start()
    sink.emit(make_event())
    await asyncio.sleep(0.15)

    await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)


async def test_concurrent_aclose_calls_do_not_deadlock_or_double_close():
    exporter = RecordingExporter()
    sink = build_sink(exporter)
    sink.start()
    sink.emit(make_event())

    await asyncio.wait_for(
        asyncio.gather(sink.aclose(), sink.aclose(), sink.aclose()), timeout=TIMEOUT
    )
    assert exporter.closed is True


async def test_aclose_without_start_does_not_hang():
    sink = build_sink(RecordingExporter())
    await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)


async def test_emit_after_close_is_a_no_op_and_does_not_raise():
    exporter = RecordingExporter()
    sink = build_sink(exporter)
    sink.start()
    await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)

    sink.emit(make_event())
    assert sink.enabled is False
    assert len(sink._queue) == 0


# ── 并发突变────────────────────────────────────────────────────


async def test_revocation_racing_a_burst_of_emits():
    """交错emit()和撤销不得丢失或泄漏事件。"""
    exporter = RecordingExporter()
    sink = build_sink(exporter, flush_delay=0.01)
    sink.start()
    try:

        async def emitter():
            for i in range(500):
                sink.emit(make_event(i))
                if i % 50 == 0:
                    await asyncio.sleep(0)

        async def flipper():
            for _ in range(20):
                sink.on_decision_changed(denied())
                await asyncio.sleep(0)
                sink.on_decision_changed(granted())
                await asyncio.sleep(0)

        await asyncio.wait_for(asyncio.gather(emitter(), flipper()), timeout=TIMEOUT)

        # 结束被拒绝：不能再传送任何内容并且队列为空。
        sink.on_decision_changed(denied())
        assert len(sink._queue) == 0

        before = len(exporter.sent)
        await asyncio.sleep(0.1)
        assert len(exporter.sent) == before
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)


async def test_drain_survives_a_consent_reader_that_always_raises():
    calls = {"n": 0}

    async def broken_reader():
        calls["n"] += 1
        raise RuntimeError("settings unreadable")

    exporter = RecordingExporter()
    sink = build_sink(exporter, decision_reader=broken_reader, flush_delay=0.02)
    sink.start()
    try:
        sink.emit(make_event())
        await asyncio.sleep(0.3)

        assert calls["n"] >= 1, "consent reader was never exercised"
        assert len(exporter.sent) >= 1
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)


async def test_sink_never_blocks_the_loop_under_load():
    """当遥测饱和时，心跳协程必须保持滴答作响。"""
    ticks = {"n": 0}

    async def heartbeat():
        for _ in range(50):
            ticks["n"] += 1
            await asyncio.sleep(0.001)

    class SlowExporter:
        async def send(self, events):
            await asyncio.sleep(0.05)

        async def aclose(self):
            pass

    sink = build_sink(SlowExporter(), flush_delay=0.01)
    sink.start()
    try:
        hb = asyncio.create_task(heartbeat())
        for i in range(2000):
            sink.emit(make_event(i))
        await asyncio.wait_for(hb, timeout=TIMEOUT)
        assert ticks["n"] == 50
    finally:
        await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)


# ── “永不中断对话”保证 ──────────────────────────── 每个订阅者入口都由注入的故障驱动；
# None 可能会传播，因为它们在实时运行期间在 PubSub 扇出内运行。
#


def _subscriber(sink):
    import uuid

    from openhands.agent_server.telemetry.factory import (
        DiagnosticEventFactory,
        build_runtime_properties,
    )
    from openhands.agent_server.telemetry.subscriber import (
        ConversationTelemetryContext,
        TelemetrySubscriber,
    )

    cid = uuid.uuid4()
    factory = DiagnosticEventFactory(
        runtime=build_runtime_properties(deferred_init=False),
        salt="s",
    )
    return TelemetrySubscriber(
        conversation_id=cid,
        sink=sink,
        factory=factory,
        context=ConversationTelemetryContext(
            conversation_ref=factory.conversation_ref(cid),
            user_id=None,
            llm_model_family="anthropic",
            agent_kind="agent",
            tool_count=0,
            is_fork=False,
            has_agent_profile=False,
            workspace_kind="localworkspace",
            confirmation_policy="neverconfirm",
        ),
    )


class _ExplodingSink:
    enabled = True

    def emit(self, event):
        raise RuntimeError("sink exploded")

    def on_consent_changed(self, consent):
        pass

    async def aclose(self):
        pass


async def test_emit_started_swallows_a_sink_failure():
    _subscriber(_ExplodingSink()).emit_started()  # 不得提高


async def test_close_swallows_a_terminal_emit_failure():
    await asyncio.wait_for(_subscriber(_ExplodingSink()).close(), timeout=TIMEOUT)


async def test_call_swallows_a_failure_from_any_event_type():
    from openhands.sdk.event import AgentErrorEvent, ConversationStateUpdateEvent
    from openhands.sdk.event.conversation_error import ConversationErrorEvent

    sub = _subscriber(_ExplodingSink())
    for event in (
        ConversationStateUpdateEvent(key="execution_status", value="idle"),
        ConversationStateUpdateEvent(key="execution_status", value="finished"),
        AgentErrorEvent(error="boom", tool_name="bash", tool_call_id="c1"),
        ConversationErrorEvent(source="environment", code="X", detail="d"),
    ):
        await asyncio.wait_for(sub(event), timeout=TIMEOUT)


async def test_capture_usage_swallows_a_malformed_stats_block():
    """full_state 中的形状变化必须降低，而不是升高。"""
    from openhands.sdk.event import ConversationStateUpdateEvent

    class _Collecting:
        enabled = True

        def __init__(self):
            self.events = []

        def emit(self, e):
            self.events.append(e)

        def on_consent_changed(self, c):
            pass

        async def aclose(self):
            pass

    sink = _Collecting()
    sub = _subscriber(sink)
    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await sub(
        ConversationStateUpdateEvent(
            key="full_state",
            value={
                "execution_status": "finished",
                # 统计数据的形状一直都是错误的
                "stats": {"usage_to_metrics": {"a": "not-a-dict", "b": None}},
            },
        )
    )
    payload = sink.events[0].to_payload()
    assert payload["total_tokens_bucket"] in {"lt-1000", "unknown"}
    assert payload["terminal_status"] == "finished"


async def test_shutdown_is_bounded_when_exporter_aclose_hangs():
    """Regression: 出口商收盘价没有上限。

    对于 PostHog 这就是真正的网络 I/O 场景 capture() 只进行队列操作，所以 aclose() ->
     client.shutdown() 是
    flush() + join(), 以及 posthog 的消费者默认为重试10 个超时每批15元。 不可达端点在
    这里阻止了 uvicorn 的生命周期几分钟。
    """
    import time

    class HangingCloseExporter:
        async def send(self, events):
            pass

        async def aclose(self):
            await asyncio.sleep(3600)

    sink = build_sink(HangingCloseExporter(), shutdown_flush_timeout=0.5)
    sink.start()
    sink.emit(make_event())

    started = time.monotonic()
    await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)
    elapsed = time.monotonic() - started

    assert elapsed < 4, f"aclose() took {elapsed:.1f}s; the exporter close is uncapped"


async def test_shutdown_is_bounded_when_both_send_and_aclose_hang():
    """两条腿都有上限，因此最坏情况的范围是超时的 2 倍。"""
    import time

    class FullyHangingExporter:
        async def send(self, events):
            await asyncio.sleep(3600)

        async def aclose(self):
            await asyncio.sleep(3600)

    sink = build_sink(
        FullyHangingExporter(), flush_delay=3600, shutdown_flush_timeout=0.5
    )
    sink.start()
    sink.emit(make_event())

    started = time.monotonic()
    await asyncio.wait_for(sink.aclose(), timeout=TIMEOUT)
    elapsed = time.monotonic() - started

    assert elapsed < 5, f"aclose() took {elapsed:.1f}s"
