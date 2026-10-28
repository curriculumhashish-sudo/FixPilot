"""测试 event_router.py 中的 WebSocket 功能"""

import logging
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketState

from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import BashCommand, BashOutput, EventPage
from openhands.agent_server.sockets import _send_bash_event, _WebSocketSubscriber
from openhands.sdk import Message
from openhands.sdk.event import Event
from openhands.sdk.event.llm_convertible import MessageEvent
from openhands.sdk.llm.message import TextContent


@pytest.fixture
def mock_websocket():
    """创建模拟对象 WebSocket 进行测试。"""
    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.receive_json = AsyncMock()
    websocket.send_json = AsyncMock()
    websocket.close = AsyncMock()
    websocket.application_state = MagicMock()
    return websocket


@pytest.fixture
def mock_event_service():
    """创建模拟对象 EventService 进行测试。"""
    service = MagicMock(spec=EventService)
    service.subscribe_to_events = AsyncMock(return_value=uuid4())
    service.unsubscribe_from_events = AsyncMock(return_value=True)
    service.send_message = AsyncMock()
    service.search_events = AsyncMock()
    return service


@pytest.fixture
def sample_conversation_id():
    """返回示例对话 ID。"""
    return uuid4()


@pytest.mark.asyncio
async def test_websocket_subscriber_call_success(mock_websocket):
    """测试通过 WebSocket 订阅者发送成功的事件。"""
    subscriber = _WebSocketSubscriber(websocket=mock_websocket)
    event = MessageEvent(
        id="test_event",
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="test")]),
    )

    await subscriber(event)

    mock_websocket.send_json.assert_called_once()
    call_args = mock_websocket.send_json.call_args[0][0]
    assert call_args["id"] == "test_event"


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_websocket_subscriber_call_exception(mock_websocket):
    """测试 WebSocket 订阅者中的异常处理。"""
    mock_websocket.send_json.side_effect = Exception("Connection error")
    subscriber = _WebSocketSubscriber(websocket=mock_websocket)
    event = MessageEvent(
        id="test_event",
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="test")]),
    )

    # 不应引发异常，只需记录它
    await subscriber(event)

    mock_websocket.send_json.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_subscriber_skips_send_when_disconnected(mock_websocket):
    """Regression: pub/sub 回调不得在已关闭的套接字上尝试 send()。

    如果我们在断开连接后发送，Starlette 会引发
    ``RuntimeError: Cannot call "send" once a close message has been sent.``。 订阅者
    应该检测
    DISCONNECTED 状态并静默跳过。
    """
    from starlette.websockets import WebSocketState

    mock_websocket.application_state = WebSocketState.DISCONNECTED
    subscriber = _WebSocketSubscriber(websocket=mock_websocket)
    event = MessageEvent(
        id="test_event",
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="test")]),
    )

    await subscriber(event)

    mock_websocket.send_json.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_subscriber_send_runtime_error_not_logged_as_exception(
    mock_websocket,
):
    """Regression: 来自发送的 RuntimeError（断开连接和发送之间的竞争）
    应该在调试级别记录，而不是作为完整的回溯
    ``logger.exception``.
    """
    mock_websocket.send_json.side_effect = RuntimeError(
        'Cannot call "send" once a close message has been sent.'
    )
    subscriber = _WebSocketSubscriber(websocket=mock_websocket)
    event = MessageEvent(
        id="test_event",
        source="user",
        llm_message=Message(role="user", content=[TextContent(text="test")]),
    )

    with patch("openhands.agent_server.sockets.logger") as mock_logger:
        await subscriber(event)

    mock_websocket.send_json.assert_called_once()
    mock_logger.exception.assert_not_called()
    mock_logger.debug.assert_called()


@pytest.mark.asyncio
async def test_send_bash_event_disconnected_log_omits_command(
    mock_websocket,
    caplog: pytest.LogCaptureFixture,
):
    secret = "ghp_" + "g" * 36
    event = BashCommand(command=f"printf '{secret}'")
    mock_websocket.application_state = WebSocketState.DISCONNECTED
    caplog.set_level(logging.DEBUG, logger="openhands.agent_server.sockets")

    await _send_bash_event(event, mock_websocket)

    mock_websocket.send_json.assert_not_awaited()
    assert "skip_sending_bash_event_socket_disconnected" in caplog.text
    assert str(event.id) in caplog.text
    assert secret not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("exception_type", [RuntimeError, ValueError])
async def test_send_bash_event_error_logs_omit_output_and_exception(
    mock_websocket,
    caplog: pytest.LogCaptureFixture,
    exception_type: type[Exception],
):
    output_secret = "ghp_" + "h" * 36
    exception_secret = "sk-oh-" + "i" * 64
    event = BashOutput(
        command_id=uuid4(),
        stdout=output_secret,
        stderr=f"failed with {output_secret}",
    )
    mock_websocket.send_json.side_effect = exception_type(exception_secret)
    caplog.set_level(logging.DEBUG, logger="openhands.agent_server.sockets")

    await _send_bash_event(event, mock_websocket)

    mock_websocket.send_json.assert_awaited_once()
    assert "error_sending_bash_event" in caplog.text
    assert str(event.command_id) in caplog.text
    assert exception_type.__name__ in caplog.text
    assert output_secret not in caplog.text
    assert exception_secret not in caplog.text


@pytest.mark.asyncio
async def test_websocket_disconnect_breaks_loop(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试 WebSocketDisconnect 异常是否会中断循环。"""
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id, mock_websocket, session_api_key=None
        )

    mock_event_service.unsubscribe_from_events.assert_called()


@pytest.mark.asyncio
async def test_websocket_no_double_unsubscription(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试即使在断开连接的情况下，取消订阅也只会发生一次。"""
    subscriber_id = uuid4()
    mock_event_service.subscribe_to_events.return_value = subscriber_id
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id, mock_websocket, session_api_key=None
        )

    assert mock_event_service.unsubscribe_from_events.call_count == 1
    mock_event_service.unsubscribe_from_events.assert_called_with(subscriber_id)


@pytest.mark.asyncio
async def test_websocket_general_exception_continues_loop(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试一般异常不会立即中断循环。"""
    call_count = 0

    def side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Some error")
        elif call_count == 2:
            raise WebSocketDisconnect()

    mock_websocket.receive_json.side_effect = side_effect

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
        patch("openhands.agent_server.sockets.logger.exception") as log_exception,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id, mock_websocket, session_api_key=None
        )

        log_exception.assert_called_once_with("error_in_subscription")

    assert mock_websocket.receive_json.call_count == 2
    mock_event_service.unsubscribe_from_events.assert_called_once()


@pytest.mark.asyncio
async def test_websocket_successful_message_processing(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """在断开连接之前测试消息处理是否成功。"""
    message_data = {"role": "user", "content": "Hello"}
    call_count = 0

    def side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return message_data
        else:
            raise WebSocketDisconnect()

    mock_websocket.receive_json.side_effect = side_effect

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id, mock_websocket, session_api_key=None
        )

    mock_event_service.send_message.assert_called_once()
    assert mock_websocket.receive_json.call_count == 2


@pytest.mark.asyncio
async def test_disconnect_and_unsubscribe_when_send_error_fails(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试发送时调用unsubscribe并且socket断开连接
    错误事件失败。"""
    mock_websocket.receive_json.side_effect = RuntimeError("Connection broken")
    mock_websocket.send_json.side_effect = RuntimeError("Connection broken")

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
        patch("openhands.agent_server.sockets.logger.debug") as log_debug,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        # RuntimeError 被优雅地捕获（如 WebSocketDisconnect）并且函数正常返回
        #
        await events_socket(
            sample_conversation_id, mock_websocket, session_api_key=None
        )

    log_debug.assert_called_once()
    mock_event_service.unsubscribe_from_events.assert_called_once()


@pytest.mark.asyncio
async def test_resend_mode_none_no_resend(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试 resend_mode=None 不会触发事件重新发送。"""
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id,
            mock_websocket,
            session_api_key=None,
            resend_mode=None,
        )

    mock_event_service.search_events.assert_not_called()


@pytest.mark.asyncio
async def test_resend_mode_all_resends_events(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试 resend_mode='all' 重新发送所有现有事件。"""
    mock_events = [
        MessageEvent(
            id="event1",
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="Hello")]),
        ),
        MessageEvent(
            id="event2",
            source="agent",
            llm_message=Message(role="assistant", content=[TextContent(text="Hi")]),
        ),
    ]
    mock_event_page = EventPage(items=cast(list[Event], mock_events), next_page_id=None)
    mock_event_service.search_events = AsyncMock(return_value=mock_event_page)
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id,
            mock_websocket,
            session_api_key=None,
            resend_mode="all",
        )

    mock_event_service.search_events.assert_called_once_with(page_id=None)
    assert mock_websocket.send_json.call_count == 2
    sent_events = [call[0][0] for call in mock_websocket.send_json.call_args_list]
    assert sent_events[0]["id"] == "event1"
    assert sent_events[1]["id"] == "event2"


@pytest.mark.asyncio
async def test_resend_mode_since_with_timestamp(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试 resend_mode='since' 和 after_timestamp 过滤事件。"""
    mock_events = [
        MessageEvent(
            id="event1",
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="Hello")]),
        ),
    ]
    mock_event_page = EventPage(items=cast(list[Event], mock_events), next_page_id=None)
    mock_event_service.search_events = AsyncMock(return_value=mock_event_page)
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    # 使用朴素的时间戳
    test_timestamp = datetime(2024, 1, 15, 10, 30, 0)

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id,
            mock_websocket,
            session_api_key=None,
            resend_mode="since",
            after_timestamp=test_timestamp,
        )

    mock_event_service.search_events.assert_called_once_with(
        page_id=None, timestamp__gte=test_timestamp
    )


@pytest.mark.asyncio
async def test_resend_mode_since_without_timestamp_logs_warning(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试 resend_mode='since' 而没有 after_timestamp 记录警告。"""
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
        patch("openhands.agent_server.sockets.logger") as mock_logger,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id,
            mock_websocket,
            session_api_key=None,
            resend_mode="since",
            after_timestamp=None,
        )

    # 应该记录警告而不是调用 search_events
    mock_logger.warning.assert_called()
    warning_call = str(mock_logger.warning.call_args)
    assert "resend_mode='since' requires after_timestamp" in warning_call
    mock_event_service.search_events.assert_not_called()


@pytest.mark.asyncio
async def test_resend_mode_since_timezone_aware_is_normalized(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试时区感知时间戳是否标准化为原始服务器时间。"""
    mock_events = [
        MessageEvent(
            id="event1",
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="Hello")]),
        ),
    ]
    mock_event_page = EventPage(items=cast(list[Event], mock_events), next_page_id=None)
    mock_event_service.search_events = AsyncMock(return_value=mock_event_page)
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    # 使用时区感知时间戳 (UTC)
    test_timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id,
            mock_websocket,
            session_api_key=None,
            resend_mode="since",
            after_timestamp=test_timestamp,
        )

    # search_events 应该使用规范化时间戳来调用
    mock_event_service.search_events.assert_called_once()
    call_args = mock_event_service.search_events.call_args
    passed_timestamp = call_args.kwargs["timestamp__gte"]
    # 时间戳应该是天真的（没有tzinfo）
    assert passed_timestamp is not None
    assert passed_timestamp.tzinfo is None
    # 它应该代表同一时刻（转换为本地）
    expected = test_timestamp.astimezone(None).replace(tzinfo=None)
    assert passed_timestamp == expected


# 向后兼容性测试已弃用 resend_all 参数


@pytest.mark.asyncio
async def test_deprecated_resend_all_true_still_works(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试向后兼容性：resend_all=True 仍然重新发送所有事件。"""
    mock_events = [
        MessageEvent(
            id="event1",
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="Hello")]),
        ),
    ]
    mock_event_page = EventPage(items=cast(list[Event], mock_events), next_page_id=None)
    mock_event_service.search_events = AsyncMock(return_value=mock_event_page)
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
        patch("openhands.agent_server.sockets.logger") as mock_logger,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id,
            mock_websocket,
            session_api_key=None,
            resend_all=True,
        )

    # 应记录弃用警告
    mock_logger.warning.assert_called()
    warning_call = str(mock_logger.warning.call_args)
    assert "resend_all is deprecated" in warning_call

    # 但仍能正常运行
    mock_event_service.search_events.assert_called_once_with(page_id=None)
    assert mock_websocket.send_json.call_count == 1


@pytest.mark.asyncio
async def test_deprecated_resend_all_false_no_resend(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试向后兼容性：resend_all=False 不会触发事件重新发送。"""
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        await events_socket(
            sample_conversation_id,
            mock_websocket,
            session_api_key=None,
            resend_all=False,
        )

    mock_event_service.search_events.assert_not_called()


@pytest.mark.asyncio
async def test_resend_mode_takes_precedence_over_resend_all(
    mock_websocket, mock_event_service, sample_conversation_id
):
    """测试 resend_mode 优先于已弃用 resend_all。"""
    mock_websocket.receive_json.side_effect = WebSocketDisconnect()

    with (
        patch(
            "openhands.agent_server.sockets.conversation_service"
        ) as mock_conv_service,
        patch("openhands.agent_server.sockets.get_default_config") as mock_config,
        patch("openhands.agent_server.sockets.logger") as mock_logger,
    ):
        mock_config.return_value.session_api_keys = None
        mock_conv_service.get_event_service = AsyncMock(return_value=mock_event_service)

        from openhands.agent_server.sockets import events_socket

        # 如果 resend_mode 显式为 None 并且 resend_all=True，则它应该回退方案到
        # resend_all 行为以实现向后兼容。 但如果设置了resend_mode，则它优先于resend_all
        # 。 让我们用 resend_mode="all" 和 resend_all=False 进行测试
        #
        mock_events = [
            MessageEvent(
                id="event1",
                source="user",
                llm_message=Message(role="user", content=[TextContent(text="Hello")]),
            ),
        ]
        mock_event_page = EventPage(
            items=cast(list[Event], mock_events), next_page_id=None
        )
        mock_event_service.search_events = AsyncMock(return_value=mock_event_page)

        await events_socket(
            sample_conversation_id,
            mock_websocket,
            session_api_key=None,
            resend_mode="all",
            resend_all=False,  # 由于设置了 resend_mode，因此应忽略此设置
        )

    # resend_mode="all" should trigger resend, not the resend_all=False
    mock_event_service.search_events.assert_called_once()
    # 由于我们使用新的 API，因此没有弃用警告
    warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
    assert not any("resend_all is deprecated" in w for w in warning_calls)
