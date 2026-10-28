"""持久化用于共享 LLM 提供商连接。

* 提供者连接 * 是一个小的、命名的凭据材料包，LLM 配置文件否则会内联：一个 ``api_key``
 和一个可选的
``base_url``. 多个 LLM 配置文件可以通过 id 引用一个连接，因此在一个位置旋转共享密钥会
更新指向它的每个配置文件。

它故意存在于 SDK 中 — :class:`LLMProfileStore` 旁边。 ``provider_connection_id`` 会解
析为凭据（见：meth:
`LLMProfileStore.load`），只有当连接存储从同一层可达时，它才能做到这一点。 将它保留在
这里（而不是在智能体-服务器上）意味着，任何将存储的凭据转换为可
运行的：class:`~openhands.sdk.llm.llm.LLM` — 命名凭据激活的路径
*和 * 默认/种子启动路径 — 解析相同。

的凭据在加密 REST 使用相同的加密机制 LLM 因此，连接文件中永远不会存储明文密钥
``OH_SECRET_KEY`` 已配置。
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from filelock import FileLock, Timeout
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_serializer,
    field_validator,
)

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.pydantic_secrets import is_redacted_secret, serialize_secret


if TYPE_CHECKING:
    from openhands.sdk.utils.cipher import Cipher


_DEFAULT_DIR: Final[Path] = Path.home() / ".openhands" / "provider-connections"
_FILENAME: Final[str] = "provider_connections.json"
_LOCK_TIMEOUT_SECONDS: Final[float] = 30.0

PROVIDER_CONNECTIONS_SCHEMA_VERSION: Final[int] = 1
MAX_PROVIDER_CONNECTIONS: Final[int] = 64

# 连接 ID：1-128 个字符，字母数字开头，然后是字母数字/._-。 与配置文件名称形状相同 - 块
# 路径分隔符和前导点。
#
CONNECTION_ID_PATTERN: Final[str] = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
CONNECTION_ID_REGEX: Final[re.Pattern[str]] = re.compile(CONNECTION_ID_PATTERN)

logger = get_logger(__name__)


class ProviderConnectionLimitExceeded(Exception):
    """创建连接将超出配置的限制时引发。"""


class ProviderConnectionNotFound(ValueError):
    """引用的提供程序连接 ID 不存在。

    当配置文件指向已删除的连接并且该配置文件没有可用的内联键可供依赖时，由：meth:
    `LLMProfileStore.load` 引发。

    子类：class:`ValueError` 因此，即使没有专用的 ``except``，每个 ``load()`` 调用者
    也会明显降级。 配置文件激活和设置端点（通
    过 ``store_errors``）将其映射到 422，OpenAI 兼容网关的 ``except ValueError`` 将其
    转换为 400 而不是不透明
    500. 智能体-配置文件启动路径已经通过以下方式汇集了加载失败
    其解析器的 ``ValueError`` 处理； 该路径实际上无法命中悬空引用，因为当任何配置文件
    指向该连接时，删除引用的连接都会被阻止。
    """


class ProviderConnection(BaseModel):
    """由一个或多个 LLM 配置文件重复使用的共享凭据捆绑包。"""

    id: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=128)
    provider: str = Field(default="custom", min_length=1, max_length=128)
    api_key: SecretStr | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    created_at: int = Field(..., description="Unix epoch seconds.")
    updated_at: int = Field(..., description="Unix epoch seconds.")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("api_key", mode="before")
    @classmethod
    def _validate_api_key(cls, v: str | SecretStr | None, info) -> SecretStr | None:
        # 提供者连接使用严格的解密路径：无法解密的 Fernet 加密密钥会升高，而不是默默地变
        # 为 None。 错误的密码读取→修改→写入将重写集合
        #
        # with api_key=null, permanently destroying the stored ciphertext.
        from openhands.sdk.utils.cipher import FERNET_TOKEN_PREFIX

        if v is None:
            return None
        secret_value = v.get_secret_value() if isinstance(v, SecretStr) else v
        if (
            not secret_value
            or not secret_value.strip()
            or is_redacted_secret(secret_value)
        ):
            return None
        cipher = (info.context or {}).get("cipher")
        if cipher is not None and secret_value.startswith(FERNET_TOKEN_PREFIX):
            decrypted = cipher.decrypt(secret_value)
            if decrypted is None:
                raise ValueError(
                    "api_key is encrypted but cannot be decrypted with the current "
                    "cipher. Verify that OH_SECRET_KEY matches the key used when "
                    "this connection was saved."
                )
            return decrypted
        return v if isinstance(v, SecretStr) else SecretStr(secret_value)

    @field_serializer("api_key", when_used="always")
    def _serialize_api_key(self, v: SecretStr | None, info):
        return serialize_secret(v, info)

    def api_key_value(self) -> str | None:
        """返回明文密钥，如果未设置/为空，则返回 ``None``。"""
        if self.api_key is None:
            return None
        value = self.api_key.get_secret_value()
        return value if value.strip() else None


class PersistedProviderConnections(BaseModel):
    """保存的提供者连接文件的容器。"""

    schema_version: int = Field(default=PROVIDER_CONNECTIONS_SCHEMA_VERSION)
    connections: list[ProviderConnection] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ProviderConnectionStore:
    """用于共享 LLM 提供者连接的文件支持存储。

    所有连接都位于由文件锁保护的单个 JSON 文件中，因此并发进程中的创建/更新/删除调用
    是已序列化。 的
    当提供密码时，每个连接的 ``api_key`` 在 REST 处加密，匹配：class:
    `LLMProfileStore` 的机密处理。
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else _DEFAULT_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._path = self.base_dir / _FILENAME
        self._file_lock = FileLock(self.base_dir / ".provider-connections.lock")

    @contextmanager
    def _acquire_lock(self, timeout: float = _LOCK_TIMEOUT_SECONDS) -> Iterator[None]:
        try:
            with self._file_lock.acquire(timeout=timeout):
                yield
        except Timeout:
            logger.error(
                f"[Provider Connections] Failed to acquire lock within {timeout}s"
            )
            raise TimeoutError(
                f"Provider connection store lock acquisition timed out after {timeout}s"
            )

    def _read(self, *, cipher: Cipher | None) -> PersistedProviderConnections:
        """读取文件而不加锁。 丢失文件 -> 空容器。

        损坏的文件会引发 ``ValueError``，而不是被静默替换，因此错误的密钥或截断的写入
        永远不会破坏存储的凭据。
        """
        if not self._path.exists():
            return PersistedProviderConnections()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"Provider connections file is unreadable: {e}") from e
        if not isinstance(raw, dict):
            raise ValueError("Provider connections file must contain a JSON object")
        version = raw.get("schema_version", PROVIDER_CONNECTIONS_SCHEMA_VERSION)
        if not isinstance(version, int):
            raise ValueError("schema_version must be an integer")
        if version > PROVIDER_CONNECTIONS_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {version} is newer than supported "
                f"{PROVIDER_CONNECTIONS_SCHEMA_VERSION}"
            )
        raw["schema_version"] = PROVIDER_CONNECTIONS_SCHEMA_VERSION
        context = {"cipher": cipher} if cipher else None
        return PersistedProviderConnections.model_validate(raw, context=context)

    def _write(
        self, persisted: PersistedProviderConnections, *, cipher: Cipher | None
    ) -> None:
        context: dict[str, Any] = {}
        if cipher is not None:
            context["cipher"] = cipher
            context["expose_secrets"] = "encrypted"
        else:
            context["expose_secrets"] = True
        data = persisted.model_dump(mode="json", context=context)
        payload = json.dumps(data, indent=2)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=self.base_dir, suffix=".tmp", delete=False
        ) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        try:
            Path.replace(tmp_path, self._path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def list(self, *, cipher: Cipher | None = None) -> list[ProviderConnection]:
        with self._acquire_lock():
            return list(self._read(cipher=cipher).connections)

    def get(
        self, connection_id: str, *, cipher: Cipher | None = None
    ) -> ProviderConnection | None:
        with self._acquire_lock():
            for connection in self._read(cipher=cipher).connections:
                if connection.id == connection_id:
                    return connection
        return None

    def create(
        self, connection: ProviderConnection, *, cipher: Cipher | None = None
    ) -> ProviderConnection:
        if not CONNECTION_ID_REGEX.match(connection.id):
            raise ValueError(f"Invalid provider connection id: {connection.id!r}")
        with self._acquire_lock():
            persisted = self._read(cipher=cipher)
            if any(c.id == connection.id for c in persisted.connections):
                raise ValueError(
                    f"Provider connection {connection.id!r} already exists"
                )
            if len(persisted.connections) >= MAX_PROVIDER_CONNECTIONS:
                raise ProviderConnectionLimitExceeded(
                    f"Provider connection limit reached ({MAX_PROVIDER_CONNECTIONS})."
                )
            persisted.connections.append(connection)
            self._write(persisted, cipher=cipher)
        logger.info(
            "[Provider Connections] Created connection",
            extra={"connection_id": connection.id},
        )
        return connection

    def update(
        self, connection: ProviderConnection, *, cipher: Cipher | None = None
    ) -> ProviderConnection:
        with self._acquire_lock():
            persisted = self._read(cipher=cipher)
            if not any(c.id == connection.id for c in persisted.connections):
                raise ProviderConnectionNotFound(connection.id)
            persisted.connections = [
                connection if c.id == connection.id else c
                for c in persisted.connections
            ]
            self._write(persisted, cipher=cipher)
        logger.info(
            "[Provider Connections] Updated connection",
            extra={"connection_id": connection.id},
        )
        return connection

    def delete(self, connection_id: str, *, cipher: Cipher | None = None) -> None:
        with self._acquire_lock():
            persisted = self._read(cipher=cipher)
            remaining = [c for c in persisted.connections if c.id != connection_id]
            if len(remaining) == len(persisted.connections):
                raise ProviderConnectionNotFound(connection_id)
            persisted.connections = remaining
            self._write(persisted, cipher=cipher)
        logger.info(
            "[Provider Connections] Deleted connection",
            extra={"connection_id": connection_id},
        )
