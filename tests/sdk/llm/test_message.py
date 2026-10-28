from unittest.mock import patch

import pytest
from litellm.types.utils import Message as LiteLLMMessage

from openhands.sdk.llm.message import Message


# to_chat_dict() 的默认序列化选项 - 测试可以根据需要覆盖
DEFAULT_SERIALIZATION_OPTS = {
    "cache_enabled": False,
    "vision_enabled": False,
    "function_calling_enabled": False,
    "force_string_serializer": False,
    "send_reasoning_content": False,
}


def test_content_base_class_not_implemented():
    """测试Content基类由于抽象方法而无法实例化。"""
    from openhands.sdk.llm.message import BaseContent

    with pytest.raises(TypeError, match="Can't instantiate abstract class BaseContent"):
        BaseContent()  # type: ignore[abstract]


def test_text_content_with_cache_prompt():
    """在启用 cache_prompt 的情况下测试 TextContent。"""
    from openhands.sdk.llm.message import TextContent

    content = TextContent(text="Hello world", cache_prompt=True)
    result = content.to_llm_dict()

    assert len(result) == 1
    assert result[0]["type"] == "text"
    assert result[0]["text"] == "Hello world"
    assert result[0]["cache_control"] == {"type": "ephemeral"}


def test_image_content_with_cache_prompt():
    """在启用 cache_prompt 的情况下测试 ImageContent。"""
    from openhands.sdk.llm.message import ImageContent

    content = ImageContent(
        image_urls=["data:image/png;base64,abc123", "data:image/jpeg;base64,def456"],
        cache_prompt=True,
    )
    result = content.to_llm_dict()

    assert len(result) == 2
    assert result[0]["type"] == "image_url"
    assert result[0]["image_url"]["url"] == "data:image/png;base64,abc123"  # type: ignore
    assert result[1]["type"] == "image_url"
    assert result[1]["image_url"]["url"] == "data:image/jpeg;base64,def456"  # type: ignore
    # 只有最后一张图片应该有 cache_control
    assert "cache_control" not in result[0]
    assert result[1]["cache_control"] == {"type": "ephemeral"}


def test_message_contains_image_property():
    """测试 Message.contains_image 属性。"""
    from openhands.sdk.llm.message import ImageContent, Message, TextContent

    # 仅包含文字内容的消息
    text_message = Message(role="user", content=[TextContent(text="Hello")])
    assert not text_message.contains_image

    # 带有图片内容的消息
    image_message = Message(
        role="user",
        content=[
            TextContent(text="Look at this:"),
            ImageContent(
                image_urls=["data:image/png;base64,abc123"],
            ),
        ],
    )
    assert image_message.contains_image


def test_message_tool_role_with_cache_prompt():
    """使用工具角色和 cache_prompt 测试消息。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="tool",
        content=[TextContent(text="Tool response", cache_prompt=True)],
        tool_call_id="call_123",
        name="test_tool",
    )

    result = message.to_chat_dict(
        **{**DEFAULT_SERIALIZATION_OPTS, "cache_enabled": True}
    )
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "call_123"
    assert result["cache_control"] == {"type": "ephemeral"}
    # 内容不应包含 cache_control，因为它已移至消息级别
    assert "cache_control" not in result["content"][0]


def test_message_tool_role_with_image_cache_prompt():
    """使用工具角色和 ImageContent 和 cache_prompt 测试消息。"""
    from openhands.sdk.llm.message import ImageContent, Message

    message = Message(
        role="tool",
        content=[
            ImageContent(
                image_urls=["data:image/png;base64,abc123"],
                cache_prompt=True,
            )
        ],
        tool_call_id="call_123",
        name="test_tool",
    )

    result = message.to_chat_dict(
        **{**DEFAULT_SERIALIZATION_OPTS, "vision_enabled": True, "cache_enabled": True}
    )
    assert result["role"] == "tool"
    assert result["tool_call_id"] == "call_123"
    assert result["cache_control"] == {"type": "ephemeral"}
    # 图像内容不应包含 cache_control，因为它已移至消息级别
    assert "cache_control" not in result["content"][0]


def test_image_content_survives_forced_string_serializer():
    """当强制使用字符串序列化时，不得删除图像。

    回归测试：DeepSeek/GLM 等模型强制字符串序列化器，其实现仅发出 TextContent。 因此
    ，携带图像的消息会默默地已序列化转换为文本，并且图像被丢弃
    ，因此具有视觉能力的模型永远不会收到图像。
    """
    from openhands.sdk.llm.message import ImageContent, TextContent

    message = Message(
        role="user",
        content=[
            TextContent(text="What is in this image?"),
            ImageContent(image_urls=["data:image/png;base64,abc123"]),
        ],
    )

    result = message.to_chat_dict(
        **{
            **DEFAULT_SERIALIZATION_OPTS,
            "vision_enabled": True,
            "force_string_serializer": True,
        }
    )

    assert isinstance(result["content"], list)
    assert any(part.get("type") == "image_url" for part in result["content"])


def test_image_content_dropped_when_vision_disabled():
    """当视力丧失时，图像会被故意省略，文字会保留下来。"""
    from openhands.sdk.llm.message import ImageContent, TextContent

    message = Message(
        role="user",
        content=[
            TextContent(text="What is in this image?"),
            ImageContent(image_urls=["data:image/png;base64,abc123"]),
        ],
    )

    result = message.to_chat_dict(
        **{
            **DEFAULT_SERIALIZATION_OPTS,
            "vision_enabled": False,
            "force_string_serializer": True,
        }
    )

    assert result["content"] == "What is in this image?"


def test_text_only_message_still_uses_string_serializer_when_forced():
    """纯文本消息保留强制提供者所需的字符串形式。"""
    from openhands.sdk.llm.message import TextContent

    message = Message(role="user", content=[TextContent(text="Hello")])

    result = message.to_chat_dict(
        **{
            **DEFAULT_SERIALIZATION_OPTS,
            "vision_enabled": True,
            "force_string_serializer": True,
        }
    )

    assert result["content"] == "Hello"


def test_message_with_tool_calls():
    """使用 tool_calls 测试消息。"""
    from openhands.sdk.llm.message import (
        Message,
        MessageToolCall,
        TextContent,
    )

    tool_call = MessageToolCall(
        id="call_123",
        name="test_function",
        arguments='{"arg": "value"}',
        origin="completion",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="I'll call a function")],
        tool_calls=[tool_call],
    )

    result = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
    assert result["role"] == "assistant"
    assert "tool_calls" in result
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["id"] == "call_123"
    assert result["tool_calls"][0]["type"] == "function"
    assert result["tool_calls"][0]["function"]["name"] == "test_function"
    assert result["tool_calls"][0]["function"]["arguments"] == '{"arg": "value"}'


def test_message_tool_calls_drop_empty_string_content():
    """没有文本的助手工具调用不应包含空内容字符串。"""
    from openhands.sdk.llm.message import Message, MessageToolCall

    tool_call = MessageToolCall(
        id="call_empty",
        name="test_function",
        arguments="{}",
        origin="completion",
    )

    message = Message(
        role="assistant",
        content=[],
        tool_calls=[tool_call],
    )

    result = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
    assert "content" not in result


def test_message_tool_calls_strip_blank_list_content():
    """List-已序列化工具调用消息应删除空白文本内容块。"""
    from openhands.sdk.llm.message import Message, MessageToolCall, TextContent

    tool_call = MessageToolCall(
        id="call_blank_list",
        name="test_function",
        arguments="{}",
        origin="completion",
    )

    message = Message(
        role="assistant",
        content=[TextContent(text="")],
        tool_calls=[tool_call],
    )

    result = message.to_chat_dict(
        **{**DEFAULT_SERIALIZATION_OPTS, "function_calling_enabled": True}
    )
    assert "content" not in result


def test_empty_assistant_message_uses_string_content_in_list_serializer():
    """List-已序列化空助手消息应保留字符串内容。"""
    message = Message(role="assistant", content=[])

    result = message.to_chat_dict(
        **{**DEFAULT_SERIALIZATION_OPTS, "function_calling_enabled": True}
    )

    assert result == {"content": "", "role": "assistant"}


def test_empty_assistant_from_llm_chat_message_uses_string_content_in_list_serializer():
    """空助手 LLM 响应应保留字符串内容。"""
    litellm_message = LiteLLMMessage(role="assistant", content=None)
    message = Message.from_llm_chat_message(litellm_message)

    result = message.to_chat_dict(
        **{**DEFAULT_SERIALIZATION_OPTS, "function_calling_enabled": True}
    )

    assert result == {"content": "", "role": "assistant"}


def test_message_from_llm_chat_message_function_role_error():
    """使用函数角色测试 Message.from_llm_chat_message 会引发错误。"""
    from openhands.sdk.llm.message import Message

    litellm_message = LiteLLMMessage(role="function", content="Function response")  # type: ignore

    with pytest.raises(AssertionError, match="Function role is not supported"):
        Message.from_llm_chat_message(litellm_message)


def test_message_from_llm_chat_message_with_non_string_content():
    """使用非字符串内容测试 Message.from_llm_chat_message。"""
    from openhands.sdk.llm.message import Message

    # 创建包含非字符串内容的消息（None 或列表）
    litellm_message = LiteLLMMessage(role="assistant", content=None)

    result = Message.from_llm_chat_message(litellm_message)
    assert result.role == "assistant"
    assert result.content == []  # 非字符串内容的空列表


def test_text_content_truncation_under_limit():
    """测试 TextContent 在低于限制时不会截断。"""
    from openhands.sdk.llm.message import TextContent

    content = TextContent(text="Short text")
    result = content.to_llm_dict()

    assert len(result) == 1
    assert result[0]["text"] == "Short text"


def test_text_content_no_truncation_over_limit():
    """TextContent 本身不应截断； 截断仅是角色=工具。"""
    from openhands.sdk.llm.message import TextContent
    from openhands.sdk.utils import DEFAULT_TEXT_CONTENT_LIMIT

    long_text = "A" * (DEFAULT_TEXT_CONTENT_LIMIT + 1000)

    with patch("openhands.sdk.llm.message.logger") as mock_logger:
        content = TextContent(text=long_text)
        result = content.to_llm_dict()

        mock_logger.warning.assert_not_called()
        assert len(result) == 1
        assert result[0]["text"] == long_text


def test_tool_message_truncates_text_over_limit():
    """工具角色消息应截断巨大的 TextContent 块。"""
    from openhands.sdk.llm.message import Message, TextContent
    from openhands.sdk.utils import DEFAULT_TEXT_CONTENT_LIMIT

    long_text = "A" * (DEFAULT_TEXT_CONTENT_LIMIT + 1000)

    with patch("openhands.sdk.llm.message.logger") as mock_logger:
        msg = Message(role="tool", content=[TextContent(text=long_text)])
        result = msg.to_chat_dict(
            cache_enabled=True,
            vision_enabled=False,
            function_calling_enabled=False,
            force_string_serializer=False,
            send_reasoning_content=False,
        )

        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0]
        assert "Tool TextContent text length" in args[0]
        assert args[1] == DEFAULT_TEXT_CONTENT_LIMIT + 1000
        assert args[2] == DEFAULT_TEXT_CONTENT_LIMIT

        content_item = result["content"][0]
        assert content_item["type"] == "text"
        text_result = content_item["text"]
        assert isinstance(text_result, str)
        assert len(text_result) == DEFAULT_TEXT_CONTENT_LIMIT
        assert "<response clipped>" in text_result


def test_user_message_does_not_truncate_text_over_limit():
    """用户角色消息不应在序列化处截断。"""
    from openhands.sdk.llm.message import Message, TextContent
    from openhands.sdk.utils import DEFAULT_TEXT_CONTENT_LIMIT

    long_text = "A" * (DEFAULT_TEXT_CONTENT_LIMIT + 1000)

    with patch("openhands.sdk.llm.message.logger") as mock_logger:
        msg = Message(role="user", content=[TextContent(text=long_text)])
        result = msg.to_chat_dict(
            cache_enabled=False,
            vision_enabled=False,
            function_calling_enabled=False,
            force_string_serializer=True,
            send_reasoning_content=False,
        )

        mock_logger.warning.assert_not_called()
        assert result["content"] == long_text


def test_tool_message_truncates_text_over_limit_with_string_serializer():
    """工具角色截断还必须应用于 string-序列化器路径。"""
    from openhands.sdk.llm.message import Message, TextContent
    from openhands.sdk.utils import DEFAULT_TEXT_CONTENT_LIMIT

    long_text = "A" * (DEFAULT_TEXT_CONTENT_LIMIT + 1000)

    with patch("openhands.sdk.llm.message.logger") as mock_logger:
        msg = Message(role="tool", content=[TextContent(text=long_text)])
        result = msg.to_chat_dict(
            cache_enabled=False,
            vision_enabled=False,
            function_calling_enabled=False,
            force_string_serializer=True,
            send_reasoning_content=False,
        )

        mock_logger.warning.assert_called_once()
        assert result["content"] != long_text
        assert len(result["content"]) == DEFAULT_TEXT_CONTENT_LIMIT
        assert "<response clipped>" in result["content"]


def test_text_content_truncation_exact_limit():
    """测试 TextContent 在恰好达到极限时不会截断。"""
    from openhands.sdk.llm.message import TextContent
    from openhands.sdk.utils import DEFAULT_TEXT_CONTENT_LIMIT

    # 创建完全符合限制的文本
    exact_text = "A" * DEFAULT_TEXT_CONTENT_LIMIT

    with patch("openhands.sdk.llm.message.logger") as mock_logger:
        content = TextContent(text=exact_text)
        result = content.to_llm_dict()

        # 检查是否未记录任何警告
        mock_logger.warning.assert_not_called()

        # 检查文本是否被截断
        assert len(result) == 1
        assert result[0]["text"] == exact_text


def test_message_with_reasoning_content_when_enabled():
    """测试当 send_reasoning_content 为 True 时是否包含 reasoning_content。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="Final answer")],
        reasoning_content="Let me think step by step...",
    )

    result = message.to_chat_dict(
        **{**DEFAULT_SERIALIZATION_OPTS, "send_reasoning_content": True}
    )
    assert result["role"] == "assistant"
    assert result["content"] == "Final answer"
    assert result["reasoning_content"] == "Let me think step by step..."


def test_message_with_reasoning_content_when_disabled():
    """测试当 send_reasoning_content 为 False 时，reasoning_content 是否包含不。"""  # noqa: E501
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="Final answer")],
        reasoning_content="Let me think step by step...",
    )

    result = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
    assert result["role"] == "assistant"
    assert result["content"] == "Final answer"
    assert "reasoning_content" not in result


def test_message_with_reasoning_content_default_disabled():
    """测试当 send_reasoning_content=False 时，reasoning_content 是否包含不。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="Final answer")],
        reasoning_content="Let me think step by step...",
    )

    result = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
    assert result["role"] == "assistant"
    assert result["content"] == "Final answer"
    assert "reasoning_content" not in result


def test_message_with_reasoning_content_none():
    """即使已启用，测试 reasoning_content 是否在 None 时包含不。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="Final answer")],
        reasoning_content=None,
    )

    result = message.to_chat_dict(
        **{**DEFAULT_SERIALIZATION_OPTS, "send_reasoning_content": True}
    )
    assert result["role"] == "assistant"
    assert result["content"] == "Final answer"
    assert "reasoning_content" not in result


def test_message_with_reasoning_content_empty_string():
    """当 reasoning_content 为空字符串时，测试是否包含不。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="Final answer")],
        reasoning_content="",
    )

    result = message.to_chat_dict(
        **{**DEFAULT_SERIALIZATION_OPTS, "send_reasoning_content": True}
    )
    assert result["role"] == "assistant"
    assert result["content"] == "Final answer"
    assert "reasoning_content" not in result


def test_message_with_reasoning_content_list_serializer():
    """测试 reasoning_content 是否适用于列表序列化器。"""
    from openhands.sdk.llm.message import Message, TextContent

    message = Message(
        role="assistant",
        content=[TextContent(text="Final answer")],
        reasoning_content="Step by step reasoning",
    )

    result = message.to_chat_dict(
        **{
            **DEFAULT_SERIALIZATION_OPTS,
            "function_calling_enabled": True,  # 势力列表序列化器
            "send_reasoning_content": True,
        }
    )
    assert result["role"] == "assistant"
    assert isinstance(result["content"], list)
    assert result["content"][0]["text"] == "Final answer"
    assert result["reasoning_content"] == "Step by step reasoning"


def test_message_deprecated_fields_silently_removed():
    """测试已弃用字段是否在没有警告的情况下被静默删除。

    已弃用字段将永久保留为向后兼容性，并被静默删除（无警告），以避免加载旧事件时出现
    噪音。
    """
    from openhands.sdk.llm.message import Message

    deprecated_fields = [
        "cache_enabled",
        "vision_enabled",
        "function_calling_enabled",
        "force_string_serializer",
        "send_reasoning_content",
    ]

    # 单独测试每个已弃用字段 - 应该加载而不会出现错误
    for field in deprecated_fields:
        message = Message.model_validate(
            {"role": "user", "content": "test", field: True}
        )
        # 消息应该已成功创建
        assert message.role == "user"
        # 已弃用字段不应存在于模型中
        assert not hasattr(message, field)


def test_message_deprecated_fields_are_ignored():
    """测试已弃用字段是否被忽略并且不会影响消息。"""
    from openhands.sdk.llm.message import Message

    # 使用 model_validate 传递 Pyright 不知道的额外字段
    message = Message.model_validate(
        {
            "role": "user",
            "content": "test",
            "cache_enabled": True,
            "vision_enabled": True,
            "function_calling_enabled": True,
            "force_string_serializer": True,
            "send_reasoning_content": True,
        }
    )

    # 消息应该已成功创建
    assert message.role == "user"
    assert len(message.content) == 1

    # 已弃用字段不应存在于模型中
    assert not hasattr(message, "cache_enabled")
    assert not hasattr(message, "vision_enabled")
    assert not hasattr(message, "function_calling_enabled")
    assert not hasattr(message, "force_string_serializer")
    assert not hasattr(message, "send_reasoning_content")


def test_text_content_deprecated_enable_truncation_silently_removed():
    """测试已弃用 enable_truncation 字段被默默删除。

    这可以确保在加载包含已弃用 enable_truncation 字段的旧事件时向后兼容性。 该字段会
    被悄悄删除（没有警告），以避免加载旧事件时出现噪音。
    """
    from openhands.sdk.llm.message import TextContent

    content = TextContent.model_validate(
        {"type": "text", "text": "Hello world", "enable_truncation": True}
    )

    # 内容应该已成功创建
    assert content.text == "Hello world"
    assert content.type == "text"
    # 已弃用字段不应存在于模型中
    assert not hasattr(content, "enable_truncation")


def test_text_content_old_format_with_enable_truncation_loads_successfully():
    """测试带有 enable_truncation 的旧事件格式加载没有错误。

    这模拟加载字段为已弃用之前为已持久化的旧事件。 该事件应成功加载，并且已弃用字段应
    被忽略。
    """
    import warnings

    from openhands.sdk.llm.message import TextContent

    # 模拟旧事件的 JSON 结构
    old_event_text_content = {
        "type": "text",
        "text": "Tool execution result",
        "cache_prompt": False,
        "enable_truncation": True,  # 旧已弃用字段
    }

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 禁止此测试的警告
        content = TextContent.model_validate(old_event_text_content)

    # 应该加载成功
    assert content.text == "Tool execution result"
    assert content.type == "text"
    assert content.cache_prompt is False


def test_text_content_both_old_and_new_format_in_sequence():
    """测试旧格式和新格式 TextContent 是否可以按顺序加载。

    这模拟了一个场景，其中包含来自不同事件的对话加载 SDK 版本 - 一些带有已弃用包含一
    些没有的字段。
    """
    import warnings

    from openhands.sdk.llm.message import TextContent

    # 模拟加载来自不同 SDK 版本的多个事件
    event_contents = [
        # 旧格式（带有已弃用字段）
        {"type": "text", "text": "Old event 1", "enable_truncation": True},
        # 新格式
        {"type": "text", "text": "New event 1"},
        # 旧格式（带有已弃用字段和 cache_prompt）
        {
            "type": "text",
            "text": "Old event 2",
            "enable_truncation": False,
            "cache_prompt": True,
        },
        # 带有 cache_prompt 的新格式
        {"type": "text", "text": "New event 2", "cache_prompt": True},
    ]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # 禁止此测试的警告
        loaded_contents = [TextContent.model_validate(ec) for ec in event_contents]

    # 全部应该加载成功
    assert len(loaded_contents) == 4
    assert loaded_contents[0].text == "Old event 1"
    assert loaded_contents[1].text == "New event 1"
    assert loaded_contents[2].text == "Old event 2"
    assert loaded_contents[2].cache_prompt is True
    assert loaded_contents[3].text == "New event 2"
    assert loaded_contents[3].cache_prompt is True
