"""测试 pydantic_secrets 序列化和验证实用程序。"""

from base64 import urlsafe_b64encode
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from openhands.sdk.settings import OpenHandsAgentSettings
from openhands.sdk.utils.cipher import FERNET_TOKEN_PREFIX, Cipher
from openhands.sdk.utils.pydantic_secrets import (
    REDACTED_SECRET_VALUE,
    STRICT_DECRYPT_CONTEXT_KEY,
    SecretDecryptionError,
    decrypt_str_with_cipher_or_keep,
    is_redacted_secret,
    serialize_secret,
    validate_secret,
    validate_secret_dict,
)


@pytest.fixture
def cipher():
    """创建一个密码进行测试。"""
    key = urlsafe_b64encode(b"a" * 32).decode("ascii")
    return Cipher(key)


@pytest.fixture
def mock_info():
    """创建模拟对象 SerializationInfo/ValidationInfo。"""

    def create_info(context=None):
        info = MagicMock()
        info.context = context
        return info

    return create_info


# ── is_redacted_secret 测试────────────────────────────────────────────


def test_is_redacted_secret_with_redacted_string():
    assert is_redacted_secret(REDACTED_SECRET_VALUE) is True


def test_is_redacted_secret_with_redacted_secretstr():
    assert is_redacted_secret(SecretStr(REDACTED_SECRET_VALUE)) is True


def test_is_redacted_secret_with_normal_string():
    assert is_redacted_secret("sk-test-123") is False


def test_is_redacted_secret_with_normal_secretstr():
    assert is_redacted_secret(SecretStr("sk-test-123")) is False


def test_is_redacted_secret_with_none():
    assert is_redacted_secret(None) is False


# ── serialize_secret 测试──────────────────────────────────────────────


def test_serialize_secret_none_returns_none(mock_info):
    result = serialize_secret(None, mock_info({}))
    assert result is None


def test_serialize_secret_no_context_returns_secretstr(mock_info):
    """如果没有上下文，则为 Pydantic 默认屏蔽返回 SecretStr。"""
    secret = SecretStr("sk-test-123")
    result = serialize_secret(secret, mock_info(None))
    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == "sk-test-123"


def test_serialize_secret_empty_context_returns_secretstr(mock_info):
    """空上下文 = 没有曝光，返回 SecretStr。"""
    secret = SecretStr("sk-test-123")
    result = serialize_secret(secret, mock_info({}))
    assert isinstance(result, SecretStr)


def test_serialize_secret_plaintext_mode(mock_info):
    """expose_secrets='plaintext' returns raw value."""
    secret = SecretStr("sk-test-123")
    result = serialize_secret(secret, mock_info({"expose_secrets": "plaintext"}))
    assert result == "sk-test-123"


def test_serialize_secret_plaintext_mode_bool_true(mock_info):
    """expose_secrets=True (legacy) returns raw value."""
    secret = SecretStr("sk-test-123")
    result = serialize_secret(secret, mock_info({"expose_secrets": True}))
    assert result == "sk-test-123"


def test_serialize_secret_encrypted_mode_with_cipher(mock_info, cipher):
    """expose_secrets='encrypted' with cipher encrypts the value."""
    secret = SecretStr("sk-test-123")
    result = serialize_secret(
        secret, mock_info({"expose_secrets": "encrypted", "cipher": cipher})
    )
    # 应该加密（不是明文，不是已脱敏）
    assert result != "sk-test-123"
    assert result != REDACTED_SECRET_VALUE
    assert isinstance(result, str)
    # 应该可以解密
    decrypted = cipher.decrypt(result)
    assert decrypted.get_secret_value() == "sk-test-123"


def test_serialize_secret_encrypted_mode_without_cipher_raises_error(
    mock_info,
):
    """expose_secrets='encrypted' without cipher raises ValueError."""
    secret = SecretStr("sk-test-123")
    with pytest.raises(ValueError, match="no cipher configured"):
        serialize_secret(secret, mock_info({"expose_secrets": "encrypted"}))


def test_serialize_secret_cipher_without_expose_mode_encrypts(mock_info, cipher):
    """上下文中没有 expose_secrets 的密码仍然可以加密（向后兼容）。"""
    secret = SecretStr("sk-test-123")
    result = serialize_secret(secret, mock_info({"cipher": cipher}))
    assert result != "sk-test-123"
    # 应该可以解密
    decrypted = cipher.decrypt(result)
    assert decrypted.get_secret_value() == "sk-test-123"


def test_serialize_secret_cipher_with_plaintext_mode_returns_plaintext(
    mock_info, cipher
):
    """expose_secrets='plaintext' overrides cipher - returns raw value."""
    secret = SecretStr("sk-test-123")
    result = serialize_secret(
        secret, mock_info({"expose_secrets": "plaintext", "cipher": cipher})
    )
    assert result == "sk-test-123"


def test_serialize_secret_cipher_with_bool_true_returns_plaintext(mock_info, cipher):
    """expose_secrets=True (legacy boolean) overrides cipher - returns raw value.

    此测试向后兼容性：当使用密码传递 expose_secrets=True 时，它应该返回明文而不是加密
    。
    """
    secret = SecretStr("sk-test-123")
    result = serialize_secret(
        secret, mock_info({"expose_secrets": True, "cipher": cipher})
    )
    # 应该是明文，不加密
    assert result == "sk-test-123"


# ── validate_secret 测试────────────────────────────────────────────────


def test_validate_secret_none_returns_none(mock_info):
    result = validate_secret(None, mock_info({}))
    assert result is None


def test_validate_secret_invalid_type_int_raises_error(mock_info):
    """由于 int 类型无效，validate_secret 引发 TypeError。

    函数签名期望字符串类型 | SecretStr | None。 尝试对值调用 .strip() 时，传递整数失
    败。
    """
    with pytest.raises((TypeError, AttributeError)):
        validate_secret(123, mock_info({}))  # type: ignore[arg-type]


def test_validate_secret_invalid_type_dict_returns_none(mock_info):
    """validate_secret 优雅地处理空字典（返回 None）。

    空字典是假的，因此它被视为空/缺失机密。
    Note: 调用 .strip() 时，非空字典将会失败。
    """
    result = validate_secret({}, mock_info({}))  # type: ignore[arg-type]
    assert result is None


def test_validate_secret_invalid_type_list_returns_none(mock_info):
    """validate_secret 优雅地处理空列表（返回 None）。

    空列表是假的，因此它被视为空/缺失机密。
    Note: 调用 .strip() 时，非空列表将失败。
    """
    result = validate_secret([], mock_info({}))  # type: ignore[arg-type]
    assert result is None


def test_validate_secret_nonempty_dict_raises_error(mock_info):
    """validate_secret 引发非空字典错误（无效类型）。"""
    with pytest.raises((TypeError, AttributeError)):
        validate_secret({"key": "value"}, mock_info({}))  # type: ignore[arg-type]


def test_validate_secret_nonempty_list_raises_error(mock_info):
    """validate_secret 引发非空列表错误（无效类型）。"""
    with pytest.raises((TypeError, AttributeError)):
        validate_secret(["value"], mock_info({}))  # type: ignore[arg-type]


def test_validate_secret_string_returns_secretstr(mock_info):
    result = validate_secret("sk-test-123", mock_info({}))
    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == "sk-test-123"


def test_validate_secret_secretstr_passthrough(mock_info):
    secret = SecretStr("sk-test-123")
    result = validate_secret(secret, mock_info({}))
    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == "sk-test-123"


def test_validate_secret_empty_string_returns_none(mock_info):
    result = validate_secret("", mock_info({}))
    assert result is None


def test_validate_secret_whitespace_only_returns_none(mock_info):
    result = validate_secret("   ", mock_info({}))
    assert result is None


def test_validate_secret_redacted_value_returns_none(mock_info):
    result = validate_secret(REDACTED_SECRET_VALUE, mock_info({}))
    assert result is None


def test_validate_secret_with_cipher_decrypts(mock_info, cipher):
    """上下文中的密码触发解密。"""
    secret = SecretStr("sk-test-123")
    encrypted = cipher.encrypt(secret)

    result = validate_secret(encrypted, mock_info({"cipher": cipher}))
    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == "sk-test-123"


def test_validate_secret_with_cipher_plaintext_returns_secretstr(mock_info, cipher):
    """带密码的非 token 明文被视为遗留/明文输入。"""
    result = validate_secret("not-encrypted-data", mock_info({"cipher": cipher}))
    assert isinstance(result, SecretStr)
    assert result.get_secret_value() == "not-encrypted-data"


def test_validate_secret_with_cipher_malformed_fernet_returns_none(mock_info, cipher):
    """带有密码的格式错误的 Fernet 数据正常返回 None。"""
    result = validate_secret(
        f"{FERNET_TOKEN_PREFIX}not-a-valid-token", mock_info({"cipher": cipher})
    )
    assert result is None


def test_validate_secret_with_cipher_wrong_key_returns_none(mock_info, cipher):
    """错误的密钥返回 None（正常失败）。"""
    # 一键加密
    secret = SecretStr("sk-test-123")
    encrypted = cipher.encrypt(secret)

    # 尝试用不同的密钥解密
    other_key = urlsafe_b64encode(b"b" * 32).decode("ascii")
    other_cipher = Cipher(other_key)

    result = validate_secret(encrypted, mock_info({"cipher": other_cipher}))
    assert result is None


# ── 往返测试──────────────────────────────────────────────────────


def test_roundtrip_encrypted_mode(mock_info, cipher):
    """完整往返：序列化使用加密模式，使用密码进行验证。"""
    original = SecretStr("sk-test-api-key-12345")

    # 序列化带加密模式
    encrypted = serialize_secret(
        original, mock_info({"expose_secrets": "encrypted", "cipher": cipher})
    )
    assert encrypted != "sk-test-api-key-12345"

    # 使用密码验证（解密）
    decrypted = validate_secret(encrypted, mock_info({"cipher": cipher}))
    assert decrypted is not None
    assert decrypted.get_secret_value() == "sk-test-api-key-12345"


def test_roundtrip_plaintext_mode(mock_info):
    """明文模式的往返（无加密）。"""
    original = SecretStr("sk-test-api-key-12345")

    # 序列化明文模式
    plaintext = serialize_secret(original, mock_info({"expose_secrets": "plaintext"}))
    assert plaintext == "sk-test-api-key-12345"

    # 验证（仅包含在 SecretStr 中）
    result = validate_secret(plaintext, mock_info({}))
    assert result is not None
    assert result.get_secret_value() == "sk-test-api-key-12345"


# ── 真实Pydantic 集成测试 ──────────────────────────────────────


def test_real_pydantic_roundtrip_encrypted(cipher):
    """通过实际的 Pydantic 序列化（不是模拟对象）测试加密。"""
    from openhands.agent_server.persistence.models import CustomSecret

    # 使用明文创建
    secret = CustomSecret(name="TEST_KEY", secret=SecretStr("my-secret-value"))

    # 序列化与加密的上下文（真实的 model_dump 调用）
    data = secret.model_dump(
        mode="json", context={"expose_secrets": "encrypted", "cipher": cipher}
    )

    # 验证加密（不是明文，不是已脱敏）
    assert data["secret"] != "my-secret-value"
    assert data["secret"] != REDACTED_SECRET_VALUE
    assert isinstance(data["secret"], str)

    # 使用密码上下文验证（解密）（真实 model_validate 调用）
    restored = CustomSecret.model_validate(data, context={"cipher": cipher})
    assert restored.secret is not None
    assert restored.secret.get_secret_value() == "my-secret-value"


def test_real_pydantic_roundtrip_plaintext():
    """通过实际的 Pydantic 序列化（不是模拟对象）测试明文。"""
    from openhands.agent_server.persistence.models import CustomSecret

    # 使用明文创建
    secret = CustomSecret(name="TEST_KEY", secret=SecretStr("my-secret-value"))

    # 序列化明文上下文
    data = secret.model_dump(mode="json", context={"expose_secrets": "plaintext"})

    # 验证明文
    assert data["secret"] == "my-secret-value"

    # 验证（无密码 - 仅包含在 SecretStr 中）
    restored = CustomSecret.model_validate(data)
    assert restored.secret is not None
    assert restored.secret.get_secret_value() == "my-secret-value"


def test_real_pydantic_redacted_mode():
    """通过实际 Pydantic 序列化测试脱敏（默认行为）。"""
    from openhands.agent_server.persistence.models import CustomSecret

    # 使用明文创建
    secret = CustomSecret(name="TEST_KEY", secret=SecretStr("my-secret-value"))

    # 序列化不带上下文（默认 = 已脱敏）
    data = secret.model_dump(mode="json")

    # 验证已脱敏 - Pydantic 返回 JSON 模式的 SecretStr repr，即“**********”（默认
    # SecretStr repr）
    #
    assert data["secret"] == REDACTED_SECRET_VALUE


def test_real_pydantic_nested_secrets_roundtrip(cipher):
    """测试机密模型中嵌套机密的加密。"""
    from openhands.agent_server.persistence.models import CustomSecret, Secrets

    # 使用多个自定义机密创建机密
    secrets = Secrets(
        custom_secrets={
            "API_KEY": CustomSecret(
                name="API_KEY", secret=SecretStr("sk-123"), description="API key"
            ),
            "DB_PASS": CustomSecret(
                name="DB_PASS",
                secret=SecretStr("password123"),
                description="DB password",
            ),
        }
    )

    # 序列化带密码（加密所有机密）
    data = secrets.model_dump(mode="json", context={"cipher": cipher})

    # 验证所有机密均已加密
    for name in ["API_KEY", "DB_PASS"]:
        assert data["custom_secrets"][name]["secret"] not in [
            "sk-123",
            "password123",
            REDACTED_SECRET_VALUE,
        ]

    # 验证（解密）所有机密
    restored = Secrets.model_validate(data, context={"cipher": cipher})
    assert restored.custom_secrets["API_KEY"].secret is not None
    assert restored.custom_secrets["API_KEY"].secret.get_secret_value() == "sk-123"
    assert restored.custom_secrets["DB_PASS"].secret is not None
    assert restored.custom_secrets["DB_PASS"].secret.get_secret_value() == "password123"


def test_real_pydantic_persisted_settings_roundtrip(cipher):
    """使用加密的 LLM api_key 测试 PersistedSettings 序列化。

    这测试了主要用例：完整的 PersistedSettings，agent_settings.llm.api_key 已加密且往
    返。
    """
    from openhands.agent_server.persistence.models import PersistedSettings

    # 使用机密创建设置
    settings = PersistedSettings()
    assert isinstance(settings.agent_settings, OpenHandsAgentSettings)
    settings.agent_settings.llm.api_key = SecretStr("sk-test-key-12345")

    # 序列化带密码
    data = settings.model_dump(mode="json", context={"cipher": cipher})
    encrypted_key = data["agent_settings"]["llm"]["api_key"]

    # 应该加密（不是明文，不是已脱敏）
    assert encrypted_key != "sk-test-key-12345"
    assert encrypted_key != REDACTED_SECRET_VALUE

    # 反序列化（解密）
    restored = PersistedSettings.model_validate(data, context={"cipher": cipher})
    assert isinstance(restored.agent_settings, OpenHandsAgentSettings)
    restored_key = restored.agent_settings.llm.api_key
    assert restored_key is not None
    assert isinstance(restored_key, SecretStr)
    assert restored_key.get_secret_value() == "sk-test-key-12345"


# ── decrypt_str_with_cipher_or_keep / validate_secret_dict 测试 ────────


def test_decrypt_str_with_cipher_or_keep_decrypts_fernet_token(cipher):
    encrypted = cipher.encrypt(SecretStr("plaintext-value"))
    assert encrypted is not None
    assert (
        decrypt_str_with_cipher_or_keep(cipher, encrypted, description="x")
        == "plaintext-value"
    )


def test_decrypt_str_with_cipher_or_keep_passes_through_non_string(cipher):
    """非字符串 (e.g. 嵌套 SecretSource dicts) 必须不变地通过。

    针对原始字典调用字符串字典助手
    mode='before' time, so values that haven't been deserialised yet
    (e.g. SecretSource 载荷表示为字典）不得被视为加密的 blob。
    """
    assert decrypt_str_with_cipher_or_keep(cipher, 42, description="x") == 42
    assert decrypt_str_with_cipher_or_keep(cipher, None, description="x") is None
    assert decrypt_str_with_cipher_or_keep(
        cipher, {"nested": "dict"}, description="x"
    ) == {"nested": "dict"}


def test_decrypt_str_with_cipher_or_keep_passes_through_legacy_plaintext(cipher):
    """来自早于加密管道的客户端的明文必须
    仍然干净地往返，以便下次保存可以重新加密它。"""
    assert (
        decrypt_str_with_cipher_or_keep(cipher, "sk-plaintext", description="x")
        == "sk-plaintext"
    )


def test_decrypt_str_with_cipher_or_keep_warns_on_undecryptable(cipher, caplog):
    """具有正确前缀的乱码密文不应崩溃 -
    记录警告并返回原件，以便操作员进行维修。"""
    bogus = "gAAAAA" + ("x" * 80)
    with caplog.at_level("WARNING"):
        result = decrypt_str_with_cipher_or_keep(cipher, bogus, description="ACP env")
    assert result == bogus
    assert any("could not be decrypted" in r.message for r in caplog.records)
    assert any("ACP env" in r.message for r in caplog.records)


def test_validate_secret_dict_decrypts_each_value(cipher, mock_info):
    encrypted_a = cipher.encrypt(SecretStr("alpha"))
    encrypted_b = cipher.encrypt(SecretStr("beta"))
    info = mock_info({"cipher": cipher})
    result = validate_secret_dict(
        {"A": encrypted_a, "B": encrypted_b}, info, description="x"
    )
    assert result == {"A": "alpha", "B": "beta"}


def test_validate_secret_dict_without_cipher_is_a_noop(mock_info):
    info = mock_info(None)
    payload = {"A": "ciphertext-shaped-but-no-cipher-to-decrypt"}
    assert validate_secret_dict(payload, info, description="x") == payload


def test_validate_secret_dict_passes_through_non_dict(cipher, mock_info):
    info = mock_info({"cipher": cipher})
    # 让下游 Pydantic 引发规范的“预期字典”错误，而不是将其转换为 TypeError 。
    #
    assert validate_secret_dict("not-a-dict", info, description="x") == "not-a-dict"
    assert validate_secret_dict(None, info, description="x") is None


# ── 严格解密（读-修改-写路径）──────────────────────────


def test_validate_secret_strict_raises_on_wrong_cipher(mock_info, cipher):
    token = cipher.encrypt(SecretStr("sk-test-123"))
    wrong = Cipher("another-key")
    lenient = mock_info({"cipher": wrong})
    strict = mock_info({"cipher": wrong, STRICT_DECRYPT_CONTEXT_KEY: True})

    assert validate_secret(token, lenient) is None
    with pytest.raises(SecretDecryptionError) as exc_info:
        validate_secret(token, strict)
    assert FERNET_TOKEN_PREFIX not in str(exc_info.value)


def test_validate_secret_dict_strict_raises_on_wrong_cipher(mock_info, cipher):
    token = cipher.encrypt(SecretStr("env-value"))
    wrong = Cipher("another-key")
    value = {"API_TOKEN": token, "PLAIN": "kept"}
    lenient = mock_info({"cipher": wrong})
    strict = mock_info({"cipher": wrong, STRICT_DECRYPT_CONTEXT_KEY: True})

    assert validate_secret_dict(value, lenient) == value
    with pytest.raises(SecretDecryptionError) as exc_info:
        validate_secret_dict(value, strict, description="MCP env")
    assert FERNET_TOKEN_PREFIX not in str(exc_info.value)
    # 匹配的密码仍以严格模式解密。
    ok = mock_info({"cipher": cipher, STRICT_DECRYPT_CONTEXT_KEY: True})
    assert validate_secret_dict(value, ok) == {
        "API_TOKEN": "env-value",
        "PLAIN": "kept",
    }


def test_strict_decrypt_accepts_a_previous_key(mock_info):
    token = Cipher("old-key").encrypt(SecretStr("sk-test-123"))
    rotated = Cipher("new-key", previous_keys=["old-key"])
    strict = mock_info({"cipher": rotated, STRICT_DECRYPT_CONTEXT_KEY: True})

    result = validate_secret(token, strict)
    assert result is not None
    assert result.get_secret_value() == "sk-test-123"
    assert validate_secret_dict({"T": token}, strict) == {"T": "sk-test-123"}


def test_strict_decrypt_error_names_previous_keys(mock_info):
    token = Cipher("old-key").encrypt(SecretStr("sk-test-123"))
    strict = mock_info({"cipher": Cipher("new-key"), STRICT_DECRYPT_CONTEXT_KEY: True})
    with pytest.raises(SecretDecryptionError, match="OH_PREVIOUS_SECRET_KEYS"):
        validate_secret(token, strict)


def test_serialize_secret_rotates_a_token_under_a_previous_key(mock_info):
    old_token = Cipher("old-key").encrypt(SecretStr("sk-test-123"))
    assert old_token is not None
    rotated = Cipher("new-key", previous_keys=["old-key"])

    out = serialize_secret(SecretStr(old_token), mock_info({"cipher": rotated}))
    assert isinstance(out, str)
    assert out != old_token
    assert Cipher("new-key").try_decrypt_str(out) == "sk-test-123"
    # 当前键下已有的 token 保持原样。
    assert serialize_secret(SecretStr(out), mock_info({"cipher": rotated})) == out
