"""测试 API 层中的对话标签。"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server.conversation_router import conversation_router
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.event_service import EventService
from openhands.agent_server.models import (
    ConversationInfo,
    StoredConversation,
    UpdateConversationRequest,
)
from openhands.agent_server.utils import utc_now
from openhands.sdk import LLM, Agent, Tool
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.security.confirmation_policy import NeverConfirm
from openhands.sdk.workspace import LocalWorkspace


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(conversation_router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def mock_conversation_service():
    return AsyncMock(spec=ConversationService)


@pytest.fixture
def mock_event_service():
    return AsyncMock(spec=EventService)


@pytest.fixture
def sample_conversation_info():
    now = utc_now()
    return ConversationInfo(
        id=uuid4(),
        agent=Agent(
            llm=LLM(
                model="gpt-4o",
                api_key=SecretStr("test-key"),
                usage_id="test-llm",
            ),
            tools=[Tool(name="TerminalTool")],
        ),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
        execution_status=ConversationExecutionStatus.IDLE,
        title="Test Conversation",
        tags={"env": "test", "team": "backend"},
        created_at=now,
        updated_at=now,
    )


def test_start_conversation_with_tags(
    client, mock_conversation_service, sample_conversation_info
):
    """开始对话时，标签将转发到服务。"""
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )
    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    try:
        request_data = {
            "agent": {
                "llm": {
                    "model": "gpt-4o",
                    "api_key": "test-key",
                    "usage_id": "test-llm",
                },
                "tools": [{"name": "TerminalTool"}],
            },
            "workspace": {"working_dir": "/tmp/test"},
            "tags": {"env": "prod", "team": "infra"},
        }
        response = client.post("/api/conversations", json=request_data)

        assert response.status_code == 201
        call_args = mock_conversation_service.start_conversation.call_args
        request_arg = call_args[0][0]
        assert request_arg.tags == {"env": "prod", "team": "infra"}
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_without_tags(
    client, mock_conversation_service, sample_conversation_info
):
    """没有标签的情况下默认为空字典。"""
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )
    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    try:
        request_data = {
            "agent": {
                "llm": {
                    "model": "gpt-4o",
                    "api_key": "test-key",
                    "usage_id": "test-llm",
                },
                "tools": [{"name": "TerminalTool"}],
            },
            "workspace": {"working_dir": "/tmp/test"},
        }
        response = client.post("/api/conversations", json=request_data)

        assert response.status_code == 201
        call_args = mock_conversation_service.start_conversation.call_args
        request_arg = call_args[0][0]
        assert request_arg.tags == {}
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_invalid_tag_key(client, mock_conversation_service):
    """无效的标签键将被拒绝并返回 422。"""
    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    try:
        request_data = {
            "agent": {
                "llm": {
                    "model": "gpt-4o",
                    "api_key": "test-key",
                    "usage_id": "test-llm",
                },
                "tools": [{"name": "TerminalTool"}],
            },
            "workspace": {"working_dir": "/tmp/test"},
            "tags": {"INVALID-KEY": "value"},
        }
        response = client.post("/api/conversations", json=request_data)
        assert response.status_code == 422
    finally:
        client.app.dependency_overrides.clear()


def test_update_conversation_tags(client, mock_conversation_service):
    """PATCH 端点更新标签。"""
    mock_conversation_service.update_conversation.return_value = True
    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    conversation_id = uuid4()
    try:
        response = client.patch(
            f"/api/conversations/{conversation_id}",
            json={"tags": {"env": "staging"}},
        )

        assert response.status_code == 200
        assert response.json() == {"success": True}
        call_args = mock_conversation_service.update_conversation.call_args
        request_arg = call_args[0][1]
        assert isinstance(request_arg, UpdateConversationRequest)
        assert request_arg.tags == {"env": "staging"}
        assert request_arg.title is None
    finally:
        client.app.dependency_overrides.clear()


def test_update_conversation_title_and_tags(client, mock_conversation_service):
    """PATCH 端点可以更新标题和标签。"""
    mock_conversation_service.update_conversation.return_value = True
    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    conversation_id = uuid4()
    try:
        response = client.patch(
            f"/api/conversations/{conversation_id}",
            json={"title": "New Title", "tags": {"env": "prod"}},
        )

        assert response.status_code == 200
        call_args = mock_conversation_service.update_conversation.call_args
        request_arg = call_args[0][1]
        assert request_arg.title == "New Title"
        assert request_arg.tags == {"env": "prod"}
    finally:
        client.app.dependency_overrides.clear()


def test_get_conversation_includes_tags(
    client, mock_conversation_service, sample_conversation_info
):
    """GET 端点返回响应中的标签。"""
    mock_conversation_service.get_conversation.return_value = sample_conversation_info
    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )

    try:
        response = client.get(f"/api/conversations/{sample_conversation_info.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["tags"] == {"env": "test", "team": "backend"}
    finally:
        client.app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_event_service_start_forwards_tags_to_local_conversation(tmp_path):
    """EventService.start() 必须将存储的标签传递给 LocalConversation。

    回归测试通过 POST /api/conversations 发送的
    https://github.com/OpenHands/software-agent-sdk/issues/2821:  标记在
    StoredConversation 中为已持久化，但未转发到 LocalConversation 构造函数，因此
    state.tags 始终为 {}。
    """
    tags = {"source": "pipeline", "symbol": "gold"}
    stored = StoredConversation(
        id=uuid4(),
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
        confirmation_policy=NeverConfirm(),
        tags=tags,
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
    )

    event_service = EventService(
        stored=stored,
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        conversations_dir=tmp_path / "conversations",
    )

    with patch(
        "openhands.agent_server.event_service.LocalConversation"
    ) as MockConversation:
        mock_conv = MagicMock()
        mock_state = MagicMock()
        mock_state.execution_status = ConversationExecutionStatus.IDLE
        mock_state.events = []
        mock_agent = MagicMock()
        mock_agent.get_all_llms.return_value = []
        mock_conv._state = mock_state
        mock_conv.state = mock_state
        mock_conv.agent = mock_agent
        mock_conv._on_event = MagicMock()
        MockConversation.return_value = mock_conv

        await event_service.start()

        # 验证使用正确的标签调用 LocalConversation
        MockConversation.assert_called_once()
        call_kwargs = MockConversation.call_args.kwargs
        assert call_kwargs["tags"] == tags


@pytest.mark.asyncio
async def test_event_service_start_forwards_observability_span_name(tmp_path):
    """EventService.start() 必须将存储的子范围名称传递给 LocalConversation。"""
    stored = StoredConversation(
        id=uuid4(),
        workspace=LocalWorkspace(working_dir=str(tmp_path)),
        confirmation_policy=NeverConfirm(),
        observability_span_name="pr_review_evaluation",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2025, 1, 1, 12, 30, 0, tzinfo=UTC),
    )

    event_service = EventService(
        stored=stored,
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        conversations_dir=tmp_path / "conversations",
    )

    with patch(
        "openhands.agent_server.event_service.LocalConversation"
    ) as MockConversation:
        mock_conv = MagicMock()
        mock_state = MagicMock()
        mock_state.execution_status = ConversationExecutionStatus.IDLE
        mock_state.events = []
        mock_agent = MagicMock()
        mock_agent.get_all_llms.return_value = []
        mock_conv._state = mock_state
        mock_conv.state = mock_state
        mock_conv.agent = mock_agent
        mock_conv._on_event = MagicMock()
        MockConversation.return_value = mock_conv

        await event_service.start()

        MockConversation.assert_called_once()
        call_kwargs = MockConversation.call_args.kwargs
        assert call_kwargs["observability_span_name"] == "pr_review_evaluation"
