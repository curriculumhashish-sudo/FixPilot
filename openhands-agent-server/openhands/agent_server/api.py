import asyncio
import os
import shutil
import sys
import tempfile
import traceback
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager, suppress
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import libtmux
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from openhands.agent_server.acp_router import acp_router
from openhands.agent_server.agent_profiles_router import agent_profiles_router
from openhands.agent_server.auth_router import auth_router
from openhands.agent_server.bash_router import bash_router
from openhands.agent_server.bash_service import get_default_bash_event_service
from openhands.agent_server.canvas_extensions.backend import (
    CanvasExtensionBackendManager,
)
from openhands.agent_server.canvas_extensions.bridge import AppBackendSessionStore
from openhands.agent_server.canvas_extensions_bridge_router import (
    app_backend_bridge_router,
)
from openhands.agent_server.canvas_extensions_router import canvas_extensions_router
from openhands.agent_server.config import (
    V1_SESSION_API_KEY_ENV,
    Config,
    export_session_api_key,
    get_default_config,
)
from openhands.agent_server.conversation_lease import (
    ConversationOwnershipLostError,
    _is_pid_alive,
)
from openhands.agent_server.conversation_registry import (
    create_conversation_registry,
)
from openhands.agent_server.conversation_router import (
    conversation_catalog_router,
    conversation_router,
)
from openhands.agent_server.conversation_service import (
    ConversationService,
    CredentialBindingActivationRequired,
)
from openhands.agent_server.credential_binding import (
    router as credential_binding_router,
)
from openhands.agent_server.dependencies import (
    check_session_api_key,
    check_workspace_session,
)
from openhands.agent_server.event_service import ConversationRunLimitExceeded
from openhands.agent_server.file_router import file_discovery_router, file_router
from openhands.agent_server.git_router import git_router
from openhands.agent_server.hooks_router import hooks_router
from openhands.agent_server.init_router import (
    InitService,
    init_router,
    require_initialized,
)
from openhands.agent_server.llm_router import llm_router
from openhands.agent_server.local_secret_resolver import local_secret_resolution
from openhands.agent_server.mcp_router import mcp_router
from openhands.agent_server.meta_profiles_router import meta_profiles_router
from openhands.agent_server.middleware import CORSDispatcher
from openhands.agent_server.openai.router import (
    check_openai_api_key,
    openai_router,
)
from openhands.agent_server.persistence import reencrypt_stale_stores
from openhands.agent_server.plugins_router import plugins_router
from openhands.agent_server.profiles_router import profiles_router
from openhands.agent_server.provider_connections_router import (
    provider_connections_router,
)
from openhands.agent_server.server_details_router import (
    get_server_info,
    mark_initialization_complete,
    server_details_router,
)
from openhands.agent_server.settings_router import settings_router
from openhands.agent_server.skills_router import skills_router
from openhands.agent_server.sub_agents_router import sub_agents_router
from openhands.agent_server.telemetry import (
    build_telemetry_sink,
    emit_server_started,
    emit_server_stopped,
    get_event_factory,
    get_telemetry_sink,
    shutdown_telemetry_sink,
)
from openhands.agent_server.telemetry.factory import (
    DISTINCT_ID_HEADER,
    distinct_id_from_header,
)
from openhands.agent_server.telemetry.models import (
    EventName,
    RequestFailedProperties,
)
from openhands.agent_server.telemetry.sanitizer import normalize_exception
from openhands.agent_server.tool_preload_service import get_tool_preload_service
from openhands.agent_server.tool_router import tool_router
from openhands.agent_server.vscode_router import vscode_router
from openhands.agent_server.vscode_service import get_vscode_service
from openhands.agent_server.workspaces_router import workspaces_router
from openhands.sdk.logger import DEBUG, get_logger
from openhands.sdk.tool.registry import seal_tool_catalog, unseal_tool_catalog
from openhands.sdk.utils.redact import sanitize_dict
from openhands.tools.terminal.constants import (
    TMUX_SOCKET_NAME,
    TMUX_SOCKET_OWNER_OPTION,
)
from openhands.tools.terminal.terminal.tmux_terminal import _socket_creation_lock


logger = get_logger(__name__)


# tmux 会绑定 $TMUX_TMPDIR/tmux-<uid>/<socket name>，当该路径不满足 sockaddr_un.sun_path
# （Linux 上为 108 字节，macOS 上为 104 字节，还包括 BSDs 和 NUL）时，会失败并返回 "文件
# 名过长"。
#
_MAX_TMUX_SOCKET_PATH = 107 if sys.platform.startswith("linux") else 103
_MAX_TMUX_SOCKET_NAME = len(f"{TMUX_SOCKET_NAME}-{uuid.uuid4().hex}")
_SHORT_TMUX_TMPDIR_ROOT = Path("/tmp")


def _fits_tmux_socket(tmux_tmpdir: Path) -> bool:
    if os.name != "posix":
        return True
    socket_dir = Path(os.path.realpath(tmux_tmpdir)) / f"tmux-{os.getuid()}"
    socket_path_len = len(os.fsencode(socket_dir)) + 1 + _MAX_TMUX_SOCKET_NAME
    return socket_path_len <= _MAX_TMUX_SOCKET_PATH


def _default_server_tmux_tmpdir() -> Path:
    name = f"openhands-agent-server-{os.getpid()}"
    tmux_tmpdir = Path(tempfile.gettempdir()) / name
    if _fits_tmux_socket(tmux_tmpdir):
        return tmux_tmpdir
    # macOS 的每个用户 $TMPDIR （/var/folders/...) 对于套接字来说太深了。
    return _SHORT_TMUX_TMPDIR_ROOT / name


def _ensure_server_tmux_tmpdir() -> tuple[Path, bool, bool]:
    """返回tmux目录，是否默认，是否为
    调用创建了它（只有这样它才会在关闭时被删除）。"""
    existing = os.getenv("TMUX_TMPDIR")
    if existing and _fits_tmux_socket(Path(existing)):
        return Path(existing), False, False

    tmux_tmpdir = _default_server_tmux_tmpdir()
    created = not tmux_tmpdir.exists()
    tmux_tmpdir.mkdir(parents=True, exist_ok=True)
    os.environ["TMUX_TMPDIR"] = str(tmux_tmpdir)
    if existing:
        logger.warning(
            "TMUX_TMPDIR %s is too long for tmux socket paths; "
            "using per-server tmux directory %s instead",
            existing,
            tmux_tmpdir,
        )
    else:
        logger.info(
            "TMUX_TMPDIR not set; defaulting to per-server tmux directory %s",
            tmux_tmpdir,
        )
    return tmux_tmpdir, True, created


def _isolated_socket_names(socket_dir: Path) -> list[str]:
    """返回 *socket_dir* 中存在的每个实例套接字名称。"""
    return [
        path.name
        for path in socket_dir.glob(f"{TMUX_SOCKET_NAME}-" + "[0-9a-f]" * 32)
        if path.is_socket()
    ]


def _kill_sessions(server: libtmux.Server) -> None:
    for session in server.sessions:
        try:
            session.kill()
        except Exception as e:
            logger.warning("Failed to kill tmux session %s: %s", session, e)


def _socket_owner_pid(server: libtmux.Server) -> int | None:
    """返回记录的套接字所有者 PID，如果未知，则返回 None。"""
    try:
        raw = server.show_option(
            TMUX_SOCKET_OWNER_OPTION, global_=True, scope=None, ignore_errors=True
        )
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def _reclaim_stale_tmux_sockets(socket_dir: Path) -> None:
    """回收旧套接字和所有者已消失的任何隔离套接字。"""
    try:
        _kill_sessions(libtmux.Server(socket_name=TMUX_SOCKET_NAME))
    except Exception as e:
        logger.warning("Failed to cleanup tmux socket %s: %s", TMUX_SOCKET_NAME, e)

    for socket_name in _isolated_socket_names(socket_dir):
        try:
            server = libtmux.Server(socket_name=socket_name)
            owner_pid = _socket_owner_pid(server)
            if owner_pid is not None and _is_pid_alive(owner_pid):
                logger.debug(
                    "Leaving tmux socket %s alone; owner pid %s is alive",
                    socket_name,
                    owner_pid,
                )
                continue
            _kill_sessions(server)
        except Exception as e:
            logger.warning("Failed to cleanup tmux socket %s: %s", socket_name, e)


def _cleanup_stale_tmux_sessions() -> None:
    """在服务器启动时清理旧的和隔离的终端套接字。

    旧套接字 (``openhands``) 始终会被回收。 每实例套接字 (``openhands-<32 hex>``) 仅
    在其所属进程消失时才被回收：多个智能体服
    务器可能共享一个外部提供的套接字
    ``TMUX_TMPDIR``，并且杀死一个活着的兄弟姐妹的会话会默默地破坏该对话的终端。

    扫描保留了终端设置时跨进程创建的相同锁，因此，一个仍在运行的进程创建的 socket 从
    未被标记为过期。
    """
    if os.name != "posix":
        return
    socket_dir = Path(os.environ.get("TMUX_TMPDIR", "/tmp")) / f"tmux-{os.getuid()}"

    try:
        with _socket_creation_lock():
            _reclaim_stale_tmux_sockets(socket_dir)
    except Exception as e:
        # 锁仅结束了一场罕见的启动竞赛； 它绝不能停止清理工作
        # from running (or the server from starting).
        logger.warning("tmux socket creation lock unavailable: %s", e)
        _reclaim_stale_tmux_sockets(socket_dir)


@asynccontextmanager
async def api_lifespan(api: FastAPI) -> AsyncIterator[None]:
    original_tmux_tmpdir = os.environ.get("TMUX_TMPDIR")
    original_session_api_key = os.environ.get(V1_SESSION_API_KEY_ENV)
    tmux_tmpdir, tmux_tmpdir_was_defaulted, tmux_tmpdir_was_created = (
        _ensure_server_tmux_tmpdir()
    )
    secret_resolution: local_secret_resolution | None = None
    try:
        # 清理先前服务器运行中的陈旧 tmux 会话
        _cleanup_stale_tmux_sessions()
        backend_manager = getattr(api.state, "canvas_extension_backend_manager", None)
        if backend_manager is not None:
            await backend_manager.reap_orphans()

        config: Config = api.state.config
        deferred = config.deferred_init
        conversation_registry = getattr(
            api.state, "conversation_registry", None
        ) or create_conversation_registry(config)
        api.state.conversation_registry = conversation_registry

        # 回答自己 LookupSecret URLs 在线； 进行环回获取
        # from the event loop cannot be served by the loop blocked on it.
        secret_resolution = local_secret_resolution(config)
        secret_resolution.__enter__()

        # 延迟的 Pod 在禁用遥测的情况下启动，并由 InitService 重建，因此它们会在那里发出
        #  `server_started`。
        #
        api.state.telemetry_sink = await build_telemetry_sink(config)
        if not deferred:
            emit_server_started()

        seal_tool_catalog()

        vscode_service = get_vscode_service()
        tool_preload_service = get_tool_preload_service()

        # 定义异步个函数来启动每个服务
        async def start_vscode_service():
            if vscode_service is not None:
                vscode_started = await vscode_service.start()
                if vscode_started:
                    logger.info("VSCode service started successfully")
                else:
                    logger.warning(
                        "VSCode service failed to start, continuing without VSCode"
                    )
            else:
                logger.info("VSCode service is disabled")

        async def start_tool_preload_service():
            if tool_preload_service is not None:
                tool_preload_started = await tool_preload_service.start()
                if tool_preload_started:
                    logger.info("Tool preload service started successfully")
                else:
                    logger.warning("Tool preload service failed to start - skipping")
            else:
                logger.info("Tool preload service is disabled")

        # 同时启动所有服务
        results = await asyncio.gather(
            start_vscode_service(),
            start_tool_preload_service(),
            return_exceptions=True,
        )

        # 检查初始化期间是否有异常
        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            logger.error(
                "Service initialization failed with %d exception(s): %s",
                len(exceptions),
                exceptions,
            )
            # 重新引发第一个异常以阻止服务器启动
            raise RuntimeError(
                f"Server initialization failed with {len(exceptions)} exception(s)"
            ) from exceptions[0]

        async def stop_stateless_services():
            async def stop_vscode_service():
                if vscode_service is not None:
                    await vscode_service.stop()

            async def stop_tool_preload_service():
                if tool_preload_service is not None:
                    await tool_preload_service.stop()

            await asyncio.gather(
                stop_vscode_service(),
                stop_tool_preload_service(),
                return_exceptions=True,
            )

        # 在延迟初始化模式下，对话服务*不*在此处输入——稍后，当POST/api/init传递运行时配
        # 置时，会发生这种情况。 我们仍然将 /ready 端点标记为就绪，以便热池编排器可以告
        # 诉 pod 已完成启动并且可以接收其 /api/init 载荷。
        #
        if deferred:
            init_service = InitService(api, base_config=config)
            api.state.init_service = init_service
            mark_initialization_complete()
            logger.info("Server started in deferred-init mode; awaiting POST /api/init")
            try:
                yield
            finally:
                await init_service.teardown()
                await stop_stateless_services()
            return

        # 非延迟（遗留）路径：构建并进入对话服务作为生命周期的一部分，与以前一样。
        #
        await asyncio.to_thread(reencrypt_stale_stores, config)
        #
        # 来自配置文件的密钥仅在 ``config`` 中可见； 该服务器的进程内调用者从环境中读取
        # 它。
        #
        export_session_api_key(config)
        # 不是 get_default_conversation_service()：它从 OH_* env 重建配置，忽略传递给
        # create_app() 的配置。
        #
        service = ConversationService.get_instance(config)
        mark_initialization_complete()
        logger.info("Server initialization complete - ready to serve requests")

        bash_svc = get_default_bash_event_service()
        api.state.bash_event_service = bash_svc

        conversation_registry.configure_service(service)
        # 运行时清理必须先于外部目录恢复，这样过时的运行时所有者就不会失去对外部服务的过
        # 期租约。
        #
        await conversation_registry.start()

        async with service:
            api.state.conversation_service = service

            config = api.state.config
            retention_task: asyncio.Task | None = None
            if config.bash_events_retention_seconds is not None:
                retention_task = asyncio.create_task(
                    bash_svc.run_retention_cleanup_loop(
                        config.bash_events_retention_seconds
                    )
                )
                logger.info(
                    "Bash events retention cleanup started (retention: %ds)",
                    config.bash_events_retention_seconds,
                )

            try:
                yield
            finally:
                session_store = getattr(api.state, "app_backend_session_store", None)
                if session_store is not None:
                    await session_store.shutdown()
                await conversation_registry.shutdown()
                if retention_task is not None:
                    retention_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await retention_task

                await stop_stateless_services()
    finally:
        # 最后，启动失败不会泄漏漏任务，并且在`async with service`之后，终端事件仍然被接
        # 受。
        #
        if secret_resolution is not None:
            secret_resolution.__exit__(None, None, None)
        unseal_tool_catalog()
        backend_manager = getattr(api.state, "canvas_extension_backend_manager", None)
        if backend_manager is not None:
            await backend_manager.shutdown()
        emit_server_stopped()
        await shutdown_telemetry_sink()

        if tmux_tmpdir_was_defaulted:
            if os.environ.get("TMUX_TMPDIR") == str(tmux_tmpdir):
                if original_tmux_tmpdir is None:
                    os.environ.pop("TMUX_TMPDIR", None)
                else:
                    os.environ["TMUX_TMPDIR"] = original_tmux_tmpdir
        if os.environ.get(V1_SESSION_API_KEY_ENV) != original_session_api_key:
            if original_session_api_key is None:
                os.environ.pop(V1_SESSION_API_KEY_ENV, None)
            else:
                os.environ[V1_SESSION_API_KEY_ENV] = original_session_api_key
        if tmux_tmpdir_was_created:
            # 仅此进程创建的每服务器目录； 用户提供的 TMUX_TMPDIR 从未被移除。
            #
            try:
                shutil.rmtree(tmux_tmpdir)
            except OSError as e:
                logger.warning(
                    "Failed to remove per-server tmux directory %s: %s",
                    tmux_tmpdir,
                    e,
                )


def _emit_request_failed(request: Request, exc: Exception, error_id: str) -> None:
    """将未处理的 5xx 报告为已清理的诊断事件。

    发送*路由模板*（``/api/conversations/{conversation_id}``）而不是
    ``request.url.path``，它嵌入了真实的标
    识符。 完全
    defensive: 遥测路径中的错误不得替换 500
    调用者已经遇到了不同的失败。
    """
    try:
        sink = get_telemetry_sink()
        if not sink.enabled:
            return

        factory = get_event_factory()
        if factory is None:
            return

        route = request.scope.get("route")
        route_template = getattr(route, "path", None)
        if not isinstance(route_template, str) or not route_template:
            # 不匹配的路由：报告原始路径可能会泄漏标识符。
            route_template = "/unmatched"

        method = request.method.upper()
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
            return

        fingerprint = normalize_exception(exc)
        # 当前端提供分析身份时，归因于前端的分析身份； 否则，请求范围的活动没有对话
        # user_id。
        #
        distinct_id = distinct_id_from_header(request.headers.get(DISTINCT_ID_HEADER))
        sink.emit(
            factory.build(
                EventName.REQUEST_FAILED,
                RequestFailedProperties(
                    route_template=route_template,
                    method=method,  # type: ignore[arg-type]
                    status_code=500,
                    error_class=fingerprint.error_class,
                    error_category=fingerprint.error_category,
                    error_fingerprint=fingerprint.error_fingerprint,
                    error_id=error_id,
                ),
                user_id=distinct_id,
            )
        )
    except Exception:
        logger.debug("Could not emit request_failed telemetry", exc_info=True)


def _get_root_path(config: Config) -> str:
    root_path = ""
    if config.web_url:
        web_url = urlparse(config.web_url)
        root_path = web_url.path.rstrip("/")
    return root_path


def _create_fastapi_instance(config: Config) -> FastAPI:
    """创建基本的 FastAPI 应用程序实例。

    Returns:
        带有标题、描述和生命周期的基本 FastAPI 应用程序。
    """
    return FastAPI(
        title="OpenHands Agent Server",
        version=version("openhands-agent-server"),
        description=(
            "OpenHands Agent Server - REST/WebSocket interface for OpenHands AI Agent"
        ),
        lifespan=api_lifespan,
        root_path=_get_root_path(config),
    )


def _find_http_exception(exc: BaseExceptionGroup) -> HTTPException | None:
    """HTTPException 在 ExceptionGroup 中查找的辅助函数。

    Args:
        exc: BaseExceptionGroup搜索HTTPException。

    Returns:
        如果找到则为 HTTPException，否则为 None。
    """
    for inner_exc in exc.exceptions:
        if isinstance(inner_exc, HTTPException):
            return inner_exc
        # 递归搜索嵌套 ExceptionGroups
        if isinstance(inner_exc, BaseExceptionGroup):
            found = _find_http_exception(inner_exc)
            if found:
                return found
    return None


def _add_api_routes(app: FastAPI) -> None:
    """将所有 API 路由添加到 FastAPI 应用程序。"""
    conversation_registry = app.state.conversation_registry
    app.include_router(server_details_router)

    # /api/init 端点绕过会话密钥身份验证和休眠门。 它有自己的 X-Init-API-Key 身份验证。
    # 当
    # ``deferred_init`` 是 False，端点仍然已安装，但返回 404，因为 app.state 上没有注册
    # InitService — 请参阅
    # ``get_init_service``.
    init_api_router = APIRouter(prefix="/api")
    init_api_router.include_router(init_router)
    app.include_router(init_api_router)

    # 仅标头身份验证：应用于每个 /api/* 路由 EXCEPT 工作区静态文件路由（下面单独处理）。
    #  此处不尊重 Cookie，因此我们不会将 CSRF 表面扩展至整个 API。 check_session_api_key
    #  在请求时从 request.app.state 读取配置，因此通过 POST /api/init 传递的密钥将得到遵
    # 守，而无需重新注册路由。
    #
    dependencies = [
        # 休眠门：每 /api/* 条路线需要 503 秒，直到 POST /api/init 完成。 非延迟部署无操
        # 作。
        #
        Depends(require_initialized),
        Depends(check_session_api_key),
    ]

    api_router = APIRouter(prefix="/api", dependencies=dependencies)
    api_router.include_router(file_discovery_router)
    # 收集路由必须先于运行时包罗万象，例如
    # ``/conversations/{conversation_id}``.
    api_router.include_router(conversation_catalog_router)
    conversation_registry.add_execution_routes(api_router)
    api_router.include_router(conversation_router)
    api_router.include_router(credential_binding_router)
    api_router.include_router(tool_router)
    api_router.include_router(bash_router)
    api_router.include_router(git_router)
    api_router.include_router(file_router)
    api_router.include_router(vscode_router)
    api_router.include_router(skills_router)
    api_router.include_router(sub_agents_router)
    api_router.include_router(plugins_router)
    api_router.include_router(canvas_extensions_router)
    api_router.include_router(hooks_router)
    api_router.include_router(llm_router)
    api_router.include_router(acp_router)
    api_router.include_router(provider_connections_router)
    api_router.include_router(mcp_router)
    api_router.include_router(settings_router)
    api_router.include_router(workspaces_router)
    api_router.include_router(profiles_router)
    api_router.include_router(agent_profiles_router)
    api_router.include_router(meta_profiles_router)
    # /api/auth/* 生成工作区 cookie 并需要标头来引导，因此它位于仅标头身份验证组下。
    #
    api_router.include_router(auth_router)
    app.include_router(
        openai_router,
        dependencies=[Depends(require_initialized), Depends(check_openai_api_key)],
    )

    # 工作区静态文件路由获得自己的身份验证组，该组接受 EITHER X-Session-API-Key 标头或工
    # 作区会话 cookie。 需要 cookie 才能使 <iframe src> / <img src> 嵌入工作区工件正常工
    # 作 - 浏览器无法将自定义标头附加到这些请求。
    #
    workspace_api_router = APIRouter(
        prefix="/api",
        dependencies=[Depends(require_initialized), Depends(check_workspace_session)],
    )
    workspace_api_router.include_router(conversation_registry.workspace_router)
    app.include_router(workspace_api_router)
    app.include_router(api_router)

    app.include_router(
        app_backend_bridge_router,
        dependencies=[Depends(require_initialized)],
    )
    app.include_router(
        conversation_registry.sockets_router,
        dependencies=[Depends(require_initialized)],
    )


def _setup_static_files(app: FastAPI, config: Config) -> None:
    """设置静态文件服务和根重定向（如果已配置）。

    Args:
        app: FastAPI 应用实例。
        config: 包含静态文件设置的配置对象。
    """
    # 仅当配置了静态文件并且目录存在时才继续
    if not (
        config.static_files_path
        and config.static_files_path.exists()
        and config.static_files_path.is_dir()
    ):
        # 如果没有静态文件，则将根路径映射到服务器信息
        app.get("/", tags=["Server Details"])(get_server_info)
        return

    # 挂载静态文件目录
    app.mount(
        "/static",
        StaticFiles(directory=str(config.static_files_path)),
        name="static",
    )

    # 将根重定向添加到静态文件
    @app.get("/", tags=["Server Details"])
    async def root_redirect():
        """将 root 端点重定向到静态文件目录。"""
        # 检查静态目录中是否存在index.html 由于外部条件，我们知道这里的static_files_path
        # 不是None
        #
        assert config.static_files_path is not None
        index_path = config.static_files_path / "index.html"
        if index_path.exists():
            return RedirectResponse(url="/static/index.html", status_code=302)
        else:
            return RedirectResponse(url="/static/", status_code=302)


def _sanitize_validation_errors(errors: Sequence[Any]) -> list[dict]:
    """清理验证错误详细信息以删除敏感输入值。

    FastAPI 的默认 422 响应在每个验证错误字典中包含原始请求 ``input``。 如果请求包含
    机密承载字段 (e.g.
    ``agent.llm.api_key``、MCP 服务器 ``env``），这些值将回显给调用者。 这个助手会编
    辑它们。

    Args:
        errors: ``exc.errors()`` 生成的错误字典列表。

    Returns:
        一个新列表，其中 ``input`` 值已通过 ``sanitize_dict`` 清理。
    """
    sanitized: list[dict] = []
    for error in errors:
        error = dict(error)  # 浅拷贝，这样我们就不会改变原始的
        if "input" in error:
            error["input"] = sanitize_dict(error["input"])
        if isinstance(error.get("ctx"), dict) and isinstance(
            error["ctx"].get("error"), Exception
        ):
            error["ctx"] = {**error["ctx"], "error": str(error["ctx"]["error"])}
        sanitized.append(error)
    return sanitized


def _add_exception_handlers(api: FastAPI) -> None:
    """将异常处理程序添加到 FastAPI 应用程序。"""

    @api.exception_handler(ConversationRunLimitExceeded)
    async def _run_limit_handler(
        _request: Request, exc: ConversationRunLimitExceeded
    ) -> JSONResponse:
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @api.exception_handler(ConversationOwnershipLostError)
    async def _ownership_lost_handler(
        _request: Request, _exc: ConversationOwnershipLostError
    ) -> JSONResponse:
        # 另一个服务器实例接管了此会话的租约，因此受保护的写入被拒绝：冲突，而不是服务器
        # 故障。
        #
        return JSONResponse(
            status_code=409,
            content={
                "detail": (
                    "Conversation is owned by another agent server instance; "
                    "the write was refused"
                )
            },
        )

    @api.exception_handler(CredentialBindingActivationRequired)
    async def _credential_binding_activation_required_handler(
        _request: Request,
        exc: CredentialBindingActivationRequired,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "retryable": True,
            },
        )

    @api.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """处理请求验证错误，清理敏感输入。

        FastAPI 的默认 422 处理程序回显原始请求正文
        ``detail[].input`` 字段。 当请求包含机密 (e.g.
        ``agent.llm.api_key``，MCP 服务器 ``env``），这会在错误响应中泄漏凭据。 我们
        拦截错误，编辑包含机密的字段，并返回安全的 4
        22 响应。

        Refs: OpenHands/评估#385
        """
        logger.info(
            "Validation error on %s %s: %d error(s)",
            request.method,
            request.url.path,
            len(exc.errors()),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": _sanitize_validation_errors(exc.errors())},
        )

    @api.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """处理未处理的异常。"""
        # 该请求号将500错误与服务器端的日志行（包含完整调用堆栈）关联起来，该日志行用于
        # 匹配服务器日志中的不可见的500错误。
        #
        error_id = uuid.uuid4().hex
        # 始终记录我们处于异常处理程序中以进行调试
        logger.debug(
            "Exception handler called for %s %s with %s: %s [error_id=%s]",
            request.method,
            request.url.path,
            type(exc).__name__,
            str(exc),
            error_id,
        )

        content = {
            "detail": "Internal Server Error",
            "exception": str(exc),
            "error_id": error_id,
        }
        # 在 DEBUG 模式下，在响应中包含堆栈跟踪
        if DEBUG:
            content["traceback"] = traceback.format_exc()
        # 检查这是一个 HTTPException 需要直接处理
        if isinstance(exc, HTTPException):
            return await _http_exception_handler(request, exc)

        # 检查这是一个 BaseExceptionGroup HTTPExceptions
        if isinstance(exc, BaseExceptionGroup):
            http_exc = _find_http_exception(exc)
            if http_exc:
                return await _http_exception_handler(request, http_exc)
            # 如果没有找到 HTTPException，视为未处理的异常
            logger.error(
                "Unhandled ExceptionGroup on %s %s [error_id=%s]",
                request.method,
                request.url.path,
                error_id,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            _emit_request_failed(request, exc, error_id)
            return JSONResponse(status_code=500, content=content)

        # 记录任何未处理错误的完整堆栈跟踪，FastAPI 将变成 500
        #
        logger.error(
            "Unhandled exception on %s %s [error_id=%s]",
            request.method,
            request.url.path,
            error_id,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        _emit_request_failed(request, exc, error_id)
        return JSONResponse(status_code=500, content=content)

    @api.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """妥善记录 HTTPExceptions。"""
        # 在信息级别记录 4xx 错误（预期的客户端错误，例如身份验证失败）
        if 400 <= exc.status_code < 500:
            logger.info(
                "HTTPException %d on %s %s: %s",
                exc.status_code,
                request.method,
                request.url.path,
                exc.detail,
            )
        # 在错误级别记录 5xx 错误。 HTTPException 有意无意地提高流控 —— 路由选择此状态并
        # 详细信息 —— 因此，堆栈跟踪不会提供任何额外信息
        # `exc.detail` 并使常规上游信号看起来与进程崩溃无法区分。 未处理的异常仍然可以通
        # 过上面的_unhandled_exception_handler获得完整的回溯。 仅当 DEBUG 打开时才包含回
        # 溯，作为选择加入的调试辅助工具。
        #
        elif exc.status_code >= 500:
            logger.error(
                "HTTPException %d on %s %s: %s",
                exc.status_code,
                request.method,
                request.url.path,
                exc.detail,
                exc_info=(type(exc), exc, exc.__traceback__) if DEBUG else None,
            )
            content = {
                "detail": "Internal Server Error",
                "exception": str(exc),
            }
            if DEBUG:
                content["traceback"] = traceback.format_exc()
            # 不要向客户泄露生产中 5xx 错误的内部详细信息
            return JSONResponse(
                status_code=exc.status_code,
                content=content,
            )

        # 对所有非 5xx HTTP 异常返回干净的 JSON 响应
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def create_app(config: Config | None = None) -> FastAPI:
    """创建并配置 FastAPI 应用程序。

    Args:
        config: 配置对象。 如果为 None，则使用默认配置。

    Returns:
        已配置 FastAPI 应用程序。
    """
    if config is None:
        config = get_default_config()
    app = _create_fastapi_instance(config)
    app.state.config = config
    app.state.conversation_registry = create_conversation_registry(config)
    app.state.canvas_extension_backend_manager = CanvasExtensionBackendManager()
    app.state.app_backend_session_store = AppBackendSessionStore()

    _add_api_routes(app)
    _setup_static_files(app, config)
    if config.conversation_runtime_selectable:
        from openhands.agent_server.docker_runtime.hybrid import (
            RuntimeDispatchMiddleware,
        )

        app.add_middleware(RuntimeDispatchMiddleware)
    app.add_middleware(
        CORSDispatcher,
        allow_origins=config.allow_cors_origins,
        allow_origin_regex=config.allow_cors_origin_regex,
    )
    _add_exception_handlers(app)

    return app


# 创建默认应用程序实例
api = create_app()
