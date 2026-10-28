"""测试 event_router.py 端点。"""

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from openhands.agent_server.dependencies import get_event_service
from openhands.agent_server.event_router import (
    event_router,
    normalize_datetime_to_server_timezone,
)
from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import SendMessageRequest
from openhands.sdk import Message
from openhands.sdk.conversation.event_store import EventLog
from openhands.sdk.event.llm_convertible.message import MessageEvent
from openhands.sdk.io.memory import InMemoryFileStore
from openhands.sdk.llm.message import ImageContent, TextContent


def test_normalize_datetime_naive_passthrough():
    """天真的日期时间应原样返回。"""
    naive_dt = datetime(2025, 1, 15, 10, 30, 0)
    result = normalize_datetime_to_server_timezone(naive_dt)

    assert result == naive_dt
    assert result.tzinfo is None


def test_normalize_datetime_utc_converted_to_naive():
    """UTC 日期时间应转换为服务器本地时间并使其变得简单。"""
    utc_dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
    result = normalize_datetime_to_server_timezone(utc_dt)

    assert result.tzinfo is None
    expected = utc_dt.astimezone(None).replace(tzinfo=None)
    assert result == expected


def test_normalize_datetime_preserves_microseconds():
    """应通过转换保留微秒。"""
    utc_dt = datetime(2025, 1, 15, 10, 30, 0, 123456, tzinfo=UTC)
    result = normalize_datetime_to_server_timezone(utc_dt)

    assert result.microsecond == 123456


def test_normalize_datetime_fixed_offset_timezone():
    """使用特定的固定偏移时区 (UTC+5:30) 进行测试。"""
    ist = timezone(timedelta(hours=5, minutes=30))
    ist_dt = datetime(2025, 1, 15, 16, 0, 0, tzinfo=ist)

    result = normalize_datetime_to_server_timezone(ist_dt)

    assert result.tzinfo is None
    expected = ist_dt.astimezone(None).replace(tzinfo=None)
    assert result == expected


@pytest.fixture
def client():
    """为没有身份验证的 FastAPI 应用程序创建一个测试客户端。"""
    app = FastAPI()
    app.include_router(event_router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def sample_conversation_id():
    """返回示例对话 ID。"""
    return uuid4()


@pytest.fixture
def mock_event_service():
    """创建模拟对象 EventService 进行测试。"""
    service = AsyncMock(spec=EventService)
    service.send_message = AsyncMock()
    return service


class TestSendMessageEndpoint:
    """测试用例为send_message端点。"""

    @pytest.mark.asyncio
    async def test_send_message_with_run_true(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用 run=True 测试 send_message 端点。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            request_data = {
                "role": "user",
                "content": [{"type": "text", "text": "Hello, world!"}],
                "run": True,
            }

            response = client.post(
                f"/api/conversations/{sample_conversation_id}/events", json=request_data
            )

            assert response.status_code == 200
            assert response.json() == {"success": True}

            # 验证使用正确的参数调用 send_message
            mock_event_service.send_message.assert_called_once()
            call_args = mock_event_service.send_message.call_args
            message, run_flag = call_args[0]

            assert isinstance(message, Message)
            assert message.role == "user"
            assert len(message.content) == 1
            assert isinstance(message.content[0], TextContent)
            assert message.content[0].text == "Hello, world!"
            assert run_flag is True
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_send_message_with_run_false(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用 run=False 测试 send_message 端点。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            request_data = {
                "role": "assistant",
                "content": [{"type": "text", "text": "I understand."}],
                "run": False,
            }

            response = client.post(
                f"/api/conversations/{sample_conversation_id}/events", json=request_data
            )

            assert response.status_code == 200
            assert response.json() == {"success": True}

            # 验证 send_message 是通过 run=False 调用的
            mock_event_service.send_message.assert_called_once()
            call_args = mock_event_service.send_message.call_args
            message, run_flag = call_args[0]

            assert isinstance(message, Message)
            assert message.role == "assistant"
            assert run_flag is False
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_send_message_default_run_value(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用默认运行值测试 send_message 端点。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 没有运行字段的请求应使用默认值
            request_data = {
                "role": "user",
                "content": [{"type": "text", "text": "Test message"}],
            }

            response = client.post(
                f"/api/conversations/{sample_conversation_id}/events", json=request_data
            )

            assert response.status_code == 200
            assert response.json() == {"success": True}

            # 验证使用默认运行值 (False) 调用 send_message
            mock_event_service.send_message.assert_called_once()
            call_args = mock_event_service.send_message.call_args
            message, run_flag = call_args[0]

            assert isinstance(message, Message)
            assert message.role == "user"
            assert run_flag is False  # 默认值来自 SendMessageRequest
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_send_message_conversation_not_found(
        self, client, sample_conversation_id
    ):
        """当未找到对话时测试 send_message 端点。"""
        from fastapi import HTTPException, status

        def raise_not_found():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation not found: {sample_conversation_id}",
            )

        # 重写依赖以 HTTPException
        client.app.dependency_overrides[get_event_service] = raise_not_found

        try:
            request_data = {
                "role": "user",
                "content": [{"type": "text", "text": "Hello"}],
                "run": True,
            }

            response = client.post(
                f"/api/conversations/{sample_conversation_id}/events", json=request_data
            )

            assert response.status_code == 404
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_send_message_with_different_content_types(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用不同的内容类型测试 send_message 端点。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 使用多个内容项进行测试
            request_data = {
                "role": "user",
                "content": [
                    {"type": "text", "text": "First part"},
                    {"type": "text", "text": "Second part"},
                ],
                "run": False,
            }

            response = client.post(
                f"/api/conversations/{sample_conversation_id}/events", json=request_data
            )

            assert response.status_code == 200
            assert response.json() == {"success": True}

            # 验证消息内容是否正确解析
            mock_event_service.send_message.assert_called_once()
            call_args = mock_event_service.send_message.call_args
            message, run_flag = call_args[0]

            assert isinstance(message, Message)
            assert message.role == "user"
            assert len(message.content) == 2
            assert all(isinstance(content, TextContent) for content in message.content)
            text_content = cast(list[TextContent], message.content)
            assert text_content[0].text == "First part"
            assert text_content[1].text == "Second part"
            assert run_flag is False
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_send_message_with_system_role(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用系统角色测试 send_message 端点。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            request_data = {
                "role": "system",
                "content": [{"type": "text", "text": "System initialization message"}],
                "run": True,
            }

            response = client.post(
                f"/api/conversations/{sample_conversation_id}/events", json=request_data
            )

            assert response.status_code == 200
            assert response.json() == {"success": True}

            # 验证系统消息是否已正确处理
            mock_event_service.send_message.assert_called_once()
            call_args = mock_event_service.send_message.call_args
            message, run_flag = call_args[0]

            assert isinstance(message, Message)
            assert message.role == "system"
            assert run_flag is True
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_send_message_invalid_request_data(
        self, client, sample_conversation_id
    ):
        """使用无效请求数据测试 send_message 端点。"""
        # 覆盖依赖项（尽管不应该因验证错误而调用它）
        client.app.dependency_overrides[get_event_service] = lambda: None

        try:
            # 使用无效的角色值进行测试
            invalid_role_data = {
                "role": "invalid_role",
                "content": [{"type": "text", "text": "Hello"}],
                "run": True,
            }

            response = client.post(
                f"/api/conversations/{sample_conversation_id}/events",
                json=invalid_role_data,
            )

            assert response.status_code == 422  # 验证错误

            # 使用无效的内容结构进行测试
            invalid_content_data = {
                "role": "user",
                "content": "invalid_content_should_be_list",  # 应该是一个列表
                "run": True,
            }

            response = client.post(
                f"/api/conversations/{sample_conversation_id}/events",
                json=invalid_content_data,
            )

            assert response.status_code == 422  # 验证错误
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    def test_create_message(self):
        content: list[TextContent | ImageContent] = [
            TextContent(
                text="This is a message",
            )
        ]
        request = SendMessageRequest(
            role="user",
            content=content,
        )
        message = request.create_message()
        assert message.content == content


class TestSearchEventsEndpoint:
    """测试用例用于具有时间戳过滤的搜索事件端点。"""

    @pytest.mark.asyncio
    async def test_search_events_with_naive_datetime(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用简单的日期时间（无时区）测试搜索事件。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 模拟对象 search_events 方法返回示例结果
            mock_event_service.search_events = AsyncMock(
                return_value={"items": [], "next_page_id": None}
            )

            # 使用朴素日期时间进行测试
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={
                    "timestamp__gte": "2025-01-01T12:00:00",  # 天真的日期时间字符串
                    "limit": 10,
                },
            )

            assert response.status_code == 200
            mock_event_service.search_events.assert_called_once()
            # 验证日期时间是否已标准化（转换为日期时间对象）
            call_args = mock_event_service.search_events.call_args
            # 检查参数：(page_id、限制、种类、来源、正文、sort_order、timestamp__gte、
            # timestamp__lt)
            #
            assert len(call_args[0]) >= 7  # 应该至少有 7 个位置参数
            assert call_args[0][6] is not None  # timestamp__gte 应该标准化
            assert call_args[0][7] is None  # timestamp__lt 应该是 None
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_search_events_with_timezone_aware_datetime(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用时区感知的日期时间测试搜索事件。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 模拟对象 search_events 方法返回示例结果
            mock_event_service.search_events = AsyncMock(
                return_value={"items": [], "next_page_id": None}
            )

            # 使用时区感知日期时间进行测试 (UTC)
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={
                    "timestamp__gte": "2025-01-01T12:00:00Z",  # UTC 时区
                    "limit": 10,
                },
            )

            assert response.status_code == 200
            mock_event_service.search_events.assert_called_once()
            # 验证日期时间是否已标准化
            call_args = mock_event_service.search_events.call_args
            # 检查参数：(page_id、限制、种类、来源、正文、sort_order、timestamp__gte、
            # timestamp__lt)
            #
            assert len(call_args[0]) >= 7  # 应该至少有 7 个位置参数
            assert call_args[0][6] is not None  # timestamp__gte 应该标准化
            assert call_args[0][7] is None  # timestamp__lt 应该是 None
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_search_events_with_timezone_range(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用两个时间戳过滤器测试搜索事件
        时区感知的日期时间。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 模拟对象 search_events 方法返回示例结果
            mock_event_service.search_events = AsyncMock(
                return_value={"items": [], "next_page_id": None}
            )

            # 使用时区感知日期时间对两个时间戳过滤器进行测试
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={
                    "timestamp__gte": "2025-01-01T10:00:00+05:00",  # UTC+5
                    "timestamp__lt": "2025-01-01T14:00:00-08:00",  # UTC-8
                    "limit": 10,
                },
            )

            assert response.status_code == 200
            mock_event_service.search_events.assert_called_once()
            # 验证两个日期时间是否已标准化
            call_args = mock_event_service.search_events.call_args
            # 检查参数：(page_id、限制、种类、来源、正文、sort_order、timestamp__gte、
            # timestamp__lt)
            #
            assert len(call_args[0]) >= 8  # 应该至少有 8 个位置参数
            assert call_args[0][6] is not None  # timestamp__gte 应该标准化
            assert call_args[0][7] is not None  # timestamp__lt 应该标准化
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_count_events_with_timezone_aware_datetime(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用时区感知日期时间测试计数事件。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 模拟对象 count_events 方法返回示例结果
            mock_event_service.count_events = AsyncMock(return_value=5)

            # 使用时区感知的日期时间进行测试
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/count",
                params={
                    "timestamp__gte": "2025-01-01T12:00:00+02:00",  # UTC+2
                },
            )

            assert response.status_code == 200
            assert response.json() == 5
            mock_event_service.count_events.assert_called_once()
            # 验证日期时间是否已标准化
            call_args = mock_event_service.count_events.call_args
            # 检查参数：（种类、来源、主体、timestamp__gte、timestamp__lt）
            assert len(call_args[0]) >= 4  # 应该至少有 4 个位置参数
            assert call_args[0][3] is not None  # timestamp__gte 应该标准化
            assert call_args[0][4] is None  # timestamp__lt 应该是 None
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_count_events_with_source_filter(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用源过滤器测试计数事件。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 模拟对象 count_events 方法返回示例结果
            mock_event_service.count_events = AsyncMock(return_value=3)

            # 使用源过滤器进行测试
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/count",
                params={
                    "source": "environment",
                },
            )

            assert response.status_code == 200
            assert response.json() == 3
            mock_event_service.count_events.assert_called_once()
            # 验证源参数是否正确传递
            call_args = mock_event_service.count_events.call_args
            # 检查位置参数：(kind, source, timestamp__gte, timestamp__lt)
            assert len(call_args[0]) >= 2  # 应该至少有 2 个位置参数
            assert call_args[0][0] is None  # 种类应该是None
            assert call_args[0][1] == "environment"  # 来源应该是“环境”
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_search_events_timezone_normalization_consistency(
        self, client, sample_conversation_id, mock_event_service
    ):
        """测试同一时刻的不同时区表示
        持续正常化。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 模拟对象 search_events 方法返回示例结果
            mock_event_service.search_events = AsyncMock(
                return_value={"items": [], "next_page_id": None}
            )

            # 测试 1：UTC 时区
            response1 = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={
                    "timestamp__gte": "2025-01-01T12:00:00Z",  # 12:00 UTC
                    "limit": 10,
                },
            )

            # 测试 2：EST 时区 (UTC-5) - 与 12:00 UTC 相同的时刻
            response2 = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={
                    # 07:00 EST = 12:00 UTC
                    "timestamp__gte": "2025-01-01T07:00:00-05:00",
                    "limit": 10,
                },
            )

            assert response1.status_code == 200
            assert response2.status_code == 200

            # 两个电话都应该被拨打
            assert mock_event_service.search_events.call_count == 2

            # 从两个调用中获取标准化日期时间
            call1_args = mock_event_service.search_events.call_args_list[0]
            call2_args = mock_event_service.search_events.call_args_list[1]

            # 两者都应该标准化为相同的服务器时间检查位置参数：(page_id, limit, kind,
            # source, sort_order, timestamp__gte, timestamp__lt)
            #
            normalized_time1 = call1_args[0][5]  # timestamp__gte 从第一次通话开始
            normalized_time2 = call2_args[0][5]  # timestamp__gte 来自第二次调用

            # 标准化后它们应该是相同的
            assert normalized_time1 == normalized_time2
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_search_events_with_source_filter(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用源过滤器测试搜索事件。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 模拟对象 search_events 方法返回示例结果
            mock_event_service.search_events = AsyncMock(
                return_value={"items": [], "next_page_id": None}
            )

            # 使用源过滤器进行测试
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={
                    "source": "agent",
                    "limit": 10,
                },
            )

            assert response.status_code == 200
            mock_event_service.search_events.assert_called_once()
            # 验证源参数是否正确传递
            call_args = mock_event_service.search_events.call_args
            # 检查参数：(page_id、限制、种类、来源、正文、sort_order、timestamp__gte、
            # timestamp__lt)
            #
            assert len(call_args[0]) >= 4  # 应该至少有 4 个位置参数
            assert call_args[0][3] == "agent"  # 来源应为“智能体”
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_search_events_with_multiple_filters(
        self, client, sample_conversation_id, mock_event_service
    ):
        """使用多个过滤器（包括源）测试搜索事件。"""
        # 覆盖依赖项以返回我们的模拟对象
        client.app.dependency_overrides[get_event_service] = lambda: mock_event_service

        try:
            # 模拟对象 search_events 方法返回示例结果
            mock_event_service.search_events = AsyncMock(
                return_value={"items": [], "next_page_id": None}
            )

            # 使用多个过滤器（包括源）进行测试
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={
                    "kind": "MessageEvent",
                    "source": "user",
                    "timestamp__gte": "2025-01-01T12:00:00Z",
                    "limit": 20,
                },
            )

            assert response.status_code == 200
            mock_event_service.search_events.assert_called_once()
            # 验证所有参数是否已正确传递
            call_args = mock_event_service.search_events.call_args
            # 检查参数：(page_id、限制、种类、来源、正文、sort_order、timestamp__gte、
            # timestamp__lt)
            #
            assert len(call_args[0]) >= 8  # 应该至少有 8 个位置参数
            assert call_args[0][1] == 20  # 限制
            assert call_args[0][2] == "MessageEvent"  # 善良
            assert call_args[0][3] == "user"  # 来源
            assert call_args[0][4] is None  # 正文应该是 None
            assert call_args[0][6] is not None  # timestamp__gte 应该标准化
            assert call_args[0][7] is None  # timestamp__lt 应该是 None
        finally:
            # 清理依赖覆盖
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_search_events_with_source_filter_real_events(
        self, client, sample_conversation_id
    ):
        """使用真实事件测试源过滤。"""
        from openhands.agent_server.event_service import EventService
        from openhands.sdk.llm.message import TextContent

        # 使用示例事件创建真实的 EventService
        event_service = EventService(
            stored=MagicMock(), conversations_dir=Path("test_dir")
        )

        # 创建具有不同来源的事件
        events = [
            MessageEvent(
                id="user1",
                source="user",
                llm_message=Message(role="user", content=[TextContent(text="Hello")]),
            ),
            MessageEvent(
                id="agent1",
                source="agent",
                llm_message=Message(
                    role="assistant", content=[TextContent(text="Hi there")]
                ),
            ),
            MessageEvent(
                id="user2",
                source="user",
                llm_message=Message(role="user", content=[TextContent(text="Help me")]),
            ),
            MessageEvent(
                id="agent2",
                source="agent",
                llm_message=Message(
                    role="assistant", content=[TextContent(text="Sure")]
                ),
            ),
        ]

        # 设置对话模拟对象
        conversation = MagicMock()
        state = MagicMock()
        state.events = events
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state
        event_service._conversation = conversation

        client.app.dependency_overrides[get_event_service] = lambda: event_service

        try:
            # 按 source="user" 测试过滤 - 应返回 2 个事件
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={"source": "user", "limit": 10},
            )

            assert response.status_code == 200
            result = response.json()
            assert len(result["items"]) == 2
            returned_ids = [event["id"] for event in result["items"]]
            assert "user1" in returned_ids
            assert "user2" in returned_ids

        finally:
            client.app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_search_events_with_body_filter_real_events(
        self, client, sample_conversation_id
    ):
        """用真实事件测试身体过滤。"""
        from openhands.agent_server.event_service import EventService
        from openhands.sdk.llm.message import TextContent

        # 使用示例事件创建真实的 EventService
        event_service = EventService(
            stored=MagicMock(), conversations_dir=Path("test_dir")
        )

        # 创建具有不同消息内容的事件
        events = [
            MessageEvent(
                id="hello1",
                source="user",
                llm_message=Message(
                    role="user", content=[TextContent(text="Hello world")]
                ),
            ),
            MessageEvent(
                id="python1",
                source="agent",
                llm_message=Message(
                    role="assistant", content=[TextContent(text="Python is great")]
                ),
            ),
            MessageEvent(
                id="hello2",
                source="user",
                llm_message=Message(
                    role="user", content=[TextContent(text="Say hello to everyone")]
                ),
            ),
            MessageEvent(
                id="other1",
                source="agent",
                llm_message=Message(
                    role="assistant", content=[TextContent(text="JavaScript rocks")]
                ),
            ),
        ]

        # 设置对话模拟对象
        conversation = MagicMock()
        state = MagicMock()
        state.events = events
        state.__enter__ = MagicMock(return_value=state)
        state.__exit__ = MagicMock(return_value=None)
        conversation._state = state
        event_service._conversation = conversation

        client.app.dependency_overrides[get_event_service] = lambda: event_service

        try:
            # 按 body="hello"（不区分大小写）测试过滤 - 应返回 2 个事件
            response = client.get(
                f"/api/conversations/{sample_conversation_id}/events/search",
                params={"body": "hello", "limit": 10},
            )

            assert response.status_code == 200
            result = response.json()
            assert len(result["items"]) == 2
            returned_ids = [event["id"] for event in result["items"]]
            assert "hello1" in returned_ids
            assert "hello2" in returned_ids

        finally:
            client.app.dependency_overrides.clear()


def test_unknown_event_id_is_404_and_null_in_batch(client, sample_conversation_id):
    """未知 id 是来自 get-one 的 404 和其批量获取槽中的 null。"""
    event_log = EventLog(InMemoryFileStore())
    known = MessageEvent(
        id="00000000-0000-0000-0000-000000000001",
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="hi")]),
    )
    event_log.append(known)
    event_service = EventService(stored=MagicMock(), conversations_dir=Path("x"))
    conversation = MagicMock()
    conversation._state.events = event_log
    event_service._conversation = conversation
    client.app.dependency_overrides[get_event_service] = lambda: event_service
    url = f"/api/conversations/{sample_conversation_id}/events"

    try:
        assert client.get(f"{url}/{known.id}").json()["id"] == known.id
        assert client.get(f"{url}/qa-missing-event").status_code == 404

        response = client.request(
            "GET", url, json=["qa-missing-event", known.id, "qa-missing-2"]
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        assert body[0] is None and body[2] is None
        assert body[1]["id"] == known.id
    finally:
        client.app.dependency_overrides.clear()
