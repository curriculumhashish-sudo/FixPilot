"""测试 View 中的多摘要支持。

该模块测试视图系统处理多个CondensationSummaryEvents的能力，包括在后续浓缩中忘记先前摘
要的能力。

测试的关键行为：
- 多个摘要可以共存于同一视图中
- 摘要可能会被单独或成组地遗忘
- 摘要偏移可以与多个摘要一起正确工作
- 摘要在视图重建中具有稳定的标识符
- 与事件遗忘整合
- 向后兼容性具有现有的摘要属性
"""

from openhands.sdk.context.view import View
from openhands.sdk.event import Condensation, CondensationSummaryEvent
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm import TextContent
from tests.sdk.context.view.conftest import message_event  # noqa: F401


# ==============================================================================
# 第一类：多重摘要共存
# ==============================================================================


def test_multiple_summaries_at_different_offsets() -> None:
    """测试来自不同压缩的两个摘要是否可以在视图中共存。

    场景：
    - 第一个上下文压缩：忘记事件 0，在偏移量 0 处添加摘要
    - 第二个上下文压缩：忘记事件 2，在偏移量 2 处添加摘要
    - 两个摘要都应以指定的偏移量出现在最终视图中
    """
    message_events = [message_event(f"Event {i}") for i in range(5)]

    condensation1 = Condensation(
        id="condensation-1",
        forgotten_event_ids={message_events[0].id},
        summary="Summary of event 0",
        summary_offset=0,
        llm_response_id="condensation_1",
    )

    condensation2 = Condensation(
        id="condensation-2",
        forgotten_event_ids={message_events[2].id},
        summary="Summary of event 2",
        summary_offset=2,
        llm_response_id="condensation_2",
    )

    events = [
        message_events[0],
        message_events[1],
        condensation1,
        message_events[2],
        message_events[3],
        condensation2,
        message_events[4],
    ]

    view = View.from_events(events)

    # 查找视图中所有CondensationSummaryEvents
    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 2, "Both summaries should be present in view"

    # 验证第一个摘要位于偏移量 0 处
    assert isinstance(view.events[0], CondensationSummaryEvent)
    assert view.events[0].summary == "Summary of event 0"

    # 验证第二个摘要位于偏移量 2 处
    assert isinstance(view.events[2], CondensationSummaryEvent)
    assert view.events[2].summary == "Summary of event 2"


def test_multiple_summaries_from_sequential_condensations() -> None:
    """测试三个缩合，每个缩合在不同位置添加摘要。

    这测试了按顺序处理压缩时摘要的累积情况。
    """
    message_events = [message_event(f"Event {i}") for i in range(6)]

    condensation1 = Condensation(
        id="condensation-1",
        forgotten_event_ids=set(),
        summary="First summary",
        summary_offset=0,
        llm_response_id="condensation_1",
    )

    condensation2 = Condensation(
        id="condensation-2",
        forgotten_event_ids=set(),
        summary="Second summary",
        summary_offset=3,
        llm_response_id="condensation_2",
    )

    condensation3 = Condensation(
        id="condensation-3",
        forgotten_event_ids=set(),
        summary="Third summary",
        summary_offset=5,
        llm_response_id="condensation_3",
    )

    events = [
        message_events[0],
        condensation1,
        message_events[1],
        message_events[2],
        condensation2,
        message_events[3],
        condensation3,
        message_events[4],
        message_events[5],
    ]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 3, "All three summaries should be present"

    # 验证每个摘要是否位于其指定的偏移量
    assert isinstance(view.events[0], CondensationSummaryEvent)
    assert view.events[0].summary == "First summary"

    assert isinstance(view.events[3], CondensationSummaryEvent)
    assert view.events[3].summary == "Second summary"

    assert isinstance(view.events[5], CondensationSummaryEvent)
    assert view.events[5].summary == "Third summary"


def test_summaries_preserve_order_and_content() -> None:
    """测试多个摘要是否正确保持其顺序和内容。

    验证摘要不会相互干扰，并且每个摘要都保持自己的内容和位置。
    """
    messages = [message_event(f"Msg {i}") for i in range(4)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids={messages[0].id},
        summary="Summary A",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids={messages[2].id},
        summary="Summary B",
        summary_offset=2,
        llm_response_id="cond_2",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        messages[2],
        condensation2,
        messages[3],
    ]

    view = View.from_events(events)

    # 事件 0 被遗忘，事件 2 被遗忘
    # 预期：[摘要 A、消息 1、摘要 B、消息 3]
    assert len(view.events) == 4

    assert isinstance(view.events[0], CondensationSummaryEvent)
    assert view.events[0].summary == "Summary A"

    assert isinstance(view.events[1], MessageEvent)
    assert isinstance(view.events[1].llm_message.content[0], TextContent)
    assert view.events[1].llm_message.content[0].text == "Msg 1"

    assert isinstance(view.events[2], CondensationSummaryEvent)
    assert view.events[2].summary == "Summary B"

    assert isinstance(view.events[3], MessageEvent)
    assert isinstance(view.events[3].llm_message.content[0], TextContent)
    assert view.events[3].llm_message.content[0].text == "Msg 3"


# ==============================================================================
# 第二类：忘记个人总结
# ==============================================================================


def test_forget_first_summary_keeps_second() -> None:
    """测试忘记第一个摘要是否会保留第二个摘要。

    场景：
    - 上下文压缩 1：添加摘要 A
    - 上下文压缩 2：添加摘要 B
    - 上下文压缩 3：忘记摘要 A
    - Result: 只剩下摘要B
    """
    messages = [message_event(f"Msg {i}") for i in range(3)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Summary A",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Summary B",
        summary_offset=2,
        llm_response_id="cond_2",
    )

    # 为了忘记摘要 A，我们需要它的事件 ID。 使用确定性 ID 方法：
    # summary_id = f"{condensation_id}_summary"
    summary_a_id = "cond-1-summary"

    condensation3 = Condensation(
        id="cond-3",
        forgotten_event_ids={summary_a_id},
        summary=None,
        summary_offset=None,
        llm_response_id="cond_3",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        condensation2,
        messages[2],
        condensation3,
    ]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 1, "Only summary B should remain"
    assert summary_events[0].summary == "Summary B"


def test_forget_middle_summary_keeps_others() -> None:
    """测试忘记中间摘要，同时保留第一个和最后一个摘要。

    场景：
    - 三个总结A、B、C
    - 忘记B
    - A 和 C 仍然存在
    """
    messages = [message_event(f"Msg {i}") for i in range(4)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Summary A",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Summary B",
        summary_offset=2,
        llm_response_id="cond_2",
    )

    condensation3 = Condensation(
        id="cond-3",
        forgotten_event_ids=set(),
        summary="Summary C",
        summary_offset=4,
        llm_response_id="cond_3",
    )

    summary_b_id = "cond-2-summary"

    condensation4 = Condensation(
        id="cond-4",
        forgotten_event_ids={summary_b_id},
        summary=None,
        llm_response_id="cond_4",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        condensation2,
        messages[2],
        condensation3,
        messages[3],
        condensation4,
    ]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 2, "Summaries A and C should remain"

    summaries_text = [s.summary for s in summary_events]
    assert "Summary A" in summaries_text
    assert "Summary C" in summaries_text
    assert "Summary B" not in summaries_text


def test_forget_most_recent_summary() -> None:
    """测试忘记最近添加的摘要。

    验证可以忘记新的摘要，而不仅仅是旧的摘要。
    """
    messages = [message_event(f"Msg {i}") for i in range(2)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Summary A",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Summary B",
        summary_offset=1,
        llm_response_id="cond_2",
    )

    summary_b_id = "cond-2-summary"

    condensation3 = Condensation(
        id="cond-3",
        forgotten_event_ids={summary_b_id},
        summary=None,
        llm_response_id="cond_3",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        condensation2,
        condensation3,
    ]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 1, "Only summary A should remain"
    assert summary_events[0].summary == "Summary A"


def test_forget_summary_adjusts_later_summary_positions() -> None:
    """测试忘记摘要是否可以正确调整后续摘要的位置。

    当忘记摘要时，其后的事件索引将向下移动 1。
    """
    messages = [message_event(f"Msg {i}") for i in range(3)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Summary at position 0",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Summary at position 2",
        summary_offset=2,
        llm_response_id="cond_2",
    )

    summary_1_id = "cond-1-summary"

    condensation3 = Condensation(
        id="cond-3",
        forgotten_event_ids={summary_1_id},
        summary=None,
        llm_response_id="cond_3",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        condensation2,
        messages[2],
        condensation3,
    ]

    view = View.from_events(events)

    # 忘记第一个摘要后：[Msg 0，摘要位于位置 2，Msg 1，Msg 2] 第二个摘要现在应位于索引 1
    #
    assert isinstance(view.events[1], CondensationSummaryEvent)
    assert view.events[1].summary == "Summary at position 2"


# ==============================================================================
# 第 3 类：忘记多重摘要
# ==============================================================================


def test_forget_multiple_summaries_simultaneously() -> None:
    """测试单个上下文压缩一次忘记多个摘要。

    场景：
    - 存在三个摘要
    - 一上下文压缩忘记了其中两个
    - 只剩下一份总结
    """
    messages = [message_event(f"Msg {i}") for i in range(4)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Summary A",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Summary B",
        summary_offset=2,
        llm_response_id="cond_2",
    )

    condensation3 = Condensation(
        id="cond-3",
        forgotten_event_ids=set(),
        summary="Summary C",
        summary_offset=4,
        llm_response_id="cond_3",
    )

    summary_a_id = "cond-1-summary"
    summary_c_id = "cond-3-summary"

    condensation4 = Condensation(
        id="cond-4",
        forgotten_event_ids={summary_a_id, summary_c_id},
        summary=None,
        llm_response_id="cond_4",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        condensation2,
        messages[2],
        condensation3,
        messages[3],
        condensation4,
    ]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 1, "Only summary B should remain"
    assert summary_events[0].summary == "Summary B"


def test_forget_all_summaries() -> None:
    """测试忘记视图中的所有摘要。

    忘记所有摘要后，视图应仅包含消息事件。
    """
    messages = [message_event(f"Msg {i}") for i in range(3)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Summary A",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Summary B",
        summary_offset=2,
        llm_response_id="cond_2",
    )

    summary_a_id = "cond-1-summary"
    summary_b_id = "cond-2-summary"

    condensation3 = Condensation(
        id="cond-3",
        forgotten_event_ids={summary_a_id, summary_b_id},
        summary=None,
        llm_response_id="cond_3",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        condensation2,
        messages[2],
        condensation3,
    ]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 0, "No summaries should remain"
    assert len(view.events) == 3, "Only message events should remain"


def test_sequential_condensations_each_forget_summary() -> None:
    """测试多次凝结，每次都忘记一个总结。

    场景：
    - 创建 3 个摘要
    - 上下文压缩 4 忘记摘要 1
    - 上下文压缩 5 忘记摘要 2
    - 只剩下摘要3
    """
    messages = [message_event(f"Msg {i}") for i in range(4)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Summary 1",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Summary 2",
        summary_offset=2,
        llm_response_id="cond_2",
    )

    condensation3 = Condensation(
        id="cond-3",
        forgotten_event_ids=set(),
        summary="Summary 3",
        summary_offset=4,
        llm_response_id="cond_3",
    )

    summary_1_id = "cond-1-summary"
    summary_2_id = "cond-2-summary"

    condensation4 = Condensation(
        id="cond-4",
        forgotten_event_ids={summary_1_id},
        summary=None,
        llm_response_id="cond_4",
    )

    condensation5 = Condensation(
        id="cond-5",
        forgotten_event_ids={summary_2_id},
        summary=None,
        llm_response_id="cond_5",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        condensation2,
        messages[2],
        condensation3,
        messages[3],
        condensation4,
        condensation5,
    ]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 1, "Only summary 3 should remain"
    assert summary_events[0].summary == "Summary 3"


# ==============================================================================
# 第四类：概要识别机制
# ==============================================================================


def test_summary_events_have_stable_identifiers() -> None:
    """测试摘要事件 ID 在视图重建中是否稳定。

    这是核心要求：如果我们使用相同的输入事件构造相同的视图两次，则摘要事件两次应该具
    有相同的 ID。
    """
    messages = [message_event(f"Msg {i}") for i in range(2)]

    condensation1 = Condensation(
        id="stable-condensation",
        forgotten_event_ids=set(),
        summary="Stable summary",
        summary_offset=0,
        llm_response_id="stable_condensation",
    )

    events = [messages[0], condensation1, messages[1]]

    # 第一次构建视图
    view1 = View.from_events(events)
    summary1 = [e for e in view1.events if isinstance(e, CondensationSummaryEvent)][0]

    # 使用相同事件第二次构造视图
    view2 = View.from_events(events)
    summary2 = [e for e in view2.events if isinstance(e, CondensationSummaryEvent)][0]

    assert summary1.id == summary2.id, (
        "Summary event ID should be stable across reconstructions"
    )

    # 验证 ID 是否符合预期模式
    expected_id = "stable-condensation-summary"
    assert summary1.id == expected_id, f"Summary ID should be {expected_id}"


def test_condensation_tracks_its_summary_event() -> None:
    """测试我们是否可以确定哪个上下文压缩创建了哪个摘要。

    这可能是通过 ID 约定或显式跟踪来实现的。
    """
    messages = [message_event(f"Msg {i}") for i in range(3)]

    condensation1 = Condensation(
        id="cond-A",
        forgotten_event_ids=set(),
        summary="First",
        summary_offset=0,
        llm_response_id="cond_A",
    )

    condensation2 = Condensation(
        id="cond-B",
        forgotten_event_ids=set(),
        summary="Second",
        summary_offset=2,
        llm_response_id="cond_B",
    )

    events = [
        messages[0],
        condensation1,
        messages[1],
        condensation2,
        messages[2],
    ]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    # 验证我们可以识别哪个摘要来自哪个上下文压缩
    summary_1 = [s for s in summary_events if s.summary == "First"][0]
    summary_2 = [s for s in summary_events if s.summary == "Second"][0]

    assert summary_1.id == "cond-A-summary"
    assert summary_2.id == "cond-B-summary"


def test_can_reference_summary_from_previous_condensation() -> None:
    """测试核心用例：引用早期上下文压缩创建的摘要。

    这验证了识别机制可以忘记摘要。
    """
    messages = [message_event(f"Msg {i}") for i in range(2)]

    # 首先上下文压缩创建一个摘要
    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="To be forgotten",
        summary_offset=0,
        llm_response_id="cond_original",
    )

    events_before_forgetting = [messages[0], condensation1, messages[1]]
    view_before = View.from_events(events_before_forgetting)

    # 查找摘要的 ID
    summary_event = [
        e for e in view_before.events if isinstance(e, CondensationSummaryEvent)
    ][0]
    summary_id = summary_event.id

    # 第二个上下文压缩引用并忘记了摘要
    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids={summary_id},
        summary="New summary",
        summary_offset=0,
        llm_response_id="cond_new",
    )

    events_after_forgetting = [messages[0], condensation1, messages[1], condensation2]
    view_after = View.from_events(events_after_forgetting)

    summary_events = [
        e for e in view_after.events if isinstance(e, CondensationSummaryEvent)
    ]

    # 旧的摘要应该消失，新的摘要应该出现
    assert len(summary_events) == 1
    assert summary_events[0].summary == "New summary"


# ==============================================================================
# 类别 5：偏移行为
# ==============================================================================


def test_summary_offset_is_absolute_in_final_view() -> None:
    """测试 summary_offset 是否指最终视图中的绝对位置。

    事件被遗忘后，偏移量应将摘要放置在结果事件列表中的确切索引处。
    """
    messages = [message_event(f"Msg {i}") for i in range(5)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids={messages[0].id, messages[1].id},
        summary="Summary at offset 1",
        summary_offset=1,
        llm_response_id="cond_1",
    )

    events = [
        messages[0],
        messages[1],
        messages[2],
        condensation1,
        messages[3],
        messages[4],
    ]

    view = View.from_events(events)

    # 忘记事件 0 和 1 后：[Msg 2、Msg 3、Msg 4] 偏移量 1 处的摘要应位于 Msg 2 和 Msg 3
    # 之间
    # 预期：[消息 2、摘要、消息 3、消息 4]

    assert len(view.events) == 4
    assert isinstance(view.events[0], MessageEvent)
    assert isinstance(view.events[0].llm_message.content[0], TextContent)
    assert view.events[0].llm_message.content[0].text == "Msg 2"

    assert isinstance(view.events[1], CondensationSummaryEvent)
    assert view.events[1].summary == "Summary at offset 1"

    assert isinstance(view.events[2], MessageEvent)
    assert isinstance(view.events[2].llm_message.content[0], TextContent)
    assert view.events[2].llm_message.content[0].text == "Msg 3"


def test_summary_offset_zero_inserts_at_beginning() -> None:
    """测试 offset=0 是否在视图的最开头插入摘要。"""
    messages = [message_event(f"Msg {i}") for i in range(3)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="At the start",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    events = [messages[0], condensation1, messages[1], messages[2]]

    view = View.from_events(events)

    assert isinstance(view.events[0], CondensationSummaryEvent)
    assert view.events[0].summary == "At the start"


def test_summary_offset_at_end_of_events() -> None:
    """测试摘要是否可以插入到事件列表的末尾。"""
    messages = [message_event(f"Msg {i}") for i in range(3)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="At the end",
        summary_offset=3,  # 所有3条消息
        llm_response_id="cond_1",
    )

    events = [messages[0], messages[1], messages[2], condensation1]

    view = View.from_events(events)

    assert len(view.events) == 4
    assert isinstance(view.events[3], CondensationSummaryEvent)
    assert view.events[3].summary == "At the end"


def test_multiple_summaries_with_same_offset() -> None:
    """测试多个摘要具有相同偏移量时的行为。

    这是测试系统如何处理偏移冲突的边缘情况。
    Expected: 摘要按照创建顺序插入。
    """
    messages = [message_event(f"Msg {i}") for i in range(2)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="First at offset 1",
        summary_offset=1,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Second at offset 1",
        summary_offset=1,
        llm_response_id="cond_2",
    )

    events = [messages[0], condensation1, condensation2, messages[1]]

    view = View.from_events(events)

    # 两个摘要都应该在视图中
    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]
    assert len(summary_events) == 2

    # 当以相同的偏移量插入时，后面的插入出现在前面的插入之前（标准 list.insert() 行为）
    #
    summaries_in_order = [s.summary for s in summary_events]
    assert summaries_in_order[0] == "Second at offset 1"
    assert summaries_in_order[1] == "First at offset 1"


# ==============================================================================
# 第 6 类：与事件遗忘的整合
# ==============================================================================


def test_forget_events_and_summary_together() -> None:
    """测试一个忘记常规事件和摘要的上下文压缩。

    验证摘要是否可以与同一上下文压缩中的常规事件一起被遗忘。
    """
    messages = [message_event(f"Msg {i}") for i in range(4)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Old summary",
        summary_offset=1,
        llm_response_id="cond_1",
    )

    old_summary_id = "cond-1-summary"

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids={messages[0].id, messages[2].id, old_summary_id},
        summary="New summary",
        summary_offset=0,
        llm_response_id="cond_2",
    )

    events = [
        messages[0],
        messages[1],
        condensation1,
        messages[2],
        messages[3],
        condensation2,
    ]

    view = View.from_events(events)

    # 应该忘记：Msg 0、Msg 2、旧摘要应保留：Msg 1、Msg 3、新摘要
    #
    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 1
    assert summary_events[0].summary == "New summary"

    message_events_in_view = [e for e in view.events if isinstance(e, MessageEvent)]
    assert len(message_events_in_view) == 2


def test_summary_offset_remains_valid_after_forgetting_events() -> None:
    """测试当之前的事件被遗忘时，摘要偏移是否正常工作。

    当删除较早的事件时，摘要偏移量仍应将摘要放置在结果视图中的正确位置。
    """
    messages = [message_event(f"Msg {i}") for i in range(5)]

    # 忘记前两条消息，在偏移量 2 处添加摘要
    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids={messages[0].id, messages[1].id},
        summary="Summary after forgetting",
        summary_offset=2,
        llm_response_id="cond_1",
    )

    events = [
        messages[0],
        messages[1],
        messages[2],
        messages[3],
        condensation1,
        messages[4],
    ]

    view = View.from_events(events)

    # 忘记后：[Msg 2、Msg 3、Msg 4] 偏移量 2 处的摘要应位于 Msg 3 之后
    # 预期：[消息 2、消息 3、摘要、消息 4]

    assert len(view.events) == 4
    assert isinstance(view.events[2], CondensationSummaryEvent)
    assert view.events[2].summary == "Summary after forgetting"


def test_interleaved_events_and_summaries() -> None:
    """测试事件和摘要交错的复杂场景。

    场景：
    - 消息和摘要交错
    - 有些消息忘记了
    - 验证最终视图具有正确的结构
    """
    messages = [message_event(f"Msg {i}") for i in range(6)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids={messages[1].id},
        summary="Summary A",
        summary_offset=1,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids={messages[3].id},
        summary="Summary B",
        summary_offset=3,
        llm_response_id="cond_2",
    )

    events = [
        messages[0],
        messages[1],
        condensation1,
        messages[2],
        messages[3],
        condensation2,
        messages[4],
        messages[5],
    ]

    view = View.from_events(events)

    # 消息 1 和 3 被遗忘
    # 剩余：消息 0、消息 2、消息 4、消息 5 + 摘要 A、摘要 B
    # 预期：[消息 0、摘要 A、消息 2、摘要 B、消息 4、消息 5]

    assert len(view.events) == 6

    assert isinstance(view.events[0], MessageEvent)
    assert isinstance(view.events[0].llm_message.content[0], TextContent)
    assert view.events[0].llm_message.content[0].text == "Msg 0"

    assert isinstance(view.events[1], CondensationSummaryEvent)
    assert view.events[1].summary == "Summary A"

    assert isinstance(view.events[2], MessageEvent)
    assert isinstance(view.events[2].llm_message.content[0], TextContent)
    assert view.events[2].llm_message.content[0].text == "Msg 2"

    assert isinstance(view.events[3], CondensationSummaryEvent)
    assert view.events[3].summary == "Summary B"


# ==============================================================================
# 第 7 类：边缘案例
# ==============================================================================


def test_condensation_without_summary_no_summary_event_created() -> None:
    """测试没有摘要的压缩不会创建摘要事件。

    并非所有凝结都有摘要 - 验证这是否仍然有效。
    """
    messages = [message_event(f"Msg {i}") for i in range(3)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids={messages[1].id},
        summary=None,  # 无摘要
        summary_offset=None,
        llm_response_id="cond_1",
    )

    events = [messages[0], messages[1], condensation1, messages[2]]

    view = View.from_events(events)

    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 0, "No summary should be created"
    assert len(view.events) == 2, "Only Msg 0 and Msg 2 should remain"


def test_empty_view_with_only_summaries() -> None:
    """测试边缘情况，其中所有常规事件都被遗忘，仅保留摘要。

    验证视图是否可以完全由摘要事件组成。
    """
    messages = [message_event(f"Msg {i}") for i in range(3)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids={messages[0].id, messages[1].id, messages[2].id},
        summary="Only summary remains",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    events = [messages[0], messages[1], messages[2], condensation1]

    view = View.from_events(events)

    assert len(view.events) == 1
    assert isinstance(view.events[0], CondensationSummaryEvent)
    assert view.events[0].summary == "Only summary remains"


def test_forget_nonexistent_summary_is_noop() -> None:
    """测试尝试忘记不存在的摘要不会导致错误。

    优雅地处理无效的摘要引用。
    """
    messages = [message_event(f"Msg {i}") for i in range(2)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="Existing summary",
        summary_offset=0,
        llm_response_id="cond_1",
    )

    # 尝试忘记不存在的摘要
    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids={"nonexistent_summary_id"},
        summary=None,
        llm_response_id="cond_2",
    )

    events = [messages[0], condensation1, messages[1], condensation2]

    view = View.from_events(events)

    # 现有的摘要应该仍然存在
    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 1
    assert summary_events[0].summary == "Existing summary"


def test_multiple_condensations_same_summary_offset() -> None:
    """测试多个缩合，每个缩合尝试以相同的偏移插入。

    验证当按顺序处理压缩时，每个压缩都可以指定相同的偏移量并且它们会按顺序插入。
    """
    messages = [message_event(f"Msg {i}") for i in range(2)]

    condensation1 = Condensation(
        id="cond-1",
        forgotten_event_ids=set(),
        summary="First at 1",
        summary_offset=1,
        llm_response_id="cond_1",
    )

    condensation2 = Condensation(
        id="cond-2",
        forgotten_event_ids=set(),
        summary="Second at 1",
        summary_offset=1,
        llm_response_id="cond_2",
    )

    condensation3 = Condensation(
        id="cond-3",
        forgotten_event_ids=set(),
        summary="Third at 1",
        summary_offset=1,
        llm_response_id="cond_3",
    )

    events = [
        messages[0],
        condensation1,
        condensation2,
        condensation3,
        messages[1],
    ]

    view = View.from_events(events)

    # 所有三个摘要都应该存在
    summary_events = [e for e in view.events if isinstance(e, CondensationSummaryEvent)]

    assert len(summary_events) == 3

    # 验证他们维持广告订单
    summaries_text = [s.summary for s in summary_events]
    assert "First at 1" in summaries_text
    assert "Second at 1" in summaries_text
    assert "Third at 1" in summaries_text
