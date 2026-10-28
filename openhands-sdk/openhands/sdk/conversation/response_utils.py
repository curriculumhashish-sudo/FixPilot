"""用于从对话事件中提取智能体响应的实用函数。"""

from collections.abc import Sequence

from openhands.sdk.event import ActionEvent, MessageEvent
from openhands.sdk.event.base import Event
from openhands.sdk.llm.message import content_to_str
from openhands.sdk.tool.builtins.finish import FinishAction, FinishTool


def get_agent_final_response(events: Sequence[Event]) -> str:
    """从智能体中提取最终响应。

    智能体可以通过两种方式结束对话：
    1. 通过调用完成工具
    2. 通过返回不带工具调用的短信

    Args:
        events: 要搜索的对话事件列表。

    Returns:
        最终的响应消息来自智能体，如果没有找到则为空字符串。
    """
    # 从智能体中查找最后一个完成操作或消息事件
    for event in reversed(events):
        # 情况1：完成工具调用
        if (
            isinstance(event, ActionEvent)
            and event.source == "agent"
            and event.tool_name == FinishTool.name
        ):
            # 从完成工具调用中提取消息
            if event.action is not None and isinstance(event.action, FinishAction):
                return event.action.message
            else:
                break
        # 情况 2：没有工具调用 (MessageEvent) 的短信
        elif isinstance(event, MessageEvent) and event.source == "agent":
            text_parts = content_to_str(event.llm_message.content)
            return "".join(text_parts)
    return ""
