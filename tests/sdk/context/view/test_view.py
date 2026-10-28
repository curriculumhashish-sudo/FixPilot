from openhands.sdk.context.view import View
from openhands.sdk.event.base import Event
from openhands.sdk.event.condenser import (
    Condensation,
    CondensationRequest,
    CondensationSummaryEvent,
)
from openhands.sdk.event.llm_convertible import (
    MessageEvent,
)
from openhands.sdk.llm import TextContent
from tests.sdk.context.view.conftest import message_event  # noqa: F401


def test_view_preserves_uncondensed_lists() -> None:
    """测试视图是否保留不包含上下文压缩的事件列表
    行动。
    """
    events: list[Event] = [message_event(f"Event {i}") for i in range(5)]
    view = View.from_events(events)
    assert len(view) == 5
    assert view.events == events


def test_view_forgets_events() -> None:
    """测试视图是否删除被遗忘的事件和上下文压缩操作。"""
    message_events: list[Event] = [message_event(f"Event {i}") for i in range(5)]
    message_event_ids = {event.id for event in message_events}

    # 构建事件列表：M_1、...、M_5、上下文压缩上下文压缩专门针对所有 M_i 消息的 ID
    #
    events: list[Event] = [
        *message_events,
        Condensation(
            forgotten_event_ids=message_event_ids,
            llm_response_id="condensation_response_1",
        ),
    ]

    # 所有事件都应该被遗忘和删除。
    view = View.from_events(events)
    assert view.events == []


def test_view_keeps_non_forgotten_events() -> None:
    """测试视图保留未被遗忘的事件。"""
    message_events: list[Event] = [message_event(f"Event {i}") for i in range(5)]
    message_event_ids = {event.id for event in message_events}

    for forgotten_event_id in message_event_ids:
        events: list[Event] = [
            *message_events,
            # 而不是忘记像这样的所有事件
            # `test_view_forgets_events`，在这个测试中我们只想忘记其中一个事件。 这样我
            # 们就可以检查事件的 REST 是否被保留。
            #
            Condensation(
                forgotten_event_ids={forgotten_event_id},
                llm_response_id="condensation_response_1",
            ),
        ]

        view = View.from_events(events)

        # 我们应该少一个消息事件
        assert len(view.events) == len(message_events) - 1
        # 并且应该_不_存在被遗忘的事件
        assert forgotten_event_id not in [event.id for event in view.events]


def test_view_inserts_summary() -> None:
    """测试视图是否在指定偏移处插入摘要观测结果。"""
    message_events = [message_event(f"Event {i}") for i in range(5)]

    for offset in range(5):
        events = [
            *message_events,
            Condensation(
                forgotten_event_ids=set(),
                summary="My Summary",
                summary_offset=offset,
                llm_response_id="condensation_response_1",
            ),
        ]
        view = View.from_events(events)

        assert len(view) == 6  # 5 个消息事件 + 1 个摘要观测结果
        for index, event in enumerate(view.events):
            if index == offset:
                assert isinstance(event, CondensationSummaryEvent)
                assert event.summary == "My Summary"

            # 插入摘要之前的事件将具有与其索引匹配的内容。
            #
            elif index < offset:
                assert isinstance(event, MessageEvent)
                assert isinstance(event.llm_message.content[0], TextContent)
                content = event.llm_message.content[0].text

                assert content == f"Event {index}"

            # 插入摘要之后的事件将偏移 1
            # from the original list.
            else:
                assert isinstance(event, MessageEvent)
                assert isinstance(event.llm_message.content[0], TextContent)
                content = event.llm_message.content[0].text

                assert content == f"Event {index - 1}"


def test_no_condensation_action_in_view() -> None:
    """确保上下文压缩事件永远不会出现在结果视图中。"""
    message_events = [message_event(f"Event {i}") for i in range(4)]

    # 构建事件序列——我们将在四个消息事件中间打包一个上下文压缩（并确保上下文压缩删除第一
    # 个事件）
    #
    events: list[Event] = []

    events.extend(message_events[:2])
    events.append(
        Condensation(
            forgotten_event_ids={message_events[0].id},
            llm_response_id="condensation_response_1",
        )
    )
    events.extend(message_events[2:])

    view = View.from_events(events)

    # 检查视图中不存在上下文压缩
    for event in view:
        assert not isinstance(event, Condensation)

    # 该视图应该只包含未被遗忘的 MessageActions
    assert len(view) == 3  # 事件 1、事件 2、事件 3（事件 0 被遗忘）


def test_unhandled_condensation_request_with_no_condensation() -> None:
    """当有一个时，测试 unhandled_condensation_request 是否为 True
    CondensationRequestAction但没有CondensationAction。
    """
    events: list[Event] = [
        message_event("Event 0"),
        message_event("Event 1"),
        CondensationRequest(),
        message_event("Event 2"),
    ]
    view = View.from_events(events)

    # 应标记为有未处理的上下文压缩请求
    assert view.unhandled_condensation_request is True

    # CondensationRequestAction 应从视图中删除
    assert len(view) == 3  # 只剩下MessageActions
    for event in view:
        assert not isinstance(event, CondensationRequest)


def test_handled_condensation_request_with_condensation_action() -> None:
    """当CondensationAction到来时测试unhandled_condensation_request是False
    在CondensationRequestAction之后。
    """
    events: list[Event] = []
    events.extend(
        [
            message_event("Event 0"),
            message_event("Event 1"),
            CondensationRequest(),
            message_event("Event 2"),
        ]
    )
    events.append(
        Condensation(
            forgotten_event_ids={event.id for event in events[:2]},
            llm_response_id="condensation_response_1",
        )
    )
    events.append(message_event("Event 3"))
    view = View.from_events(events)

    # 应将不标记为具有未处理的上下文压缩请求
    assert view.unhandled_condensation_request is False

    # CondensationRequestAction 和 CondensationAction 都应从视图中删除
    #
    assert len(view) == 2  # 事件2和事件3（事件0、1忘记了）
    for event in view:
        assert not isinstance(event, CondensationRequest)
        assert not isinstance(event, Condensation)


def test_multiple_condensation_requests_pattern() -> None:
    """使用多个上下文压缩请求和操作测试模式。"""
    events = [
        message_event(content="Event 0"),
        CondensationRequest(),  # 第一次请求
        message_event(content="Event 1"),
        Condensation(
            forgotten_event_ids=set(), llm_response_id="condensation_response_1"
        ),  # 处理第一个请求
        message_event(content="Event 2"),
        CondensationRequest(),  # 第二个请求 - 应该未被处理
        message_event(content="Event 3"),
    ]
    view = View.from_events(events)

    # 应标记为有未处理的上下文压缩请求（第二个）
    assert view.unhandled_condensation_request is True

    # CondensationRequests 和上下文压缩都应从视图中删除
    assert len(view) == 4  # 事件 0、事件 1、事件 2、事件 3
    for event in view:
        assert not isinstance(event, CondensationRequest)
        assert not isinstance(event, Condensation)


def test_condensation_action_before_request() -> None:
    """测试 CondensationRequestAction 之前的 CondensationAction 不会影响
    未处理状态。
    """
    events = [
        message_event(content="Event 0"),
        Condensation(
            forgotten_event_ids=set(), llm_response_id="condensation_response_1"
        ),  # 这不处理后面的请求
        message_event(content="Event 1"),
        CondensationRequest(),  # 这应该是未处理的
        message_event(content="Event 2"),
    ]
    view = View.from_events(events)

    # 应标记为有未处理的上下文压缩请求
    assert view.unhandled_condensation_request is True

    # CondensationRequestAction 和 CondensationAction 都应该被删除
    # from the view
    assert len(view) == 3  # 事件 0、事件 1、事件 2
    for event in view:
        assert not isinstance(event, CondensationRequest)
        assert not isinstance(event, Condensation)


def test_no_condensation_events() -> None:
    """当没有上下文压缩时，测试 unhandled_condensation_request 是 False
    事件。
    """
    events: list[Event] = [
        message_event(content="Event 0"),
        message_event(content="Event 1"),
        message_event(content="Event 2"),
    ]
    view = View.from_events(events)

    # 应将不标记为具有未处理的上下文压缩请求
    assert view.unhandled_condensation_request is False

    # 所有事件都应该保留
    assert len(view) == 3
    assert view.events == events


def test_condensation_request_always_removed_from_view() -> None:
    """测试 CondensationRequest 始终从视图中删除，无论
    未处理状态。
    """
    # 测试用例 1：未处理的请求
    events_unhandled: list[Event] = [
        message_event(content="Event 0"),
        CondensationRequest(),
        message_event(content="Event 1"),
    ]
    view_unhandled = View.from_events(events_unhandled)

    assert view_unhandled.unhandled_condensation_request is True
    assert len(view_unhandled) == 2  # 仅MessageEvents
    for event in view_unhandled:
        assert not isinstance(event, CondensationRequest)

    # 测试用例 2：已处理的请求
    events_handled = [
        message_event(content="Event 0"),
        CondensationRequest(),
        message_event(content="Event 1"),
        Condensation(
            forgotten_event_ids=set(), llm_response_id="condensation_response_1"
        ),
        message_event(content="Event 2"),
    ]
    view_handled = View.from_events(events_handled)

    assert view_handled.unhandled_condensation_request is False
    assert len(view_handled) == 3  # 仅MessageEvents
    for event in view_handled:
        assert not isinstance(event, CondensationRequest)
        assert not isinstance(event, Condensation)
