"""测试 get_agent_final_response 效用函数。"""

from openhands.sdk.conversation.response_utils import get_agent_final_response
from openhands.sdk.event import ActionEvent, MessageEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.tool.builtins.finish import FinishAction


def test_get_agent_final_response_with_finish_action():
    """测试从完成操作中提取最终响应。"""
    # 创建完成操作事件
    finish_action = FinishAction(message="Task completed successfully!")
    tool_call = MessageToolCall(
        id="test-call-id", name="finish", arguments="{}", origin="completion"
    )
    action_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="Finishing the task")],
        action=finish_action,
        tool_name="finish",
        tool_call_id="test-call-id",
        tool_call=tool_call,
        llm_response_id="test-response-id",
    )

    events = [action_event]
    result = get_agent_final_response(events)

    assert result == "Task completed successfully!"


def test_get_agent_final_response_with_message_event():
    """测试从消息事件中提取最终响应。"""
    # 创建消息事件
    message_event = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant", content=[TextContent(text="Here is my response")]
        ),
    )

    events = [message_event]
    result = get_agent_final_response(events)

    assert result == "Here is my response"


def test_get_agent_final_response_with_multiple_events():
    """测试在存在多个事件时提取最终响应。"""
    # 创建多个事件 - 应返回最后一个智能体事件
    user_message = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Hello")]),
    )

    agent_message1 = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant", content=[TextContent(text="First response")]
        ),
    )

    agent_message2 = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant", content=[TextContent(text="Final response")]
        ),
    )

    events = [user_message, agent_message1, agent_message2]
    result = get_agent_final_response(events)

    # 应返回最后一条智能体消息
    assert result == "Final response"


def test_get_agent_final_response_finish_action_takes_precedence():
    """测试完成操作是否优先于消息事件。"""
    # 创建消息事件
    agent_message = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant", content=[TextContent(text="Regular message")]
        ),
    )

    # 创建随后发生的完成操作
    finish_action = FinishAction(message="Finished!")
    tool_call = MessageToolCall(
        id="test-call-id", name="finish", arguments="{}", origin="completion"
    )
    action_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="Done")],
        action=finish_action,
        tool_name="finish",
        tool_call_id="test-call-id",
        tool_call=tool_call,
        llm_response_id="test-response-id",
    )

    events = [agent_message, action_event]
    result = get_agent_final_response(events)

    # 应返回完成操作消息（最后出现）
    assert result == "Finished!"


def test_get_agent_final_response_empty_events():
    """测试空事件列表的处理。"""
    events = []
    result = get_agent_final_response(events)

    assert result == ""


def test_get_agent_final_response_no_agent_events():
    """测试没有智能体事件时的处理。"""
    # 仅创建用户事件
    user_message = MessageEvent(
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Hello")]),
    )

    events = [user_message]
    result = get_agent_final_response(events)

    assert result == ""


def test_get_agent_final_response_with_none_action():
    """使用 None 操作测试完成工具调用的处理。"""
    # 创建一个带有 tool_name="finish" 但 action=None 的操作事件
    tool_call = MessageToolCall(
        id="test-call-id", name="finish", arguments="{}", origin="completion"
    )
    action_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="Trying to finish")],
        action=None,  # 没有可执行的动作
        tool_name="finish",
        tool_call_id="test-call-id",
        tool_call=tool_call,
        llm_response_id="test-response-id",
    )

    events = [action_event]
    result = get_agent_final_response(events)

    # 当操作为 None 时应返回空字符串
    assert result == ""


def test_get_agent_final_response_with_multiple_content_parts():
    """测试提取具有多个内容部分的最终响应。"""
    # 创建具有多个文本内容部分的消息事件
    message_event = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant",
            content=[
                TextContent(text="Part 1. "),
                TextContent(text="Part 2. "),
                TextContent(text="Part 3."),
            ],
        ),
    )

    events = [message_event]
    result = get_agent_final_response(events)

    assert result == "Part 1. Part 2. Part 3."


def test_get_agent_final_response_ignores_non_agent_finish():
    """测试是否忽略来自非智能体源的完成操作。"""
    # 从用户创建完成操作（不应该发生，但测试边缘情况）
    finish_action = FinishAction(message="User finish")
    tool_call = MessageToolCall(
        id="test-call-id", name="finish", arguments="{}", origin="completion"
    )
    action_event = ActionEvent(
        source="user",  # 不是来自智能体
        thought=[TextContent(text="User thought")],
        action=finish_action,
        tool_name="finish",
        tool_call_id="test-call-id",
        tool_call=tool_call,
        llm_response_id="test-response-id",
    )

    # 还添加常规智能体消息
    agent_message = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant", content=[TextContent(text="Agent response")]
        ),
    )

    events = [action_event, agent_message]
    result = get_agent_final_response(events)

    # 应该返回智能体消息，而不是用户完成操作
    assert result == "Agent response"


def test_get_agent_final_response_with_non_finish_action():
    """测试未完成的操作是否被忽略。"""
    # 创建非完成操作事件 (e.g., read_file)
    tool_call = MessageToolCall(
        id="test-call-id", name="read_file", arguments="{}", origin="completion"
    )
    action_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="Reading file")],
        action=None,
        tool_name="read_file",  # 不是结束动作
        tool_call_id="test-call-id",
        tool_call=tool_call,
        llm_response_id="test-response-id",
    )

    # 还添加一条智能体消息
    agent_message = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant", content=[TextContent(text="File contents")]
        ),
    )

    events = [action_event, agent_message]
    result = get_agent_final_response(events)

    # 应返回智能体消息
    assert result == "File contents"
