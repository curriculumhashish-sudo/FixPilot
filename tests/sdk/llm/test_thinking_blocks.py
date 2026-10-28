"""测试 LLM 和 Message 类中的 Anthropic 思维块支持。"""

from litellm.types.llms.openai import ChatCompletionThinkingBlock
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from pydantic import SecretStr

from openhands.sdk import LLM, Message, MessageEvent, TextContent, ThinkingBlock


def create_mock_response_with_thinking(
    content: str = "Test response",
    thinking_content: str = "Let me think about this...",
    response_id: str = "test-id",
):
    """使用思维块创建模拟对象响应的辅助函数。"""
    # 创建一个思维块
    thinking_block = ChatCompletionThinkingBlock(
        type="thinking",
        thinking=thinking_content,
    )

    # 用思维块创建消息
    message = LiteLLMMessage(
        content=content,
        role="assistant",
        thinking_blocks=[thinking_block],
    )

    return ModelResponse(
        id=response_id,
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=message,
            )
        ],
        created=1234567890,
        model="claude-sonnet-4-5",
        object="chat.completion",
        usage=Usage(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    )


def test_thinking_block_model():
    """测试 ThinkingBlock 模型创建和验证。"""
    # 测试基本思维块
    block = ThinkingBlock(
        thinking="Complex reasoning process...",
        signature="signature_hash_123",
    )

    assert block.type == "thinking"
    assert block.thinking == "Complex reasoning process..."
    assert block.signature == "signature_hash_123"


def test_thinking_block_without_signature():
    """具有可选签名的测试 ThinkingBlock 模型（Gemini 2.5 兼容性）。

    Gemini 2.5 模型可能会返回没有签名的思维块，这与始终包含签名的 Gemini 3 不同。 此
    测试验证 ThinkingBlock 模型是否正确处理 Non
    e 签名。

    See: https://github.com/OpenHands/software-agent-sdk/issues/1392
    """
    # 测试没有签名的思维块（Gemini 2.5行为）
    block = ThinkingBlock(
        thinking="Let me think about this step by step...",
        signature=None,
    )

    assert block.type == "thinking"
    assert block.thinking == "Let me think about this step by step..."
    assert block.signature is None

    # 测试序列化是否正常工作
    serialized = block.model_dump()
    assert serialized["type"] == "thinking"
    assert serialized["thinking"] == "Let me think about this step by step..."
    assert serialized["signature"] is None


def test_thinking_block_from_litellm_without_signature():
    """测试从没有签名的 LiteLLM 响应创建 ThinkingBlock。

    当签名字段不存在时（Gemini 2.5 行为），这将测试与 LiteLLM 的
    ChatCompletionThinkingBlock 的集成。
    """
    # 创建LiteLLM无签名思维块（Gemini 2.5风格）
    litellm_thinking_block = ChatCompletionThinkingBlock(
        type="thinking",
        thinking="Analyzing the problem...",
        # 无签名字段 - 这对 Gemini 2.5 有效
    )

    # 从 LiteLLM 块创建 SDK ThinkingBlock
    block = ThinkingBlock(
        type=litellm_thinking_block.get("type", "thinking"),
        thinking=litellm_thinking_block.get("thinking", ""),
        signature=litellm_thinking_block.get("signature"),
    )

    assert block.type == "thinking"
    assert block.thinking == "Analyzing the problem..."
    assert block.signature is None


def test_message_from_llm_chat_message_with_thinking_no_signature():
    """使用没有签名的思维块测试Message.from_llm_chat_message。

    这测试了使用没有签名的思维块解析 LiteLLM 响应的完整流程（Gemini 2.5 行为）。
    """
    # 使用没有签名的思维块创建模拟对象 LiteLLM 消息
    thinking_block = ChatCompletionThinkingBlock(
        type="thinking",
        thinking="Let me analyze this problem...",
        # 无签名 - Gemini 2.5 样式
    )

    litellm_message = LiteLLMMessage(
        role="assistant",
        content="The answer is 42.",
        thinking_blocks=[thinking_block],
    )

    message = Message.from_llm_chat_message(litellm_message)

    assert message.role == "assistant"
    assert len(message.content) == 1
    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == "The answer is 42."

    # 检查思维块 - 签名应为 None
    assert len(message.thinking_blocks) == 1
    assert isinstance(message.thinking_blocks[0], ThinkingBlock)
    assert message.thinking_blocks[0].thinking == "Let me analyze this problem..."
    assert message.thinking_blocks[0].signature is None


def test_message_with_thinking_blocks():
    """使用思维块字段测试消息。"""
    from openhands.sdk.llm.message import Message, TextContent, ThinkingBlock

    thinking_block = ThinkingBlock(
        thinking="Let me think about this step by step...",
        signature="sig123",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="The answer is 42.")],
        thinking_blocks=[thinking_block],
    )

    assert len(message.thinking_blocks) == 1
    assert isinstance(message.thinking_blocks[0], ThinkingBlock)
    assert (
        message.thinking_blocks[0].thinking == "Let me think about this step by step..."
    )
    assert message.thinking_blocks[0].signature == "sig123"


def test_message_without_thinking_blocks():
    """在没有思考块的情况下测试消息（默认行为）。"""
    message = Message(role="assistant", content=[TextContent(text="The answer is 42.")])

    assert message.thinking_blocks == []


def test_message_from_llm_chat_message_with_thinking():
    """用思维块测试Message.from_llm_chat_message。"""
    # 使用思维块创建模拟对象 LiteLLM 消息
    thinking_block = ChatCompletionThinkingBlock(
        type="thinking",
        thinking="Let me analyze this problem...",
        signature="hash_456",
    )

    litellm_message = LiteLLMMessage(
        role="assistant",
        content="The answer is 42.",
        thinking_blocks=[thinking_block],
    )

    message = Message.from_llm_chat_message(litellm_message)

    assert message.role == "assistant"
    assert len(message.content) == 1
    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == "The answer is 42."

    # 检查思维块
    assert len(message.thinking_blocks) == 1
    assert isinstance(message.thinking_blocks[0], ThinkingBlock)
    assert message.thinking_blocks[0].thinking == "Let me analyze this problem..."
    assert message.thinking_blocks[0].signature == "hash_456"


def test_message_from_llm_chat_message_without_thinking():
    """测试Message.from_llm_chat_message，没有思维障碍。"""
    litellm_message = LiteLLMMessage(role="assistant", content="The answer is 42.")

    message = Message.from_llm_chat_message(litellm_message)

    assert message.role == "assistant"
    assert len(message.content) == 1
    assert isinstance(message.content[0], TextContent)
    assert message.content[0].text == "The answer is 42."

    assert message.thinking_blocks == []


def test_message_serialization_with_thinking_blocks():
    """测试消息序列化包含思维块。"""
    thinking_block = ThinkingBlock(
        thinking="Reasoning process...",
        signature="sig789",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="Answer")],
        thinking_blocks=[thinking_block],
    )

    serialized = message.model_dump()

    assert len(serialized["thinking_blocks"]) == 1
    assert serialized["thinking_blocks"][0]["thinking"] == "Reasoning process..."
    assert serialized["thinking_blocks"][0]["signature"] == "sig789"
    assert serialized["thinking_blocks"][0]["type"] == "thinking"


def test_message_serialization_without_thinking_blocks():
    """无思维障碍测试消息序列化。"""
    message = Message(role="assistant", content=[TextContent(text="Answer")])

    serialized = message.model_dump()

    assert serialized["thinking_blocks"] == []


def test_message_list_serializer_with_thinking_blocks():
    """测试 Message._list_serializer 包括将思维块作为单独的字段。"""
    thinking_block = ThinkingBlock(
        thinking="Let me think...",
        signature="sig_abc",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="The answer is 42.")],
        thinking_blocks=[thinking_block],
    )

    serialized = message._list_serializer(vision_enabled=False)

    # 思维块应该在单独的领域，而不是在内容中
    assert "thinking_blocks" in serialized
    assert len(serialized["thinking_blocks"]) == 1
    assert serialized["thinking_blocks"][0]["type"] == "thinking"
    assert serialized["thinking_blocks"][0]["thinking"] == "Let me think..."
    assert serialized["thinking_blocks"][0]["signature"] == "sig_abc"

    # 内容应该只有文字内容
    content_list = serialized["content"]
    assert len(content_list) == 1
    assert content_list[0]["type"] == "text"
    assert content_list[0]["text"] == "The answer is 42."


def test_message_event_thinking_blocks_property():
    """测试 MessageEvent thinking_blocks 属性。"""
    thinking_block = ThinkingBlock(
        thinking="Complex reasoning...",
        signature="sig_def",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="Result")],
        thinking_blocks=[thinking_block],
    )

    event = MessageEvent(llm_message=message, source="agent")

    # 测试 thinking_blocks 属性
    assert len(event.thinking_blocks) == 1
    thinking_block = event.thinking_blocks[0]
    assert isinstance(thinking_block, ThinkingBlock)
    assert thinking_block.thinking == "Complex reasoning..."
    assert thinking_block.signature == "sig_def"


def test_message_event_str_with_thinking_blocks():
    """测试 MessageEvent.__str__ 包括思维块计数。"""
    thinking_blocks = [
        ThinkingBlock(thinking="First thought", signature="sig1"),
        ThinkingBlock(thinking="Second thought", signature="sig2"),
    ]

    message = Message(
        role="assistant",
        content=[TextContent(text="Answer")],
        thinking_blocks=thinking_blocks,
    )

    event = MessageEvent(llm_message=message, source="agent")

    str_repr = str(event)

    # 应包括思维块计数
    assert "[Thinking blocks: 2]" in str_repr


def test_multiple_thinking_blocks():
    """测试处理多个思维块。"""
    thinking_blocks = [
        ThinkingBlock(thinking="First reasoning step", signature="sig1"),
        ThinkingBlock(thinking="Second reasoning step", signature="sig2"),
    ]

    message = Message(
        role="assistant",
        content=[TextContent(text="Conclusion")],
        thinking_blocks=thinking_blocks,
    )

    assert len(message.thinking_blocks) == 2
    assert isinstance(message.thinking_blocks[0], ThinkingBlock)
    assert message.thinking_blocks[0].thinking == "First reasoning step"
    assert isinstance(message.thinking_blocks[1], ThinkingBlock)
    assert message.thinking_blocks[1].thinking == "Second reasoning step"
    assert message.thinking_blocks[1].signature is not None

    # 测试序列化 - 思维块应该位于单独的字段中
    serialized = message._list_serializer(vision_enabled=False)

    # 验证 thinking_blocks 字段
    assert "thinking_blocks" in serialized
    assert len(serialized["thinking_blocks"]) == 2
    assert all(item["type"] == "thinking" for item in serialized["thinking_blocks"])

    # 验证内容只有文本
    content_list = serialized["content"]
    assert len(content_list) == 1
    assert content_list[0]["type"] == "text"


def test_llm_preserves_existing_thinking_blocks():
    """测试 LLM 保留现有思维块并且不添加重复项。"""
    # 使用 Anthropic 模型和推理工作创建 LLM
    llm = LLM(
        usage_id="test",
        model="anthropic/claude-sonnet-4-5",
        reasoning_effort="high",
        api_key=SecretStr("test-key"),
    )

    # 使用现有的思维块创建消息
    existing_thinking = ThinkingBlock(
        thinking="I already have a thinking block", signature="existing_sig"
    )

    messages = [
        Message(
            role="assistant",
            content=[TextContent(text="Response with existing thinking")],
            thinking_blocks=[existing_thinking],
        ),
    ]

    # 设置 LLM 的消息格式
    formatted_messages = llm.format_messages_for_llm(messages)

    # 检查现有的思维块是否保存在单独的字段中
    assert "thinking_blocks" in formatted_messages[0]
    thinking_blocks = formatted_messages[0]["thinking_blocks"]

    assert len(thinking_blocks) == 1
    assert thinking_blocks[0]["thinking"] == "I already have a thinking block"
    assert thinking_blocks[0]["signature"] == "existing_sig"


def test_thinking_blocks_in_message_dict():
    """测试思维块是否作为字段放置在 message_dict 中。"""
    thinking_block = ThinkingBlock(
        thinking="Analyzing the problem...",
        signature="sig_xyz",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="Here's my answer.")],
        thinking_blocks=[thinking_block],
    )

    # 通过_list_serializer测试
    message_dict = message._list_serializer(vision_enabled=False)

    # 验证 thinking_blocks 是 message_dict 中的顶级字段
    assert "thinking_blocks" in message_dict
    assert isinstance(message_dict["thinking_blocks"], list)
    assert len(message_dict["thinking_blocks"]) == 1

    # 验证message_dict中思维块的结构
    thinking_dict = message_dict["thinking_blocks"][0]
    assert thinking_dict["type"] == "thinking"
    assert thinking_dict["thinking"] == "Analyzing the problem..."
    assert thinking_dict["signature"] == "sig_xyz"

    # 验证内容与 thinking_blocks 分开
    assert "content" in message_dict
    assert len(message_dict["content"]) == 1
    assert message_dict["content"][0]["type"] == "text"


def test_thinking_blocks_in_message_dict_via_to_chat_dict():
    """测试调用 to_chat_dict 时是否包含思维块。"""
    thinking_block = ThinkingBlock(
        thinking="Step-by-step reasoning...",
        signature="sig_chat",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="Final result.")],
        thinking_blocks=[thinking_block],
    )

    # 通过调用 _list_serializer 的 to_chat_dict 进行测试
    chat_dict = message.to_chat_dict(
        cache_enabled=False,
        vision_enabled=False,
        function_calling_enabled=True,
        force_string_serializer=False,
        send_reasoning_content=False,
    )

    # 验证 thinking_blocks 字段是否存在
    assert "thinking_blocks" in chat_dict
    assert len(chat_dict["thinking_blocks"]) == 1
    assert chat_dict["thinking_blocks"][0]["thinking"] == "Step-by-step reasoning..."
    assert chat_dict["thinking_blocks"][0]["signature"] == "sig_chat"


def test_no_thinking_blocks_field_when_empty():
    """测试没有块时不添加thinking_blocks字段。"""
    message = Message(
        role="assistant",
        content=[TextContent(text="Simple response.")],
    )

    message_dict = message._list_serializer(vision_enabled=False)

    # 当没有思维障碍时，场域就不应该存在
    assert "thinking_blocks" not in message_dict
    assert "content" in message_dict


def test_thinking_blocks_only_for_assistant_role():
    """测试思维块是否仅针对助理角色消息添加。"""
    thinking_block = ThinkingBlock(
        thinking="This should not appear...",
        signature="sig_user",
    )

    # 使用思维块创建用户消息（不常见但可能）
    user_message = Message(
        role="user",
        content=[TextContent(text="User input.")],
        thinking_blocks=[thinking_block],
    )

    user_dict = user_message._list_serializer(vision_enabled=False)

    # 非辅助角色不宜添加思维块
    assert "thinking_blocks" not in user_dict

    # 现在用助手角色进行测试
    assistant_message = Message(
        role="assistant",
        content=[TextContent(text="Assistant response.")],
        thinking_blocks=[thinking_block],
    )

    assistant_dict = assistant_message._list_serializer(vision_enabled=False)

    # 辅助角色应添加思维块
    assert "thinking_blocks" in assistant_dict
    assert len(assistant_dict["thinking_blocks"]) == 1


def test_redacted_thinking_block_in_message_dict():
    """测试已脱敏思维块是否也正确放置在 message_dict 中。"""
    from openhands.sdk.llm.message import RedactedThinkingBlock

    redacted_block = RedactedThinkingBlock(
        data="[REDACTED]",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="Response after redaction.")],
        thinking_blocks=[redacted_block],
    )

    message_dict = message._list_serializer(vision_enabled=False)

    # 验证已脱敏思维块在message_dict中
    assert "thinking_blocks" in message_dict
    assert len(message_dict["thinking_blocks"]) == 1
    assert message_dict["thinking_blocks"][0]["type"] == "redacted_thinking"
    assert message_dict["thinking_blocks"][0]["data"] == "[REDACTED]"


def test_mixed_thinking_and_redacted_blocks():
    """测试混合思维和已脱敏思维块的处理。"""
    from openhands.sdk.llm.message import RedactedThinkingBlock

    thinking_block = ThinkingBlock(
        thinking="Active reasoning...",
        signature="sig_active",
    )
    redacted_block = RedactedThinkingBlock(data="[REDACTED]")

    message = Message(
        role="assistant",
        content=[TextContent(text="Mixed blocks response.")],
        thinking_blocks=[thinking_block, redacted_block],
    )

    message_dict = message._list_serializer(vision_enabled=False)

    # 验证这两种类型都在 message_dict 中
    assert "thinking_blocks" in message_dict
    assert len(message_dict["thinking_blocks"]) == 2
    assert message_dict["thinking_blocks"][0]["type"] == "thinking"
    assert message_dict["thinking_blocks"][1]["type"] == "redacted_thinking"
