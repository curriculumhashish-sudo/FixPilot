"""用于视图属性测试的通用测试夹具和实用程序。"""

from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    MessageEvent,
    ObservationEvent,
)
from openhands.sdk.llm import (
    Message,
    MessageToolCall,
    RedactedThinkingBlock,
    TextContent,
    ThinkingBlock,
)
from openhands.sdk.mcp.definition import MCPToolAction, MCPToolObservation


def create_action_event(
    event_id: str,
    llm_response_id: str,
    tool_call_id: str,
    tool_name: str = "test_tool",
    thinking: str | None = None,
) -> ActionEvent:
    """帮助程序创建具有指定 ID 的 ActionEvent。"""
    action = MCPToolAction(data={})

    tool_call = MessageToolCall(
        id=tool_call_id,
        name=tool_name,
        arguments="{}",
        origin="completion",
    )

    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = []
    if thinking is not None:
        thinking_blocks = [ThinkingBlock(thinking=thinking)]

    return ActionEvent(
        id=event_id,
        thought=[TextContent(text="Test thought")],
        action=action,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_call=tool_call,
        llm_response_id=llm_response_id,
        thinking_blocks=thinking_blocks,
        source="agent",
    )


def create_observation_event(
    event_id: str,
    tool_call_id: str,
    tool_name: str = "test_tool",
    content: str = "Success",
) -> ObservationEvent:
    """创建 ObservationEvent 的帮助程序。"""
    observation = MCPToolObservation.from_text(
        text=content,
        tool_name=tool_name,
    )
    return ObservationEvent(
        id=event_id,
        observation=observation,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        action_id="action_event_id",
        source="environment",
    )


def create_message_event(event_id: str, content: str) -> MessageEvent:
    """创建非工具循环事件的帮助程序 (MessageEvent)。"""
    return MessageEvent(
        id=event_id,
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


def message_event(content: str) -> MessageEvent:
    """创建 MessageEvent 的帮助程序。"""
    return MessageEvent(
        llm_message=Message(role="user", content=[TextContent(text=content)]),
        source="user",
    )


def create_action_event_with_none_action(
    event_id: str,
    llm_response_id: str,
    tool_call_id: str,
    tool_name: str = "missing_tool",
) -> ActionEvent:
    """使用 action=None 创建 ActionEvent 的帮助程序（未执行操作）。

    这用于测试未执行操作（e.g.，未找到工具）但仍有匹配的观测结果（e.g.，
    AgentErrorEvent）的情况。
    """
    tool_call = MessageToolCall(
        id=tool_call_id,
        name=tool_name,
        arguments="{}",
        origin="completion",
    )

    return ActionEvent(
        id=event_id,
        thought=[TextContent(text="Test thought")],
        action=None,  # 动作没有被执行
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_call=tool_call,
        llm_response_id=llm_response_id,
        source="agent",
    )
