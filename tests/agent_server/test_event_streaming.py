"""测试 EventService 中的 token 流式传输回调接线。"""

import asyncio
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from litellm.types.utils import Delta, ModelResponseStream, StreamingChoices
from pydantic import SecretStr

from openhands.agent_server import server_details_router
from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import StoredConversation
from openhands.agent_server.pub_sub import Subscriber
from openhands.sdk import Event
from openhands.sdk.agent import ACPAgent, Agent
from openhands.sdk.agent.acp_agent import ACTIVITY_SIGNAL_INTERVAL
from openhands.sdk.agent.stream_context import StreamProgress, StreamStarted
from openhands.sdk.event import StreamingDeltaEvent
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import LocalWorkspace


def _make_chunk(
    content: str | None = None, reasoning_content: str | None = None
) -> ModelResponseStream:
    """构建一个最小的 ModelResponseStream 块进行测试。"""
    delta_kwargs: dict = {"role": "assistant"}
    if content is not None:
        delta_kwargs["content"] = content
    delta = Delta(**delta_kwargs)
    if reasoning_content is not None:
        object.__setattr__(delta, "reasoning_content", reasoning_content)
    choice = StreamingChoices(delta=delta, index=0, finish_reason=None)
    return ModelResponseStream(id="chunk-id", choices=[choice], model="test-model")


class _CollectorSubscriber(Subscriber):
    """选择增量并收集断言事件的订阅者。"""

    receives_streaming_deltas = True

    def __init__(self):
        self.events: list[Event] = []

    async def __call__(self, event: Event):
        self.events.append(event)

    async def close(self):
        pass


class _PlainSubscriber(_CollectorSubscriber):
    """保持默认值的收集器：它绝不能观察到增量。"""

    receives_streaming_deltas = False


@pytest.fixture
def event_service(tmp_path):
    with patch("openhands.sdk.llm.utils.model_info.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: {"data": []})
        service = EventService(
            stored=StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir=str(tmp_path / "workspace")),
            ),
            agent=Agent(
                llm=LLM(
                    usage_id="test-llm",
                    model="test-model",
                    api_key=SecretStr("test-key"),
                    stream=True,
                ),
                tools=[],
            ),
            conversations_dir=tmp_path / "conversations",
        )
        yield service


def _mock_local_conversation():
    """返回 LocalConversation 的补丁上下文管理器。"""
    return patch("openhands.agent_server.event_service.LocalConversation")


async def _start_and_capture_callback(event_service, tmp_path):
    """
    使用模拟的 LocalConversation 启动事件服务并返回 token 回调。
    """
    (tmp_path / "workspace").mkdir(exist_ok=True)

    with _mock_local_conversation() as MockConv:
        mock_conv = MagicMock()
        mock_conv.state = MagicMock()
        mock_conv.state.execution_status = "idle"
        mock_conv._state = MagicMock()
        mock_conv._on_event = MagicMock()
        MockConv.return_value = mock_conv

        await event_service.start()
        return MockConv.call_args.kwargs["token_callbacks"][0]


@pytest.mark.asyncio
async def test_start_wires_token_callback(event_service, tmp_path):
    (tmp_path / "workspace").mkdir(exist_ok=True)

    with _mock_local_conversation() as MockConv:
        mock_conv = MagicMock()
        mock_conv.state = MagicMock()
        mock_conv.state.execution_status = "idle"
        mock_conv._state = MagicMock()
        mock_conv._on_event = MagicMock()
        MockConv.return_value = mock_conv

        await event_service.start()

        call_kwargs = MockConv.call_args
        assert "token_callbacks" in call_kwargs.kwargs
        assert len(call_kwargs.kwargs["token_callbacks"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunk_kwargs, expected_content, expected_reasoning",
    [
        ({"content": "Hello"}, "Hello", None),
        ({"reasoning_content": "Let me think"}, None, "Let me think"),
        ({"content": "answer", "reasoning_content": "thought"}, "answer", "thought"),
    ],
    ids=["content-delta", "reasoning-delta", "both-deltas"],
)
async def test_callback_publishes_delta(
    event_service, tmp_path, chunk_kwargs, expected_content, expected_reasoning
):
    collector = _CollectorSubscriber()
    event_service._pub_sub.subscribe(collector)

    callback = await _start_and_capture_callback(event_service, tmp_path)

    callback(_make_chunk(**chunk_kwargs))
    await asyncio.sleep(0.05)

    delta_events = [e for e in collector.events if isinstance(e, StreamingDeltaEvent)]
    assert len(delta_events) == 1
    assert delta_events[0].content == expected_content
    assert delta_events[0].reasoning_content == expected_reasoning


@pytest.mark.asyncio
async def test_callback_ignores_delta_with_no_content_fields(event_service, tmp_path):
    """内容和 reasoning_content 均为 None 的块将被丢弃。"""
    collector = _CollectorSubscriber()
    event_service._pub_sub.subscribe(collector)

    callback = await _start_and_capture_callback(event_service, tmp_path)

    callback(_make_chunk())
    await asyncio.sleep(0.05)

    delta_events = [e for e in collector.events if isinstance(e, StreamingDeltaEvent)]
    assert len(delta_events) == 0


@pytest.mark.asyncio
async def test_callback_forwards_empty_string_delta(event_service, tmp_path):
    """必须转发空字符串块（在流边界合法）。"""
    collector = _CollectorSubscriber()
    event_service._pub_sub.subscribe(collector)

    callback = await _start_and_capture_callback(event_service, tmp_path)
    callback(_make_chunk(content=""))
    await asyncio.sleep(0.05)

    delta_events = [e for e in collector.events if isinstance(e, StreamingDeltaEvent)]
    assert len(delta_events) == 1
    assert delta_events[0].content == ""


@pytest.mark.asyncio
async def test_callback_handles_none_choices(event_service, tmp_path):
    """一些提供者会发出 choice=None 的 keepalive 块。"""
    collector = _CollectorSubscriber()
    event_service._pub_sub.subscribe(collector)

    callback = await _start_and_capture_callback(event_service, tmp_path)
    keepalive = ModelResponseStream(id="k", choices=[], model="test-model")
    object.__setattr__(keepalive, "choices", None)

    callback(keepalive)
    await asyncio.sleep(0.05)

    assert not [e for e in collector.events if isinstance(e, StreamingDeltaEvent)]


@pytest.mark.asyncio
async def test_token_callbacks_not_wired_when_stream_disabled(tmp_path):
    """如果没有LLM具有stream=True，则根本不附加流式传输回调。"""
    with patch("openhands.sdk.llm.utils.model_info.httpx.get") as mock_get:
        mock_get.return_value = MagicMock(json=lambda: {"data": []})
        service = EventService(
            stored=StoredConversation(
                id=uuid4(),
                workspace=LocalWorkspace(working_dir=str(tmp_path / "workspace")),
            ),
            agent=Agent(
                llm=LLM(
                    usage_id="test-llm",
                    model="test-model",
                    api_key=SecretStr("test-key"),
                    stream=False,
                ),
                tools=[],
            ),
            conversations_dir=tmp_path / "conversations",
        )
        (tmp_path / "workspace").mkdir(exist_ok=True)

        with _mock_local_conversation() as MockConv:
            mock_conv = MagicMock()
            mock_conv.state = MagicMock(execution_status="idle")
            mock_conv._state = MagicMock()
            mock_conv._on_event = MagicMock()
            MockConv.return_value = mock_conv

            await service.start()
            assert MockConv.call_args.kwargs["token_callbacks"] == []


@pytest.mark.asyncio
async def test_acp_agents_wire_token_callback_without_llm_streaming(tmp_path):
    """ACP AgentMessageChunk 文本应该流式传输，尽管 ACPAgent 没有 LLM。"""
    service = EventService(
        stored=StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir=str(tmp_path / "workspace")),
        ),
        agent=ACPAgent(acp_command=["echo", "test"]),
        conversations_dir=tmp_path / "conversations",
    )
    (tmp_path / "workspace").mkdir(exist_ok=True)

    with _mock_local_conversation() as MockConv:
        mock_conv = MagicMock()
        mock_conv.state = MagicMock(execution_status="idle")
        mock_conv._state = MagicMock()
        mock_conv._on_event = MagicMock()
        MockConv.return_value = mock_conv

        await service.start()
        assert len(MockConv.call_args.kwargs["token_callbacks"]) == 1


@pytest.mark.asyncio
async def test_acp_string_token_callback_publishes_delta(tmp_path):
    """ACPAgent invokes token  回调以纯文本块。"""
    service = EventService(
        stored=StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir=str(tmp_path / "workspace")),
        ),
        agent=ACPAgent(acp_command=["echo", "test"]),
        conversations_dir=tmp_path / "conversations",
    )
    collector = _CollectorSubscriber()
    service._pub_sub.subscribe(collector)
    (tmp_path / "workspace").mkdir(exist_ok=True)

    with _mock_local_conversation() as MockConv:
        mock_conv = MagicMock()
        mock_conv.state = MagicMock(execution_status="idle")
        mock_conv._state = MagicMock()
        mock_conv._on_event = MagicMock()
        MockConv.return_value = mock_conv

        await service.start()
        callback = MockConv.call_args.kwargs["token_callbacks"][0]

    callback("ACP live text")
    await asyncio.sleep(0.05)

    delta_events = [e for e in collector.events if isinstance(e, StreamingDeltaEvent)]
    assert len(delta_events) == 1
    assert delta_events[0].content == "ACP live text"
    assert delta_events[0].reasoning_content is None


@pytest.mark.asyncio
async def test_multiple_chunks_produce_multiple_events(event_service, tmp_path):
    collector = _CollectorSubscriber()
    event_service._pub_sub.subscribe(collector)

    callback = await _start_and_capture_callback(event_service, tmp_path)

    words = ["Hello", " ", "world", "!"]
    for word in words:
        callback(_make_chunk(content=word))

    await asyncio.sleep(0.05)

    delta_events = [e for e in collector.events if isinstance(e, StreamingDeltaEvent)]
    assert len(delta_events) == 4
    assert [e.content for e in delta_events] == words


@pytest.mark.asyncio
async def test_deltas_only_reach_subscribers_that_opted_in(event_service, tmp_path):
    """Delta 只到达选择加入的订阅者，而不是总线的 REST。"""
    streaming = _CollectorSubscriber()
    plain = _PlainSubscriber()
    event_service._pub_sub.subscribe(streaming)
    event_service._pub_sub.subscribe(plain)

    callback = await _start_and_capture_callback(event_service, tmp_path)
    callback(_make_chunk(content="Hello"))
    await asyncio.sleep(0.05)

    assert [e for e in streaming.events if isinstance(e, StreamingDeltaEvent)]
    assert not [e for e in plain.events if isinstance(e, StreamingDeltaEvent)]


# 一旦 /server_info 报告这么多空闲时间，运行时 API 就会获得一个托管 Pod； 它注入的值约为
#  20 分钟。
#
_IDLE_THRESHOLD = 20 * 60.0


@pytest.mark.asyncio
async def test_deltas_keep_idle_time_below_the_threshold(
    event_service, tmp_path, monkeypatch
):
    """超过空闲阈值的完成使 Pod 保持活动状态。

    增量永远不会是已持久化，因此持久事件路径上没有任何内容会在单个流式完成的长度内刷
    新空闲时钟。
    """
    callback = await _start_and_capture_callback(event_service, tmp_path)

    # 如果流长于空闲阈值且不发出持久事件，则离开服务器：人们会失去完成度。
    #
    monkeypatch.setattr(
        server_details_router,
        "_last_event_time",
        time.time() - 2 * _IDLE_THRESHOLD,
    )

    callback(_make_chunk(content="tok"))

    assert server_details_router.build_server_info().idle_time < _IDLE_THRESHOLD


@pytest.mark.asyncio
async def test_delta_idle_signal_is_throttled(event_service, tmp_path, monkeypatch):
    """第一个增量触及空闲计时器； 区间的 REST 则不然。"""
    callback = await _start_and_capture_callback(event_service, tmp_path)

    stale = time.time() - 2 * ACTIVITY_SIGNAL_INTERVAL
    monkeypatch.setattr(server_details_router, "_last_event_time", stale)

    # 无论进程时钟运行了多久，从未发出信号的服务都不得限制其自己的第一个增量。
    #
    callback(_make_chunk(content="first"))
    assert server_details_router._last_event_time > stale

    monkeypatch.setattr(server_details_router, "_last_event_time", stale)
    callback(_make_chunk(content="second"))
    assert server_details_router._last_event_time == stale


async def _start_and_capture_stream_callback(event_service, tmp_path):
    """启动服务并返回有线流进度回调。"""
    (tmp_path / "workspace").mkdir(exist_ok=True)

    with _mock_local_conversation() as MockConv:
        mock_conv = MagicMock()
        mock_conv.state = MagicMock()
        mock_conv.state.execution_status = "idle"
        mock_conv._state = MagicMock()
        mock_conv._on_event = MagicMock()
        MockConv.return_value = mock_conv

        await event_service.start()
        return MockConv.call_args.kwargs["stream_callbacks"][0]


class _ProgressCollector(Subscriber[StreamProgress]):
    def __init__(self):
        self.frames: list[StreamProgress] = []

    async def __call__(self, frame: StreamProgress):
        self.frames.append(frame)

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_stream_progress_reaches_its_own_subscribers(event_service, tmp_path):
    """进度依赖于单独的扇出，因此事件总线消费者不会看到它。"""
    callback = await _start_and_capture_stream_callback(event_service, tmp_path)

    progress = _ProgressCollector()
    event_service._stream_pub_sub.subscribe(progress)
    on_the_event_bus = _CollectorSubscriber()
    event_service._pub_sub.subscribe(on_the_event_bus)

    callback(StreamStarted(item_id="item-1", attempt=1, anchor_seq=3))
    await asyncio.sleep(0.05)

    assert progress.frames == [StreamStarted("item-1", 1, 3)]
    assert on_the_event_bus.events == []
