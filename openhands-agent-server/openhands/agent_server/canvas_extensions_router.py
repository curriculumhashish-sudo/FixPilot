"""OpenHands Agent Server 的 Canvas Extensions 路由器。

HTTP API 端点用于画布扩展操作。 业务逻辑委托给``canvas_extensions/installed.py``； 该
模块镜像
``plugins_router.py`` / ``skills_router.py`` 并专注于 HTTP
concerns: 安装/列表/获取/启用-禁用/卸载，以及服务
将已安装的扩展的入口捆绑到 Canvas 前端。
"""

import asyncio
from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError

from openhands.agent_server.canvas_extensions.backend import (
    BackendLogs,
    BackendRevisionRequest,
    BackendStatus,
    CanvasExtensionBackendManager,
)
from openhands.agent_server.canvas_extensions.bridge import AppBackendSessionStore
from openhands.agent_server.canvas_extensions.installed import (
    InstalledCanvasExtensionInfo,
    disable_canvas_extension,
    enable_canvas_extension,
    get_canvas_extension_bundle_path,
    get_canvas_extension_icon_path,
    get_installed_canvas_extension,
    get_installed_canvas_extension_manifest,
    install_canvas_extension,
    list_installed_canvas_extensions,
    uninstall_canvas_extension,
)
from openhands.agent_server.canvas_extensions.manifest import (
    MANIFEST_FILENAME,
    CanvasExtensionManifest,
)
from openhands.sdk.extensions.fetch import ExtensionFetchError
from openhands.sdk.utils.redact import redact_url_credentials


canvas_extensions_router = APIRouter(
    prefix="/canvas-extensions", tags=["Canvas Extensions"]
)

# 匹配 SDK 的 validate_extension_name() 规则。
CANVAS_EXTENSION_NAME_PATTERN: Final[str] = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

CanvasExtensionNamePath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=255,
        pattern=CANVAS_EXTENSION_NAME_PATTERN,
        description="Canvas extension name (lowercase alphanumeric, hyphens)",
    ),
]


def _backend_manager(request: Request) -> CanvasExtensionBackendManager:
    manager = getattr(request.app.state, "canvas_extension_backend_manager", None)
    if manager is None:
        manager = CanvasExtensionBackendManager()
        request.app.state.canvas_extension_backend_manager = manager
    return manager


async def _revoke_and_stop_backend(
    request: Request, extension_name: str
) -> BackendStatus:
    session_store = getattr(request.app.state, "app_backend_session_store", None)
    if isinstance(session_store, AppBackendSessionStore):
        await session_store.revoke_app(extension_name)
    return await _backend_manager(request).stop(extension_name)


class InstallCanvasExtensionRequest(BaseModel):
    """安装画布扩展的请求正文。"""

    source: str = Field(
        min_length=1,
        description=(
            "Canvas extension source - git URL, GitHub shorthand, or local "
            "path. Examples: 'github:owner/repo', '/path/to/extension'"
        ),
    )
    ref: str | None = Field(
        default=None, description="Optional branch, tag, or commit to install"
    )
    repo_path: str | None = Field(
        default=None,
        description="Subdirectory path within the repository (for monorepos)",
    )
    force: bool = Field(
        default=False, description="If true, overwrite existing installation"
    )


class InstalledCanvasExtensionResponse(BaseModel):
    """包含已安装画布扩展信息的响应。"""

    name: str = Field(description="Canvas extension name")
    version: str = Field(default="", description="Canvas extension version")
    description: str = Field(default="", description="Canvas extension description")
    enabled: bool = Field(
        default=False, description="Whether the canvas extension is enabled"
    )
    source: str = Field(description="Original source (e.g., 'github:owner/repo')")
    requested_ref: str | None = Field(
        default=None,
        description=(
            "Branch, tag, or commit requested at install time. None means no "
            "ref was requested (tracking the source's default branch)."
        ),
    )
    resolved_ref: str | None = Field(
        default=None, description="Resolved git commit SHA"
    )
    repo_path: str | None = Field(
        default=None, description="Subdirectory path within the repository"
    )
    installed_at: str = Field(description="ISO 8601 timestamp of installation")
    install_path: str = Field(description="Path where the extension is installed")
    manifest: CanvasExtensionManifest | None = Field(
        default=None,
        description=(
            "The extension's validated manifest (display_name, "
            "contributes.pages, ...). None if the installed manifest can "
            "no longer be read."
        ),
    )

    @classmethod
    def from_info(
        cls,
        info: InstalledCanvasExtensionInfo,
        manifest: CanvasExtensionManifest | None,
    ) -> "InstalledCanvasExtensionResponse":
        return cls(
            name=info.name,
            version=info.version,
            description=info.description,
            enabled=info.enabled,
            source=info.source,
            requested_ref=info.requested_ref,
            resolved_ref=info.resolved_ref,
            repo_path=info.repo_path,
            installed_at=info.installed_at,
            install_path=str(info.install_path),
            manifest=manifest,
        )


class InstalledCanvasExtensionsListResponse(BaseModel):
    """包含已安装画布扩展列表的响应。"""

    canvas_extensions: list[InstalledCanvasExtensionResponse]


class UpdateCanvasExtensionStateRequest(BaseModel):
    """用于更新画布扩展状态（启用/禁用）的请求正文。"""

    enabled: bool


class UpdateCanvasExtensionStateResponse(BaseModel):
    """来自画布扩展状态更新的响应。"""

    name: str
    enabled: bool


class UninstallCanvasExtensionResponse(BaseModel):
    """来自画布扩展卸载的响应。"""

    message: str


@canvas_extensions_router.post(
    "/install",
    response_model=InstalledCanvasExtensionResponse,
    responses={
        400: {"description": "Could not read canvas extension source"},
        409: {"description": "Canvas extension already installed (use force=true)"},
        422: {"description": "Invalid canvas extension (bad manifest, etc.)"},
    },
)
async def install_canvas_extension_endpoint(
    request: InstallCanvasExtensionRequest,
    http_request: Request,
) -> InstalledCanvasExtensionResponse:
    """从 git URL、GitHub 简写或本地安装画布扩展
    路径。

    无论请求主体如何，全新安装始终会被禁用 - 没有 ``enabled`` 字段可以通过不同的状态
    。
    """
    manager = _backend_manager(http_request)
    if request.force and manager.has_running_backends():
        raise HTTPException(
            status_code=409,
            detail="Stop running Canvas App backends before a forced install",
        )
    try:
        info = await asyncio.to_thread(
            install_canvas_extension,
            source=request.source,
            ref=request.ref,
            repo_path=request.repo_path,
            force=request.force,
        )
        manager.invalidate_approval(info.name)
        return InstalledCanvasExtensionResponse.from_info(
            info, get_installed_canvas_extension_manifest(info.name)
        )
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail="Canvas extension already installed. Use force=true to overwrite.",
        )
    except ExtensionFetchError as e:
        # 通过 -- 传递具体的理由，是源/  repo_path 整个诊断是错误的，通用消息错误地将一
        # 个坏的错误归因于它 repo_path 到源。 已脱敏在以下情况下 URL carried a token. 故
        # 意没有写“未能获取”：画布客户端将该短语视为网络中断，并隐藏原因以显示“断开连接
        # ，请检查网络”弹窗。
        #
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not read canvas extension source: "
                f"{redact_url_credentials(str(e))}"
            ),
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No {MANIFEST_FILENAME} found at the resolved location. "
                "Source plus Path must point at the extension's own "
                "directory, not the repository root."
            ),
        )
    except (ValidationError, ValueError, OSError):
        raise HTTPException(
            status_code=422,
            detail="Invalid canvas extension. Ensure the manifest is well-formed.",
        )


@canvas_extensions_router.get(
    "/installed", response_model=InstalledCanvasExtensionsListResponse
)
def list_installed_canvas_extensions_endpoint() -> (
    InstalledCanvasExtensionsListResponse
):
    """列出所有已安装的画布扩展（启用和禁用）。"""
    infos = list_installed_canvas_extensions()
    return InstalledCanvasExtensionsListResponse(
        canvas_extensions=[
            InstalledCanvasExtensionResponse.from_info(
                i, get_installed_canvas_extension_manifest(i.name)
            )
            for i in infos
        ]
    )


@canvas_extensions_router.get(
    "/installed/{extension_name}",
    response_model=InstalledCanvasExtensionResponse,
    responses={404: {"description": "Canvas extension not installed"}},
)
def get_installed_canvas_extension_endpoint(
    extension_name: CanvasExtensionNamePath,
) -> InstalledCanvasExtensionResponse:
    """获取有关特定已安装画布扩展的信息。"""
    info = get_installed_canvas_extension(name=extension_name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Canvas extension '{extension_name}' is not installed",
        )
    return InstalledCanvasExtensionResponse.from_info(
        info, get_installed_canvas_extension_manifest(extension_name)
    )


@canvas_extensions_router.patch(
    "/installed/{extension_name}",
    response_model=UpdateCanvasExtensionStateResponse,
    responses={404: {"description": "Canvas extension not installed"}},
)
async def set_canvas_extension_enabled_endpoint(
    extension_name: CanvasExtensionNamePath,
    request: UpdateCanvasExtensionStateRequest,
    http_request: Request,
) -> UpdateCanvasExtensionStateResponse:
    """启用或禁用已安装的画布扩展。"""
    if not request.enabled:
        await _revoke_and_stop_backend(http_request, extension_name)
    fn = enable_canvas_extension if request.enabled else disable_canvas_extension
    if not fn(name=extension_name):
        raise HTTPException(
            status_code=404,
            detail=f"Canvas extension '{extension_name}' is not installed",
        )
    return UpdateCanvasExtensionStateResponse(
        name=extension_name, enabled=request.enabled
    )


@canvas_extensions_router.delete(
    "/installed/{extension_name}",
    response_model=UninstallCanvasExtensionResponse,
    responses={404: {"description": "Canvas extension not installed"}},
)
async def uninstall_canvas_extension_endpoint(
    extension_name: CanvasExtensionNamePath,
    request: Request,
) -> UninstallCanvasExtensionResponse:
    """按名称卸载画布扩展，同时保留后端数据。"""
    await _revoke_and_stop_backend(request, extension_name)
    if not uninstall_canvas_extension(name=extension_name):
        raise HTTPException(
            status_code=404,
            detail=f"Canvas extension '{extension_name}' is not installed",
        )
    return UninstallCanvasExtensionResponse(
        message=f"Canvas extension '{extension_name}' uninstalled"
    )


@canvas_extensions_router.get(
    "/installed/{extension_name}/backend",
    response_model=BackendStatus,
)
async def get_canvas_extension_backend_status_endpoint(
    extension_name: CanvasExtensionNamePath,
    request: Request,
) -> BackendStatus:
    """探测可选的后端生命周期状态。"""
    return await _backend_manager(request).status(extension_name)


@canvas_extensions_router.post(
    "/installed/{extension_name}/backend/prepare",
    response_model=BackendStatus,
    responses={409: {"description": "Revision or checksum approval conflict"}},
)
async def prepare_canvas_extension_backend_endpoint(
    extension_name: CanvasExtensionNamePath,
    body: BackendRevisionRequest,
    request: Request,
) -> BackendStatus:
    """验证并准备不可变工件以进行精确修订。"""
    try:
        return await _backend_manager(request).prepare(extension_name, body.revision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@canvas_extensions_router.post(
    "/installed/{extension_name}/backend/start",
    response_model=BackendStatus,
    responses={409: {"description": "Revision is not prepared or cannot start"}},
)
async def start_canvas_extension_backend_endpoint(
    extension_name: CanvasExtensionNamePath,
    body: BackendRevisionRequest,
    request: Request,
) -> BackendStatus:
    """仅启动先前准备的精确后端修订版。"""
    try:
        return await _backend_manager(request).start(extension_name, body.revision)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@canvas_extensions_router.post(
    "/installed/{extension_name}/backend/stop",
    response_model=BackendStatus,
)
async def stop_canvas_extension_backend_endpoint(
    extension_name: CanvasExtensionNamePath,
    request: Request,
) -> BackendStatus:
    """幂等地停止后端拥有的进程组。"""
    # 也撤销应用程序范围的会话：停止的后端不得通过比其寿命更长的 cookie 保持可访问性。
    #
    return await _revoke_and_stop_backend(request, extension_name)


@canvas_extensions_router.get(
    "/installed/{extension_name}/backend/logs",
    response_model=BackendLogs,
)
async def get_canvas_extension_backend_logs_endpoint(
    extension_name: CanvasExtensionNamePath,
    request: Request,
    limit_bytes: Annotated[int, Query(ge=1, le=256 * 1024)] = 64 * 1024,
) -> BackendLogs:
    """从所属进程返回有界组合的 stdout 和 stderr。"""
    return await _backend_manager(request).logs(extension_name, limit_bytes)


@canvas_extensions_router.delete(
    "/installed/{extension_name}/backend/data",
    response_model=BackendStatus,
    responses={409: {"description": "Backend must be stopped first"}},
)
async def delete_canvas_extension_backend_data_endpoint(
    extension_name: CanvasExtensionNamePath,
    request: Request,
) -> BackendStatus:
    """与应用程序卸载分开删除可变后端数据。"""
    try:
        return await _backend_manager(request).delete_data(extension_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@canvas_extensions_router.get(
    "/installed/{extension_name}/bundle",
    responses={404: {"description": "Canvas extension or bundle not found"}},
)
def get_canvas_extension_bundle_endpoint(
    extension_name: CanvasExtensionNamePath,
) -> FileResponse:
    """提供已安装画布扩展的入口捆绑文件。

    入口遏制会根据每个请求的实时安装路径重新验证，而不仅仅是在安装时 - 请参阅
    ``get_canvas_extension_bundle_path``. ``Cache-Control: no-cache`` 强制对每个请求
    进行重新验证，因此
    客户端永远不会继续提供捆绑服务
    from before the extension's last refresh: the actual bytes are re-read
    from disk, and Starlette's file-stat-based ``ETag``/``Last-Modified``
    在磁盘上的修订发生时进行更改。
    """
    bundle_path = get_canvas_extension_bundle_path(name=extension_name)
    if bundle_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Canvas extension '{extension_name}' bundle not found",
        )
    return FileResponse(bundle_path, headers={"Cache-Control": "no-cache"})


@canvas_extensions_router.get(
    "/installed/{extension_name}/icon",
    response_class=FileResponse,
    responses={
        200: {
            "content": {
                "image/svg+xml": {"schema": {"type": "string", "format": "binary"}}
            }
        },
        404: {"description": "Canvas extension or icon not found"},
    },
)
def get_canvas_extension_icon_endpoint(
    extension_name: CanvasExtensionNamePath,
) -> FileResponse:
    """提供由已安装的画布扩展的清单声明的 SVG 图标。

    路径来自清单，而不是请求。 CSP 沙箱阻止直接打开的 SVG 在智能体服务器源上运行脚本
    。
    """
    icon_path = get_canvas_extension_icon_path(name=extension_name)
    if icon_path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Canvas extension '{extension_name}' icon not found",
        )
    return FileResponse(
        icon_path,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "no-cache",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; sandbox"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
