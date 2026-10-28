"""OpenHands Agent Server 的插件路由器。

HTTP API 端点用于插件操作。 业务逻辑被委托给
``plugins_service.py``; 该模块反映了 ``skills_router.py`` 并专注于 HTTP 问题。 它暴露
了：

* 已安装插件管理 - 安装/列表/启用-禁用/卸载/刷新 - 以及列出本地可用的插件。
* 仅限插件的市场目录。
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from openhands.agent_server.plugins_service import (
    MarketplacePluginInfo,
    PluginSkillSummary,
    service_disable_plugin,
    service_enable_plugin,
    service_fetch_plugin,
    service_get_installed_plugin,
    service_get_plugins_marketplace_catalog,
    service_install_plugin,
    service_list_available_plugins,
    service_list_installed_plugins,
    service_load_plugin_contents,
    service_plugin_contents,
    service_uninstall_plugin,
    service_update_plugin,
)
from openhands.sdk.extensions.fetch import ExtensionFetchError
from openhands.sdk.plugin import InstalledPluginInfo, Plugin, PluginFetchError
from openhands.sdk.plugin.strict_fetch import PluginSourceError
from openhands.sdk.secret import SecretSource


type JSONValue = (
    str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
)


plugins_router = APIRouter(prefix="/plugins", tags=["Plugins"])

# Kebab-case 插件名称 — 与 SDK 的已安装插件名称规则匹配。 保护 {plugin_name} 路径参数免
# 受空字符串、路径遍历和无效字符的影响。
#
PLUGIN_NAME_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"

PluginNamePath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=255,
        pattern=PLUGIN_NAME_PATTERN,
        description="Plugin name (lowercase alphanumeric, hyphens)",
    ),
]


# ---------------------------------------------------------------------------
# 型号
# ---------------------------------------------------------------------------


class PluginsRequest(BaseModel):
    """列出本地可用插件的请求正文。"""

    load_user: bool = Field(
        default=True, description="Load user plugins (~/.agents/plugins, etc.)"
    )
    load_project: bool = Field(
        default=True, description="Load project plugins from the workspace"
    )
    project_dir: str | None = Field(
        default=None, description="Workspace directory path for project plugins"
    )


class PluginInfo(BaseModel):
    """可用插件的摘要。"""

    name: str
    version: str = ""
    description: str = ""
    path: str = Field(default="", description="Path to the plugin directory")
    skills: list[PluginSkillSummary] = Field(
        default_factory=list, description="Skills bundled in the plugin"
    )
    files: list[str] = Field(
        default_factory=list,
        description="Plugin files, relative to the plugin directory",
    )


class PluginsResponse(BaseModel):
    """包含本地可用插件的响应。"""

    plugins: list[PluginInfo]


class InstallPluginRequest(BaseModel):
    """安装插件的请求正文。"""

    source: str = Field(
        min_length=1,
        description=(
            "Plugin source - git URL, GitHub shorthand (github:owner/repo, "
            "optionally followed by the plugin's path in the repository), or "
            "local path. Examples: "
            "'github:OpenHands/extensions/plugins/city-weather', '/path/to/plugin'"
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


class FetchPluginRequest(BaseModel):
    """请求正文严格获取插件而不安装它。"""

    source: str = Field(min_length=1, description="Plugin git source")
    ref: str | None = Field(default=None, description="Branch, tag, or commit")
    repo_path: str | None = Field(
        default=None,
        description="Subdirectory path within the repository (for monorepos)",
    )
    secrets: dict[str, SecretSource] = Field(
        default_factory=dict,
        description="Secrets used to expand ${VAR} placeholders in source and ref",
    )
    timeout: int = Field(default=60, ge=1, le=600, description="Git timeout seconds")


class FetchPluginResponse(BaseModel):
    """严格获取插件源的响应。"""

    path: str
    resolved_ref: str | None
    source: str
    repo_path: str | None
    manifest: dict[str, JSONValue]
    skills: list[str]
    commands: list[str]


class InstalledPluginResponse(BaseModel):
    """包含已安装插件信息的响应。"""

    name: str = Field(description="Plugin name")
    version: str = Field(default="", description="Plugin version")
    description: str = Field(default="", description="Plugin description")
    enabled: bool = Field(default=True, description="Whether the plugin is enabled")
    source: str = Field(description="Original source (e.g., 'github:owner/repo')")
    resolved_ref: str | None = Field(
        default=None, description="Resolved git commit SHA"
    )
    repo_path: str | None = Field(
        default=None, description="Subdirectory path within the repository"
    )
    installed_at: str = Field(description="ISO 8601 timestamp of installation")
    install_path: str = Field(description="Path where the plugin is installed")
    skills: list[PluginSkillSummary] | None = Field(
        default=None,
        description="Skills bundled in the plugin (None if it failed to load)",
    )
    files: list[str] | None = Field(
        default=None,
        description="Plugin files, relative to install_path (None if load failed)",
    )

    @classmethod
    def from_plugin_info(cls, info: InstalledPluginInfo) -> "InstalledPluginResponse":
        return cls(
            name=info.name,
            version=info.version,
            description=info.description,
            enabled=info.enabled,
            source=info.source,
            resolved_ref=info.resolved_ref,
            repo_path=info.repo_path,
            installed_at=info.installed_at,
            install_path=str(info.install_path),
        )


class InstalledPluginsListResponse(BaseModel):
    """包含已安装插件列表的响应。"""

    plugins: list[InstalledPluginResponse]


class UpdatePluginStateRequest(BaseModel):
    """用于更新插件状态（启用/禁用）的请求正文。"""

    enabled: bool


class UpdatePluginStateResponse(BaseModel):
    """来自插件状态更新的响应。"""

    name: str
    enabled: bool


class UninstallPluginResponse(BaseModel):
    """插件卸载的响应。"""

    message: str


class UpdatePluginResponse(BaseModel):
    """来自插件刷新/更新的响应。"""

    message: str
    plugin: InstalledPluginResponse


class MarketplaceCatalogResponse(BaseModel):
    """包含插件市场目录的响应。"""

    plugins: list[MarketplacePluginInfo]


def _installed_response(info: InstalledPluginInfo) -> InstalledPluginResponse:
    """构建一个包含插件内容的已安装插件响应。"""
    response = InstalledPluginResponse.from_plugin_info(info)
    contents = service_load_plugin_contents(info.install_path)
    if contents is not None:
        response.skills, response.files = contents
    return response


def _plugin_info(plugin: Plugin) -> PluginInfo:
    """构建可用插件摘要（包括其内容）。"""
    skills, files = service_plugin_contents(plugin)
    return PluginInfo(
        name=plugin.name,
        version=plugin.version,
        description=plugin.description,
        path=plugin.path,
        skills=skills,
        files=files,
    )


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@plugins_router.post("", response_model=PluginsResponse)
def get_plugins(request: PluginsRequest) -> PluginsResponse:
    """列出本地可用的插件（已启用的已安装+用户/项目目录）。

    Args:
        request: 要加载哪些本地源。

    Returns:
        PluginsResponse 包含可用插件摘要。
    """
    plugins = service_list_available_plugins(
        load_user=request.load_user,
        load_project=request.load_project,
        project_dir=request.project_dir,
    )
    return PluginsResponse(plugins=[_plugin_info(p) for p in plugins])


@plugins_router.post(
    "/fetch",
    response_model=FetchPluginResponse,
    responses={
        422: {"description": "Invalid plugin source, ref, path, or plugin"},
        502: {"description": "Plugin source unavailable"},
        504: {"description": "Plugin fetch timed out"},
    },
)
def fetch_plugin_endpoint(request: FetchPluginRequest) -> FetchPluginResponse:
    """获取并固定插件源，无需安装或启用它。"""
    try:
        checked = service_fetch_plugin(
            source=request.source,
            ref=request.ref,
            repo_path=request.repo_path,
            secrets=request.secrets,
            timeout=request.timeout,
        )
    except PluginSourceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return FetchPluginResponse(
        path=str(checked.path),
        resolved_ref=checked.resolved_ref,
        source=checked.source,
        repo_path=checked.repo_path,
        manifest=checked.manifest,
        skills=checked.skills,
        commands=checked.commands,
    )


@plugins_router.post(
    "/install",
    response_model=InstalledPluginResponse,
    responses={
        400: {"description": "Failed to fetch plugin source"},
        409: {"description": "Plugin already installed (use force=true)"},
        422: {"description": "Invalid plugin (bad name, etc.)"},
    },
)
def install_plugin_endpoint(request: InstallPluginRequest) -> InstalledPluginResponse:
    """从 git URL、GitHub 简写或本地路径安装插件。"""
    try:
        info = service_install_plugin(
            source=request.source,
            ref=request.ref,
            repo_path=request.repo_path,
            force=request.force,
        )
        return _installed_response(info)
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail="Plugin already installed. Use force=true to overwrite.",
        )
    except (PluginFetchError, ExtensionFetchError):
        raise HTTPException(
            status_code=400,
            detail="Failed to fetch plugin source. Check that the source is valid.",
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid plugin. Ensure it has a valid kebab-case name.",
        )


@plugins_router.get("/installed", response_model=InstalledPluginsListResponse)
def list_installed_plugins_endpoint() -> InstalledPluginsListResponse:
    """列出所有已安装的插件（启用和禁用）。"""
    plugins = service_list_installed_plugins()
    return InstalledPluginsListResponse(
        plugins=[_installed_response(info) for info in plugins]
    )


@plugins_router.get(
    "/installed/{plugin_name}",
    response_model=InstalledPluginResponse,
    responses={404: {"description": "Plugin not installed"}},
)
def get_installed_plugin_endpoint(
    plugin_name: PluginNamePath,
) -> InstalledPluginResponse:
    """获取有关特定已安装插件的信息。"""
    info = service_get_installed_plugin(name=plugin_name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{plugin_name}' is not installed",
        )
    return _installed_response(info)


@plugins_router.patch(
    "/installed/{plugin_name}",
    response_model=UpdatePluginStateResponse,
    responses={404: {"description": "Plugin not installed"}},
)
def set_plugin_enabled_endpoint(
    plugin_name: PluginNamePath, request: UpdatePluginStateRequest
) -> UpdatePluginStateResponse:
    """启用或禁用已安装的插件。"""
    fn = service_enable_plugin if request.enabled else service_disable_plugin
    if not fn(name=plugin_name):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{plugin_name}' is not installed",
        )
    return UpdatePluginStateResponse(name=plugin_name, enabled=request.enabled)


@plugins_router.delete(
    "/installed/{plugin_name}",
    response_model=UninstallPluginResponse,
    responses={404: {"description": "Plugin not installed"}},
)
def uninstall_plugin_endpoint(plugin_name: PluginNamePath) -> UninstallPluginResponse:
    """按名称卸载插件。"""
    if not service_uninstall_plugin(name=plugin_name):
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{plugin_name}' is not installed",
        )
    return UninstallPluginResponse(message=f"Plugin '{plugin_name}' uninstalled")


@plugins_router.post(
    "/installed/{plugin_name}/refresh",
    response_model=UpdatePluginResponse,
    responses={
        400: {"description": "Failed to fetch the plugin's recorded source"},
        404: {"description": "Plugin not installed"},
    },
)
def refresh_plugin_endpoint(plugin_name: PluginNamePath) -> UpdatePluginResponse:
    """将已安装的插件从其源刷新到最新版本。

    刷新失败会使已安装的副本保持不变。
    """
    try:
        info = service_update_plugin(name=plugin_name)
    except (PluginFetchError, ExtensionFetchError):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Failed to fetch the source of plugin '{plugin_name}'. "
                "The installed copy was kept."
            ),
        )
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The source of plugin '{plugin_name}' no longer holds a valid "
                "plugin. The installed copy was kept."
            ),
        )
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{plugin_name}' is not installed",
        )
    return UpdatePluginResponse(
        message=f"Plugin '{plugin_name}' updated",
        plugin=_installed_response(info),
    )


@plugins_router.get("/marketplace", response_model=MarketplaceCatalogResponse)
def get_marketplace_catalog() -> MarketplaceCatalogResponse:
    """获取带有安装状态的插件市场目录。

    返回 True 插件（源位于 ``./plugins/`` 下的条目）
    from the OpenHands extensions repository marketplace, each with attachable
    ``PluginSource`` 坐标 (``source`` / ``ref`` / ``repo_path``) 和
    ``installed`` 标志。 这使得前端能够呈现具有安装/已安装状态的插件市场，并将插件附
    加到对话中。

    Returns:
        MarketplaceCatalogResponse 包含可用插件的列表。
    """
    return MarketplaceCatalogResponse(plugins=service_get_plugins_marketplace_catalog())
