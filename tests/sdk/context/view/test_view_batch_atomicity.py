"""测试 View.from_events() 中的批次原子性。

该模块测试在上下文压缩期间以原子方式处理多操作批次（来自同一 LLM 响应的多个
ActionEvents）。 这对于像 Claude Sonnet 4.5 这样的扩展思维
模型至关重要，其中思维块必须与其相关的工具调用保持一致。
"""

from openhands.sdk.context.view import View
from openhands.sdk.event.condenser import Condensation
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    ObservationEvent,
)
from openhands.sdk.llm import (
    RedactedThinkingBlock,
    ThinkingBlock,
)
from tests.sdk.context.view.conftest import (  # noqa: F401
    create_action_event,
    create_observation_event,
    message_event,
)


def test_batch_atomicity_partial_batch_forgotten() -> None:
    """测试如果批次中的一个事件被遗忘，则该批次中的所有事件都会被遗忘
    忘记了。

    这模拟了上下文压缩器从一批E44-E47中忘记了E44-E46，只留下E47的场景。 批量原子性逻
    辑应该确保E47也被遗忘，以防止思维块被分离。
    """
    # 根据同一 LLM 响应创建一批 4 个操作
    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = [
        ThinkingBlock(
            type="thinking", thinking="Extended thinking...", signature="sig1"
        )
    ]
    llm_response_id = "response_1"

    action1 = create_action_event(
        llm_response_id, "tool_call_1", thinking_blocks=thinking_blocks
    )
    action2 = create_action_event(llm_response_id, "tool_call_2")
    action3 = create_action_event(llm_response_id, "tool_call_3")
    action4 = create_action_event(llm_response_id, "tool_call_4")

    # 创建匹配观测结果
    obs1 = create_observation_event("tool_call_1")
    obs2 = create_observation_event("tool_call_2")
    obs3 = create_observation_event("tool_call_3")
    obs4 = create_observation_event("tool_call_4")

    # 上下文压缩忘记了前3个动作(E44-E46)，但没有忘记第4个(E47)。这模拟了上下文压缩器在不
    # 考虑批次边界的情况下使用事件索引可能会发生的情况
    #
    events = [
        message_event("User message"),
        action1,
        action2,
        action3,
        action4,
        obs1,
        obs2,
        obs3,
        obs4,
        Condensation(
            forgotten_event_ids={action1.id, action2.id, action3.id},
            llm_response_id="condensation_response_1",
        ),
    ]

    view = View.from_events(events)

    # 批处理原子性应该确保 action4 也被忘记，即使它没有在 forgotten_event_ids 中明确列出
    #
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]

    assert action1.id not in action_ids_in_view
    assert action2.id not in action_ids_in_view
    assert action3.id not in action_ids_in_view
    assert action4.id not in action_ids_in_view, (
        "action4 should be forgotten due to batch atomicity, "
        "even though it wasn't explicitly in forgotten_event_ids"
    )

    # 由于工具调用不匹配，验证观测结果也被过滤掉
    obs_ids_in_view = [e.id for e in view.events if isinstance(e, ObservationEvent)]
    assert len(obs_ids_in_view) == 0


def test_batch_atomicity_complete_batch_forgotten() -> None:
    """测试当批次中的所有事件都被遗忘时，它们都会被删除。"""
    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = [
        ThinkingBlock(
            type="thinking", thinking="Extended thinking...", signature="sig1"
        )
    ]
    llm_response_id = "response_1"

    action1 = create_action_event(
        llm_response_id, "tool_call_1", thinking_blocks=thinking_blocks
    )
    action2 = create_action_event(
        llm_response_id, "tool_call_2", thinking_blocks=thinking_blocks
    )

    obs1 = create_observation_event("tool_call_1")
    obs2 = create_observation_event("tool_call_2")

    events = [
        message_event("User message"),
        action1,
        action2,
        obs1,
        obs2,
        Condensation(
            forgotten_event_ids={action1.id, action2.id},
            llm_response_id="condensation_response_1",
        ),
    ]

    view = View.from_events(events)

    # 这两个动作都应该被忘记
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]
    assert len(action_ids_in_view) == 0

    # 观测结果也应该被过滤掉
    obs_ids_in_view = [e.id for e in view.events if isinstance(e, ObservationEvent)]
    assert len(obs_ids_in_view) == 0


def test_batch_atomicity_no_forgetting_preserves_batch() -> None:
    """测试当批次中没有事件被遗忘时，所有事件都会被保留。"""
    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = [
        ThinkingBlock(
            type="thinking", thinking="Extended thinking...", signature="sig1"
        )
    ]
    llm_response_id = "response_1"

    action1 = create_action_event(
        llm_response_id, "tool_call_1", thinking_blocks=thinking_blocks
    )
    action2 = create_action_event(
        llm_response_id, "tool_call_2", thinking_blocks=thinking_blocks
    )
    action3 = create_action_event(
        llm_response_id, "tool_call_3", thinking_blocks=thinking_blocks
    )

    obs1 = create_observation_event("tool_call_1")
    obs2 = create_observation_event("tool_call_2")
    obs3 = create_observation_event("tool_call_3")

    events = [
        message_event("User message"),
        action1,
        action2,
        action3,
        obs1,
        obs2,
        obs3,
        Condensation(
            forgotten_event_ids=set(), llm_response_id="condensation_response_1"
        ),  # 不要忘记任何事情
    ]

    view = View.from_events(events)

    # 应保留所有操作
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]
    assert action1.id in action_ids_in_view
    assert action2.id in action_ids_in_view
    assert action3.id in action_ids_in_view


def test_batch_atomicity_multiple_batches() -> None:
    """测试批处理原子性是否可以在多个单独的批处理中正常工作。"""
    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = [
        ThinkingBlock(
            type="thinking", thinking="Extended thinking...", signature="sig1"
        )
    ]

    # 第一批
    batch1_id = "response_1"
    action1_1 = create_action_event(
        batch1_id, "tool_call_1", thinking_blocks=thinking_blocks
    )
    action1_2 = create_action_event(
        batch1_id, "tool_call_2", thinking_blocks=thinking_blocks
    )
    obs1_1 = create_observation_event("tool_call_1")
    obs1_2 = create_observation_event("tool_call_2")

    # 第二批
    batch2_id = "response_2"
    action2_1 = create_action_event(
        batch2_id, "tool_call_3", thinking_blocks=thinking_blocks
    )
    action2_2 = create_action_event(
        batch2_id, "tool_call_4", thinking_blocks=thinking_blocks
    )
    obs2_1 = create_observation_event("tool_call_3")
    obs2_2 = create_observation_event("tool_call_4")

    # 只忘记第一批的第一个操作这应该会导致整个第一批被忘记，但不会忘记第二批
    #
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
            forgotten_event_ids={action1_1.id},
            llm_response_id="condensation_response_1",
        ),
    ]

    view = View.from_events(events)

    # 第一批应该被完全遗忘
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]
    assert action1_1.id not in action_ids_in_view
    assert action1_2.id not in action_ids_in_view, (
        "action1_2 should be forgotten due to batch atomicity"
    )

    # 第二批应保存
    assert action2_1.id in action_ids_in_view
    assert action2_2.id in action_ids_in_view


def test_batch_atomicity_single_action_batch() -> None:
    """测试单个操作的批次是否正常工作。"""
    thinking_blocks: list[ThinkingBlock | RedactedThinkingBlock] = [
        ThinkingBlock(
            type="thinking", thinking="Extended thinking...", signature="sig1"
        )
    ]
    llm_response_id = "response_1"

    action = create_action_event(
        llm_response_id, "tool_call_1", thinking_blocks=thinking_blocks
    )
    obs = create_observation_event("tool_call_1")

    events = [
        message_event("User message"),
        action,
        obs,
        Condensation(
            forgotten_event_ids={action.id}, llm_response_id="condensation_response_1"
        ),
    ]

    view = View.from_events(events)

    # 单一动作应该被遗忘
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]
    assert action.id not in action_ids_in_view


def test_batch_atomicity_no_thinking_blocks() -> None:
    """测试即使没有思维块，批处理原子性也能正常工作。

    虽然批处理原子性的动机是保留思维块，但逻辑应该适用于所有多操作批处理。
    """
    llm_response_id = "response_1"

    action1 = create_action_event(llm_response_id, "tool_call_1")
    action2 = create_action_event(llm_response_id, "tool_call_2")
    action3 = create_action_event(llm_response_id, "tool_call_3")

    obs1 = create_observation_event("tool_call_1")
    obs2 = create_observation_event("tool_call_2")
    obs3 = create_observation_event("tool_call_3")

    # 忘记前两个动作
    events = [
        message_event("User message"),
        action1,
        obs1,
        action2,
        obs2,
        action3,
        obs3,
        Condensation(
            forgotten_event_ids={action1.id, action2.id},
            llm_response_id="condensation_response_1",
        ),
    ]

    view = View.from_events(events)

    # 由于原子性，批处理中的所有操作都应该被忘记
    action_ids_in_view = [e.id for e in view.events if isinstance(e, ActionEvent)]
    assert action1.id not in action_ids_in_view
    assert action2.id not in action_ids_in_view
    assert action3.id not in action_ids_in_view, (
        "action3 should be forgotten due to batch atomicity"
    )
