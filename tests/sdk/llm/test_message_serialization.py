"""对消息序列化行为的综合测试。

该模块测试 Message 类序列化，该类现在有两个不同的路径：
1. 标准 Pydantic 序列化 (model_dump/model_dump_json) 用于存储 - 始终保留结构
2. LLM API 序列化 (to_chat_dict) 用于提供商消费 - 根据功能调整格式

重构的设计将存储问题与 API 格式化问题分开。 测试是按序列化策略组织的，以确保明确的关
注点分离。
"""

import json

from openhands.sdk.llm.message import (
    ImageContent,
    Message,
    TextContent,
)


# to_chat_dict() 的默认序列化选项 - 测试可以根据需要覆盖
DEFAULT_SERIALIZATION_OPTS = {
    "cache_enabled": False,
    "vision_enabled": False,
    "function_calling_enabled": False,
    "force_string_serializer": False,
    "send_reasoning_content": False,
}


class TestStorageSerialization:
    """测试存储序列化 (model_dump/model_dump_json) - 始终保留
    结构。
    """

    def test_basic_text_message_storage_serialization(self):
        """测试基本文本消息存储序列化保留列表结构。"""
        message = Message(
            role="user",
            content=[TextContent(text="Hello, world!")],
        )

        # 存储序列化 - 始终保留结构
        storage_data = message.model_dump()
        assert isinstance(storage_data["content"], list)
        assert len(storage_data["content"]) == 1
        assert storage_data["content"][0]["text"] == "Hello, world!"
        assert storage_data["content"][0]["type"] == "text"
        assert storage_data["role"] == "user"

        # 往返存储效果完美
        json_data = message.model_dump_json()
        deserialized = Message.model_validate_json(json_data)
        assert deserialized == message

    def test_vision_message_storage_serialization(self):
        """测试视觉消息存储序列化保留所有内容类型。"""
        message = Message(
            role="user",
            content=[
                TextContent(text="What's in this image?"),
                ImageContent(
                    image_urls=["https://example.com/image.jpg"],
                ),
            ],
        )

        # 存储序列化 - 始终列表格式
        storage_data = message.model_dump()
        assert isinstance(storage_data["content"], list)
        assert len(storage_data["content"]) == 2
        assert storage_data["content"][0]["type"] == "text"
        assert storage_data["content"][1]["type"] == "image"

        # 往返工程
        deserialized = Message.model_validate(storage_data)
        assert deserialized == message

    def test_tool_response_message_storage_serialization(self):
        """测试工具响应消息存储序列化保留所有字段。"""
        message = Message(
            role="tool",
            content=[TextContent(text="Weather in NYC: 72°F, sunny")],
            tool_call_id="call_123",
            name="get_weather",
        )

        # 存储序列化
        storage_data = message.model_dump()
        assert isinstance(storage_data["content"], list)
        assert storage_data["tool_call_id"] == "call_123"
        assert storage_data["name"] == "get_weather"

        # 往返工程
        deserialized = Message.model_validate(storage_data)
        assert deserialized == message

    def test_empty_content_storage_serialization(self):
        """测试空内容列表存储序列化。"""
        message = Message(role="user", content=[])

        # 存储序列化
        storage_data = message.model_dump()
        assert storage_data["content"] == []

        # 往返工程
        deserialized = Message.model_validate(storage_data)
        assert deserialized == message

    def test_field_defaults_after_minimal_deserialization(self):
        """反序列化最小 JSON 后测试字段默认值是正确的。"""
        minimal_json = json.dumps(
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]}
        )

        message = Message.model_validate_json(minimal_json)
        assert message.tool_calls is None
        assert message.tool_call_id is None
        assert message.name is None

        # 存储往返保留默认值
        storage_data = message.model_dump()
        deserialized = Message.model_validate(storage_data)
        assert deserialized == message


class TestLLMAPISerialization:
    """测试 LLM API 序列化 (to_chat_dict) - 根据以下内容调整格式
    能力。
    """

    def test_basic_text_message_llm_string_serialization(self):
        """测试基本文本消息使用字符串格式为LLMAPI。"""
        message = Message(
            role="user",
            content=[TextContent(text="Hello, world!")],
        )

        # LLM API 序列化 - 使用字符串格式表示简单消息
        llm_data = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
        assert isinstance(llm_data["content"], str)
        assert llm_data["content"] == "Hello, world!"
        assert llm_data["role"] == "user"

    def test_cache_enabled_triggers_list_serialization(self):
        """cache_enabled=True 的测试消息会触发 LLM 的列表序列化器。"""
        message = Message(
            role="user",
            content=[TextContent(text="Hello, world!")],
        )

        # LLM API 序列化 - 由于 cache_enabled 而使用列表格式
        llm_data = message.to_chat_dict(
            **{**DEFAULT_SERIALIZATION_OPTS, "cache_enabled": True}
        )
        assert isinstance(llm_data["content"], list)
        assert len(llm_data["content"]) == 1
        assert llm_data["content"][0]["text"] == "Hello, world!"

    def test_vision_enabled_triggers_list_serialization(self):
        """vision_enabled=True 的测试消息会触发 LLM 的列表序列化器。"""
        message = Message(
            role="user",
            content=[
                TextContent(text="What's in this image?"),
                ImageContent(
                    image_urls=["https://example.com/image.jpg"],
                ),
            ],
        )

        # LLM API 序列化 - 由于 vision_enabled 而使用列表格式
        llm_data = message.to_chat_dict(
            **{**DEFAULT_SERIALIZATION_OPTS, "vision_enabled": True}
        )
        assert isinstance(llm_data["content"], list)
        assert len(llm_data["content"]) == 2
        assert llm_data["content"][0]["text"] == "What's in this image?"
        assert llm_data["content"][1]["type"] == "image_url"

    def test_function_calling_enabled_triggers_list_serialization(self):
        """测试消息 function_calling_enabled=True 触发列表序列化器
        LLM.
        """
        message = Message(
            role="user",
            content=[TextContent(text="Call a function")],
        )

        # LLM API 序列化 - 由于 function_calling_enabled 而使用列表格式
        llm_data = message.to_chat_dict(
            **{**DEFAULT_SERIALIZATION_OPTS, "function_calling_enabled": True}
        )
        assert isinstance(llm_data["content"], list)

    def test_force_string_serializer_override(self):
        """测试 force_string_serializer=True 覆盖 LLM 的其他设置。"""
        message = Message(
            role="user",
            content=[TextContent(text="Hello, world!")],
        )

        # LLM API 序列化 - 强制为字符串格式
        llm_data = message.to_chat_dict(
            **{
                **DEFAULT_SERIALIZATION_OPTS,
                "cache_enabled": True,  # 通常会触发列表序列化器
                "force_string_serializer": True,  # 但这迫使字符串
            }
        )
        assert isinstance(llm_data["content"], str)
        assert llm_data["content"] == "Hello, world!"

    def test_tool_response_message_llm_serialization(self):
        """测试工具响应消息使用字符串格式，以实现简单的工具响应。"""
        message = Message(
            role="tool",
            content=[TextContent(text="Weather in NYC: 72°F, sunny")],
            tool_call_id="call_123",
            name="get_weather",
        )

        # LLM API 序列化 - 使用字符串格式进行简单的工具响应
        llm_data = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
        assert isinstance(llm_data["content"], str)
        assert llm_data["content"] == "Weather in NYC: 72°F, sunny"
        assert llm_data["tool_call_id"] == "call_123"
        assert llm_data["name"] == "get_weather"

    def test_empty_content_llm_serialization(self):
        """测试空内容列表转换为LLM序列化中的空字符串。"""
        message = Message(
            role="user",
            content=[],
        )

        # LLM API 序列化 - 字符串序列化器将空列表转换为空字符串
        llm_data = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
        assert llm_data["content"] == ""

    def test_multiple_text_content_string_serialization(self):
        """测试多个 TextContent 项目与 LLM 中的换行符连接
        序列化。
        """
        message = Message(
            role="user",
            content=[
                TextContent(text="First line"),
                TextContent(text="Second line"),
                TextContent(text="Third line"),
            ],
        )

        # LLM API 序列化 - 用换行符连接
        llm_data = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
        assert isinstance(llm_data["content"], str)
        assert llm_data["content"] == "First line\nSecond line\nThird line"

    def test_content_type_preservation_in_list_serializer(self):
        """测试内容类型在 LLM 的列表序列化器中正确保留。"""
        message = Message(
            role="user",
            content=[
                TextContent(text="Describe this image"),
                ImageContent(
                    image_urls=["https://example.com/image.jpg"],
                ),
            ],
        )

        # LLM API 序列化
        llm_data = message.to_chat_dict(
            **{**DEFAULT_SERIALIZATION_OPTS, "vision_enabled": True}
        )
        assert isinstance(llm_data["content"], list)
        assert len(llm_data["content"]) == 2
        assert llm_data["content"][0]["type"] == "text"
        assert llm_data["content"][1]["type"] == "image_url"


class TestSerializationPathSelection:
    """测试确定 LLM API 使用哪个序列化路径的逻辑。"""

    def test_serialization_path_selection_logic(self):
        """测试确定将哪个序列化路径用于 LLM 的逻辑。"""
        message = Message(
            role="user",
            content=[TextContent(text="test")],
        )

        # 默认设置（全部 False）-> 字符串序列化器
        llm_data1 = message.to_chat_dict(**DEFAULT_SERIALIZATION_OPTS)
        assert isinstance(llm_data1["content"], str)

        # cache_enabled -> 列表序列化器
        llm_data2 = message.to_chat_dict(
            **{**DEFAULT_SERIALIZATION_OPTS, "cache_enabled": True}
        )
        assert isinstance(llm_data2["content"], list)

        # vision_enabled -> 列表序列化器
        llm_data3 = message.to_chat_dict(
            **{**DEFAULT_SERIALIZATION_OPTS, "vision_enabled": True}
        )
        assert isinstance(llm_data3["content"], list)

        # function_calling_enabled -> 列表序列化器
        llm_data4 = message.to_chat_dict(
            **{**DEFAULT_SERIALIZATION_OPTS, "function_calling_enabled": True}
        )
        assert isinstance(llm_data4["content"], list)

        # force_string_serializer 覆盖一切
        llm_data5 = message.to_chat_dict(
            cache_enabled=True,
            vision_enabled=True,
            function_calling_enabled=True,
            force_string_serializer=True,
            send_reasoning_content=False,
        )
        assert isinstance(llm_data5["content"], str)


class TestDualSerializationConsistency:
    """测试两个序列化策略是否正确协同工作。"""

    def test_storage_always_list_llm_adapts(self):
        """测试存储始终为列表格式，而 LLM 根据
        设置。
        """
        messages = [
            Message(role="user", content=[TextContent(text="test1")]),
            Message(role="user", content=[TextContent(text="test2")]),
            Message(role="user", content=[TextContent(text="test3")]),
            Message(role="user", content=[TextContent(text="test4")]),
        ]

        serialization_configs = [
            # 默认（全部False）->LLM使用字符串，存储使用列表
            DEFAULT_SERIALIZATION_OPTS,
            # 启用缓存 -> 都使用列表
            {**DEFAULT_SERIALIZATION_OPTS, "cache_enabled": True},
            # 启用视觉 -> 均使用列表
            {**DEFAULT_SERIALIZATION_OPTS, "vision_enabled": True},
            # 强制字符串 -> LLM 使用字符串，存储使用列表
            {
                **DEFAULT_SERIALIZATION_OPTS,
                "cache_enabled": True,
                "force_string_serializer": True,
            },
        ]

        for msg, opts in zip(messages, serialization_configs):
            # 存储序列化为始终列表格式
            storage_data = msg.model_dump()
            assert isinstance(storage_data["content"], list)

            # LLM 序列化根据设置进行调整
            llm_data = msg.to_chat_dict(**opts)
            # 内容类型取决于消息设置
            assert "content" in llm_data

            # 往返存储始终有效
            deserialized = Message.model_validate(storage_data)
            assert deserialized == msg
