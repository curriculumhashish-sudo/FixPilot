"""用于热池智能体服务器的延迟初始化路由器。

当 ``Config.deferred_init`` 是 True 服务器启动了 *沉睡的* 模式：无状态服务 ([])VSCode
工具预加载通常也会出现，但对话、事件和b
ash路由器返回503 ``POST /api/init`` 提供运行时配置。 这是为暖池部署设计的，其中的pod
在用户匹配之前就被预热了工作区 + 凭据稍后会附加。

See: https://github.com/OpenHands/software-agent-sdk/issues/2523
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, ClassVar, Literal

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocketException,
    status,
)
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.requests import HTTPConnection

from openhands.agent_server.bash_service import BashEventService
from openhands.agent_server.config import (
    V1_SESSION_API_KEY_ENV,
    Config,
    TelemetrySpec,
    WebhookSpec,
    export_session_api_key,
)
from openhands.agent_server.conversation_registry import (
    ConversationRegistry,
    create_conversation_registry,
)
from openhands.agent_server.conversation_service import ConversationService
from openhands.agent_server.persistence import reencrypt_stale_stores, reset_stores
from openhands.agent_server.server_details_router import mark_initialization_complete
from openhands.agent_server.telemetry import (
    build_telemetry_sink,
    emit_server_started,
    shutdown_telemetry_sink,
)
from openhands.agent_server.vscode_service import get_vscode_service
from openhands.sdk.logger import get_logger
from openhands.sdk.observability import maybe_init_laminar


logger = get_logger(__name__)


# 初始化端点使用自己的头衔（不同于 X-Session-）API-Key) 因为在热启动时，池中的会话密钥未
# 知 - 他们会到达 *inside* 的 /api/init body. 该值与休眠服务器进行比较 ``secret_key``,
# 该端点用于加密目的，且将被初始化时覆盖载荷。
#
_INIT_API_KEY_HEADER = APIKeyHeader(name="X-Init-API-Key", auto_error=False)


InitState = Literal["dormant", "initializing", "ready"]


class InitRequest(BaseModel):
    """运行时配置在 /api/init 时间交付。

    每个字段都是可选的，并且会覆盖休眠中的等效字段
    ``Config``. 未提供的字段保留构建服务器时使用的值（通常来自 Pod 启动时的环境变量）
    。 可覆盖的字段集是故意狭窄的——它覆盖了今天以环境变量形式呈现的
    值，这些值需要根据用户而变化，而不是在图像构建时间的配置Python (依赖、插件集等)仍
    然绑定到热池风味。
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    session_api_keys: list[str] | None = Field(
        default=None,
        description=(
            "Per-user session API keys. If provided, all subsequent /api/* "
            "requests must authenticate with one of these keys via the "
            "X-Session-API-Key header."
        ),
    )
    secret_key: SecretStr | None = Field(
        default=None,
        description=(
            "Symmetric secret used to encrypt persisted secrets. If not "
            "provided, falls back to the first session_api_key (matching the "
            "default Config behavior)."
        ),
    )
    previous_secret_keys: list[SecretStr] | None = Field(
        default=None,
        description=(
            "Earlier values of secret_key (or of the first session_api_key it "
            "falls back to), used only to decrypt values saved under them; "
            "they are re-encrypted under the current key when next saved."
        ),
    )
    conversations_path: Path | None = Field(
        default=None,
        description=(
            "Directory where conversations are persisted. Override this to "
            "point at the mounted user workspace."
        ),
    )
    bash_events_dir: Path | None = Field(
        default=None,
        description=(
            "Directory where bash events are persisted. Typically located "
            "inside the mounted user workspace."
        ),
    )
    conversation_worktree_root: Path | None = Field(
        default=None,
        description=(
            "Root directory for conversation git worktrees. Override this to "
            "point at the mounted user workspace."
        ),
    )
    webhooks: list[WebhookSpec] | None = Field(
        default=None,
        description="Per-user webhooks (e.g. for streaming events back).",
    )
    web_url: str | None = Field(
        default=None,
        description=(
            "External URL where this server is reachable, used for root-path "
            "calculation. Only honored when not already set in dormant config."
        ),
    )
    allow_cors_origins: list[str] | None = Field(
        default=None,
        description="CORS origins to add to the existing localhost allowlist.",
    )
    max_concurrent_runs: int | None = Field(
        default=None,
        ge=1,
        description="Override the conversation-step concurrency limit.",
    )
    env: dict[str, str] | None = Field(
        default=None,
        description=(
            "Process environment variables to set before conversation services "
            "start. Useful for credentials consumed by tools (e.g. GITHUB_TOKEN). "
            "These are applied with ``os.environ.update``; existing values are "
            "overwritten."
        ),
    )
    telemetry: TelemetrySpec | None = Field(
        default=None,
        description=(
            "Product-analytics policy for this pod. Without this, a warm-pool "
            "pod keeps whatever mode it booted with (normally 'disabled'), so "
            "a deployment that expects telemetry must supply it here."
        ),
    )


class InitStatus(BaseModel):
    state: InitState = Field(
        description=(
            "``dormant`` — server is up but waiting for /api/init. "
            "``initializing`` — /api/init has been received and services are "
            "starting. "
            "``ready`` — initialization complete; all /api/* routes are live."
        )
    )
    error: str | None = Field(
        default=None,
        description=(
            "If a previous /api/init attempt failed, the error message. The state "
            "rolls back to ``dormant`` so /api/init can be retried."
        ),
    )


def _build_initialized_config(base: Config, req: InitRequest) -> Config:
    """将休眠 ``base`` 配置与 ``req`` 合并并清除 ``deferred_init``。"""
    updates: dict[str, Any] = {"deferred_init": False}
    if req.session_api_keys is not None:
        updates["session_api_keys"] = req.session_api_keys
    # 空白 secret_key 被视为未设置，就像空白 OH_SECRET_KEY 一样。
    if req.secret_key is not None and req.secret_key.get_secret_value().strip():
        updates["secret_key"] = req.secret_key
    elif req.session_api_keys and base.secret_key is None:
        # 匹配配置默认值：当未提供 secret_key 时，回退到第一个会话密钥。
        #
        updates["secret_key"] = SecretStr(req.session_api_keys[0])
    if req.previous_secret_keys is not None:
        updates["previous_secret_keys"] = req.previous_secret_keys
    if req.conversations_path is not None:
        updates["conversations_path"] = req.conversations_path
    if req.bash_events_dir is not None:
        updates["bash_events_dir"] = req.bash_events_dir
    if req.conversation_worktree_root is not None:
        updates["conversation_worktree_root"] = req.conversation_worktree_root
    if req.webhooks is not None:
        updates["webhooks"] = req.webhooks
    if req.web_url is not None:
        updates["web_url"] = req.web_url
    if req.allow_cors_origins is not None:
        updates["allow_cors_origins"] = req.allow_cors_origins
    if req.max_concurrent_runs is not None:
        updates["max_concurrent_runs"] = req.max_concurrent_runs
    if req.telemetry is not None:
        updates["telemetry"] = req.telemetry
    return base.model_copy(update=updates)


class InitService:
    """跟踪休眠→就绪转换并序列化 /api/init 调用。

    单个 ``asyncio.Lock`` 使并发 /api/init 帖子安全； 第二个看到
    ``state != "dormant"`` 并得到 400。 如果在初
    始化过程中发生故障，状态会回滚到 ``dormant``，以便协调器可以重试。
    """

    def __init__(self, app: FastAPI, base_config: Config) -> None:
        self._app = app
        self._base_config = base_config
        self._state: InitState = "dormant"
        self._error: str | None = None
        self._lock = asyncio.Lock()
        self._entered_service: ConversationService | None = None
        self._entered_conversation_registry: ConversationRegistry | None = None
        self._entered_bash_service: BashEventService | None = None
        # ``initialize`` 将下发的会话密钥导出到环境中；
        # ``(None, None)`` 表示没有可放回的内容。
        self._session_api_key_env_before_init: tuple[bool, str | None] = (
            False,
            None,
        )

    @property
    def state(self) -> InitState:
        return self._state

    def snapshot(self) -> InitStatus:
        return InitStatus(state=self._state, error=self._error)

    async def initialize(self, req: InitRequest) -> InitStatus:
        async with self._lock:
            if self._state != "dormant":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"server already in state: {self._state}",
                )
            if req.session_api_keys is not None and any(
                not key for key in req.session_api_keys
            ):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="session_api_keys cannot contain empty keys",
                )
            self._state = "initializing"
            self._error = None
        try:
            new_config = _build_initialized_config(self._base_config, req)
            if req.env:
                # 在服务启动之前设置环境变量可以让密码等选择 OH_SECRET_KEY 样式的覆盖，
                # 而工具则选择凭据。
                #
                for key, value in req.env.items():
                    os.environ[key] = value
            # 该服务器现在使用的密钥也必须传递给从环境读取该密钥的在进程中的调用者（
            # start_child_conversation 工具，LLM 管理密钥刷新）； 它替换休眠进程启动时使
            # 用的任何键，并且
            # ``teardown`` 恢复之前的值。
            self._session_api_key_env_before_init = (
                True,
                os.environ.get(V1_SESSION_API_KEY_ENV),
            )
            export_session_api_key(new_config)
            maybe_init_laminar()

            # 必须位于捕获接收器的 get_instance() 之前。 emit_server_started匹配项推迟到
            # 以下``ready``转换中：在这里发出会生成一个server_started，导致一个初始化失
            # 败并回滚到休眠状态，留下一个未配对的开始，从而让一个重试发出第二个。
            #
            await shutdown_telemetry_sink()
            reset_stores()
            await asyncio.to_thread(reencrypt_stale_stores, new_config)
            self._app.state.telemetry_sink = await build_telemetry_sink(new_config)

            # 重置模块级单例，以便通过 ``get_default_conversation_service`` 的其他调用站
            # 点看到从合并的配置构建的新实例。
            #
            from openhands.agent_server import conversation_service as cs_mod

            service = ConversationService.get_instance(new_config)
            cs_mod._conversation_service = service
            conversation_registry = create_conversation_registry(new_config)
            conversation_registry.configure_service(service)

            bash_svc = BashEventService(bash_events_dir=new_config.bash_events_dir)
            await bash_svc.__aenter__()
            self._entered_bash_service = bash_svc

            await service.__aenter__()
            self._entered_service = service
            await conversation_registry.start()
            self._entered_conversation_registry = conversation_registry
            self._app.state.config = new_config
            self._app.state.conversation_service = service
            self._app.state.conversation_registry = conversation_registry
            self._app.state.bash_event_service = bash_svc

            # 从合并的配置中重新派生 root_path，以便文档 URLS 有效
            from openhands.agent_server.api import _get_root_path

            new_root_path = _get_root_path(new_config)
            self._app.root_path = new_root_path

            # VSCode 的 token 是第一次会话密钥，就像正常启动时一样。 一个没有启动的休眠
            # 服务器 VSCode 生成了一个随机 token，所以切换到这里提供的密钥。
            #
            vscode_service = get_vscode_service()
            if vscode_service is not None and new_config.session_api_keys:
                await vscode_service.set_connection_token(
                    new_config.session_api_keys[0]
                )

            mark_initialization_complete()
            self._state = "ready"
            # 仅当 init 实际成功时才发出，因此失败的尝试永远不会产生启动，并且重试不能双
            # 重发出。
            #
            emit_server_started()
            logger.info("deferred_init: server transitioned to ready")
            return self.snapshot()
        except Exception as exc:  # pragma: no cover - logged + re-raised
            logger.exception("deferred_init: /api/init failed; rolling back to dormant")
            self._restore_session_api_key_env()
            self._error = f"{type(exc).__name__}: {exc}"
            self._state = "dormant"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=self._error,
            ) from exc

    async def teardown(self) -> None:
        """如果 /api/init 成功，则关闭对话服务。

        从 FastAPI 生命周期的 finally 子句中调用，因此从未初始化的休眠 Pod 不需要任何
        清理。
        """
        if self._entered_service is not None:
            if self._entered_conversation_registry is not None:
                await self._entered_conversation_registry.shutdown()
                self._entered_conversation_registry = None
            await self._entered_service.__aexit__(None, None, None)
            self._entered_service = None
        if self._entered_bash_service is not None:
            await self._entered_bash_service.__aexit__(None, None, None)
            self._entered_bash_service = None
        self._restore_session_api_key_env()

    def _restore_session_api_key_env(self) -> None:
        """撤消所做的导出 ``initialize``（如果已完成）。"""
        exported, previous = self._session_api_key_env_before_init
        if not exported:
            return
        self._session_api_key_env_before_init = (False, None)
        if previous is None:
            os.environ.pop(V1_SESSION_API_KEY_ENV, None)
        else:
            os.environ[V1_SESSION_API_KEY_ENV] = previous


def get_init_service(request: Request) -> InitService:
    init_service = getattr(request.app.state, "init_service", None)
    if init_service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "server is not running with deferred_init=True; the /api/init "
                "endpoint is not available"
            ),
        )
    return init_service


def check_init_api_key(
    request: Request,
    init_api_key: str | None = Depends(_INIT_API_KEY_HEADER),
) -> None:
    """/api/init. 的身份验证门使用休眠服务器的 ``secret_key`` 作为
    bootstrap 凭据 - 编排器已经保存它，因为它是加密所必需的。 当 /api/init 提供每用户
    运行时配置时，密钥将被替换。
    """
    config: Config | None = getattr(request.app.state, "config", None)
    if config is None or config.secret_key is None:
        if config is not None and config.secret_key_was_blank:
            # 配置了空白密钥，但没有保留可用密钥 → 关闭失败，因为没有客户端可以提供空白
            # 密钥。
            #
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        # 未配置按键 → 端点已打开。 开发人员可以接受。
        return
    expected = config.secret_key.get_secret_value()
    if init_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


def require_initialized(connection: HTTPConnection) -> None:
    """当服务器处于休眠状态时拒绝请求和 WebSockets 的依赖关系。

    HTTP请求得到503； WebSockets 在握手被接受之前以 1013（稍后重试）关闭。 立即返回，
    当
    ``deferred_init`` 是 False（正常路径），因此非延迟部署的成本为零。
    """
    init_service: InitService | None = getattr(
        connection.app.state, "init_service", None
    )
    if init_service is None or init_service.state == "ready":
        return
    reason = (
        f"server is in deferred-init state '{init_service.state}'; "
        "call POST /api/init first"
    )
    if connection.scope["type"] == "websocket":
        raise WebSocketException(code=status.WS_1013_TRY_AGAIN_LATER, reason=reason)
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=reason)


init_router = APIRouter(prefix="/init", tags=["Init"])


@init_router.get("", response_model=InitStatus)
async def get_init_status(
    init_service: InitService = Depends(get_init_service),
) -> InitStatus:
    """报告当前初始化状态。

    端点上故意不需要身份验证，因此热池控制器可以轮询它而无需持有初始化密钥。 载荷不包
    含敏感数据。
    """
    return init_service.snapshot()


@init_router.post(
    "",
    response_model=InitStatus,
    dependencies=[Depends(check_init_api_key)],
)
async def initialize_server(
    req: InitRequest,
    init_service: InitService = Depends(get_init_service),
) -> InitStatus:
    """使用运行时配置初始化休眠服务器。

    如果服务器已经初始化（状态！=休眠），则返回 400。 如果初始化失败则返回500； 在这
    种情况下，状态回滚到
    ``dormant`` 因此协调器可以重试。
    """
    return await init_service.initialize(req)
