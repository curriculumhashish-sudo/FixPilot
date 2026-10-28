from __future__ import annotations

import json
import socket
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import uvicorn
from fastmcp import FastMCP
from fastmcp.server.auth.providers.in_memory import InMemoryOAuthProvider
from mcp.server.auth.provider import RefreshToken
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import SecretStr

from openhands.agent_server.config import Config, WebhookSpec
from openhands.agent_server.mcp_oauth_store import (
    MCPSettingsOAuthTokenStore,
    SettingsBackedMCPToolProvider,
    create_settings_backed_mcp_tool_provider,
)
from openhands.agent_server.persistence import (
    PersistedSettings,
    get_settings_store,
    reset_stores,
)
from openhands.sdk.mcp.config import MCPServer, coerce_mcp_config, dump_mcp_config
from openhands.sdk.mcp.exceptions import MCPError, MCPTimeoutError
from openhands.sdk.mcp.oauth import MCPOAuth
from openhands.sdk.mcp.utils import create_mcp_tools


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return int(sock.getsockname()[1])


def _wait_for_http_server(port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=0.2) as client:
                client.get(f"http://127.0.0.1:{port}/")
            return
        except httpx.ConnectError:
            time.sleep(0.05)
        except Exception:
            return
    raise RuntimeError(f"Timed out waiting for test MCP server on port {port}")


class _HeadlessOAuth(MCPOAuth):
    """FastMCP 遵循授权重定向本身的 OAuth 客户端。

    这保留了真实的 DCR/PKCE/令牌交换，同时避免了 CI 中的外部浏览器和本地回调服务器。
    """

    redirect_count = 0

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("callback_port", _find_free_port())
        super().__init__(*args, **kwargs)
        self._redirect_location: str | None = None

    async def redirect_handler(self, authorization_url: str) -> None:
        type(self).redirect_count += 1
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            response = await client.get(authorization_url)
        assert response.status_code in {302, 303, 307, 308}
        self._redirect_location = response.headers["location"]

    async def callback_handler(self) -> tuple[str, str | None]:
        assert self._redirect_location is not None
        query = parse_qs(urlparse(self._redirect_location).query)
        code = query.get("code", [None])[0]
        assert code is not None
        return code, query.get("state", [None])[0]


@pytest.fixture
def oauth_provider() -> InMemoryOAuthProvider:
    """``protected_oauth_mcp_server`` 的授权服务器。"""
    return InMemoryOAuthProvider(
        base_url=f"http://127.0.0.1:{_find_free_port()}",
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mail.read"],
            default_scopes=["mail.read"],
        ),
        required_scopes=["mail.read"],
    )


@pytest.fixture
def protected_oauth_mcp_server(oauth_provider: InMemoryOAuthProvider):
    port = urlparse(str(oauth_provider.base_url)).port
    assert port is not None
    mcp = FastMCP("protected-oauth-mcp", auth=oauth_provider)

    @mcp.tool()
    def read_subject(subject: str) -> str:
        return f"OAuth mail subject: {subject}"

    server = uvicorn.Server(
        uvicorn.Config(
            mcp.http_app(path="/mcp", transport="http"),
            host="127.0.0.1",
            port=port,
            timeout_graceful_shutdown=2,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_http_server(port)
    yield f"http://127.0.0.1:{port}/mcp"
    # 保持运行的服务器不断调用 asyncio.sleep，其他测试补丁。
    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.asyncio
async def test_mcp_oauth_token_store_persists_values_in_settings(
    tmp_path: Path,
):
    reset_stores()
    try:
        config = Config(
            session_api_keys=[],
            conversations_path=tmp_path / "conversations",
            secret_key=SecretStr("mcp-oauth-test-key"),
        )
        settings = PersistedSettings()
        settings.agent_settings = settings.agent_settings.model_copy(
            update={
                "mcp_config": coerce_mcp_config(
                    {
                        "superhuman": {
                            "url": "https://mcp.example.com/mcp",
                            "auth": {
                                "strategy": "oauth2",
                                "authentication": {
                                    "type": "oauth",
                                    "client_auth_method": "none",
                                },
                            },
                        }
                    }
                )
            }
        )
        settings_store = get_settings_store(config)
        settings_store.save(settings)
        create_settings_backed_mcp_tool_provider(config)

        key = "https://mcp.example.com/mcp/tokens"
        client_info_key = "https://mcp.example.com/mcp/client_info"
        token_expiry_key = "https://mcp.example.com/mcp/token_expiry"
        value = {
            "access_token": "super-secret-token",
            "refresh_token": "refresh-token",
        }
        client_info = {
            "redirect_uris": ["http://127.0.0.1:64801/callback"],
            "client_id": "superhuman-client",
            "client_secret": "superhuman-client-secret",
        }
        token_expiry = {"expires_at": 12345.0}

        store = MCPSettingsOAuthTokenStore()
        await store.put(key=key, value=value, collection="mcp-oauth-token")
        await store.put(
            key=client_info_key,
            value=client_info,
            collection="mcp-oauth-client-info",
        )
        await store.put(
            key=token_expiry_key,
            value=token_expiry,
            collection="mcp-oauth-token-expiry",
        )

        reloaded_store = MCPSettingsOAuthTokenStore()
        assert (
            await reloaded_store.get(key=key, collection="mcp-oauth-token")
        ) == value
        assert (
            await reloaded_store.get(
                key=client_info_key,
                collection="mcp-oauth-client-info",
            )
        ) == client_info
        assert (
            await reloaded_store.get(
                key=token_expiry_key,
                collection="mcp-oauth-token-expiry",
            )
        ) == token_expiry

        on_disk_text = (settings_store.persistence_dir / "settings.json").read_text()
        assert "super-secret-token" not in on_disk_text
        assert "refresh-token" not in on_disk_text
        assert "superhuman-client-secret" not in on_disk_text

        on_disk = json.loads(on_disk_text)
        stored_state = on_disk["agent_settings"]["mcp_config"]["superhuman"]["auth"][
            "state"
        ]
        stored_value = stored_state["tokens"]
        assert stored_value["access_token"].startswith("gAAAA")
        assert stored_value["refresh_token"].startswith("gAAAA")
        assert stored_state["client_info"]["client_secret"].startswith("gAAAA")
        assert stored_state["token_expires_at"] == 12345.0

        loaded = settings_store.load()
        assert loaded is not None
        server = dump_mcp_config(loaded.agent_settings.mcp_config)["superhuman"]
        auth = server["auth"]
        assert isinstance(auth, dict)
        assert auth["state"] == {
            "tokens": value,
            "client_info": client_info,
            "token_expires_at": 12345.0,
        }
    finally:
        reset_stores()


def test_oauth_mcp_connection_persists_and_reuses_settings_state(
    tmp_path: Path,
    protected_oauth_mcp_server: str,
):
    """对受保护的 MCP 服务器进行一次身份验证，序列化、重新加载并重复使用。

    服务器使用 FastMCP 的内存中 OAuth 提供程序。 客户端使用正常的SDKMCP设置形状加上
    FastMCPOAuth； 只有人类浏览器/回调步骤被确定性重
    定向跟随器取代。 对话从不授权，因此设置支持的提供程序仅重用已持久化状态。
    """

    reset_stores()
    _HeadlessOAuth.redirect_count = 0
    try:
        config = Config(
            session_api_keys=[],
            conversations_path=tmp_path / "conversations",
            secret_key=SecretStr("mcp-oauth-e2e-test-key"),
        )
        mcp_config = coerce_mcp_config(
            {
                "mail": {
                    "url": protected_oauth_mcp_server,
                    "transport": "http",
                    "auth": {
                        "strategy": "oauth2",
                        "authentication": {
                            "type": "oauth",
                            "client_auth_method": "none",
                            "scopes": ["mail.read"],
                        },
                    },
                }
            }
        )
        settings = PersistedSettings()
        settings.agent_settings = settings.agent_settings.model_copy(
            update={"mcp_config": mcp_config}
        )
        settings_store = get_settings_store(config)
        settings_store.save(settings)
        tool_provider = create_settings_backed_mcp_tool_provider(config)

        with create_mcp_tools(
            mcp_config,
            timeout=10.0,
            mcp_oauth_token_storage=MCPSettingsOAuthTokenStore(),
            mcp_oauth_class=_HeadlessOAuth,
        ) as client:
            tool = next(tool for tool in client.tools if tool.name == "read_subject")
            assert tool.executor is not None
            observation = tool.executor(
                tool.action_from_arguments({"subject": "Quarterly Plan"})
            )
            assert "OAuth mail subject: Quarterly Plan" in observation.text

        assert _HeadlessOAuth.redirect_count == 1
        on_disk_text = (settings_store.persistence_dir / "settings.json").read_text()
        assert "test_access_token_" not in on_disk_text
        assert "test_refresh_token_" not in on_disk_text

        reloaded = settings_store.load()
        assert reloaded is not None
        persisted_mcp_config = reloaded.agent_settings.mcp_config
        server = dump_mcp_config(persisted_mcp_config)["mail"]
        auth = server["auth"]
        assert isinstance(auth, dict)
        state = auth["state"]
        assert isinstance(state, dict)
        tokens = state["tokens"]
        assert isinstance(tokens, dict)
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        assert isinstance(access_token, str)
        assert isinstance(refresh_token, str)
        assert access_token.startswith("test_access_token_")
        assert refresh_token.startswith("test_refresh_token_")
        client_info = state["client_info"]
        assert isinstance(client_info, dict)
        assert client_info["client_id"]

        with tool_provider.create_tools(
            persisted_mcp_config,
            timeout=10.0,
        ) as client:
            tool = next(tool for tool in client.tools if tool.name == "read_subject")
            assert tool.executor is not None
            observation = tool.executor(
                tool.action_from_arguments({"subject": "Follow-up"})
            )
            assert "OAuth mail subject: Follow-up" in observation.text
    finally:
        reset_stores()


@pytest.mark.asyncio
async def test_mcp_oauth_token_storage_does_not_attach_to_non_oauth_server(
    tmp_path: Path,
):
    reset_stores()
    try:
        config = Config(
            session_api_keys=[],
            conversations_path=tmp_path / "conversations",
            secret_key=SecretStr("mcp-oauth-test-key"),
        )
        settings = PersistedSettings()
        settings.agent_settings = settings.agent_settings.model_copy(
            update={
                "mcp_config": coerce_mcp_config(
                    {"plain": {"url": "https://mcp.example.com/mcp"}}
                )
            }
        )
        settings_store = get_settings_store(config)
        settings_store.save(settings)

        create_settings_backed_mcp_tool_provider(config)
        store = MCPSettingsOAuthTokenStore()

        await store.put(
            key="https://mcp.example.com/mcp/tokens",
            value={"access_token": "super-secret-token"},
            collection="mcp-oauth-token",
        )

        loaded = settings_store.load()
        assert loaded is not None
        server = dump_mcp_config(loaded.agent_settings.mcp_config)["plain"]
        assert "auth" not in server
    finally:
        reset_stores()


def test_settings_backed_provider_forwards_on_tools_reconciled():
    """on_tools_reconciled 必须到达 create_mcp_tools()，不能被丢弃。

    以前，这个提供者只接受 on_tools_changed，因此调用者必须在连接完成后附加
    on_tools_reconciled。
    """
    provider = SettingsBackedMCPToolProvider()
    config = coerce_mcp_config({"fake": {"command": "true"}})

    def callback(client, tools):
        return None

    with patch(
        "openhands.agent_server.mcp_oauth_store.create_mcp_tools"
    ) as mock_create:
        provider.create_tools(config, on_tools_reconciled=callback)

    assert mock_create.call_args.kwargs["on_tools_reconciled"] is callback


def _inline_oauth_server(access_token: str):
    """当托管智能体传递它时，一台 OAuth 服务器内嵌其状态。"""
    return coerce_mcp_config(
        {
            "mail": {
                "url": "https://mcp.example.com/mcp",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {"type": "oauth", "client_auth_method": "none"},
                    "state": {"tokens": {"access_token": access_token}},
                },
            }
        }
    )


@pytest.mark.asyncio
async def test_mcp_oauth_token_store_serves_inline_state_for_servers_absent_from_settings(  # noqa: E501
    tmp_path: Path,
):
    reset_stores()
    try:
        # 安排：沙箱设置存储根本不知道 MCP 个服务器。
        config = Config(
            session_api_keys=[],
            conversations_path=tmp_path / "conversations",
            secret_key=SecretStr("mcp-oauth-test-key"),
        )
        settings_store = get_settings_store(config)
        settings_store.save(PersistedSettings())
        store = MCPSettingsOAuthTokenStore(
            seed_mcp_config=_inline_oauth_server("agent-access-token"),
            cipher=config.cipher,
        )
        key = "https://mcp.example.com/mcp/tokens"

        # 法案
        initial = await store.get(key=key, collection="mcp-oauth-token")
        await store.put(
            key=key,
            value={"access_token": "refreshed-access-token"},
            collection="mcp-oauth-token",
        )
        refreshed = await store.get(key=key, collection="mcp-oauth-token")
        deleted = await store.delete(key=key, collection="mcp-oauth-token")

        # 断言：从内联状态提供服务，在内存中刷新，从不
        # 写入设置。
        assert initial == {"access_token": "agent-access-token"}
        assert refreshed == {"access_token": "refreshed-access-token"}
        assert deleted is True
        assert await store.get(key=key, collection="mcp-oauth-token") is None
        loaded = settings_store.load()
        assert loaded is not None
        assert not loaded.agent_settings.mcp_config
    finally:
        reset_stores()


@pytest.mark.asyncio
async def test_mcp_oauth_token_store_prefers_settings_over_inline_state(
    tmp_path: Path,
):
    reset_stores()
    try:
        # 排列：设置中存在相同的服务器并具有自己的token。
        config = Config(
            session_api_keys=[],
            conversations_path=tmp_path / "conversations",
            secret_key=SecretStr("mcp-oauth-test-key"),
        )
        settings = PersistedSettings()
        settings.agent_settings = settings.agent_settings.model_copy(
            update={"mcp_config": _inline_oauth_server("settings-access-token")}
        )
        get_settings_store(config).save(settings)
        store = MCPSettingsOAuthTokenStore(
            seed_mcp_config=_inline_oauth_server("agent-access-token"),
            cipher=config.cipher,
        )

        # 法案
        value = await store.get(
            key="https://mcp.example.com/mcp/tokens", collection="mcp-oauth-token"
        )

        # 断言
        assert value == {"access_token": "settings-access-token"}
    finally:
        reset_stores()


@pytest.mark.asyncio
async def test_settings_backed_provider_seeds_token_store_from_agent_mcp_config(
    tmp_path: Path,
):
    reset_stores()
    try:
        # 安排
        config = Config(
            session_api_keys=[],
            conversations_path=tmp_path / "conversations",
            secret_key=SecretStr("mcp-oauth-test-key"),
        )
        get_settings_store(config).save(PersistedSettings())
        provider = create_settings_backed_mcp_tool_provider(config)
        mcp_config = _inline_oauth_server("agent-access-token")

        # 法案
        with patch(
            "openhands.agent_server.mcp_oauth_store.create_mcp_tools"
        ) as mock_create:
            provider.create_tools(mcp_config)

        # 断言：传递给 FastMCP 的存储已经知道智能体的 token。
        storage = mock_create.call_args.kwargs["mcp_oauth_token_storage"]
        assert await storage.get(
            key="https://mcp.example.com/mcp/tokens", collection="mcp-oauth-token"
        ) == {"access_token": "agent-access-token"}
    finally:
        reset_stores()


def _hosted_config(tmp_path: Path) -> Config:
    """托管沙箱运行的智能体-服务器配置：应用程序服务器
    Webhook 发布到应用程序服务器验证的会话密钥。"""
    return Config(
        session_api_keys=["sandbox-session-key"],
        conversations_path=tmp_path / "conversations",
        secret_key=SecretStr("mcp-oauth-test-key"),
        webhooks=[
            WebhookSpec(
                base_url="https://app.example/api/v1/webhooks",
                headers={"X-Trace": "on"},
            )
        ],
    )


@pytest.mark.asyncio
async def test_settings_backed_provider_writes_refreshed_inline_state_back_to_the_app_server(  # noqa: E501
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    reset_stores()
    try:
        # 排列：服务器仅内联，因为托管对话会通过它。
        config = _hosted_config(tmp_path)
        get_settings_store(config).save(PersistedSettings())
        posted: list[dict] = []

        def fake_post(url, *, json, headers, timeout):
            posted.append({"url": url, "json": json, "headers": headers})
            return httpx.Response(200, request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx, "post", fake_post)
        provider = create_settings_backed_mcp_tool_provider(config)
        with patch(
            "openhands.agent_server.mcp_oauth_store.create_mcp_tools"
        ) as mock_create:
            provider.create_tools(_inline_oauth_server("agent-access-token"))
        storage = mock_create.call_args.kwargs["mcp_oauth_token_storage"]

        # Act: FastMCP 存储刷新的 token 及其到期时间。
        await storage.put(
            key="https://mcp.example.com/mcp/tokens",
            value={
                "access_token": "refreshed-access-token",
                "refresh_token": "rotated-refresh-token",
            },
            collection="mcp-oauth-token",
        )
        await storage.put(
            key="https://mcp.example.com/mcp/token_expiry",
            value={"expires_at": 1234.0},
            collection="mcp-oauth-token-expiry",
        )

        # 断言：每次写入都会将整个状态发布到应用程序服务器。
        assert [entry["url"] for entry in posted] == [
            "https://app.example/api/v1/webhooks/mcp-oauth-state"
        ] * 2
        assert posted[-1]["headers"] == {
            "X-Trace": "on",
            "X-Session-API-Key": "sandbox-session-key",
        }
        assert posted[-1]["json"] == {
            "server_url": "https://mcp.example.com/mcp",
            "oauth_state": {
                "tokens": {
                    "access_token": "refreshed-access-token",
                    "refresh_token": "rotated-refresh-token",
                },
                "token_expires_at": 1234.0,
            },
        }
    finally:
        reset_stores()


@pytest.mark.asyncio
async def test_mcp_oauth_token_store_does_not_write_back_settings_backed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    reset_stores()
    try:
        # 排列：同一服务器位于此 Agent Server 自己的设置中。
        config = _hosted_config(tmp_path)
        settings = PersistedSettings()
        settings.agent_settings = settings.agent_settings.model_copy(
            update={"mcp_config": _inline_oauth_server("settings-access-token")}
        )
        get_settings_store(config).save(settings)
        posted: list[str] = []
        monkeypatch.setattr(
            httpx, "post", lambda url, **kwargs: posted.append(url) or None
        )
        store = MCPSettingsOAuthTokenStore(
            seed_mcp_config=_inline_oauth_server("agent-access-token"),
            cipher=config.cipher,
            write_back_webhooks=config.webhooks,
            session_api_key="sandbox-session-key",
        )
        key = "https://mcp.example.com/mcp/tokens"

        # 法案
        await store.put(
            key=key,
            value={"access_token": "refreshed-access-token"},
            collection="mcp-oauth-token",
        )

        # 断言：已持久化在本地，没有任何内容发送到应用程序服务器。
        assert posted == []
        assert await store.get(key=key, collection="mcp-oauth-token") == {
            "access_token": "refreshed-access-token"
        }
    finally:
        reset_stores()


@pytest.mark.asyncio
async def test_mcp_oauth_token_store_keeps_refreshed_inline_state_when_write_back_fails(  # noqa: E501
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    reset_stores()
    try:
        # 安排：无法访问应用程序服务器。
        config = _hosted_config(tmp_path)
        get_settings_store(config).save(PersistedSettings())

        def failing_post(url, **kwargs):
            raise httpx.ConnectError(
                "app server unreachable", request=httpx.Request("POST", url)
            )

        monkeypatch.setattr(httpx, "post", failing_post)
        store = MCPSettingsOAuthTokenStore(
            seed_mcp_config=_inline_oauth_server("agent-access-token"),
            cipher=config.cipher,
            write_back_webhooks=config.webhooks,
            session_api_key="sandbox-session-key",
        )
        key = "https://mcp.example.com/mcp/tokens"

        # 法案
        await store.put(
            key=key,
            value={"access_token": "refreshed-access-token"},
            collection="mcp-oauth-token",
        )

        # 断言：会话继续使用刷新后的token。
        assert await store.get(key=key, collection="mcp-oauth-token") == {
            "access_token": "refreshed-access-token"
        }
    finally:
        reset_stores()


@pytest.fixture
def write_backs(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """正文 Agent Server 发布到应用服务器的 OAuth 状态 Webhook。"""
    posted: list[dict] = []

    def fake_post(url, *, json, headers, timeout):
        posted.append(json)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    return posted


@pytest.mark.asyncio
async def test_mcp_oauth_token_store_does_not_write_back_state_without_tokens(
    tmp_path: Path, write_backs: list[dict]
):
    reset_stores()
    try:
        # 安排
        config = _hosted_config(tmp_path)
        get_settings_store(config).save(PersistedSettings())
        store = MCPSettingsOAuthTokenStore(
            seed_mcp_config=_inline_oauth_server("agent-access-token"),
            cipher=config.cipher,
            write_back_webhooks=config.webhooks,
            session_api_key="sandbox-session-key",
        )

        # 行动：FastMCP删除存储的token并注册一个新客户端。
        await store.delete(
            key="https://mcp.example.com/mcp/tokens", collection="mcp-oauth-token"
        )
        await store.put(
            key="https://mcp.example.com/mcp/client_info",
            value={
                "client_id": "loopback-client",
                "redirect_uris": ["http://localhost:4321/callback"],
            },
            collection="mcp-oauth-client-info",
        )

        # 断言：没有任何内容可以替代应用程序服务器持有的凭据。
        assert write_backs == []
    finally:
        reset_stores()


@pytest.mark.asyncio
async def test_mcp_oauth_token_store_does_not_write_back_a_client_it_registered(
    tmp_path: Path, write_backs: list[dict]
):
    reset_stores()
    try:
        # 排列：内联状态有token但没有客户端注册。
        config = _hosted_config(tmp_path)
        get_settings_store(config).save(PersistedSettings())
        store = MCPSettingsOAuthTokenStore(
            seed_mcp_config=_inline_oauth_server("agent-access-token"),
            cipher=config.cipher,
            write_back_webhooks=config.webhooks,
            session_api_key="sandbox-session-key",
        )

        # Act：FastMCP注册一个环回客户端，同时保留token。
        await store.put(
            key="https://mcp.example.com/mcp/client_info",
            value={
                "client_id": "loopback-client",
                "redirect_uris": ["http://localhost:4321/callback"],
            },
            collection="mcp-oauth-client-info",
        )

        # 断言
        assert write_backs == []
    finally:
        reset_stores()


def _installed_client(oauth_provider: InMemoryOAuthProvider) -> dict[str, Any]:
    """仅为应用程序服务器的公共回调注册的客户端。"""
    client = OAuthClientInformationFull.model_validate(
        {
            "client_id": "installed-client",
            "redirect_uris": ["https://app.example/api/v1/mcp/oauth/callback"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": "mail.read",
        }
    )
    oauth_provider.clients["installed-client"] = client
    return client.model_dump(mode="json", exclude_none=True)


def _expired_inline_oauth_server(
    url: str,
    client_info: dict[str, Any] | None,
    refresh_token: str,
    static_client_id: str | None = None,
) -> dict[str, MCPServer]:
    """存储的访问令牌已过期的内联 OAuth 服务器。"""
    return coerce_mcp_config(
        {
            "mail": {
                "url": url,
                "transport": "http",
                "auth": {
                    "strategy": "oauth2",
                    "authentication": {
                        "type": "oauth",
                        "client_auth_method": "none",
                        "scopes": ["mail.read"],
                        "client_id": static_client_id,
                    },
                    "state": {
                        "tokens": {
                            "access_token": "expired-access-token",
                            "refresh_token": refresh_token,
                            "token_type": "Bearer",
                            "expires_in": 3600,
                        },
                        "client_info": client_info,
                        "token_expires_at": time.time() - 60,
                    },
                },
            }
        }
    )


def test_settings_backed_provider_keeps_stored_state_when_refresh_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    oauth_provider: InMemoryOAuthProvider,
    protected_oauth_mcp_server: str,
    write_backs: list[dict],
):
    """被拒绝的刷新令牌会使连接失败，而不是重新授权。

    FastMCP'的交互回退方案预飞一个回环重定向 URI 安装的客户端从未注册，400错误时，存
    储的状态会注册一个新的客户端并打开浏览器。
    """
    reset_stores()
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *_, **__: opened.append(url))
    try:
        # 排列：服务器不再接受存储的刷新令牌。
        config = _hosted_config(tmp_path)
        get_settings_store(config).save(PersistedSettings())
        client_info = _installed_client(oauth_provider)
        mcp_config = _expired_inline_oauth_server(
            protected_oauth_mcp_server, client_info, "revoked-refresh-token"
        )
        provider = create_settings_backed_mcp_tool_provider(config)

        # 法案
        with pytest.raises(MCPError) as exc_info:
            provider.create_tools(mcp_config, timeout=5.0)

        # 断言：没有浏览器或回调等待，没有新客户端，什么也没有
        # 通过应用服务器保存的凭据发布。
        assert not isinstance(exc_info.value, MCPTimeoutError)
        assert opened == []
        assert list(oauth_provider.clients) == ["installed-client"]
        assert write_backs == []
    finally:
        reset_stores()


def test_settings_backed_provider_does_not_write_back_a_client_it_registers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    protected_oauth_mcp_server: str,
    write_backs: list[dict],
):
    """未经客户端注册而存储的 token 无法刷新。

    FastMCP 在请求授权之前注册一个环回客户端； 该客户端不得到达应用程序服务器。
    """
    reset_stores()
    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *_, **__: opened.append(url))
    try:
        # 安排
        config = _hosted_config(tmp_path)
        get_settings_store(config).save(PersistedSettings())
        mcp_config = _expired_inline_oauth_server(
            protected_oauth_mcp_server, None, "stored-refresh-token"
        )
        provider = create_settings_backed_mcp_tool_provider(config)

        # 法案
        with pytest.raises(MCPError) as exc_info:
            provider.create_tools(mcp_config, timeout=5.0)

        # 断言
        assert not isinstance(exc_info.value, MCPTimeoutError)
        assert opened == []
        assert write_backs == []
    finally:
        reset_stores()


def test_settings_backed_provider_writes_back_tokens_refreshed_on_connect(
    tmp_path: Path,
    oauth_provider: InMemoryOAuthProvider,
    protected_oauth_mcp_server: str,
    write_backs: list[dict],
):
    reset_stores()
    try:
        # 安排：服务器发出的过期访问令牌和刷新令牌。
        config = _hosted_config(tmp_path)
        get_settings_store(config).save(PersistedSettings())
        client_info = _installed_client(oauth_provider)
        oauth_provider.refresh_tokens["issued-refresh-token"] = RefreshToken(
            token="issued-refresh-token",
            client_id="installed-client",
            scopes=["mail.read"],
        )
        mcp_config = _expired_inline_oauth_server(
            protected_oauth_mcp_server, client_info, "issued-refresh-token"
        )
        provider = create_settings_backed_mcp_tool_provider(config)

        # 法案
        with provider.create_tools(mcp_config, timeout=10.0) as client:
            tool_names = [tool.name for tool in client.tools]

        # 断言：与旋转的token连接，返回到
        # 应用程序服务器以及客户端和新的到期。
        assert "read_subject" in tool_names
        state = write_backs[-1]["oauth_state"]
        assert state["tokens"]["refresh_token"] in oauth_provider.refresh_tokens
        assert state["tokens"]["refresh_token"] != "issued-refresh-token"
        assert state["client_info"]["client_id"] == "installed-client"
        assert state["token_expires_at"] > time.time()
    finally:
        reset_stores()


@pytest.mark.parametrize("stored_client", [True, False])
def test_settings_backed_provider_writes_back_tokens_refreshed_for_a_static_client(
    tmp_path: Path,
    oauth_provider: InMemoryOAuthProvider,
    protected_oauth_mcp_server: str,
    write_backs: list[dict],
    stored_client: bool,
):
    """FastMCP 使用环回重写静态客户端的注册
    每次连接时重定向 URI； 其刷新token仍回去。"""
    reset_stores()
    try:
        # 安排
        config = _hosted_config(tmp_path)
        get_settings_store(config).save(PersistedSettings())
        client_info = _installed_client(oauth_provider)
        oauth_provider.refresh_tokens["issued-refresh-token"] = RefreshToken(
            token="issued-refresh-token",
            client_id="installed-client",
            scopes=["mail.read"],
        )
        mcp_config = _expired_inline_oauth_server(
            protected_oauth_mcp_server,
            client_info if stored_client else None,
            "issued-refresh-token",
            static_client_id="installed-client",
        )
        provider = create_settings_backed_mcp_tool_provider(config)

        # 法案
        with provider.create_tools(mcp_config, timeout=10.0) as client:
            tool_names = [tool.name for tool in client.tools]

        # 断言
        assert "read_subject" in tool_names
        state = write_backs[-1]["oauth_state"]
        assert state["tokens"]["refresh_token"] in oauth_provider.refresh_tokens
        assert state["tokens"]["refresh_token"] != "issued-refresh-token"
        assert state["client_info"]["client_id"] == "installed-client"
    finally:
        reset_stores()
