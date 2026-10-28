"""MCP OpenHands SDK 的路由器。

暴露了一个单一的端点，``POST /api/mcp/test``，允许客户端在隔离环境中验证候选 MCP 服务
器配置 -- 在持久化到设置之前，否则在会话开始时就会出现错
误配置（并且在智能体初始化时显而易见，表现为一个噪音堆栈跟踪，导致初始化失败）。

的端点它不会修改服务器状态或修改存储的设置：它启动了 MCP 连接，列出已发布的工具，可选
地调用一个用户选择的工具``tool_call``然后断开连接。 可选的工具调用存
在是因为列出工具并未测试过凭据许多服务器只使用内部工具处理器（e.g. Slack MCP 服务器启
动正常，但使用了无效的  token); callers must pi
ck a 只读 tool. 对于 OAuth MCP 在探测过程中获取的任何服务器、令牌/客户端元数据都将包
含在成功响应中 ``oauth_state`` 字段以便于调用者
使用持久化通过设置 API 在测试服务器的 ``auth.state``.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

import httpx
import mcp.types
from fastapi import APIRouter, HTTPException, Request
from fastmcp.client.auth.oauth import ClientNotFoundError, OAuth
from pydantic import BaseModel, Field, model_validator

from openhands.agent_server._secrets_exposure import get_cipher
from openhands.agent_server.mcp_oauth_store import (
    InMemoryMCPOAuthTokenStore,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.mcp import create_mcp_tools
from openhands.sdk.mcp.client import MCPClient
from openhands.sdk.mcp.config import (
    MCPAuthCredential,
    MCPOAuthAuthCredential,
    MCPOAuthAuthentication,
    MCPOAuthStateResponse,
    MCPServer,
)
from openhands.sdk.mcp.exceptions import MCPError, MCPTimeoutError
from openhands.sdk.mcp.oauth import MCPOAuth
from openhands.sdk.utils.cipher import Cipher


logger = get_logger(__name__)

mcp_router = APIRouter(prefix="/mcp", tags=["MCP"])


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------
#
# 我们接受一个单一的MCPServer，而不是完整的MCP服务器映射。 这个UI流（“添加一个新的MCP服
# 务器”）一次验证一个服务器。 该路由仅在运行时边界将其包装在临时映射中。
#

_DEFAULT_SERVER_NAME = "test-server"
_OAUTH_PROBE_JOB_TTL_SECONDS = 15 * 60


class _StdioMCPServerSpec(BaseModel):
    """传统 stdio MCP 服务器规范已被公众接受 REST API。"""

    type: Literal["stdio"] = "stdio"
    command: str = Field(..., min_length=1, description="Executable to invoke")
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None

    def to_mcp_server(self) -> MCPServer:
        return MCPServer.model_validate(
            {
                "transport": "stdio",
                "command": self.command,
                "args": self.args,
                "env": self.env,
                "cwd": self.cwd,
            }
        )


class _RemoteMCPServerSpec(BaseModel):
    """传统远程 MCP 服务器规范已被公众接受 REST API。"""

    type: Literal["http", "shttp", "streamable-http", "sse"]
    url: str = Field(..., min_length=1)
    headers: dict[str, str] = Field(default_factory=dict)
    auth: MCPAuthCredential | None = None
    timeout: float | None = None
    sse_read_timeout: float | None = None
    keep_alive: bool | None = None

    @model_validator(mode="after")
    def _reject_ambiguous_auth(self) -> _RemoteMCPServerSpec:
        if self.auth is not None and any(
            name.lower() == "authorization" for name in self.headers
        ):
            raise ValueError(
                "'auth' cannot be combined with an explicit top-level "
                "'Authorization' header; use auth.strategy='header' instead."
            )
        return self

    def to_mcp_server(self) -> MCPServer:
        transport = "http" if self.type == "shttp" else self.type
        data: dict[str, Any] = {
            "url": self.url,
            "transport": transport,
            "headers": self.headers,
            "timeout": self.timeout,
            "sse_read_timeout": self.sse_read_timeout,
            "keep_alive": self.keep_alive,
        }
        if self.auth is not None:
            data["auth"] = self.auth
        return MCPServer.model_validate(data)


MCPTestServerSpec = Annotated[
    _StdioMCPServerSpec | _RemoteMCPServerSpec,
    Field(discriminator="type"),
]


class MCPToolCallSpec(BaseModel):
    """作为连接测试的一部分运行的单个工具调用。

    列出工具不会调用凭据个服务器，这些服务器只有工具处理器使用，因此调用者在列出成功
    后可以为一个工具命名并调用它。 调用者负责选择只读工具； 端点逐字执行它。
    """

    name: str = Field(..., min_length=1, description="Name of the tool to invoke")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments passed to the tool unchanged.",
    )


class MCPTestRequest(BaseModel):
    """``POST /api/mcp/test`` 的主体。"""

    name: str = Field(
        default=_DEFAULT_SERVER_NAME,
        min_length=1,
        max_length=128,
        description=(
            "Name to use for the server inside the temporary MCP server map. "
            "Only affects error messages -- does not need to match any "
            "persisted setting."
        ),
    )
    server: MCPTestServerSpec
    timeout: float = Field(
        default=15.0,
        gt=0,
        le=120,
        description="Seconds to wait for connection + tools/list to complete.",
    )
    tool_call: MCPToolCallSpec | None = Field(
        default=None,
        description=(
            "Optional read-only tool to invoke after listing succeeds, so "
            "callers can verify credentials the server only exercises on "
            "tool invocation. Its outcome is reported verbatim in "
            "`tool_result` without affecting `ok`."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_native_server_transport(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        server = value.get("server")
        if not isinstance(server, dict):
            return value
        if "authentication" in server:
            raise ValueError(
                "OAuth authentication metadata belongs under auth.authentication."
            )
        if "type" in server:
            return value
        normalized = dict(value)
        normalized_server = dict(server)
        transport = normalized_server.pop("transport", None)
        if transport is None:
            transport = "stdio" if "command" in normalized_server else "http"
        normalized_server["type"] = transport
        normalized["server"] = normalized_server
        return normalized

    @model_validator(mode="after")
    def _strip_name(self) -> MCPTestRequest:
        # 镜像验证 MCP 服务器映射本身适用于服务器键 - 仅空白名称将默默绕过上面的
        # min_length=1。
        #
        self.name = self.name.strip() or _DEFAULT_SERVER_NAME
        self.resolved_server
        return self

    @property
    def resolved_server(self) -> MCPServer:
        return self.server.to_mcp_server()

    def to_mcp_config(self, *, cipher: Cipher | None = None) -> dict[str, MCPServer]:
        return {self.name: self.resolved_server.with_decrypted_secrets(cipher=cipher)}


class MCPToolCallResult(BaseModel):
    """所请求的逐字结果``tool_call``。

    端点保持提供商中立：许多服务器报告上游故障（e.g. Slack 的
    ``{"ok": false, "error": "invalid_auth"}``) 作为普
    通文本内容，``isError`` 未设置，因此解释载荷是调用者的工作。
    """

    is_error: bool = Field(description="The MCP-level isError flag of the result.")
    text: str = Field(description="Concatenated text content of the result.")


class MCPTestSuccess(BaseModel):
    """当候选服务器连接并列出其工具时的响应。"""

    ok: Literal[True] = True
    tools: list[str] = Field(
        default_factory=list,
        description="Names of tools advertised by the MCP server.",
    )
    tool_result: MCPToolCallResult | None = Field(
        default=None,
        description=("Outcome of the requested `tool_call`, when one was supplied."),
    )
    resolved_mcp_servers: list[dict[str, Any]] | None = Field(
        default=None,
        deprecated=True,
        description=(
            "Deprecated compatibility field for older clients that expected "
            "resolved MCP server metadata in test responses."
        ),
    )
    oauth_state: MCPOAuthStateResponse | None = Field(
        default=None,
        description=(
            "Serialized OAuth state acquired or refreshed by the probe. "
            "Clients should persist this under the tested server's auth.state."
        ),
    )


class MCPTestFailure(BaseModel):
    """候选服务器无法连接或列出工具时的响应。

    端点返回值为 HTTP 200，在成功和失败两种情况下：这里失败是 * 验证用户提供的配置 *
    的预期结果，而不是服务器端错误。 结构化的形状使 UI 可以轻松呈现
    可操作的消息。
    """

    ok: Literal[False] = False
    error: str = Field(description="Human-readable error message.")
    error_kind: Literal["timeout", "connection", "unknown"] = Field(
        description="Coarse error classification, useful for branching UI."
    )


MCPTestResponse = Annotated[
    MCPTestSuccess | MCPTestFailure,
    Field(discriminator="ok"),
]


class MCPOAuthStartResponse(BaseModel):
    """启动安装时 OAuth MCP 探测的响应。"""

    ok: bool
    job_id: str | None = None
    authorization_url: str | None = None
    error: str | None = None
    error_kind: Literal["timeout", "connection", "unknown"] | None = None


class MCPOAuthStatusResponse(BaseModel):
    """安装时 OAuth MCP 探测的当前状态。"""

    ok: bool
    status: Literal["pending", "authorizing", "succeeded", "failed"]
    job_id: str
    authorization_url: str | None = None
    callback_ready: bool = False
    tools: list[str] | None = None
    tool_result: MCPToolCallResult | None = None
    oauth_state: MCPOAuthStateResponse | None = None
    error: str | None = None
    error_kind: Literal["timeout", "connection", "unknown"] | None = None


class MCPOAuthCallbackRequest(BaseModel):
    """回调 URL 从浏览器 OAuth 重定向复制。"""

    callback_url: str = Field(..., min_length=1)


class _MCPOAuthProbeJob:
    def __init__(self, *, request: MCPTestRequest, cipher: Cipher | None):
        self.id = uuid.uuid4().hex
        self.request = request
        self.cipher = cipher
        self.created_at = time.monotonic()
        self.authorization_url: str | None = None
        self.callback_url: str | None = None
        self.result: MCPTestResponse | None = None
        self.status: Literal["pending", "authorizing", "succeeded", "failed"] = (
            "pending"
        )
        self.authorization_ready = threading.Event()
        self.callback_ready = threading.Event()
        self.done = threading.Event()
        self.lock = threading.Lock()

    def set_authorization_url(self, authorization_url: str) -> None:
        with self.lock:
            self.authorization_url = authorization_url
            self.status = "authorizing"
        self.authorization_ready.set()

    def set_callback_ready(self, callback_url: str) -> None:
        with self.lock:
            self.callback_url = callback_url
        self.callback_ready.set()

    def set_result(self, result: MCPTestResponse) -> None:
        with self.lock:
            self.result = result
            self.status = (
                "succeeded" if isinstance(result, MCPTestSuccess) else "failed"
            )
        self.done.set()
        # 当探测在无需同意的情况下完成（存储的 token 仍然有效或刷新）或提前失败时，也会
        # 唤醒启动路由。
        #
        self.authorization_ready.set()

    def to_status_response(self) -> MCPOAuthStatusResponse:
        with self.lock:
            result = self.result
            status = self.status
            authorization_url = self.authorization_url

        if isinstance(result, MCPTestSuccess):
            return MCPOAuthStatusResponse(
                ok=True,
                status="succeeded",
                job_id=self.id,
                authorization_url=authorization_url,
                callback_ready=self.callback_ready.is_set(),
                tools=result.tools,
                tool_result=result.tool_result,
                oauth_state=result.oauth_state,
            )
        if isinstance(result, MCPTestFailure):
            return MCPOAuthStatusResponse(
                ok=False,
                status="failed",
                job_id=self.id,
                authorization_url=authorization_url,
                callback_ready=self.callback_ready.is_set(),
                error=result.error,
                error_kind=result.error_kind,
            )
        return MCPOAuthStatusResponse(
            ok=True,
            status=status,
            job_id=self.id,
            authorization_url=authorization_url,
            callback_ready=self.callback_ready.is_set(),
        )


_oauth_probe_jobs: dict[str, _MCPOAuthProbeJob] = {}
_oauth_probe_jobs_lock = threading.Lock()


def _sweep_oauth_probe_jobs_locked(now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    expired = [
        job_id
        for job_id, job in _oauth_probe_jobs.items()
        if now - job.created_at > _OAUTH_PROBE_JOB_TTL_SECONDS
    ]
    for job_id in expired:
        _oauth_probe_jobs.pop(job_id, None)


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


def _oauth_auth_from_authentication(
    authentication: MCPOAuthAuthentication | None,
    *,
    oauth_token_storage: InMemoryMCPOAuthTokenStore | None,
    job: _MCPOAuthProbeJob,
) -> OAuth:
    additional_client_metadata: dict[str, Any] = {}
    if authentication is not None:
        additional_client_metadata.update(
            authentication.additional_client_metadata or {}
        )
        if authentication.client_auth_method is not None:
            additional_client_metadata["token_endpoint_auth_method"] = (
                authentication.client_auth_method
            )
    return _BrowserCoordinatedOAuth(
        job=job,
        scopes=authentication.scopes if authentication is not None else None,
        client_name=(
            authentication.client_name
            if authentication is not None and authentication.client_name
            else "FastMCP Client"
        ),
        token_storage=oauth_token_storage,
        additional_client_metadata=additional_client_metadata or None,
        client_metadata_url=(
            authentication.client_metadata_url if authentication is not None else None
        ),
        client_id=authentication.client_id if authentication is not None else None,
        client_secret=(
            authentication.client_secret.get_secret_value()
            if authentication is not None and authentication.client_secret is not None
            else None
        ),
    )


class _BrowserCoordinatedOAuth(MCPOAuth):
    """FastMCP OAuth 客户端，让前端拥有浏览器导航。"""

    def __init__(self, *, job: _MCPOAuthProbeJob, **kwargs: Any):
        super().__init__(**kwargs)
        self._job = job

    async def redirect_handler(self, authorization_url: str) -> None:
        """捕获 URL，而不是从后端打开浏览器。"""
        async with self.httpx_client_factory() as client:
            response = await client.get(authorization_url, follow_redirects=False)
            if response.status_code == 400:
                raise ClientNotFoundError(
                    "OAuth client not found - cached credentials may be stale"
                )
            if response.status_code not in (200, 302, 303, 307, 308):
                raise RuntimeError(
                    f"Unexpected authorization response: {response.status_code}"
                )

        logger.info("MCP OAuth authorization URL captured for job %s", self._job.id)
        self._job.set_authorization_url(authorization_url)

    async def callback_handler(self):
        """发布回调 URL，然后遵循 FastMCP。

        重新实现它会将返回类型冻结为元组，这是 MCP 2.x 拒绝的——它需要一个
        ``AuthorizationCodeResult``。 仅
        ``redirect_port`` 被读取：``_callback_host`` 在 FastMCP 3.2.0 中不存在。
        """
        callback_url = f"http://localhost:{self.redirect_port}/callback"
        self._job.set_callback_ready(callback_url)
        logger.info(
            "MCP OAuth callback server ready for job %s at %s",
            self._job.id,
            callback_url,
        )
        return await super().callback_handler()


def _run_tool_call(
    client: MCPClient, spec: MCPToolCallSpec, tool_names: list[str], timeout: float
) -> MCPToolCallResult:
    """在连接的客户端上调用请求的工具。

    使用 ``call_tool_mcp``（不是 ``call_tool``，它在 ``isError`` 上引发），因此带内故
    障作为数据返回 - 镜像
    ``MCPToolExecutor``。 超时被报告为错误结果，而不是整个测试失败：服务器确实连接并
    列出了，这仍然有用。
    """
    if spec.name not in tool_names:
        return MCPToolCallResult(
            is_error=True,
            text=(
                f"Tool {spec.name!r} not advertised by server "
                f"(available: {', '.join(tool_names) or 'none'})"
            ),
        )
    try:
        result: mcp.types.CallToolResult = client.call_async_from_sync(
            client.call_tool_mcp,
            name=spec.name,
            arguments=spec.arguments,
            timeout=timeout,
        )
    except TimeoutError:
        return MCPToolCallResult(
            is_error=True,
            text=f"Tool {spec.name!r} call timed out after {timeout} seconds",
        )
    text = "\n".join(
        block.text
        for block in result.content
        if isinstance(block, mcp.types.TextContent)
    )
    return MCPToolCallResult(is_error=bool(result.isError), text=text)


def _probe_mcp_server(
    request: MCPTestRequest,
    cipher: Cipher | None,
    mcp_oauth_factory: Any | None = None,
) -> MCPTestResponse:
    """同步探测器——在 ``run_in_executor`` 内安全运行。

    ``create_mcp_tools`` 已经通过 ``MCPClient.call_async_from_sync`` 在后台线程运行自
    己的事件循环。 我们故意不
    从FastAPI请求任务中调用它； 相反，调用者首先跳入线程池。
    """

    mcp_config = request.to_mcp_config(cipher=cipher)

    try:
        server = request.resolved_server
        oauth_auth = server.oauth_auth
        oauth_token_storage: InMemoryMCPOAuthTokenStore | None = None
        if oauth_auth is not None:
            oauth_token_storage = InMemoryMCPOAuthTokenStore(
                state=server.initial_oauth_state(cipher=cipher)
            )
        # ``create_mcp_tools`` 返回一个拥有后台循环和（可能是长期存在的）子进程的客户端
        # 。 使用上下文-manager 形式，以便我们始终将其拆除，即使列表成功。
        #
        create_tools_kwargs: dict[str, Any] = {
            "mcp_oauth_token_storage": oauth_token_storage
        }
        if mcp_oauth_factory is not None:
            create_tools_kwargs["mcp_oauth_factory"] = mcp_oauth_factory
        with create_mcp_tools(
            mcp_config,
            timeout=request.timeout,
            **create_tools_kwargs,
        ) as client:
            tool_names = [tool.name for tool in client.tools]
            tool_result: MCPToolCallResult | None = None
            if request.tool_call is not None:
                tool_result = _run_tool_call(
                    client,
                    request.tool_call,
                    tool_names,
                    request.timeout,
                )
            oauth_state: MCPOAuthStateResponse | None = None
            if oauth_token_storage is not None:
                state = oauth_token_storage.export_state()
                if state.has_values:
                    oauth_state = state.to_response(cipher=cipher)
            return MCPTestSuccess(
                tools=tool_names,
                tool_result=tool_result,
                oauth_state=oauth_state,
            )
    except MCPTimeoutError as exc:
        logger.info("MCP test timed out for server %r: %s", request.name, exc)
        return MCPTestFailure(error=str(exc), error_kind="timeout")
    except MCPError as exc:
        # ``MCPError("MCP Connection Failure")`` 是当底层 FastMCP 客户端无法启动时
        # client.connect() 引发的。 揭示根本原因消息 (e.g. “sh：1：MCP-server-GitHub：权
        # 限被拒绝”）因为单独的包装器没有用。
        #
        cause = exc.__cause__ or exc.__context__
        detail = str(cause) if cause else str(exc) or "Failed to connect to MCP server"
        logger.info(
            "MCP test connection failed for server %r: %s", request.name, detail
        )
        return MCPTestFailure(error=detail, error_kind="connection")
    except Exception as exc:  # noqa: BLE001 - we want to surface anything else
        # 任何其他异常都是意外的，但仍应返回结构化响应：UI 无法从 500 恢复。
        #
        logger.warning(
            "MCP test failed unexpectedly for server %r",
            request.name,
            exc_info=True,
        )
        return MCPTestFailure(
            error=f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__,
            error_kind="unknown",
        )


@mcp_router.post(
    "/test",
    response_model=MCPTestResponse,
    response_model_exclude_none=True,
    summary="Test an MCP server configuration",
    description=(
        "Attempt to connect to a candidate MCP server and list its tools, "
        "without persisting any settings. Useful for validating user input "
        "in 'add MCP server' flows before storing the config. "
        "For OAuth servers, any acquired state is returned as `oauth_state` "
        "so clients can persist it under the MCP server object's `auth.state`. "
        "Optionally invokes one caller-chosen (read-only) tool via "
        "`tool_call` and reports its outcome in `tool_result`, so callers "
        "can verify credentials that are only exercised on tool invocation. "
        "Encrypted `env`/`headers` values round-tripped from settings are "
        "decrypted before the connection is attempted. "
        "Returns 200 with `ok=false` for connection / timeout failures "
        "(those are expected during validation, not server errors)."
    ),
)
async def test_mcp_server(
    request: MCPTestRequest, http_request: Request
) -> MCPTestResponse:
    """探测单个 MCP 服务器配置并报告其是否有效。"""
    # 解决此处的密码：下面的线程池函数不得返回到 ``http_request.app.state``。
    #
    cipher = get_cipher(http_request)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _probe_mcp_server, request, cipher)


def _run_oauth_probe_job(job: _MCPOAuthProbeJob) -> None:
    def oauth_factory(
        _server_name: str,
        _server: MCPServer,
        auth: MCPOAuthAuthCredential,
        oauth_token_storage: InMemoryMCPOAuthTokenStore | None,
    ) -> OAuth:
        return _oauth_auth_from_authentication(
            auth.authentication,
            oauth_token_storage=oauth_token_storage,
            job=job,
        )

    result = _probe_mcp_server(
        job.request,
        job.cipher,
        mcp_oauth_factory=oauth_factory,
    )
    job.set_result(result)


def _register_oauth_job(job: _MCPOAuthProbeJob) -> None:
    with _oauth_probe_jobs_lock:
        _sweep_oauth_probe_jobs_locked()
        _oauth_probe_jobs[job.id] = job


def _get_oauth_job(job_id: str) -> _MCPOAuthProbeJob:
    with _oauth_probe_jobs_lock:
        _sweep_oauth_probe_jobs_locked()
        job = _oauth_probe_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="MCP OAuth job not found")
    return job


@mcp_router.post(
    "/oauth/start",
    response_model=MCPOAuthStartResponse,
    response_model_exclude_none=True,
    summary="Start an MCP OAuth install probe",
)
async def start_mcp_oauth(
    request: MCPTestRequest, http_request: Request
) -> MCPOAuthStartResponse:
    """为候选 MCP 服务器启动 OAuth 并返回授权 URL。"""
    if request.resolved_server.oauth_auth is None:
        raise HTTPException(
            status_code=400,
            detail="MCP OAuth start requires auth.strategy='oauth2'",
        )

    job = _MCPOAuthProbeJob(request=request, cipher=get_cipher(http_request))
    _register_oauth_job(job)
    thread = threading.Thread(
        target=_run_oauth_probe_job,
        args=(job,),
        name=f"mcp-oauth-{job.id[:8]}",
        daemon=True,
    )
    thread.start()

    authorization_timeout = min(max(request.timeout, 1.0), 30.0)
    loop = asyncio.get_running_loop()
    authorization_ready = await loop.run_in_executor(
        None,
        job.authorization_ready.wait,
        authorization_timeout,
    )
    if authorization_ready and job.authorization_url is not None:
        return MCPOAuthStartResponse(
            ok=True,
            job_id=job.id,
            authorization_url=job.authorization_url,
        )

    if job.done.is_set() and isinstance(job.result, MCPTestSuccess):
        # 无需同意：存储的 token 有效或已刷新。 调用者从状态路由读取结果。
        #
        return MCPOAuthStartResponse(ok=True, job_id=job.id)

    if job.done.is_set() and isinstance(job.result, MCPTestFailure):
        return MCPOAuthStartResponse(
            ok=False,
            job_id=job.id,
            error=job.result.error,
            error_kind=job.result.error_kind,
        )

    return MCPOAuthStartResponse(
        ok=False,
        job_id=job.id,
        error="Timed out waiting for OAuth authorization URL",
        error_kind="timeout",
    )


@mcp_router.get(
    "/oauth/status/{job_id}",
    response_model=MCPOAuthStatusResponse,
    response_model_exclude_none=True,
    summary="Get an MCP OAuth install probe status",
)
async def get_mcp_oauth_status(job_id: str) -> MCPOAuthStatusResponse:
    return _get_oauth_job(job_id).to_status_response()


def _validate_callback_url(callback_url: str, job: _MCPOAuthProbeJob) -> None:
    try:
        parsed = urlparse(callback_url)
    except ValueError:  # e.g. 未闭合的 IPv6 括号
        raise HTTPException(
            status_code=400, detail="Invalid OAuth callback URL"
        ) from None
    if parsed.scheme != "http" or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise HTTPException(status_code=400, detail="Invalid OAuth callback URL")

    with job.lock:
        expected = job.callback_url
    if expected is None:
        raise HTTPException(status_code=409, detail="OAuth callback is not ready")

    expected_parsed = urlparse(expected)
    try:
        port = parsed.port
    except ValueError:  # 超出范围或不是数字
        raise HTTPException(
            status_code=400, detail="Unexpected OAuth callback URL"
        ) from None
    if port != expected_parsed.port or parsed.path != expected_parsed.path:
        raise HTTPException(status_code=400, detail="Unexpected OAuth callback URL")


@mcp_router.post(
    "/oauth/callback/{job_id}",
    response_model=MCPOAuthStatusResponse,
    response_model_exclude_none=True,
    summary="Submit an MCP OAuth callback URL",
)
async def submit_mcp_oauth_callback(
    job_id: str, request: MCPOAuthCallbackRequest
) -> MCPOAuthStatusResponse:
    job = _get_oauth_job(job_id)
    _validate_callback_url(request.callback_url, job)
    if job.done.is_set():
        # 重播或延迟回调：探测完成并且其回调服务器已关闭，因此报告结果而不是转发。
        #
        return job.to_status_response()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.get(request.callback_url)
    except httpx.TransportError as exc:
        # 当我们转发时，探测可能已经完成。
        if job.done.is_set():
            return job.to_status_response()
        raise HTTPException(
            status_code=409, detail="OAuth callback server is not listening"
        ) from exc
    if response.status_code >= 400:
        return MCPOAuthStatusResponse(
            ok=False,
            status="failed",
            job_id=job.id,
            authorization_url=job.authorization_url,
            callback_ready=job.callback_ready.is_set(),
            error=f"OAuth callback returned HTTP {response.status_code}",
            error_kind="connection",
        )

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, job.done.wait, 5.0)
    return job.to_status_response()
