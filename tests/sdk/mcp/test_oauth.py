"""测试 for ``MCPOAuth``过期的 token 刷新  token  端点的授权服务器广播，注册要求一个
token  端点支持的认证方法，以及使用基本认证的 t
oken requests leave
``client_id`` 脱离身体。"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from key_value.aio.stores.memory import MemoryStore

from openhands.sdk.mcp.exceptions import MCPError
from openhands.sdk.mcp.oauth import MCPOAuth, NonInteractiveMCPOAuth


pytestmark = pytest.mark.filterwarnings("ignore:Using in-memory token storage")

MCP_URL = "https://gitlab.example/api/v4/mcp"
TOKEN_ENDPOINT = "https://gitlab.example/oauth/token"
REGISTRATION_ENDPOINT = "https://gitlab.example/oauth/register"
RESOURCE_METADATA = {
    "resource": MCP_URL,
    "authorization_servers": ["https://gitlab.example"],
}
SERVER_METADATA = {
    "issuer": "https://gitlab.example",
    "authorization_endpoint": "https://gitlab.example/oauth/authorize",
    "token_endpoint": TOKEN_ENDPOINT,
    "registration_endpoint": REGISTRATION_ENDPOINT,
    "response_types_supported": ["code"],
}
CLIENT_INFO = {
    "client_id": "client-id",
    "redirect_uris": ["https://app.example/callback"],
    "token_endpoint_auth_method": "none",
}
BASIC_CLIENT_INFO = {
    **CLIENT_INFO,
    "client_secret": "client-secret",
    "token_endpoint_auth_method": "client_secret_basic",
}
POST_CLIENT_INFO = {
    **BASIC_CLIENT_INFO,
    "token_endpoint_auth_method": "client_secret_post",
}


async def _stored_state(
    expires_at: float | None, client_info: dict[str, Any] = CLIENT_INFO
) -> MemoryStore:
    """一个存储完成安装后留下的东西的商店。

    ``expires_at=None``存储没有任何token的注册客户端。
    """
    store = MemoryStore()
    if expires_at is not None:
        await store.put(
            key=f"{MCP_URL}/tokens",
            value={
                "access_token": "stored-access-token",
                "refresh_token": "stored-refresh-token",
                "token_type": "Bearer",
                "expires_in": 7200,
            },
            collection="mcp-oauth-token",
        )
        await store.put(
            key=f"{MCP_URL}/token_expiry",
            value={"expires_at": expires_at},
            collection="mcp-oauth-token-expiry",
        )
    await store.put(
        key=f"{MCP_URL}/client_info",
        value=client_info,
        collection="mcp-oauth-client-info",
    )
    return store


def _authorization_server(
    metadata: dict[str, Any],
) -> Callable[[httpx.Request], httpx.Response]:
    """为``metadata``服务发现； MCP 端点本身需要 OAuth。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/mcp":
            return httpx.Response(401)
        if request.url.path == "/.well-known/oauth-protected-resource/api/v4/mcp":
            return httpx.Response(200, json=RESOURCE_METADATA)
        if request.url.path == "/.well-known/oauth-authorization-server":
            return httpx.Response(200, json=metadata)
        return httpx.Response(404)

    return handler


_discovery = _authorization_server(SERVER_METADATA)


def _oauth(
    store: MemoryStore,
    handler: Callable[[httpx.Request], httpx.Response],
    oauth_class: type[MCPOAuth] = MCPOAuth,
    **kwargs: Any,
) -> tuple[MCPOAuth, list[str]]:
    """``MCPOAuth``，其发现客户端由 ``handler`` 提供服务。"""
    requested: list[str] = []

    def recording(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return handler(request)

    def factory(headers=None, timeout=None, auth=None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(recording),
            headers=headers,
            timeout=timeout,
            auth=auth,
        )

    oauth = oauth_class(
        mcp_url=MCP_URL, token_storage=store, client_name="test", **kwargs
    )
    oauth.httpx_client_factory = factory
    return oauth, requested


def _consent(oauth: MCPOAuth) -> None:
    """代表浏览器：返回我们发送的状态代码。"""
    states: list[str] = []

    async def redirect(authorization_url: str) -> None:
        states.append(parse_qs(urlparse(authorization_url).query)["state"][0])

    async def callback() -> tuple[str, str | None]:
        return "auth-code", states[-1]

    oauth.context.redirect_handler = redirect
    oauth.context.callback_handler = callback


async def _first_request(oauth: MCPOAuth) -> httpx.Request:
    """auth 流程为 MCP 调用发出的第一个请求。"""
    flow = oauth.async_auth_flow(httpx.Request("POST", MCP_URL, json={}))
    try:
        return await flow.__anext__()
    finally:
        await flow.aclose()


async def _serve_flow(
    oauth: MCPOAuth, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """回答 auth 流程为 MCP 调用发出的每个请求。"""
    flow = oauth.async_auth_flow(httpx.Request("POST", MCP_URL, json={}))
    try:
        request = await anext(flow)
        while True:
            request = await flow.asend(handler(request))
    except StopAsyncIteration:
        pass
    finally:
        await flow.aclose()


async def _request_to(
    oauth: MCPOAuth, handler: Callable[[httpx.Request], httpx.Response], url: str
) -> httpx.Request:
    """驱动身份验证流程，用 ``handler`` 应答，直到它请求 ``url``。"""
    flow = oauth.async_auth_flow(httpx.Request("POST", MCP_URL, json={}))
    try:
        request = await anext(flow)
        while str(request.url) != url:
            response = handler(request)
            response.request = request
            request = await flow.asend(response)
        return request
    finally:
        await flow.aclose()


def _form(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(request.content.decode(), keep_blank_values=True)


@pytest.mark.asyncio
async def test_expired_token_refreshes_against_the_discovered_endpoint():
    # 安排
    oauth, requested = _oauth(await _stored_state(time.time() - 60), _discovery)

    # 法案
    request = await _first_request(oauth)

    # 断言
    assert (request.method, str(request.url)) == ("POST", TOKEN_ENDPOINT)
    assert b"grant_type=refresh_token" in request.content
    assert requested == [
        "https://gitlab.example/.well-known/oauth-protected-resource/api/v4/mcp",
        "https://gitlab.example/.well-known/oauth-authorization-server",
    ]


@pytest.mark.asyncio
async def test_refresh_falls_back_to_the_default_endpoint_when_discovery_fails():
    # 安排
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unreachable", request=request)

    oauth, _ = _oauth(await _stored_state(time.time() - 60), unreachable)

    # 法案
    request = await _first_request(oauth)

    # 断言：上游的猜测，与没有发现步骤时完全相同。
    assert (request.method, str(request.url)) == (
        "POST",
        "https://gitlab.example/token",
    )
    assert b"grant_type=refresh_token" in request.content


@pytest.mark.asyncio
async def test_valid_token_is_sent_without_discovery_or_refresh():
    # 安排
    oauth, requested = _oauth(await _stored_state(time.time() + 3600), _discovery)

    # 法案
    request = await _first_request(oauth)

    # 断言
    assert str(request.url) == MCP_URL
    assert request.headers["Authorization"] == "Bearer stored-access-token"
    assert requested == []


@pytest.mark.asyncio
async def test_non_interactive_client_fails_instead_of_authorizing_again():
    # 排列：服务器拒绝存储的刷新令牌，然后
    # 未经身份验证的 MCP 调用。
    store = await _stored_state(time.time() - 60)
    requested: list[str] = []

    def server(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if str(request.url) == TOKEN_ENDPOINT:
            return httpx.Response(400, json={"error": "invalid_grant"})
        if str(request.url) == MCP_URL:
            return httpx.Response(401)
        return _discovery(request)

    oauth, _ = _oauth(store, server, NonInteractiveMCPOAuth)

    # 法案
    with pytest.raises(MCPError):
        await _serve_flow(oauth, server)

    # 断言：没有授权请求或客户端注册，并且
    # 存储的状态留给用户通过再次授权来替换。
    paths = {httpx.URL(url).path for url in requested}
    assert not paths & {"/oauth/authorize", "/register"}
    assert await store.get(key=f"{MCP_URL}/tokens", collection="mcp-oauth-token")
    assert await store.get(
        key=f"{MCP_URL}/client_info", collection="mcp-oauth-client-info"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("supported", "requested"),
    [
        (["client_secret_basic", "client_secret_post", "none"], "none"),
        (["client_secret_post", "client_secret_basic"], "client_secret_post"),
        (["private_key_jwt"], None),
    ],
)
async def test_registration_requests_a_supported_token_endpoint_auth_method(
    supported: list[str], requested: str | None
):
    # 安排
    server = _authorization_server(
        {**SERVER_METADATA, "token_endpoint_auth_methods_supported": supported}
    )
    oauth, _ = _oauth(MemoryStore(), server)

    # 法案
    registration = await _request_to(oauth, server, REGISTRATION_ENDPOINT)

    # 断言
    body = json.loads(registration.content)
    assert body.get("token_endpoint_auth_method") == requested
    assert body["client_name"] == "test"


@pytest.mark.asyncio
async def test_registration_keeps_an_explicitly_configured_auth_method():
    # 安排
    server = _authorization_server(
        {
            **SERVER_METADATA,
            "token_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
        }
    )
    oauth, _ = _oauth(
        MemoryStore(),
        server,
        additional_client_metadata={
            "token_endpoint_auth_method": "client_secret_basic"
        },
    )

    # 法案
    registration = await _request_to(oauth, server, REGISTRATION_ENDPOINT)

    # 断言
    body = json.loads(registration.content)
    assert body["token_endpoint_auth_method"] == "client_secret_basic"


@pytest.mark.asyncio
async def test_static_client_is_used_as_configured_without_registration():
    # 安排：服务器会分发一个公共客户端，但我们的是固定的。
    server = _authorization_server(
        {**SERVER_METADATA, "token_endpoint_auth_methods_supported": ["none"]}
    )
    oauth, _ = _oauth(
        MemoryStore(), server, client_id="static-id", client_secret="static-secret"
    )
    _consent(oauth)

    # 行动：注册尝试将出现 404 错误并中止流程。
    token = await _request_to(oauth, server, TOKEN_ENDPOINT)

    # 断言
    body = _form(token)
    assert "Authorization" not in token.headers
    assert body["client_id"] == ["static-id"]
    assert body["client_secret"] == ["static-secret"]


@pytest.mark.asyncio
async def test_basic_auth_token_exchange_sends_client_id_only_in_the_header():
    # 安排
    oauth, _ = _oauth(await _stored_state(None, BASIC_CLIENT_INFO), _discovery)
    _consent(oauth)

    # 法案
    token = await _request_to(oauth, _discovery, TOKEN_ENDPOINT)

    # 断言
    credentials = base64.b64encode(b"client-id:client-secret").decode()
    assert token.headers["Authorization"] == f"Basic {credentials}"
    body = _form(token)
    assert "client_id" not in body
    assert "client_secret" not in body
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["auth-code"]
    assert {"code_verifier", "redirect_uri"} <= body.keys()
    assert token.headers["Content-Length"] == str(len(token.content))


@pytest.mark.asyncio
async def test_basic_auth_refresh_sends_client_id_only_in_the_header():
    # 安排
    oauth, _ = _oauth(
        await _stored_state(time.time() - 60, BASIC_CLIENT_INFO), _discovery
    )

    # 法案
    request = await _first_request(oauth)

    # 断言
    assert str(request.url) == TOKEN_ENDPOINT
    assert request.headers["Authorization"].startswith("Basic ")
    body = _form(request)
    assert "client_id" not in body
    assert body["grant_type"] == ["refresh_token"]
    assert body["refresh_token"] == ["stored-refresh-token"]
    assert request.headers["Content-Length"] == str(len(request.content))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_info", "secret"),
    [(POST_CLIENT_INFO, ["client-secret"]), (CLIENT_INFO, None)],
)
async def test_body_authenticated_clients_keep_client_id_in_the_body(
    client_info: dict[str, Any], secret: list[str] | None
):
    # 安排
    oauth, _ = _oauth(await _stored_state(time.time() - 60, client_info), _discovery)

    # 法案
    request = await _first_request(oauth)

    # 断言
    assert "Authorization" not in request.headers
    body = _form(request)
    assert body["client_id"] == ["client-id"]
    assert body.get("client_secret") == secret
