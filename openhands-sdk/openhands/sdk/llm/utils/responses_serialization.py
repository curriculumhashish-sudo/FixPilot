"""序列化器将 ``Message`` 个实例转换为 OpenAI 个响应 API
``input`` 项。 ``Message.to_responses_dict`` 代表们在此。
"""

from collections.abc import Sequence
from typing import Any

from openhands.sdk.llm.message import (
    ImageContent,
    Message,
    ReasoningItemModel,
    TextContent,
)


def message_to_responses_dict(
    message: Message, *, vision_enabled: bool
) -> list[dict[str, Any]]:
    """序列化 OpenAI 响应消息（输入参数）。

    生成响应 API 的“输入”项目列表：
    - system: 返回 []，系统内容应在“指令”中
    - user: 一个包含内容部分的“消息”项目 -> input_text / input_image（启用视觉时）
    - assistant: 发出先前的辅助内容为 input_text，function_call 项为 tool_calls
    - tool: 发出 function_call_output 个项目（每个 TextContent 一个）并匹配 call_id
    """
    match message.role:
        case "system":
            return []
        case "user":
            return _user_to_responses_items(message, vision_enabled=vision_enabled)
        case "assistant":
            return _assistant_to_responses_items(message)
        case "tool":
            return _tool_to_responses_items(message, vision_enabled=vision_enabled)
        case _:
            return []


def _user_to_responses_items(
    message: Message, *, vision_enabled: bool
) -> list[dict[str, Any]]:
    """将用户消息转换为响应 API 格式。"""
    content_items = _build_user_content_items(
        message.content, vision_enabled=vision_enabled
    )
    return [
        {
            "type": "message",
            "role": "user",
            "content": content_items or [{"type": "input_text", "text": ""}],
        }
    ]


def _build_user_content_items(
    content: Sequence[TextContent | ImageContent], *, vision_enabled: bool
) -> list[dict[str, Any]]:
    """构建用户消息的内容项（input_text 和 input_image）。"""
    items: list[dict[str, Any]] = []
    for c in content:
        if isinstance(c, TextContent):
            items.append({"type": "input_text", "text": c.text})
        elif isinstance(c, ImageContent) and vision_enabled:
            for url in c.image_urls:
                items.append(
                    {"type": "input_image", "image_url": url, "detail": "auto"}
                )
    return items


def _assistant_to_responses_items(message: Message) -> list[dict[str, Any]]:
    """将助理消息转换为响应 API 格式。"""
    items: list[dict[str, Any]] = []

    reasoning_item = _build_reasoning_item(message.responses_reasoning_item)
    if reasoning_item:
        items.append(reasoning_item)

    content_items = _build_assistant_content_items(message.content)
    if content_items:
        items.append({"type": "message", "role": "assistant", "content": content_items})

    if message.tool_calls:
        items.extend(tc.to_responses_dict() for tc in message.tool_calls)

    return items


def _build_reasoning_item(
    reasoning_item: ReasoningItemModel | None,
) -> dict[str, Any] | None:
    """如果存在的话，从 responses_reasoning_item 构建推理项。"""
    if reasoning_item is None or reasoning_item.id is None:
        return None

    item: dict[str, Any] = {
        "type": "reasoning",
        "id": reasoning_item.id,
        "summary": [
            {"type": "summary_text", "text": s} for s in (reasoning_item.summary or [])
        ],
    }

    if reasoning_item.content:
        item["content"] = [
            {"type": "reasoning_text", "text": t} for t in reasoning_item.content
        ]
    if reasoning_item.encrypted_content:
        item["encrypted_content"] = reasoning_item.encrypted_content
    if reasoning_item.status:
        item["status"] = reasoning_item.status

    return item


def _build_assistant_content_items(
    content: Sequence[TextContent | ImageContent],
) -> list[dict[str, Any]]:
    """从助理内容构建 output_text 项。"""
    return [
        {"type": "output_text", "text": c.text}
        for c in content
        if isinstance(c, TextContent) and c.text
    ]


def _tool_to_responses_items(
    message: Message, *, vision_enabled: bool
) -> list[dict[str, Any]]:
    """将工具消息转换为响应 API 格式 (function_call_output)。"""
    if message.tool_call_id is None:
        return []

    items: list[dict[str, Any]] = []
    for c in message.content:
        if isinstance(c, TextContent):
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message._maybe_truncate_tool_text(c.text),
                }
            )
        elif isinstance(c, ImageContent) and vision_enabled:
            for url in c.image_urls:
                items.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": [
                            {
                                "type": "input_image",
                                "image_url": url,
                                "detail": "auto",
                            }
                        ],
                    }
                )
    return items
