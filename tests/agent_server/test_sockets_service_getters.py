"""在 sockets.py 中测试每个应用程序服务 getter。

WebSocket 处理程序必须读取 ``ConversationService`` 和
``BashEventService`` 来自 ``app.state``（由寿命或由
``POST /api/init`` 在 deferred-init 模式下）而不是导入时捕获的模块级单例。 这些帮助器
封装了该查找，并在未配置 ``app.state``
 时优雅地回退到模块级默认值（e.g. 当sockets.py作为没有生命周期的库导入时）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import WebSocketDisconnect

import openhands.agent_server.sockets as sockets_mod
from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.config import Config
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.event_service import EventService
from openhands.agent_server.sockets import (
    _get_bash_event_service,
    _get_conversation_service,
)


def _make_ws(state: dict[str, object] | None = None) -> MagicMock:
    """构建一个模拟对象 WebSocket，其 ``app.state`` 暴露 ``state``。"""
    ws = MagicMock()
    ws.app.state = SimpleNamespace()
    if state is not None:
        ws.app.state = SimpleNamespace(**state)
    return ws


@pytest.fixture
def conv_service():
    return MagicMock(spec=ConversationService)


@pytest.fixture
def bash_service():
    return MagicMock(spec=BashEventService)


# -- _get_conversation_service --


def test_get_conversation_service_prefers_app_state(conv_service):
    """当应用程序注册一项服务时，会返回该服务（而不是
    模块级单例）。"""
    ws = _make_ws({"conversation_service": conv_service})
    assert _get_conversation_service(ws) is conv_service


def test_get_conversation_service_falls_back_to_module_singleton():
    """当``app.state``没有会话服务时，模块级
    返回默认值（保留修补模块级单例的测试的行为）。
    """
    ws = _make_ws()
    assert _get_conversation_service(ws) is sockets_mod.conversation_service


def test_get_conversation_service_ignores_wrong_type():
    """如果 ``app.state.conversation_service`` 设置为非
    a ConversationService (e.g. None 或其他一些对象），回退到模块级默认值而不是炸毁。
    """
    for bogus in (None, "not a service", 42):
        ws = _make_ws({"conversation_service": bogus})
        # 不能引发——只返回模块级默认值。
        result = _get_conversation_service(ws)
        assert isinstance(result, ConversationService)


# -- _get_bash_event_service --


def test_get_bash_event_service_prefers_app_state(bash_service):
    ws = _make_ws({"bash_event_service": bash_service})
    assert _get_bash_event_service(ws) is bash_service


def test_get_bash_event_service_falls_back_to_module_singleton():
    ws = _make_ws()
    assert _get_bash_event_service(ws) is sockets_mod.bash_event_service


def test_get_bash_event_service_ignores_wrong_type():
    for bogus in (None, "not a service", 42):
        ws = _make_ws({"bash_event_service": bogus})
        result = _get_bash_event_service(ws)
        assert isinstance(result, BashEventService)


# -- 与配置集成 --


def test_get_conversation_service_handles_real_config(tmp_path):
    """健全性检查：助手返回一个真实的 ConversationService 构建的
    from a Config on ``app.state`` rather than the import-time default."""
    from openhands.agent_server import conversation_service as cs_mod

    original_default = sockets_mod.conversation_service
    cs_mod._conversation_service = None
    try:
        new_service = ConversationService(
            conversations_dir=tmp_path / "convs",
        )
        cfg = Config(
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "bash",
        )
        ws = _make_ws({"conversation_service": new_service, "config": cfg})
        assert _get_conversation_service(ws) is new_service
        assert _get_conversation_service(ws) is not original_default
    finally:
        cs_mod._conversation_service = None


def test_get_bash_event_service_handles_real_config(tmp_path):
    """健全性检查：助手返回一个真实的 BashEventService 构建的
    from a Config on ``app.state`` rather than the import-time default."""
    from openhands.agent_server import bash_service as bash_mod

    original_default = sockets_mod.bash_event_service
    bash_mod._bash_event_service = None
    try:
        new_service = BashEventService(bash_events_dir=tmp_path / "user" / "bash")
        cfg = Config(
            conversations_path=tmp_path / "convs",
            bash_events_dir=tmp_path / "user" / "bash",
        )
        ws = _make_ws({"bash_event_service": new_service, "config": cfg})
        assert _get_bash_event_service(ws) is new_service
        assert _get_bash_event_service(ws) is not original_default
    finally:
        bash_mod._bash_event_service = None


# -- 端到端：WebSocket 处理程序在 /api/init 之后使用每个应用程序服务 --


@pytest.mark.asyncio
async def test_events_socket_uses_app_state_conversation_service():
    """events_socket 必须使用 app.state.conversation_service（由 /api/init) 设置）
    而不是在导入时捕获的模块级单例。"""
    from openhands.agent_server.sockets import events_socket

    mock_event_svc = MagicMock(spec=EventService)
    mock_event_svc.subscribe_to_events = AsyncMock(return_value=uuid4())
    mock_event_svc.unsubscribe_from_events = AsyncMock(return_value=True)

    per_app_conv_svc = MagicMock(spec=ConversationService)
    per_app_conv_svc.get_event_service = AsyncMock(return_value=mock_event_svc)

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.headers = {}
    # 在 /api/init 提供每用户服务后模拟 app.state。
    ws.app.state = SimpleNamespace(
        conversation_service=per_app_conv_svc,
        config=Config(session_api_keys=[]),
    )

    await events_socket(uuid4(), ws, session_api_key=None)

    per_app_conv_svc.get_event_service.assert_called_once()
    mock_event_svc.subscribe_to_events.assert_called_once()
    mock_event_svc.unsubscribe_from_events.assert_called_once()


@pytest.mark.asyncio
async def test_bash_events_socket_uses_app_state_bash_event_service():
    """bash_events_socket 必须使用 app.state.bash_event_service（由 /api/init) 设置）
    而不是在导入时捕获的模块级单例。"""
    from openhands.agent_server.sockets import bash_events_socket

    per_app_bash_svc = MagicMock(spec=BashEventService)
    per_app_bash_svc.subscribe_to_events = AsyncMock(return_value=uuid4())
    per_app_bash_svc.unsubscribe_from_events = AsyncMock(return_value=True)

    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.receive_json = AsyncMock(side_effect=WebSocketDisconnect())
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.headers = {}
    # 在 /api/init 提供每用户服务后模拟 app.state。
    ws.app.state = SimpleNamespace(
        bash_event_service=per_app_bash_svc,
        config=Config(session_api_keys=[]),
    )

    await bash_events_socket(ws, session_api_key=None)

    per_app_bash_svc.subscribe_to_events.assert_called_once()
    per_app_bash_svc.unsubscribe_from_events.assert_called_once()


@pytest.mark.parametrize("send_fails", [False, True])
async def test_events_socket_preserves_diagnostics_without_extra_stack(
    caplog, send_fails
):
    event_service = MagicMock(spec=EventService)
    subscriber_id = uuid4()
    event_service.subscribe_to_events = AsyncMock(return_value=subscriber_id)
    event_service.unsubscribe_from_events = AsyncMock()
    service = MagicMock(spec=ConversationService)
    service.get_event_service = AsyncMock(return_value=event_service)
    ws = _make_ws(
        {
            "conversation_service": service,
            "config": Config(session_api_keys=[]),
        }
    )
    ws.headers = {}
    ws.accept = AsyncMock()
    ws.receive_json = AsyncMock(
        side_effect=[ValueError("invalid input"), WebSocketDisconnect()]
    )
    ws.send_json = AsyncMock(side_effect=RuntimeError("closed") if send_fails else None)
    ws.close = AsyncMock()
    caplog.set_level("DEBUG", logger=sockets_mod.__name__)

    await sockets_mod.events_socket(uuid4(), ws)

    payload = ws.send_json.call_args.args[0]
    assert payload["code"] == "ValueError"
    assert payload["detail"] == "invalid input"
    event_service.unsubscribe_from_events.assert_awaited_once_with(subscriber_id)
    records = [
        record for record in caplog.records if record.name == sockets_mod.__name__
    ]
    assert records
    assert all(record.stack_info is None for record in records)
    if send_fails:
        assert all(record.exc_info is None for record in records)
        assert any("Event websocket disconnected" in r.getMessage() for r in records)
    else:
        error_record = next(
            r for r in records if r.getMessage().startswith("error_in_subscription")
        )
        assert error_record.exc_info is not None
        assert isinstance(error_record.exc_info[1], ValueError)
        assert str(error_record.exc_info[1]) == "invalid input"
        assert error_record.exc_info[2] is not None
