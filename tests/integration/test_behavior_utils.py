"""测试 behavior_utils 函数。"""

from collections.abc import Sequence

from openhands.sdk.event import ActionEvent
from openhands.sdk.event.base import Event
from openhands.sdk.llm.message import MessageToolCall, TextContent
from tests.integration.behavior_utils import verify_all_actions_have_summary


def _create_action_event(tool_name: str, summary: str | None) -> ActionEvent:
    """帮助程序创建具有给定摘要的 ActionEvent。"""
    return ActionEvent(
        source="agent",
        tool_name=tool_name,
        thought=[TextContent(text="test thought")],
        tool_call_id="test-call-id",
        tool_call=MessageToolCall(
            id="test-id",
            name=tool_name,
            arguments="{}",
            origin="completion",
        ),
        llm_response_id="test-response-id",
        summary=summary,
    )


def test_verify_all_actions_have_summary_all_present():
    """当所有操作都有摘要时，测试验证是否通过。"""
    events: Sequence[Event] = [
        _create_action_event("terminal", "running tests"),
        _create_action_event("file_editor", "editing config file"),
    ]
    success, reason = verify_all_actions_have_summary(list(events))
    assert success is True
    assert "All 2 actions have summaries" in reason


def test_verify_all_actions_have_summary_missing():
    """测试当操作缺少摘要时验证是否失败。"""
    events: Sequence[Event] = [
        _create_action_event("terminal", "running tests"),
        _create_action_event("file_editor", None),
    ]
    success, reason = verify_all_actions_have_summary(list(events))
    assert success is False
    assert "file_editor" in reason


def test_verify_all_actions_have_summary_empty_string():
    """测试当摘要为空字符串时验证失败。"""
    events: Sequence[Event] = [
        _create_action_event("terminal", ""),
    ]
    success, reason = verify_all_actions_have_summary(list(events))
    assert success is False
    assert "terminal" in reason


def test_verify_all_actions_have_summary_whitespace_only():
    """测试当摘要仅是空格时验证失败。"""
    events: Sequence[Event] = [
        _create_action_event("terminal", "   "),
    ]
    success, reason = verify_all_actions_have_summary(list(events))
    assert success is False
    assert "terminal" in reason


def test_verify_all_actions_have_summary_no_actions():
    """当没有动作事件时测试验证是否通过。"""
    events: list[Event] = []
    success, reason = verify_all_actions_have_summary(events)
    assert success is True
    assert "No action events found" in reason
