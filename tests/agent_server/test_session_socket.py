"""会话套接字语义：成帧、重放边界，背压。"""

import asyncio
import json
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect

from openhands.agent_server.session_protocol import MAX_FRAME_BYTES
from openhands.agent_server.session_socket import (
    _ConnectionWriter,
    _inbound_loop,
    _ProgressSubscriber,
    _read_page,
    _replay,
    _SessionSubscriber,
)
from openhands.sdk import Message, TextContent
from openhands.sdk.agent.stream_context import (
    StreamAborted,
    StreamDelta,
    StreamStarted,
)
from openhands.sdk.event import MessageEvent, StreamingDeltaEvent
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent


def _msg(text: str) -> MessageEvent:
    return MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text=text)]),
    )


class _FakeWebSocket:
    """记录实际到达电线的内容，并可以将其挂起。"""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.gate: asyncio.Event | None = None

    async def send_text(self, payload: str) -> None:
        if self.gate is not None:
            await self.gate.wait()
        self.sent.append(payload)

    def frames(self) -> list[dict]:
        return [json.loads(p) for p in self.sent]


class _FakeEventLog:
    """足够的 EventLog 用于框架：按 id 索引，按索引读取，长度。"""

    def __init__(self) -> None:
        self._events: list = []
        self._by_id: dict[str, int] = {}

    def add(self, event) -> int:
        idx = len(self._events)
        self._events.append(event)
        self._by_id[event.id] = idx
        return idx

    def get_index(self, event_id: str) -> int:
        try:
            return self._by_id[event_id]
        except KeyError:
            raise KeyError(f"Unknown event_id: {event_id}")

    def __getitem__(self, idx: int):
        return self._events[idx]

    def __len__(self) -> int:
        return len(self._events)


async def _drain(writer: _ConnectionWriter) -> None:
    """让作者任务刷新已承认的内容。"""
    for _ in range(10):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_durable_frame_carries_seq_and_untouched_event():
    ws, log = _FakeWebSocket(), _FakeEventLog()
    event = _msg("hello")
    log.add(event)

    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _SessionSubscriber(writer=writer, events=log)  # type: ignore[arg-type]
    sub.go_live(None)
    await sub(event)
    await _drain(writer)
    await writer.aclose()

    (frame,) = ws.frames()
    assert frame["type"] == "durable"
    assert frame["seq"] == 0
    # 与旧版端点发送的字节相同。
    assert frame["event"] == event.model_dump(mode="json", exclude_none=True)


@pytest.mark.asyncio
async def test_deltas_never_reach_the_durable_channel():
    """将 token 增量放在 Webhook 和遥测上的错误。"""
    ws, log = _FakeWebSocket(), _FakeEventLog()
    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _SessionSubscriber(writer=writer, events=log)  # type: ignore[arg-type]
    sub.go_live(None)

    await sub(StreamingDeltaEvent(content="tok"))
    await sub(StreamingDeltaEvent(reasoning_content="think"))
    await _drain(writer)
    await writer.aclose()

    assert ws.frames() == []


@pytest.mark.asyncio
async def test_unpersisted_event_is_transient_and_carries_no_seq():
    ws, log = _FakeWebSocket(), _FakeEventLog()
    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _SessionSubscriber(writer=writer, events=log)  # type: ignore[arg-type]
    sub.go_live(None)

    await sub(ConversationStateUpdateEvent(key="execution_status", value="idle"))
    await _drain(writer)
    await writer.aclose()

    (frame,) = ws.frames()
    assert frame["type"] == "transient"
    assert "seq" not in frame


@pytest.mark.asyncio
async def test_replay_and_live_do_not_interleave_or_duplicate():
    """订阅（缓冲）->读取标记->重放->刷新。

    重播期间的事件着陆仅在历史记录之后到达一次。
    """
    ws, log = _FakeWebSocket(), _FakeEventLog()
    history = [_msg(f"h{i}") for i in range(3)]
    for e in history:
        log.add(e)

    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _SessionSubscriber(writer=writer, events=log)  # type: ignore[arg-type]

    through_seq = len(log) - 1

    # 其中两份在重播中到达：一份已经在磁盘上，一份是真正新的。
    await sub(history[2])
    live = _msg("live")
    log.add(live)
    await sub(live)

    assert await _replay(log, 0, through_seq + 1, writer)  # type: ignore[arg-type]
    sub.go_live(through_seq)
    await _drain(writer)
    await writer.aclose()

    frames = ws.frames()
    assert [f["seq"] for f in frames] == [0, 1, 2, 3], "no gaps, no duplicates"
    assert [f["event"]["id"] for f in frames] == [e.id for e in [*history, live]]


@pytest.mark.asyncio
async def test_persisted_state_update_is_durable_and_deduped():
    """日志中的 ConversationStateUpdateEvent 不能是暂时的。

    append_event 会存储这些信息，因此按类型决定会丢失它们的 seq 并破坏 dedupe — 事件
    会从回放和缓冲区再次到达。
    """
    ws, log = _FakeWebSocket(), _FakeEventLog()
    state_update = ConversationStateUpdateEvent(key="execution_status", value="running")
    log.add(state_update)
    through_seq = len(log) - 1

    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _SessionSubscriber(writer=writer, events=log)  # type: ignore[arg-type]

    # 缓冲中重播并且也从磁盘发送：一份副本必须到达线路。
    await sub(state_update)
    assert await _replay(log, 0, through_seq + 1, writer)  # type: ignore[arg-type]
    sub.go_live(through_seq)
    await _drain(writer)
    await writer.aclose()

    frames = ws.frames()
    assert [f["type"] for f in frames] == ["durable"], "sent twice, or sent transient"
    assert frames[0]["seq"] == 0


@pytest.mark.asyncio
async def test_live_only_connection_keeps_events_buffered_during_subscribe():
    """没有重播运行，因此任何内容都不会因为“已重播”而被丢弃。

    省略 ``after_seq`` 的客户端没有游标来恢复针对标记的重复数据删除操作将丢弃的内容。
    """
    ws, log = _FakeWebSocket(), _FakeEventLog()
    for i in range(3):
        log.add(_msg(f"h{i}"))

    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _SessionSubscriber(writer=writer, events=log)  # type: ignore[arg-type]

    # 在订阅期间到达，因此其 seq 低于标记。
    raced = _msg("landed during subscribe")
    log.add(raced)
    await sub(raced)

    # 仅直播：当没有重播发生时，端点通过 None。
    sub.go_live(None)
    await _drain(writer)
    await writer.aclose()

    frames = ws.frames()
    assert [f["event"]["id"] for f in frames] == [raced.id]
    assert frames[0]["seq"] == 3


@pytest.mark.asyncio
async def test_wedged_connection_drops_instead_of_blocking_the_publisher():
    """准入是同步：卡住的套接字绝不能阻止调用者。

    遗留端点在其订阅者中等待 send_json 会出现什么问题。
    """
    ws, log = _FakeWebSocket(), _FakeEventLog()
    ws.gate = asyncio.Event()  # 释放之前不接受任何内容

    writer = _ConnectionWriter(ws, max_pending_bytes=4096)  # type: ignore[arg-type]
    writer.start()
    sub = _SessionSubscriber(writer=writer, events=log)  # type: ignore[arg-type]
    sub.go_live(None)

    # 发布远远超出预算，并为发布者计时。
    started = asyncio.get_running_loop().time()
    for i in range(500):
        event = _msg(f"m{i}" * 50)
        log.add(event)
        await sub(event)
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.5, "publisher blocked on a wedged consumer"
    assert writer.closed, "over-budget connection should be dropped"
    assert writer.drop_reason == "slow_consumer"

    ws.gate.set()
    await writer.aclose()


@pytest.mark.asyncio
async def test_oversized_frame_drops_the_connection_not_the_event():
    """持久性必须在重新连接后仍然存在，因此无法发送的帧会杀死
    连接，以及客户端从其光标处恢复。"""
    ws, log = _FakeWebSocket(), _FakeEventLog()
    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _SessionSubscriber(writer=writer, events=log)  # type: ignore[arg-type]
    sub.go_live(None)

    huge = _msg("x" * (MAX_FRAME_BYTES + 1))
    log.add(huge)
    await sub(huge)
    await _drain(writer)

    assert writer.closed
    assert writer.drop_reason == "frame_too_large"
    assert ws.frames() == []
    await writer.aclose()


def test_replay_skips_unreadable_events_instead_of_failing():
    class _Corrupt(_FakeEventLog):
        def __getitem__(self, idx: int):
            if idx == 1:
                raise FileNotFoundError("half-written")
            return super().__getitem__(idx)

    log = _Corrupt()
    for i in range(3):
        log.add(_msg(f"e{i}"))

    page = _read_page(log, 0, 3)  # type: ignore[arg-type]
    assert [seq for seq, _ in page] == [0, 2]


@pytest.mark.asyncio
async def test_malformed_inbound_frame_is_reported_not_raised():
    """非 JSON 文本框不得逃逸入站循环。

    receive_json 引发 JSONDecodeError，而不是 WebSocketDisconnect，因此只捕获后者会导
    致一个坏帧导致连接崩溃。
    """
    ws = _FakeWebSocket()
    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()

    receives = 0

    async def receive_json():
        nonlocal receives
        receives += 1
        if receives == 1:
            raise json.JSONDecodeError("Expecting value", "not json", 0)
        raise WebSocketDisconnect()

    ws.receive_json = receive_json  # type: ignore[attr-defined]

    await asyncio.wait_for(
        _inbound_loop(uuid4(), ws, object(), writer),  # type: ignore[arg-type]
        timeout=5,
    )
    await _drain(writer)
    await writer.aclose()

    (frame,) = ws.frames()
    assert frame["type"] == "error"
    assert frame["code"] == "JSONDecodeError"
    # 循环继续进行，而不是放松。
    assert receives == 2


@pytest.mark.asyncio
async def test_progress_frames_reach_the_wire_with_their_identity():
    """StreamContext的帧映射到外层，一一对应。"""
    ws = _FakeWebSocket()
    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _ProgressSubscriber(writer)

    await sub(StreamStarted(item_id="item-1", attempt=1, anchor_seq=4))
    await sub(
        StreamDelta(
            item_id="item-1",
            attempt=1,
            order=0,
            kind="reasoning",
            content="thinking",
            chunk_id="chatcmpl-9",
            choice_index=0,
        )
    )
    await sub(StreamAborted(item_id="item-1", attempt=1, reason="cancelled"))
    await _drain(writer)
    await writer.aclose()

    started, delta, aborted = ws.frames()
    assert started == {
        "type": "item_started",
        "item_id": "item-1",
        "attempt": 1,
        "anchor_seq": 4,
    }
    assert delta["type"] == "delta"
    assert (delta["order"], delta["kind"], delta["content"]) == (
        0,
        "reasoning",
        "thinking",
    )
    # 提供者自己的身份，作为佐证进行。
    assert (delta["chunk_id"], delta["choice_index"]) == ("chatcmpl-9", 0)
    assert aborted["type"] == "item_aborted"
    assert aborted["reason"] == "cancelled"


@pytest.mark.asyncio
async def test_a_dropped_progress_frame_does_not_drop_the_connection():
    """进度可以从持久事件中恢复，因此它是可删除的。"""
    ws = _FakeWebSocket()
    writer = _ConnectionWriter(ws)  # type: ignore[arg-type]
    writer.start()
    sub = _ProgressSubscriber(writer)

    await sub(
        StreamDelta(
            item_id="item-1",
            attempt=1,
            order=0,
            kind="text",
            content="x" * (MAX_FRAME_BYTES + 1),
        )
    )
    await _drain(writer)
    assert writer.closed
