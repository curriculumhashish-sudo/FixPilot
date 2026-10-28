"""测试 GET /conversations/{id}/agent_final_response 端点。"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server.conversation_router import conversation_router
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.event_service import EventService
from openhands.sdk import LLM, Agent, Conversation, LocalConversation, Message
from openhands.sdk.event import ActionEvent, MessageEvent
from openhands.sdk.llm import MessageToolCall, TextContent
from openhands.sdk.tool.builtins.finish import FinishAction


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(conversation_router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def sample_conversation_id():
    return uuid4()


@pytest.fixture
def mock_conversation_service():
    return AsyncMock(spec=ConversationService)


@pytest.fixture
def mock_event_service():
    return AsyncMock(spec=EventService)


def test_get_response_with_finish_action(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """端点返回 FinishAction 消息文本。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_agent_final_response.return_value = (
        "Task completed successfully!"
    )

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    try:
        response = client.get(
            f"/api/conversations/{sample_conversation_id}/agent_final_response"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Task completed successfully!"
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
        mock_event_service.get_agent_final_response.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_get_response_empty_when_no_agent_events(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """当不存在智能体响应时，端点返回空字符串。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_agent_final_response.return_value = ""

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    try:
        response = client.get(
            f"/api/conversations/{sample_conversation_id}/agent_final_response"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == ""
    finally:
        client.app.dependency_overrides.clear()


def test_get_response_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """端点当对话不存在时返回 404。"""
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    try:
        response = client.get(
            f"/api/conversations/{sample_conversation_id}/agent_final_response"
        )
        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_event_service_get_agent_final_response_with_finish():
    """EventService 从 SDK 委托给 get_agent_final_response。"""
    event_service = EventService(stored=MagicMock(), conversations_dir=Path("test_dir"))

    finish_action = FinishAction(message="Done!")
    tool_call = MessageToolCall(
        id="tc1", name="finish", arguments="{}", origin="completion"
    )
    action_event = ActionEvent(
        source="agent",
        thought=[TextContent(text="Finishing")],
        action=finish_action,
        tool_name="finish",
        tool_call_id="tc1",
        tool_call=tool_call,
        llm_response_id="resp1",
    )

    conversation = MagicMock()
    state = MagicMock()
    state.active_branch.return_value = [action_event]
    conversation._state = state
    event_service._conversation = conversation

    result = event_service._get_agent_final_response_sync()
    assert result == "Done!"


def test_event_service_get_agent_final_response_with_message():
    """当没有 FinishAction 时，EventService 返回 MessageEvent 文本。"""
    event_service = EventService(stored=MagicMock(), conversations_dir=Path("test_dir"))

    message_event = MessageEvent(
        source="agent",
        llm_message=Message(
            role="assistant",
            content=[TextContent(text="Here is my answer")],
        ),
    )

    conversation = MagicMock()
    state = MagicMock()
    state.active_branch.return_value = [message_event]
    conversation._state = state
    event_service._conversation = conversation

    result = event_service._get_agent_final_response_sync()
    assert result == "Here is my answer"


def test_event_service_get_agent_final_response_empty():
    """EventService 返回空字符串，没有智能体事件。"""
    event_service = EventService(stored=MagicMock(), conversations_dir=Path("test_dir"))

    conversation = MagicMock()
    state = MagicMock()
    state.active_branch.return_value = []
    conversation._state = state
    event_service._conversation = conversation

    result = event_service._get_agent_final_response_sync()
    assert result == ""


def test_event_service_get_agent_final_response_inactive():
    """当服务处于非活动状态时，EventService 会引发 ValueError。"""
    event_service = EventService(stored=MagicMock(), conversations_dir=Path("test_dir"))

    with pytest.raises(ValueError, match="inactive_service"):
        event_service._get_agent_final_response_sync()


def test_event_service_get_agent_final_response_ignores_abandoned_branch():
    """返回到答案之前后，放弃的答案将被忽略。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        conversation = Conversation(
            agent=Agent(
                llm=LLM(model="gpt-4o-mini", api_key=SecretStr("k"), usage_id="t"),
                tools=[],
            ),
            persistence_dir=tmpdir,
            workspace=tmpdir,
            visualizer=None,
        )
        assert isinstance(conversation, LocalConversation)
        user = MessageEvent(
            source="user",
            llm_message=Message(role="user", content=[TextContent(text="hi")]),
        )
        answer = MessageEvent(
            source="agent",
            llm_message=Message(role="assistant", content=[TextContent(text="OK")]),
        )
        with conversation._state:
            conversation._on_event(user)
            conversation._on_event(answer)

        event_service = EventService(stored=MagicMock(), conversations_dir=Path(tmpdir))
        event_service._conversation = conversation
        assert event_service._get_agent_final_response_sync() == "OK"

        conversation.navigate_to(user.id)
        assert event_service._get_agent_final_response_sync() == ""

        conversation.navigate_to(answer.id)
        assert event_service._get_agent_final_response_sync() == "OK"
