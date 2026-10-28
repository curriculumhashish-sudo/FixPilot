import asyncio
import contextlib
import io
import json
import logging
import shutil
import threading
import time
import zipfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from pydantic import SecretStr

from openhands.agent_server.conversation_lease import LEASE_FILE_NAME
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.event_service import (
    CondensationUnavailable,
    EventService,
    RunSlot,
    _log_emit_failure,
)
from openhands.agent_server.file_router import _create_zip_from_directory
from openhands.agent_server.models import (
    ConfirmationResponseRequest,
    EventPage,
    EventSortOrder,
    StoredConversation,
)
from openhands.agent_server.pub_sub import Subscriber
from openhands.sdk import LLM, Agent, AgentBase, Conversation, Message
from openhands.sdk.agent import ACPAgent
from openhands.sdk.context.condenser import NoOpCondenser
from openhands.sdk.conversation.event_store import EventLog
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.conversation.fifo_lock import FIFOLock
from openhands.sdk.conversation.impl.local_conversation import (
    ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID,
    ACP_SUPERSEDE_INFLIGHT_PROMPT,
    LocalConversation,
)
from openhands.sdk.conversation.state import (
    ConversationExecutionStatus,
    ConversationState,
)
from openhands.sdk.credential import CredentialSyncError
from openhands.sdk.event import AgentErrorEvent, Event
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.event.llm_convertible import (
    ActionEvent,
    MessageEvent,
    ObservationEvent,
)
from openhands.sdk.io.local import LocalFileStore
from openhands.sdk.io.memory import InMemoryFileStore
from openhands.sdk.llm import MessageToolCall, TextContent
from openhands.sdk.mcp.config import coerce_mcp_config
from openhands.sdk.secret import StaticSecret
from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands.sdk.subagent.schema import AgentDefinition
from openhands.sdk.utils.cipher import FERNET_TOKEN_PREFIX, Cipher
from openhands.sdk.utils.pydantic_secrets import REDACTED_SECRET_VALUE
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.terminal import TerminalAction, TerminalObservation
from tests.agent_server.stress.scripts import (
    SlowTestLLM,
    start_conversation_with_test_llm,
    text_message,
)


# 智能体进行新对话。 meta.json (StoredConversation) 不再带有智能体 - base_state.json 是
# 其唯一的事实来源 - 因此测试将其单独传递给 EventService。
#
def _sample_agent() -> Agent:
    return Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[])


@pytest.fixture
def sample_agent():
    return _sample_agent()


@pytest.fixture
def sample_stored_conversation():
    """创建样本 StoredConversation 进行测试。"""
    return StoredConversation(
        id=uuid4(),
        workspace=LocalWorkspace(working_dir="workspace/project"),
        confirmation_policy=NeverConfirm(),
        initial_message=None,
        metrics=None,
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
    )


@pytest.fixture
def event_service(sample_stored_conversation, sample_agent):
    """创建一个 EventService 实例用于测试。"""
    service = EventService(
        stored=sample_stored_conversation,
        agent=sample_agent,
        conversations_dir=Path("test_conversation_dir"),
    )
    return service


@pytest.fixture
def mock_conversation_with_events():
    """使用示例事件创建模拟对象对话。"""
    conversation = MagicMock(spec=Conversation)
    state = MagicMock(spec=ConversationState)

    # 创建具有不同时间戳和类型的示例事件
    events = [
        MessageEvent(
            id=f"event{index}", source="user", llm_message=Message(role="user")
        )
        for index in range(1, 6)
    ]

    state.events = events
    state.__enter__ = MagicMock(return_value=state)
    state.__exit__ = MagicMock(return_value=None)
    conversation._state = state

    return conversation


@pytest.fixture
def mock_conversation_with_timestamped_events():
    """创建一个包含具有特定时间戳的事件的模拟对象对话以进行测试。"""
    conversation = MagicMock(spec=Conversation)
    state = MagicMock(spec=ConversationState)

    # 创建具有特定 ISO 格式时间戳的事件这些时间戳按时间顺序排列
    #
    timestamps = [
        "2025-01-01T10:00:00.000000",
        "2025-01-01T11:00:00.000000",
        "2025-01-01T12:00:00.000000",
        "2025-01-01T13:00:00.000000",
        "2025-01-01T14:00:00.000000",
    ]

    events = []
    for index, timestamp in enumerate(timestamps, 1):
        event = MessageEvent(
            id=f"event{index}",
            source="user",
            llm_message=Message(role="user"),
            timestamp=timestamp,
        )
        events.append(event)

    state.events = events
    state.__enter__ = MagicMock(return_value=state)
    state.__exit__ = MagicMock(return_value=None)
    conversation._state = state

    return conversation


def _message_event(event_id: str, text: str, timestamp: str) -> MessageEvent:
    return MessageEvent(
        id=event_id,
        source="user",
        llm_message=Message(role="user", content=[TextContent(text=text)]),
        timestamp=timestamp,
    )


def _event_log_with_unreadable_middle(
    fs, unreadable_payload: str | bytes
) -> tuple[EventLog, MessageEvent, MessageEvent, str]:
    event0 = _message_event(
        "00000000-0000-0000-0000-000000000001",
        "first",
        "2026-06-16T09:00:00",
    )
    unreadable_event_id = "00000000-0000-0000-0000-000000000002"
    event2 = _message_event(
        "00000000-0000-0000-0000-000000000003",
        "third",
        "2026-06-16T09:00:02",
    )
    unreadable_path = f"events/event-00001-{unreadable_event_id}.json"
    fs.write(
        f"events/event-00000-{event0.id}.json",
        event0.model_dump_json(exclude_none=True),
    )
    fs.write(unreadable_path, unreadable_payload)
    fs.write(
        f"events/event-00002-{event2.id}.json",
        event2.model_dump_json(exclude_none=True),
    )
    return EventLog(fs), event0, event2, unreadable_path


def _attach_event_log(event_service, event_log: EventLog) -> None:
    conversation = MagicMock(spec=Conversation)
    state = MagicMock(spec=ConversationState)
    state.events = event_log
    conversation._state = state
    event_service._conversation = conversation


class TestEventServiceSearchEvents:
    """测试用例代表 EventService.search_events 方法。"""

    @pytest.mark.asyncio
    async def test_search_events_inactive_service(self, event_service):
        """测试当对话不活跃时 search_events 是否会引发 ValueError。"""
        event_service._conversation = None

        with pytest.raises(ValueError, match="inactive_service"):
            await event_service.search_events()

    @pytest.mark.asyncio
    async def test_search_events_empty_result(self, event_service):
        """search_events 无事件地进行测试。"""
        # 模拟对象与空事件的对话
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)
        state.events = []
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state

        event_service._conversation = conversation

        result = await event_service.search_events()

        assert isinstance(result, EventPage)
        assert result.items == []
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_events_basic(
        self, event_service, mock_conversation_with_events
    ):
        """测试基本 search_events 功能。"""
        event_service._conversation = mock_conversation_with_events

        result = await event_service.search_events()

        assert len(result.items) == 5
        assert result.next_page_id is None
        # 默认排序为 TIMESTAMP（升序），因此第一个事件应该是最早的
        assert result.items[0].timestamp < result.items[-1].timestamp

    @pytest.mark.asyncio
    async def test_search_events_kind_filter(
        self, event_service, mock_conversation_with_events
    ):
        """测试按类型过滤事件。"""
        event_service._conversation = mock_conversation_with_events

        # 按 ActionEvent 测试过滤
        result = await event_service.search_events(kind="ActionEvent")
        assert len(result.items) == 0

        # 按 MessageEvent 测试过滤
        result = await event_service.search_events(
            kind="openhands.sdk.event.llm_convertible.message.MessageEvent"
        )
        assert len(result.items) == 5
        for event in result.items:
            assert event.__class__.__name__ == "MessageEvent"

        # 按不存在的种类测试过滤
        result = await event_service.search_events(kind="NonExistentEvent")
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_search_events_short_kind_matches_qualified_kind(
        self, event_service, mock_conversation_with_events
    ):
        """裸类名（连线 ``kind``）像完整路径一样进行过滤。"""
        event_service._conversation = mock_conversation_with_events

        qualified = await event_service.search_events(
            kind="openhands.sdk.event.llm_convertible.message.MessageEvent"
        )
        short = await event_service.search_events(kind="MessageEvent")
        assert len(short.items) == 5
        assert [e.id for e in short.items] == [e.id for e in qualified.items]
        assert short.next_page_id == qualified.next_page_id

        # 与另一个过滤器结合使用，两者都适用。
        result = await event_service.search_events(kind="MessageEvent", source="user")
        assert len(result.items) == 5
        result = await event_service.search_events(kind="MessageEvent", source="agent")
        assert len(result.items) == 0

        # 部分模块路径既不是短名称也不是全名称。
        result = await event_service.search_events(kind="message.MessageEvent")
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_search_events_sorting(
        self, event_service, mock_conversation_with_events
    ):
        """测试按时间戳对事件进行排序。"""
        event_service._conversation = mock_conversation_with_events

        # 测试 TIMESTAMP（升序）- 默认
        result = await event_service.search_events(sort_order=EventSortOrder.TIMESTAMP)
        assert len(result.items) == 5
        for i in range(len(result.items) - 1):
            assert result.items[i].timestamp <= result.items[i + 1].timestamp

        # 测试 TIMESTAMP_DESC（降序）
        result = await event_service.search_events(
            sort_order=EventSortOrder.TIMESTAMP_DESC
        )
        assert len(result.items) == 5
        for i in range(len(result.items) - 1):
            assert result.items[i].timestamp >= result.items[i + 1].timestamp

    @pytest.mark.asyncio
    async def test_search_events_pagination(
        self, event_service, mock_conversation_with_events
    ):
        """测试分页功能。"""
        event_service._conversation = mock_conversation_with_events

        # 测试首页限制为 2
        result = await event_service.search_events(limit=2)
        assert len(result.items) == 2
        assert result.next_page_id is not None

        # 使用 next_page_id 测试第二页
        result = await event_service.search_events(page_id=result.next_page_id, limit=2)
        assert len(result.items) == 2
        assert result.next_page_id is not None

        # 测试第三页
        result = await event_service.search_events(page_id=result.next_page_id, limit=2)
        assert len(result.items) == 1  # 仅剩一件商品
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_events_combined_filter_and_sort(
        self, event_service, mock_conversation_with_events
    ):
        """测试将种类过滤与排序相结合。"""
        event_service._conversation = mock_conversation_with_events

        # 按 ActionEvent 过滤并按 TIMESTAMP_DESC 排序
        result = await event_service.search_events(
            kind="openhands.sdk.event.llm_convertible.message.MessageEvent",
            sort_order=EventSortOrder.TIMESTAMP_DESC,
        )

        assert len(result.items) == 5
        for event in result.items:
            assert event.__class__.__name__ == "MessageEvent"
        # 应按时间戳降序排序（最新的在前）
        assert result.items[0].timestamp > result.items[1].timestamp

    @pytest.mark.asyncio
    async def test_search_events_pagination_with_filter(
        self, event_service, mock_conversation_with_events
    ):
        """使用过滤测试分页。"""
        event_service._conversation = mock_conversation_with_events

        # 按 MessageEvent 过滤，限制为 1
        result = await event_service.search_events(
            kind="openhands.sdk.event.llm_convertible.message.MessageEvent", limit=1
        )
        assert len(result.items) == 1
        assert result.items[0].__class__.__name__ == "MessageEvent"
        assert result.next_page_id is not None

        # 获取第二页
        result = await event_service.search_events(
            kind="openhands.sdk.event.llm_convertible.message.MessageEvent",
            page_id=result.next_page_id,
            limit=4,
        )
        assert len(result.items) == 4
        assert result.items[0].__class__.__name__ == "MessageEvent"
        assert result.next_page_id is None  # 没有了 MessageEvents

    @pytest.mark.asyncio
    async def test_search_events_invalid_page_id(
        self, event_service, mock_conversation_with_events
    ):
        """使用无效的 page_id 测试 search_events。"""
        event_service._conversation = mock_conversation_with_events

        # 使用不存在的 page_id
        invalid_page_id = "invalid_event_id"
        result = await event_service.search_events(page_id=invalid_page_id)

        # 应该返回所有项目，因为 page_id 与任何事件都不匹配
        assert len(result.items) == 5
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_events_large_limit(
        self, event_service, mock_conversation_with_events
    ):
        """使用大于可用事件的限制来测试 search_events。"""
        event_service._conversation = mock_conversation_with_events

        result = await event_service.search_events(limit=100)

        assert len(result.items) == 5  # 所有可用事件
        assert result.next_page_id is None

    @pytest.mark.parametrize("unreadable_payload", ["", "{not-json", "{}"])
    @pytest.mark.asyncio
    async def test_search_events_skips_unreadable_event_files(
        self, event_service, unreadable_payload
    ):
        fs = InMemoryFileStore()
        event_log, event0, event2, _ = _event_log_with_unreadable_middle(
            fs, unreadable_payload
        )
        _attach_event_log(event_service, event_log)

        result = await event_service.search_events(limit=10)

        assert [event.id for event in result.items] == [event0.id, event2.id]
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_events_skips_missing_event_files(self, event_service):
        fs = InMemoryFileStore()
        event_log, event0, event2, unreadable_path = _event_log_with_unreadable_middle(
            fs, "will be deleted"
        )
        fs.delete(unreadable_path)
        _attach_event_log(event_service, event_log)

        result = await event_service.search_events(limit=10)

        assert [event.id for event in result.items] == [event0.id, event2.id]
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_events_skips_non_utf8_event_files(
        self, event_service, tmp_path
    ):
        fs = LocalFileStore(str(tmp_path))
        event_log, event0, event2, _ = _event_log_with_unreadable_middle(fs, b"\xff")
        _attach_event_log(event_service, event_log)

        result = await event_service.search_events(limit=10)

        assert [event.id for event in result.items] == [event0.id, event2.id]
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_events_zero_limit(
        self, event_service, mock_conversation_with_events
    ):
        """用零极限测试 search_events。"""
        event_service._conversation = mock_conversation_with_events

        result = await event_service.search_events(limit=0)

        assert len(result.items) == 0
        # 如果有活动可用，仍应有 next_page_id
        assert result.next_page_id is not None

    @pytest.mark.asyncio
    async def test_search_events_does_not_scan_whole_log(self, event_service):
        """加载最近的 N 个事件必须是 O(limit)，而不是 O(total)。

        回归测试读取每个事件的先前实现
        from the EventLog before returning a single page, making long
        对话实际上无法使用。
        """

        class _CountingEvents:
            """对 ``__getitem__`` 次访问进行计数的序列包装器。"""

            def __init__(self, items: list[Event]):
                self._items = items
                self.getitem_calls = 0
                # ``get_index`` 是 EventLog 暴露的内容； 镜像它可以让我们验证 O(1)
                # page_id 查找路径是否已执行。
                #
                self._id_to_idx = {e.id: i for i, e in enumerate(items)}

            def __len__(self) -> int:
                return len(self._items)

            def __getitem__(self, idx: int) -> Event:
                self.getitem_calls += 1
                return self._items[idx]

            def __iter__(self):  # pragma: no cover - must NOT be used in fast path
                raise AssertionError(
                    "search_events fell back to full iteration; expected "
                    "index-based access only"
                )

            def get_index(self, event_id: str) -> int:
                return self._id_to_idx[event_id]

        total = 1000
        events = [
            MessageEvent(
                id=f"event{i:05d}",
                source="user",
                llm_message=Message(role="user"),
            )
            for i in range(total)
        ]
        wrapper = _CountingEvents(cast(list[Event], events))

        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)
        state.events = wrapper
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state
        event_service._conversation = conversation

        # 第一页：1000 个最新事件中的 50 个。
        result = await event_service.search_events(
            limit=50, sort_order=EventSortOrder.TIMESTAMP_DESC
        )
        assert len(result.items) == 50
        assert result.items[0].id == events[-1].id
        assert result.items[-1].id == events[-50].id
        assert result.next_page_id == events[-51].id
        # 最多必须读取 limit + 1 个事件（next_page_id 需要额外读取一个事件）。
        assert wrapper.getitem_calls <= 51, (
            f"Expected <=51 getitem calls, got {wrapper.getitem_calls}"
        )

        # 第二页通过 page_id：也是 O(limit) 并使用 get_index（无扫描）。
        wrapper.getitem_calls = 0
        next_page = await event_service.search_events(
            page_id=result.next_page_id,
            limit=50,
            sort_order=EventSortOrder.TIMESTAMP_DESC,
        )
        assert len(next_page.items) == 50
        assert next_page.items[0].id == events[-51].id
        assert wrapper.getitem_calls <= 51

    @pytest.mark.asyncio
    async def test_search_events_exact_pagination_boundary(self, event_service):
        """当事件数量完全符合限制时测试分页。"""
        # 正好创建 3 个事件
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)

        events = [
            MessageEvent(
                id=f"event{index}", source="user", llm_message=Message(role="user")
            )
            for index in range(1, 4)
        ]

        state.events = events
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state

        event_service._conversation = conversation

        # 请求恰好 3 个事件（与可用事件相同）
        result = await event_service.search_events(limit=3)

        assert len(result.items) == 3
        assert result.next_page_id is None  # 没有更多活动

    @pytest.mark.asyncio
    async def test_search_events_timestamp_gte_filter(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """使用 timestamp__gte（大于或等于）测试过滤事件。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 过滤事件 >= 12:00:00（应返回事件 3、4、5）
        filter_time = datetime(2025, 1, 1, 12, 0, 0)
        result = await event_service.search_events(timestamp__gte=filter_time)

        assert len(result.items) == 3
        assert result.items[0].id == "event3"
        assert result.items[1].id == "event4"
        assert result.items[2].id == "event5"
        # 所有返回的事件应具有时间戳 >= 过滤器值
        filter_iso = filter_time.isoformat()
        for event in result.items:
            assert event.timestamp >= filter_iso

    @pytest.mark.asyncio
    async def test_search_events_timestamp_lt_filter(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """使用 timestamp__lt（小于）测试过滤事件。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 过滤 < 13:00:00 的事件（应返回事件 1、2、3）
        filter_time = datetime(2025, 1, 1, 13, 0, 0)
        result = await event_service.search_events(timestamp__lt=filter_time)

        assert len(result.items) == 3
        assert result.items[0].id == "event1"
        assert result.items[1].id == "event2"
        assert result.items[2].id == "event3"
        # 所有返回的事件应具有时间戳 < 过滤器值
        filter_iso = filter_time.isoformat()
        for event in result.items:
            assert event.timestamp < filter_iso

    @pytest.mark.asyncio
    async def test_search_events_timestamp_range_filter(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """使用 timestamp__gte 和 timestamp__lt 测试过滤事件。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 过滤 11:00:00 和 13:00:00 之间的事件（应返回事件 2、3）
        gte_time = datetime(2025, 1, 1, 11, 0, 0)
        lt_time = datetime(2025, 1, 1, 13, 0, 0)
        result = await event_service.search_events(
            timestamp__gte=gte_time, timestamp__lt=lt_time
        )

        assert len(result.items) == 2
        assert result.items[0].id == "event2"
        assert result.items[1].id == "event3"
        # 所有返回的事件都应该在范围内
        gte_iso = gte_time.isoformat()
        lt_iso = lt_time.isoformat()
        for event in result.items:
            assert event.timestamp >= gte_iso
            assert event.timestamp < lt_iso

    @pytest.mark.asyncio
    async def test_search_events_timestamp_filter_with_timezone_aware(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """使用时区感知的日期时间测试过滤事件需要标准化。

        事件时间戳是幼稚的（服务器本地时间），因此调用者必须在过滤之前将时区感知的日
        期时间标准化为幼稚。 这是由 REST/WebSocket API 层通过
        normalize_datetime_to_server_timezone() 完成的。
        """
        event_service._conversation = mock_conversation_with_timestamped_events

        # 过滤事件 >= 12:00:00（天真，就好像由 API 层标准化） API 层会将 tz 感知的日期时
        # 间转换为天真的服务器时间
        #
        filter_time = datetime(2025, 1, 1, 12, 0, 0)  # 天真的日期时间
        result = await event_service.search_events(timestamp__gte=filter_time)

        assert len(result.items) == 3
        assert result.items[0].id == "event3"
        assert result.items[1].id == "event4"
        assert result.items[2].id == "event5"

    @pytest.mark.asyncio
    async def test_search_events_timestamp_filter_no_matches(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """测试过滤时间戳与任何事件都不匹配的事件。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 过滤事件 >= 15:00:00（不应返回任何事件）
        filter_time = datetime(2025, 1, 1, 15, 0, 0)
        result = await event_service.search_events(timestamp__gte=filter_time)

        assert len(result.items) == 0
        assert result.next_page_id is None

    @pytest.mark.asyncio
    async def test_search_events_timestamp_filter_all_events(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """使用包含所有事件的时间戳测试过滤事件。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 过滤事件 >= 09:00:00（应返回所有事件）
        filter_time = datetime(2025, 1, 1, 9, 0, 0)
        result = await event_service.search_events(timestamp__gte=filter_time)

        assert len(result.items) == 5
        assert result.items[0].id == "event1"
        assert result.items[4].id == "event5"


class TestEventServiceCountEvents:
    """测试用例代表 EventService.count_events 方法。"""

    @pytest.mark.asyncio
    async def test_count_events_inactive_service(self, event_service):
        """测试当服务处于非活动状态时 count_events 是否会引发 ValueError。"""
        event_service._conversation = None

        with pytest.raises(ValueError, match="inactive_service"):
            await event_service.count_events()

    @pytest.mark.asyncio
    async def test_count_events_empty_result(self, event_service):
        """count_events 无事件地进行测试。"""
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)
        state.events = []
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state

        event_service._conversation = conversation

        result = await event_service.count_events()
        assert result == 0

    @pytest.mark.asyncio
    async def test_count_events_basic(
        self, event_service, mock_conversation_with_events
    ):
        """测试基本 count_events 功能。"""
        event_service._conversation = mock_conversation_with_events

        result = await event_service.count_events()
        assert result == 5  # mock_conversation_with_events 中的事件总数

    @pytest.mark.asyncio
    async def test_count_events_kind_filter(
        self, event_service, mock_conversation_with_events
    ):
        """测试使用 kind 过滤器对事件进行计数。"""
        event_service._conversation = mock_conversation_with_events

        # 统计所有事件
        result = await event_service.count_events()
        assert result == 5

        # 计数 ActionEvent 个事件（应为 5）
        result = await event_service.count_events(
            kind="openhands.sdk.event.llm_convertible.message.MessageEvent"
        )
        assert result == 5

        # 裸类名称（连线 ``kind``）对相同事件进行计数
        result = await event_service.count_events(kind="MessageEvent")
        assert result == 5
        result = await event_service.count_events(kind="MessageEvent", source="agent")
        assert result == 0

        # 计数不存在的事件类型（应为 0）
        result = await event_service.count_events(kind="NonExistentEvent")
        assert result == 0

    @pytest.mark.asyncio
    async def test_count_events_skips_unreadable_event_files_when_filtering(
        self, event_service
    ):
        fs = InMemoryFileStore()
        event_log, _, _, _ = _event_log_with_unreadable_middle(fs, "")
        _attach_event_log(event_service, event_log)

        assert await event_service.count_events() == 3
        assert await event_service.count_events(source="user") == 2

    @pytest.mark.asyncio
    async def test_count_events_timestamp_gte_filter(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """使用 timestamp__gte 过滤器测试计数事件。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 计数事件 >= 12:00:00（应返回 3）
        filter_time = datetime(2025, 1, 1, 12, 0, 0)
        result = await event_service.count_events(timestamp__gte=filter_time)
        assert result == 3

    @pytest.mark.asyncio
    async def test_count_events_timestamp_lt_filter(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """使用 timestamp__lt 过滤器测试计数事件。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 对 < 13:00:00 的事件进行计数（应返回 3）
        filter_time = datetime(2025, 1, 1, 13, 0, 0)
        result = await event_service.count_events(timestamp__lt=filter_time)
        assert result == 3

    @pytest.mark.asyncio
    async def test_count_events_timestamp_range_filter(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """测试使用两个时间戳过滤器对事件进行计数。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 统计 11:00:00 到 13:00:00 之间的事件（应返回 2）
        gte_time = datetime(2025, 1, 1, 11, 0, 0)
        lt_time = datetime(2025, 1, 1, 13, 0, 0)
        result = await event_service.count_events(
            timestamp__gte=gte_time, timestamp__lt=lt_time
        )
        assert result == 2

    @pytest.mark.asyncio
    async def test_count_events_timestamp_filter_with_timezone_aware(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """使用时区感知日期时间测试计数事件需要标准化。

        事件时间戳是幼稚的（服务器本地时间），因此调用者必须在过滤之前将时区感知的日
        期时间标准化为幼稚。 这是由 REST/WebSocket API 层通过
        normalize_datetime_to_server_timezone() 完成的。
        """
        event_service._conversation = mock_conversation_with_timestamped_events

        # 计数事件 >= 12:00:00（天真，就好像通过 API 层标准化）
        filter_time = datetime(2025, 1, 1, 12, 0, 0)  # 天真的日期时间
        result = await event_service.count_events(timestamp__gte=filter_time)
        assert result == 3

    @pytest.mark.asyncio
    async def test_count_events_timestamp_filter_no_matches(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """测试时间戳与任何事件都不匹配的事件计数。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 计数事件 >= 15:00:00（应返回 0）
        filter_time = datetime(2025, 1, 1, 15, 0, 0)
        result = await event_service.count_events(timestamp__gte=filter_time)
        assert result == 0

    @pytest.mark.asyncio
    async def test_count_events_timestamp_filter_all_events(
        self, event_service, mock_conversation_with_timestamped_events
    ):
        """测试使用包含所有事件的时间戳对事件进行计数。"""
        event_service._conversation = mock_conversation_with_timestamped_events

        # 计数事件 >= 09:00:00（应返回 5）
        filter_time = datetime(2025, 1, 1, 9, 0, 0)
        result = await event_service.count_events(timestamp__gte=filter_time)
        assert result == 5


class TestEventServiceSendMessage:
    """测试用例代表 EventService.send_message 方法。"""

    async def _mock_executor(self, *args):
        """帮助程序为 run_in_executor 创建模拟对象协程。"""
        return None

    @pytest.mark.asyncio
    async def test_send_message_inactive_service(self, event_service):
        """测试当服务处于非活动状态时 send_message 是否会引发 ValueError。"""
        event_service._conversation = None
        message = Message(role="user", content=[])

        with pytest.raises(ValueError, match="inactive_service"):
            await event_service.send_message(message)

    @pytest.mark.asyncio
    async def test_send_message_with_run_false_default(self, event_service):
        """使用默认 run=True 测试 send_message。"""
        # 模拟对象对话及其方法
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        conversation.run = MagicMock()

        event_service._conversation = conversation
        message = Message(role="user", content=[])

        # 模拟对象事件循环和执行者
        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            mock_loop.run_in_executor.side_effect = lambda *args: self._mock_executor()

            # 使用默认 run=True 调用 send_message
            await event_service.send_message(message)

            # 验证 send_message 是通过执行器调用的
            mock_loop.run_in_executor.assert_any_call(
                None, conversation.send_message, message
            )
            # 验证 run 是通过执行程序调用的，因为 run=True 且智能体未运行
            assert (
                None,
                conversation.run,
            ) not in mock_loop.run_in_executor.call_args_list

    @pytest.mark.asyncio
    async def test_send_message_with_run_false(self, event_service):
        """使用 run=False 测试 send_message。"""
        # 模拟对象对话及其方法
        conversation = MagicMock()
        conversation.send_message = MagicMock()
        conversation.run = MagicMock()

        event_service._conversation = conversation
        message = Message(role="user", content=[])

        # 模拟对象事件循环和执行者
        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            mock_loop.run_in_executor.side_effect = lambda *args: self._mock_executor()

            # 使用 run=False 调用 send_message
            await event_service.send_message(message, run=False)

            # 验证 send_message 是通过执行器调用的
            mock_loop.run_in_executor.assert_called_once_with(
                None, conversation.send_message, message
            )
            # 验证运行已被调用不，因为 run=False
            assert mock_loop.run_in_executor.call_count == 1  # 仅 send_message 次通话

    @pytest.mark.asyncio
    async def test_send_message_with_run_true_agent_already_running(
        self, event_service
    ):
        """使用 run=True 测试 send_message，但智能体已在运行。"""
        # 模拟对象对话及其方法
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.RUNNING
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        conversation.run = MagicMock()

        event_service._conversation = conversation
        # 模拟已运行的对话以测试 ValueError 路径
        event_service._run_task = asyncio.create_task(asyncio.sleep(10))
        message = Message(role="user", content=[])

        # 使用 run=True 调用 send_message — 应该默默地跳过运行
        await event_service.send_message(message, run=True)

        conversation.send_message.assert_called_once_with(message)
        # run() 委托给 self.run()，它检查锁下的状态并引发 ValueError（被 send_message 捕
        # 获）——因此 conversation.run 永远不会被调用。
        #
        conversation.run.assert_not_called()

        # 清理模拟运行任务
        event_service._run_task.cancel()
        with suppress(asyncio.CancelledError):
            await event_service._run_task

    @pytest.mark.asyncio
    async def test_send_message_with_run_true_agent_idle(self, event_service):
        """使用 run=True 和智能体空闲触发器运行测试 send_message。"""
        # 模拟对象对话及其方法
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        conversation.run = MagicMock()

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()
        message = Message(role="user", content=[])

        # 使用 run=True 调用 send_message
        await event_service.send_message(message, run=True)

        # 验证 send_message 被调用
        conversation.send_message.assert_called_once_with(message)

        # send_message 委托给 self.run() 创建后台任务
        assert event_service._run_task is not None
        await event_service._run_task

        # 由于智能体空闲而调用了验证运行
        conversation.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_with_run_true_interrupts_running_acp_turn(
        self, event_service, tmp_path
    ):
        """新的用户消息应该会中断正在进行的 ACP 提示词。"""
        agent = ACPAgent(acp_command=["echo", "test"])
        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            max_iteration_per_run=4,
            stuck_detection=False,
        )
        conversation.send_message("initial request")
        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        first_step_started = asyncio.Event()
        first_step_cancelled = asyncio.Event()
        second_step_seen = asyncio.Event()
        prompts_seen: list[str] = []

        def user_text(event: MessageEvent | None) -> str:
            assert event is not None
            content = event.llm_message.content[0]
            assert isinstance(content, TextContent)
            return content.text

        async def blocking_astep(
            self,  # noqa: ARG001
            conv: LocalConversation,  # noqa: ARG001
            on_event,  # noqa: ARG001
            on_token=None,  # noqa: ARG001
            prompt_message: MessageEvent | None = None,
        ) -> None:
            prompts_seen.append(user_text(prompt_message))
            if len(prompts_seen) == 1:
                first_step_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    first_step_cancelled.set()
                    raise

            second_step_seen.set()
            conv.state.execution_status = ConversationExecutionStatus.FINISHED

        with (
            patch.object(ACPAgent, "init_state", autospec=True),
            patch.object(ACPAgent, "astep", new=blocking_astep),
        ):
            try:
                await event_service.run()
                await asyncio.wait_for(first_step_started.wait(), timeout=1.0)

                await event_service.send_message(
                    Message(role="user", content=[TextContent(text="intervening")]),
                    run=True,
                )

                await asyncio.wait_for(first_step_cancelled.wait(), timeout=1.0)
                await asyncio.wait_for(second_step_seen.wait(), timeout=1.0)
            finally:
                if (
                    event_service._run_task is not None
                    and not event_service._run_task.done()
                ):
                    conversation.interrupt()
                    with suppress(asyncio.CancelledError, TimeoutError):
                        await asyncio.wait_for(event_service._run_task, timeout=1.0)

        assert prompts_seen == ["initial request", "intervening"]

    @pytest.mark.asyncio
    async def test_send_message_with_run_true_does_not_interrupt_current_acp_prompt(
        self, event_service, tmp_path
    ):
        """如果 ACP 提示词已前进到新消息，请勿取消。"""
        agent = ACPAgent(acp_command=["echo", "test"])
        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            max_iteration_per_run=4,
            stuck_detection=False,
        )
        conversation.send_message("initial request")
        conversation.state.execution_status = ConversationExecutionStatus.RUNNING
        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        release_run = asyncio.Event()
        event_service._run_task = asyncio.create_task(release_run.wait())
        original_send_message = conversation.send_message

        def send_and_mark_active_prompt(message):
            original_send_message(message)
            conversation.state.execution_status = ConversationExecutionStatus.RUNNING
            conversation.state.agent_state = {
                **conversation.state.agent_state,
                ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID: (
                    conversation.state.last_user_message_id
                ),
            }

        conversation.send_message = send_and_mark_active_prompt  # type: ignore[method-assign]
        conversation.interrupt = MagicMock()  # type: ignore[method-assign]

        try:
            await event_service.send_message(
                Message(role="user", content=[TextContent(text="intervening")]),
                run=True,
            )
        finally:
            release_run.set()
            await event_service._run_task
            event_service._run_task = None

        conversation.interrupt.assert_not_called()
        assert event_service._rerun_requested is False

    @pytest.mark.asyncio
    async def test_acp_supersede_holds_capacity_across_interrupt(
        self, event_service, tmp_path
    ):
        """ACP 取代重新启动必须保留其前任持有的许可证。

        ``send_message(run=True)`` 中断正在进行的 ACP 提示词，这使得该运行在退出时获
        得许可，然后才开始替换运行。 如果替换需要获取一
        个新的许可，那么在对话的工作运行已经被终止后拒绝它（429），就会丢弃用户的请求
        ，没有任何重试信号。 即使在服务器处于极限时，在整个取代窗口中保持会话许可也
        可以确保重新启动容量安全。
        """
        agent = ACPAgent(acp_command=["echo", "test"])
        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            max_iteration_per_run=4,
            stuck_detection=False,
        )
        conversation.send_message("initial request")
        conversation.state.execution_status = ConversationExecutionStatus.RUNNING
        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()
        event_service._mark_running_acp_prompt_superseded = AsyncMock(
            return_value=(True, False)
        )
        # 服务器已满：一个插槽，由被取代的运行占用。
        event_service._run_semaphore = asyncio.Semaphore(1)
        owner = await RunSlot.acquire(event_service._run_semaphore)
        event_service._run_session_slot = owner
        event_service._run_task = asyncio.create_task(asyncio.Event().wait())

        async def interrupt_and_yield(*, internal_acp_rerun=False):
            # 当中断耗尽它时，对传出运行进行建模，产生自己的句柄； 会话许可通过 pin 保留
            # 。
            #
            run_task = event_service._run_task
            if run_task is not None:
                run_task.cancel()
                with suppress(asyncio.CancelledError):
                    await run_task
            event_service._run_task = None
            conversation.state.execution_status = ConversationExecutionStatus.IDLE
            # 由于前一个版本的用户名消失，一个新的获取应该成功预处理 -- 而且一个竞争的调
            # 用者可能会接管它，导致下面的重启失败返回429。
            #
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(
                    event_service._run_semaphore.acquire(), timeout=0.25
                )
            capacity_held_at_interrupt.set()

        event_service.interrupt = interrupt_and_yield
        replacement_started = asyncio.Event()
        capacity_held_at_interrupt = asyncio.Event()

        async def finishing_astep(
            self,  # noqa: ARG001
            conv: LocalConversation,
            on_event,  # noqa: ARG001
            on_token=None,  # noqa: ARG001
            prompt_message=None,  # noqa: ARG001
        ) -> None:
            replacement_started.set()
            conv.state.execution_status = ConversationExecutionStatus.FINISHED

        with (
            patch.object(ACPAgent, "init_state", autospec=True),
            patch.object(ACPAgent, "astep", new=finishing_astep),
        ):
            # 不得引发 ConversationRunLimitExceeded：重新启动会重用其前任持有的会话许可
            # ，而不是获取新的会话许可。
            #
            await event_service.send_message(
                Message(role="user", content=[TextContent(text="intervening")]),
                run=True,
            )

            assert event_service._run_task is not None
            await asyncio.wait_for(event_service._run_task, timeout=5)

        assert replacement_started.is_set()
        # 在整个取代窗口期间容量保持不变，并且一旦链稳定，会话许可将返回到共享池。
        #
        assert capacity_held_at_interrupt.is_set()
        assert event_service._run_session_pins == 0
        assert event_service._run_session_slot is None
        await asyncio.wait_for(event_service._run_semaphore.acquire(), timeout=5)
        event_service._run_semaphore.release()

    @pytest.mark.asyncio
    async def test_acp_supersede_pin_released_when_interrupt_raises(
        self, event_service, tmp_path
    ):
        """即使中断发生，也必须释放取代引脚。"""
        agent = ACPAgent(acp_command=["echo", "test"])
        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            max_iteration_per_run=4,
            stuck_detection=False,
        )
        conversation.send_message("initial request")
        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()
        event_service._mark_running_acp_prompt_superseded = AsyncMock(
            return_value=(True, False)
        )
        event_service._run_semaphore = asyncio.Semaphore(1)
        event_service.interrupt = AsyncMock(side_effect=RuntimeError("teardown"))

        with pytest.raises(RuntimeError, match="teardown"):
            await event_service.send_message(
                Message(role="user", content=[TextContent(text="intervening")]),
                run=True,
            )
        assert event_service._run_session_pins == 0

    @pytest.mark.asyncio
    async def test_acp_supersede_mark_rechecks_current_prompt(
        self, event_service, tmp_path
    ):
        """请勿将取代标记附加到替换 ACP 提示词上。"""
        agent = ACPAgent(acp_command=["echo", "test"])
        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            max_iteration_per_run=4,
            stuck_detection=False,
        )
        conversation.send_message("initial request")
        conversation.send_message("replacement request")
        latest_user_message_id = conversation.state.last_user_message_id
        assert latest_user_message_id is not None
        conversation.state.execution_status = ConversationExecutionStatus.RUNNING
        conversation.state.agent_state = {
            **conversation.state.agent_state,
            ACP_INFLIGHT_PROMPT_USER_MESSAGE_ID: latest_user_message_id,
        }
        event_service._conversation = conversation
        release_run = asyncio.Event()
        event_service._run_task = asyncio.create_task(release_run.wait())

        try:
            (
                marked,
                active_prompt_has_latest,
            ) = await event_service._mark_running_acp_prompt_superseded()
        finally:
            release_run.set()
            await event_service._run_task
            event_service._run_task = None

        assert marked is False
        assert active_prompt_has_latest is True
        assert ACP_SUPERSEDE_INFLIGHT_PROMPT not in conversation.state.agent_state

    @pytest.mark.asyncio
    async def test_explicit_interrupt_clears_internal_acp_rerun_request(
        self, event_service
    ):
        """稍后的显式停止应该胜过早期的内部 ACP 重新运行。"""
        conversation = MagicMock()
        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()
        event_service._rerun_requested = True
        event_service._acp_internal_rerun_requested = True

        await event_service.interrupt()

        conversation.interrupt.assert_called_once()
        assert event_service._rerun_requested is False
        assert event_service._acp_internal_rerun_requested is False

    @pytest.mark.asyncio
    async def test_internal_acp_rerun_does_not_override_explicit_interrupt(
        self, event_service
    ):
        """当内部 ACP 中断耗尽时，显式停止/暂停应该获胜。"""
        conversation = MagicMock()
        conversation.send_message = MagicMock()
        event_service._conversation = conversation
        event_service._mark_running_acp_prompt_superseded = AsyncMock(
            return_value=(True, False)
        )
        event_service.run = AsyncMock()

        async def interrupt_and_simulate_user_stop(internal_acp_rerun=False):
            assert internal_acp_rerun is True
            event_service._explicit_interrupt_generation += 1
            event_service._rerun_requested = False
            event_service._acp_internal_rerun_requested = False

        event_service.interrupt = interrupt_and_simulate_user_stop

        await event_service.send_message(Message(role="user", content=[]), run=True)

        event_service.run.assert_not_awaited()
        assert event_service._rerun_requested is False
        assert event_service._acp_internal_rerun_requested is False

    @pytest.mark.asyncio
    async def test_internal_acp_send_message_restart_rechecks_generation_in_run(
        self, event_service, tmp_path
    ):
        """较晚的显式停止/暂停应防止直接 ACP 重新启动。"""
        agent = ACPAgent(acp_command=["echo", "test"])
        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            max_iteration_per_run=3,
            stuck_detection=False,
        )
        mock_arun = AsyncMock()
        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()
        event_service._mark_running_acp_prompt_superseded = AsyncMock(
            return_value=(True, False)
        )
        event_service.interrupt = AsyncMock()

        async def status_with_late_explicit_interrupt():
            event_service._explicit_interrupt_generation += 1
            event_service._rerun_requested = False
            event_service._acp_internal_rerun_requested = False
            return ConversationExecutionStatus.PAUSED

        event_service._get_execution_status = status_with_late_explicit_interrupt

        with patch.object(conversation, "arun", mock_arun):
            await event_service.send_message(Message(role="user", content=[]), run=True)

        event_service.interrupt.assert_awaited_once_with(internal_acp_rerun=True)
        mock_arun.assert_not_awaited()
        assert event_service._run_task is None
        assert event_service._rerun_requested is False
        assert event_service._acp_internal_rerun_requested is False

    @pytest.mark.asyncio
    async def test_internal_acp_rerun_rechecks_explicit_interrupt_before_restart(
        self, event_service, tmp_path
    ):
        """在最终重新启动状态检查期间，显式停止/暂停应该获胜。"""
        agent = ACPAgent(acp_command=["echo", "test"])
        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            max_iteration_per_run=3,
            stuck_detection=False,
        )
        mock_arun = AsyncMock()
        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()
        event_service._rerun_requested = True
        event_service._acp_internal_rerun_requested = True

        status_calls = 0

        async def status_with_late_explicit_interrupt():
            nonlocal status_calls
            status_calls += 1
            if status_calls == 1:
                return ConversationExecutionStatus.IDLE
            event_service._explicit_interrupt_generation += 1
            event_service._rerun_requested = False
            event_service._acp_internal_rerun_requested = False
            return ConversationExecutionStatus.PAUSED

        event_service._get_execution_status = status_with_late_explicit_interrupt

        with patch.object(conversation, "arun", mock_arun):
            await event_service.run()
            assert event_service._run_task is not None
            await asyncio.wait_for(event_service._run_task, timeout=1.0)

        mock_arun.assert_awaited_once()
        assert status_calls == 2
        assert event_service._rerun_requested is False
        assert event_service._acp_internal_rerun_requested is False

    @pytest.mark.asyncio
    async def test_late_stop_during_run_lock_wait_drops_internal_acp_rerun(
        self, event_service, tmp_path
    ):
        """在 run() 等待 _run_lock 期间到达的止损必须获胜，即使
        旧的运行任务仍然存在（其中断消耗超时）。"""
        agent = ACPAgent(acp_command=["echo", "test"])
        conversation = LocalConversation(
            agent=agent,
            workspace=str(tmp_path),
            max_iteration_per_run=3,
            stuck_detection=False,
        )
        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()
        event_service._mark_running_acp_prompt_superseded = AsyncMock(
            return_value=(True, False)
        )
        event_service.interrupt = AsyncMock()
        event_service._get_execution_status = AsyncMock(
            return_value=ConversationExecutionStatus.PAUSED
        )
        run_task = asyncio.create_task(asyncio.Event().wait())
        event_service._run_task = run_task
        await event_service._run_lock.acquire()
        try:
            send = asyncio.create_task(
                event_service.send_message(Message(role="user", content=[]), run=True)
            )
            for _ in range(200):
                if event_service.interrupt.await_count:
                    break
                await asyncio.sleep(0.01)
            event_service.interrupt.assert_awaited_once_with(internal_acp_rerun=True)
            for _ in range(5):
                await asyncio.sleep(0)

            event_service._explicit_interrupt_generation += 1
            event_service._rerun_requested = False
            event_service._acp_internal_rerun_requested = False
            event_service._run_lock.release()
            await asyncio.wait_for(send, timeout=2)
        finally:
            run_task.cancel()

        assert event_service._rerun_requested is False
        assert event_service._acp_internal_rerun_requested is False

    @pytest.mark.asyncio
    async def test_send_message_with_run_true_logs_exception(self, event_service):
        """测试来自 conversation.run() 的异常是否被捕获并记录。"""
        # 模拟对象对话及其方法
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        conversation.run = MagicMock(side_effect=RuntimeError("Test error"))

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()
        message = Message(role="user", content=[])

        # 修补记录器以验证异常日志记录
        with patch("openhands.agent_server.event_service.logger") as mock_logger:
            # 使用 run=True 调用 send_message
            await event_service.send_message(message, run=True)

            # 等待后台任务完成
            assert event_service._run_task is not None
            await event_service._run_task

            # 验证故障是否已通过其回溯记录（由 run() 的 _run_and_publish 处理程序记录）
            # 。
            #
            mock_logger.error.assert_called_once()
            fmt, detail = mock_logger.error.call_args.args
            assert fmt == "Error during conversation run\n%s"
            assert detail.startswith("Traceback (most recent call last):")
            assert detail.endswith("RuntimeError: Test error")

        # 验证 send_message 仍被调用
        conversation.send_message.assert_called_once_with(message)

        # 验证运行被调用（并引发异常）
        conversation.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_error_log_has_no_exc_info(self, event_service):
        """失败的运行的回溯记录为纯文本，而不是 exc_info：
        默认的 Rich 控制台处理程序在事件循环上同步呈现 exc_info，这会使服务器在每次运
        行失败时停止几秒（问题 #5633）。
        """
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.ERROR
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        try:
            try:
                raise ConnectionRefusedError("connection refused")
            except ConnectionRefusedError as cause:
                raise RuntimeError("LLM call failed") from cause
        except RuntimeError as chained:
            conversation.run = MagicMock(side_effect=chained)

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        records: list[logging.LogRecord] = []

        class _Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        capture = _Capture(level=logging.DEBUG)
        service_logger = logging.getLogger("openhands.agent_server.event_service")
        service_logger.addHandler(capture)
        try:
            await event_service.send_message(Message(role="user", content=[]), run=True)
            assert event_service._run_task is not None
            await event_service._run_task
        finally:
            service_logger.removeHandler(capture)

        failures = [
            r
            for r in records
            if r.getMessage().startswith("Error during conversation run")
        ]
        assert len(failures) == 1
        record = failures[0]
        assert record.levelno == logging.ERROR
        assert record.exc_info is None
        message = record.getMessage()
        assert "ConnectionRefusedError: connection refused" in message
        assert message.endswith("RuntimeError: LLM call failed")

    @pytest.mark.asyncio
    async def test_run_exception_forces_error_status(self, event_service):
        """在设置自己的 ERROR 状态 (e.g. 一个 ACP
        init_state 中冷启动失败，该故障在 run()/arun()'s 之外运行
        try-block) must be flipped to ERROR so the finally's state publish
        显示故障而不是陈旧的 IDLE/RUNNING 状态（问题
        #1024)."""
        conversation = MagicMock()
        state = MagicMock()
        # 状态从未超过 IDLE，因为故障发生在运行循环集 RUNNING 之前的 _ensure_agent_ready
        # () 中。
        #
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        conversation.run = MagicMock(side_effect=RuntimeError("init failed"))

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        await event_service.send_message(Message(role="user", content=[]), run=True)
        assert event_service._run_task is not None
        await event_service._run_task

        assert state.execution_status == ConversationExecutionStatus.ERROR
        # 最终状态更新仍会在翻转后发布。
        event_service._publish_state_update.assert_awaited()

    @pytest.mark.asyncio
    async def test_run_exception_preserves_existing_error_status(self, event_service):
        """当运行已设置 ERROR（常规智能体路径）时，逆止器
        是一个无操作——它不能破坏运行已经拥有的状态。"""
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.ERROR
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        conversation.run = MagicMock(side_effect=RuntimeError("boom"))

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        await event_service.send_message(Message(role="user", content=[]), run=True)
        assert event_service._run_task is not None
        await event_service._run_task

        assert state.execution_status == ConversationExecutionStatus.ERROR

    @pytest.mark.asyncio
    async def test_run_exception_emits_conversation_error_event(self, event_service):
        """逃避 run()/arun()'s 自身排放的故障必须浮出水面
        由逆止器作为 ConversationErrorEvent（问题＃16686）。"""
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        conversation._on_event = MagicMock()
        conversation.run = MagicMock(side_effect=RuntimeError("model does not exist"))

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        await event_service.send_message(Message(role="user", content=[]), run=True)
        assert event_service._run_task is not None
        await event_service._run_task

        # 通过 _on_event 发出单个 ConversationErrorEvent，携带异常类型和消息，以便 UI 可
        # 以呈现详细信息。
        #
        error_events = [
            call.args[0]
            for call in conversation._on_event.call_args_list
            if isinstance(call.args[0], ConversationErrorEvent)
        ]
        assert len(error_events) == 1
        assert error_events[0].code == "RuntimeError"
        assert error_events[0].detail == "model does not exist"
        assert error_events[0].source == "environment"
        assert state.execution_status == ConversationExecutionStatus.ERROR

    @pytest.mark.asyncio
    async def test_run_conversation_run_error_does_not_double_emit(self, event_service):
        """ConversationRunError 已经被 run()/arun() 浮现，所以
        backstop 不应产生重复 ConversationErrorEvent。"""
        conversation = MagicMock()
        state = MagicMock()
        state.execution_status = ConversationExecutionStatus.ERROR
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation.state = state
        conversation._state = state
        conversation.send_message = MagicMock()
        conversation._on_event = MagicMock()
        conversation.run = MagicMock(
            side_effect=ConversationRunError(
                conversation_id=uuid4(),
                original_exception=RuntimeError("already surfaced"),
            )
        )

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        await event_service.send_message(Message(role="user", content=[]), run=True)
        assert event_service._run_task is not None
        await event_service._run_task

        error_events = [
            call.args[0]
            for call in conversation._on_event.call_args_list
            if isinstance(call.args[0], ConversationErrorEvent)
        ]
        assert error_events == []

    @pytest.mark.asyncio
    async def test_send_message_with_different_message_types(self, event_service):
        """使用不同的消息类型测试 send_message。"""
        # 模拟对象对话
        conversation = MagicMock()
        conversation.send_message = MagicMock()
        conversation.run = MagicMock()

        event_service._conversation = conversation

        # 模拟对象事件循环和执行者
        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            # 创建一个每次返回一个新的协程的副作用
            mock_loop.run_in_executor.side_effect = lambda *args: self._mock_executor()

            # 使用用户消息进行测试（run=False 以避免状态检查）
            user_message = Message(role="user", content=[])
            await event_service.send_message(user_message, run=False)
            mock_loop.run_in_executor.assert_any_call(
                None, conversation.send_message, user_message
            )

            # 使用助手消息进行测试
            assistant_message = Message(role="assistant", content=[])
            await event_service.send_message(assistant_message, run=False)
            mock_loop.run_in_executor.assert_any_call(
                None, conversation.send_message, assistant_message
            )

            # 用系统消息测试
            system_message = Message(role="system", content=[])
            await event_service.send_message(system_message, run=False)
            mock_loop.run_in_executor.assert_any_call(
                None, conversation.send_message, system_message
            )

    @pytest.mark.asyncio
    async def test_load_plugin_delegates_to_conversation(self, event_service):
        """运行时插件加载通过执行器委托。"""
        conversation = MagicMock()
        conversation.load_plugin = MagicMock()
        event_service._conversation = conversation

        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            mock_loop.run_in_executor.side_effect = lambda *args: self._mock_executor()

            await event_service.load_plugin("plugin@team")

        mock_loop.run_in_executor.assert_called_once_with(
            None, conversation.load_plugin, "plugin@team"
        )

    @pytest.mark.asyncio
    async def test_load_plugin_inactive_service(self, event_service):
        """运行时插件加载需要主动对话。"""
        event_service._conversation = None

        with pytest.raises(ValueError, match="inactive_service"):
            await event_service.load_plugin("plugin@team")


class TestEventServiceRespondToConfirmation:
    """测试用例用于确认响应和拒绝处理。"""

    @pytest.mark.asyncio
    async def test_respond_to_confirmation_accept_calls_run(self, event_service):
        """接受确认应该触发运行而不是拒绝。"""
        event_service._conversation = MagicMock()
        event_service.run = AsyncMock()
        event_service.reject_pending_actions = AsyncMock()

        request = ConfirmationResponseRequest(accept=True, reason="ignored")

        await event_service.respond_to_confirmation(request)

        event_service.run.assert_awaited_once_with()
        event_service.reject_pending_actions.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_respond_to_confirmation_rejects_actions(self, event_service):
        """拒绝确认应致电reject_pending_actions并说明原因。"""
        event_service._conversation = MagicMock()
        event_service.run = AsyncMock()
        event_service.reject_pending_actions = AsyncMock()

        reason = "User rejected actions"
        request = ConfirmationResponseRequest(accept=False, reason=reason)

        await event_service.respond_to_confirmation(request)

        event_service.reject_pending_actions.assert_awaited_once_with(reason)
        event_service.run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reject_pending_actions_inactive_service(self, event_service):
        """当服务处于非活动状态时，拒绝待处理的操作应该会失败。"""
        event_service._conversation = None

        with pytest.raises(ValueError, match="inactive_service"):
            await event_service.reject_pending_actions("any reason")

    @pytest.mark.asyncio
    async def test_reject_pending_actions_invokes_conversation(self, event_service):
        """拒绝待处理的操作应通过执行器委托给对话。"""
        conversation = MagicMock()
        conversation.reject_pending_actions = MagicMock()
        event_service._conversation = conversation

        async def _mock_executor(*_args, **_kwargs):
            return None

        with patch("asyncio.get_running_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop
            mock_loop.run_in_executor.return_value = _mock_executor()

            await event_service.reject_pending_actions("custom reason")

            mock_loop.run_in_executor.assert_called_once_with(
                None, conversation.reject_pending_actions, "custom reason"
            )


class TestEventServiceIsOpen:
    """测试用例代表 EventService.is_open 方法。"""

    def test_is_open_when_conversation_is_none(self, event_service):
        """当 _conversation 为 None 时，测试 is_open 返回 False。"""
        event_service._conversation = None
        assert not event_service.is_open()

    def test_is_open_when_conversation_exists(self, event_service):
        """当 _conversation 存在时，测试 is_open 返回 True。"""
        conversation = MagicMock(spec=Conversation)
        event_service._conversation = conversation
        assert event_service.is_open()

    def test_is_open_when_conversation_is_falsy(self, event_service):
        """当 _conversation 为假时，测试 is_open 返回 False。"""
        # 使用各种虚假值进行测试
        falsy_values = [None, False, 0, "", [], {}]

        for falsy_value in falsy_values:
            event_service._conversation = falsy_value
            assert not event_service.is_open(), f"Expected False for {falsy_value}"

    def test_is_open_when_conversation_is_truthy(self, event_service):
        """当 _conversation 为真时，测试 is_open 返回 True。"""
        # 使用各种真值进行测试
        truthy_values = [
            MagicMock(spec=Conversation),
            "some_string",
            1,
            [1, 2, 3],
            {"key": "value"},
            True,
        ]

        for truthy_value in truthy_values:
            event_service._conversation = truthy_value
            assert event_service.is_open(), f"Expected True for {truthy_value}"


class TestEventServiceBodyFiltering:
    """测试用例用于 EventService 正文过滤功能。"""

    def test_event_matches_body_with_message_event(self, event_service):
        """使用包含文本内容的 MessageEvent 测试 _event_matches_body。"""
        from openhands.sdk.llm.message import TextContent

        # 创建一个包含文本内容的 MessageEvent
        message = Message(role="user", content=[TextContent(text="Hello world")])
        event = MessageEvent(id="test", source="user", llm_message=message)

        # 测试用例-不敏感匹配
        assert event_service._event_matches_body(event, "hello")
        assert event_service._event_matches_body(event, "WORLD")
        assert event_service._event_matches_body(event, "Hello world")
        assert event_service._event_matches_body(event, "llo wor")

        # 测试不匹配
        assert not event_service._event_matches_body(event, "goodbye")
        assert not event_service._event_matches_body(event, "xyz")

    def test_event_matches_body_with_non_message_event(self, event_service):
        """使用非 MessageEvent 测试 _event_matches_body（应返回 False）。"""
        from openhands.sdk.event.user_action import PauseEvent

        # 创建一个非MessageEvent
        event = PauseEvent(id="test")

        # 对于非 MessageEvent 应该始终返回 False
        assert not event_service._event_matches_body(event, "any text")
        assert not event_service._event_matches_body(event, "")

    def test_event_matches_body_with_empty_content(self, event_service):
        """使用包含空内容的 MessageEvent 测试 _event_matches_body。"""
        # 创建一个内容为空的 MessageEvent
        message = Message(role="user", content=[])
        event = MessageEvent(id="test", source="user", llm_message=message)

        # 不应匹配任何非空文本
        assert not event_service._event_matches_body(event, "any text")
        # 空字符串应该匹配空内容（空字符串包含空字符串）
        assert event_service._event_matches_body(event, "")

    @pytest.mark.asyncio
    async def test_search_events_with_body_filter_integration(self, event_service):
        """使用真实的 MessageEvents 使用主体过滤器测试 search_events。"""
        from openhands.sdk.llm.message import TextContent

        # 创建与 MessageEvents 的对话，其中包含不同的文本
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)

        events = [
            MessageEvent(
                id="event1",
                source="user",
                llm_message=Message(
                    role="user", content=[TextContent(text="Hello world")]
                ),
            ),
            MessageEvent(
                id="event2",
                source="agent",
                llm_message=Message(
                    role="assistant", content=[TextContent(text="How can I help?")]
                ),
            ),
            MessageEvent(
                id="event3",
                source="user",
                llm_message=Message(
                    role="user", content=[TextContent(text="Create a Python script")]
                ),
            ),
        ]

        state.events = events
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state

        event_service._conversation = conversation

        # 按“hello”测试过滤（应匹配 event1）
        result = await event_service.search_events(body="hello")
        assert len(result.items) == 1
        assert result.items[0].id == "event1"

        # 按“Python”测试过滤（应匹配 event3）
        result = await event_service.search_events(body="python")
        assert len(result.items) == 1
        assert result.items[0].id == "event3"

        # 通过“help”测试过滤（应匹配 event2）
        result = await event_service.search_events(body="help")
        assert len(result.items) == 1
        assert result.items[0].id == "event2"

        # 通过不匹配的文本测试过滤
        result = await event_service.search_events(body="nonexistent")
        assert len(result.items) == 0

    @pytest.mark.asyncio
    async def test_count_events_with_body_filter_integration(self, event_service):
        """使用真实的 MessageEvents 使用主体过滤器测试 count_events。"""
        from openhands.sdk.llm.message import TextContent

        # 创建与 MessageEvents 的对话，其中包含不同的文本
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)

        events = [
            MessageEvent(
                id="event1",
                source="user",
                llm_message=Message(
                    role="user", content=[TextContent(text="Hello world")]
                ),
            ),
            MessageEvent(
                id="event2",
                source="agent",
                llm_message=Message(
                    role="assistant", content=[TextContent(text="Hello there")]
                ),
            ),
            MessageEvent(
                id="event3",
                source="user",
                llm_message=Message(
                    role="user", content=[TextContent(text="Create a Python script")]
                ),
            ),
        ]

        state.events = events
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state

        event_service._conversation = conversation

        # 测试按“hello”计数（应匹配 2 个事件）
        result = await event_service.count_events(body="hello")
        assert result == 2

        # 按“Python”测试计数（应匹配 1 个事件）
        result = await event_service.count_events(body="python")
        assert result == 1

        # 通过不匹配的文本测试计数
        result = await event_service.count_events(body="nonexistent")
        assert result == 0


class TestEventServiceRun:
    """测试用例代表 EventService.run 方法。"""

    @pytest.mark.asyncio
    async def test_wait_for_run_completion_waits_for_task_finalization(
        self, event_service
    ):
        release_run = asyncio.Event()
        event_service._get_execution_status = AsyncMock(
            return_value=ConversationExecutionStatus.FINISHED
        )
        event_service._run_task = asyncio.create_task(release_run.wait())

        waiter = asyncio.create_task(event_service.wait_for_run_completion(timeout=1))
        await asyncio.sleep(0)

        assert not waiter.done()
        release_run.set()
        assert await waiter == ConversationExecutionStatus.FINISHED

    @pytest.mark.asyncio
    async def test_wait_for_run_completion_timeout_does_not_cancel_run(
        self, event_service
    ):
        release_run = asyncio.Event()
        run_task = asyncio.create_task(release_run.wait())
        event_service._run_task = run_task

        with pytest.raises(TimeoutError, match="Conversation run timed out"):
            await event_service.wait_for_run_completion(timeout=0.01)

        assert not run_task.done()
        release_run.set()
        await run_task

    @pytest.mark.asyncio
    async def test_run_inactive_service(self, event_service):
        """测试当对话不活跃时 run 会引发 ValueError。"""
        event_service._conversation = None

        with pytest.raises(ValueError, match="inactive_service"):
            await event_service.run()

    @pytest.mark.asyncio
    async def test_run_already_running_by_status(self, event_service):
        """当对话已在运行时，测试 run 是否引发 ValueError。"""
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)
        state.execution_status = ConversationExecutionStatus.RUNNING
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state

        event_service._conversation = conversation

        with pytest.raises(ValueError, match="conversation_already_running"):
            await event_service.run()

    @pytest.mark.asyncio
    async def test_run_already_running_by_task(self, event_service):
        """测试当存在活动的运行任务时，运行是否引发 ValueError。"""
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state

        event_service._conversation = conversation

        # 创建一个未完成的模拟对象任务
        mock_task = MagicMock()
        mock_task.done.return_value = False
        event_service._run_task = mock_task

        with pytest.raises(ValueError, match="conversation_already_running"):
            await event_service.run()

    @pytest.mark.asyncio
    async def test_run_already_running_does_not_wait_for_state_lock(
        self, event_service
    ):
        """实时运行在整个步骤中保持状态锁 (e.g. 一个长工具
        打电话）； run()必须立即拒绝，而不是在后面阻塞。"""
        lock_released = threading.Event()
        state = MagicMock(spec=ConversationState)
        state.execution_status = ConversationExecutionStatus.RUNNING
        state.__enter__ = MagicMock(
            side_effect=lambda: (lock_released.wait(10), state)[1]
        )
        state.__exit__ = MagicMock(return_value=None)
        conversation = MagicMock(spec=Conversation)
        conversation._state = state
        event_service._conversation = conversation

        run_task = asyncio.create_task(asyncio.Event().wait())
        event_service._run_task = run_task
        try:
            with pytest.raises(ValueError, match="conversation_already_running"):
                await asyncio.wait_for(event_service.run(), timeout=2)
            state.__enter__.assert_not_called()
        finally:
            lock_released.set()
            run_task.cancel()

    @pytest.mark.asyncio
    async def test_run_starts_background_task(self, event_service):
        """测试 run 启动后台任务并立即返回。"""
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state
        conversation.run = MagicMock()

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        # 调用 run - 应该立即返回
        await event_service.run()

        # 验证任务已创建
        assert event_service._run_task is not None

        # 等待后台任务完成
        await event_service._run_task

        # 验证 conversation.run 被调用
        conversation.run.assert_called_once()

        # 验证运行完成后已发布状态更新
        event_service._publish_state_update.assert_called()

    @pytest.mark.asyncio
    async def test_run_publishes_state_update_on_completion(self, event_service):
        """测试运行完成后发布状态更新。"""
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state
        conversation.run = MagicMock()

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        await event_service.run()
        await event_service._run_task  # 等待完成

        # 运行完成后应发布状态更新
        event_service._publish_state_update.assert_called()

    @pytest.mark.asyncio
    async def test_run_publishes_state_update_on_error(self, event_service):
        """测试即使运行引发错误，运行也会发布状态更新。"""
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)
        state.execution_status = ConversationExecutionStatus.IDLE
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state
        conversation.run = MagicMock(side_effect=RuntimeError("Test error"))

        event_service._conversation = conversation
        event_service._publish_state_update = AsyncMock()

        await event_service.run()

        # 等待后台任务完成（它会引发但被捕获）
        try:
            await event_service._run_task
        except RuntimeError:
            pass  # 预计

        # 状态更新仍应发布（在finally块中）
        event_service._publish_state_update.assert_called()


class _PausingWriter:
    """每次写入过程中运行 ``pause`` 的文本文件句柄。

    前半部分在 ``pause`` 运行之前刷新到磁盘，因此 ``pause`` 会像并发读取器在写入过程
    中一样查看该文件。
    """

    def __init__(self, handle, pause):
        self._handle = handle
        self._pause = pause

    def __enter__(self):
        self._handle.__enter__()
        return self

    def __exit__(self, *exc_info):
        return self._handle.__exit__(*exc_info)

    def write(self, data):
        half = len(data) // 2
        written = self._handle.write(data[:half])
        self._handle.flush()
        self._pause()
        return written + self._handle.write(data[half:])

    def __getattr__(self, name):
        return getattr(self._handle, name)


def _pause_text_writes_halfway(monkeypatch, pause) -> None:
    """在每次文本模式写入 (``mode="w"``) 的过程中运行 ``pause``。"""
    original_open = io.open

    def open_(file, mode="r", *args, **kwargs):
        handle = original_open(file, mode, *args, **kwargs)
        return _PausingWriter(handle, pause) if mode == "w" else handle

    monkeypatch.setattr(io, "open", open_)


class TestEventServiceSaveMeta:
    """测试用例代表 EventService.save_meta 方法。"""

    @pytest.mark.asyncio
    async def test_save_meta_preserves_updated_at(self, event_service, tmp_path):
        """测试 save_meta 不会修改 updated_at。

        服务器重新启动时，每个对话的 save_meta 都会被调用。 在修复之前，save_meta 标
        记为 updated_at = utc_now()，因此所
        有对话似乎都已在重新启动时更新。
        """
        original_updated_at = datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC)
        event_service.stored.updated_at = original_updated_at
        event_service.conversations_dir = tmp_path
        conv_dir = tmp_path / event_service.stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)

        await event_service.save_meta()

        # 内存中的值必须保持不变
        assert event_service.stored.updated_at == original_updated_at

        # 已持久化值也必须匹配
        meta_file = conv_dir / "meta.json"
        loaded = StoredConversation.model_validate_json(meta_file.read_text())
        assert loaded.updated_at == original_updated_at

    @pytest.mark.asyncio
    async def test_save_meta_round_trips_title_prompt(self, event_service, tmp_path):
        event_service.stored.prompt = (
            "Create a concise title for {conversation_content}."
        )
        event_service.conversations_dir = tmp_path
        conv_dir = tmp_path / event_service.stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)

        await event_service.save_meta()

        meta_file = conv_dir / "meta.json"
        loaded = StoredConversation.model_validate_json(meta_file.read_text())
        assert loaded.prompt == ("Create a concise title for {conversation_content}.")

    @pytest.mark.asyncio
    async def test_save_meta_round_trips_agent_definition_mcp_secrets(
        self, sample_stored_conversation, tmp_path
    ):
        cipher = Cipher("stored-conversation-mcp-secret")
        sample_stored_conversation.agent_definitions = [
            AgentDefinition(
                name="web-researcher",
                mcp_config=coerce_mcp_config(
                    {
                        "tavily": {
                            "command": "npx",
                            "args": ["-y", "tavily-mcp@0.2.1"],
                            "env": {"TAVILY_API_KEY": "${TAVILY_API_KEY}"},
                        }
                    }
                ),
            )
        ]
        service = EventService(
            stored=sample_stored_conversation,
            conversations_dir=tmp_path,
            cipher=cipher,
        )
        service.conversation_dir.mkdir(parents=True)

        await service.save_meta()

        payload = (service.conversation_dir / "meta.json").read_text()
        assert "${TAVILY_API_KEY}" not in payload
        loaded = StoredConversation.model_validate_json(
            payload,
            context={"cipher": cipher},
        )
        assert loaded.agent_definitions[0].mcp_config is not None
        env = loaded.agent_definitions[0].mcp_config["tavily"].env
        assert env is not None
        assert env["TAVILY_API_KEY"].get_secret_value() == "${TAVILY_API_KEY}"

    @pytest.mark.asyncio
    async def test_save_meta_never_exposes_a_partial_meta_json(
        self, event_service, tmp_path, monkeypatch
    ):
        """保存期间 meta.json 的读取器会看到上一个完整文件。"""
        event_service.conversations_dir = tmp_path
        event_service.conversation_dir.mkdir()
        meta_file = event_service.conversation_dir / "meta.json"
        await event_service.save_meta()
        previous = meta_file.read_bytes()
        seen_mid_save: list[bytes] = []
        _pause_text_writes_halfway(
            monkeypatch, lambda: seen_mid_save.append(meta_file.read_bytes())
        )

        event_service.stored.title = "renamed"
        await event_service.save_meta()

        assert seen_mid_save == [previous]
        saved = StoredConversation.model_validate_json(meta_file.read_text())
        assert saved.title == "renamed"

    @pytest.mark.asyncio
    async def test_trajectory_zip_built_during_save_meta_has_no_partial_meta_json(
        self, sample_stored_conversation, tmp_path, monkeypatch
    ):
        """在保存过程中构建的轨迹拉链包含完整的已脱敏meta.json。

        部分 JSON 不会解析，因此 zip 无法对其进行编辑，并且其中加密的机密将按原样存档
        。
        """
        sample_stored_conversation.secrets = {
            "GITHUB_TOKEN": StaticSecret(value=SecretStr("ghp_zip_during_save"))
        }
        service = EventService(
            stored=sample_stored_conversation,
            conversations_dir=tmp_path,
            cipher=Cipher("trajectory-zip-during-save-meta"),
        )
        service.conversation_dir.mkdir()
        await service.save_meta()
        meta_file = service.conversation_dir / "meta.json"
        assert FERNET_TOKEN_PREFIX in meta_file.read_text()
        archive_path = tmp_path / "trajectory.zip"
        _pause_text_writes_halfway(
            monkeypatch,
            lambda: _create_zip_from_directory(service.conversation_dir, archive_path),
        )

        service.stored.title = "renamed"
        await service.save_meta()

        with zipfile.ZipFile(archive_path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        assert not [
            name
            for name, data in members.items()
            if FERNET_TOKEN_PREFIX.encode() in data
        ]
        meta = json.loads(members[f"{service.stored.id.hex}/meta.json"])
        assert meta["secrets"]["GITHUB_TOKEN"]["value"] == REDACTED_SECRET_VALUE

    @pytest.mark.asyncio
    async def test_switch_acp_model_persists_via_conversation(self, tmp_path):
        """switch_acp_model 代表参加 SDK 对话，该对话坚持
        新模型到base_state.json（单一事实来源）。

        meta.json 不再携带智能体，因此事件服务必须不镜像那里的开关。 SDK
        ``LocalConversation.switch_acp_model``将
        ``state.agent``设置为携带新``acp_model``的智能体，自动保存路径写入
        base_state.json； 恢复后智能体被重建
        from base_state.
        """
        stored = StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir=str(tmp_path)),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
        )
        service = EventService(stored=stored, conversations_dir=tmp_path)
        conv_dir = tmp_path / stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)

        # 写一个 meta.json 提前告知，以证明下面的断言不会导致切换覆盖一个 *现有的*
        # meta.json 与一个智能体镜像，而不是因为过于简单而通过 meta.json 从未创建过。
        #
        await service.save_meta()
        meta_file = conv_dir / "meta.json"
        assert meta_file.exists()
        assert "agent" not in json.loads(meta_file.read_text())

        # 代替现场对话； 协议级切换和base_state 持久化由SDK的自身测试覆盖——这里我们只验
        # 证委托和meta.json不是用智能体写的。
        #
        service._conversation = MagicMock()

        await service.switch_acp_model("new-model")

        # 实时切换被委托给 SDK 对话（持续到 base_state.json）。
        #
        service._conversation.switch_acp_model.assert_called_once_with("new-model")
        # StoredConversation 不再带有智能体。
        assert not hasattr(service.stored, "agent")
        # meta.json 仍然存在，并且从未获得过智能体镜像。
        assert meta_file.exists()
        assert "agent" not in json.loads(meta_file.read_text())

    @pytest.mark.asyncio
    async def test_switch_acp_model_inactive_service_raises_value_error(self, tmp_path):
        """不活跃的服务（没有实时对话）会引发共享
        ``inactive_service`` ValueError — 与其他事件服务方法一致 — 路由器将其映射到
        400。 它不再是一个
        RuntimeError: SDK 现在推迟（而不是拒绝）之前的切换
        第一个 run()，因此这里唯一的故障模式是关闭/从未启动的服务。
        """

        stored = StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir=str(tmp_path)),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
        )
        service = EventService(stored=stored, conversations_dir=tmp_path)
        # _conversation 默认为 None（服务未启动）。
        assert service._conversation is None

        with pytest.raises(ValueError, match="inactive_service"):
            await service.switch_acp_model("new-model")


class TestEventServiceStartWithRunningStatus:
    """测试用例用于 EventService.start 处理 RUNNING 执行状态。"""

    @pytest.mark.asyncio
    async def test_start_sets_error_status_when_running_from_disk(
        self, event_service, tmp_path
    ):
        """测试 start() 设置 ERROR 状态并添加 AgentErrorEvent。

        当从磁盘加载状态为 RUNNING 的对话时，表示进程崩溃或意外终止。 EventService 应
        该：
        1. 将 execution_status 设置为 ERROR
        2. 为第一个不匹配的操作添加 AgentErrorEvent 以通知智能体
        """
        from openhands.sdk.event import AgentErrorEvent
        from openhands.sdk.event.llm_convertible import ActionEvent
        from openhands.sdk.llm import MessageToolCall, TextContent
        from openhands.tools.terminal import TerminalAction

        # 设置路径
        event_service.conversations_dir = tmp_path
        conv_dir = tmp_path / event_service.stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)

        # 更新工作区以使用有效的临时目录
        event_service.stored.workspace = LocalWorkspace(working_dir=str(tmp_path))

        with patch(
            "openhands.agent_server.event_service.LocalConversation"
        ) as MockConversation:
            mock_conv = MagicMock()
            mock_state = MagicMock()
            mock_agent = MagicMock()

            # 创建一个不匹配的动作事件（不带观测结果的动作）
            unmatched_action = ActionEvent(
                source="agent",
                thought=[TextContent(text="I need to run ls command")],
                action=TerminalAction(command="ls"),
                tool_name="terminal",
                tool_call_id="call_1",
                tool_call=MessageToolCall(
                    id="call_1",
                    name="terminal",
                    arguments='{"command": "ls"}',
                    origin="completion",
                ),
                llm_response_id="response_1",
            )

            # 设置模拟对象状态与RUNNING状态以及不匹配的动作
            mock_state.execution_status = ConversationExecutionStatus.RUNNING
            mock_state.events = [unmatched_action]
            mock_state.stats = MagicMock()

            # 设置模拟对象智能体
            mock_agent.get_all_llms.return_value = []

            mock_conv._state = mock_state
            mock_conv.state = mock_state
            mock_conv.agent = mock_agent
            mock_conv._on_event = MagicMock()
            MockConversation.return_value = mock_conv

            # 呼叫开始
            await event_service.start()

            # 验证 execution_status 已更改为 ERROR
            assert mock_state.execution_status == ConversationExecutionStatus.ERROR

            # 验证 AgentErrorEvent 是通过 _on_event 添加的
            mock_conv._on_event.assert_called()
            call_args = mock_conv._on_event.call_args_list

            # 找到 AgentErrorEvent 呼叫
            error_event_calls = [
                call for call in call_args if isinstance(call[0][0], AgentErrorEvent)
            ]
            assert len(error_event_calls) == 1

            error_event = error_event_calls[0][0][0]
            assert error_event.tool_name == "terminal"
            assert error_event.tool_call_id == "call_1"
            assert "restart occurred" in error_event.error
            assert "fatal memory error" in error_event.error

    @pytest.mark.asyncio
    async def test_start_does_not_add_error_event_when_no_unmatched_actions(
        self, event_service, tmp_path
    ):
        """测试 start() 在没有不匹配操作的情况下不会添加 AgentErrorEvent。

        即使execution_status是RUNNING，如果没有不匹配的动作，也不应该添加
        AgentErrorEvent。
        """
        from openhands.sdk.event import AgentErrorEvent

        # 设置路径
        event_service.conversations_dir = tmp_path
        conv_dir = tmp_path / event_service.stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)

        # 更新工作区以使用有效的临时目录
        event_service.stored.workspace = LocalWorkspace(working_dir=str(tmp_path))

        with patch(
            "openhands.agent_server.event_service.LocalConversation"
        ) as MockConversation:
            mock_conv = MagicMock()
            mock_state = MagicMock()
            mock_agent = MagicMock()

            # 将模拟对象状态设置为 RUNNING 状态，但没有事件（没有不匹配的操作）
            mock_state.execution_status = ConversationExecutionStatus.RUNNING
            mock_state.events = []
            mock_state.stats = MagicMock()

            # 设置模拟对象智能体
            mock_agent.get_all_llms.return_value = []

            mock_conv._state = mock_state
            mock_conv.state = mock_state
            mock_conv.agent = mock_agent
            mock_conv._on_event = MagicMock()
            MockConversation.return_value = mock_conv

            # 呼叫开始
            await event_service.start()

            # 验证 execution_status 已更改为 ERROR
            assert mock_state.execution_status == ConversationExecutionStatus.ERROR

            # 验证 _on_event 是通过 AgentErrorEvent 调用的不
            error_event_calls = [
                call
                for call in mock_conv._on_event.call_args_list
                if isinstance(call[0][0], AgentErrorEvent)
            ]
            assert len(error_event_calls) == 0

    @pytest.mark.asyncio
    async def test_start_does_nothing_when_status_not_running(
        self, event_service, tmp_path
    ):
        """测试，start() 不修改 execution_status 当它不是 RUNNING."""
        from openhands.sdk.event import AgentErrorEvent

        # 设置路径
        event_service.conversations_dir = tmp_path
        conv_dir = tmp_path / event_service.stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)

        # 更新工作区以使用有效的临时目录
        event_service.stored.workspace = LocalWorkspace(working_dir=str(tmp_path))

        with patch(
            "openhands.agent_server.event_service.LocalConversation"
        ) as MockConversation:
            mock_conv = MagicMock()
            mock_state = MagicMock()
            mock_agent = MagicMock()

            # 设置模拟对象状态和IDLE状态
            mock_state.execution_status = ConversationExecutionStatus.IDLE
            mock_state.events = []
            mock_state.stats = MagicMock()

            # 设置模拟对象智能体
            mock_agent.get_all_llms.return_value = []

            mock_conv._state = mock_state
            mock_conv.state = mock_state
            mock_conv.agent = mock_agent
            mock_conv._on_event = MagicMock()
            MockConversation.return_value = mock_conv

            # 呼叫开始
            await event_service.start()

            # 验证 execution_status 仍为 IDLE
            assert mock_state.execution_status == ConversationExecutionStatus.IDLE

            # 验证 _on_event 是通过 AgentErrorEvent 调用的不
            error_event_calls = [
                call
                for call in mock_conv._on_event.call_args_list
                if isinstance(call[0][0], AgentErrorEvent)
            ]
            assert len(error_event_calls) == 0

    @pytest.mark.asyncio
    async def test_start_skips_error_event_when_observation_already_exists(
        self, event_service, tmp_path
    ):
        """如果加载状态已经带有一个，则不要合成 AgentErrorEvent
        ObservationBaseEvent 表示不匹配操作的 tool_call_id。

        重现 get_unmatched_actions 遗漏的间隙：与 tool_call_id 匹配但不与 action_id
        匹配的
        ObservationEvent (e.g. action_id 在重播时重写）——如果没有这个保护，我们会发出
        一个重复的类似观测结果的事件。
        """
        event_service.conversations_dir = tmp_path
        conv_dir = tmp_path / event_service.stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)
        event_service.stored.workspace = LocalWorkspace(working_dir=str(tmp_path))

        with patch(
            "openhands.agent_server.event_service.LocalConversation"
        ) as MockConversation:
            mock_conv = MagicMock()
            mock_state = MagicMock()
            mock_agent = MagicMock()

            unmatched_action = ActionEvent(
                source="agent",
                thought=[TextContent(text="run ls")],
                action=TerminalAction(command="ls"),
                tool_name="terminal",
                tool_call_id="call_1",
                tool_call=MessageToolCall(
                    id="call_1",
                    name="terminal",
                    arguments='{"command": "ls"}',
                    origin="completion",
                ),
                llm_response_id="response_1",
            )
            # 观测结果与 tool_call_id 匹配，但 action_id 不同，因此
            # get_unmatched_actions 仍将操作报告为不匹配。
            #
            stale_observation = ObservationEvent(
                observation=TerminalObservation.from_text(
                    "done", command="ls", exit_code=0
                ),
                action_id="some_other_action_id",
                tool_name="terminal",
                tool_call_id="call_1",
            )

            mock_state.execution_status = ConversationExecutionStatus.RUNNING
            mock_state.events = [unmatched_action, stale_observation]
            mock_state.stats = MagicMock()

            mock_agent.get_all_llms.return_value = []
            mock_conv._state = mock_state
            mock_conv.state = mock_state
            mock_conv.agent = mock_agent
            mock_conv._on_event = MagicMock()
            MockConversation.return_value = mock_conv

            await event_service.start()

            assert mock_state.execution_status == ConversationExecutionStatus.ERROR
            error_event_calls = [
                call
                for call in mock_conv._on_event.call_args_list
                if isinstance(call[0][0], AgentErrorEvent)
            ]
            assert len(error_event_calls) == 0

    @pytest.mark.skipif(not shutil.which("git"), reason="git executable not found")
    @pytest.mark.asyncio
    async def test_start_initializes_workspace_as_git_repo(
        self, event_service, tmp_path
    ):
        """新的工作区目录应该在 start() 期间被 `git init`-ed。

        如果没有这个，非存储库工作区和智能体创建的文件上的 /api/git/changes 500 永远
        不会出现在“更改”选项卡中。
        """
        # 安排
        event_service.conversations_dir = tmp_path
        conv_dir = tmp_path / event_service.stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir = tmp_path / "fresh_workspace"
        event_service.stored.workspace = LocalWorkspace(working_dir=str(workspace_dir))

        with patch(
            "openhands.agent_server.event_service.LocalConversation"
        ) as MockConversation:
            mock_conv = MagicMock()
            mock_state = MagicMock()
            mock_agent = MagicMock()
            mock_state.execution_status = ConversationExecutionStatus.IDLE
            mock_state.events = []
            mock_state.stats = MagicMock()
            mock_agent.get_all_llms.return_value = []
            mock_conv._state = mock_state
            mock_conv.state = mock_state
            mock_conv.agent = mock_agent
            mock_conv._on_event = MagicMock()
            MockConversation.return_value = mock_conv

            # 法案
            await event_service.start()

        # 断言
        assert (workspace_dir / ".git").exists()

    @pytest.mark.skipif(not shutil.which("git"), reason="git executable not found")
    @pytest.mark.asyncio
    async def test_start_is_idempotent_for_already_initialized_repo(
        self, event_service, tmp_path
    ):
        """恢复现有存储库上的对话不得重新初始化它。

        防止意外的双重初始化可能会破坏用户已经提交的工作区上的 refs/HEAD。
        """
        # 安排 — 将工作区目录预初始化为 git 存储库并捕获 .git 目录的标识，以便我们可以检
        # 测重新初始化。
        #
        event_service.conversations_dir = tmp_path
        conv_dir = tmp_path / event_service.stored.id.hex
        conv_dir.mkdir(parents=True, exist_ok=True)
        workspace_dir = tmp_path / "existing_repo"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        from openhands.sdk.git.utils import run_git_command

        run_git_command(["git", "init"], workspace_dir)
        marker = workspace_dir / ".git" / "_idempotency_marker"
        marker.write_text("preexisting")

        event_service.stored.workspace = LocalWorkspace(working_dir=str(workspace_dir))

        with patch(
            "openhands.agent_server.event_service.LocalConversation"
        ) as MockConversation:
            mock_conv = MagicMock()
            mock_state = MagicMock()
            mock_agent = MagicMock()
            mock_state.execution_status = ConversationExecutionStatus.IDLE
            mock_state.events = []
            mock_state.stats = MagicMock()
            mock_agent.get_all_llms.return_value = []
            mock_conv._state = mock_state
            mock_conv.state = mock_state
            mock_conv.agent = mock_agent
            mock_conv._on_event = MagicMock()
            MockConversation.return_value = mock_conv

            # 法案
            await event_service.start()

        # 断言 - 存储库仍然存在，并且我们的标记幸存下来（无需重新初始化）。
        assert (workspace_dir / ".git").exists()
        assert marker.exists()
        assert marker.read_text() == "preexisting"


class TestEventServiceConcurrentSubscriptions:
    """测试用例用于并发订阅处理，无需死锁。

    这些测试验证了将异步操作移动到 FIFOLock 上下文之外的修复，当多个订阅者活跃或订阅
    者慢时，防止死锁。
    """

    @pytest.fixture
    def mock_conversation_with_real_lock(self):
        """创建与真实FIFOLock的模拟对象对话，用于测试并发。"""
        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)

        # 使用真实的FIFOLock来测试实际的锁定行为
        real_lock = FIFOLock()
        state._lock = real_lock
        state.__enter__ = lambda self: (real_lock.acquire(), self)[1]
        state.__exit__ = lambda self, *args: real_lock.release()

        # 设置 ConversationStateUpdateEvent 所需的最小状态属性
        state.events = []
        state.execution_status = ConversationExecutionStatus.IDLE
        state.model_dump = MagicMock(
            return_value={
                "execution_status": "idle",
                "events": [],
            }
        )

        conversation._state = state
        return conversation

    @pytest.mark.asyncio
    async def test_concurrent_subscriptions_no_deadlock(
        self, event_service, mock_conversation_with_real_lock
    ):
        """测试多个并发订阅不会导致死锁。

        此测试创建多个并发订阅的订阅者，并验证所有订阅是否完成而不会挂起。
        """
        event_service._conversation = mock_conversation_with_real_lock
        received_events: list[list[Event]] = [[] for _ in range(3)]

        class TestSubscriber(Subscriber[Event]):
            def __init__(self, index: int):
                self.index = index

            async def __call__(self, event: Event):
                received_events[self.index].append(event)

        # 同时订阅多个订阅者
        subscribers = [TestSubscriber(i) for i in range(3)]

        # 使用 asyncio.wait_for 检测死锁和超时
        async def subscribe_all():
            tasks = [event_service.subscribe_to_events(sub) for sub in subscribers]
            return await asyncio.gather(*tasks)

        # 如果没有死锁，这应该在 2 秒内完成
        subscriber_ids = await asyncio.wait_for(subscribe_all(), timeout=2.0)

        # 验证所有订阅是否成功
        assert len(subscriber_ids) == 3
        for sub_id in subscriber_ids:
            assert sub_id is not None

        # 验证所有订阅者收到初始状态事件
        for i, events in enumerate(received_events):
            assert len(events) == 1, f"Subscriber {i} should have received 1 event"
            assert isinstance(events[0], ConversationStateUpdateEvent)

    @pytest.mark.asyncio
    async def test_subscription_receives_state_when_conversation_not_open(
        self, event_service
    ):
        """非活动服务仍需要初始状态事件才能为 WS 做好准备。"""
        received_events: list[Event] = []

        class TestSubscriber(Subscriber[Event]):
            async def __call__(self, event: Event):
                received_events.append(event)

        await event_service.subscribe_to_events(TestSubscriber())

        assert len(received_events) == 1
        event = received_events[0]
        assert isinstance(event, ConversationStateUpdateEvent)
        assert event.key == "execution_status"
        assert event.value == ConversationExecutionStatus.IDLE

    @pytest.mark.asyncio
    async def test_slow_subscriber_does_not_block_lock(
        self, event_service, mock_conversation_with_real_lock
    ):
        """测试慢速订阅者在 I/O 期间是否不持有锁。

        此测试验证锁在异步发送操作之前被释放，即使订阅者速度缓慢，也允许其他操作继续
        进行。
        """
        event_service._conversation = mock_conversation_with_real_lock
        state = mock_conversation_with_real_lock._state
        lock_held_during_sleep = False

        class SlowSubscriber(Subscriber[Event]):
            async def __call__(self, event: Event):
                nonlocal lock_held_during_sleep
                # 检查是否锁是在异步如果修正是正确的，那么 [操作] 锁应该不他被关在这里
                #
                lock_held_during_sleep = state._lock.locked()
                await asyncio.sleep(0.1)  # 模拟慢速 I/O

        slow_subscriber = SlowSubscriber()

        # 与慢速订阅者一起订阅
        await asyncio.wait_for(
            event_service.subscribe_to_events(slow_subscriber),
            timeout=2.0,
        )

        # 锁应该在异步睡眠期间保留不（它在等待 subscriber() 调用之前释放）
        #
        assert not lock_held_during_sleep, (
            "Lock should not be held during async subscriber call"
        )

    @pytest.mark.asyncio
    async def test_subscription_snapshot_wait_does_not_block_event_loop(
        self, event_service, mock_conversation_with_real_lock
    ):
        """创建初始状态快照不得停止异步循环。

        重连 WebSocket 订阅者在订阅开始之前会获取初始状态快照流式传输事件。 如果快照
        创建需要等待会话的同步  FIFOLock它必须在 worker 中
        执行线程; 如果它在时阻塞异步任务完成后，整个服务器循环停止回答存活探针。
        """
        event_service._conversation = mock_conversation_with_real_lock

        original_snapshot = event_service._create_state_update_event_sync
        release_snapshot = threading.Event()
        timings: dict[str, float] = {}

        def blocking_snapshot() -> ConversationStateUpdateEvent:
            timings["snapshot_start"] = time.monotonic()
            release_snapshot.wait(timeout=1.0)
            timings["snapshot_end"] = time.monotonic()
            return original_snapshot()

        event_service._create_state_update_event_sync = blocking_snapshot

        def release_after_delay() -> None:
            time.sleep(0.2)
            release_snapshot.set()

        threading.Thread(target=release_after_delay, daemon=True).start()

        class TestSubscriber(Subscriber[Event]):
            async def __call__(self, event: Event):
                return None

        async def heartbeat() -> None:
            await asyncio.sleep(0.05)
            timings["heartbeat"] = time.monotonic()

        await asyncio.wait_for(
            asyncio.gather(
                event_service.subscribe_to_events(TestSubscriber()),
                heartbeat(),
            ),
            timeout=1.0,
        )

        assert "snapshot_end" in timings
        assert "heartbeat" in timings
        assert timings["heartbeat"] < timings["snapshot_end"], (
            "subscribe_to_events blocked the async loop while waiting for the "
            "state snapshot lock"
        )

    @pytest.mark.asyncio
    async def test_subscription_during_state_update(
        self, event_service, mock_conversation_with_real_lock
    ):
        """测试订阅和状态更新是否可以在没有死锁的情况下交错。

        此测试模拟在发布状态更新时发生订阅的场景，验证没有死锁发生。
        """
        event_service._conversation = mock_conversation_with_real_lock
        events_received: list[Event] = []

        class CollectorSubscriber(Subscriber[Event]):
            async def __call__(self, event: Event):
                events_received.append(event)
                # 模拟一些异步工作
                await asyncio.sleep(0.01)

        # 一、订阅收藏家
        collector = CollectorSubscriber()
        await event_service.subscribe_to_events(collector)

        # 现在，当可能发生另一个订阅时触发状态更新
        async def subscribe_new():
            new_subscriber = CollectorSubscriber()
            return await event_service.subscribe_to_events(new_subscriber)

        async def publish_update():
            await event_service._publish_state_update()

        # 同时运行两者 - 这不应该死锁
        results = await asyncio.wait_for(
            asyncio.gather(subscribe_new(), publish_update(), return_exceptions=True),
            timeout=2.0,
        )

        # 验证没有发生异常
        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Unexpected exception: {result}")

    @pytest.mark.asyncio
    async def test_multiple_state_updates_with_slow_subscribers(
        self, event_service, mock_conversation_with_real_lock
    ):
        """测试多个快速状态更新，而慢速订阅者则不需要死锁。

        此测试验证，即使订阅者速度较慢，也可以处理多个状态更新，而不会导致锁导致争用
        问题。
        """
        event_service._conversation = mock_conversation_with_real_lock
        events_received: list[Event] = []

        class SlowCollectorSubscriber(Subscriber[Event]):
            async def __call__(self, event: Event):
                events_received.append(event)
                await asyncio.sleep(0.05)  # 模拟慢速处理

        # 订阅慢速收集器
        slow_collector = SlowCollectorSubscriber()
        await event_service.subscribe_to_events(slow_collector)

        # 清除初始状态事件
        events_received.clear()

        # 快速触发多个状态更新
        async def rapid_updates():
            for _ in range(5):
                await event_service._publish_state_update()

        # 这应该在没有死锁的情况下完成
        await asyncio.wait_for(rapid_updates(), timeout=5.0)

        # 验证已收到所有更新
        assert len(events_received) == 5, (
            f"Expected 5 events, got {len(events_received)}"
        )


class TestSearchEventsBlockedByRunLoop:
    """Reproduce: search_events 在 agent.step() 的整个持续时间内阻塞。

    运行循环在 LocalConversation.run() 保持不变 FIFOLock 在 ConversationState 在每次
    迭代（包括） LLM 呼叫和工
    具执行。 EventService._search_events_sync() 获取了 *相同的*  锁为了迭代事件，因此
    它会阻塞直到步骤完成。

    完整的文章请参见 HANG_REPRO.md。
    """

    @pytest.mark.asyncio
    async def test_search_events_not_blocked_by_state_lock(
        self, sample_stored_conversation
    ):
        """即使运行循环持有锁，search_events 也必须立即返回。

        这模拟了真实场景：LocalConversation.run() 成立
        ``_state`` (FIFOLock) for the entire 智能体 step, while
        ``_search_events_sync`` 尝试在线程池执行器中获取相同的锁。

        预期的行为（已修复）是读路径不会与写路径锁 search_events 不会争用，无论步骤花
        费多长时间。
        """
        service = EventService(
            stored=sample_stored_conversation,
            conversations_dir=Path("test_conversation_dir"),
        )

        conversation = MagicMock(spec=Conversation)
        state = MagicMock(spec=ConversationState)

        real_lock = FIFOLock()
        state._lock = real_lock
        state.__enter__ = lambda self: (real_lock.acquire(), self)[1]
        state.__exit__ = lambda self, *args: real_lock.release()
        state.events = [
            MessageEvent(id=f"evt-{i}", source="user", llm_message=Message(role="user"))
            for i in range(3)
        ]
        state.execution_status = ConversationExecutionStatus.RUNNING
        conversation._state = state
        service._conversation = conversation

        hold_seconds = 2.0
        lock_acquired = threading.Event()

        def hold_lock_like_run_loop():
            """模拟 LocalConversation.run() 在步骤中按住锁。"""
            with state:
                lock_acquired.set()
                time.sleep(hold_seconds)

        # 启动保存锁的“运行循环”线程
        run_thread = threading.Thread(target=hold_lock_like_run_loop, daemon=True)
        run_thread.start()
        lock_acquired.wait(timeout=5.0)

        # 即使锁被按住，search_events 也应该快速返回
        t0 = time.monotonic()
        result = await service.search_events()
        elapsed = time.monotonic() - t0

        run_thread.join(timeout=5.0)

        # search_events返回正确的数据
        assert len(result.items) == 3

        # 关键断言：search_events 必须不被运行循环的锁阻止。 如果它花费在 hold_seconds
        # 附近的任何位置，则读取路径仍在写入锁上竞争（HANG_REPRO.md 中的错误）。
        #
        max_acceptable = 0.5
        assert elapsed < max_acceptable, (
            f"search_events took {elapsed:.3f}s, but should return in "
            f"<{max_acceptable}s even while the run loop holds the state lock "
            f"for {hold_seconds}s.  The read path is blocked by the write lock "
            f"(see HANG_REPRO.md)."
        )


class _SyncOnlyAgent(AgentBase):
    """智能体仅实现同步 step()（无步进覆盖）。

    在模块级别定义（不在测试内部），因为 ``AgentBase`` 是可区分联合成员并且无法注册本
    地类。
    """

    def step(self, conversation, on_event, on_token=None):
        pass


class TestEventServiceClose:
    """测试 EventService.close() 等待对话拆除。"""

    @pytest.mark.asyncio
    async def test_close_awaits_conversation_close(self, event_service):
        """close() 必须等待 conversation.close()，而不是即发即弃。"""
        conversation = MagicMock(spec=Conversation)
        event_service._conversation = conversation

        closed = asyncio.Event()

        def slow_close():
            # 模拟重要的拆卸工作
            time.sleep(0.05)
            closed.set()

        conversation.close = slow_close

        await event_service.close()

        assert closed.is_set(), (
            "EventService.close() returned before conversation.close() finished"
        )

    @pytest.mark.asyncio
    async def test_close_clears_conversation_reference(self, event_service):
        """close() 关闭后必须将 _conversation 设置为 None。"""
        conversation = MagicMock()
        event_service._conversation = conversation

        await event_service.close()

        assert event_service._conversation is None

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, event_service):
        """调用 close() 两次不得引发。"""
        conversation = MagicMock()
        event_service._conversation = conversation

        await event_service.close()
        await event_service.close()  # 第二次通话 — _conversation 已经是 None

        conversation.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_exit_closes_after_meta_save_failure(self, event_service):
        event_service.save_meta = AsyncMock(side_effect=OSError("save failed"))
        event_service.close = AsyncMock()

        with pytest.raises(OSError, match="save failed"):
            await event_service.__aexit__(None, None, None)

        event_service.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exit_prioritizes_credential_close_failure(self, event_service):
        event_service.save_meta = AsyncMock(side_effect=OSError("save failed"))
        event_service.close = AsyncMock(
            side_effect=CredentialSyncError("broker unavailable")
        )

        with pytest.raises(CredentialSyncError, match="broker unavailable"):
            await event_service.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_close_pauses_before_closing_conversation(self, event_service):
        """close() 必须在调用 conversation.close() 之前暂停正在进行的运行。
        如果 close() 首先运行，仍然活动的运行循环将与执行程序拆卸竞争 - 在工具调用运
        行时关闭 MCP 客户端。
        """
        conversation = MagicMock(spec=Conversation)
        call_order: list[str] = []

        def record_pause():
            call_order.append("pause")

        def record_close():
            call_order.append("close")

        conversation.pause = record_pause
        conversation.close = record_close
        event_service._conversation = conversation

        # 当 close() 检查任务时，任务正在进行中，并在等待期间完成。
        async def fake_run():
            await asyncio.sleep(0.05)

        event_service._run_task = asyncio.create_task(fake_run())

        await event_service.close()

        assert call_order == ["pause", "close"], (
            f"Expected pause before close, got {call_order}"
        )
        assert event_service._run_task is None

    @pytest.mark.asyncio
    async def test_close_skips_pause_when_no_run_task(self, event_service):
        """当没有正在运行的任务时，close() 不得调用 pause()。"""
        conversation = MagicMock(spec=Conversation)
        conversation.pause = MagicMock()
        conversation.close = MagicMock()
        event_service._conversation = conversation
        event_service._run_task = None

        await event_service.close()

        conversation.pause.assert_not_called()
        conversation.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_proceeds_on_run_task_timeout(self, event_service, caplog):
        """如果运行任务未在超时、close() 日志内完成
        并仍在继续。 服务器关闭不应因挂起的 agent.step 而阻塞：仅在超时上取消不会取消
        底层工作线程，所以我们接受这种情况为尽力而为。 仍必须尝试暂停，以
        便常见情况（步骤立即完成）保持干净。
        """
        conversation = MagicMock(spec=Conversation)
        conversation.pause = MagicMock()
        conversation.close = MagicMock()
        event_service._conversation = conversation

        async def hanging_run():
            await asyncio.sleep(60)

        hanging_task = asyncio.create_task(hanging_run())
        event_service._run_task = hanging_task

        try:
            with (
                caplog.at_level("WARNING"),
                patch(
                    "openhands.agent_server.event_service.asyncio.wait_for",
                    AsyncMock(side_effect=asyncio.TimeoutError),
                ),
            ):
                await event_service.close()
        finally:
            hanging_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, BaseException):
                await hanging_task

        conversation.pause.assert_called_once()
        assert "did not exit cleanly" in caplog.text
        assert event_service._run_task is None
        conversation.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_uses_executor_for_sync_only_conversation(self, event_service):
        """当 EventService.run() 必须使用线程-pool 执行器时
        对话仅继承默认的 BaseConversation.arun() （委托给同步 run()）。 这可以防止仅
        限同步的子类意外阻塞事件循环。
        """
        from openhands.sdk.conversation.base import BaseConversation

        run_thread_id: int | None = None
        mock = MagicMock()

        # 永远不会覆盖 arun() 的具体子类； 所有抽象方法都由 MagicMock 委托填充，因此我们
        # 只测试调度逻辑。
        #
        class SyncOnlyConversation(BaseConversation):
            """仅实现同步 run() 的最小子类。"""

            @property
            def id(self):
                return mock.id

            @property
            def state(self):
                return mock.state

            @property
            def conversation_stats(self):
                return mock.conversation_stats

            def send_message(self, message, sender=None):
                pass

            def run(self):
                nonlocal run_thread_id
                run_thread_id = threading.current_thread().ident

            def pause(self):
                pass

            def close(self):
                pass

            def set_confirmation_policy(self, policy):
                pass

            def set_security_analyzer(self, analyzer):
                pass

            def update_secrets(self, secrets):
                pass

            def reject_pending_actions(self, reason=""):
                pass

            def interrupt(self):
                pass

            def generate_title(self, llm=None, max_length=50):
                return ""

            def ask_agent(self, question):
                return ""

            def condense(self):
                pass

            def execute_tool(self, tool_name, action):
                return mock.execute_tool(tool_name, action)

            def fork(self, **kwargs):
                return mock.fork(**kwargs)

            def navigate_to(self, event_id):
                return mock.navigate_to(event_id)

        conv = SyncOnlyConversation()
        event_service._conversation = conv  # type: ignore[assignment]

        # 理智：此对话确实不覆盖 arun()
        assert type(conv).arun is BaseConversation.arun

        # 绕过访问内部_state（不是抽象接口的一部分）的保护，因此我们只测试调度逻辑。
        #
        with (
            patch.object(
                type(event_service),
                "_get_execution_status",
                new_callable=AsyncMock,
                return_value=ConversationExecutionStatus.PAUSED,
            ),
            patch.object(
                type(event_service),
                "_publish_state_update",
                new_callable=AsyncMock,
            ),
        ):
            await event_service.run()
            # 给后台任务一点时间来执行
            await asyncio.sleep(0.3)

        event_loop_thread = threading.current_thread().ident
        assert run_thread_id is not None, "run() was never called"
        assert run_thread_id != event_loop_thread, (
            "run() executed on the event loop thread — expected thread-pool"
        )

    async def test_run_uses_executor_for_sync_only_agent(self, event_service):
        """当 EventService.run() 必须使用线程-pool 执行器时
        智能体仅实现同步 step()（不覆盖 astep()），即使对话覆盖 arun()。
        ``LocalConversation`` 总是覆盖 arun()，
        因此会话级防护会单独通过本机异步路径路由仅同步的自定义智能体，在工作线程线程
        中运行它们的同步 step()，而 arun() 在事件循环线程上保存状态锁 (
        B5)。
        """
        from openhands.sdk.conversation.base import BaseConversation

        run_called = False
        arun_called = False
        agent = _SyncOnlyAgent(llm=LLM(model="gpt-4o", usage_id="sync-only"))

        # 替代 arun()（如 LocalConversation）但包装仅同步的智能体的替代对话。 仅实施与调
        # 度相关的成员。
        #
        class AsyncConvSyncAgent:
            def __init__(self):
                self.agent = agent

            async def arun(self):
                nonlocal arun_called
                arun_called = True

            def run(self):
                nonlocal run_called
                run_called = True

        conv = AsyncConvSyncAgent()
        event_service._conversation = conv  # type: ignore[assignment]

        # 理智：对话覆盖 arun()，但智能体继承
        # 默认 astep()，因此必须采用本机异步路径不。
        assert type(conv).arun is not BaseConversation.arun
        assert type(conv.agent).astep is AgentBase.astep

        with (
            patch.object(
                type(event_service),
                "_get_execution_status",
                new_callable=AsyncMock,
                return_value=ConversationExecutionStatus.PAUSED,
            ),
            patch.object(
                type(event_service),
                "_publish_state_update",
                new_callable=AsyncMock,
            ),
        ):
            await event_service.run()
            # 给后台任务一点时间来执行
            await asyncio.sleep(0.3)

        assert run_called, "sync run() was never called"
        assert not arun_called, (
            "arun() was used for a sync-only agent — expected sync run()"
        )


@pytest_asyncio.fixture
async def real_conversation_service(tmp_path):
    persist = tmp_path / "persist"
    persist.mkdir()
    service = ConversationService(conversations_dir=persist)
    async with service:
        yield service


class _WedgedSubscriber:
    """表示一个 WS 客户端的 TCP 缓冲区已满。"""

    def __init__(self) -> None:
        self.unblock = asyncio.Event()

    async def __call__(self, event):
        await self.unblock.wait()

    async def close(self) -> None:
        self.unblock.set()  # let PubSub.close() finish


@pytest.mark.timeout(15)
async def test_subscribe_to_events_does_not_deadlock_on_wedged_subscriber(
    real_conversation_service, tmp_path
):
    (tmp_path / "ws").mkdir()
    info = await start_conversation_with_test_llm(
        real_conversation_service,
        parent_llm=SlowTestLLM.from_messages([text_message("ok")], latency_s=0.0),
        workspace_dir=str(tmp_path / "ws"),
        usage_id="wedged-sub",
        initial_text=None,
    )
    es = await real_conversation_service.get_event_service(info.id)
    assert es is not None

    wedged = _WedgedSubscriber()
    try:
        await asyncio.wait_for(es.subscribe_to_events(wedged), timeout=1.0)
    except TimeoutError:
        pytest.fail("subscribe_to_events blocked > 1 s on a wedged subscriber.")
    finally:
        wedged.unblock.set()


@pytest.mark.timeout(45)
async def test_close_blocks_until_executor_thread_finishes(
    real_conversation_service, tmp_path, monkeypatch
):
    # close() 取消 _run_task，然后等待它稳定下来。 通过本机 arun() 路径，任务可以快速处
    # 理 CancelledError 并转换到 PAUSED。 我们验证 close() 是否及时返回（取消机器正常工
    # 作）并且任务已正确清理。
    #
    (tmp_path / "ws").mkdir()
    parent_llm = SlowTestLLM.from_messages(
        [text_message("done")],
        latency_s=12.0,  # > close() 中的 10 s wait_for
    )
    info = await start_conversation_with_test_llm(
        real_conversation_service,
        parent_llm=parent_llm,
        workspace_dir=str(tmp_path / "ws"),
        usage_id="close-race",
        initial_text=None,
    )
    es = await real_conversation_service.get_event_service(info.id)
    assert es is not None

    await es.send_message(
        Message(role="user", content=[TextContent(text="long step")]),
        run=False,
    )
    await es.run()
    await asyncio.sleep(0.5)

    def _broken():
        raise RuntimeError("pause/close unavailable")

    conv = es.get_conversation()
    monkeypatch.setattr(conv, "pause", _broken)
    monkeypatch.setattr(conv, "close", _broken)

    close_start = time.monotonic()
    with contextlib.suppress(Exception):
        await es.close()
    close_elapsed = time.monotonic() - close_start

    # close() 应该在 12 s LLM 延迟之前返回，因为它取消了 arun() 任务，该任务处理
    # CancelledError 并转换到 PAUSED。 为 CI 留出足够的余量，但确保它不会阻塞整个 12 秒
    # 。
    #
    assert close_elapsed < 11.0, (
        f"close() took {close_elapsed:.1f}s — expected fast cancellation"
    )

    monkeypatch.undo()


class TestStatsCallbackNoDeadlock:
    """Regression: stats_callback 不得重新获取状态锁。

    ``Telemetry._stats_update_callback`` 从 LLM 完成/ACP 轮转管道内部同步调用，而另一
    个线程 (
    ``LocalConversation.run()``) 保存对话状态的
    ``FIFOLock`` 通过 ``with self._state:``。

    根据经验，死锁是 **cross-线程**：FIFOLock 的 Same-线程重入工作正常（在
    ``test_same_thread_reentry_works_on_fifolock``），但是当回调向与锁所有者不同的线
    程开火时，回调内额外的
    ``with state:`` 会永远等待。 这就是此次修复之前所有短文本 ACP 对话挂起的原因。

    这些测试固定合约：回调立即返回，并且统计事件排队等待发射，无论哪个线程拥有锁。
    """

    def _make_service_with_callback(self):
        stored = StoredConversation(
            id=uuid4(),
            workspace=LocalWorkspace(working_dir="workspace/project"),
            confirmation_policy=NeverConfirm(),
            initial_message=None,
            metrics=None,
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
        )
        service = EventService(
            stored=stored,
            agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-stats"), tools=[]),
            conversations_dir=Path("test_conversation_dir"),
        )
        # 一个真实的 FIFOLock 在模拟对象-ish 状态，以便回调争执于实际生产锁基本的，但我
        # 们不需要启动它 LocalConversation  事件循环 / 持久化将堆栈用于练习死锁。
        #
        state = MagicMock()
        state._lock = FIFOLock()
        state.__enter__ = MagicMock(side_effect=lambda: state._lock.acquire())
        state.__exit__ = MagicMock(side_effect=lambda *a: state._lock.release())
        state.stats = MagicMock(name="stats")

        conversation = MagicMock()
        conversation._state = state
        service._conversation = conversation
        # 存根 executor-线程发射路径，以便测试保持同步 + 确定性。 被测行为只是
        # ``stats_callback returns promptly``; _emit_event_from_thread 的
        # locked_on_event 侧已在其他地方覆盖。
        #
        service._emit_event_from_thread = MagicMock(name="_emit_event_from_thread")

        callbacks: list = []
        service._setup_stats_streaming(
            MagicMock(
                get_all_llms=lambda: [
                    MagicMock(
                        telemetry=MagicMock(set_stats_update_callback=callbacks.append)
                    )
                ]
            )
        )
        assert len(callbacks) == 1, "stats_callback must be registered exactly once"
        return service, state, callbacks[0]

    def test_same_thread_reentry_works_on_fifolock(self):
        """Sanity: FIFOLock的可重入性合同适用于线程重新获取。

        文档说明，修复**不是**关于掩盖一个可重入锁 — 即使有``with state:``的错误重入
        ，同样的线程也能FIFOLock重新获得死锁。 这将死锁作
        为跨线程现象（见下一项测试）。
        """
        lock = FIFOLock()
        finished = threading.Event()

        def run():
            with lock:
                with lock:  # 相同的线程重入
                    pass
            finished.set()

        threading.Thread(target=run, daemon=True).start()
        assert finished.wait(timeout=2.0), "FIFOLock should support same-thread reentry"

    @pytest.mark.timeout(10)
    def test_returns_promptly_when_another_thread_holds_state_lock(self):
        """死锁情况：当回调触发时，另一个线程拥有锁。

        镜子生产：``LocalConversation.run()`` 在线程 A 上
        ``state``'s FIFOLock via ``with self._state:``; stats 回调在不同地方发生线程
        (执行器/门户/桥梁)
        并重新获取锁与 ``with state:`` — 永久阻塞 FIFOLock's 可重入性门
        ``threading.get_ident()`` 和线程
        B的身份不是所有者。

        预先修复此测试将永远挂起并且 pytest 超时上限触发。 修复后回调不再重新获取锁并
        立即返回，统计事件将序列化一次线程 A 最终释放锁交给
        ``_emit_event_from_thread``。
        """
        service, state, stats_callback = self._make_service_with_callback()
        lock_acquired = threading.Event()
        callback_completed = threading.Event()
        release_lock = threading.Event()

        def thread_a_holds_lock():
            with state:
                lock_acquired.set()
                # 按住锁直到回调线程完成其工作（或直到测试超时，以先到者为准）。
                #
                release_lock.wait(timeout=5.0)

        def thread_b_invokes_callback():
            assert lock_acquired.wait(timeout=2.0), "thread A never took the lock"
            stats_callback()
            callback_completed.set()

        a = threading.Thread(target=thread_a_holds_lock, daemon=True)
        b = threading.Thread(target=thread_b_invokes_callback, daemon=True)
        a.start()
        b.start()
        try:
            assert callback_completed.wait(timeout=2.0), (
                "stats_callback hung — thread A still holds the FIFOLock "
                "and the callback's `with state:` is blocking on it. "
                "Restore the fix that removes the redundant lock acquire."
            )
            emit_mock = cast(MagicMock, service._emit_event_from_thread)
            emit_mock.assert_called_once()
        finally:
            release_lock.set()
            a.join(timeout=2.0)
            b.join(timeout=2.0)

    def test_returns_promptly_with_no_lock_contention(self):
        """Baseline: 回调返回并在没有任何内容时调度发出。"""
        service, _state, stats_callback = self._make_service_with_callback()
        finished = threading.Event()

        def run():
            stats_callback()
            finished.set()

        threading.Thread(target=run, daemon=True).start()
        assert finished.wait(timeout=2.0), (
            "stats_callback did not return within 2s with no lock contention"
        )
        emit_mock = cast(MagicMock, service._emit_event_from_thread)
        emit_mock.assert_called_once()


@pytest.mark.timeout(30)
async def test_message_in_run_cleanup_tail_is_not_stranded(
    real_conversation_service, tmp_path, monkeypatch
):
    """当*完成*运行仍在其状态时到达的消息
    ``wait_for_pending()`` 清理尾部仍必须进行处理。

    回归测试跨线路上的断言消息竞争： ``send_message(run=True)`` 抑制 run()'s
    ``conversation_already_running`` while ``_run_task`` 正在收尾，缺少重新武装
    ``_run_and_publish`` 一旦尾部清空，就不会再重跑 —— 因此，消息会一直处于未处理状态
    ，直到下一次发送。

    不是飞行中的情况：``LocalConversation.run`` 故意在 FINISHED 上保持循环，因此在 *
    步骤期间到达 * 的消息将被吸收。 不受保护
    的间隙严格来说是 ``_run_and_publish`` 拥有的运行后执行器尾部。
    """
    (tmp_path / "ws").mkdir()
    # 每条用户消息一份脚本化回复； 每个都是纯文本（没有工具调用），因此智能体立即完成转
    # 弯。 ``_call_count`` 告诉我们实际跑了多少圈。
    #
    parent_llm = SlowTestLLM.from_messages(
        [text_message("reply one"), text_message("reply two")],
        latency_s=0.0,
    )
    info = await start_conversation_with_test_llm(
        real_conversation_service,
        parent_llm=parent_llm,
        workspace_dir=str(tmp_path / "ws"),
        usage_id="tail-strand",
        initial_text=None,
    )
    es = await real_conversation_service.get_event_service(info.id)
    assert es is not None and es._callback_wrapper is not None

    # 将每次运行停放在 wait_for_pending() 尾部直至释放。 它在线程池工作线程中运行，因此
    # 在 threading.Event 上阻塞并发出信号返回测试。
    #
    entered_tail = threading.Event()
    release_tail = threading.Event()

    def _blocking_wait(timeout: float) -> None:
        entered_tail.set()
        release_tail.wait(timeout)

    monkeypatch.setattr(es._callback_wrapper, "wait_for_pending", _blocking_wait)

    # 第 1 回合：智能体“首先”回答，完成 (FINISHED)，然后运行任务停在我们的阻塞
    # wait_for_pending() 中。
    #
    await es.send_message(
        Message(role="user", content=[TextContent(text="first")]), run=True
    )
    assert await asyncio.to_thread(entered_tail.wait, 10.0), (
        "first run never reached its wait_for_pending tail"
    )
    first_run_task = es._run_task
    assert first_run_task is not None
    assert parent_llm._call_count == 1
    assert await es._get_execution_status() == ConversationExecutionStatus.FINISHED

    # 回合2到达DURING尾部：send_message追加它并将终端状态重置为IDLE，然后run()被拒绝（任
    # 务未完成）并被抑制。 还没有运行。
    #
    await es.send_message(
        Message(role="user", content=[TextContent(text="second")]), run=True
    )
    assert parent_llm._call_count == 1, "second turn ran before the tail cleared?!"
    assert es._run_task is first_run_task, "a second run started concurrently"

    # 松开尾巴； 第一个运行任务完成并清除 _run_task。
    release_tail.set()
    await first_run_task

    # 现在必须处理第二条消息。 如果没有 _run_and_publish 重新启动，它就会陷入困境（
    # call_count 保持 1，状态卡住 IDLE）。
    #
    deadline = time.monotonic() + 5.0
    while parent_llm._call_count < 2 and time.monotonic() < deadline:
        await asyncio.sleep(0.05)

    assert parent_llm._call_count == 2, (
        "second message was stranded — the agent never ran for it after the "
        f"first run's cleanup tail cleared (call_count={parent_llm._call_count}, "
        f"status={await es._get_execution_status()})"
    )


@pytest.mark.timeout(30)
async def test_run_false_message_in_cleanup_tail_is_not_run(
    real_conversation_service, tmp_path, monkeypatch
):
    """清理尾部中的 run=False 追加着陆必须不自动运行。

    保护重新武装背后的明确意图合约：send_message(
    run=False) appends without running, and _run_and_publish must not
    复活它只是因为send_message将终端状态重置为IDLE。
    """
    (tmp_path / "ws").mkdir()
    # 两个脚本回复，但只应运行第一轮。
    parent_llm = SlowTestLLM.from_messages(
        [text_message("reply one"), text_message("must not run")],
        latency_s=0.0,
    )
    info = await start_conversation_with_test_llm(
        real_conversation_service,
        parent_llm=parent_llm,
        workspace_dir=str(tmp_path / "ws"),
        usage_id="tail-run-false",
        initial_text=None,
    )
    es = await real_conversation_service.get_event_service(info.id)
    assert es is not None and es._callback_wrapper is not None

    entered_tail = threading.Event()
    release_tail = threading.Event()

    def _blocking_wait(timeout: float) -> None:
        entered_tail.set()
        release_tail.wait(timeout)

    monkeypatch.setattr(es._callback_wrapper, "wait_for_pending", _blocking_wait)

    # 1 号弯运行并停在 wait_for_pending 尾部。
    await es.send_message(
        Message(role="user", content=[TextContent(text="first")]), run=True
    )
    assert await asyncio.to_thread(entered_tail.wait, 10.0), (
        "first run never reached its wait_for_pending tail"
    )
    first_run_task = es._run_task
    assert first_run_task is not None
    assert parent_llm._call_count == 1

    # 在尾部附加一条带有 run=False 的消息：调用者明确确实不想要运行。 它将终端状态重置为
    # IDLE，但不得设置重新运行标志。
    #
    await es.send_message(
        Message(role="user", content=[TextContent(text="just append")]), run=False
    )
    assert es._rerun_requested is False

    # 释放尾巴，让运行任务安定下来； 没有什么应该重新运行。
    release_tail.set()
    await first_run_task
    await asyncio.sleep(0.3)  # 给任何错误的重新武装机会

    assert parent_llm._call_count == 1, (
        "run=False append in the cleanup tail was unexpectedly run "
        f"(call_count={parent_llm._call_count})"
    )
    assert es._run_task is None


def test_emit_event_from_thread_uses_captured_loop(event_service: EventService) -> None:
    """_emit_event_from_thread 必须使用捕获的 main_loop，而不是 self._main_loop。

    在此修复之前，该方法将 _main_loop 捕获到局部变量中以进行 if 检查，但随后在主体中
    调用 self._main_loop.run_in_executor
    (...)。 检查和调用之间的并发 close() 设置 self._main_loop = None 将导致
    AttributeError。 该修复使用main_
    loop。
    """
    captured_calls: list = []

    mock_loop = MagicMock()
    mock_loop.is_running.return_value = True

    def record_and_null(*args, **kwargs):
        # 模拟并发 close() 清零 self._main_loop 通话中
        object.__setattr__(event_service, "_main_loop", None)
        captured_calls.append(args)
        # run_in_executor 总是返回一个 Future； 调用者将完成回调附加到表面执行器故障。
        #
        return MagicMock()

    mock_loop.run_in_executor.side_effect = record_and_null

    event_service._main_loop = mock_loop  # type: ignore[assignment]
    event_service._conversation = MagicMock()  # type: ignore[assignment]

    event = MagicMock()

    # 即使 self._main_loop 已清除，也不应提高 AttributeError
    event_service._emit_event_from_thread(event)
    assert len(captured_calls) == 1, "run_in_executor should have been called once"


async def test_emit_event_from_thread_stamps_event_when_persisted(
    event_service: EventService,
) -> None:
    """从回调发出的事件在附加时会带有时间戳。

    统计数据更新是在模型回答时构建的，但仅在保存状态锁的步骤附加其操作和观测结果后才
    会附加。 保留构建时间时间戳会使其不符合时间戳顺序，因此
    ``timestamp__gte`` 和 ``resend_mode=since`` 跳过了它。
    """
    state_lock = FIFOLock()
    appended: list[Event] = []
    conversation = MagicMock()
    conversation._state = state_lock
    conversation._on_event.side_effect = appended.append
    event_service._main_loop = asyncio.get_running_loop()
    event_service._conversation = conversation  # type: ignore[assignment]

    event = ConversationStateUpdateEvent(key="stats", value={})
    with state_lock:
        event_service._emit_event_from_thread(event)
        await asyncio.sleep(0.01)
        # 代表锁下附加的步骤操作/观察。
        step_end = datetime.now().isoformat()
        await asyncio.sleep(0.01)

    for _ in range(200):
        if appended:
            break
        await asyncio.sleep(0.01)
    assert len(appended) == 1
    persisted = appended[0]
    assert persisted.id == event.id
    assert persisted.timestamp > step_end > event.timestamp


def test_llm_log_callback_swallows_emit_failures(
    event_service: EventService, caplog
) -> None:
    callbacks = []
    llm = MagicMock(log_completions=True, usage_id="test-usage", model="gpt-4o")
    llm.telemetry.set_log_completions_callback.side_effect = callbacks.append

    object.__setattr__(
        event_service,
        "_emit_event_from_thread",
        MagicMock(side_effect=RuntimeError("emit failed")),
    )

    with caplog.at_level("ERROR"):
        event_service._setup_llm_log_streaming(MagicMock(get_all_llms=lambda: [llm]))
        callbacks[0]("completion.json", "{}")

    emit_mock = cast(MagicMock, event_service._emit_event_from_thread)
    emit_mock.assert_called_once()
    assert "Failed to emit LLM completion log event" in caplog.text


def _make_stored(tmp_path: Path) -> StoredConversation:
    return StoredConversation(
        id=uuid4(),
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
        confirmation_policy=NeverConfirm(),
        initial_message=None,
        metrics=None,
    )


def _make_mock_conv() -> MagicMock:
    mock_conv = MagicMock()
    mock_state = MagicMock()
    mock_state.execution_status = ConversationExecutionStatus.IDLE
    mock_state.events = []
    mock_state.stats = MagicMock()
    mock_conv.agent.get_all_llms.return_value = []
    mock_conv._state = mock_state
    mock_conv.state = mock_state
    mock_conv._on_event = MagicMock()
    return mock_conv


@pytest.mark.asyncio
async def test_event_service_skips_lease_when_ttl_is_zero(tmp_path: Path) -> None:
    stored = _make_stored(tmp_path)
    service = EventService(
        stored=stored,
        agent=_sample_agent(),
        conversations_dir=tmp_path,
        lease_ttl_seconds=0,
    )
    with patch(
        "openhands.agent_server.event_service.LocalConversation",
        return_value=_make_mock_conv(),
    ):
        await service.start()

    assert service._lease is None
    assert not (tmp_path / stored.id.hex / LEASE_FILE_NAME).exists()


@pytest.mark.asyncio
async def test_event_service_creates_lease_with_custom_ttl(tmp_path: Path) -> None:
    stored = _make_stored(tmp_path)
    service = EventService(
        stored=stored,
        agent=_sample_agent(),
        conversations_dir=tmp_path,
        lease_ttl_seconds=10.0,
    )
    with patch(
        "openhands.agent_server.event_service.LocalConversation",
        return_value=_make_mock_conv(),
    ):
        await service.start()

    assert service._lease is not None
    assert service._lease._ttl_seconds == 10.0
    assert (tmp_path / stored.id.hex / LEASE_FILE_NAME).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("condenser", "message"),
    [
        (None, "No condenser configured"),
        (NoOpCondenser(), "NoOpCondenser does not handle condensation requests"),
    ],
)
async def test_condense_without_request_handling_condenser_is_refused(
    event_service: EventService, condenser, message: str
) -> None:
    """无法服务请求的上下文压缩器是调用者的配置，
    因此 condense 会提高 CondensationUnavailable（映射到 409），而不是让
    LocalConversation 的
    ValueError 变成 500。
    """
    conversation = MagicMock()
    conversation.agent.condenser = condenser
    event_service._conversation = conversation

    with pytest.raises(CondensationUnavailable, match=message):
        await event_service.condense()

    conversation.condense.assert_not_called()


class TestEmitEventFromThreadFailures:
    """执行器的失败必须浮出水面，而不是随着未来消亡（#4386）。"""

    @pytest.mark.asyncio
    async def test_emit_failure_is_logged(
        self, sample_stored_conversation, tmp_path, caplog
    ):
        service = EventService(
            stored=sample_stored_conversation, conversations_dir=tmp_path
        )
        conversation = MagicMock()
        conversation._state = MagicMock()
        conversation._state.__enter__ = MagicMock(return_value=None)
        conversation._state.__exit__ = MagicMock(return_value=False)
        conversation._on_event.side_effect = RuntimeError("disk full")

        service._conversation = conversation
        service._main_loop = asyncio.get_running_loop()

        event = MessageEvent(
            id="emit-failure", source="agent", llm_message=Message(role="assistant")
        )

        with caplog.at_level(logging.ERROR):
            service._emit_event_from_thread(event)
            # 让执行器运行并触发 did-回调。
            for _ in range(20):
                await asyncio.sleep(0)

        messages = [record.getMessage() for record in caplog.records]
        assert any("Failed to emit MessageEvent from thread" in m for m in messages), (
            f"emission failure was not surfaced; captured={messages}"
        )
        assert any("disk full" in m for m in messages)

    @pytest.mark.asyncio
    async def test_cancelled_future_is_not_reported(self, caplog):
        """取消的发射并不是失败，并且不能记录或引发。"""
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        future.cancel()
        # 让取消稳定下来，这样 `cancelled()` 就是 True。
        with suppress(asyncio.CancelledError):
            await future

        with caplog.at_level(logging.ERROR):
            _log_emit_failure("MessageEvent", future)

        assert [record.getMessage() for record in caplog.records] == []

    @pytest.mark.asyncio
    async def test_callback_is_attached_from_the_loop_thread(
        self, sample_stored_conversation, tmp_path
    ):
        """`add_done_callback` 必须与 call_soon_threadsafe 一起安排。

        该帮助程序在外部线程上运行，并且直接附加到已完成的 future 将使用普通
        `call_soon`，这不会唤醒空闲循环。
        """
        service = EventService(
            stored=sample_stored_conversation, conversations_dir=tmp_path
        )
        conversation = MagicMock()
        conversation._state = MagicMock()
        conversation._state.__enter__ = MagicMock(return_value=None)
        conversation._state.__exit__ = MagicMock(return_value=False)
        service._conversation = conversation

        real_loop = asyncio.get_running_loop()
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = True
        finished: asyncio.Future[None] = real_loop.create_future()
        finished.set_result(None)
        mock_loop.run_in_executor.return_value = finished
        service._main_loop = mock_loop

        event = MessageEvent(
            id="thread-safety", source="agent", llm_message=Message(role="assistant")
        )
        service._emit_event_from_thread(event)

        assert mock_loop.call_soon_threadsafe.called, (
            "done-callback must be attached via call_soon_threadsafe"
        )
        scheduled = mock_loop.call_soon_threadsafe.call_args.args
        assert scheduled[0] == finished.add_done_callback
