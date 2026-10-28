"""用于 FastMCP MCP 个客户端的设置支持的 OAuth token 存储。

FastMCP'OAuth客户端读取和写入一个' ``AsyncKeyValue``  token store. 这个适配器映射了
FastMCP将“token/clien
t-info/expiry”键值对放到 OpenHands 设置好 MCP OAuth 凭据留在设置中 DataModel 并且使用
其他设置的加密/删除路径机密。
"""

from __future__ import annotations

import asyncio
import copy
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NamedTuple, SupportsFloat

import httpx

from openhands.agent_server.config import Config, WebhookSpec
from openhands.agent_server.persistence import PersistedSettings, get_settings_store
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.config import (
    MCPOAuthAuthCredential,
    MCPOAuthClientInfoState,
    MCPOAuthState,
    MCPOAuthTokenStorageField,
    MCPServer,
)
from openhands.sdk.mcp.oauth import NonInteractiveMCPOAuth
from openhands.sdk.mcp.utils import (
    ToolsChangedCallback,
    ToolsReconciledCallback,
    create_mcp_tools,
)
from openhands.sdk.utils.cipher import Cipher


logger = get_logger(__name__)

_WRITE_BACK_TIMEOUT_SECONDS = 10.0


class _OAuthKeySpec(NamedTuple):
    suffix: str
    collection: str
    field: MCPOAuthTokenStorageField


_OAUTH_KEY_SPECS: tuple[_OAuthKeySpec, ...] = (
    _OAuthKeySpec("/tokens", "mcp-oauth-token", "tokens"),
    _OAuthKeySpec("/client_info", "mcp-oauth-client-info", "client_info"),
    _OAuthKeySpec("/token_expiry", "mcp-oauth-token-expiry", "token_expires_at"),
)


def _client_id(client_info: MCPOAuthClientInfoState | None) -> str | None:
    """客户端存储注册名称。"""
    if client_info is None:
        return None
    client_id = (client_info.model_extra or {}).get("client_id")
    return client_id if isinstance(client_id, str) else None


def _server_url_from_fastmcp_key(key: str) -> str:
    """从其 OAuth token 存储密钥中提取 FastMCP 的服务器 URL 前缀。"""
    for spec in _OAUTH_KEY_SPECS:
        if key.endswith(spec.suffix):
            return key[: -len(spec.suffix)].rstrip("/")
    return key.rsplit("/", 1)[0].rstrip("/")


def _server_url_matches_key(server_url: str, key: str) -> bool:
    return server_url.rstrip("/") == _server_url_from_fastmcp_key(key)


def _find_matching_oauth_server(
    mcp_config: dict[str, MCPServer],
    key: str,
) -> tuple[str, MCPServer, MCPOAuthAuthCredential] | None:
    for server_name, server in mcp_config.items():
        if server.url is None or not _server_url_matches_key(server.url, key):
            continue
        auth = server.auth
        if isinstance(auth, MCPOAuthAuthCredential):
            return server_name, server, auth
    return None


def _state_field_for_fastmcp_key(
    key: str,
    collection: str | None,
) -> MCPOAuthTokenStorageField | None:
    for spec in _OAUTH_KEY_SPECS:
        if collection == spec.collection and key.endswith(spec.suffix):
            return spec.field
    return None


class MCPSettingsOAuthTokenStore:
    """将 FastMCP OAuth 令牌持久化到设置中的 MCP 服务器配置。

    ``seed_mcp_config`` 涵盖未保存在本服务器设置中的 OAuth 服务器，例如托管部署
    通过内联配置传入智能体的服务器；它们的设置保存在远程应用服务器上。
    这些服务器携带的 ``auth.state`` 会提供给 FastMCP。对话期间刷新的令牌会在
    存储对象的整个生命周期内保留在内存中，而不是被丢弃。设置中已有的服务器始终优先。

    ``write_back_webhooks`` 是本智能体服务器发送对话事件时调用的应用服务器回调。
    刷新后的内联状态也会发送到这些回调，让应用服务器能够持久化该状态；
    参见 ``_write_back_seeded_state``。
    """

    def __init__(
        self,
        *,
        seed_mcp_config: Mapping[str, MCPServer] | None = None,
        cipher: Cipher | None = None,
        write_back_webhooks: Sequence[WebhookSpec] = (),
        session_api_key: str | None = None,
    ):
        self._seeded: dict[str, MCPOAuthState] = {}
        self._seeded_client_ids: dict[str, str | None] = {}
        self._seeded_lock = threading.Lock()
        self._write_back_webhooks = tuple(write_back_webhooks)
        self._session_api_key = session_api_key
        for server in (seed_mcp_config or {}).values():
            oauth_auth = server.oauth_auth
            if server.url is None or oauth_auth is None:
                continue
            state = server.initial_oauth_state(cipher=cipher) or MCPOAuthState()
            self._seeded[server.url.rstrip("/")] = state
            # FastMCP 始终使用配置的静态客户端，在每次连接时重写其存储的注册。
            #
            authentication = oauth_auth.authentication
            static_client_id = authentication.client_id if authentication else None
            self._seeded_client_ids[server.url.rstrip("/")] = (
                static_client_id or _client_id(state.client_info)
            )

    def _seeded_state(self, key: str) -> MCPOAuthState | None:
        with self._seeded_lock:
            return self._seeded.get(_server_url_from_fastmcp_key(key))

    def _get_entry_sync(
        self, key: str, collection: str | None
    ) -> tuple[dict[str, Any] | None, float | None]:
        field = _state_field_for_fastmcp_key(key, collection)
        if field is None:
            return None, None

        store = get_settings_store()
        settings = store.load()
        mcp_config = settings.agent_settings.mcp_config if settings else {}
        match = _find_matching_oauth_server(mcp_config, key)
        if match is None:
            seeded = self._seeded_state(key)
            if seeded is None:
                return None, None
            return seeded.get_token_storage_value(field), None
        _, _, auth = match
        return (auth.state or MCPOAuthState()).get_token_storage_value(field), None

    async def get(
        self, key: str, *, collection: str | None = None
    ) -> dict[str, Any] | None:
        value, _ = await asyncio.to_thread(self._get_entry_sync, key, collection)
        return value

    async def ttl(
        self, key: str, *, collection: str | None = None
    ) -> tuple[dict[str, Any] | None, float | None]:
        return await asyncio.to_thread(self._get_entry_sync, key, collection)

    def _put_sync(
        self,
        key: str,
        value: Mapping[str, Any],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        del ttl
        field = _state_field_for_fastmcp_key(key, collection)
        if field is None:
            return
        stored_value = copy.deepcopy(dict(value))
        seeded_updates: list[tuple[str, MCPOAuthState]] = []

        def apply_update(settings: PersistedSettings) -> PersistedSettings:
            mcp_config = settings.agent_settings.mcp_config
            match = _find_matching_oauth_server(mcp_config, key)
            if match is None:
                server_url = _server_url_from_fastmcp_key(key)
                with self._seeded_lock:
                    seeded = self._seeded.get(server_url)
                    if seeded is not None:
                        updated = seeded.with_token_storage_value(field, stored_value)
                        self._seeded[server_url] = updated
                        seeded_updates.append((server_url, updated))
                        return settings
                logger.warning(
                    "Could not persist MCP OAuth state: no configured MCP "
                    "server matches FastMCP key %r",
                    key,
                )
                return settings

            server_name, server, auth = match

            state = (auth.state or MCPOAuthState()).with_token_storage_value(
                field, stored_value
            )
            updated_servers = dict(mcp_config)
            updated_servers[server_name] = server.model_copy(
                update={
                    "auth": auth.model_copy(
                        update={"state": state if state.has_values else None}
                    )
                }
            )
            settings.agent_settings = settings.agent_settings.model_copy(
                update={"mcp_config": updated_servers}
            )
            return settings

        get_settings_store().update(apply_update)
        for server_url, state in seeded_updates:
            self._write_back_seeded_state(server_url, state)

    def _write_back_seeded_state(self, server_url: str, state: MCPOAuthState) -> None:
        """将内联服务器的刷新状态发布到应用程序服务器。

        服务器的设置在 inline 上通过智能体在启动对话的服务器上运行。 没有它，刷新就失
        效了 token 在沙盒中死亡，接下来的对话从上一个开始刷新令牌，该端
        点已弃用 token 已经撤销。 尽力而为：失败只会记录，内存映射层继续提供新内容
        token. 只有  token 对于客户端来说，它被填充了，所以
        FastMCP 删除存储的凭据在对话期间，客户端不能替换这些端点。
        """
        if not self._write_back_webhooks:
            return
        if state.tokens is None or state.tokens.access_token is None:
            return
        if _client_id(state.client_info) != self._seeded_client_ids.get(server_url):
            return
        payload = {
            "server_url": server_url,
            "oauth_state": state.to_response().model_dump(
                mode="json", exclude_none=True
            ),
        }
        for spec in self._write_back_webhooks:
            headers = dict(spec.headers)
            if self._session_api_key:
                headers["X-Session-API-Key"] = self._session_api_key
            url = f"{spec.base_url.rstrip('/')}/mcp-oauth-state"
            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=_WRITE_BACK_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
            except httpx.HTTPError:
                logger.warning(
                    "Could not write back MCP OAuth state for %s to %s",
                    server_url,
                    url,
                    exc_info=True,
                )

    async def put(
        self,
        key: str,
        value: Mapping[str, Any],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._put_sync,
            key,
            value,
            collection=collection,
            ttl=ttl,
        )

    def _delete_sync(self, key: str, collection: str | None = None) -> bool:
        field = _state_field_for_fastmcp_key(key, collection)
        if field is None:
            return False

        deleted = False

        def apply_update(settings: PersistedSettings) -> PersistedSettings:
            nonlocal deleted
            mcp_config = settings.agent_settings.mcp_config
            match = _find_matching_oauth_server(mcp_config, key)
            if match is None:
                server_url = _server_url_from_fastmcp_key(key)
                with self._seeded_lock:
                    seeded = self._seeded.get(server_url)
                    if seeded is not None:
                        seeded, deleted = seeded.without_token_storage_value(field)
                        self._seeded[server_url] = seeded
                return settings
            server_name, server, auth = match
            state, deleted = (
                auth.state or MCPOAuthState()
            ).without_token_storage_value(field)
            if not deleted:
                return settings
            updated_servers = dict(mcp_config)
            updated_servers[server_name] = server.model_copy(
                update={
                    "auth": auth.model_copy(
                        update={"state": state if state.has_values else None}
                    )
                }
            )
            settings.agent_settings = settings.agent_settings.model_copy(
                update={"mcp_config": updated_servers}
            )
            return settings

        get_settings_store().update(apply_update)
        return deleted

    async def delete(self, key: str, *, collection: str | None = None) -> bool:
        return await asyncio.to_thread(self._delete_sync, key, collection)

    async def get_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[dict[str, Any] | None]:
        return [await self.get(key, collection=collection) for key in keys]

    async def ttl_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[tuple[dict[str, Any] | None, float | None]]:
        return [await self.ttl(key, collection=collection) for key in keys]

    async def put_many(
        self,
        keys: Sequence[str],
        values: Sequence[Mapping[str, Any]],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        if len(keys) != len(values):
            raise ValueError("keys and values must have the same length")
        for key, value in zip(keys, values, strict=True):
            await self.put(key, value, collection=collection, ttl=ttl)

    async def delete_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> int:
        deleted = 0
        for key in keys:
            if await self.delete(key, collection=collection):
                deleted += 1
        return deleted


class InMemoryMCPOAuthTokenStore:
    """非变异 MCP 安装探针使用的内存存储。"""

    def __init__(
        self,
        *,
        state: MCPOAuthState | None = None,
    ):
        self._state = state or MCPOAuthState()

    def export_state(self) -> MCPOAuthState:
        return self._state

    async def get(
        self, key: str, *, collection: str | None = None
    ) -> dict[str, Any] | None:
        field = _state_field_for_fastmcp_key(key, collection)
        if field is None:
            return None
        return self._state.get_token_storage_value(field)

    async def ttl(
        self, key: str, *, collection: str | None = None
    ) -> tuple[dict[str, Any] | None, float | None]:
        return await self.get(key, collection=collection), None

    async def put(
        self,
        key: str,
        value: Mapping[str, Any],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        del ttl
        field = _state_field_for_fastmcp_key(key, collection)
        if field is not None:
            self._state = self._state.with_token_storage_value(field, value)

    async def delete(self, key: str, *, collection: str | None = None) -> bool:
        field = _state_field_for_fastmcp_key(key, collection)
        if field is None:
            return False
        state, deleted = self._state.without_token_storage_value(field)
        if deleted:
            self._state = state
        return deleted

    async def get_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[dict[str, Any] | None]:
        return [await self.get(key, collection=collection) for key in keys]

    async def ttl_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[tuple[dict[str, Any] | None, float | None]]:
        return [await self.ttl(key, collection=collection) for key in keys]

    async def put_many(
        self,
        keys: Sequence[str],
        values: Sequence[Mapping[str, Any]],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        if len(keys) != len(values):
            raise ValueError("keys and values must have the same length")
        for key, value in zip(keys, values, strict=True):
            await self.put(key, value, collection=collection, ttl=ttl)

    async def delete_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> int:
        deleted = 0
        for key in keys:
            if await self.delete(key, collection=collection):
                deleted += 1
        return deleted


@dataclass(frozen=True, slots=True)
class SettingsBackedMCPToolProvider:
    """在设置中创建具有 FastMCP OAuth 状态已持久化的 MCP 工具。

    不在设置中的OAuth服务器（通过智能体传递）会回退到它们携带的OAuth状态，并通过
    ``webhooks``发布刷新状态。 参见
    ``MCPSettingsOAuthTokenStore``。 对话仅使用和刷新该状态：再次授权服务器由用户决定
    。
    """

    cipher: Cipher | None = None
    webhooks: tuple[WebhookSpec, ...] = ()
    session_api_key: str | None = None

    def create_tools(
        self,
        mcp_config: dict[str, MCPServer],
        timeout: float = 30.0,
        *,
        on_tools_changed: ToolsChangedCallback | None = None,
        on_tools_reconciled: ToolsReconciledCallback | None = None,
    ) -> MCPClient:
        return create_mcp_tools(
            mcp_config,
            timeout,
            mcp_oauth_token_storage=MCPSettingsOAuthTokenStore(
                seed_mcp_config=mcp_config,
                cipher=self.cipher,
                write_back_webhooks=self.webhooks,
                session_api_key=self.session_api_key,
            ),
            mcp_oauth_class=NonInteractiveMCPOAuth,
            on_tools_changed=on_tools_changed,
            on_tools_reconciled=on_tools_reconciled,
        )


def create_settings_backed_mcp_tool_provider(
    config: Config,
) -> SettingsBackedMCPToolProvider:
    """初始化设置存储并返回智能体-服务器 MCP 提供程序。"""
    get_settings_store(config)
    if config.secret_key is None:
        logger.warning(
            "Saving MCP OAuth state without encryption "
            "(no OH_SECRET_KEY configured). Configure OH_SECRET_KEY for "
            "production deployments."
        )
    return SettingsBackedMCPToolProvider(
        cipher=config.cipher,
        webhooks=tuple(config.webhooks),
        session_api_key=(
            config.session_api_keys[0] if config.session_api_keys else None
        ),
    )
