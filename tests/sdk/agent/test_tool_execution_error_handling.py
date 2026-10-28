"""当工具执行引发 ValueError 时测试智能体行为。"""

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
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import ActionEvent, AgentErrorEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool import Action, Observation, Tool, ToolExecutor, register_tool
from openhands.sdk.tool.tool import ToolDefinition


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


class RaisingAction(Action):
    """将导致执行者加注 ValueError 的操作。"""

    value: str = ""


class RaisingObservation(Observation):
    """观测结果为提升工具。"""

    result: str = ""


class RaisingExecutor(ToolExecutor[RaisingAction, RaisingObservation]):
    """引发 ValueError 的执行者。"""

    def __call__(self, action: RaisingAction, conversation=None) -> RaisingObservation:
        raise ValueError("Cannot use reset=True with is_input=True")


class RaisingTool(ToolDefinition[RaisingAction, RaisingObservation]):
    """在执行期间引发 ValueError 的工具。"""

    name = "raising_tool"

    @classmethod
    def create(cls, conv_state: "ConversationState | None" = None) -> Sequence[Self]:
        return [
            cls(
                description="A tool that raises ValueError",
                action_type=RaisingAction,
                observation_type=RaisingObservation,
                executor=RaisingExecutor(),
            )
        ]


# 注册该工具，以便可以通过名称解析
register_tool("RaisingTool", RaisingTool)


def test_tool_execution_valueerror_returns_error_event():
    """测试工具执行中的 ValueError 是否返回 AgentErrorEvent。"""

    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[Tool(name="RaisingTool")])

    def mock_llm_response(messages, **kwargs):
        return ModelResponse(
            id="mock-response-1",
            choices=[
                Choices(
                    index=0,
                    message=LiteLLMMessage(
                        role="assistant",
                        content="I'll use the raising tool.",
                        tool_calls=[
                            ChatCompletionMessageToolCall(
                                id="call_1",
                                type="function",
                                function=Function(
                                    name="raising_tool",
                                    arguments='{"value": "test"}',
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

    collected_events = []

    def event_callback(event):
        collected_events.append(event)

    conversation = Conversation(agent=agent, callbacks=[event_callback])

    with patch(
        "openhands.sdk.llm.llm.litellm_completion", side_effect=mock_llm_response
    ):
        conversation.send_message(
            Message(
                role="user",
                content=[TextContent(text="Please use the raising tool.")],
            )
        )

        # 运行一步即可触发工具调用
        agent.step(conversation, on_event=event_callback)

    # 验证是否生成了 AgentErrorEvent
    error_events = [e for e in collected_events if isinstance(e, AgentErrorEvent)]
    assert len(error_events) == 1, (
        f"Expected 1 AgentErrorEvent, got {len(error_events)}"
    )

    error_event = error_events[0]
    assert "raising_tool" in error_event.error
    assert "Cannot use reset=True with is_input=True" in error_event.error
    assert error_event.tool_name == "raising_tool"
    assert error_event.tool_call_id == "call_1"

    # 验证对话是否已完成不
    with conversation.state:
        assert (
            conversation.state.execution_status != ConversationExecutionStatus.FINISHED
        ), "Agent should not be finished after tool execution error"


def test_conversation_continues_after_tool_execution_error():
    """测试工具执行错误后对话是否可以继续。"""

    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[Tool(name="RaisingTool")])

    call_count = 0

    def mock_llm_response(messages, **kwargs):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # 第一次调用：尝试提升工具
            return ModelResponse(
                id="mock-response-1",
                choices=[
                    Choices(
                        index=0,
                        message=LiteLLMMessage(
                            role="assistant",
                            content="I'll try the raising tool first.",
                            tool_calls=[
                                ChatCompletionMessageToolCall(
                                    id="call_1",
                                    type="function",
                                    function=Function(
                                        name="raising_tool",
                                        arguments='{"value": "test"}',
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
        else:
            # 第二次调用：使用完成工具响应
            return ModelResponse(
                id="mock-response-2",
                choices=[
                    Choices(
                        index=0,
                        message=LiteLLMMessage(
                            role="assistant",
                            content=None,
                            tool_calls=[
                                ChatCompletionMessageToolCall(
                                    id="finish-call-1",
                                    type="function",
                                    function=Function(
                                        name="finish",
                                        arguments=(
                                            '{"message": "I see there '
                                            'was an error. Task completed."}'
                                        ),
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

    collected_events = []

    def event_callback(event):
        collected_events.append(event)

    conversation = Conversation(agent=agent, callbacks=[event_callback])

    with patch(
        "openhands.sdk.llm.llm.litellm_completion", side_effect=mock_llm_response
    ):
        conversation.send_message(
            Message(
                role="user",
                content=[TextContent(text="Please help me.")],
            )
        )

        # 运行第一步 - 应该生成错误
        agent.step(conversation, on_event=event_callback)

        # 验证我们收到错误事件
        error_events = [e for e in collected_events if isinstance(e, AgentErrorEvent)]
        assert len(error_events) == 1

        # 验证对话尚未结束
        with conversation.state:
            assert (
                conversation.state.execution_status
                != ConversationExecutionStatus.FINISHED
            )

        # 运行第二步 - 应该调用完成工具
        agent.step(conversation, on_event=event_callback)

        # 验证我们获得了完成工具的操作事件
        action_events = [
            e
            for e in collected_events
            if isinstance(e, ActionEvent)
            and e.source == "agent"
            and e.tool_name == "finish"
        ]
        assert len(action_events) == 1

        # 现在谈话应该结束了
        with conversation.state:
            assert (
                conversation.state.execution_status
                == ConversationExecutionStatus.FINISHED
            )

    # 验证我们进行了两次 LLM 调用
    assert call_count == 2
