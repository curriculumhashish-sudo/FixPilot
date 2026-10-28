"""测试带有机密参数的对话构造函数。"""

import tempfile
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.impl.remote_conversation import RemoteConversation
from openhands.sdk.llm import LLM
from openhands.sdk.secret import SecretSource
from openhands.sdk.workspace import RemoteWorkspace

from .conftest import create_mock_http_client


# 注意：有意的模块级。 局部函数 ``SecretSource``
# (DiscriminatedUnionMixin) 类自动注册全局，并且使注册表在任何后续的歧异联合中引发 "本地
# 类不支持！" 验证在同一个 xdist 工作器中（e.g. 无关的 ConversationState  反序列化).
#
class _DynamicTokenSource(SecretSource):
    def get_value(self):
        return "dynamic-token-789"


class _CallableApiKeySource(SecretSource):
    def get_value(self):
        return "callable-api-key"


def create_test_agent() -> Agent:
    """创建测试智能体。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    return Agent(llm=llm, tools=[])


def test_local_conversation_constructor_with_secrets():
    """测试 LocalConversation 构造函数接受并初始化机密。"""
    agent = create_test_agent()

    # 测试机密为 dict[str, str]
    test_secrets = {
        "API_KEY": "test-api-key-123",
        "DATABASE_URL": "postgresql://localhost/test",
        "AUTH_TOKEN": "bearer-token-456",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(
            agent=agent, workspace=tmpdir, persistence_dir=tmpdir, secrets=test_secrets
        )

        # 验证它是 LocalConversation
        assert isinstance(conv, LocalConversation)

        # 验证机密已初始化
        secret_registry = conv.state.secret_registry
        assert secret_registry is not None

        # 验证机密可通过机密注册表访问
        env_vars = secret_registry.get_secrets_as_env_vars("echo $API_KEY")
        assert env_vars == {"API_KEY": "test-api-key-123"}

        env_vars = secret_registry.get_secrets_as_env_vars("echo $DATABASE_URL")
        assert env_vars == {"DATABASE_URL": "postgresql://localhost/test"}

        # 在一个命令中测试多个机密
        env_vars = secret_registry.get_secrets_as_env_vars(
            "export API_KEY=$API_KEY && export AUTH_TOKEN=$AUTH_TOKEN"
        )
        assert env_vars == {
            "API_KEY": "test-api-key-123",
            "AUTH_TOKEN": "bearer-token-456",
        }


def test_local_conversation_constructor_with_callable_secrets():
    """使用可调用机密测试 LocalConversation 构造函数。"""
    agent = create_test_agent()

    test_secrets = {
        "STATIC_KEY": "static-value",
        "DYNAMIC_TOKEN": _DynamicTokenSource(),
        "API_KEY": _CallableApiKeySource(),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(
            agent=agent, workspace=tmpdir, persistence_dir=tmpdir, secrets=test_secrets
        )

        # 验证它是 LocalConversation
        assert isinstance(conv, LocalConversation)

        # 验证可调用机密工作
        secret_registry = conv.state.secret_registry

        env_vars = secret_registry.get_secrets_as_env_vars("echo $DYNAMIC_TOKEN")
        assert env_vars == {"DYNAMIC_TOKEN": "dynamic-token-789"}

        env_vars = secret_registry.get_secrets_as_env_vars("echo $API_KEY")
        assert env_vars == {"API_KEY": "callable-api-key"}

        env_vars = secret_registry.get_secrets_as_env_vars("echo $STATIC_KEY")
        assert env_vars == {"STATIC_KEY": "static-value"}


def test_local_conversation_constructor_without_secrets():
    """测试 LocalConversation 构造函数在没有机密参数的情况下工作。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(
            agent=agent,
            workspace=tmpdir,
            persistence_dir=tmpdir,
            # 无机密参数
        )

        # 验证它是 LocalConversation
        assert isinstance(conv, LocalConversation)

        # 验证机密管理器存在但为空
        secret_registry = conv.state.secret_registry
        assert secret_registry is not None

        # 应该为任何命令返回空字典
        env_vars = secret_registry.get_secrets_as_env_vars("echo $API_KEY")
        assert env_vars == {}


def test_local_conversation_constructor_with_empty_secrets():
    """使用空的机密字典测试 LocalConversation 构造函数。"""
    agent = create_test_agent()

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(
            agent=agent,
            workspace=tmpdir,
            persistence_dir=tmpdir,
            secrets={},  # 空字典
        )

        # 验证它是 LocalConversation
        assert isinstance(conv, LocalConversation)

        # 验证机密管理器存在但为空
        secret_registry = conv.state.secret_registry
        assert secret_registry is not None

        # 应该为任何命令返回空字典
        env_vars = secret_registry.get_secrets_as_env_vars("echo $API_KEY")
        assert env_vars == {}


@pytest.mark.parametrize("api_key", [None, "test-api-key"])
def test_remote_conversation_constructor_with_secrets(api_key):
    """测试 RemoteConversation 构造函数接受并初始化机密。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端
    mock_client_instance = create_mock_http_client()

    test_secrets = {
        "API_KEY": "test-api-key-123",
        "DATABASE_URL": "postgresql://localhost/test",
    }

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创建一个RemoteWorkspace
        workspace = RemoteWorkspace(
            host="http://localhost:3000",
            api_key=api_key,
            working_dir="/workspace/project",
        )

        # 将工作区客户端替换为模拟对象，以确保所有 HTTP 调用都使用模拟对象
        workspace._client = mock_client_instance

        conv = Conversation(agent=agent, workspace=workspace, secrets=test_secrets)

        # 验证它是 RemoteConversation
        assert isinstance(conv, RemoteConversation)

        # 验证 update_secrets 在初始化期间被调用 RemoteConversation 应该发出 POST 请求来
        # 更新机密
        #
        mock_client_instance.request.assert_any_call(
            "POST",
            "/api/conversations/12345678-1234-5678-9abc-123456789abc/secrets",
            json={"secrets": test_secrets},
        )


def test_remote_conversation_constructor_with_callable_secrets():
    """使用可调用机密测试 RemoteConversation 构造函数。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端
    mock_client_instance = create_mock_http_client()

    def get_dynamic_token():
        return "dynamic-token-789"

    test_secrets = {"STATIC_KEY": "static-value", "DYNAMIC_TOKEN": get_dynamic_token}

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创建一个RemoteWorkspace
        workspace = RemoteWorkspace(
            host="http://localhost:3000",
            api_key="test-api-key",
            working_dir="/workspace/project",
        )

        # 将工作区客户端替换为模拟对象，以确保所有 HTTP 调用都使用模拟对象
        workspace._client = mock_client_instance

        conv = Conversation(agent=agent, workspace=workspace, secrets=test_secrets)

        # 验证它是 RemoteConversation
        assert isinstance(conv, RemoteConversation)

        # 验证可调用机密已解析并发送到服务器
        expected_serialized_secrets = {
            "STATIC_KEY": "static-value",
            "DYNAMIC_TOKEN": "dynamic-token-789",  # Callable 被调用
        }

        mock_client_instance.request.assert_any_call(
            "POST",
            "/api/conversations/12345678-1234-5678-9abc-123456789abc/secrets",
            json={"secrets": expected_serialized_secrets},
        )


def test_remote_conversation_constructor_without_secrets():
    """测试 RemoteConversation 构造函数在没有机密参数的情况下工作。"""
    agent = create_test_agent()

    # 模拟对象 httpx 客户端
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        # 创建一个RemoteWorkspace
        workspace = RemoteWorkspace(
            host="http://localhost:3000",
            api_key="test-api-key",
            working_dir="/workspace/project",
        )

        # 将工作区客户端替换为模拟对象，以确保所有 HTTP 调用都使用模拟对象
        workspace._client = mock_client_instance

        conv = Conversation(
            agent=agent,
            workspace=workspace,
            # 无机密参数
        )

        # 验证它是 RemoteConversation
        assert isinstance(conv, RemoteConversation)

        # 验证是否未进行机密更新调用
        secrets_calls = [
            call
            for call in mock_client_instance.request.call_args_list
            if "/secrets" in str(call)
        ]
        assert len(secrets_calls) == 0


def test_conversation_factory_routing_with_secrets():
    """测试对话工厂是否使用机密正确路由到本地/远程。"""
    agent = create_test_agent()
    test_secrets = {"API_KEY": "test-key"}

    # 测试LocalConversation路由
    with tempfile.TemporaryDirectory() as tmpdir:
        local_conv = Conversation(agent=agent, workspace=tmpdir, secrets=test_secrets)
        assert isinstance(local_conv, LocalConversation)

    # 测试 RemoteConversation 路由模拟对象 httpx 客户端
    #
    mock_client_instance = create_mock_http_client()

    with (
        patch("httpx.Client", return_value=mock_client_instance),
        patch(
            "openhands.sdk.conversation.impl.remote_conversation"
            ".WebSocketCallbackClient"
        ),
    ):
        workspace = RemoteWorkspace(
            host="http://localhost:3000",
            api_key="test-api-key",
            working_dir="/workspace/project",
        )

        # 将工作区客户端替换为模拟对象，以确保所有 HTTP 调用都使用模拟对象
        workspace._client = mock_client_instance

        remote_conv = Conversation(
            agent=agent, workspace=workspace, secrets=test_secrets
        )
        assert isinstance(remote_conv, RemoteConversation)


def test_secrets_parameter_type_validation():
    """测试机密参数是否接受正确的类型。"""
    agent = create_test_agent()

    # 使用有效的 dict[str、str] 进行测试
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, workspace=tmpdir, secrets={"KEY": "value"})
        assert isinstance(conv, LocalConversation)

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(
            agent=agent, workspace=tmpdir, secrets={"KEY": "secret-value"}
        )  # type: ignore[dict-item]
        assert isinstance(conv, LocalConversation)

    # 使用 None 进行测试（应该有效）
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, workspace=tmpdir, secrets=None)
        assert isinstance(conv, LocalConversation)
