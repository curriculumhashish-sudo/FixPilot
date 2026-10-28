import logging
from collections.abc import Mapping
from typing import Any, Final, Literal, overload

from pydantic import SecretStr, ValidationInfo

from openhands.sdk.utils.cipher import FERNET_TOKEN_PREFIX, Cipher


REDACTED_SECRET_VALUE = "**********"

# 输入 expose_secrets 上下文值
ExposeSecretsMode = Literal["encrypted", "plaintext"] | bool

ResolvedExposeMode = Literal["plaintext", "encrypted", "redact"]

_logger = logging.getLogger(__name__)


class MissingCipherError(ValueError):
    """当请求加密而不使用密码时，将引发 ``serialize_secret``。"""


# 验证-上下文标志：当 True、``validate_secret`` 升高时
# ``SecretDecryptionError`` 对于 Fernet token，密码无法解密，而不是返回 ``None``。 读取-
# 修改-写入路径对其进行设置，以便更改密钥下的写入无法持久化 ``null`` 覆盖存储的密文。
#
STRICT_DECRYPT_CONTEXT_KEY: Final[str] = "strict_decrypt"


# 对于没有配置的密钥可以解密的存储值的操作员指南。
UNDECRYPTABLE_SECRET_HINT: Final[str] = (
    "It was saved under a key that is neither OH_SECRET_KEY nor in "
    "OH_PREVIOUS_SECRET_KEYS: restore that key as OH_SECRET_KEY, or add it to "
    "OH_PREVIOUS_SECRET_KEYS to rotate to the current key."
)


class SecretDecryptionError(Exception):
    """存储的机密无法使用当前密码解密。

    故意不是 ``ValueError``: Pydantic 让它按原样传播，而不是将其包装在与 token 相呼应
    的 ``ValidationError`` 中。
    """


def resolve_expose_mode(context: Mapping[str, Any] | None) -> ResolvedExposeMode:
    """将 Pydantic 上下文解析为明文/加密/编辑。

    密码的存在意味着 ``"encrypted"``（存储路径选择），除非
    ``expose_secrets`` 覆盖。
    """
    if not context:
        return "redact"
    expose_mode = context.get("expose_secrets")
    if expose_mode == "plaintext" or expose_mode is True:
        return "plaintext"
    if expose_mode == "encrypted" or context.get("cipher") is not None:
        return "encrypted"
    return "redact"


def is_redacted_secret(v: str | SecretStr | None) -> bool:
    if v is None:
        return False
    if isinstance(v, SecretStr):
        return v.get_secret_value() == REDACTED_SECRET_VALUE
    return v == REDACTED_SECRET_VALUE


def serialize_secret(v: SecretStr | None, info):
    """
    序列化机密已加密、明文公开的字段或脱敏。

    上下文选项：
    - ``cipher``：如果提供，则加密机密值（优先）
    - ``expose_secrets``：控制机密的暴露方式：
      - ``"encrypted"``：使用上下文中的密码进行加密（需要密码）
      - ``"plaintext"``或``True``：公开实际值（仅后端使用）
      - ``False`` 或不存在：让 Pydantic 处理默认屏蔽 (脱敏)

    ``"encrypted"`` 模式对于前端客户端来说是安全的，因为它们无法解密。
    ``"plaintext"`` 模式只能由受信任的后端客户端使用。
    """
    if v is None:
        return None

    mode = resolve_expose_mode(info.context)

    if mode == "plaintext":
        return v.get_secret_value()

    if mode == "encrypted":
        cipher: Cipher | None = info.context.get("cipher") if info.context else None
        if cipher is None:
            raise MissingCipherError(
                "Cannot encrypt secret: no cipher configured. "
                "Set OH_SECRET_KEY environment variable."
            )
        raw = v.get_secret_value()
        if raw.startswith(FERNET_TOKEN_PREFIX) and cipher.try_decrypt_str(raw):
            # 已经是token：保留它，当只有以前的密钥可以读取它时，用当前密钥重新加密。
            #
            return cipher.rotate(raw) or raw
        return cipher.encrypt(v)

    return v


def validate_secret(v: str | SecretStr | None, info) -> SecretStr | None:
    """
    反序列化机密字段，处理加密和空值。

    接受字符串和SecretStr输入，总是返回SecretStr | None。
    - 空的机密转换为None
    - 普通字符串转换为 SecretStr
    - 如果上下文中提供了密码并且该值为 Fernet token，则尝试解密该值
    - 如果 Fernet 解密失败，密码将返回 None 并记录警告； 上下文中的
    ``strict_decrypt`` 会引发
    SecretDecryptionError
    - 非-token 字符串作为明文通过，用于 legacy 设置 PATCHes
    - 它优雅地处理使用不同密钥加密的对话或已脱敏
    """  # noqa: E501
    if v is None:
        return None

    # 处理 SecretStr 和字符串输入
    if isinstance(v, SecretStr):
        secret_value = v.get_secret_value()
    else:
        secret_value = v

    # 如果机密为空、仅包含空格或已脱敏 - 返回 None
    if not secret_value or not secret_value.strip() or is_redacted_secret(secret_value):
        return None

    # 检查是否提供了密码并且该值是加密的 Fernet token。 不应仅仅因为存储层配置了加密就丢
    # 弃旧的明文设置和普通的 PATCH 载荷。
    #
    if (
        info.context
        and info.context.get("cipher")
        and secret_value.startswith(FERNET_TOKEN_PREFIX)
    ):
        cipher: Cipher = info.context.get("cipher")
        decrypted = cipher.decrypt(secret_value)
        if decrypted is None and info.context.get(STRICT_DECRYPT_CONTEXT_KEY):
            raise SecretDecryptionError(
                "A stored secret cannot be decrypted with any configured key. "
                + UNDECRYPTABLE_SECRET_HINT
            )
        return decrypted

    # 始终返回 SecretStr
    if isinstance(v, SecretStr):
        return v
    else:
        return SecretStr(secret_value)


@overload
def decrypt_str_with_cipher_or_keep(
    cipher: Cipher, value: str, *, description: str = ...
) -> str: ...


@overload
def decrypt_str_with_cipher_or_keep(
    cipher: Cipher, value: Any, *, description: str = ...
) -> Any: ...


def decrypt_str_with_cipher_or_keep(
    cipher: Cipher,
    value: Any,
    *,
    description: str = "secret",
) -> Any:
    """就地解密单个 Fernet 加密字符串。

    当值不是字符串、看起来不是 Fernet token (来自预加密管道的旧客户端的纯文本) 或者无
    法解密 (密钥不匹配 / token 损坏 — 登记以便操作员修复
    而不是对象在构造时死亡) 时，返回不变。

    机密基块，包含 `agent_context.secrets` 和 MCP 服务器 `env`/`headers`) 的字典字段
    ，每个值都是单独加密的，以 REST
     为键的密文。它们不能像 `SecretStr` 类那样输入，因为它们的键是用户提供的。
    """
    if not isinstance(value, str):
        return value
    if not value.startswith(FERNET_TOKEN_PREFIX):
        return value
    decrypted = cipher.try_decrypt_str(value)
    if decrypted is None:
        _logger.warning(
            "%s value looks encrypted but could not be decrypted "
            "(cipher mismatch or corruption); leaving the ciphertext in place.",
            description,
        )
        return value
    return decrypted


def validate_secret_dict(
    value: Any,
    info: ValidationInfo,
    *,
    description: str = "secret",
) -> Any:
    """解密 ``dict[str, str]`` 字段中的每个 Fernet 加密条目。

    镜像：func:`validate_secret` 用于机密值位于每个键字典中的字段（env-var 映射、标头
    映射、智能体-上下文机密）。 用作
    ``field_validator(mode="before")`` 挂钩：

    .. 代码块：: Python

        @field_validator("env", mode="before")
        @classmethod
        def _decrypt_env(cls, value, info):
            return validate_secret_dict(value, info, description="MCP env")

    当字段不是字典时，不做任何操作（下游验证引发默认类型错误），以及当上下文中没有加
    密时（旧的明文调用者或已经解密的上下文）。
    """
    if not isinstance(value, dict):
        return value
    context = info.context or {}
    cipher: Cipher | None = context.get("cipher")
    if cipher is None:
        return value
    if context.get(STRICT_DECRYPT_CONTEXT_KEY):
        for v in value.values():
            if (
                isinstance(v, str)
                and v.startswith(FERNET_TOKEN_PREFIX)
                and cipher.try_decrypt_str(v) is None
            ):
                raise SecretDecryptionError(
                    f"A stored {description} value cannot be decrypted with any "
                    "configured key. " + UNDECRYPTABLE_SECRET_HINT
                )
    return {
        k: decrypt_str_with_cipher_or_keep(cipher, v, description=description)
        for k, v in value.items()
    }
