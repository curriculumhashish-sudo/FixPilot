"""测试工具调用参数解析和空响应恢复。

涵盖了 Qwen3.5-Flash 卡住对话问题的两个修复：

1. JSON 参数解析：原始 json.loads 首先，sanitize_json_control_chars 作为回退方案（修
复文字 \\n 空白被错误转义）。

2. 纠正性反馈：当 LLM 无工具调用且无内容时，注入用户消息，使模型能够自我纠正，而不是
无声地陷入循环检测器。
"""

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Self
from unittest.mock import patch

from litellm import ChatCompletionMessageToolCall
from litellm.types.utils import (
    Choices,
    Function,
    Message as LiteLLMMessage,
    ModelResponse,
)
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.event import ActionEvent, AgentErrorEvent, MessageEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool import Action, Observation, Tool, ToolExecutor, register_tool
from openhands.sdk.tool.tool import ToolDefinition


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


# ── 最小工具──────────────────────────────────────────────────────────


class _ViewAction(Action):
    command: str
    path: str
    view_range: list[int] | None = None


class _ViewObs(Observation):
    output: str

    @property
    def to_llm_content(self) -> Sequence[TextContent]:
        return [TextContent(text=self.output)]


class _ViewExec(ToolExecutor[_ViewAction, _ViewObs]):
    def __call__(self, action: _ViewAction, conversation=None) -> _ViewObs:
        return _ViewObs(output=f"viewed {action.path}")


class _ViewTool(ToolDefinition[_ViewAction, _ViewObs]):
    name = "view_tool"

    @classmethod
    def create(cls, conv_state: "ConversationState | None" = None) -> Sequence[Self]:
        return [
            cls(
                description="View a file",
                action_type=_ViewAction,
                observation_type=_ViewObs,
                executor=_ViewExec(),
            )
        ]


register_tool("ViewTool", _ViewTool)


# ── 帮手──────────────────────────────────────────────────────────────


def _make_agent(*, with_tool: bool = True) -> Agent:
    llm = LLM(
        model="test-model",
        usage_id="test-llm",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    tools = [Tool(name="ViewTool")] if with_tool else []
    return Agent(llm=llm, tools=tools)


def _model_response(
    content: str | None,
    tool_calls: list[ChatCompletionMessageToolCall] | None = None,
    *,
    response_id: str = "resp-1",
    reasoning_content: str | None = None,
) -> ModelResponse:
    msg = LiteLLMMessage(
        role="assistant",
        content=content,
        tool_calls=tool_calls,
    )
    if reasoning_content is not None:
        msg.reasoning_content = reasoning_content  # type: ignore[attr-defined]
    return ModelResponse(
        id=response_id,
        choices=[Choices(index=0, message=msg, finish_reason="stop")],
        created=0,
        model="test-model",
        object="chat.completion",
    )


# ── 修正1：JSON参数解析──────────────────────────────────────────


def test_newline_whitespace_in_arguments_parses_ok():
    """原始换行符作为 JSON 空格的参数应该直接解析。

    Qwen3.5-Flash 发出如下参数：
        "view_range": \\n[1, 100]\\n\\n
    API JSON 解码后，\\n 变为 0x0A — 有效的 JSON 空白。
    """
    args_with_newlines = (
        '{"command": "view", "path": "/workspace/test.py", '
        '"view_range": \n[1, 100]\n\n}'
    )
    assert json.loads(args_with_newlines) is not None  # 理智

    agent = _make_agent()
    conv = Conversation(agent=agent)

    resp = _model_response(
        content="Viewing file",
        tool_calls=[
            ChatCompletionMessageToolCall(
                id="call_1",
                type="function",
                function=Function(
                    name="view_tool",
                    arguments=args_with_newlines,
                ),
            )
        ],
    )

    events: list[object] = []
    with patch("openhands.sdk.llm.llm.litellm_completion", return_value=resp):
        conv.send_message(
            Message(
                role="user",
                content=[TextContent(text="View file.")],
            )
        )
        agent.step(conv, on_event=events.append)

    action_events = [e for e in events if isinstance(e, ActionEvent)]
    error_events = [e for e in events if isinstance(e, AgentErrorEvent)]
    assert len(action_events) >= 1, (
        f"Expected ActionEvent, got errors: {[e.error for e in error_events]}"
    )
    assert action_events[0].action is not None
    assert isinstance(action_events[0].action, _ViewAction)


def test_control_chars_in_string_values_still_sanitized():
    """JSON 字符串值内的原始 0x0A 会触发回退方案清理。"""
    args_raw = '{"command": "view", "path": "/workspace/test\n.py"}'
    # 这是无效的 JSON（字符串内的原始换行符）
    try:
        json.loads(args_raw)
        # 如果没有出现，则测试前提是错误的
        assert False, "Expected json.loads to fail"
    except json.JSONDecodeError:
        pass

    agent = _make_agent()
    conv = Conversation(agent=agent)

    resp = _model_response(
        content="Viewing file",
        tool_calls=[
            ChatCompletionMessageToolCall(
                id="call_2",
                type="function",
                function=Function(
                    name="view_tool",
                    arguments=args_raw,
                ),
            )
        ],
    )

    events: list[object] = []
    with patch("openhands.sdk.llm.llm.litellm_completion", return_value=resp):
        conv.send_message(
            Message(
                role="user",
                content=[TextContent(text="View file.")],
            )
        )
        agent.step(conv, on_event=events.append)

    # 清理回退方案后，操作仍会创建
    action_events = [e for e in events if isinstance(e, ActionEvent)]
    assert len(action_events) >= 1
    assert action_events[0].action is not None


# ── 修复2：修正空响应反馈────────────────────────


def test_reasoning_only_response_injects_nudge():
    """当 LLM 返回推理但没有工具调用 / 内容时，注入微移。"""
    agent = _make_agent(with_tool=False)
    conv = Conversation(agent=agent)

    resp = _model_response(
        content="",
        reasoning_content="Let me think about this...",
    )

    events: list[object] = []
    with patch("openhands.sdk.llm.llm.litellm_completion", return_value=resp):
        conv.send_message(
            Message(
                role="user",
                content=[TextContent(text="Fix the bug.")],
            )
        )
        agent.step(conv, on_event=events.append)

    agent_msgs = [
        e for e in events if isinstance(e, MessageEvent) and e.source == "agent"
    ]
    corrective_nudges = [
        e for e in events if isinstance(e, MessageEvent) and e.source == "environment"
    ]
    assert len(agent_msgs) == 1
    assert len(corrective_nudges) == 1
    assert corrective_nudges[0].llm_message.role == "user"
    nudge_text = corrective_nudges[0].llm_message.content[0]
    assert isinstance(nudge_text, TextContent)
    assert "function call" in nudge_text.text


def test_content_response_does_not_inject_nudge():
    """当 LLM 产生有意义的内容时，不应注入任何微调。"""
    agent = _make_agent(with_tool=False)
    conv = Conversation(agent=agent)

    resp = _model_response(content="Here is my analysis of the bug...")

    events: list[object] = []
    with patch("openhands.sdk.llm.llm.litellm_completion", return_value=resp):
        conv.send_message(
            Message(
                role="user",
                content=[TextContent(text="Fix the bug.")],
            )
        )
        agent.step(conv, on_event=events.append)

    corrective_nudges = [
        e for e in events if isinstance(e, MessageEvent) and e.source == "environment"
    ]
    assert len(corrective_nudges) == 0


def test_completely_empty_response_injects_nudge():
    """完全空洞的回答（没有推理，没有内容）会受到推动。"""
    agent = _make_agent(with_tool=False)
    conv = Conversation(agent=agent)

    resp = _model_response(content="")

    events: list[object] = []
    with patch("openhands.sdk.llm.llm.litellm_completion", return_value=resp):
        conv.send_message(
            Message(
                role="user",
                content=[TextContent(text="Fix the bug.")],
            )
        )
        agent.step(conv, on_event=events.append)

    corrective_nudges = [
        e for e in events if isinstance(e, MessageEvent) and e.source == "environment"
    ]
    assert len(corrective_nudges) == 1
    assert corrective_nudges[0].llm_message.role == "user"
