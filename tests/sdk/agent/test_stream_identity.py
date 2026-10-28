"""流产生的持久事件带有流创建的 id。

:class:`Agent` 入口：同步路径也会流，因此仅异步的修复可以解决一半问题。

参见 https://github.com/OpenHands/software-agent-sdk/issues/4682.
"""

from collections.abc import Sequence
from typing import cast

import pytest
from litellm.types.utils import Delta, ModelResponseStream, StreamingChoices
from pydantic import PrivateAttr

from openhands.sdk.agent import Agent
from openhands.sdk.agent.stream_context import (
    StreamAborted,
    StreamDelta,
    StreamStarted,
)
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event import ActionEvent, MessageEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.llm.exceptions import LLMNoResponseError
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


class _StreamEchoAction(Action):
    text: str


class _StreamEchoObservation(Observation):
    pass


class _StreamEchoExecutor(ToolExecutor[_StreamEchoAction, _StreamEchoObservation]):
    def __call__(
        self, action: _StreamEchoAction, conversation=None
    ) -> _StreamEchoObservation:
        return _StreamEchoObservation.from_text(action.text)


class _StreamEchoTool(ToolDefinition[_StreamEchoAction, _StreamEchoObservation]):
    name = "stream_echo"

    @classmethod
    def create(cls, conv_state=None) -> Sequence["_StreamEchoTool"]:
        return [
            cls(
                description="Echo the given text",
                action_type=_StreamEchoAction,
                observation_type=_StreamEchoObservation,
                executor=_StreamEchoExecutor(),
            )
        ]


register_tool("EchoStreamTool", _StreamEchoTool)


class StreamingTestLLM(TestLLM):
    """首先将脚本文本作为块发出的 ``TestLLM``。"""

    _chunks: list[str] = PrivateAttr(default_factory=list)
    _raises: BaseException | None = PrivateAttr(default=None)
    _seen_on_token: list = PrivateAttr(default_factory=list)

    def script(self, chunks: list[str], raises: BaseException | None = None):
        self._chunks = chunks
        self._raises = raises
        return self

    def _stream(self, on_token) -> None:
        for text in self._chunks:
            if on_token is None:
                continue
            on_token(
                ModelResponseStream(
                    id="completion-1",
                    model="test-model",
                    choices=[
                        StreamingChoices(
                            delta=Delta(role="assistant", content=text),
                            index=0,
                            finish_reason=None,
                        )
                    ],
                )
            )

    def completion(self, messages, tools=None, on_token=None, **kwargs):  # type: ignore[override]
        self._seen_on_token.append(on_token)
        self._stream(on_token)
        if self._raises is not None:
            raise self._raises
        return super().completion(messages, tools=tools, **kwargs)

    async def acompletion(self, messages, tools=None, on_token=None, **kwargs):  # type: ignore[override]
        # TestLLM.acompletion 删除了 on_token，因此改为在此处进行流式传输。
        self._stream(on_token)
        if self._raises is not None:
            raise self._raises
        return await super().acompletion(messages, tools=tools, **kwargs)


def _conversation(tmp_path, llm, frames: list, tools: Sequence[Tool] = ()):
    agent = Agent(llm=llm, tools=list(tools))
    convo = LocalConversation(
        agent=agent,
        workspace=str(tmp_path / "workspace"),
        persistence_dir=str(tmp_path / "conversations"),
        visualizer=None,
        stream_callbacks=[frames.append],
    )
    convo._ensure_agent_ready()
    return convo


def _llm(messages, chunks, raises=None) -> StreamingTestLLM:
    llm = cast(StreamingTestLLM, StreamingTestLLM.from_messages(messages))
    llm.stream = True
    return llm.script(chunks, raises)


def test_the_message_carries_the_id_its_stream_minted(tmp_path):
    frames: list = []
    llm = _llm(
        [Message(role="assistant", content=[TextContent(text="Hello there")])],
        ["Hello ", "there"],
    )
    convo = _conversation(tmp_path, llm, frames)

    events: list = []
    convo.agent.step(convo, on_event=events.append)

    started = next(f for f in frames if isinstance(f, StreamStarted))
    message = next(e for e in events if isinstance(e, MessageEvent))
    assert message.id == started.item_id
    assert [f.content for f in frames if isinstance(f, StreamDelta)] == [
        "Hello ",
        "there",
    ]
    # 由于持久事件而退出，因此不会中止。
    assert not any(isinstance(f, StreamAborted) for f in frames)


@pytest.mark.asyncio
async def test_astep_mints_the_same_way(tmp_path):
    frames: list = []
    llm = _llm(
        [Message(role="assistant", content=[TextContent(text="Hello there")])],
        ["Hello ", "there"],
    )
    convo = _conversation(tmp_path, llm, frames)

    events: list = []
    await convo.agent.astep(convo, on_event=events.append)

    started = next(f for f in frames if isinstance(f, StreamStarted))
    message = next(e for e in events if isinstance(e, MessageEvent))
    assert message.id == started.item_id


def test_a_tool_call_turn_retires_the_slot_on_its_first_action(tmp_path):
    """流式文本是该操作的想法，因此该操作将其关闭。"""
    frames: list = []
    llm = _llm(
        [
            Message(
                role="assistant",
                content=[TextContent(text="Listing the directory")],
                tool_calls=[
                    MessageToolCall(
                        id="call-1",
                        name="stream_echo",
                        arguments='{"text": "hi"}',
                        origin="completion",
                    )
                ],
            )
        ],
        ["Listing ", "the directory"],
    )
    convo = _conversation(tmp_path, llm, frames, tools=[Tool(name="EchoStreamTool")])

    events: list = []
    convo.agent.step(convo, on_event=events.append)

    started = next(f for f in frames if isinstance(f, StreamStarted))
    action = next(e for e in events if isinstance(e, ActionEvent))
    assert action.id == started.item_id
    assert not any(isinstance(f, StreamAborted) for f in frames)


def test_an_invalid_tool_call_retires_the_stream_with_its_action(tmp_path):
    frames: list = []
    llm = _llm(
        [
            Message(
                role="assistant",
                content=[TextContent(text="Trying the requested operation")],
                tool_calls=[
                    MessageToolCall(
                        id="call-invalid",
                        name="missing_tool",
                        arguments="{}",
                        origin="completion",
                    )
                ],
            )
        ],
        ["Trying the requested operation"],
    )
    convo = _conversation(tmp_path, llm, frames)

    events: list = []
    convo.agent.step(convo, on_event=events.append)

    started = next(f for f in frames if isinstance(f, StreamStarted))
    invalid_action = next(
        e for e in events if isinstance(e, ActionEvent) and e.action is None
    )
    assert invalid_action.id == started.item_id
    assert not any(isinstance(f, StreamAborted) for f in frames)


def test_a_provider_failure_retires_the_slot_with_an_abort(tmp_path):
    frames: list = []
    llm = _llm(
        [Message(role="assistant", content=[TextContent(text="unused")])],
        ["half a "],
        raises=LLMNoResponseError("provider gave up"),
    )
    convo = _conversation(tmp_path, llm, frames)

    with pytest.raises(LLMNoResponseError):
        convo.agent.step(convo, on_event=lambda _: None)

    started = [f for f in frames if isinstance(f, StreamStarted)]
    aborted = [f for f in frames if isinstance(f, StreamAborted)]
    assert len(started) == len(aborted) == 1
    assert aborted[0].item_id == started[0].item_id


def test_a_persistence_failure_after_streaming_retires_the_slot(tmp_path):
    """id 在事件发出之前分发； 发射可以提高。"""
    frames: list = []
    llm = _llm(
        [Message(role="assistant", content=[TextContent(text="hello there")])],
        ["hello ", "there"],
    )
    convo = _conversation(tmp_path, llm, frames)

    def explode(event):
        if isinstance(event, MessageEvent) and event.source == "agent":
            raise RuntimeError("persisting the durable event failed")

    with pytest.raises(RuntimeError):
        convo.agent.step(convo, on_event=explode)

    started = [f for f in frames if isinstance(f, StreamStarted)]
    aborted = [f for f in frames if isinstance(f, StreamAborted)]
    assert len(started) == len(aborted) == 1
    assert aborted[0].item_id == started[0].item_id


def test_no_stream_consumer_leaves_the_llm_free_to_skip_streaming(tmp_path):
    """如果没有消费者，智能体不得强制流式传输完成。"""
    llm = _llm([Message(role="assistant", content=[TextContent(text="hi")])], ["hi"])
    agent = Agent(llm=llm, tools=[])
    convo = LocalConversation(
        agent=agent,
        workspace=str(tmp_path / "workspace"),
        persistence_dir=str(tmp_path / "conversations"),
        visualizer=None,
    )
    convo._ensure_agent_ready()

    convo.agent.step(convo, on_event=lambda _: None)

    assert llm._seen_on_token == [None]


def test_a_step_that_never_reaches_the_provider_opens_nothing(tmp_path):
    """没有 LLM 调用，没有槽——所以没有什么可以中止的。"""
    frames: list = []
    llm = _llm([Message(role="assistant", content=[TextContent(text="hi")])], [])
    convo = _conversation(tmp_path, llm, frames)

    convo.agent.step(convo, on_event=lambda _: None)

    assert frames == []


def test_a_resolved_secret_is_masked_in_the_deltas(tmp_path):
    """LLM 流路径在此之前没有任何屏蔽； 现在确实如此。

    仅屏蔽已经解析的值。 首先导出可以到达模型输出的机密以用于命令，从而解决该问题。
    """
    frames: list = []
    llm = _llm(
        [Message(role="assistant", content=[TextContent(text="done")])],
        ["the token is ", "hunter2"],
    )
    convo = _conversation(tmp_path, llm, frames)
    convo.state.secret_registry.update_secrets({"TOKEN": "hunter2"})
    # 当命令引用该名称时，就会发生解析。
    convo.state.secret_registry.get_secrets_as_env_vars("echo $TOKEN")

    convo.agent.step(convo, on_event=lambda _: None)

    streamed = "".join(f.content for f in frames if isinstance(f, StreamDelta))
    assert streamed == "the token is <secret-hidden>"
