"""测试 View.manipulation_indices 属性。

该模块测试缓存属性，该属性用于识别可以安全操作事件（插入新事件或忘记范围）的索引，同
时遵守原子性约束。
"""

from openhands.sdk.context.view import View
from openhands.sdk.llm import (
    ThinkingBlock,
)
from tests.sdk.context.view.conftest import (  # noqa: F401
    create_action_event,
    create_observation_event,
    message_event,
)


def test_empty_list() -> None:
    """使用空事件列表测试 manipulation_indices。"""
    view = View.from_events([])
    assert view.manipulation_indices == {0}


def test_single_message_event() -> None:
    """使用单个消息事件测试 manipulation_indices。"""
    events = [message_event("Event 0")]
    view = View.from_events(events)

    # 在单个消息之前和之后应该有边界
    assert view.manipulation_indices == {0, 1}


def test_multiple_message_events() -> None:
    """使用多个消息事件测试 manipulation_indices。"""
    events = [
        message_event("Event 0"),
        message_event("Event 1"),
        message_event("Event 2"),
    ]
    view = View.from_events(events)

    # 每条消息都是它自己的原子单元，因此它们之间存在边界
    assert view.manipulation_indices == {0, 1, 2, 3}


def test_single_action_observation_pair() -> None:
    """使用单个操作-观测结果对测试 manipulation_indices。"""
    action = create_action_event("response_1", "tool_call_1")
    obs = create_observation_event("tool_call_1")

    events = [action, obs]
    indices = View.from_events(events).manipulation_indices

    # 该对是一个原子单元，因此边界仅在开始和结束处
    assert indices == {0, 2}


def test_action_observation_with_message_events() -> None:
    """使用围绕操作观测结果的消息事件测试操作索引。"""
    msg1 = message_event("Before")
    action = create_action_event("response_1", "tool_call_1")
    obs = create_observation_event("tool_call_1")
    msg2 = message_event("After")

    events = [msg1, action, obs, msg2]
    indices = View.from_events(events).manipulation_indices

    # 边界：[0 msg1 1（操作+obs）3 msg2 4]
    assert indices == {0, 1, 3, 4}


def test_batch_of_actions_simple() -> None:
    """使用来自相同 LLM 响应的一批操作来测试操纵指数。"""
    thinking = [
        ThinkingBlock(type="thinking", thinking="Thinking...", signature="sig1")
    ]

    action1 = create_action_event("response_1", "tool_call_1", thinking_blocks=thinking)
    action2 = create_action_event("response_1", "tool_call_2")
    action3 = create_action_event("response_1", "tool_call_3")

    obs1 = create_observation_event("tool_call_1")
    obs2 = create_observation_event("tool_call_2")
    obs3 = create_observation_event("tool_call_3")

    events = [action1, action2, action3, obs1, obs2, obs3]
    indices = View.from_events(events).manipulation_indices

    # 所有动作都是同一批次的一部分，并且观测结果扩展了范围整个批次（动作 + 观测结果）是
    # 一个原子单元
    #
    assert indices == {0, 6}


def test_multiple_separate_batches() -> None:
    """使用多个单独的操作批次测试操作指数。"""
    # 第一批
    action1_1 = create_action_event("response_1", "tool_call_1")
    action1_2 = create_action_event("response_1", "tool_call_2")
    obs1_1 = create_observation_event("tool_call_1")
    obs1_2 = create_observation_event("tool_call_2")

    # 第二批
    action2_1 = create_action_event("response_2", "tool_call_3")
    action2_2 = create_action_event("response_2", "tool_call_4")
    obs2_1 = create_observation_event("tool_call_3")
    obs2_2 = create_observation_event("tool_call_4")

    events = [
        action1_1,
        action1_2,
        obs1_1,
        obs1_2,
        action2_1,
        action2_2,
        obs2_1,
        obs2_2,
    ]
    indices = View.from_events(events).manipulation_indices

    # 两个原子单元：batch1（索引0-3）和batch2（索引4-7）
    assert indices == {0, 4, 8}


def test_batches_separated_by_messages() -> None:
    """使用操作批次之间的消息测试操作索引。"""
    msg1 = message_event("Start")

    action1 = create_action_event("response_1", "tool_call_1")
    action2 = create_action_event("response_1", "tool_call_2")
    obs1 = create_observation_event("tool_call_1")
    obs2 = create_observation_event("tool_call_2")

    msg2 = message_event("Middle")

    action3 = create_action_event("response_2", "tool_call_3")
    obs3 = create_observation_event("tool_call_3")

    msg3 = message_event("End")

    events = [msg1, action1, action2, obs1, obs2, msg2, action3, obs3, msg3]
    indices = View.from_events(events).manipulation_indices

    # [0 msg1 1 (batch1: action1,action2,obs1,obs2) 5 msg2 6 (batch2) 8 msg3 9]
    assert indices == {0, 1, 5, 6, 8, 9}


def test_single_action_in_batch() -> None:
    """使用仅包含一个操作的批次测试操作指数。"""
    action = create_action_event("response_1", "tool_call_1")
    obs = create_observation_event("tool_call_1")

    events = [action, obs]
    indices = View.from_events(events).manipulation_indices

    # 单动作批次仍然是原子单元
    assert indices == {0, 2}


def test_complex_interleaved_scenario() -> None:
    """测试具有多种事件类型交错的复杂场景。"""
    msg1 = message_event("Message 1")

    # Batch 1: 2 actions
    action1_1 = create_action_event("response_1", "call_1")
    action1_2 = create_action_event("response_1", "call_2")
    obs1_1 = create_observation_event("call_1")

    msg2 = message_event("Message 2")

    obs1_2 = create_observation_event("call_2")  # 观测结果来晚了

    msg3 = message_event("Message 3")

    # 第 2 批：1 次行动
    action2 = create_action_event("response_2", "call_3")
    obs2 = create_observation_event("call_3")

    events = [
        msg1,
        action1_1,
        action1_2,
        obs1_1,
        msg2,
        obs1_2,
        msg3,
        action2,
        obs2,
    ]
    indices = View.from_events(events).manipulation_indices

    # 消息 1: [0, 1]
    # 批次1 (action1_1, action1_2, obs1_1, msg2, obs1_2): [1, 6]
    # 消息 3：[6、7]
    # 批次2（操作2，obs2）：[7，9]
    #
    # 等等 - msg2 在批次之间，但它是一个独立的原子单元。实际上，批次1 跨越了索引 1-5 (
    # action1_1, action1_2, obs1_1, -, obs1_2)，但在索引 4 处有一个消息
    #
    # 我们重新计算一下：
    # 0：msg1（原子单元）
    # 1：action1_1（batch1的一部分）
    # 2：action1_2（batch1的一部分）
    # 3：obs1_1（batch1的一部分）
    # 4：msg2（原子单位，但检查它是否在批次范围内）
    # 5：obs1_2（batch1的一部分，扩展范围）
    # 6：msg3（原子单元）
    # 7：action2（batch2的一部分）
    # 8：obs2（batch2的一部分）
    #
    # 批次1范围：min(1,2)=1，观测结果之后的最大值为max(2, 5)=5。但是，msg2在索引4处位于1
    # 和5之间
    #
    # 预期：[0、1、6、7、9]
    # - 0：在msg1之前
    # - 1：msg1之后，batch1之前
    # - 6：batch1 之后（包括索引 1-5），msg3 之前
    # - 7：msg3之后，batch2之前
    # - 9：第2批之后

    assert indices == {0, 1, 6, 7, 9}


def test_observations_extend_batch_range() -> None:
    """测试观测结果扩展批次的原子单元范围。"""
    action1 = create_action_event("response_1", "call_1")
    action2 = create_action_event("response_1", "call_2")

    msg = message_event("Middle")

    obs1 = create_observation_event("call_1")
    obs2 = create_observation_event("call_2")

    events = [action1, action2, msg, obs1, obs2]
    indices = View.from_events(events).manipulation_indices

    # 批次包括操作 0-1 和观测结果 3-4 2 处的消息属于批次范围，因此被视为批次范围的一部分
    # 范围：最小值=0，最大值=4
    assert indices == {0, 5}


def test_batch_with_all_observations() -> None:
    """当所有操作都匹配观测结果时测试批次边界。

    Note: 实际上，from_events() 过滤掉不匹配的操作，所以这
    测试批次中所有操作都有观测结果的实际场景。
    """
    action1 = create_action_event("response_1", "call_1")
    action2 = create_action_event("response_1", "call_2")
    obs1 = create_observation_event("call_1")
    obs2 = create_observation_event("call_2")

    events = [action1, action2, obs1, obs2]
    view = View.from_events(events)
    indices = view.manipulation_indices

    # 批次是一个包含两个 action-观测结果对的原子单元
    assert indices == {0, 4}


def test_interleaved_batches_and_messages() -> None:
    """测试批次和消息的交替模式。"""
    msg1 = message_event("Msg 1")

    action1 = create_action_event("response_1", "call_1")
    obs1 = create_observation_event("call_1")

    msg2 = message_event("Msg 2")

    action2 = create_action_event("response_2", "call_2")
    obs2 = create_observation_event("call_2")

    msg3 = message_event("Msg 3")

    events = [msg1, action1, obs1, msg2, action2, obs2, msg3]
    indices = View.from_events(events).manipulation_indices

    # [0 msg1 1 batch1 3 msg2 4 batch2 6 msg3 7]
    assert indices == {0, 1, 3, 4, 6, 7}


def test_three_action_batch() -> None:
    """使用三个并行操作测试批次。"""
    action1 = create_action_event("response_1", "call_1")
    action2 = create_action_event("response_1", "call_2")
    action3 = create_action_event("response_1", "call_3")

    obs1 = create_observation_event("call_1")
    obs2 = create_observation_event("call_2")
    obs3 = create_observation_event("call_3")

    events = [action1, action2, action3, obs1, obs2, obs3]
    indices = View.from_events(events).manipulation_indices

    # 一批的所有部分
    assert indices == {0, 6}


def test_consecutive_atomic_units() -> None:
    """测试连续索引是否正确定义原子单位。"""
    msg1 = message_event("Msg 1")
    msg2 = message_event("Msg 2")

    action = create_action_event("response_1", "call_1")
    obs = create_observation_event("call_1")

    msg3 = message_event("Msg 3")

    events = [msg1, msg2, action, obs, msg3]
    indices = View.from_events(events).manipulation_indices

    # [0 msg1 1 msg2 2 batch 4 msg3 5]
    assert indices == {0, 1, 2, 4, 5}

    # 验证原子单位：事件[0:1] = [msg1] events[1:2] = [msg2] events[2:4] = [action, obs]
    # events[4:5] = [msg3]
    #


def test_forgetting_range_selection() -> None:
    """测试连续索引之间的范围可以被安全地遗忘。"""
    msg1 = message_event("Keep")

    action1 = create_action_event("response_1", "call_1")
    action2 = create_action_event("response_1", "call_2")
    obs1 = create_observation_event("call_1")
    obs2 = create_observation_event("call_2")

    msg2 = message_event("Keep")

    events = [msg1, action1, action2, obs1, obs2, msg2]
    indices = View.from_events(events).manipulation_indices

    # [0 msg1 1 batch 5 msg2 6]
    assert indices == {0, 1, 5, 6}
