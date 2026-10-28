"""MCP 积分的实用函数。"""

import asyncio
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

import httpx
import mcp.types
from fastmcp.client.auth import OAuth
from fastmcp.client.logging import LogMessage
from fastmcp.client.messages import MessageHandler
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.mcp_config import MCPConfig as FastMCPConfig, RemoteMCPServer
from key_value.aio.protocols import AsyncKeyValue
from mcp.shared._httpx_utils import create_mcp_http_client

from openhands.sdk.logger import get_logger
from openhands.sdk.mcp.client import MCPClient, ToolsReconciledCallback
from openhands.sdk.mcp.config import (
    MCPOAuthAuthCredential,
    MCPOAuthAuthentication,
    MCPServer,
    enabled_mcp_servers,
    to_fastmcp_mcp_config,
)
from openhands.sdk.mcp.exceptions import MCPTimeoutError
from openhands.sdk.mcp.oauth import MCPOAuth
from openhands.sdk.mcp.tool import MCPToolDefinition


logger = get_logger(__name__)
LOGGING_LEVEL_MAP = logging.getLevelNamesMapping()

MCPOAuthFactory = Callable[
    [str, MCPServer, MCPOAuthAuthCredential, AsyncKeyValue | None],
    OAuth | None,
]

# 向后兼容回调仅报告新添加的工具。
ToolsChangedCallback = Callable[[Sequence[MCPToolDefinition]], None]


class MCPToolProvider(Protocol):
    """仅运行时 MCP 工具物化器。"""

    def create_tools(
        self,
        mcp_config: dict[str, MCPServer],
        timeout: float = 30.0,
        *,
        on_tools_changed: ToolsChangedCallback | None = None,
        on_tools_reconciled: ToolsReconciledCallback | None = None,
    ) -> MCPClient: ...


class DefaultMCPToolProvider:
    """运行时 MCP 工具物化器，无需额外的持久化挂钩。"""

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
            on_tools_changed=on_tools_changed,
            on_tools_reconciled=on_tools_reconciled,
        )


def provider_supports_on_tools_reconciled(provider: MCPToolProvider) -> bool:
    """``provider.create_tools``是否接受``on_tools_reconciled``。

    在此参数存在之前编写的自定义 ``MCPToolProvider`` 实现仅接受 ``on_tools_changed``
    ； 将 new 关键字传递给他们会引发
    ``TypeError``。 调用者应首先检查这一点，并忽略不支持它的提供商的关键字。
    """
    try:
        params = inspect.signature(provider.create_tools).parameters
    except (TypeError, ValueError):
        return False
    return "on_tools_reconciled" in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )


def _oauth_auth_from_authentication_config(
    authentication: MCPOAuthAuthentication | None,
    *,
    mcp_oauth_token_storage: AsyncKeyValue | None = None,
    mcp_oauth_class: type[MCPOAuth] = MCPOAuth,
) -> OAuth | None:
    """从显式 SDK MCP 身份验证元数据构建 FastMCP OAuth 身份验证。"""
    if authentication is None:
        return None

    additional_client_metadata = dict(authentication.additional_client_metadata or {})
    client_auth_method = authentication.client_auth_method
    if client_auth_method is not None:
        additional_client_metadata["token_endpoint_auth_method"] = client_auth_method

    return mcp_oauth_class(
        scopes=authentication.scopes,
        client_name=authentication.client_name or "FastMCP Client",
        token_storage=mcp_oauth_token_storage,
        additional_client_metadata=additional_client_metadata or None,
        client_metadata_url=authentication.client_metadata_url,
        client_id=authentication.client_id,
        client_secret=authentication.client_secret.get_secret_value()
        if authentication.client_secret is not None
        else None,
    )


class _PackageRemoteMCPServer(RemoteMCPServer):
    """包声明的远程服务器，其标头保留在其自己的源上。

    智能体插件§7.2.1：配置的标头不得遵循重定向到不同来源的重定向。 httpx 只在那里删除
     ``Authorization``，因此该服务器的 HTTP 客户端
    会从离开配置源的任何请求中删除每个配置的标头名称。
    """

    def to_transport(self):  # type: ignore[override]
        transport = super().to_transport()
        if isinstance(transport, StreamableHttpTransport) and self.headers:
            transport.httpx_client_factory = _origin_bound_client_factory(
                self.url, tuple(self.headers)
            )
        return transport


def _origin_bound_client_factory(url: str, header_names: tuple[str, ...]):
    origin = _origin(httpx.URL(url))

    async def drop_headers_off_origin(request: httpx.Request) -> None:
        # 在 httpx 将前一个请求的标头复制到下一个请求之后，请求挂钩在每个重定向跃点上运
        # 行。
        #
        if _origin(request.url) != origin:
            for name in header_names:
                request.headers.pop(name, None)

    def factory(
        headers: dict[str, str] | None = None,
        timeout: httpx.Timeout | None = None,
        auth: httpx.Auth | None = None,
        **_: object,
    ) -> httpx.AsyncClient:
        client = create_mcp_http_client(headers=headers, timeout=timeout, auth=auth)
        client.event_hooks = {"request": [drop_headers_off_origin], "response": []}
        return client

    return factory


def _origin(url: httpx.URL) -> tuple[str, str, int | None]:
    default_port = {"http": 80, "https": 443}.get(url.scheme)
    return url.scheme, url.host, url.port or default_port


def _prepare_mcp_config(
    mcp_config: dict[str, MCPServer],
    *,
    mcp_oauth_token_storage: AsyncKeyValue | None = None,
    mcp_oauth_factory: MCPOAuthFactory | None = None,
    mcp_oauth_class: type[MCPOAuth] = MCPOAuth,
) -> FastMCPConfig:
    """验证 MCP 配置并应用显式 OpenHands 运行时身份验证元数据。"""
    prepared = FastMCPConfig.model_validate(to_fastmcp_mcp_config(mcp_config))

    for server_name, server_spec in mcp_config.items():
        server = prepared.mcpServers.get(server_name)
        if server_spec.literal_values and isinstance(server, RemoteMCPServer):
            prepared.mcpServers[server_name] = _PackageRemoteMCPServer.model_validate(
                server.model_dump()
            )

    for server_name, server_spec in mcp_config.items():
        auth = server_spec.auth
        if not isinstance(auth, MCPOAuthAuthCredential):
            continue
        server = prepared.mcpServers.get(server_name)
        if not isinstance(server, RemoteMCPServer) or server.auth != "oauth":
            continue
        oauth_auth = (
            mcp_oauth_factory(
                server_name,
                server_spec,
                auth,
                mcp_oauth_token_storage,
            )
            if mcp_oauth_factory is not None
            else _oauth_auth_from_authentication_config(
                auth.authentication,
                mcp_oauth_token_storage=mcp_oauth_token_storage,
                mcp_oauth_class=mcp_oauth_class,
            )
        )
        if oauth_auth is not None:
            server.auth = oauth_auth
        elif mcp_oauth_token_storage is not None:
            server.auth = mcp_oauth_class(token_storage=mcp_oauth_token_storage)

    return prepared


def _require_native_mcp_config(
    mcp_config: Mapping[str, MCPServer],
) -> dict[str, MCPServer]:
    if not isinstance(mcp_config, Mapping):
        raise TypeError(
            "create_mcp_tools expects native MCP servers: dict[str, MCPServer]. "
            "Use coerce_mcp_config() at external config boundaries."
        )

    invalid = [
        name
        for name, server in mcp_config.items()
        if not isinstance(name, str) or not isinstance(server, MCPServer)
    ]
    if invalid:
        raise TypeError(
            "create_mcp_tools expects native MCP servers: dict[str, MCPServer]. "
            "Use coerce_mcp_config() at external config boundaries."
        )
    return dict(mcp_config)


async def log_handler(message: LogMessage):
    """
    处理来自 MCP 服务器的传入日志并将其转发到标准 Python 日志系统。
    """
    msg = message.data.get("msg")
    extra = message.data.get("extra")

    # 将 MCP 日志级别转换为 Python 日志级别
    level = LOGGING_LEVEL_MAP.get(message.level.upper(), logging.INFO)

    # 使用标准日志库记录消息
    logger.log(level, msg, extra=extra)


async def _connect_and_list_tools(client: MCPClient) -> None:
    """连接到 MCP 服务器并填充 client._tools。"""
    await client.connect()
    await _refresh_tools(client)


async def _refresh_tools(
    client: MCPClient,
    on_tools_changed: ToolsChangedCallback | None = None,
    on_tools_reconciled: ToolsReconciledCallback | None = None,
) -> None:
    """重新列出服务器中的工具并协调 ``client._tools``。

    在初始连接后以及每当服务器发送一个
    ``notifications/tools/list_changed`` 通知。 当
    ``on_tools_changed`` 保留原始的仅添加内容回调合同。
    ``on_tools_reconciled`` 接收完整的当前快照，因此正在运行的智能体可以添加、替换和
    删除该客户端拥有的工具。
    """
    mcp_type_tools: list[mcp.types.Tool] = await client.list_tools()
    existing_by_name = {tool.name: tool for tool in client._tools}
    server_names = {mcp_tool.name for mcp_tool in mcp_type_tools}

    reconciled: list[MCPToolDefinition] = []
    added: list[MCPToolDefinition] = []
    updated: list[MCPToolDefinition] = []
    for mcp_tool in mcp_type_tools:
        prior = existing_by_name.get(mcp_tool.name)
        if prior is not None and prior.mcp_tool == mcp_tool:
            reconciled.append(prior)
            continue
        tool_sequence = MCPToolDefinition.create(mcp_tool=mcp_tool, mcp_client=client)
        reconciled.extend(tool_sequence)
        if prior is None:
            added.extend(tool_sequence)
        else:
            updated.extend(tool_sequence)

    # 删除服务器不再宣传的工具。 以原子方式重新分配，以便迭代 client.tools 的并发读者永
    # 远不会观察更新中期状态。
    #
    removed = [
        tool.name for name, tool in existing_by_name.items() if name not in server_names
    ]
    if removed:
        logger.info("MCP server removed tools: %s", ", ".join(sorted(removed)))
    if updated:
        logger.info(
            "MCP server updated tools: %s",
            ", ".join(sorted(tool.name for tool in updated)),
        )
    client._tools = reconciled

    if added and on_tools_changed is not None:
        try:
            on_tools_changed(added)
        except Exception:
            logger.warning(
                "on_tools_changed callback failed for %d new MCP tools",
                len(added),
                exc_info=True,
            )

    if (added or updated or removed) and on_tools_reconciled is not None:
        try:
            on_tools_reconciled(client, reconciled)
        except Exception:
            logger.warning(
                "on_tools_reconciled callback failed for MCP tool refresh",
                exc_info=True,
            )


class _ToolListChangedHandler(MessageHandler):
    """刷新 ``tools/list_changed`` 上的工具的消息处理程序。

    一些 MCP 服务器 (e.g. Datadog的托管服务器）使用渐进式
    disclosure: 他们在连接时公开一个小型网关工具集，并且
    仅在调用技能加载工具后才注册其他工具，并用 ``notifications/tools/list_changed``
    表示更改。 如果不订阅，客户就永远不会重新列出
    ，并且新工具将保持不可见。
    """

    def __init__(
        self,
        client: MCPClient,
        on_tools_changed: ToolsChangedCallback | None = None,
    ):
        super().__init__()
        self._client = client
        self._on_tools_changed = on_tools_changed
        self._refresh_lock = asyncio.Lock()
        self._refresh_tasks: set[asyncio.Task[None]] = set()

    async def on_tool_list_changed(
        self,
        message: mcp.types.ToolListChangedNotification,  # noqa: ARG002
    ) -> None:
        client = self._client
        if client._closed:
            return
        logger.debug("MCP tools/list_changed received; refreshing tools")
        # 保持接收循环空闲以处理 list_tools 响应。
        task = asyncio.create_task(self._refresh_tools())
        self._refresh_tasks.add(task)
        task.add_done_callback(self._refresh_tasks.discard)

    async def _refresh_tools(self) -> None:
        client = self._client
        try:
            async with self._refresh_lock:
                if client._closed:
                    return
                await _refresh_tools(
                    client,
                    self._on_tools_changed,
                    client._tools_reconciled_callback,
                )
        except Exception:
            logger.warning(
                "Failed to refresh MCP tools after list_changed notification",
                exc_info=True,
            )


def create_mcp_tools(
    mcp_config: dict[str, MCPServer],
    timeout: float = 30.0,
    *,
    on_tools_changed: ToolsChangedCallback | None = None,
    on_tools_reconciled: ToolsReconciledCallback | None = None,
    mcp_oauth_token_storage: AsyncKeyValue | None = None,
    mcp_oauth_factory: MCPOAuthFactory | None = None,
    mcp_oauth_class: type[MCPOAuth] = MCPOAuth,
) -> MCPClient:
    """从 OpenHands 本机 MCP 服务器设置创建 MCP 工具。

    返回一个工具已填充的MCPClient。 使用为上下文管理器。

        with create_mcp_tools(mcp_config) as client:
            for tool in client.tools:
                # 使用工具
        # 连接自动关闭

    每当服务器发出更改信号时，客户端就会订阅 ``notifications/tools/list_changed`` 并
    协调其工具列表。 当
    提供了 ``on_tools_changed``，客户端使用新添加的工具定义调用它，保留原始的回调合约
    。 当
    提供``on_tools_reconciled``，它接收客户端并在添加、更新或删除后完成当前工具快照。
     回调在客户端的后台事件循环线程上运行并且必须是线程安全。
    """
    mcp_config = _require_native_mcp_config(mcp_config)
    requested = mcp_config
    mcp_config = enabled_mcp_servers(mcp_config)
    if requested and not mcp_config:
        raise ValueError(
            "All configured MCP servers are disabled: "
            f"{', '.join(sorted(requested))}. Enable at least one, or skip "
            "the call entirely."
        )
    config = _prepare_mcp_config(
        mcp_config,
        mcp_oauth_token_storage=mcp_oauth_token_storage,
        mcp_oauth_factory=mcp_oauth_factory,
        mcp_oauth_class=mcp_oauth_class,
    )
    handler = _ToolListChangedHandler(
        client=None,  # type: ignore[arg-type]
        on_tools_changed=on_tools_changed,
    )
    client = MCPClient(config, log_handler=log_handler, message_handler=handler)
    handler._client = client
    client._tools_reconciled_callback = on_tools_reconciled

    try:
        client.call_async_from_sync(
            _connect_and_list_tools, timeout=timeout, client=client
        )
    except TimeoutError as e:
        client.sync_close()
        # 从配置中提取服务器名称以获得更好的错误消息
        server_names = (
            list(config.mcpServers.keys()) if config.mcpServers else ["unknown"]
        )
        error_msg = (
            f"MCP tool listing timed out after {timeout} seconds.\n"
            f"MCP servers configured: {', '.join(server_names)}\n\n"
            "Possible solutions:\n"
            "  1. Increase the timeout value (default is 30 seconds)\n"
            "  2. Check if the MCP server is running and responding\n"
            "  3. Verify network connectivity to the MCP server\n"
        )
        raise MCPTimeoutError(
            error_msg, timeout=timeout, config=config.model_dump()
        ) from e
    except BaseException:
        try:
            client.sync_close()
        except Exception as close_exc:
            logger.warning(
                "Failed to close MCP client during error cleanup", exc_info=close_exc
            )
        raise

    logger.info("Created %d MCP tools", len(client.tools))
    return client
