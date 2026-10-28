"""测试 conversation_router.py 端点。"""

import time
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from openhands.agent_server.config import Config
from openhands.agent_server.conversation_registry import ConversationRegistry
from openhands.agent_server.conversation_router import conversation_router
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.dependencies import get_conversation_service
from openhands.agent_server.event_service import CondensationUnavailable, EventService
from openhands.agent_server.launch import launch_source
from openhands.agent_server.models import (
    ConversationInfo,
    ConversationPage,
    ConversationRuntimeInfo,
    ConversationRuntimeStatus,
    ConversationSortOrder,
    SendMessageRequest,
    StartConversationRequest,
)
from openhands.agent_server.utils import utc_now
from openhands.sdk import LLM, Agent, TextContent, Tool
from openhands.sdk.agent.acp_agent import ACPAgent
from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.launch import LaunchRuntime, LaunchStores, finalize
from openhands.sdk.llm import llm_profile_store
from openhands.sdk.llm.llm_profile_store import LLMProfileStore
from openhands.sdk.marketplace.registry import (
    PluginNotFoundError,
    PluginResolutionError,
)
from openhands.sdk.plugin import PluginFetchError
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
from openhands.sdk.settings import AGENT_SETTINGS_SCHEMA_VERSION
from openhands.sdk.workspace import LocalWorkspace


@pytest.fixture
def client():
    """为没有身份验证的 FastAPI 应用程序创建一个测试客户端。"""
    app = FastAPI()
    app.include_router(conversation_router, prefix="/api")
    # switch_llm读取request.app.state.config以获取可选密码； 使用无密码配置填充它，这样
    # 不相关的测试就不会发生 503。
    #
    app.state.config = Config(
        static_files_path=None, session_api_keys=[], secret_key=None
    )
    return TestClient(app)


@pytest.fixture
def sample_conversation_id():
    """返回示例对话 ID。"""
    return uuid4()


@pytest.fixture
def sample_conversation_info():
    """创建样本 ConversationInfo 进行测试。"""
    conversation_id = uuid4()
    now = utc_now()
    return ConversationInfo(
        id=conversation_id,
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
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def mock_conversation_service():
    """创建模拟对象 ConversationService 进行测试。"""
    service = AsyncMock(spec=ConversationService)
    return service


@pytest.fixture
def mock_event_service():
    """创建模拟对象 EventService 进行测试。"""
    service = AsyncMock(spec=EventService)
    return service


@pytest.fixture
def llm_security_analyzer():
    """创建一个 LLMSecurityAnalyzer 进行测试。"""
    return LLMSecurityAnalyzer()


@pytest.fixture
def sample_start_conversation_request():
    """创建样本 StartConversationRequest 进行测试。"""
    return StartConversationRequest(
        agent=Agent(
            llm=LLM(
                model="gpt-4o",
                api_key=SecretStr("test-key"),
                usage_id="test-llm",
            ),
            tools=[Tool(name="TerminalTool")],
        ),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
        initial_message=SendMessageRequest(
            role="user", content=[TextContent(text="Hello, world!")]
        ),
    )


def test_search_conversations_default_params(
    client, mock_conversation_service, sample_conversation_info
):
    """使用默认参数测试 search_conversations 端点。"""

    # 模拟对象服务响应
    mock_page = ConversationPage(items=[sample_conversation_info], next_page_id=None)
    mock_conversation_service.search_conversations.return_value = mock_page

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get("/api/conversations/search")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "next_page_id" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == str(sample_conversation_info.id)

        # 验证使用默认参数调用服务
        mock_conversation_service.search_conversations.assert_called_once_with(
            None, 100, None, ConversationSortOrder.CREATED_AT_DESC
        )
    finally:
        client.app.dependency_overrides.clear()


def test_search_conversations_includes_runtime_info(
    client, mock_conversation_service, sample_conversation_info
):
    mock_conversation_service.search_conversations.return_value = ConversationPage(
        items=[sample_conversation_info]
    )

    class MissingRuntimeRegistry(ConversationRegistry):
        def runtime_info(self, conversation_id: UUID) -> ConversationRuntimeInfo:
            return ConversationRuntimeInfo(
                runtime_status=ConversationRuntimeStatus.MISSING,
                can_resume=False,
            )

    registry = MissingRuntimeRegistry(client.app.state.config)
    client.app.state.conversation_registry = registry
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get("/api/conversations/search")
    finally:
        client.app.dependency_overrides.clear()
        del client.app.state.conversation_registry

    assert response.status_code == 200
    assert response.json()["items"][0]["runtime_info"] == {
        "runtime_status": "missing",
        "can_resume": False,
        "runtime_error": None,
    }


def test_search_conversations_with_all_params(
    client, mock_conversation_service, sample_conversation_info
):
    """使用所有参数测试 search_conversations 端点。"""

    # 模拟对象服务响应
    mock_page = ConversationPage(
        items=[sample_conversation_info], next_page_id="next_page"
    )
    mock_conversation_service.search_conversations.return_value = mock_page

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get(
            "/api/conversations/search",
            params={
                "page_id": "test_page",
                "limit": 50,
                "status": ConversationExecutionStatus.IDLE.value,
                "sort_order": ConversationSortOrder.UPDATED_AT_DESC.value,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["next_page_id"] == "next_page"

        # 验证使用正确的参数调用服务
        mock_conversation_service.search_conversations.assert_called_once_with(
            "test_page",
            50,
            ConversationExecutionStatus.IDLE,
            ConversationSortOrder.UPDATED_AT_DESC,
        )
    finally:
        client.app.dependency_overrides.clear()


def test_search_conversations_limit_validation(client, mock_conversation_service):
    """使用无效限值测试 search_conversations 端点。"""

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 测试限制太低（gt=0 表示 > 0，因此 0 应该失败）
        response = client.get("/api/conversations/search", params={"limit": 0})
        assert response.status_code == 422

        # 测试限制太高 - 被 FastAPI 验证拒绝 (le=100)
        response = client.get("/api/conversations/search", params={"limit": 101})
        assert response.status_code == 422

        # 测试有效限度
        mock_conversation_service.search_conversations.return_value = ConversationPage(
            items=[], next_page_id=None
        )
        response = client.get("/api/conversations/search", params={"limit": 50})
        assert response.status_code == 200
    finally:
        client.app.dependency_overrides.clear()


def test_search_conversations_empty_result(client, mock_conversation_service):
    """测试 search_conversations 端点，结果为空。"""

    # 模拟对象 empty response
    mock_page = ConversationPage(items=[], next_page_id=None)
    mock_conversation_service.search_conversations.return_value = mock_page

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get("/api/conversations/search")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["next_page_id"] is None
    finally:
        client.app.dependency_overrides.clear()


def test_count_conversations_no_filter(client, mock_conversation_service):
    """测试 count_conversations 端点，无状态过滤器。"""

    # 模拟对象服务响应
    mock_conversation_service.count_conversations.return_value = 5

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get("/api/conversations/count")

        assert response.status_code == 200
        assert response.json() == 5

        # 验证在没有状态过滤器的情况下调用服务
        mock_conversation_service.count_conversations.assert_called_once_with(None)
    finally:
        client.app.dependency_overrides.clear()


def test_count_conversations_with_status_filter(client, mock_conversation_service):
    """使用状态过滤器测试 count_conversations 端点。"""

    # 模拟对象服务响应
    mock_conversation_service.count_conversations.return_value = 3

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get(
            "/api/conversations/count",
            params={"status": ConversationExecutionStatus.RUNNING.value},
        )

        assert response.status_code == 200
        assert response.json() == 3

        # 验证使用状态过滤器调用服务
        mock_conversation_service.count_conversations.assert_called_once_with(
            ConversationExecutionStatus.RUNNING
        )
    finally:
        client.app.dependency_overrides.clear()


def test_count_conversations_zero_result(client, mock_conversation_service):
    """测试 count_conversations 端点，结果为零。"""

    # 模拟对象零计数响应
    mock_conversation_service.count_conversations.return_value = 0

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get("/api/conversations/count")

        assert response.status_code == 200
        assert response.json() == 0
    finally:
        client.app.dependency_overrides.clear()


def test_get_conversation_success(
    client, mock_conversation_service, sample_conversation_info, sample_conversation_id
):
    """使用现有对话测试 get_conversation 端点。"""

    # 模拟对象服务响应
    mock_conversation_service.get_conversation.return_value = sample_conversation_info

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get(f"/api/conversations/{sample_conversation_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_conversation_info.id)
        assert data["title"] == sample_conversation_info.title

        # 验证使用正确的对话 ID 调用服务
        mock_conversation_service.get_conversation.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_get_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """使用不存在的对话测试 get_conversation 端点。"""

    # 模拟对象要返回的服务None（未找到会话）
    mock_conversation_service.get_conversation.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get(f"/api/conversations/{sample_conversation_id}")

        assert response.status_code == 404

        # 验证使用正确的对话 ID 调用服务
        mock_conversation_service.get_conversation.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_get_conversation_invalid_uuid(client, mock_conversation_service):
    """使用无效的 UUID 测试 get_conversation 端点。"""

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get("/api/conversations/invalid-uuid")

        assert response.status_code == 422  # 验证无效 UUID 错误
    finally:
        client.app.dependency_overrides.clear()


def test_batch_get_conversations_success(
    client, mock_conversation_service, sample_conversation_info
):
    """使用有效 ID 测试 batch_get_conversations 端点。"""

    # 创建额外的对话信息以进行测试
    conversation_id_1 = uuid4()
    conversation_id_2 = uuid4()

    # 模拟对象服务响应 - 返回一发现，一 None
    mock_conversation_service.batch_get_conversations.return_value = [
        sample_conversation_info,
        None,
    ]

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get(
            "/api/conversations",
            params={"ids": [str(conversation_id_1), str(conversation_id_2)]},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == str(sample_conversation_info.id)
        assert data[1] is None

        # 验证使用正确的 ID 调用服务
        mock_conversation_service.batch_get_conversations.assert_called_once_with(
            [conversation_id_1, conversation_id_2]
        )
    finally:
        client.app.dependency_overrides.clear()


def test_batch_get_conversations_empty_list(client, mock_conversation_service):
    """使用空 ID 列表测试 batch_get_conversations 端点。"""

    # 模拟对象 empty response
    mock_conversation_service.batch_get_conversations.return_value = []

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # FastAPI 需要至少一个需要列表的查询参数值因此我们将使用单个有效的 UUID 进行测试
        #
        test_id = str(uuid4())
        mock_conversation_service.batch_get_conversations.return_value = [None]

        response = client.get("/api/conversations", params={"ids": [test_id]})

        assert response.status_code == 200
        data = response.json()
        assert data == [None]

        # 验证服务被调用
        mock_conversation_service.batch_get_conversations.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_batch_get_conversations_too_many_ids(client, mock_conversation_service):
    """使用太多 ID 测试 batch_get_conversations 端点。"""

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 100 个 ID 超出 99 个 ID 限制：422 命名限制，而不是 500
        many_ids = [str(uuid4()) for _ in range(100)]
        response = client.get("/api/conversations", params={"ids": many_ids})
        assert response.status_code == 422
        assert "at most 99 items" in response.text
        mock_conversation_service.batch_get_conversations.assert_not_called()

        # 使用 99 个 ID 进行测试（应该有效）
        mock_conversation_service.batch_get_conversations.return_value = [None] * 99
        valid_ids = [str(uuid4()) for _ in range(99)]
        response = client.get("/api/conversations", params={"ids": valid_ids})
        assert response.status_code == 200
        assert response.json() == [None] * 99
    finally:
        client.app.dependency_overrides.clear()


def test_batch_get_conversations_openapi_declares_id_limit(client):
    """99-id 限制是已发布的模式的一部分，而不仅仅是强制执行的。"""
    operation = client.app.openapi()["paths"]["/api/conversations"]["get"]
    ids_param = next(p for p in operation["parameters"] if p["name"] == "ids")
    assert ids_param["schema"]["maxItems"] == 99


def test_batch_get_conversations_invalid_uuid(client, mock_conversation_service):
    """使用无效的 UUID 测试 batch_get_conversations 端点。"""

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.get("/api/conversations", params={"ids": ["invalid-uuid"]})

        assert response.status_code == 422  # 验证无效 UUID 错误
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_new(
    client, mock_conversation_service, sample_conversation_info
):
    """测试 start_conversation 端点创建新对话。"""

    # 模拟对象服务响应 - 创建新对话
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 使用正确的序列化创建请求数据
        request_data = {
            "agent": {
                "kind": "Agent",
                "llm": {
                    "model": "gpt-4o",
                    "api_key": "test-key",
                    "usage_id": "test-llm",
                },
                "tools": [{"name": "TerminalTool"}],
            },
            "workspace": {"working_dir": "/tmp/test"},
            "initial_message": {
                "role": "user",
                "content": [{"type": "text", "text": "Hello, world!"}],
            },
        }

        response = client.post("/api/conversations", json=request_data)

        assert response.status_code == 201  # 已创建
        data = response.json()
        assert data["id"] == str(sample_conversation_info.id)
        assert data["title"] == sample_conversation_info.title

        # 验证服务被调用
        mock_conversation_service.start_conversation.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_merges_observability_headers(
    client, mock_conversation_service, sample_conversation_info
):
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        request_data = {
            "agent": {
                "kind": "Agent",
                "llm": {"model": "gpt-4o", "api_key": "test-key"},
                "tools": [{"name": "TerminalTool"}],
            },
            "workspace": {"working_dir": "/tmp/test"},
            "observability_metadata": {"caller": "body"},
        }

        response = client.post(
            "/api/conversations",
            json=request_data,
            headers={
                "X-OpenHands-Observability-Metadata": (
                    '{"automation.id":"a1","caller":"header"}'
                ),
                "X-OpenHands-Observability-Span-Name": "automation.conversation",
                "X-OpenHands-Observability-Tags": "automation,webhook",
                "X-OpenHands-Observability-Parent-Span-Context": "parent-context",
            },
        )

        assert response.status_code == 201
        request = mock_conversation_service.start_conversation.call_args.args[0]
        assert request.observability_metadata == {
            "automation.id": "a1",
            "caller": "body",
        }
        assert request.observability_span_name == "automation.conversation"
        assert request.observability_tags == ["automation", "webhook"]
        assert request.observability_parent_span_context == "parent-context"
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_body_observability_overrides_headers(
    client, mock_conversation_service, sample_conversation_info
):
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        request_data = {
            "agent": {
                "kind": "Agent",
                "llm": {"model": "gpt-4o", "api_key": "test-key"},
                "tools": [{"name": "TerminalTool"}],
            },
            "workspace": {"working_dir": "/tmp/test"},
            "observability_span_name": "body.span",
            "observability_tags": ["body_tag"],
        }

        response = client.post(
            "/api/conversations",
            json=request_data,
            headers={
                "X-OpenHands-Observability-Span-Name": "header.span",
                "X-OpenHands-Observability-Tags": "header_tag",
            },
        )

        assert response.status_code == 201
        request = mock_conversation_service.start_conversation.call_args.args[0]
        assert request.observability_span_name == "body.span"
        assert request.observability_tags == ["body_tag"]
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_existing(
    client, mock_conversation_service, sample_conversation_info
):
    """使用现有对话测试 start_conversation 端点。"""

    # 模拟对象服务响应 - 返回现有对话
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        False,
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 使用正确的序列化创建请求数据
        request_data = {
            "agent": {
                "kind": "Agent",
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

        assert response.status_code == 200  # 好的（现有）
        data = response.json()
        assert data["id"] == str(sample_conversation_info.id)

        # 验证服务被调用
        mock_conversation_service.start_conversation.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def _launched_agent(request: StartConversationRequest) -> AgentBase:
    def no_stores() -> LaunchStores:
        raise AssertionError("an agent_settings launch reads no store")

    return finalize(
        launch_source(request, no_stores, None), LaunchRuntime(browser_available=True)
    ).agent


def test_start_conversation_accepts_openhands_agent_settings(
    client, mock_conversation_service
):
    now = utc_now()
    info = ConversationInfo(
        id=uuid4(),
        agent=Agent(llm=LLM(model="settings-model", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
        execution_status=ConversationExecutionStatus.IDLE,
        title="Settings Conversation",
        created_at=now,
        updated_at=now,
    )
    mock_conversation_service.start_conversation.return_value = (info, True)
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            "/api/conversations",
            json={
                "agent_settings": {
                    "schema_version": 1,
                    "agent_kind": "llm",
                    "llm": {"model": "settings-model", "usage_id": "test-llm"},
                    "tools": [],
                    "verification": {
                        "confirmation_mode": True,
                        "security_analyzer": "llm",
                    },
                },
                "workspace": {"working_dir": "/tmp/test"},
            },
        )

        assert response.status_code == 201
        request = mock_conversation_service.start_conversation.call_args.args[0]
        assert request.agent is None
        assert (
            request.model_dump(mode="json")["agent_settings"] == request.agent_settings
        )
        agent = _launched_agent(request)
        assert agent.kind == "Agent"
        assert agent.llm.model == "settings-model"
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_agent_settings_uses_sdk_default_tools(
    client, mock_conversation_service, monkeypatch, tmp_path
):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    monkeypatch.setattr(llm_profile_store, "_DEFAULT_PROFILE_DIR", profile_dir)
    LLMProfileStore(base_dir=profile_dir).save(
        "fast", LLM(model="fast-model", usage_id="fast")
    )

    now = utc_now()
    info = ConversationInfo(
        id=uuid4(),
        agent=Agent(llm=LLM(model="settings-model", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
        execution_status=ConversationExecutionStatus.IDLE,
        title="Settings Conversation",
        created_at=now,
        updated_at=now,
    )
    mock_conversation_service.start_conversation.return_value = (info, True)
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            "/api/conversations",
            json={
                "agent_settings": {
                    "schema_version": 1,
                    "agent_kind": "llm",
                    "llm": {"model": "settings-model", "usage_id": "test-llm"},
                    "enable_switch_llm_tool": True,
                    "tools": [
                        {"name": "terminal", "params": {}},
                        {"name": "file_editor", "params": {}},
                        {"name": "task_tracker", "params": {}},
                        {"name": "browser_tool_set", "params": {}},
                    ],
                },
                "workspace": {"working_dir": "/tmp/test"},
            },
        )

        assert response.status_code == 201
        request = mock_conversation_service.start_conversation.call_args.args[0]
        agent = _launched_agent(request)
        assert "SwitchLLMTool" in agent.include_default_tools
        assert {tool.name for tool in agent.tools} == {
            "terminal",
            "file_editor",
            "task_tracker",
            "browser_tool_set",
        }
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_accepts_acp_agent(client, mock_conversation_service):
    now = utc_now()
    acp_info = ConversationInfo(
        id=uuid4(),
        agent=ACPAgent(acp_command=["echo", "test"]),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
        execution_status=ConversationExecutionStatus.IDLE,
        title="ACP Conversation",
        created_at=now,
        updated_at=now,
    )
    mock_conversation_service.start_conversation.return_value = (acp_info, True)
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            "/api/conversations",
            json={
                "agent": {
                    "kind": "ACPAgent",
                    "acp_command": ["echo", "test"],
                },
                "workspace": {"working_dir": "/tmp/test"},
            },
        )

        assert response.status_code == 201
        assert response.json()["agent"]["kind"] == "ACPAgent"
        mock_conversation_service.start_conversation.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_accepts_acp_agent_settings(
    client, mock_conversation_service
):
    now = utc_now()
    acp_info = ConversationInfo(
        id=uuid4(),
        agent=ACPAgent(acp_command=["echo", "settings"]),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
        execution_status=ConversationExecutionStatus.IDLE,
        title="ACP Conversation",
        created_at=now,
        updated_at=now,
    )
    mock_conversation_service.start_conversation.return_value = (acp_info, True)
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            "/api/conversations",
            json={
                "agent_settings": {
                    "schema_version": AGENT_SETTINGS_SCHEMA_VERSION,
                    "agent_kind": "acp",
                    "acp_server": "custom",
                    "acp_command": ["echo", "settings"],
                    "acp_args": ["--verbose"],
                    "acp_model": "acp-test-model",
                    "acp_session_mode": "bypassPermissions",
                    "acp_prompt_timeout": 123.0,
                },
                "workspace": {"working_dir": "/tmp/test"},
            },
        )

        assert response.status_code == 201
        request = mock_conversation_service.start_conversation.call_args.args[0]
        agent = _launched_agent(request)
        assert isinstance(agent, ACPAgent)
        assert agent.acp_command == ["echo", "settings"]
        assert agent.acp_args == ["--verbose"]
        assert agent.acp_model == "acp-test-model"
        assert agent.acp_session_mode == "bypassPermissions"
        assert agent.acp_prompt_timeout == 123.0

    finally:
        client.app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "agent_settings",
    [
        {"agent_kind": "invalid"},
        "not-a-settings-object",
    ],
)
def test_start_conversation_rejects_invalid_agent_settings(
    client, mock_conversation_service, agent_settings
):
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            "/api/conversations",
            json={
                "agent_settings": agent_settings,
                "workspace": {"working_dir": "/tmp/test"},
            },
        )

        assert response.status_code == 422
        mock_conversation_service.start_conversation.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_agent_takes_precedence_over_agent_settings(
    client, mock_conversation_service
):
    now = utc_now()
    info = ConversationInfo(
        id=uuid4(),
        agent=Agent(llm=LLM(model="gpt-4o", usage_id="test-llm"), tools=[]),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
        execution_status=ConversationExecutionStatus.IDLE,
        created_at=now,
        updated_at=now,
    )
    mock_conversation_service.start_conversation.return_value = (info, True)
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            "/api/conversations",
            json={
                "agent": {
                    "llm": {"model": "gpt-4o", "usage_id": "test-llm"},
                    "tools": [],
                },
                "agent_settings": {"agent_kind": "invalid"},
                "workspace": {"working_dir": "/tmp/test"},
            },
        )

        assert response.status_code == 201
        request = mock_conversation_service.start_conversation.call_args.args[0]
        assert request.agent.kind == "Agent"
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_rejects_acp_agent_without_kind(
    client, mock_conversation_service
):
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            "/api/conversations",
            json={
                "agent": {"acp_command": ["echo", "test"]},
                "workspace": {"working_dir": "/tmp/test"},
            },
        )

        assert response.status_code == 422
        mock_conversation_service.start_conversation.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_invalid_request(client, mock_conversation_service):
    """使用无效请求数据测试 start_conversation 端点。"""

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 测试缺少必填字段
        invalid_request = {"invalid": "data"}

        response = client.post("/api/conversations", json=invalid_request)

        assert response.status_code == 422  # 验证错误
    finally:
        client.app.dependency_overrides.clear()


@pytest.mark.parametrize("value", ["plain-value", 5, None, True])
def test_start_conversation_non_object_secret_is_422(
    client, mock_conversation_service, value
):
    """不是对象的机密值是 422，而不是 500。"""

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request = {
            "agent": {
                "kind": "Agent",
                "llm": {"model": "gpt-4o", "api_key": "k", "usage_id": "test-llm"},
                "tools": [],
            },
            "workspace": {"working_dir": "/tmp/test"},
            "secrets": {"PLAIN": value},
        }

        response = client.post("/api/conversations", json=request)

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "secrets", "PLAIN"]
        mock_conversation_service.start_conversation.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()


@pytest.mark.parametrize("value", [5, None, True])
def test_update_secrets_non_string_value_is_422(
    client, mock_conversation_service, mock_event_service, sample_conversation_id, value
):
    """数字、null 或布尔值机密是 422，而不是 500。"""

    mock_conversation_service.get_event_service.return_value = mock_event_service
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/secrets",
            json={"secrets": {"BAD": value}},
        )

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "secrets", "BAD"]
        mock_event_service.update_secrets.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_minimal_request(
    client, mock_conversation_service, sample_conversation_info
):
    """使用最少的有效请求测试 start_conversation 端点。"""

    # 模拟对象服务响应
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 创建最小有效请求
        minimal_request = {
            "agent": {
                "kind": "Agent",
                "llm": {
                    "model": "gpt-4o",
                    "api_key": "test-key",
                    "usage_id": "test-llm",
                },
                "tools": [{"name": "TerminalTool"}],
            },
            "workspace": {"working_dir": "/tmp/test"},
        }

        response = client.post("/api/conversations", json=minimal_request)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(sample_conversation_info.id)
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_legacy_request_without_agent_kind(
    client, mock_conversation_service, sample_conversation_info
):
    """v1 对话创建应保留 ACP 智能体之前的形状。"""

    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
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
        mock_conversation_service.start_conversation.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_pause_conversation_success(
    client, mock_conversation_service, sample_conversation_id
):
    """测试 pause_conversation 端点并成功暂停。"""

    # 模拟对象服务响应 - 暂停成功
    mock_conversation_service.pause_conversation.return_value = True

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 验证使用正确的对话 ID 调用服务
        mock_conversation_service.pause_conversation.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_pause_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """未知会话是路由声明的 404，而不是 400。"""

    mock_conversation_service.pause_conversation.return_value = False

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/pause")

        assert response.status_code == 404

        # 验证服务被调用
        mock_conversation_service.pause_conversation.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_interrupt_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """未知会话是路由声明的 404，而不是 400。"""

    mock_conversation_service.interrupt_conversation.return_value = False

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/interrupt")

        assert response.status_code == 404
        mock_conversation_service.interrupt_conversation.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_delete_conversation_success(
    client, mock_conversation_service, sample_conversation_id
):
    """测试delete_conversation端点删除成功。"""

    # 模拟对象服务响应-删除成功
    mock_conversation_service.delete_conversation.return_value = True

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.delete(f"/api/conversations/{sample_conversation_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 验证使用正确的对话 ID 调用服务
        mock_conversation_service.delete_conversation.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_delete_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """未知或已删除的对话是 404，而不是 400。"""

    mock_conversation_service.delete_conversation.return_value = False

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.delete(f"/api/conversations/{sample_conversation_id}")

        assert response.status_code == 404

        # 验证服务被调用
        mock_conversation_service.delete_conversation.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_run_conversation_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """测试 run_conversation 端点并成功运行。"""

    # 模拟对象服务响应
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.run.return_value = None  # 运行成功

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/run")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 验证服务被调用
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
        mock_event_service.run.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_run_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当未找到对话时测试 run_conversation 端点。"""

    # 模拟对象服务响应 - 未找到对话
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/run")

        assert response.status_code == 404

        # 验证服务被调用
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_start_goal_in_conversation_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/goal 端点将目标转发到事件服务。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.start_goal_loop.return_value = None

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/goal",
            json={"objective": "build x"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_event_service.start_goal_loop.assert_awaited_once_with(
            "build x", max_iterations=10
        )
    finally:
        client.app.dependency_overrides.clear()


def test_start_goal_in_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当对话未知时，/goal 返回 404。"""
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/goal",
            json={"objective": "build x"},
        )
        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_start_goal_in_conversation_rejects_busy_loop(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """当目标循环或对话运行处于活动状态时，/goal 返回 409。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.start_goal_loop.side_effect = ValueError("goal_already_running")

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/goal",
            json={"objective": "build x"},
        )
        assert response.status_code == 409
    finally:
        client.app.dependency_overrides.clear()


def test_stop_goal_in_conversation_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/goal/stop 端点转发到事件服务。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.stop_goal_loop.return_value = True

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )
    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/goal/stop")
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_event_service.stop_goal_loop.assert_awaited_once()
    finally:
        client.app.dependency_overrides.clear()


def test_stop_goal_in_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当对话未知时，/goal/stop 返回 404。"""
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )
    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/goal/stop")
        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_resume_goal_in_conversation_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/goal/resume 端点转发到事件服务。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.resume_goal_loop.return_value = None

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/goal/resume"
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_event_service.resume_goal_loop.assert_awaited_once()
    finally:
        client.app.dependency_overrides.clear()


def test_resume_goal_in_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当对话未知时，/goal/resume 返回 404。"""
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/goal/resume"
        )
        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_resume_goal_in_conversation_no_resumable(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """当没有任何内容可恢复时，/goal/resume 返回 400。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.resume_goal_loop.side_effect = ValueError("no_resumable_goal")

    client.app.dependency_overrides[get_conversation_service] = (
        lambda: mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/goal/resume"
        )
        assert response.status_code == 400
    finally:
        client.app.dependency_overrides.clear()


def test_switch_acp_model_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """switch_acp_model 端点将模型转发到事件服务。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.switch_acp_model.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_acp_model",
            json={"model": "haiku"},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_event_service.switch_acp_model.assert_awaited_once_with("haiku")
    finally:
        client.app.dependency_overrides.clear()


def test_switch_acp_model_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当对话未知时，switch_acp_model 返回 404。"""
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_acp_model",
            json={"model": "haiku"},
        )
        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_switch_acp_model_non_acp_returns_400(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """A ValueError (e.g. 非 ACP 智能体 / 不受支持的提供商）映射到 400。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.switch_acp_model.side_effect = ValueError(
        "switch_acp_model is only supported for ACP conversations."
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_acp_model",
            json={"model": "haiku"},
        )
        assert response.status_code == 400
    finally:
        client.app.dependency_overrides.clear()


def test_switch_acp_model_pre_session_returns_200(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """第一个 run() 之前的开关是 200，而不是 409。

    回归对于 #3763：现在 SDK 会持久化（推迟）预会话切换，而不是抛出，因此路由不再将其
    映射到 409 "ACP 会话尚未初始化"。 事件服务正常返回（在第一个
    会话开始时应用延迟）。
    """
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.switch_acp_model.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_acp_model",
            json={"model": "haiku"},
        )
        assert response.status_code == 200
        mock_event_service.switch_acp_model.assert_awaited_once_with("haiku")
    finally:
        client.app.dependency_overrides.clear()


def test_switch_acp_model_inactive_service_returns_400(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """不活动的服务（关闭/从未启动）映射到 400。

    事件服务针对丢失的实时对话提出共享 ``inactive_service`` ValueError，与其其他方法
    一致； 路由器的通用 ValueError 处理程序
    将其转换为 400。
    """
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.switch_acp_model.side_effect = ValueError("inactive_service")

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_acp_model",
            json={"model": "haiku"},
        )
        assert response.status_code == 400
    finally:
        client.app.dependency_overrides.clear()


def test_switch_acp_model_protocol_error_returns_400(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """被拒绝的 ACP 模型选择调用映射到 400，而不是 500。

    ``ACPAgent.set_acp_model`` 翻译 ``acp.exceptions.RequestError`` (e.g. 将自定义服
    务器上的方法未找到
    错误，或无效的模型ID转换为ValueError，因此协议级拒绝以400客户端错误而不是500无意
    义错误表面。
    """
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.switch_acp_model.side_effect = ValueError(
        "ACP server rejected model switch to 'bogus': method not found"
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_acp_model",
            json={"model": "bogus"},
        )
        assert response.status_code == 400
    finally:
        client.app.dependency_overrides.clear()


def test_switch_acp_model_timeout_returns_504(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """TimeoutError（楔入/慢速 ACP 服务器）映射到 504，而不是 500。

    ``ACPAgent.set_acp_model`` 将提供者模型选择往返与 ``acp_prompt_timeout`` 绑定；
    过期的呼叫引发
    ``TimeoutError``，路由将其显示为网关超时，而不是不透明的 500。
    """
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.switch_acp_model.side_effect = TimeoutError(
        "ACP server did not answer model switch within 600s"
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_acp_model",
            json={"model": "haiku"},
        )
        assert response.status_code == 504
    finally:
        client.app.dependency_overrides.clear()


def test_run_conversation_already_running(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """当对话已在运行时测试 run_conversation 端点。"""

    # 模拟对象服务响应
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.run.side_effect = ValueError("conversation_already_running")

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/run")

        assert response.status_code == 409  # 冲突
        data = response.json()
        assert "already running" in data["detail"]

        # 验证服务被调用
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
        mock_event_service.run.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_run_conversation_other_error(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """与其他 ValueError 一起测试 run_conversation 端点。"""

    # 模拟对象服务响应
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.run.side_effect = ValueError("some other error")

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/run")

        assert response.status_code == 400  # 错误的请求
        data = response.json()
        assert data["detail"] == "some other error"
    finally:
        client.app.dependency_overrides.clear()


def test_update_conversation_secrets_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """测试 update_conversation_secrets 端点更新成功。"""

    # 模拟对象服务响应
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.update_secrets.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 使用正确的机密源格式
        request_data = {
            "secrets": {
                "API_KEY": {"kind": "StaticSecret", "value": "secret-value"},
                "TOKEN": {"kind": "StaticSecret", "value": "token-value"},
            }
        }

        response = client.post(
            f"/api/conversations/{sample_conversation_id}/secrets", json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 验证服务被调用
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
        mock_event_service.update_secrets.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_update_conversation_secrets_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当未找到对话时测试 update_conversation_secrets 端点。"""

    # 模拟对象服务响应 - 未找到对话
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {
            "secrets": {"API_KEY": {"kind": "StaticSecret", "value": "secret-value"}}
        }

        response = client.post(
            f"/api/conversations/{sample_conversation_id}/secrets", json=request_data
        )

        assert response.status_code == 404

        # 验证服务被调用
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_set_conversation_confirmation_policy_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """测试 set_conversation_confirmation_policy 端点更新成功。"""

    # 模拟对象服务响应
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.set_confirmation_policy.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {"policy": {"kind": "NeverConfirm"}}

        response = client.post(
            f"/api/conversations/{sample_conversation_id}/confirmation_policy",
            json=request_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 验证服务被调用
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
        mock_event_service.set_confirmation_policy.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_set_conversation_confirmation_policy_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当未找到对话时测试 set_conversation_confirmation_policy 端点。"""  # noqa: E501

    # 模拟对象服务响应 - 未找到对话
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {"policy": {"kind": "NeverConfirm"}}

        response = client.post(
            f"/api/conversations/{sample_conversation_id}/confirmation_policy",
            json=request_data,
        )

        assert response.status_code == 404

        # 验证服务被调用
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_update_conversation_success(
    client, mock_conversation_service, sample_conversation_id
):
    """测试 update_conversation 端点更新成功。"""

    # 模拟对象服务响应 - 更新成功
    mock_conversation_service.update_conversation.return_value = True

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {"title": "Updated Conversation Title"}

        response = client.patch(
            f"/api/conversations/{sample_conversation_id}", json=request_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 验证使用正确的参数调用服务
        mock_conversation_service.update_conversation.assert_called_once()
        call_args = mock_conversation_service.update_conversation.call_args
        assert call_args[0][0] == sample_conversation_id
        assert call_args[0][1].title == "Updated Conversation Title"
    finally:
        client.app.dependency_overrides.clear()


def test_update_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """未知对话是 404，而不是成功=False 的 200。"""

    mock_conversation_service.update_conversation.return_value = False

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {"title": "Updated Title"}

        response = client.patch(
            f"/api/conversations/{sample_conversation_id}", json=request_data
        )

        assert response.status_code == 404

        # 验证服务被调用
        mock_conversation_service.update_conversation.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_update_conversation_invalid_title(
    client, mock_conversation_service, sample_conversation_id
):
    """使用无效标题测试 update_conversation 端点。"""

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 使用空标题进行测试
        request_data = {"title": ""}
        response = client.patch(
            f"/api/conversations/{sample_conversation_id}", json=request_data
        )
        assert response.status_code == 422  # 验证错误

        # 测试标题太长
        long_title = "x" * 201  # 超过max_length=200
        request_data = {"title": long_title}
        response = client.patch(
            f"/api/conversations/{sample_conversation_id}", json=request_data
        )
        assert response.status_code == 422  # 验证错误
    finally:
        client.app.dependency_overrides.clear()


@pytest.mark.parametrize("title", ["   ", "\t\n"])
def test_update_conversation_whitespace_only_title_rejected(
    client, mock_conversation_service, sample_conversation_id, title
):
    """仅包含空格的标题会像空标题 (422) 一样被拒绝，并且
    服务永远不会被调用，因此存储的标题被保留。"""

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.patch(
            f"/api/conversations/{sample_conversation_id}", json={"title": title}
        )
        assert response.status_code == 422
        mock_conversation_service.update_conversation.assert_not_called()
    finally:
        client.app.dependency_overrides.clear()


def test_generate_title_endpoint_removed_from_openapi(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200

    openapi_schema = response.json()
    assert (
        "/api/conversations/{conversation_id}/generate_title"
        not in openapi_schema["paths"]
    )


def test_start_conversation_with_tool_module_qualnames(
    client, mock_conversation_service, sample_conversation_info
):
    """使用 tool_module_qualnames 字段测试 start_conversation 端点。"""

    # 模拟对象服务响应
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {
            "agent": {
                "kind": "Agent",
                "llm": {
                    "model": "gpt-4o",
                    "api_key": "test-key",
                    "usage_id": "test-llm",
                },
                "tools": [
                    {"name": "glob"},
                    {"name": "grep"},
                    {"name": "planning_file_editor"},
                ],
            },
            "workspace": {"working_dir": "/tmp/test"},
            "tool_module_qualnames": {
                "glob": "openhands.tools.glob.definition",
                "grep": "openhands.tools.grep.definition",
                "planning_file_editor": (
                    "openhands.tools.planning_file_editor.definition"
                ),
            },
        }

        response = client.post("/api/conversations", json=request_data)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(sample_conversation_info.id)

        # 验证服务被调用
        mock_conversation_service.start_conversation.assert_called_once()
        call_args = mock_conversation_service.start_conversation.call_args
        request_arg = call_args[0][0]
        assert hasattr(request_arg, "tool_module_qualnames")
        assert request_arg.tool_module_qualnames == {
            "glob": "openhands.tools.glob.definition",
            "grep": "openhands.tools.grep.definition",
            "planning_file_editor": ("openhands.tools.planning_file_editor.definition"),
        }
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_without_tool_module_qualnames(
    client, mock_conversation_service, sample_conversation_info
):
    """在没有 tool_module_qualnames 字段的情况下测试 start_conversation 端点。"""

    # 模拟对象服务响应
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {
            "agent": {
                "kind": "Agent",
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
        data = response.json()
        assert data["id"] == str(sample_conversation_info.id)

        # 验证服务被调用
        mock_conversation_service.start_conversation.assert_called_once()
        call_args = mock_conversation_service.start_conversation.call_args
        request_arg = call_args[0][0]
        assert hasattr(request_arg, "tool_module_qualnames")
        # 应该默认为空字典
        assert request_arg.tool_module_qualnames == {}
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_autotitle_defaults_to_true(
    client, mock_conversation_service, sample_conversation_info
):
    """当请求中未提供时，autotitle 默认为 True。"""
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {
            "agent": {
                "kind": "Agent",
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
        assert request_arg.autotitle is True
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_autotitle_false(
    client, mock_conversation_service, sample_conversation_info
):
    """autotitle=False is forwarded correctly to the service."""
    mock_conversation_service.start_conversation.return_value = (
        sample_conversation_info,
        True,
    )
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        request_data = {
            "agent": {
                "kind": "Agent",
                "llm": {
                    "model": "gpt-4o",
                    "api_key": "test-key",
                    "usage_id": "test-llm",
                },
                "tools": [{"name": "TerminalTool"}],
            },
            "workspace": {"working_dir": "/tmp/test"},
            "autotitle": False,
        }
        response = client.post("/api/conversations", json=request_data)

        assert response.status_code == 201
        call_args = mock_conversation_service.start_conversation.call_args
        request_arg = call_args[0][0]
        assert request_arg.autotitle is False
    finally:
        client.app.dependency_overrides.clear()


def test_set_conversation_security_analyzer_success(
    client,
    sample_conversation_id,
    mock_conversation_service,
    mock_event_service,
    llm_security_analyzer,
):
    """通过 API 端点测试安全分析器设置是否成功。"""
    # 设置模拟对象
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.set_security_analyzer.return_value = None

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    # 提出请求
    response = client.post(
        f"/api/conversations/{sample_conversation_id}/security_analyzer",
        json={"security_analyzer": llm_security_analyzer.model_dump()},
    )

    # 验证响应
    assert response.status_code == 200
    assert response.json() == {"success": True}

    # 验证服务调用
    mock_conversation_service.get_event_service.assert_called_once_with(
        sample_conversation_id
    )
    mock_event_service.set_security_analyzer.assert_called_once()


def test_set_conversation_security_analyzer_with_none(
    client, sample_conversation_id, mock_conversation_service, mock_event_service
):
    """通过 API 端点测试将安全分析器设置为 None。"""
    # 设置模拟对象
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.set_security_analyzer.return_value = None

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    # 使用 None 分析器发出请求
    response = client.post(
        f"/api/conversations/{sample_conversation_id}/security_analyzer",
        json={"security_analyzer": None},
    )

    # 验证响应
    assert response.status_code == 200
    assert response.json() == {"success": True}

    # 验证服务调用
    mock_conversation_service.get_event_service.assert_called_once_with(
        sample_conversation_id
    )
    mock_event_service.set_security_analyzer.assert_called_once_with(None)


def test_security_analyzer_endpoint_with_malformed_analyzer_data(
    client, sample_conversation_id, mock_conversation_service, mock_event_service
):
    """使用格式错误的安全分析器数据测试端点行为。"""
    # 设置模拟对象
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.set_security_analyzer.return_value = None

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    # 使用无效的分析仪类型进行测试（应被拒绝）
    response = client.post(
        f"/api/conversations/{sample_conversation_id}/security_analyzer",
        json={"security_analyzer": {"kind": "InvalidAnalyzerType"}},
    )

    # 对于未知的分析器类型应返回验证错误
    assert response.status_code == 422
    response_data = response.json()
    assert "detail" in response_data


def test_update_secrets_with_string_values(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """测试 update_secrets 端点接受纯字符串值。"""

    # 模拟对象服务
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.update_secrets.return_value = None

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 使用纯字符串机密进行测试（应该自动转换）
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/secrets",
            json={
                "secrets": {
                    "API_KEY": "plain-secret-value",
                    "TOKEN": "another-secret",
                }
            },
        )

        assert response.status_code == 200
        assert response.json() == {"success": True}

        # 验证事件服务被调用（机密应在内部转换）
        mock_event_service.update_secrets.assert_called_once()
        call_args = mock_event_service.update_secrets.call_args

        # 验证机密已转换为正确的 SecretSource 对象
        secrets_dict = call_args[0][0]  # 机密参数
        assert "API_KEY" in secrets_dict
        assert "TOKEN" in secrets_dict

    finally:
        client.app.dependency_overrides.clear()


def test_update_secrets_with_mixed_formats(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """测试 update_secrets 端点接受混合机密格式。"""

    # 模拟对象服务
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.update_secrets.return_value = None

    # 覆盖依赖关系
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        # 使用混合格式进行测试：纯字符串和正确的 SecretSource 对象
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/secrets",
            json={
                "secrets": {
                    "PLAIN_SECRET": "plain-value",
                    "STATIC_SECRET": {
                        "kind": "StaticSecret",
                        "value": "static-value",
                    },
                    "LOOKUP_SECRET": {
                        "kind": "LookupSecret",
                        "url": "https://example.com/secret",
                    },
                }
            },
        )

        assert response.status_code == 200
        assert response.json() == {"success": True}

        # 验证事件服务被调用
        mock_event_service.update_secrets.assert_called_once()
        call_args = mock_event_service.update_secrets.call_args

        # 验证所有机密都存在
        secrets_dict = call_args[0][0]  # 机密参数
        assert "PLAIN_SECRET" in secrets_dict
        assert "STATIC_SECRET" in secrets_dict
        assert "LOOKUP_SECRET" in secrets_dict

    finally:
        client.app.dependency_overrides.clear()


# --- switch_profile 端点测试 ---


def test_switch_conversation_profile_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """使用有效的配置文件测试 switch_conversation_profile 端点。"""
    mock_conversation = MagicMock()
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_conversation.return_value = mock_conversation

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_profile",
            json={"profile_name": "gpt"},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
        mock_event_service.get_conversation.assert_called_once()
        mock_conversation.switch_profile.assert_called_once_with("gpt")
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_profile_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当未找到对话时测试 switch_conversation_profile 端点。"""
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_profile",
            json={"profile_name": "gpt"},
        )

        assert response.status_code == 404
        mock_conversation_service.get_event_service.assert_called_once_with(
            sample_conversation_id
        )
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_profile_nonexistent_profile(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """当磁盘上不存在配置文件时测试 switch_conversation_profile。"""
    mock_conversation = MagicMock()
    mock_conversation.switch_profile.side_effect = FileNotFoundError(
        "Profile 'missing' not found"
    )
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_conversation.return_value = mock_conversation

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_profile",
            json={"profile_name": "missing"},
        )

        assert response.status_code == 404
        assert "missing" in response.json()["detail"]
        mock_conversation.switch_profile.assert_called_once_with("missing")
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_profile_corrupted_profile(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """当配置文件损坏或无效时测试 switch_conversation_profile。"""
    mock_conversation = MagicMock()
    mock_conversation.switch_profile.side_effect = ValueError("Invalid profile format")
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_conversation.return_value = mock_conversation

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_profile",
            json={"profile_name": "corrupted"},
        )

        assert response.status_code == 400
        assert "Invalid profile format" in response.json()["detail"]
        mock_conversation.switch_profile.assert_called_once_with("corrupted")
    finally:
        client.app.dependency_overrides.clear()


def test_load_conversation_plugin_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/load_plugin 端点将插件引用转发到 EventService。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/load_plugin",
            json={"plugin_ref": "review-bot@team"},
        )

        assert response.status_code == 200
        mock_event_service.load_plugin.assert_awaited_once_with("review-bot@team")
    finally:
        client.app.dependency_overrides.clear()


def test_load_conversation_plugin_not_found(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/load_plugin 端点将插件解析错误映射到 404。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.load_plugin.side_effect = PluginNotFoundError("missing")
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/load_plugin",
            json={"plugin_ref": "missing"},
        )

        assert response.status_code == 404
        assert "missing" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


def test_load_conversation_plugin_malformed_ref_returns_400(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/load_plugin 端点将格式错误的插件引用映射到 400。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.load_plugin.side_effect = PluginResolutionError(
        "Plugin reference must use 'plugin-name@marketplace-name'"
    )
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/load_plugin",
            json={"plugin_ref": "review-bot@"},
        )

        assert response.status_code == 400
        assert "Plugin reference must use" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


def test_load_conversation_plugin_fetch_error_returns_400(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/load_plugin 端点将插件获取失败映射到 400。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.load_plugin.side_effect = PluginFetchError("fetch failed")
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/load_plugin",
            json={"plugin_ref": "review-bot@team"},
        )

        assert response.status_code == 400
        assert "fetch failed" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


def test_load_conversation_plugin_file_not_found_returns_400(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/load_plugin 端点将插件加载失败映射到 400。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.load_plugin.side_effect = FileNotFoundError("missing plugin dir")
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/load_plugin",
            json={"plugin_ref": "review-bot@team"},
        )

        assert response.status_code == 400
        assert "missing plugin dir" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


def test_load_conversation_plugin_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当会话丢失时，/load_plugin 端点返回 404。"""
    mock_conversation_service.get_event_service.return_value = None
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/load_plugin",
            json={"plugin_ref": "review-bot@team"},
        )

        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_load_conversation_plugin_inactive_service_returns_400(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/load_plugin 端点将非活动运行时状态映射到 400。"""
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.load_plugin.side_effect = ValueError("inactive_service")
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/load_plugin",
            json={"plugin_ref": "review-bot@team"},
        )

        assert response.status_code == 400
        assert "inactive_service" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_llm_success(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """/switch_llm 端点将内联 LLM 转发到 switch_llm，
    绕过配置文件存储（#3017）。
    """
    mock_conversation = MagicMock()
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_conversation.return_value = mock_conversation

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    llm_payload = {
        "model": "openai/gpt-4o",
        "api_key": "sk-test",
        "usage_id": "caller-supplied-id",
    }

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_llm",
            json={"llm": llm_payload},
        )

        assert response.status_code == 200
        mock_conversation.switch_llm.assert_called_once()
        forwarded_llm = mock_conversation.switch_llm.call_args.args[0]
        assert isinstance(forwarded_llm, LLM)
        assert forwarded_llm.model == "openai/gpt-4o"
        assert forwarded_llm.usage_id == "caller-supplied-id"
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_llm_decrypts_encrypted_api_key(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """当服务器有密码并且客户端发布加密的 api_key
    （自然的FE流：GET配置文件与X-Expose-机密：加密，然后转发到switch_llm），路由器在
    应用之前解密。 回归
    for #3164.
    """
    from base64 import urlsafe_b64encode

    from openhands.sdk.utils.cipher import Cipher

    secret_key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(secret_key)
    encrypted_api_key = cipher.encrypt(SecretStr("plaintext-api-key"))
    assert encrypted_api_key is not None

    # 为此测试在测试应用程序上安装启用密码的配置。
    client.app.state.config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(secret_key),
    )

    mock_conversation = MagicMock()
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_conversation.return_value = mock_conversation

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_llm",
            json={
                "llm": {
                    "model": "openai/gpt-4o",
                    "api_key": encrypted_api_key,
                    "usage_id": "caller-supplied-id",
                }
            },
        )

        assert response.status_code == 200
        forwarded_llm = mock_conversation.switch_llm.call_args.args[0]
        assert isinstance(forwarded_llm, LLM)
        assert isinstance(forwarded_llm.api_key, SecretStr)
        assert forwarded_llm.api_key.get_secret_value() == "plaintext-api-key"
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_llm_plaintext_with_cipher_passes_through(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """明文 api_key 必须不受影响地通过，即使服务器
    已配置密码（无 Fernet 前缀 → 未尝试解密）。 回归 #3164 的防护：向后兼容提供明文密
    钥的应用程序服务器。
    """
    from base64 import urlsafe_b64encode

    secret_key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    client.app.state.config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(secret_key),
    )

    mock_conversation = MagicMock()
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_conversation.return_value = mock_conversation

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_llm",
            json={
                "llm": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-plaintext",
                    "usage_id": "caller-supplied-id",
                }
            },
        )

        assert response.status_code == 200
        forwarded_llm = mock_conversation.switch_llm.call_args.args[0]
        assert isinstance(forwarded_llm.api_key, SecretStr)
        assert forwarded_llm.api_key.get_secret_value() == "sk-plaintext"
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_llm_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当会话丢失时，/switch_llm 端点返回 404。"""
    mock_conversation_service.get_event_service.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_llm",
            json={
                "llm": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-test",
                    "usage_id": "x",
                }
            },
        )

        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_llm_resolves_provider_connection(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """provider_connection_id 被解析为连接的 api_key /
    安装 LLM 之前的 base_url — OpenHands/OpenHands#17206 的回归（切换到链接的
    OpenRouter 配置文件丢失凭据）。
    """
    import tempfile
    from pathlib import Path

    from openhands.agent_server.persistence import store as store_module
    from openhands.sdk.llm.provider_connection_store import ProviderConnectionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        provider_store = ProviderConnectionStore(base_dir=base / "connections")
        provider_store.create(
            _provider_connection("or-conn", api_key="or-secret", base_url=None),
            cipher=None,
        )
        profile_store = LLMProfileStore(
            base_dir=base / "profiles", provider_store=provider_store
        )

        mock_conversation = MagicMock()
        mock_conversation_service.get_event_service.return_value = mock_event_service
        mock_event_service.get_conversation.return_value = mock_conversation
        client.app.dependency_overrides[get_conversation_service] = lambda: (
            mock_conversation_service
        )

        old_store = store_module._llm_profile_store
        store_module._llm_profile_store = profile_store
        try:
            response = client.post(
                f"/api/conversations/{sample_conversation_id}/switch_llm",
                json={
                    "llm": {
                        "model": "openrouter/z-ai/glm-5.3-flash",
                        "provider_connection_id": "or-conn",
                        "usage_id": "caller-supplied-id",
                    }
                },
            )

            assert response.status_code == 200
            mock_conversation.switch_llm.assert_called_once()
            forwarded = mock_conversation.switch_llm.call_args.args[0]
            assert isinstance(forwarded, LLM)
            assert forwarded.provider_connection_id == "or-conn"
            assert isinstance(forwarded.api_key, SecretStr)
            assert forwarded.api_key.get_secret_value() == "or-secret"
        finally:
            store_module._llm_profile_store = old_store
            client.app.dependency_overrides.clear()


def test_switch_conversation_llm_resolves_encrypted_provider_connection(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """Encrypted-at-REST 提供者凭据使用服务器的
    安装 LLM 之前的密码。"""
    import tempfile
    from base64 import urlsafe_b64encode
    from pathlib import Path

    from openhands.agent_server.persistence import store as store_module
    from openhands.sdk.llm.provider_connection_store import ProviderConnectionStore
    from openhands.sdk.utils.cipher import Cipher

    secret_key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    cipher = Cipher(secret_key)
    client.app.state.config = Config(
        static_files_path=None,
        session_api_keys=[],
        secret_key=SecretStr(secret_key),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        provider_store = ProviderConnectionStore(base_dir=base / "connections")
        provider_store.create(
            _provider_connection(
                "or-conn",
                api_key="plaintext-or-secret",
                base_url="https://openrouter.ai/api/v1",
            ),
            cipher=cipher,
        )
        profile_store = LLMProfileStore(
            base_dir=base / "profiles", provider_store=provider_store
        )

        mock_conversation = MagicMock()
        mock_conversation_service.get_event_service.return_value = mock_event_service
        mock_event_service.get_conversation.return_value = mock_conversation
        client.app.dependency_overrides[get_conversation_service] = lambda: (
            mock_conversation_service
        )

        old_store = store_module._llm_profile_store
        store_module._llm_profile_store = profile_store
        try:
            response = client.post(
                f"/api/conversations/{sample_conversation_id}/switch_llm",
                json={
                    "llm": {
                        "model": "openrouter/z-ai/glm-5.3-flash",
                        "provider_connection_id": "or-conn",
                        "usage_id": "caller-supplied-id",
                    }
                },
            )

            assert response.status_code == 200
            forwarded = mock_conversation.switch_llm.call_args.args[0]
            assert isinstance(forwarded.api_key, SecretStr)
            assert forwarded.api_key.get_secret_value() == "plaintext-or-secret"
            assert forwarded.base_url == "https://openrouter.ai/api/v1"
        finally:
            store_module._llm_profile_store = old_store
            client.app.dependency_overrides.clear()


def test_switch_conversation_llm_inline_key_without_provider_connection(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """不带 provider_connection_id 的内联 api_key 保持不变
    （字节相同的旧路径）。"""
    mock_conversation = MagicMock()
    mock_conversation_service.get_event_service.return_value = mock_event_service
    mock_event_service.get_conversation.return_value = mock_conversation
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/switch_llm",
            json={
                "llm": {
                    "model": "openai/gpt-4o",
                    "api_key": "sk-test",
                    "usage_id": "caller-supplied-id",
                }
            },
        )

        assert response.status_code == 200
        forwarded = mock_conversation.switch_llm.call_args.args[0]
        assert forwarded.api_key.get_secret_value() == "sk-test"
        assert forwarded.provider_connection_id is None
    finally:
        client.app.dependency_overrides.clear()


def test_switch_conversation_llm_missing_provider_connection_rejects_before_switch(
    client, mock_conversation_service, mock_event_service, sample_conversation_id
):
    """悬空的 provider_connection_id（并且没有内联键）在 422 之前出现
    工作 LLM 被替换。"""
    import tempfile
    from pathlib import Path

    from openhands.agent_server.persistence import store as store_module
    from openhands.sdk.llm.provider_connection_store import ProviderConnectionStore

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        provider_store = ProviderConnectionStore(base_dir=base / "connections")
        profile_store = LLMProfileStore(
            base_dir=base / "profiles", provider_store=provider_store
        )

        mock_conversation = MagicMock()
        mock_conversation_service.get_event_service.return_value = mock_event_service
        mock_event_service.get_conversation.return_value = mock_conversation
        client.app.dependency_overrides[get_conversation_service] = lambda: (
            mock_conversation_service
        )

        old_store = store_module._llm_profile_store
        store_module._llm_profile_store = profile_store
        try:
            response = client.post(
                f"/api/conversations/{sample_conversation_id}/switch_llm",
                json={
                    "llm": {
                        "model": "openrouter/z-ai/glm-5.3-flash",
                        "provider_connection_id": "ghost-conn",
                        "usage_id": "caller-supplied-id",
                    }
                },
            )

            assert response.status_code == 422
            assert "ghost-conn" in response.json()["detail"]
            mock_conversation.switch_llm.assert_not_called()
        finally:
            store_module._llm_profile_store = old_store
            client.app.dependency_overrides.clear()


def _provider_connection(connection_id: str, *, api_key: str, base_url: str | None):
    from openhands.sdk.llm.provider_connection_store import ProviderConnection

    now = int(time.time())
    return ProviderConnection(
        id=connection_id,
        display_name=connection_id,
        provider="custom",
        api_key=SecretStr(api_key),
        base_url=base_url,
        created_at=now,
        updated_at=now,
    )


def test_fork_conversation_success(
    client, mock_conversation_service, sample_conversation_info, sample_conversation_id
):
    """测试分叉端点返回 201 以及分叉对话信息。"""
    mock_conversation_service.fork_conversation.return_value = sample_conversation_info

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/fork",
            json={"title": "Forked", "reset_metrics": True},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(sample_conversation_info.id)
        mock_conversation_service.fork_conversation.assert_called_once()
    finally:
        client.app.dependency_overrides.clear()


def test_fork_conversation_not_found(
    client, mock_conversation_service, sample_conversation_id
):
    """当源会话不存在时，测试分支返回 404。"""
    mock_conversation_service.fork_conversation.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/fork",
            json={},
        )

        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_fork_conversation_duplicate_id_returns_409(
    client, mock_conversation_service, sample_conversation_id
):
    """当请求的分叉 ID 已存在时，测试分叉返回 409。"""
    mock_conversation_service.fork_conversation.side_effect = ValueError(
        f"Conversation with id {sample_conversation_id} already exists"
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/fork",
            json={"id": str(sample_conversation_id)},
        )

        assert response.status_code == 409
    finally:
        client.app.dependency_overrides.clear()


def test_fork_conversation_from_event_id_passed_through(
    client, mock_conversation_service, sample_conversation_info, sample_conversation_id
):
    """fork with from_event_id 将分支点转发到服务。"""
    mock_conversation_service.fork_conversation.return_value = sample_conversation_info

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/fork",
            json={"from_event_id": "evt-123"},
        )

        assert response.status_code == 201
        _, kwargs = mock_conversation_service.fork_conversation.call_args
        assert kwargs["from_event_id"] == "evt-123"
    finally:
        client.app.dependency_overrides.clear()


def test_fork_conversation_unknown_from_event_id_returns_404(
    client, mock_conversation_service, sample_conversation_id
):
    """具有未知 from_event_id 表面的叉子为 404。"""
    mock_conversation_service.fork_conversation.side_effect = ValueError(
        "Unknown from_event_id: evt-missing"
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/fork",
            json={"from_event_id": "evt-missing"},
        )

        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_navigate_conversation_success(
    client, mock_conversation_service, sample_conversation_info, sample_conversation_id
):
    """导航返回更新的对话信息并转发event_id。"""
    mock_conversation_service.navigate_conversation.return_value = (
        sample_conversation_info
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/navigate",
            json={"event_id": "evt-42"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_conversation_info.id)
        _, kwargs = mock_conversation_service.navigate_conversation.call_args
        assert kwargs["event_id"] == "evt-42"
    finally:
        client.app.dependency_overrides.clear()


def test_ask_agent_unknown_conversation_returns_404(
    client, mock_conversation_service, sample_conversation_id
):
    """当对话不存在时，ask_agent 返回 404，而不是 500。"""
    mock_conversation_service.ask_agent.return_value = None

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/ask_agent",
            json={"question": "hi"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Conversation not found"
    finally:
        client.app.dependency_overrides.clear()


@pytest.mark.parametrize("failure_mode", ["missing_conversation", "unknown_event"])
def test_navigate_conversation_returns_404(
    client, mock_conversation_service, sample_conversation_id, failure_mode
):
    """如果缺少对话或未知事件，navigate 将返回 404。"""
    if failure_mode == "missing_conversation":
        mock_conversation_service.navigate_conversation.return_value = None
    else:
        mock_conversation_service.navigate_conversation.side_effect = ValueError(
            "Unknown event_id: evt-missing"
        )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(
            f"/api/conversations/{sample_conversation_id}/navigate",
            json={"event_id": "evt-42"},
        )

        assert response.status_code == 404
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_client_tool_registration_error_returns_422(
    client, mock_conversation_service
):
    """客户端工具注册输入错误产生 422，而不是 500。"""
    from openhands.sdk.tool.client_tool import ClientToolRegistrationError

    mock_conversation_service.start_conversation.side_effect = (
        ClientToolRegistrationError(
            "Client tool name 'terminal' collides with an existing non-client tool."
        )
    )

    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    request = StartConversationRequest(
        agent=Agent(
            llm=LLM(model="gpt-4o", api_key=SecretStr("test-key"), usage_id="t"),
            tools=[],
        ),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
    )

    try:
        response = client.post(
            "/api/conversations",
            json=request.model_dump(mode="json"),
        )

        assert response.status_code == 422
        assert "collides with an existing non-client tool" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


def test_start_conversation_unavailable_agent_tool_returns_422(
    client, mock_conversation_service
):
    """服务器无法导入其模块的智能体工具会生成 422，而不是 500。"""
    from openhands.agent_server.conversation_service import UnavailableAgentTool

    mock_conversation_service.start_conversation.side_effect = UnavailableAgentTool(
        "The agent uses tools whose modules the agent server cannot import: "
        "'qa_ghost_tool' (qa_ghost: No module named 'qa_ghost')"
    )
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    request = StartConversationRequest(
        agent=Agent(
            llm=LLM(model="gpt-4o", api_key=SecretStr("test-key"), usage_id="t"),
            tools=[],
        ),
        workspace=LocalWorkspace(working_dir="/tmp/test"),
    )

    try:
        response = client.post(
            "/api/conversations", json=request.model_dump(mode="json")
        )

        assert response.status_code == 422
        assert "'qa_ghost_tool'" in response.json()["detail"]
    finally:
        client.app.dependency_overrides.clear()


@pytest.mark.parametrize("method,suffix", [("get", ""), ("post", "/reprovision")])
def test_runtime_requires_existing_conversation(
    client, mock_conversation_service, method, suffix
):
    mock_conversation_service.get_conversation.return_value = None
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )
    response = client.request(method, f"/api/conversations/{uuid4()}/runtime{suffix}")
    assert response.status_code == 404


def test_condense_conversation_without_condenser_returns_409(
    client, mock_conversation_service, sample_conversation_id
):
    """condense 当智能体无法压缩时回答 409 并说明原因。"""
    mock_conversation_service.condense.side_effect = CondensationUnavailable(
        "Cannot condense conversation: No condenser configured"
    )
    client.app.dependency_overrides[get_conversation_service] = lambda: (
        mock_conversation_service
    )

    try:
        response = client.post(f"/api/conversations/{sample_conversation_id}/condense")

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "Cannot condense conversation: No condenser configured"
        )
    finally:
        client.app.dependency_overrides.clear()
