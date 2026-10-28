"""用于跨配置文件共享 LLM 凭据的提供商连接端点。

提供者连接是一个共享的 ``api_key`` + 可选的 ``base_url``，一个或多个 LLM 配置文件通过
 id 引用。 凭据被解析为可运行的
:class:`~openhands.sdk.llm.llm.LLM` 在配置文件加载时延迟
(:meth:`LLMProfileStore.load`) — 该路由器仅通过存储的连接执行 CRUD。 由于分辨率是在使
用时读取的，因此此处旋转密钥将在下次激活或启动链
接的配置文件时生效； 没有任何内容被复制到活动设置中，因此没有单独的刷新路径可以保留在
同步中。
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from openhands.agent_server._secrets_exposure import (
    get_cipher,
    get_config,
    store_errors,
)
from openhands.agent_server.persistence import (
    ProviderConnection,
    get_llm_profile_store,
    get_provider_connections_store,
    get_settings_store,
)
from openhands.sdk.llm.provider_connection_store import (
    ProviderConnectionLimitExceeded,
    ProviderConnectionNotFound,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.settings import OpenHandsAgentSettings
from openhands.sdk.utils.pydantic_secrets import is_redacted_secret


logger = get_logger(__name__)

provider_connections_router = APIRouter(
    prefix="/llm/provider-connections", tags=["LLM Provider Connections"]
)


def _now() -> int:
    return int(time.time())


def _require_usable_api_key(v: SecretStr | None) -> SecretStr | None:
    # 存储的模型将空白或已脱敏密钥转换为 None，因此接受该模型将创建无密钥连接 (POST) 或
    # 擦除/损坏共享密钥 (PATCH)。 预先拒绝； 消息不得回显该值。
    #
    if v is not None and (not v.get_secret_value().strip() or is_redacted_secret(v)):
        raise ValueError("api_key must be a real key, not blank or redacted")
    return v


class ProviderConnectionCreateRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=128)
    provider: str = Field(default="custom", min_length=1, max_length=128)
    api_key: SecretStr = Field(..., min_length=1)
    base_url: str | None = Field(default=None, max_length=2048)

    model_config = ConfigDict(extra="forbid")

    _validate_api_key = field_validator("api_key")(_require_usable_api_key)


class ProviderConnectionUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=128)
    api_key: SecretStr | None = None
    base_url: str | None = Field(default=None, max_length=2048)

    model_config = ConfigDict(extra="forbid")

    _validate_api_key = field_validator("api_key")(_require_usable_api_key)

    @model_validator(mode="after")
    def _reject_null_required_fields(self) -> ProviderConnectionUpdateRequest:
        # 仅 `base_url` 可以设置为 null（将其清除）。 `display_name` 和
        # `provider` 需要在存储模型中指定。 在 PATCH 上接受显式的 null 会导致持久化 a
        # null 毒害每个后续的存储读取。
        #
        for field in ("display_name", "provider"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be set to null")
        return self


class ProviderConnectionResponse(BaseModel):
    id: str
    display_name: str
    provider: str
    base_url: str | None = None
    created_at: int
    updated_at: int
    api_key_set: bool = False


def _to_response(connection: ProviderConnection) -> ProviderConnectionResponse:
    return ProviderConnectionResponse(
        id=connection.id,
        display_name=connection.display_name,
        provider=connection.provider,
        base_url=connection.base_url,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
        api_key_set=connection.api_key_value() is not None,
    )


def _linked_profile_names(connection_id: str) -> list[str]:
    return sorted(
        str(summary["name"])
        for summary in get_llm_profile_store().list_summaries()
        if summary.get("provider_connection_id") == connection_id
    )


def _active_settings_references_connection(config, connection_id: str) -> bool:
    settings = get_settings_store(config).load()
    if settings is None or not isinstance(
        settings.agent_settings, OpenHandsAgentSettings
    ):
        return False
    return settings.agent_settings.llm.provider_connection_id == connection_id


def _raise_if_connection_is_referenced(config, connection_id: str) -> None:
    """当任何配置文件或活动设置仍指向此处时阻止删除。

    删除引用的连接会使这些引用悬空； 没有内联键的链接配置文件会在下次加载时引发。 因
    此删除将被拒绝，直到首先删除引用。
    """
    profile_names = _linked_profile_names(connection_id)
    active_reference = _active_settings_references_connection(config, connection_id)
    if not profile_names and not active_reference:
        return

    reasons = []
    if profile_names:
        reasons.append(f"referenced by LLM profile(s): {', '.join(profile_names)}")
    if active_reference:
        reasons.append("referenced by the active agent settings")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "Provider connection cannot be deleted while it is "
            + " and ".join(reasons)
            + ". Update those references before deleting it."
        ),
    )


@provider_connections_router.get("", response_model=list[ProviderConnectionResponse])
def list_provider_connections(
    request: Request,
) -> list[ProviderConnectionResponse]:
    cipher = get_cipher(request)
    store = get_provider_connections_store(get_config(request))
    with store_errors():
        connections = store.list(cipher=cipher)
    return [_to_response(c) for c in connections]


@provider_connections_router.post(
    "", response_model=ProviderConnectionResponse, status_code=status.HTTP_201_CREATED
)
def create_provider_connection(
    request: Request, body: ProviderConnectionCreateRequest
) -> ProviderConnectionResponse:
    cipher = get_cipher(request)
    store = get_provider_connections_store(get_config(request))
    now = _now()
    connection = ProviderConnection(
        id=uuid.uuid4().hex,
        display_name=body.display_name,
        provider=body.provider,
        api_key=body.api_key,
        base_url=body.base_url,
        created_at=now,
        updated_at=now,
    )
    try:
        with store_errors():
            store.create(connection, cipher=cipher)
    except ProviderConnectionLimitExceeded as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{e} Delete one before adding another.",
        )
    logger.info(
        "Created LLM provider connection", extra={"connection_id": connection.id}
    )
    return _to_response(connection)


@provider_connections_router.patch(
    "/{connection_id}", response_model=ProviderConnectionResponse
)
def update_provider_connection(
    request: Request, connection_id: str, body: ProviderConnectionUpdateRequest
) -> ProviderConnectionResponse:
    fields = body.model_fields_set
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one provider connection field to update",
        )

    cipher = get_cipher(request)
    store = get_provider_connections_store(get_config(request))
    with store_errors():
        connection = store.get(connection_id, cipher=cipher)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider connection '{connection_id}' not found",
        )

    # 连接必须始终有一个密钥，因此清除它不是有效的更新。 明确拒绝 api_key: null，而不是
    # 默默地丢弃它。
    #
    if "api_key" in fields and body.api_key is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="api_key cannot be cleared; provide a new key to rotate it",
        )

    updates: dict[str, Any] = {"updated_at": _now()}
    for field in ("display_name", "provider", "base_url"):
        if field in fields:
            updates[field] = getattr(body, field)
    if "api_key" in fields:
        updates["api_key"] = body.api_key
    updated = connection.model_copy(update=updates)

    # store_errors() 映射基础设施故障 (锁超时 -> 503, 未正确加密/错误的密钥文件 -> 4xx)
    # 。 内部 except 将删除之间的获取和更新竞赛保留为 404，而不是 422 store_errors 给出
    # 的 ProviderConnectionNotFound。
    #
    with store_errors():
        try:
            store.update(updated, cipher=cipher)
        except ProviderConnectionNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider connection '{connection_id}' not found",
            )
    logger.info(
        "Updated LLM provider connection", extra={"connection_id": connection_id}
    )
    return _to_response(updated)


@provider_connections_router.delete(
    "/{connection_id}", response_model=ProviderConnectionResponse
)
def delete_provider_connection(
    request: Request, connection_id: str
) -> ProviderConnectionResponse:
    config = get_config(request)
    cipher = get_cipher(request)
    store = get_provider_connections_store(config)
    with store_errors():
        connection = store.get(connection_id, cipher=cipher)
    if connection is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider connection '{connection_id}' not found",
        )
    _raise_if_connection_is_referenced(config, connection_id)

    # 请参阅更新处理程序：将删除竞赛保留为 404，映射基础设施错误。
    with store_errors():
        try:
            store.delete(connection_id, cipher=cipher)
        except ProviderConnectionNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider connection '{connection_id}' not found",
            )
    logger.info(
        "Deleted LLM provider connection", extra={"connection_id": connection_id}
    )
    return ProviderConnectionResponse(
        id=connection.id,
        display_name=connection.display_name,
        provider=connection.provider,
        base_url=connection.base_url,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
        api_key_set=False,
    )
