"""当上下文压缩忘记 ObservationEvents 时测试批量原子性。

该测试重现了上下文压缩忘记了 ObservationEvent，导致其对应的 ActionEvent 被
filter_unmatched_tool_calls 过滤掉，但
同一批次中的其他 ActionEvents （同 llm_response_id）也被不过滤掉的 bug。

这打破了 Anthropic API 的要求，即 tool_use 块必须有对应的 tool_result 块。

错误消息：“messages.28：在 toolu_01L5zJ74i3tPdZDVGoMzeMHm 之后发现 `tool_use` id 没有
 `tool_result`
 块。 每个`tool_use`块必须有一个对应的
`tool_result` 阻止下一条消息。”
"""

from openhands.sdk.context.view import View
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    ObservationEvent,
)
from tests.sdk.context.view.conftest import (  # noqa: F401
    create_action_event,
    create_observation_event,
    message_event,
)


def test_batch_atomicity_when_observation_forgotten() -> None:
    """测试如果忘记了 ObservationEvent，则所有 ActionEvents 都在同一个中
    批次也被过滤掉。

    这会重现该错误，其中：
    1. Action1（批次 A）和 Action2（批次 A）在同一批次中
    2. 上下文压缩忘记 Obs1（但不忘记 Action1、Action2 或 Obs2）
    3. Obs1 匹配 Action1，Obs2 匹配 Action2
    4. filter_unmatched_tool_calls 过滤掉 Action1（没有匹配的 Obs1）
    5. 但 Action2 被保留（因为 Obs2 与 Action2 匹配）

    这会破坏 Anthropic API，因为 Action1 和 Action2 最初位于同一 LLM 响应中，而现在
    Action2 是孤立的，没有其批次配合。
    """
    # 根据同一 LLM 响应创建一批 2 个操作
    llm_response_id = "response_1"

    action1 = create_action_event(llm_response_id, "tool_call_1")
    action2 = create_action_event(llm_response_id, "tool_call_2")

    # 创建匹配观测结果
    obs1 = create_observation_event("tool_call_1")
    obs2 = create_observation_event("tool_call_2")

    # 上下文压缩忘记了 obs1（但没有 action1、action2 或 obs2），这模拟了上下文压缩器使用
    # 事件索引而不考虑 action-观测结果对象的情况可能会发生的事情
    #
    events = [
        message_event("User message"),
        action1,
        action2,
        obs1,
        obs2,
        Condensation(
            forgotten_event_ids={obs1.id},
            llm_response_id="condensation_response_1",
        ),
    ]

    view = View.from_events(events)

    # 修复后：action1和action2都应该被过滤掉，因为它们在同一个批次中，并且action1丢失了
    # 它的观测结果
    #
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]

    # action1 应该被过滤掉，因为 obs1 被忘记了
    assert action1.id not in action_ids_in_view, (
        "action1 should be filtered out because its observation (obs1) was forgotten"
    )

    # 由于批处理原子性，action2 应该 ALSO 被过滤掉（即使 obs2 仍然存在）
    #
    assert action2.id not in action_ids_in_view, (
        "action2 should be filtered out due to batch atomicity, "
        "because action1 (in the same batch) was filtered out"
    )

    # obs2 也应该被过滤掉，因为 action2 消失了
    obs_ids_in_view = [e.id for e in view.events if isinstance(e, ObservationEvent)]
    assert obs2.id not in obs_ids_in_view, (
        "obs2 should be filtered out because action2 was filtered out"
    )


def test_batch_atomicity_when_multiple_observations_forgotten() -> None:
    """当多个观测结果被遗忘时测试批次原子性。"""
    llm_response_id = "response_1"

    action1 = create_action_event(llm_response_id, "tool_call_1")
    action2 = create_action_event(llm_response_id, "tool_call_2")
    action3 = create_action_event(llm_response_id, "tool_call_3")

    obs1 = create_observation_event("tool_call_1")
    obs2 = create_observation_event("tool_call_2")
    obs3 = create_observation_event("tool_call_3")

    # 上下文压缩忘记 obs1 和 obs2（但不忘记 obs3）
    events = [
        message_event("User message"),
        action1,
        action2,
        action3,
        obs1,
        obs2,
        obs3,
        Condensation(
            forgotten_event_ids={obs1.id, obs2.id},
            llm_response_id="condensation_response_1",
        ),
    ]

    view = View.from_events(events)

    # 由于批处理原子性，所有操作都应该被过滤掉
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]
    assert action1.id not in action_ids_in_view
    assert action2.id not in action_ids_in_view
    assert action3.id not in action_ids_in_view, (
        "action3 should be filtered out due to batch atomicity"
    )

    # obs3 也应该被过滤掉，因为 action3 已经消失了
    obs_ids_in_view = [e.id for e in view.events if isinstance(e, ObservationEvent)]
    assert obs3.id not in obs_ids_in_view


def test_batch_atomicity_different_batches_independent() -> None:
    """测试批次原子性仅影响同一批次中的事件。"""
    batch1_id = "response_1"
    batch2_id = "response_2"

    # 第一批
    action1_1 = create_action_event(batch1_id, "tool_call_1")
    action1_2 = create_action_event(batch1_id, "tool_call_2")
    obs1_1 = create_observation_event("tool_call_1")
    obs1_2 = create_observation_event("tool_call_2")

    # 第二批
    action2_1 = create_action_event(batch2_id, "tool_call_3")
    action2_2 = create_action_event(batch2_id, "tool_call_4")
    obs2_1 = create_observation_event("tool_call_3")
    obs2_2 = create_observation_event("tool_call_4")

    # 上下文压缩忘记了 obs1_1（仅限第一批）
    events = [
        message_event("User message"),
        action1_1,
        action1_2,
        obs1_1,
        obs1_2,
        message_event("Another message"),
        action2_1,
        action2_2,
        obs2_1,
        obs2_2,
        Condensation(
            forgotten_event_ids={obs1_1.id},
            llm_response_id="condensation_response_1",
        ),
    ]

    view = View.from_events(events)

    # 第一批应完全过滤掉
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]
    assert action1_1.id not in action_ids_in_view
    assert action1_2.id not in action_ids_in_view, (
        "action1_2 should be filtered out due to batch atomicity"
    )

    # 第二批应保留（不同批次）
    assert action2_1.id in action_ids_in_view
    assert action2_2.id in action_ids_in_view


def test_single_action_batch_observation_forgotten() -> None:
    """测试当忘记观测结果时单操作批次是否正常工作。"""
    llm_response_id = "response_1"

    action = create_action_event(llm_response_id, "tool_call_1")
    obs = create_observation_event("tool_call_1")

    # 上下文压缩忘记了观测结果
    events = [
        message_event("User message"),
        action,
        obs,
        Condensation(
            forgotten_event_ids={obs.id},
            llm_response_id="condensation_response_1",
        ),
    ]

    view = View.from_events(events)

    # 应该过滤掉操作，因为它的观测结果被忘记了
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]
    assert action.id not in action_ids_in_view
