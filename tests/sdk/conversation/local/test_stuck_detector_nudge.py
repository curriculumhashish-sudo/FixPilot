"""集成测试用于重复操作错误纠正微调 (#4331)。"""

from collections.abc import Sequence
from typing import ClassVar

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import AgentErrorEvent, MessageEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool import (
    Action,
    Observation,
    Tool,
    ToolDefinition,
    ToolExecutor,
    register_tool,
)


class _AlwaysErrorAction(Action):
    command: str


class _AlwaysErrorObservation(Observation):
    result: str

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        return [TextContent(text=self.result)]


class _AlwaysErrorExecutor(ToolExecutor[_AlwaysErrorAction, _AlwaysErrorObservation]):
    def __call__(self, action: _AlwaysErrorAction, conversation=None):
        raise ValueError("`file_text` is required for command: create.")


class _AlwaysErrorTool(ToolDefinition[_AlwaysErrorAction, _AlwaysErrorObservation]):
    name: ClassVar[str] = "always_error_tool"

    @classmethod
    def create(cls, conv_state=None, *, executor: ToolExecutor, **params):
        return [
            cls(
                description="A tool that always errors",
                action_type=_AlwaysErrorAction,
                observation_type=_AlwaysErrorObservation,
                executor=executor,
            )
        ]


def _bad_tool_call(call_id: str) -> MessageToolCall:
    return MessageToolCall(
        id=call_id,
        name="always_error_tool",
        arguments='{"command": "create"}',
        origin="completion",
    )


def _bad_tool_call_message(call_id: str) -> Message:
    return Message(
        role="assistant",
        content=[TextContent(text="")],
        tool_calls=[_bad_tool_call(call_id)],
    )


def _make_conversation(
    scripted_messages: list[Message | Exception],
) -> LocalConversation:
    register_tool(
        "always_error_tool", _AlwaysErrorTool.create(executor=_AlwaysErrorExecutor())[0]
    )
    llm = TestLLM.from_messages(scripted_messages)
    agent = Agent(llm=llm, tools=[Tool(name="always_error_tool")])
    conversation = Conversation(agent=agent)
    assert isinstance(conversation, LocalConversation)
    return conversation


def test_run_nudges_before_going_stuck_on_repeating_action_error():
    """4 个相同的失败调用：在第 3 个之后微移，在第 4 个之后硬 STUCK。"""
    scripted_messages: list[Message | Exception] = [
        _bad_tool_call_message(f"call_{i}") for i in range(4)
    ]
    conversation = _make_conversation(scripted_messages)
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Create /tmp/foo.py")])
    )
    conversation.run()

    assert conversation.state.execution_status == ConversationExecutionStatus.STUCK

    error_events = [
        e for e in conversation.state.events if isinstance(e, AgentErrorEvent)
    ]
    assert len(error_events) == 4

    nudges = [
        e
        for e in conversation.state.events
        if isinstance(e, MessageEvent) and e.source == "environment"
    ]
    assert len(nudges) == 1
    nudge_text = nudges[0].llm_message.content[0]
    assert isinstance(nudge_text, TextContent)
    assert "always_error_tool" in nudge_text.text
    assert "file_text" in nudge_text.text

    events = list(conversation.state.events)
    nudge_index = events.index(nudges[0])
    preceding_errors = [
        e for e in events[:nudge_index] if isinstance(e, AgentErrorEvent)
    ]
    following_errors = [
        e for e in events[nudge_index:] if isinstance(e, AgentErrorEvent)
    ]
    assert len(preceding_errors) == 3
    assert len(following_errors) == 1


def test_run_recovers_after_nudge_when_model_self_corrects():
    """3 个相同的失败调用，然后是不同的响应：根本没有 STUCK。"""
    scripted_messages: list[Message | Exception] = [
        *[_bad_tool_call_message(f"call_{i}") for i in range(3)],
        Message(
            role="assistant",
            content=[TextContent(text="I see the issue, stopping here.")],
        ),
    ]
    conversation = _make_conversation(scripted_messages)
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Create /tmp/foo.py")])
    )
    conversation.run()

    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED

    error_events = [
        e for e in conversation.state.events if isinstance(e, AgentErrorEvent)
    ]
    assert len(error_events) == 3

    nudges = [
        e
        for e in conversation.state.events
        if isinstance(e, MessageEvent) and e.source == "environment"
    ]
    assert len(nudges) == 1


def test_run_does_not_renudge_action_error_while_streak_is_frozen():
    """轻推后的空响应不得重新触发相同的轻推。

    3 个相同的失败调用达到微移阈值并发出一次微移。 然后，模型因空响应而停止，这不会添
    加新的操作/观察，因此操作错误条纹保持冻结在阈值。 不相关的 EMPTY 纠正微
    移会为此触发，但动作错误微移不得在冻结的条纹上重新触发。
    """
    scripted_messages: list[Message | Exception] = [
        *[_bad_tool_call_message(f"call_{i}") for i in range(3)],
        Message(role="assistant", content=[]),
        Message(
            role="assistant",
            content=[TextContent(text="I see the issue, stopping here.")],
        ),
    ]
    conversation = _make_conversation(scripted_messages)
    conversation.send_message(
        Message(role="user", content=[TextContent(text="Create /tmp/foo.py")])
    )
    conversation.run()

    assert conversation.state.execution_status == ConversationExecutionStatus.FINISHED

    error_events = [
        e for e in conversation.state.events if isinstance(e, AgentErrorEvent)
    ]
    assert len(error_events) == 3

    nudges = [
        e
        for e in conversation.state.events
        if isinstance(e, MessageEvent) and e.source == "environment"
    ]
    # 一次行动错误推动加上不相关的 EMPTY 纠正推动——而不是对已经推动的、冻结的连胜进行第
    # 二次行动错误推动。
    #
    assert len(nudges) == 2
    action_error_nudge = nudges[0].llm_message.content[0]
    empty_corrective_nudge = nudges[1].llm_message.content[0]
    assert isinstance(action_error_nudge, TextContent)
    assert isinstance(empty_corrective_nudge, TextContent)
    assert "always_error_tool" in action_error_nudge.text
    assert "did not include a function call" in empty_corrective_nudge.text
