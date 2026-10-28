"""测试调用不存在的工具时的智能体行为。"""

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


def test_nonexistent_tool_returns_error_and_continues_conversation():
    """测试调用不存在的工具是否返回 AgentErrorEvent 并继续对话。"""  # noqa: E501

    # 创建一个简单的智能体，没有自定义工具（只有内置工具）
    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[])

    # 模拟对象 LLM 条回复
    def mock_llm_response(messages, **kwargs):
        # 第一个响应：智能体尝试调用不存在的工具
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
                                id="call_1",
                                type="function",
                                function=Function(
                                    name="nonexistent_tool",
                                    arguments='{"param": "value"}',
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

    # 从对话中收集事件
    collected_events = []

    def event_callback(event):
        collected_events.append(event)

    # 创建对话并使用模拟的 LLM 运行
    conversation = Conversation(agent=agent, callbacks=[event_callback])

    with patch(
        "openhands.sdk.llm.llm.litellm_completion", side_effect=mock_llm_response
    ):
        # 发送消息以开始对话
        conversation.send_message(
            Message(
                role="user",
                content=[TextContent(text="Please help me with something.")],
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
    assert "nonexistent_tool" in error_event.error
    assert "not found" in error_event.error
    assert error_event.tool_name == "nonexistent_tool"
    assert error_event.tool_call_id == "call_1"

    # 验证对话是否已不完成（这是关键修复）
    with conversation.state:
        assert (
            conversation.state.execution_status != ConversationExecutionStatus.FINISHED
        ), "Agent should not be finished after encountering non-existent tool"

    # 验证 LLM 的错误事件格式是否正确
    llm_message = error_event.to_llm_message()
    assert llm_message.role == "tool"
    assert llm_message.tool_call_id == "call_1"
    content_text = llm_message.content[0]
    assert isinstance(content_text, TextContent)
    assert "nonexistent_tool" in content_text.text
    assert "not found" in content_text.text


def test_nonexistent_tool_error_includes_available_tools():
    """测试错误消息是否包含可用的工具。"""

    # 使用一些工具创建智能体
    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[])  # 仅内置工具

    # 模拟对象 LLM 调用不存在的工具的响应
    def mock_llm_response(messages, **kwargs):
        return ModelResponse(
            id="mock-response-1",
            choices=[
                Choices(
                    index=0,
                    message=LiteLLMMessage(
                        role="assistant",
                        content="I'll use a non-existent tool.",
                        tool_calls=[
                            ChatCompletionMessageToolCall(
                                id="call_1",
                                type="function",
                                function=Function(
                                    name="missing_tool",
                                    arguments="{}",
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
                content=[TextContent(text="Test message")],
            )
        )
        agent.step(conversation, on_event=event_callback)

    # 查找错误事件
    error_events = [e for e in collected_events if isinstance(e, AgentErrorEvent)]
    assert len(error_events) == 1

    error_event = error_events[0]

    # 验证错误消息是否包含可用的工具
    assert "missing_tool" in error_event.error
    assert "not found" in error_event.error
    assert "Available:" in error_event.error

    # 应包括“完成”和“思考”等内置工具
    assert "finish" in error_event.error
    assert "think" in error_event.error


def test_conversation_continues_after_tool_error():
    """测试工具错误后对话是否可以继续。"""

    llm = LLM(
        usage_id="test-llm",
        model="test-model",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    agent = Agent(llm=llm, tools=[])

    call_count = 0

    def mock_llm_response(messages, **kwargs):
        nonlocal call_count
        call_count += 1

        if call_count == 1:
            # 第一次调用：尝试不存在的工具
            return ModelResponse(
                id="mock-response-1",
                choices=[
                    Choices(
                        index=0,
                        message=LiteLLMMessage(
                            role="assistant",
                            content="I'll try a non-existent tool first.",
                            tool_calls=[
                                ChatCompletionMessageToolCall(
                                    id="call_1",
                                    type="function",
                                    function=Function(
                                        name="bad_tool",
                                        arguments="{}",
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
