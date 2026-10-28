"""机密用于处理敏感数据的来源和类型。"""

import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import Field, SecretStr, field_serializer, field_validator

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.models import DiscriminatedUnionMixin
from openhands.sdk.utils.pydantic_secrets import (
    is_redacted_secret,
    serialize_secret,
    validate_secret,
)
from openhands.sdk.utils.redact import is_secret_key


logger = get_logger(__name__)

_INTERNAL_SERVER_URL_ENV = "OH_INTERNAL_SERVER_URL"
_DEFAULT_INTERNAL_SERVER_URL = "http://127.0.0.1:8000"


def _resolve_lookup_secret_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.netloc or parsed.scheme:
        return url

    base_url = os.getenv(_INTERNAL_SERVER_URL_ENV, _DEFAULT_INTERNAL_SERVER_URL)
    return urljoin(f"{base_url.rstrip('/')}/", url)


LocalSecretResolver = Callable[[str], str | None]

_local_secret_resolvers: list[LocalSecretResolver] = []


def register_local_secret_resolver(resolver: LocalSecretResolver) -> None:
    """注册一个 ``LookupSecret`` URLs 在线解析器。

    既是服务者又是消费者的过程 ``LookupSecret``  URLs — an 智能体- 服务器正在运行一个
    在进程中的对话，比如 — 无法从中获取它们 HTTP
     从自身事件循环： 请求只能由等待它的人阻塞的循环来回答，因此它会阻塞直到客户端超
     时。 注册一个解析器可以让这种过程回答自己 URLs 直接跳过往返。

    解析器接收完全解析的URL，返回机密值，或``None``当它不提供该URL时，此时解析继续向
    下到下一个解析器，最终到达HTTP。
    """
    if resolver not in _local_secret_resolvers:
        _local_secret_resolvers.append(resolver)


def unregister_local_secret_resolver(resolver: LocalSecretResolver) -> None:
    """删除使用 ``register_local_secret_resolver`` 注册的解析器。"""
    if resolver in _local_secret_resolvers:
        _local_secret_resolvers.remove(resolver)


def _resolve_secret_locally(url: str) -> str | None:
    """返回 ``url`` 的本地服务值，如果存在 None，则返回 ``None``。"""
    for resolver in list(_local_secret_resolvers):
        try:
            value = resolver(url)
        except Exception:
            logger.warning(
                "Local secret resolver raised; falling back to HTTP", exc_info=True
            )
            continue
        if value is not None:
            return value
    return None


class SecretSource(DiscriminatedUnionMixin, ABC):
    """可以动态获取的命名机密的源"""

    description: str | None = Field(
        default=None,
        description="Optional description for this secret",
    )

    @abstractmethod
    def get_value(self) -> str | None:
        """获取纯文本形式的机密的值"""


class StaticSecret(SecretSource):
    """A 机密存储在本地"""

    value: SecretStr | None = None

    def get_value(self) -> str | None:
        if self.value is None:
            return None
        return self.value.get_secret_value()

    @field_validator("value")
    @classmethod
    def _validate_secrets(cls, v: SecretStr | None, info):
        return validate_secret(v, info)

    @field_serializer("value", when_used="always")
    def _serialize_secrets(self, v: SecretStr | None, info):
        return serialize_secret(v, info)


class LookupSecret(SecretSource):
    """A 机密从某个外部 url 查找"""

    url: str
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def _normalize_url(cls, url: str) -> str:
        return _resolve_lookup_secret_url(url)

    def get_value(self) -> str:
        local_value = _resolve_secret_locally(self.url)
        if local_value is not None:
            return local_value
        response = httpx.get(self.url, headers=self.headers, timeout=30.0)
        response.raise_for_status()
        return response.text

    @field_validator("headers")
    @classmethod
    def _validate_secrets(cls, headers: dict[str, str], info):
        result = {}
        for key, value in headers.items():
            if not is_secret_key(key):
                result[key] = value
                continue

            # 预先删除空/已脱敏标头值； 无论密码状态如何，它们都不携带可用的身份验证材料
            # 。
            #
            if not value or not value.strip() or is_redacted_secret(value):
                logger.debug(f"Skipping redacted header '{key}' during deserialization")
                continue

            secret_value = validate_secret(SecretStr(value), info)
            if secret_value is None:
                # 当验证上下文中提供了密码但解密失败时，validate_secret 仅针对非空输入返
                # 回 None。 当调用者 (e.g. 前端正在构建一个 LookupSecret 发送纯文本认证
                # 头，但请求的其他部分被标记为包含加密机密。 保留原始值而不是默默地删除
                # 标头 - 调用者对标头的意图始终是纯文本身份验证元数据。
                #
                logger.debug(
                    f"Header '{key}' could not be decrypted; "
                    "treating value as plaintext"
                )
                result[key] = value
            else:
                result[key] = secret_value.get_secret_value()
        return result

    @field_serializer("headers", when_used="always")
    def _serialize_secrets(self, headers: dict[str, str], info):
        result = {}
        for key, value in headers.items():
            if is_secret_key(key):
                secret_value = serialize_secret(SecretStr(value), info)
                if secret_value is None:
                    logger.debug(
                        f"Skipping redacted header '{key}' during serialization"
                    )
                    continue
                result[key] = secret_value
            else:
                result[key] = value
        return result


# 机密值的类型别名 - 可以是纯字符串或 SecretSource
SecretValue = str | SecretSource
