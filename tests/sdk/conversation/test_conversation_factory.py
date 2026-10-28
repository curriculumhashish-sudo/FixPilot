"""测试对话工厂功能。"""

import uuid
from unittest.mock import Mock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk import Agent, Conversation
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import RemoteWorkspace


@pytest.fixture
def agent():
    """创建测试智能体。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"))
    return Agent(llm=llm, tools=[])


@pytest.fixture
def remote_workspace():
    """使用模拟的客户端创建 RemoteWorkspace。"""
    workspace = RemoteWorkspace(
        host="http://localhost:8000", working_dir="/workspace/project"
    )

    # 模拟对象工作区客户端
    mock_client = Mock()
    workspace._client = mock_client

    # 模拟对象对话创建响应
    conversation_id = str(uuid.uuid4())
    mock_conv_response = Mock()
    mock_conv_response.raise_for_status.return_value = None
    mock_conv_response.json.return_value = {"id": conversation_id}

    # 模拟对象事件响应（_do_full_sync 在 RemoteEventsList 初始化期间使用）
    mock_events_response = Mock()
    mock_events_response.raise_for_status.return_value = None
    mock_events_response.json.return_value = {"items": [], "next_page_id": None}

    # WebSocket 订阅后 reconcile() 调用的模拟对象事件响应
    mock_reconcile_response = Mock()
    mock_reconcile_response.raise_for_status.return_value = None
    mock_reconcile_response.json.return_value = {"items": [], "next_page_id": None}

    mock_client.request.side_effect = [
        mock_conv_response,
        mock_events_response,
        mock_reconcile_response,
    ]

    return workspace


def test_conversation_factory_creates_local_by_default(agent):
    """当未指定工作区时，测试工厂创建 LocalConversation。"""
    conversation = Conversation(agent=agent)

    assert isinstance(conversation, LocalConversation)
    conversation.close()


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_conversation_factory_creates_remote_with_workspace(
    mock_ws_client, agent, remote_workspace
):
    """测试工厂用 RemoteWorkspace 创建 RemoteConversation。"""
    conversation = Conversation(agent=agent, workspace=remote_workspace)

    assert isinstance(conversation, RemoteConversation)


def test_conversation_factory_forwards_local_parameters(agent):
    """测试工厂正确地将参数转发到LocalConversation。"""
    conversation = Conversation(
        agent=agent,
        max_iteration_per_run=100,
        stuck_detection=False,
        visualizer=None,
    )

    assert isinstance(conversation, LocalConversation)
    assert conversation.max_iteration_per_run == 100
    conversation.close()


def test_conversation_factory_forwards_local_observability_span_name(agent):
    with (
        patch(
            "openhands.sdk.conversation.base.should_enable_observability",
            return_value=True,
        ),
        patch("openhands.sdk.conversation.base.start_root_span") as mock_start_span,
        patch("openhands.sdk.conversation.base.start_child_span") as mock_child_span,
        patch("openhands.sdk.conversation.base.end_root_span"),
    ):
        conversation = Conversation(
            agent=agent,
            visualizer=None,
            observability_span_name="pr_review_evaluation",
        )
        assert isinstance(conversation, LocalConversation)
        mock_start_span.assert_called_once()
        assert mock_start_span.call_args.args[0] == "conversation"
        mock_child_span.assert_called_once_with(
            mock_start_span.return_value,
            "pr_review_evaluation",
            tags=None,
        )
        conversation.close()


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_conversation_factory_forwards_remote_parameters(
    mock_ws_client, agent, remote_workspace
):
    """测试工厂正确地将参数转发到RemoteConversation。"""
    conversation = Conversation(
        agent=agent,
        workspace=remote_workspace,
        max_iteration_per_run=200,
        stuck_detection=True,
    )

    assert isinstance(conversation, RemoteConversation)
    assert conversation.max_iteration_per_run == 200


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_conversation_factory_forwards_remote_user_id_to_create_payload(
    mock_ws_client, agent, remote_workspace
):
    """RemoteConversation 必须将 user_id 发送到智能体服务器创建请求。"""
    conversation = Conversation(
        agent=agent,
        workspace=remote_workspace,
        tags={"automationid": "auto-1"},
        user_id="user-42",
        observability_span_name="pr_review_evaluation",
    )

    assert isinstance(conversation, RemoteConversation)
    create_call = remote_workspace._client.request.call_args_list[0]
    assert create_call.args[:2] == ("POST", "/api/conversations")
    payload = create_call.kwargs["json"]
    assert payload["user_id"] == "user-42"
    assert payload["tags"] == {"automationid": "auto-1"}
    assert payload["observability_span_name"] == "pr_review_evaluation"


def test_conversation_factory_string_workspace_creates_local(agent):
    """测试字符串工作区创建 LocalConversation。"""
    conversation = Conversation(agent=agent, workspace="")

    assert isinstance(conversation, LocalConversation)
    conversation.close()


@patch("openhands.sdk.conversation.impl.remote_conversation.WebSocketCallbackClient")
def test_conversation_factory_type_inference(mock_ws_client, agent, remote_workspace):
    """测试类型提示是否适用于两种对话类型。"""
    local_conv = Conversation(agent=agent)
    remote_conv = Conversation(agent=agent, workspace=remote_workspace)

    assert isinstance(local_conv, LocalConversation)
    assert isinstance(remote_conv, RemoteConversation)
    local_conv.close()
