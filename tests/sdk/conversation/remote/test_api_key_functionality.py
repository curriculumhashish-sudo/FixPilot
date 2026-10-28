"""测试 RemoteConversation 中的 API 关键功能。"""

import uuid
from unittest.mock import Mock, patch

from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.impl.remote_conversation import (
    RemoteConversation,
    WebSocketCallbackClient,
)
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import RemoteWorkspace

from ..conftest import create_mock_http_client


def create_test_agent() -> Agent:
    """创建测试智能体。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(llm=llm, tools=[])


def test_conversation_factory_passes_api_key_to_remote():
    """测试会话工厂是否通过 api_key 到 RemoteConversation。"""
    agent = create_test_agent()
    test_api_key = "test-api-key-123"

    with patch(
        "openhands.sdk.conversation.impl.remote_conversation.RemoteConversation"
    ) as mock_remote:
        # 模拟对象 RemoteConversation 构造函数
        mock_instance = Mock()
        mock_remote.return_value = mock_instance

        # 与 RemoteWorkspace 创建对话
        workspace = RemoteWorkspace(
            working_dir="/tmp",
            host="http://localhost:3000",
            api_key=test_api_key,
        )
        Conversation(
            agent=agent,
            workspace=workspace,
        )

        # 验证 RemoteConversation 是通过工作区调用的
        mock_remote.assert_called_once()
        call_args = mock_remote.call_args
        assert call_args.kwargs["workspace"] == workspace


def test_remote_conversation_no_api_key_no_headers():
    """测试在未提供 API 键时 RemoteConversation 是否不添加标头。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance) as mock_httpx_client,
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创建没有 API 键的 RemoteWorkspace
        workspace = RemoteWorkspace(
            working_dir="/tmp",
            host="http://localhost:3000",
            api_key=None,
        )
        # 创建没有 API 键的 RemoteConversation
        RemoteConversation(
            agent=agent,
            workspace=workspace,
        )

        # 验证 httpx.Client 是在没有 API 密钥标头的情况下调用的
        mock_httpx_client.assert_called_once()
        call_args = mock_httpx_client.call_args

        # 检查标头是否为空或不包含 API 键
        headers = call_args.kwargs.get("headers", {})
        assert "X-Session-API-Key" not in headers


def test_websocket_client_includes_api_key_in_url():
    """测试 WebSocketCallbackClient 是否包含 WebSocket URL 中的 API 键。"""
    test_api_key = "test-api-key-123"
    host = "http://localhost:3000"
    conversation_id = str(uuid.uuid4())
    callback = Mock()

    ws_client = WebSocketCallbackClient(
        host=host,
        conversation_id=conversation_id,
        callback=callback,
        api_key=test_api_key,
    )

    # 通过检查存储的 api_key 来测试 URL 构造逻辑
    assert ws_client.api_key == test_api_key
    assert ws_client.host == host
    assert ws_client.conversation_id == conversation_id


def test_websocket_client_no_api_key():
    """测试 WebSocketCallbackClient 是否在没有 API 键的情况下工作。"""
    host = "http://localhost:3000"
    conversation_id = str(uuid.uuid4())
    callback = Mock()

    ws_client = WebSocketCallbackClient(
        host=host,
        conversation_id=conversation_id,
        callback=callback,
        api_key=None,
    )

    # 测试它是否可以在没有 API 键的情况下工作
    assert ws_client.api_key is None
    assert ws_client.host == host
    assert ws_client.conversation_id == conversation_id


def test_remote_conversation_passes_api_key_to_websocket_client():
    """测试 RemoteConversation 将 API 密钥传递给 WebSocketCallbackClient。"""
    agent = create_test_agent()
    test_api_key = "test-api-key-123"

    # 模拟对象 httpx 客户端
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ) as mock_ws_client,
    ):
        mock_ws_instance = Mock()
        mock_ws_client.return_value = mock_ws_instance

        # 使用 API 键创建 RemoteWorkspace
        workspace = RemoteWorkspace(
            working_dir="/tmp",
            host="http://localhost:3000",
            api_key=test_api_key,
        )
        # 使用 API 键创建 RemoteConversation
        RemoteConversation(
            agent=agent,
            workspace=workspace,
        )

        # 验证 WebSocketCallbackClient 是通过 api_key 调用的
        mock_ws_client.assert_called_once()
        call_args = mock_ws_client.call_args
        assert call_args.kwargs["api_key"] == test_api_key
