"""用于将 OpenHands SDK 事件转换为 OpenAI 消息格式的实用程序。

该模块提供将 SDK 事件转换为 GraySwan Cygnal API 所需的 OpenAI 消息格式的功能。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from openhands.sdk.event import (
    ActionEvent,
    LLMConvertibleEvent,
    MessageEvent,
    ObservationBaseEvent,
    ObservationEvent,
    SystemPromptEvent,
)
from openhands.sdk.llm import ImageContent, TextContent, content_to_str
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


def convert_events_to_openai_messages(
    events: Sequence[LLMConvertibleEvent],
) -> list[dict[str, Any]]:
    """将 OpenHands SDK 事件转换为 LLM APIs 的 OpenAI 消息格式。

    该函数将 SDK 事件转换为 OpenAI-兼容的 APIs 需要的格式，这是 GraySwan Cygnal API
    所需的。

    Args:
        events: LLMConvertibleEvent 个要转换的对象列表

    Returns:
        OpenAI消息格式的字典列表
    """
    openai_messages: list[dict[str, Any]] = []

    logger.debug(f"Converting {len(events)} events to OpenAI messages")

    for event in events:
        event_type = type(event).__name__

        # 手柄系统提示词
        if isinstance(event, SystemPromptEvent):
            msg = {"role": "system", "content": event.system_prompt.text}
            openai_messages.append(msg)

        # 处理消息事件（用户/代理消息）
        elif isinstance(event, MessageEvent):
            source = event.source
            llm_message = event.to_llm_message()

            # 从消息中提取文本内容
            content_parts = []
            for content in llm_message.content:
                if isinstance(content, TextContent):
                    content_parts.append(content.text)
                elif isinstance(content, ImageContent):
                    # 跳过图像进行安全分析
                    logger.debug("Skipping image content in security analysis")
                    continue

            content_str = " ".join(content_parts)

            if source == "user":
                msg = {"role": "user", "content": content_str}
                openai_messages.append(msg)
            elif source == "agent":
                msg = {"role": "assistant", "content": content_str}
                openai_messages.append(msg)

        # 处理动作事件（智能体中的工具调用）
        elif isinstance(event, ActionEvent):
            # 构建工具调用结构
            tool_call_dict = {
                "id": event.tool_call_id,
                "type": "function",
                "function": {
                    "name": event.tool_name,
                    "arguments": event.tool_call.arguments,
                },
            }

            # 从参数中删除 security_risk 以避免分析出现偏差
            try:
                args = json.loads(event.tool_call.arguments)
                if "security_risk" in args:
                    del args["security_risk"]
                    tool_call_dict["function"]["arguments"] = json.dumps(args)
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(f"Could not remove security_risk from arguments: {e}")

            # 提取思想内容
            thought_text = " ".join([t.text for t in event.thought])

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": thought_text,
                "tool_calls": [tool_call_dict],
            }
            openai_messages.append(assistant_msg)

        # 处理观测结果事件（工具响应）
        elif isinstance(event, ObservationEvent):
            tool_call_id = event.tool_call_id

            if tool_call_id:
                # 从观测结果获取内容
                content_parts = content_to_str(event.observation.to_llm_content)
                content_str = " ".join(content_parts)

                msg = {
                    "role": "tool",
                    "content": content_str,
                    "tool_call_id": tool_call_id,
                }
                openai_messages.append(msg)
            else:
                logger.warning(
                    f"Could not find tool_call_id for observation {event_type}"
                )

        # 处理其他观测结果基本事件（错误、拒绝）
        elif isinstance(event, ObservationBaseEvent):
            tool_call_id = event.tool_call_id

            if tool_call_id:
                # 从事件的 LLM 消息中获取内容
                llm_message = event.to_llm_message()
                content_parts = content_to_str(llm_message.content)
                content_str = " ".join(content_parts)

                msg = {
                    "role": "tool",
                    "content": content_str,
                    "tool_call_id": tool_call_id,
                }
                openai_messages.append(msg)
            else:
                logger.warning(
                    f"Could not find tool_call_id for observation {event_type}"
                )

    return openai_messages
