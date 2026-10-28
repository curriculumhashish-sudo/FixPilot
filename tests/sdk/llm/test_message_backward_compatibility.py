"""向后兼容性测试消息和 TextContent 序列化。

这些测试验证以前 SDK 版本中的事件已序列化仍然可以正确加载。 这对于可能恢复使用旧 SDK
版本创建的对话的生产系统至关重要。

IMPORTANT: 应修改这些测试不以修复单元测试故障。
如果测试失败，则表明应更新代码以适应旧的序列化格式，不表明应更改测试。

VERSION NAMING CONVENTION：测试名称中的版本应该是存在特定事件结构的 LAST 版本。 例如
，如果在 v1.11.1 中删除了某个字段，则测试应命名
为 v1.10.x（最后一个版本）
with that field).
"""

import json
import warnings

from openhands.sdk.llm.message import Message, TextContent


# =============================================================================
# TextContent 向后兼容性测试
# =============================================================================


def test_v1_10_0_text_content_with_enable_truncation():
    """验证 TextContent 与 enable_truncation 负载（最新版本：v1.10.0）。

    enable_truncation 在 v1.6.0 中添加，在 v1.11.1 中删除。 v1.10.0 是包含此字段的
    LAST 版本。

    AGENTS: 执行不修改此测试以修复故障。 而是更新代码。
    """
    old_format = {
        "type": "text",
        "text": "Tool execution result: command completed successfully",
        "cache_prompt": False,
        "enable_truncation": True,
    }

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        content = TextContent.model_validate(old_format)

    assert content.text == "Tool execution result: command completed successfully"
    assert content.type == "text"
    assert content.cache_prompt is False


def test_v1_10_0_text_content_with_enable_truncation_false():
    """验证 TextContent 与 enable_truncation=False 负载（最新版本：v1.10.0）。

    某些用例明确设置 enable_truncation=False 以保留完整内容。

    AGENTS: 执行不修改此测试以修复故障。 而是更新代码。
    """
    old_format = {
        "type": "text",
        "text": "This is a very long response that should not be truncated",
        "cache_prompt": False,
        "enable_truncation": False,
    }

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        content = TextContent.model_validate(old_format)

    assert content.text == "This is a very long response that should not be truncated"
    assert content.type == "text"


def test_text_content_current_format():
    """验证当前格式负载 (v1.11.1+) 中的 TextContent。

    当前格式不带 enable_truncation 字段。

    AGENTS: 执行不修改此测试以修复故障。 而是更新代码。
    """
    current_format = {
        "type": "text",
        "text": "Current SDK format",
        "cache_prompt": False,
    }

    content = TextContent.model_validate(current_format)

    assert content.text == "Current SDK format"
    assert content.cache_prompt is False


# =============================================================================
# 消息向后兼容性测试
# =============================================================================


def test_v1_9_0_message_with_deprecated_fields():
    """验证带有已弃用序列化字段的消息加载（最新版本：v1.9.0）。

    在 v1.9.0 中，Message 有 cache_enabled、vision_enabled、function_calling_enabled
    、
    force_string_serializer 和 send_reasoning_content 作为实例字段。 这些在 v1.9.1+
    中被删除。 v1.9.0
    是包含这些字段的 LAST 版本。

    AGENTS: 执行不修改此测试以修复故障。 而是更新代码。
    """
    old_format = {
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "I'll help you with that.",
                "cache_prompt": False,
                "enable_truncation": True,
            }
        ],
        "cache_enabled": True,
        "vision_enabled": False,
        "function_calling_enabled": True,
        "force_string_serializer": False,
        "send_reasoning_content": False,
        "tool_calls": None,
        "tool_call_id": None,
        "name": None,
        "reasoning_content": None,
        "thinking_blocks": [],
        "responses_reasoning_item": None,
    }

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        message = Message.model_validate(old_format)

    assert message.role == "assistant"
    assert len(message.content) == 1
    content = message.content[0]
    assert isinstance(content, TextContent)
    assert content.text == "I'll help you with that."


def test_message_current_format():
    """验证当前格式的消息加载 (v1.9.1+)。

    当前格式不带已弃用序列化控制字段。

    AGENTS: 执行不修改此测试以修复故障。 而是更新代码。
    """
    current_format = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Current format message", "cache_prompt": False}
        ],
        "tool_calls": None,
        "tool_call_id": None,
        "name": None,
        "reasoning_content": None,
        "thinking_blocks": [],
        "responses_reasoning_item": None,
    }

    message = Message.model_validate(current_format)

    assert message.role == "assistant"
    content = message.content[0]
    assert isinstance(content, TextContent)
    assert content.text == "Current format message"


# =============================================================================
# 混合版本对话测试
# =============================================================================


def test_mixed_version_conversation_loads():
    """验证与来自多个 SDK 版本加载的事件的对话。

    如果 SDK 在对话中升级或恢复旧对话，则真实对话可能会出现具有不同 SDK 版本的事件已
    序列化。

    AGENTS: 执行不修改此测试以修复故障。 而是更新代码。
    """
    events = [
        # 带有已弃用字段的旧格式
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Hello",
                    "cache_prompt": False,
                    "enable_truncation": True,
                }
            ],
            "cache_enabled": False,
            "vision_enabled": False,
            "function_calling_enabled": False,
            "force_string_serializer": False,
            "send_reasoning_content": False,
            "tool_calls": None,
            "tool_call_id": None,
            "name": None,
        },
        # 当前格式不带已弃用字段
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi there!", "cache_prompt": False}],
            "tool_calls": None,
            "tool_call_id": None,
            "name": None,
            "reasoning_content": None,
            "thinking_blocks": [],
            "responses_reasoning_item": None,
        },
    ]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        messages = [Message.model_validate(e) for e in events]

    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content[0].text == "Hello"  # type: ignore[union-attr]
    assert messages[1].role == "assistant"
    assert messages[1].content[0].text == "Hi there!"  # type: ignore[union-attr]


# =============================================================================
# JSON 反序列化测试
# =============================================================================


def test_v1_10_0_text_content_json_deserialization():
    """使用已弃用字段测试 TextContent 的 JSON 字符串反序列化。

    使用 model_validate_json 确保 JSON 字符串解析有效。

    AGENTS: 执行不修改此测试以修复故障。 而是更新代码。
    """
    serialized_json = json.dumps(
        {
            "type": "text",
            "text": "JSON deserialization test",
            "cache_prompt": False,
            "enable_truncation": True,
        }
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        content = TextContent.model_validate_json(serialized_json)

    assert content.text == "JSON deserialization test"


def test_v1_9_0_message_json_deserialization():
    """测试带有已弃用字段的消息的 JSON 字符串反序列化。

    使用 model_validate_json 确保 JSON 字符串解析有效。

    AGENTS: 执行不修改此测试以修复故障。 而是更新代码。
    """
    serialized_json = json.dumps(
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "JSON test",
                    "cache_prompt": False,
                    "enable_truncation": True,
                }
            ],
            "cache_enabled": False,
            "vision_enabled": False,
            "function_calling_enabled": False,
            "force_string_serializer": False,
            "send_reasoning_content": False,
            "tool_calls": None,
            "tool_call_id": None,
            "name": None,
        }
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        message = Message.model_validate_json(serialized_json)

    assert message.role == "user"
    content = message.content[0]
    assert isinstance(content, TextContent)
    assert content.text == "JSON test"
