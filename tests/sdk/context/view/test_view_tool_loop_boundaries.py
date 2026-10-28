"""测试工具循环感知操作索引。

该模块测试 manipulation_indices 是否正确识别工具循环边界。 工具循环从具有思考块的批处
理开始，并继续执行所有后续批处理，直到遇到非批处理事件。
"""

from openhands.sdk.context.view import View
from tests.sdk.context.view.conftest import (  # noqa: F401
    create_action_event,
    create_observation_event,
    message_event,
)


def test_single_batch_with_thinking():
    """测试带有思维块的单个批次是否形成工具循环。"""
    events = [
        message_event("User message"),
        create_action_event("resp_1", "call_1", thinking="Thinking..."),
        create_observation_event("call_1"),
    ]

    view = View.from_events(events)
    indices = view.manipulation_indices

    # 应该有边界：[0, 1, 3]
    # - 0：在用户消息之前
    # - 1：工具循环之前（动作+观测结果）
    # - 3: 在工具循环之后
    assert indices == {0, 1, 3}


def test_tool_loop_multiple_batches():
    """测试工具循环是否继续进行多个连续批次。"""
    events = [
        message_event("User message"),
        # 工具循环从思考开始
        create_action_event("resp_1", "call_1", thinking="Thinking..."),
        create_observation_event("call_1"),
        # 继续第二批（没有思考）
        create_action_event("resp_2", "call_2"),
        create_observation_event("call_2"),
        # 继续第三批（没有思考）
        create_action_event("resp_3", "call_3"),
        create_observation_event("call_3"),
        # 当我们点击下一条用户消息时，工具循环结束
        message_event("Next user message"),
    ]

    view = View.from_events(events)
    indices = view.manipulation_indices

    # 应该有边界：[0, 1, 7, 8]
    # - 0：在第一条用户消息之前
    # - 1：工具循环之前（所有3批都是一个原子单元）
    # - 7：工具循环之后，第二条用户消息之前
    # - 8：第二条用户消息后
    assert indices == {0, 1, 7, 8}


def test_tool_loop_ends_at_non_batch_event():
    """测试工具循环在遇到非批处理事件时是否结束。"""
    events = [
        message_event("User message 1"),
        # 第一个工具循环
        create_action_event("resp_1", "call_1", thinking="Thinking..."),
        create_observation_event("call_1"),
        create_action_event("resp_2", "call_2"),
        create_observation_event("call_2"),
        # 非批处理事件结束工具循环
        message_event("User message 2"),
        # 第二个工具循环开始
        create_action_event("resp_3", "call_3", thinking="Thinking..."),
        create_observation_event("call_3"),
    ]

    view = View.from_events(events)
    indices = view.manipulation_indices

    # 应该有边界：[0, 1, 5, 6, 8]
    # - 0：在第一条用户消息之前
    # - 1：第一个工具循环之前（批次 1-2）
    # - 5：第一个工具循环之后，第二个用户消息之前
    # - 6：第二个用户消息之后，第二个工具循环之前
    # - 8：第二个工具循环之后
    assert indices == {0, 1, 5, 6, 8}


def test_multiple_separate_tool_loops():
    """测试由用户消息分隔的多个工具循环。"""
    events = [
        message_event("User 1"),
        # 第一个工具循环
        create_action_event("resp_1", "call_1", thinking="Thinking..."),
        create_observation_event("call_1"),
        create_action_event("resp_2", "call_2"),
        create_observation_event("call_2"),
        message_event("User 2"),
        # 第二个工具循环
        create_action_event("resp_3", "call_3", thinking="Thinking..."),
        create_observation_event("call_3"),
        message_event("User 3"),
    ]

    view = View.from_events(events)
    indices = view.manipulation_indices

    # 应该有边界：[0, 1, 5, 6, 8, 9]
    # - 0：在用户1之前
    # - 1：第一个工具循环之前
    # - 5：第一个工具循环之后，用户 2 之前
    # - 6：用户 2 之后，第二个工具循环之前
    # - 8：第二个工具循环之后，用户 3 之前
    # - 9：用户3之后
    assert indices == {0, 1, 5, 6, 8, 9}


def test_parallel_tool_calls_in_tool_loop():
    """测试批次内的并行工具调用是否已正确处理。"""
    events = [
        message_event("User message"),
        # 工具循环以平行工具调用开始
        create_action_event("resp_1", "call_1a", thinking="Thinking..."),
        create_action_event("resp_1", "call_1b"),  # 相同 response_id = 平行
        create_observation_event("call_1a"),
        create_observation_event("call_1b"),
        # 工具循环中的第二批
        create_action_event("resp_2", "call_2"),
        create_observation_event("call_2"),
        message_event("Next user message"),
    ]

    view = View.from_events(events)
    indices = view.manipulation_indices

    # 应该有边界：[0, 1, 7, 8]
    # - 0：在用户消息之前
    # - 1：工具循环之前（包括两个批次）
    # - 7：工具循环之后，下一条用户消息之前
    # - 8：下一条用户消息后
    assert indices == {0, 1, 7, 8}


def test_empty_events():
    """使用空事件列表测试操作索引。"""
    view = View.from_events([])
    indices = view.manipulation_indices
    assert indices == {0}


def test_only_user_messages():
    """仅使用用户消息（无批次）测试操作索引。"""
    events = [
        message_event("User 1"),
        message_event("User 2"),
    ]

    view = View.from_events(events)
    indices = view.manipulation_indices

    # 每条消息都应该有边界
    # - 0：在第一条消息之前
    # - 1：第一条消息之后，第二条消息之前
    # - 2：第二条消息后
    assert list(indices) == [0, 1, 2]
