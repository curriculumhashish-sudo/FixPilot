"""测试 RemoteEventsList。"""

from datetime import datetime
from unittest.mock import Mock

import httpx
import pytest

from openhands.sdk.conversation.impl.remote_conversation import RemoteEventsList
from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.event.streaming_delta import StreamingDeltaEvent
from openhands.sdk.llm import Message, TextContent


@pytest.fixture
def mock_client():
    """创建模拟对象 HTTP 客户端。"""
    return Mock(spec=httpx.Client)


@pytest.fixture
def conversation_id():
    """测试对话 ID。"""
    return "test-conv-id"


def create_mock_event(event_id: str) -> Event:
    """创建一个测试事件。"""
    return MessageEvent(
        id=event_id,
        timestamp=datetime.now().isoformat(),
        source="agent",
        llm_message=Message(
            role="assistant", content=[TextContent(text=f"Message {event_id}")]
        ),
    )


def create_mock_api_response(events: list[Event], next_page_id: str | None = None):
    """创建模拟对象 API 响应。"""
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {
        "items": [event.model_dump() for event in events],
        "next_page_id": next_page_id,
    }
    return mock_response


def test_remote_events_list_single_page(mock_client, conversation_id):
    """测试从单个页面加载事件。"""
    events = [
        create_mock_event("event-1"),
        create_mock_event("event-2"),
        create_mock_event("event-3"),
    ]

    mock_response = create_mock_api_response(events)
    mock_client.request.return_value = mock_response

    events_list = RemoteEventsList(mock_client, conversation_id)

    assert isinstance(events_list, RemoteEventsList)
    assert len(events_list) == 3
    assert events_list[0].id == "event-1"
    assert events_list[2].id == "event-3"


def test_remote_events_list_pagination(mock_client, conversation_id):
    """测试跨多个页面的加载事件。"""
    page1_events = [create_mock_event("event-1"), create_mock_event("event-2")]
    page2_events = [create_mock_event("event-3"), create_mock_event("event-4")]

    page1_response = create_mock_api_response(page1_events, "page-2")
    page2_response = create_mock_api_response(page2_events)

    mock_client.request.side_effect = [page1_response, page2_response]

    events_list = RemoteEventsList(mock_client, conversation_id)

    assert len(events_list) == 4
    assert events_list[0].id == "event-1"
    assert events_list[3].id == "event-4"
    assert mock_client.request.call_count == 2


def test_remote_events_list_indexing_and_slicing(mock_client, conversation_id):
    """测试类似列表的索引和切片操作。"""
    events = [
        create_mock_event("event-1"),
        create_mock_event("event-2"),
        create_mock_event("event-3"),
    ]

    mock_response = create_mock_api_response(events)
    mock_client.request.return_value = mock_response

    events_list = RemoteEventsList(mock_client, conversation_id)

    # 正向和负向索引
    assert events_list[0].id == "event-1"
    assert events_list[-1].id == "event-3"

    # 切片
    slice_result = events_list[1:3]
    assert len(slice_result) == 2
    assert slice_result[0].id == "event-2"

    # 迭代
    assert [e.id for e in events_list] == ["event-1", "event-2", "event-3"]


def test_remote_events_list_add_event_deduplication(mock_client, conversation_id):
    """测试使用自动重复数据删除功能添加事件。"""
    mock_response = create_mock_api_response([])
    mock_client.request.return_value = mock_response

    events_list = RemoteEventsList(mock_client, conversation_id)

    event = create_mock_event("new-event")
    events_list.add_event(event)
    assert len(events_list) == 1

    # 应忽略添加重复项
    events_list.add_event(event)
    assert len(events_list) == 1

    # 添加具有相同 ID 的事件应被忽略
    duplicate = create_mock_event("new-event")
    events_list.add_event(duplicate)
    assert len(events_list) == 1
    assert events_list[0] != duplicate
    assert events_list[0] == event


def test_remote_events_list_callback_integration(mock_client, conversation_id):
    """测试事件流式传输的回调集成。"""
    mock_response = create_mock_api_response([])
    mock_client.request.return_value = mock_response

    events_list = RemoteEventsList(mock_client, conversation_id)
    callback = events_list.create_default_callback()

    test_event = create_mock_event("callback-event")
    callback(test_event)

    # 默认回调应将事件添加到列表中
    assert len(events_list) == 1
    assert events_list[0].id == "callback-event"


def test_remote_events_list_callback_skips_streaming_deltas(
    mock_client, conversation_id
):
    """流式增量是暂时的：服务器从不存储它们，因此
    默认回调必须将它们排除在缓存事件之外。"""
    mock_client.request.return_value = create_mock_api_response([])

    events_list = RemoteEventsList(mock_client, conversation_id)
    callback = events_list.create_default_callback()

    callback(StreamingDeltaEvent(content="Hel"))
    callback(StreamingDeltaEvent(content="lo"))
    callback(create_mock_event("message-event"))

    assert [e.id for e in events_list] == ["message-event"]


def test_remote_events_list_api_error(mock_client, conversation_id):
    """当 API 调用失败时测试错误传播。"""
    mock_request = Mock()
    mock_error_response = Mock()
    mock_error_response.status_code = 500

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "API Error", request=mock_request, response=mock_error_response
    )
    mock_client.request.return_value = mock_response

    with pytest.raises(httpx.HTTPStatusError):
        RemoteEventsList(mock_client, conversation_id)


def test_remote_events_list_empty(mock_client, conversation_id):
    """测试空事件列表的处理。"""
    mock_response = create_mock_api_response([])
    mock_client.request.return_value = mock_response

    events_list = RemoteEventsList(mock_client, conversation_id)

    assert len(events_list) == 0
    assert list(events_list) == []

    with pytest.raises(IndexError):
        _ = events_list[0]


def test_remote_events_list_maintains_timestamp_order(mock_client, conversation_id):
    """测试事件是否按时间戳按排序顺序插入。

    这测试了竞态条件的修复，其中 WebSocket 可能会无序地传递事件（e.g.、ActionEvent 在
     MessageEvent 之前到达）。
    """
    mock_response = create_mock_api_response([])
    mock_client.request.return_value = mock_response

    events_list = RemoteEventsList(mock_client, conversation_id)

    # 创建具有特定时间戳的事件（无序）
    event1 = MessageEvent(
        id="event-1",
        timestamp="2024-01-01T10:00:00",  # 首先按时间顺序
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="Hello")]),
    )
    event2 = MessageEvent(
        id="event-2",
        timestamp="2024-01-01T10:00:02",  # 第三按时间顺序
        source="agent",
        llm_message=Message(role="assistant", content=[TextContent(text="Response")]),
    )
    event3 = MessageEvent(
        id="event-3",
        timestamp="2024-01-01T10:00:01",  # 第二按时间顺序
        source="agent",
        llm_message=Message(role="assistant", content=[TextContent(text="Action")]),
    )

    # 以错误的顺序添加事件（模拟 WebSocket 无序交付）
    events_list.add_event(event2)  # 首先添加第三个事件
    events_list.add_event(event1)  # 添加第一个事件第二个
    events_list.add_event(event3)  # 最后添加第二个事件

    # 事件应按时间戳排序，无论插入顺序如何
    assert len(events_list) == 3
    assert events_list[0].id == "event-1"  # 10:00:00
    assert events_list[1].id == "event-3"  # 10:00:01
    assert events_list[2].id == "event-2"  # 10:00:02


def test_remote_events_list_timestamp_order_with_existing_events(
    mock_client, conversation_id
):
    """测试新事件是否插入到现有事件中的正确位置。"""
    # 从已经加载的一些事件开始
    initial_events: list[Event] = [
        MessageEvent(
            id="initial-1",
            timestamp="2024-01-01T10:00:00",
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="First")]),
        ),
        MessageEvent(
            id="initial-2",
            timestamp="2024-01-01T10:00:02",
            source="agent",
            llm_message=Message(role="assistant", content=[TextContent(text="Third")]),
        ),
    ]

    mock_response = create_mock_api_response(initial_events)
    mock_client.request.return_value = mock_response

    events_list = RemoteEventsList(mock_client, conversation_id)
    assert len(events_list) == 2

    # 添加应该插入中间的事件
    middle_event = MessageEvent(
        id="middle",
        timestamp="2024-01-01T10:00:01",  # 在初始 1 和初始 2 之间
        source="agent",
        llm_message=Message(role="assistant", content=[TextContent(text="Middle")]),
    )
    events_list.add_event(middle_event)

    assert len(events_list) == 3
    assert events_list[0].id == "initial-1"
    assert events_list[1].id == "middle"
    assert events_list[2].id == "initial-2"


def test_remote_events_list_identical_timestamps_stable_order(
    mock_client, conversation_id
):
    """测试具有相同时间戳的事件是否保持插入顺序。"""
    mock_response = create_mock_api_response([])
    mock_client.request.return_value = mock_response

    events_list = RemoteEventsList(mock_client, conversation_id)

    # 创建具有相同时间戳的事件
    same_timestamp = "2024-01-01T10:00:00"
    event1 = MessageEvent(
        id="event-1",
        timestamp=same_timestamp,
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="First")]),
    )
    event2 = MessageEvent(
        id="event-2",
        timestamp=same_timestamp,
        source="agent",
        llm_message=Message(role="assistant", content=[TextContent(text="Second")]),
    )
    event3 = MessageEvent(
        id="event-3",
        timestamp=same_timestamp,
        source="agent",
        llm_message=Message(role="assistant", content=[TextContent(text="Third")]),
    )

    # 按顺序添加事件
    events_list.add_event(event1)
    events_list.add_event(event2)
    events_list.add_event(event3)

    # 具有相同时间戳的事件应保持插入顺序。 bisect_right 确保新事件插入到具有相同时间戳的
    # 现有事件之后。
    #
    assert len(events_list) == 3
    assert events_list[0].id == "event-1"
    assert events_list[1].id == "event-2"
    assert events_list[2].id == "event-3"
