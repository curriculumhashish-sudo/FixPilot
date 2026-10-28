"""FastMCP OAuth客户端在刷新之前发现 token 端点。"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any, Literal
from urllib.parse import parse_qsl

import httpx
from fastmcp.client.auth import OAuth
from mcp.client.auth.utils import (
    build_oauth_authorization_server_metadata_discovery_urls,
    build_protected_resource_metadata_discovery_urls,
    create_client_registration_request,
    create_oauth_metadata_request,
    handle_auth_metadata_response,
    handle_protected_resource_response,
)

from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.exceptions import MCPError


logger = get_logger(__name__)

_DISCOVERY_TIMEOUT = httpx.Timeout(10.0)

_TokenEndpointAuthMethod = Literal["none", "client_secret_post", "client_secret_basic"]

# 最优先考虑的是：公共客户端永远不会被授予机密来保留。
_TOKEN_ENDPOINT_AUTH_METHODS: tuple[_TokenEndpointAuthMethod, ...] = (
    "none",
    "client_secret_post",
    "client_secret_basic",
)


def _preferred_token_endpoint_auth_method(
    supported: list[str] | None,
) -> _TokenEndpointAuthMethod | None:
    for method in _TOKEN_ENDPOINT_AUTH_METHODS:
        if method in (supported or ()):
            return method
    return None


def _without_client_id_when_basic(request: httpx.Request) -> httpx.Request:
    """从基本身份验证请求的表单正文中删除 ``client_id``。

    RFC 6749 第 2.3.1 节禁止将 ``Authorization`` 标头与主体凭据组合，并且严格服务器拒
    绝使用多个身份验证方法的混合。
    """
    if not request.headers.get("Authorization", "").startswith("Basic "):
        return request
    data = dict(parse_qsl(request.content.decode(), keep_blank_values=True))
    data.pop("client_id", None)
    headers = request.headers.copy()
    headers.pop("Content-Length", None)
    return httpx.Request(request.method, request.url, data=data, headers=headers)


class MCPOAuth(OAuth):
    """FastMCP ``OAuth``，其 token 刷新以发现的端点为目标。

    上游 ``OAuthClientProvider`` 刷新过期的访问令牌在发送请求之前，但发现授权服务器的
    元数据仅存在于其401分支中，并且永远不会持久化。 每一场
    对话都会构建一个新的客户端，所以 ``_refresh_token``  退而求其次
    ``<MCP server origin>/token``，这对于 GitLab (``/oauth/token``) 和 Atlassian (
    ``/v1/token``) 等提供者来说是错误的。 接下来的 404 会删除 token 并启动交互式浏览
    器流程，该流程无法在沙箱内完成。

    ``_refresh_token`` 运行在上游的上下文锁之后
    ``_initialize()`` 恢复了存储的 token 和过期时间，因此仅在实际尝试刷新时才会发生发
    现。

    动态客户端注册需要授权服务器通告的 token 端点身份验证方法，首选公共客户端。 上游
    发送 None，因此服务器回退到默认值 RFC 7591
    ``client_secret_basic``并发出机密。 token 确实使用基本身份验证的请求将
    ``client_id`` 排除在正文之外，上游始终包含该请求
    ，而严格服务器会拒绝该请求。
    """

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        async with aclosing(super().async_auth_flow(request)) as flow:
            outgoing = await anext(flow)
            while True:
                response = yield self._with_supported_auth_method(outgoing)
                try:
                    outgoing = await flow.asend(response)
                except StopAsyncIteration:
                    return

    def _with_supported_auth_method(self, request: httpx.Request) -> httpx.Request:
        """围绕支持的身份验证方法重建注册请求。

        任何其他请求、显式配置的方法和通告未知方法的服务器都不会发生变化。
        """
        context = self.context
        if (
            context.client_info is not None
            or context.oauth_metadata is None
            or context.client_metadata.token_endpoint_auth_method is not None
        ):
            return request
        method = _preferred_token_endpoint_auth_method(
            context.oauth_metadata.token_endpoint_auth_methods_supported
        )
        if method is None or request.url != self._registration_request().url:
            return request
        context.client_metadata.token_endpoint_auth_method = method
        return self._registration_request()

    def _registration_request(self) -> httpx.Request:
        return create_client_registration_request(
            self.context.oauth_metadata,
            self.context.client_metadata,
            self.context.get_authorization_base_url(self.context.server_url),
        )

    async def _exchange_token_authorization_code(
        self,
        auth_code: str,
        code_verifier: str,
        *,
        token_data: dict[str, Any] | None = None,
    ) -> httpx.Request:
        request = await super()._exchange_token_authorization_code(
            auth_code, code_verifier, token_data=token_data
        )
        return _without_client_id_when_basic(request)

    async def _refresh_token(self) -> httpx.Request:
        if self.context.oauth_metadata is None:
            await self._discover_oauth_metadata()
        return _without_client_id_when_basic(await super()._refresh_token())

    async def _discover_oauth_metadata(self) -> None:
        """填充资源和授权-服务器元数据。

        镜像上游在 401 上执行的发现（首先是受保护的资源元数据，然后是授权服务器元数据
        ，具有相同的回退方案 URL 列表）。 网络故障仅记录：刷新然后转到上游的
        默认值端点，与以前完全相同。
        """
        server_url = self.context.server_url
        try:
            async with self.httpx_client_factory(timeout=_DISCOVERY_TIMEOUT) as client:
                for url in build_protected_resource_metadata_discovery_urls(
                    None, server_url
                ):
                    response = await client.send(create_oauth_metadata_request(url))
                    prm = await handle_protected_resource_response(response)
                    if prm is None:
                        continue
                    await self._validate_resource_match(prm)
                    self.context.protected_resource_metadata = prm
                    # ``authorization_servers`` 的最小长度为 1。
                    self.context.auth_server_url = str(prm.authorization_servers[0])
                    break

                for url in build_oauth_authorization_server_metadata_discovery_urls(
                    self.context.auth_server_url, server_url
                ):
                    response = await client.send(create_oauth_metadata_request(url))
                    ok, metadata = await handle_auth_metadata_response(response)
                    if not ok:
                        break
                    if metadata is not None:
                        self.context.oauth_metadata = metadata
                        break
        except httpx.HTTPError as exc:
            logger.warning(
                "OAuth metadata discovery failed for %s; refreshing against the "
                "default token endpoint: %s",
                server_url,
                exc,
            )


class NonInteractiveMCPOAuth(MCPOAuth):
    """``MCPOAuth`` 仅使用存储的 token 并刷新它们。

    当没有存储 token 可用的 FastMCP 启动新进程授权它预检查了授权  URL 使用回环重定向
    URI, 如果服务器拒绝了那个 URI 它清除了解析 tok
    en 在打开浏览器之前，存储并注册一个新的客户端。 没有人能为未连接的客户端完成那个
    流程，因此它会失败并留下用户存储的状态，让用户重新授权。
    """

    async def redirect_handler(self, authorization_url: str) -> None:  # noqa: ARG002
        raise MCPError(
            f"MCP server {self.mcp_url} must be authorized again: its stored "
            "OAuth tokens are missing or could not be refreshed."
        )
