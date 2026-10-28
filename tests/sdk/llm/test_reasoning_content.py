"""测试 LLM 和 Message 类中的推理内容支持。"""

from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage

from openhands.sdk.tool import Action


class _TestActionForReasoningContent(Action):
    """用于测试ActionEvent中推理内容的测试动作。

    此类在模块级别定义（而不是在测试函数内部），以确保它在序列化/反序列化期间可由
    Pydantic 导入。 当与 pytest-xdist 并行运行测试时，在测试函数
    中定义它会导致测试污染。
    """

    action: str = "test"


def create_mock_response(content: str = "Test response", response_id: str = "test-id"):
    """用于创建结构正确的模拟对象响应的辅助函数。"""
    return ModelResponse(
        id=response_id,
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(content=content, role="assistant"),
            )
        ],
        created=1234567890,
        model="claude-sonnet-4-20250514",
        object="chat.completion",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def test_message_with_reasoning_content():
    """带有推理内容字段的测试消息。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="The answer is 42.")],
        reasoning_content="Let me think about this step by step...",
    )

    assert message.reasoning_content == "Let me think about this step by step..."


def test_message_without_reasoning_content():
    """测试消息而不推理内容（默认行为）。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(role="assistant", content=[TextContent(text="The answer is 42.")])

    assert message.reasoning_content is None


def test_message_from_llm_chat_message_with_reasoning():
    """用推理内容测试Message.from_llm_chat_message。"""
    from openhands.sdk.llm.message import Message

    # 创建一条包含推理内容的模拟对象 LiteLLM 消息
    litellm_message = LiteLLMMessage(role="assistant", content="The answer is 42.")
    # 添加推理内容作为属性
    litellm_message.reasoning_content = "Let me think about this..."

    message = Message.from_llm_chat_message(litellm_message)

    assert message.role == "assistant"
    assert len(message.content) == 1
    from openhands.sdk.llm.message import TextContent

    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == "The answer is 42."
    assert message.reasoning_content == "Let me think about this..."


def test_message_from_llm_chat_message_without_reasoning():
    """测试Message.from_llm_chat_message无推理内容。"""
    from openhands.sdk.llm.message import Message

    litellm_message = LiteLLMMessage(role="assistant", content="The answer is 42.")

    message = Message.from_llm_chat_message(litellm_message)

    assert message.role == "assistant"
    assert len(message.content) == 1
    from openhands.sdk.llm.message import TextContent

    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == "The answer is 42."
    assert message.reasoning_content is None


def test_message_serialization_with_reasoning():
    """测试消息序列化包含推理内容。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="Answer")],
        reasoning_content="Thinking process...",
    )

    serialized = message.model_dump()

    assert serialized["reasoning_content"] == "Thinking process..."


def test_message_serialization_without_reasoning():
    """测试消息序列化，无推理内容。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(role="assistant", content=[TextContent(text="Answer")])

    serialized = message.model_dump()

    assert serialized["reasoning_content"] is None


def test_action_event_with_reasoning_content():
    """使用推理内容字段测试 ActionEvent。"""
    from openhands.sdk.event.llm_convertible import ActionEvent
    from openhands.sdk.llm.message import (
        MessageToolCall,
        TextContent,
    )

    # 创建一个工具调用
    tool_call = MessageToolCall(
        id="test-id",
        name="test_tool",
        arguments='{"arg": "value"}',
        origin="completion",
    )

    action_event = ActionEvent(
        thought=[TextContent(text="I need to test this")],
        action=_TestActionForReasoningContent(),
        tool_name="test_tool",
        tool_call_id="test-id",
        tool_call=tool_call,
        llm_response_id="response-123",
        reasoning_content="Let me think about this step by step...",
    )

    # 测试推理内容是否被保留
    assert action_event.reasoning_content == "Let me think about this step by step..."

    # 测试LLM消息中是否包含推理内容
    llm_message = action_event.to_llm_message()
    assert llm_message.reasoning_content == "Let me think about this step by step..."
