"""测试智能体在缺少工具时发出 ActionEvent 的动作为 None。"""

import json
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
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    AgentErrorEvent,
    MessageEvent,
)
from openhands.sdk.llm import LLM, Message, TextContent


def test_emits_action_event_with_none_action_then_error_on_missing_tool() -> None:
    """测试当工具丢失时智能体是否发出 ActionEvent(action=None)。"""
    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[])

    def mock_llm_response(messages, **kwargs):
        return ModelResponse(
            id="mock-response-1",
            choices=[
                Choices(
                    index=0,
                    message=LiteLLMMessage(
                        role="assistant",
                        content="I'll use a non-existent tool to help you.",
                        tool_calls=[
                            ChatCompletionMessageToolCall(
                                id="call_x",
                                type="function",
                                function=Function(
                                    name="nonexistent_tool",
                                    arguments=json.dumps({"param": "value"}),
                                ),
                            )
                        ],
                    ),
                    finish_reason="tool_calls",
                )
            ],
            created=0,
            model="test-model",
            object="chat.completion",
        )

    collected = []

    def cb(e):
        collected.append(e)

    conv = Conversation(agent=agent, callbacks=[cb])

    with patch(
        "openhands.sdk.llm.llm.litellm_completion", side_effect=mock_llm_response
    ):
        conv.send_message(Message(role="user", content=[TextContent(text="go")]))
        agent.step(conv, on_event=cb)

    # 使用 action=None 查找 ActionEvent
    action_events_none = [
        e for e in collected if isinstance(e, ActionEvent) and e.action is None
    ]
    error_events = [e for e in collected if isinstance(e, AgentErrorEvent)]

    # 我们期望至少有一个 ActionEvent 且 action=None 和一个 AgentErrorEvent
    assert len(action_events_none) > 0
    assert len(error_events) > 0

    # 确保排序：ActionEvent(action=None) 发生在 AgentErrorEvent 之前
    first_action_none_idx = next(
        i
        for i, e in enumerate(collected)
        if isinstance(e, ActionEvent) and e.action is None
    )
    first_err_idx = next(
        i for i, e in enumerate(collected) if isinstance(e, AgentErrorEvent)
    )
    assert first_action_none_idx < first_err_idx

    # 验证 tool_call_id 连续性
    action_event = action_events_none[0]
    tc_id = action_event.tool_call.id
    err = error_events[0]
    assert err.tool_call_id == tc_id

    # 确保初始系统提示词存在消息事件
    assert any(isinstance(e, MessageEvent) for e in collected)
