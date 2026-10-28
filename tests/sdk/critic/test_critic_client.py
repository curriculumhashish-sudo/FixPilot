"""测试 CriticClient api_key 处理。"""

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent
from openhands.sdk.critic.impl.api import APIBasedCritic
from openhands.sdk.critic.impl.api.client import (
    DEFAULT_CRITIC_MODEL_NAME,
    DEFAULT_CRITIC_SERVER_URL,
    CriticClient,
)
from openhands.sdk.utils.cipher import Cipher


def test_critic_client_uses_current_default_route():
    """默认批评者路由应针对托管代理传递。"""
    client = CriticClient(api_key="test_api_key_123")

    assert DEFAULT_CRITIC_SERVER_URL == "https://llm-proxy.app.all-hands.dev/vllm"
    assert DEFAULT_CRITIC_MODEL_NAME == "critic"
    assert client.server_url == DEFAULT_CRITIC_SERVER_URL
    assert client.model_name == DEFAULT_CRITIC_MODEL_NAME


def test_critic_client_with_str_api_key():
    """测试 CriticClient 接受 str api_key 并转换为 SecretStr。"""
    client = CriticClient(api_key="test_api_key_123")

    assert isinstance(client.api_key, SecretStr)
    assert client.api_key.get_secret_value() == "test_api_key_123"


def test_critic_client_with_secret_str_api_key():
    """测试 CriticClient 是否直接接受 SecretStr api_key。"""
    secret_key = SecretStr("secret_api_key_456")
    client = CriticClient(api_key=secret_key)

    assert isinstance(client.api_key, SecretStr)
    assert client.api_key.get_secret_value() == "secret_api_key_456"


def test_critic_client_empty_string_api_key():
    """测试 CriticClient 将空字符串 api_key 标准化为 None。"""
    client = CriticClient(api_key="")

    assert client.api_key is None


def test_critic_client_whitespace_only_api_key():
    """测试 CriticClient 将纯空白 api_key 标准化为 None。"""
    client = CriticClient(api_key="   \t\n  ")

    assert client.api_key is None


def test_critic_client_empty_secret_str_api_key():
    """测试 CriticClient 将空 SecretStr api_key 标准化为 None。"""
    client = CriticClient(api_key=SecretStr(""))

    assert client.api_key is None


def test_critic_client_normalizes_redacted_api_key_placeholder():
    """测试已脱敏评论家 api_key 占位符变为 None。"""
    client = CriticClient(api_key="**********")

    assert client.api_key is None


def test_critic_client_rejects_none_api_key_for_inference():
    """测试缺少的api_key不能用作运行时凭据。"""
    client = CriticClient(api_key="**********")

    with pytest.raises(ValueError, match="api_key must be non-empty"):
        client._get_api_key_value()


def test_critic_client_whitespace_secret_str_api_key():
    """测试 CriticClient 规范化仅包含空格的 SecretStr api_key。"""
    client = CriticClient(api_key=SecretStr("   \t\n  "))

    assert client.api_key is None


def test_critic_client_api_key_not_exposed_in_repr():
    """测试 api_key 是否未在字符串表示形式中公开。"""
    client = CriticClient(api_key="super_secret_key")

    client_repr = repr(client)
    client_str = str(client)

    # SecretStr 应该隐藏 repr/str 中的实际键值
    assert "super_secret_key" not in client_repr
    assert "super_secret_key" not in client_str


def test_critic_client_api_key_preserved_after_validation():
    """测试 api_key 值是否正确保留在验证之后。"""
    test_key = "my_test_key_789"
    client = CriticClient(api_key=test_key)

    # 验证密钥是否正确保存
    assert isinstance(client.api_key, SecretStr)
    assert client.api_key.get_secret_value() == test_key

    # 验证它也适用于 SecretStr 输入
    secret_key = SecretStr("another_key_101112")
    client2 = CriticClient(api_key=secret_key)
    assert isinstance(client2.api_key, SecretStr)
    assert client2.api_key.get_secret_value() == "another_key_101112"


def test_critic_client_api_key_exposed_with_context():
    """测试 expose_secrets 是否揭示了传输层载荷的 api_key。"""
    client = CriticClient(api_key="critic-secret")

    dumped = client.model_dump(mode="json", context={"expose_secrets": True})

    assert dumped["api_key"] == "critic-secret"


def test_critic_client_api_key_encrypted_with_cipher():
    """测试密码上下文加密并恢复 api_key。"""
    cipher = Cipher(secret_key="test-secret-key")
    client = CriticClient(api_key="critic-secret")

    dumped = client.model_dump(mode="json", context={"cipher": cipher})

    assert dumped["api_key"] != "critic-secret"
    assert dumped["api_key"] != "**********"
    restored = CriticClient.model_validate(dumped, context={"cipher": cipher})
    assert isinstance(restored.api_key, SecretStr)
    assert restored.api_key.get_secret_value() == "critic-secret"


def test_agent_dump_exposes_nested_critic_api_key_with_context():
    """测试智能体序列化保留批评家 api_key 和上下文。"""
    agent = Agent(
        llm=LLM(model="test-model", api_key=SecretStr("llm-secret")),
        critic=APIBasedCritic(
            api_key=SecretStr("critic-secret"),
            server_url="https://critic.example.com",
            model_name="critic",
        ),
    )

    dumped = agent.model_dump(mode="json", context={"expose_secrets": True})

    assert dumped["llm"]["api_key"] == "llm-secret"
    assert dumped["critic"]["api_key"] == "critic-secret"


def test_agent_dump_encrypts_nested_critic_api_key_with_cipher():
    """测试智能体序列化使用密码加密嵌套批评家 api_key。"""
    cipher = Cipher(secret_key="test-secret-key")
    agent = Agent(
        llm=LLM(model="test-model", api_key=SecretStr("llm-secret")),
        critic=APIBasedCritic(
            api_key=SecretStr("critic-secret"),
            server_url="https://critic.example.com",
            model_name="critic",
        ),
    )

    dumped = agent.model_dump(mode="json", context={"cipher": cipher})

    assert dumped["llm"]["api_key"] != "llm-secret"
    assert dumped["critic"]["api_key"] != "critic-secret"
    assert dumped["critic"]["api_key"] != "**********"

    restored = Agent.model_validate(dumped, context={"cipher": cipher})
    assert isinstance(restored.critic, APIBasedCritic)
    assert isinstance(restored.critic.api_key, SecretStr)
    assert restored.critic.api_key.get_secret_value() == "critic-secret"
