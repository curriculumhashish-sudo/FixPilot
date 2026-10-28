"""单元测试用于 LLM 响应分类和调度。"""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from litellm.types.utils import ModelResponse

from openhands.sdk.agent import Agent
from openhands.sdk.agent.response_dispatch import LLMResponseType, classify_response
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.conversation.stuck_detector import StuckDetector
from openhands.sdk.event import ActionEvent, Event, MessageEvent, ObservationEvent
from openhands.sdk.llm import (
    LLM,
    LLMResponse,
    Message,
    MessageToolCall,
    ReasoningItemModel,
    RedactedThinkingBlock,
    TextContent,
    ThinkingBlock,
)
from openhands.sdk.llm.utils.metrics import MetricsSnapshot, TokenUsage
from openhands.sdk.tool import Action, Observation


class _LoopAction(Action):
    command: str


class _LoopObservation(Observation):
    command: str
    exit_code: int


def _msg(**kwargs) -> Message:
    """使用默认值构建消息的简写。"""
    return Message(role="assistant", **kwargs)


def _tool_call() -> MessageToolCall:
    return MessageToolCall(id="tc1", name="bash", arguments="{}", origin="completion")


# ---------------------------------------------------------------------------
# classify_response
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(
            dict(
                tool_calls=[_tool_call()],
                content=[TextContent(text="Let me run this")],
                reasoning_content="I should use bash",
            ),
            id="row1-tools+content+reasoning",
        ),
        pytest.param(
            dict(
                tool_calls=[_tool_call()],
                content=[TextContent(text="Running command")],
            ),
            id="row2-tools+content",
        ),
        pytest.param(
            dict(tool_calls=[_tool_call()], reasoning_content="Thinking about it..."),
            id="row3-tools+reasoning",
        ),
        pytest.param(
            dict(tool_calls=[_tool_call()]),
            id="row4-tools-only",
        ),
        pytest.param(
            dict(tool_calls=[_tool_call()], content=[]),
            id="tools-with-empty-content",
        ),
    ],
)
def test_tool_calls_response(kwargs):
    """任何带有 tool_calls 的消息都归类为 TOOL_CALLS。"""
    assert classify_response(_msg(**kwargs)) == LLMResponseType.TOOL_CALLS


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(
            dict(
                content=[TextContent(text="The answer is 42")],
                reasoning_content="Let me calculate...",
            ),
            id="row5-content+reasoning",
        ),
        pytest.param(
            dict(content=[TextContent(text="Hello world")]),
            id="row6-content-only",
        ),
        pytest.param(
            dict(
                content=[TextContent(text="Here is my answer")],
                thinking_blocks=[
                    ThinkingBlock(thinking="Let me think", signature="sig")
                ],
            ),
            id="content-with-thinking-blocks",
        ),
    ],
)
def test_content_response(kwargs):
    """无 tool_calls + 非空白 TextContent 分类为 CONTENT。"""
    assert classify_response(_msg(**kwargs)) == LLMResponseType.CONTENT


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(
            dict(reasoning_content="Let me think about this..."),
            id="row7a-reasoning-content",
        ),
        pytest.param(
            dict(
                content=[],
                thinking_blocks=[
                    ThinkingBlock(thinking="The answer is 2", signature="sig-1")
                ],
            ),
            id="row7b-thinking-blocks",
        ),
        pytest.param(
            dict(
                content=[],
                thinking_blocks=[RedactedThinkingBlock(data="encrypted")],
            ),
            id="row7c-redacted-thinking",
        ),
        pytest.param(
            dict(
                content=[],
                responses_reasoning_item=ReasoningItemModel(
                    id="ri-1", summary=["thinking"]
                ),
            ),
            id="row7d-responses-reasoning-item",
        ),
    ],
)
def test_reasoning_only_response(kwargs):
    """没有tool_calls，没有可见内容，但推理分类为REASONING_ONLY。"""
    assert classify_response(_msg(**kwargs)) == LLMResponseType.REASONING_ONLY


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(dict(content=[]), id="row8-empty-content"),
        pytest.param(
            dict(content=[TextContent(text="   \n  ")]),
            id="whitespace-only-content",
        ),
        pytest.param(
            dict(content=[], thinking_blocks=[]),
            id="empty-content-and-thinking-blocks",
        ),
    ],
)
def test_empty_response(kwargs):
    """没有tool_calls、没有内容、没有推理归类为EMPTY。"""
    assert classify_response(_msg(**kwargs)) == LLMResponseType.EMPTY


# ---------------------------------------------------------------------------
# ResponseDispatchMixin（通过智能体积分）
# ---------------------------------------------------------------------------


def _make_metrics() -> MetricsSnapshot:
    return MetricsSnapshot(
        model_name="test",
        accumulated_cost=0.0,
        max_budget_per_task=0.0,
        accumulated_token_usage=TokenUsage(model="test"),
    )


def _make_llm_response(message: Message) -> LLMResponse:
    return LLMResponse(
        message=message,
        metrics=_make_metrics(),
        raw_response=MagicMock(spec=ModelResponse, id="r1"),
    )


def _run_single_step(
    llm_response: LLMResponse,
    *,
    seed_events: list[Event] | None = None,
    record_emitted_events_in_state: bool = False,
    secrets: dict[str, str] | None = None,
    prepare: Callable[[LocalConversation], None] | None = None,
) -> tuple[list[Event], LocalConversation]:
    """使用预设的 LLM 响应运行一个智能体步骤。"""
    from pydantic import PrivateAttr

    class SingleShotLLM(LLM):
        _response: LLMResponse = PrivateAttr()

        def __init__(self, response: LLMResponse):
            super().__init__(model="test-model")
            self._response = response

        def completion(  # type: ignore[override]
            self, *, messages, tools=None, **kwargs
        ) -> LLMResponse:
            return self._response

    llm = SingleShotLLM(llm_response)
    agent = Agent(llm=llm, tools=[])
    conversation = Conversation(agent=agent)
    conversation._ensure_agent_ready()
    if secrets is not None:
        conversation.update_secrets(secrets)
    if seed_events is not None:
        for event in seed_events:
            conversation.state.append_event(event)
    if prepare is not None:
        prepare(conversation)

    events: list[Event] = []

    def on_event(e: Event) -> None:
        events.append(e)
        if record_emitted_events_in_state:
            conversation.state.append_event(e)

    agent.step(conversation, on_event=on_event)
    return events, conversation


def _user_message(text: str) -> MessageEvent:
    return MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text=text)]),
    )


def _repeating_terminal_loop_events(repeat_count: int) -> list[Event]:
    loop_events: list[Event] = []
    for i in range(repeat_count):
        action = ActionEvent(
            source="agent",
            thought=[TextContent(text="I need to run ls command")],
            action=_LoopAction(command="ls"),
            tool_name="terminal",
            tool_call_id=f"call_{i}",
            tool_call=MessageToolCall(
                id=f"call_{i}",
                name="terminal",
                arguments='{"command": "ls"}',
                origin="completion",
            ),
            llm_response_id=f"response_{i}",
        )
        loop_events.append(action)
        loop_events.append(
            ObservationEvent(
                source="environment",
                observation=_LoopObservation.from_text(
                    text="file1.txt\nfile2.txt",
                    command="ls",
                    exit_code=0,
                ),
                action_id=action.id,
                tool_name="terminal",
                tool_call_id=f"call_{i}",
            )
        )
    return loop_events


def test_content_response_sets_finished():
    """_handle_content_response 将执行状态设置为 FINISHED。"""
    msg = Message(role="assistant", content=[TextContent(text="Done!")])
    events, convo = _run_single_step(_make_llm_response(msg))
    msg_events = [e for e in events if isinstance(e, MessageEvent)]

    assert convo.state.execution_status == ConversationExecutionStatus.FINISHED
    assert len(msg_events) == 1
    assert msg_events[0].source == "agent"


def test_empty_response_sends_nudge():
    """_handle_no_content_response 发出智能体消息 + 纠正性推动。"""
    msg = Message(role="assistant", content=[])
    events, convo = _run_single_step(_make_llm_response(msg))
    msg_events = [e for e in events if isinstance(e, MessageEvent)]

    assert convo.state.execution_status != ConversationExecutionStatus.FINISHED
    assert len(msg_events) == 2
    assert msg_events[0].source == "agent"
    assert msg_events[1].source == "environment"
    assert msg_events[1].llm_message.role == "user"
    nudge_content = msg_events[1].llm_message.content[0]
    assert isinstance(nudge_content, TextContent)
    assert "function call" in nudge_content.text


def test_reasoning_only_sends_nudge():
    """_handle_no_content_response 发送纠正性微调仅用于推理。"""
    msg = Message(role="assistant", reasoning_content="Let me think...")
    events, convo = _run_single_step(_make_llm_response(msg))
    msg_events = [e for e in events if isinstance(e, MessageEvent)]

    assert convo.state.execution_status != ConversationExecutionStatus.FINISHED
    assert len(msg_events) == 2
    assert msg_events[0].source == "agent"
    assert msg_events[1].source == "environment"
    assert msg_events[1].llm_message.role == "user"


def test_corrective_nudge_does_not_reset_stuck_detection_window():
    """框架反馈不得算作卡住检测的新人类转向。"""
    seed_events = [
        _user_message("Please keep trying ls"),
        *_repeating_terminal_loop_events(repeat_count=4),
    ]
    msg = Message(role="assistant", content=[])
    events, convo = _run_single_step(
        _make_llm_response(msg),
        seed_events=seed_events,
        record_emitted_events_in_state=True,
    )
    msg_events = [e for e in events if isinstance(e, MessageEvent)]

    assert len(msg_events) == 2
    assert msg_events[1].source == "environment"
    assert msg_events[1].llm_message.role == "user"
    assert StuckDetector(convo.state).is_stuck() is True


def test_tool_calls_response_executes_actions():
    """_handle_tool_calls 创建并执行动作事件。"""
    tool_call = MessageToolCall(
        id="tc-finish",
        name="finish",
        arguments='{"message": "All done"}',
        origin="completion",
    )
    msg = Message(
        role="assistant",
        tool_calls=[tool_call],
        content=[TextContent(text="Finishing up")],
    )
    events, convo = _run_single_step(_make_llm_response(msg))
    action_events = [e for e in events if isinstance(e, ActionEvent)]

    assert len(action_events) == 1
    assert action_events[0].tool_call_id == "tc-finish"
    assert convo.state.execution_status == ConversationExecutionStatus.FINISHED


def test_batch_action_events_are_emitted_consecutively():
    """固定指标可视化工具所依赖的不变量 (#4189)。

    平行工具调用 from one LLM 响应以连续的流形式发出 ActionEvents 它们共享一个
    llm_response_id在工具调用顺序中，只第一个携带
    回合的想法。 ``DefaultConversationVisualizer. _claim_batch_primary`` 只追踪 *
    previous* 在查找批
    次兄弟时，响应 ID O(1); 如果发射不再是连续的，那么该捷径将默默地错误地标记指标——
    这个测试应该首先捕获它。
    """
    tool_calls = [
        MessageToolCall(
            id="tc-1",
            name="think",
            arguments='{"thought": "first"}',
            origin="completion",
        ),
        MessageToolCall(
            id="tc-2",
            name="think",
            arguments='{"thought": "second"}',
            origin="completion",
        ),
    ]
    msg = Message(
        role="assistant",
        tool_calls=tool_calls,
        content=[TextContent(text="Thinking in parallel")],
    )
    events, _ = _run_single_step(_make_llm_response(msg))

    action_events = [e for e in events if isinstance(e, ActionEvent)]
    assert len(action_events) == 2
    # 一个 LLM 响应 -> 整个批次共享一个 llm_response_id。
    assert len({a.llm_response_id for a in action_events}) == 1
    # 按工具调用顺序作为连续运行发出（没有其他响应交错）。
    #
    assert [a.tool_call_id for a in action_events] == ["tc-1", "tc-2"]
    # 只有批次中的第一个事件才带有回合的想法。
    assert action_events[0].thought and not action_events[1].thought


def _agent_message_text(events: list[Event]) -> str:
    """步骤发出的单个智能体 MessageEvent 的文本。"""
    msg_event = next(
        e for e in events if isinstance(e, MessageEvent) and e.source == "agent"
    )
    part = msg_event.llm_message.content[0]
    assert isinstance(part, TextContent)
    return part.text


def test_content_response_masks_registered_secret():
    """模特自己的话语被隐藏在持久的MessageEvent中。

    只有工具输出被屏蔽了，所以机密模型回传的内容是已持久化逐字记录到存储的副本中，重
    播到 LLM, rendered, exported and POSTed to W
    ebhook.
    """
    msg = Message(
        role="assistant", content=[TextContent(text="the value is supersecret now")]
    )
    events, _ = _run_single_step(
        _make_llm_response(msg), secrets={"TOKEN": "supersecret"}
    )

    text = _agent_message_text(events)
    assert "supersecret" not in text
    assert text == "the value is <secret-hidden> now"


def test_content_response_masks_secret_joined_from_stream_chunks():
    """跨越两个增量的机密在持久消息中被屏蔽。

    ``Agent``路径在构建``Message``之前累积差异，因此，每个分块都无法单独匹配，只有重
    新组装的文本才能匹配，这是持久副本构建的基础。
    """
    chunks = ["the value is super", "secret now"]
    msg = Message(role="assistant", content=[TextContent(text="".join(chunks))])
    events, _ = _run_single_step(
        _make_llm_response(msg), secrets={"TOKEN": "supersecret"}
    )

    assert _agent_message_text(events) == "the value is <secret-hidden> now"


def test_content_response_without_secrets_is_left_alone():
    """如果没有注册任何内容，消息文本将保持不变。"""
    msg = Message(role="assistant", content=[TextContent(text="nothing to hide")])
    events, _ = _run_single_step(_make_llm_response(msg))

    assert _agent_message_text(events) == "nothing to hide"


def test_reasoning_only_response_masks_registered_secret():
    """微移路径穿过相同的阻塞点。

    仅推理消息不携带 ``content``，因此单独屏蔽它在这里将是无效的 -
    ``reasoning_content`` 是泄漏的文本。
    """
    msg = Message(role="assistant", reasoning_content="the value is supersecret now")
    events, _ = _run_single_step(
        _make_llm_response(msg), secrets={"TOKEN": "supersecret"}
    )

    msg_event = next(
        e for e in events if isinstance(e, MessageEvent) and e.source == "agent"
    )
    assert msg_event.llm_message.reasoning_content == "the value is <secret-hidden> now"


def test_content_response_masks_value_dropped_from_secret_sources():
    """遮罩遵循跟踪的值，而不是注册表的源列表。

    ``EventService.activate_credential_binding`` 弹出一个名字
    ``secret_sources`` 而解析的值会保持跟踪以进行屏蔽，因此关闭 ``secret_sources`` 会
    在此处泄漏实时凭据。
    """

    def drop_source(convo: LocalConversation) -> None:
        registry = convo.state.secret_registry
        registry.get_secret_value("TOKEN")  # 解析 -> 跟踪掩码
        with convo.state:
            convo.state.secret_registry = registry.model_copy(
                update={"secret_sources": {}}
            )

    msg = Message(
        role="assistant", content=[TextContent(text="the value is supersecret now")]
    )
    events, convo = _run_single_step(
        _make_llm_response(msg),
        secrets={"TOKEN": "supersecret"},
        prepare=drop_source,
    )

    assert not convo.state.secret_registry.secret_sources
    assert _agent_message_text(events) == "the value is <secret-hidden> now"
