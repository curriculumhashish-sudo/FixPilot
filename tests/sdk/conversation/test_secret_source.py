"""测试 SecretSources 类。"""

from unittest.mock import Mock, patch

import pytest
from pydantic import SecretStr

from openhands.sdk.secret import LookupSecret, StaticSecret
from openhands.sdk.utils.cipher import Cipher


@pytest.fixture
def lookup_secret():
    return LookupSecret(
        url="https://my-oauth-service.com",
        headers={
            "authorization": "Bearer Token",
            "cookie": "sessionid=abc123;",
            "x-access-token": "token-abc123",
            "some-key": "a key",
            "not-sensitive": "hello there",
        },
    )


def test_lookup_secret_serialization_default(lookup_secret):
    """测试 LookupSecret 序列化"""
    dumped = lookup_secret.model_dump(mode="json")
    expected = {
        "kind": "LookupSecret",
        "description": None,
        "url": "https://my-oauth-service.com",
        "headers": {
            "authorization": "**********",
            "cookie": "**********",
            "x-access-token": "**********",
            "some-key": "**********",
            "not-sensitive": "hello there",
        },
    }
    assert dumped == expected


def test_lookup_secret_serialization_expose_secrets(lookup_secret):
    """测试 LookupSecret 序列化"""
    dumped = lookup_secret.model_dump(mode="json", context={"expose_secrets": True})
    expected = {
        "kind": "LookupSecret",
        "description": None,
        "url": "https://my-oauth-service.com",
        "headers": {
            "authorization": "Bearer Token",
            "cookie": "sessionid=abc123;",
            "x-access-token": "token-abc123",
            "some-key": "a key",
            "not-sensitive": "hello there",
        },
    }
    assert dumped == expected
    validated = LookupSecret.model_validate(dumped)
    assert validated == lookup_secret


def test_lookup_secret_serialization_encrypt(lookup_secret):
    """测试 LookupSecret 序列化"""
    cipher = Cipher(secret_key="some secret key")
    dumped = lookup_secret.model_dump(mode="json", context={"cipher": cipher})
    validated = LookupSecret.model_validate(dumped, context={"cipher": cipher})
    assert validated == lookup_secret


def test_lookup_secret_deserialization_redacted_headers():
    """测试 LookupSecret 可以是带有已脱敏标头值的已反序列化。

    这是针对问题 1505 的回归测试，其中具有已脱敏（屏蔽）值的 LookupSecret 标头由于断
    言错误而无法反序列化。
    """
    # 使用已脱敏标头模拟已序列化状态
    serialized = {
        "kind": "LookupSecret",
        "description": None,
        "url": "https://my-oauth-service.com",
        "headers": {
            "authorization": "**********",  # 已脱敏
            "cookie": "**********",  # 已脱敏
            "x-access-token": "**********",  # 已脱敏
            "some-key": "**********",  # 已脱敏
            "not-sensitive": "hello there",  # 不是机密标头
        },
    }

    # 在修复断言错误之前此操作失败
    validated = LookupSecret.model_validate(serialized)

    # 应删除机密标头，因为它们是已脱敏
    assert validated.url == "https://my-oauth-service.com"
    # 应删除机密标头（因为它们的值为已脱敏）
    assert "authorization" not in validated.headers
    assert "cookie" not in validated.headers
    assert "x-access-token" not in validated.headers
    assert "some-key" not in validated.headers
    # 应保留非敏感标头
    assert validated.headers["not-sensitive"] == "hello there"


def test_static_secret_optional_value():
    """测试 StaticSecret 使用可选值（None 默认值）。

    这是针对问题 1505 的回归测试，其中 StaticSecret.value 是必填字段，导致反序列化在
    机密为已脱敏（转换为 None）时失败。
    """
    # 测试价值
    secret_with_value = StaticSecret(value=SecretStr("test-secret"))
    assert secret_with_value.get_value() == "test-secret"

    # 使用 None 值进行测试（默认）
    secret_without_value = StaticSecret()
    assert secret_without_value.value is None
    assert secret_without_value.get_value() is None

    # 使用 None 值测试反序列化
    serialized = {"kind": "StaticSecret", "value": None}
    validated = StaticSecret.model_validate(serialized)
    assert validated.value is None
    assert validated.get_value() is None


def test_static_secret_deserialization_redacted():
    """测试 StaticSecret 可以从已脱敏值变为已反序列化。

    这是问题 1505 的回归测试。
    """
    # 使用已脱敏值模拟已序列化状态
    serialized = {"kind": "StaticSecret", "value": "**********"}

    # 在修复之前此操作失败
    validated = StaticSecret.model_validate(serialized)

    # 该值应该是 None，因为它是已脱敏
    assert validated.value is None
    assert validated.get_value() is None


def test_lookup_secret_redacts_token_and_cookie_headers():
    """测试 X-Access-token 和 Cookie 标头是否正确已脱敏。

    这是一项回归测试，旨在防止轨迹导出中泄漏身份验证 token。 像 X-Access-token 和
    Cookie 这样的标头应在序列化期间被视为敏感标头和已脱敏。
    """
    secret = LookupSecret(
        url="https://api.example.com/secrets",
        headers={
            "X-Access-Token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "Cookie": "session_id=abc123; keycloak_auth=eyJhbGci...",
            "X-Auth-Token": "bearer_token_value",
            "Content-Type": "application/json",
        },
    )

    # 序列化不带 expose_secrets 上下文（默认行为）
    serialized = secret.model_dump(mode="json")

    # 检查基于 token 的标头是否为已脱敏
    assert serialized["headers"]["X-Access-Token"] == "**********"
    assert serialized["headers"]["Cookie"] == "**********"
    assert serialized["headers"]["X-Auth-Token"] == "**********"

    # 检查是否保留非机密标头
    assert serialized["headers"]["Content-Type"] == "application/json"


def test_lookup_secret_validate_with_cipher_preserves_plaintext_headers():
    """当密码存在时，明文身份验证标头必须保留验证
    上下文。

    回归测试：智能体-canvas（以及通过 ``secrets_encrypted=True`` 往返加密智能体机密的
    任何其他客户端）发送
    ``LookupSecret``，其``headers``携带明文``X-Session-API-Key``，用于验证延迟查找。
    验证器以前用来将明文头部通过
    ``cipher.decrypt``（因为头部名称匹配机密模式）传递，但失败了，并且以前默默地丢弃
    了头部。 然后，运行时 ``httpx.get`` 向智能体服务器
    发出未经身份验证的请求并收到 401，因此机密值永远无法用于对话。
    """
    cipher = Cipher(secret_key="some secret key")
    plaintext_session_key = "plaintext-session-api-key-value"

    serialized = {
        "kind": "LookupSecret",
        "url": "http://localhost:8000/api/settings/secrets/MY_TOKEN",
        "headers": {
            "X-Session-API-Key": plaintext_session_key,
            "Content-Type": "application/json",
        },
    }

    validated = LookupSecret.model_validate(serialized, context={"cipher": cipher})

    # 尽管密码位于上下文中，明文身份验证标头仍然存在。
    assert validated.headers["X-Session-API-Key"] == plaintext_session_key
    # 非机密标头仍可传递。
    assert validated.headers["Content-Type"] == "application/json"


def test_lookup_secret_validate_with_cipher_decrypts_encrypted_headers():
    """使用密码的往返加密标头仍应解密。

    与上面的明文测试相结合：当标头实际上使用相同的密码（e.g. 从 at-REST 存储加载），
    验证仍然必须将其解密回明文，而不是将其视为不透明的密文。
    """
    cipher = Cipher(secret_key="some secret key")
    secret = LookupSecret(
        url="https://my-oauth-service.com",
        headers={"Authorization": "Bearer real-token"},
    )

    dumped = secret.model_dump(mode="json", context={"cipher": cipher})
    # 健全性检查：标头在线路上进行加密。
    assert dumped["headers"]["Authorization"] != "Bearer real-token"

    validated = LookupSecret.model_validate(dumped, context={"cipher": cipher})
    assert validated.headers["Authorization"] == "Bearer real-token"


def test_lookup_secret_validate_with_cipher_drops_redacted_headers():
    """即使设置了密码，已脱敏标头仍必须被删除。

    确认明文-回退方案修复不会意外地复活像``"**********"``这样的屏蔽值，就好像它们是真
    正的身份验证材料一样。
    """
    cipher = Cipher(secret_key="some secret key")
    serialized = {
        "kind": "LookupSecret",
        "url": "https://my-oauth-service.com",
        "headers": {
            "Authorization": "**********",
            "X-Access-Token": "",
            "Content-Type": "application/json",
        },
    }

    validated = LookupSecret.model_validate(serialized, context={"cipher": cipher})
    assert "Authorization" not in validated.headers
    assert "X-Access-Token" not in validated.headers
    assert validated.headers["Content-Type"] == "application/json"


def test_lookup_secret_author_header_not_redacted():
    """测试合法的“作者”标头是否为不错误已脱敏。

    回归进行测试以确保子字符串模式匹配不会导致 False 诸如 Author、Co-Author、GitHub-
    Author 之类的标题出现正值。
    """
    secret = LookupSecret(
        url="https://api.example.com/data",
        headers={
            "Author": "john.doe@example.com",
            "Co-Author": "jane.doe@example.com",
            "GitHub-Author": "contributor@example.com",
            "Authorization": "Bearer secret_token",
        },
    )

    serialized = secret.model_dump(mode="json")

    # 与作者相关的标题应不为已脱敏（False 肯定检查）
    assert serialized["headers"]["Author"] == "john.doe@example.com"
    assert serialized["headers"]["Co-Author"] == "jane.doe@example.com"
    assert serialized["headers"]["GitHub-Author"] == "contributor@example.com"

    # 但授权应该是已脱敏
    assert serialized["headers"]["Authorization"] == "**********"


def test_lookup_secret_relative_url_uses_current_server(monkeypatch):
    monkeypatch.setenv("OH_INTERNAL_SERVER_URL", "http://127.0.0.1:4321")

    secret = LookupSecret(url="/api/settings/secrets/OPENAI_API_KEY")

    assert secret.url == "http://127.0.0.1:4321/api/settings/secrets/OPENAI_API_KEY"


def test_lookup_secret_get_value_resolves_relative_url(monkeypatch):
    monkeypatch.setenv("OH_INTERNAL_SERVER_URL", "http://127.0.0.1:4321")
    response = Mock(text="resolved-secret")
    response.raise_for_status = Mock()

    with patch(
        "openhands.sdk.secret.secrets.httpx.get", return_value=response
    ) as mock_get:
        secret = LookupSecret(url="api/settings/secrets/OPENAI_API_KEY")

        assert secret.get_value() == "resolved-secret"

    mock_get.assert_called_once_with(
        "http://127.0.0.1:4321/api/settings/secrets/OPENAI_API_KEY",
        headers={},
        timeout=30.0,
    )


@pytest.fixture
def local_resolvers_cleared():
    """每次测试时保持进程范围解析器注册表隔离。"""
    from openhands.sdk.secret import secrets as secrets_module

    original = list(secrets_module._local_secret_resolvers)
    secrets_module._local_secret_resolvers.clear()
    yield secrets_module._local_secret_resolvers
    secrets_module._local_secret_resolvers[:] = original


def test_local_resolver_short_circuits_http(local_resolvers_cleared):
    """匹配的解析器在没有任何 HTTP 请求的情况下进行应答。

    这是死锁防护：解析来自事件循环的环回会阻止服务请求的循环。
    """
    from openhands.sdk.secret import register_local_secret_resolver

    secret = LookupSecret(url="http://127.0.0.1:8000/api/settings/secrets/TOKEN")
    register_local_secret_resolver(
        lambda url: "resolved-locally" if url.endswith("/TOKEN") else None
    )

    with patch("httpx.get", side_effect=AssertionError("HTTP must not be used")):
        assert secret.get_value() == "resolved-locally"


def test_local_resolver_declining_falls_back_to_http(local_resolvers_cleared):
    """返回 None 的解析器将 URL 保留为 HTTP。"""
    from openhands.sdk.secret import register_local_secret_resolver

    secret = LookupSecret(url="https://remote.example/api/settings/secrets/TOKEN")
    register_local_secret_resolver(lambda url: None)

    response = Mock(text="from-http")
    response.raise_for_status = Mock()
    with patch("httpx.get", return_value=response) as http_get:
        assert secret.get_value() == "from-http"
    http_get.assert_called_once()


def test_local_resolver_raising_falls_back_to_http(local_resolvers_cleared):
    """损坏的解析器不得降低机密分辨率。"""
    from openhands.sdk.secret import register_local_secret_resolver

    def boom(url: str) -> str | None:
        raise RuntimeError("resolver is broken")

    secret = LookupSecret(url="https://remote.example/api/settings/secrets/TOKEN")
    register_local_secret_resolver(boom)

    response = Mock(text="from-http")
    response.raise_for_status = Mock()
    with patch("httpx.get", return_value=response):
        assert secret.get_value() == "from-http"


def test_unregister_local_secret_resolver(local_resolvers_cleared):
    from openhands.sdk.secret import (
        register_local_secret_resolver,
        unregister_local_secret_resolver,
    )

    def resolver(url: str) -> str | None:
        return "resolved-locally"

    register_local_secret_resolver(resolver)
    register_local_secret_resolver(resolver)
    assert len(local_resolvers_cleared) == 1

    unregister_local_secret_resolver(resolver)
    assert local_resolvers_cleared == []
