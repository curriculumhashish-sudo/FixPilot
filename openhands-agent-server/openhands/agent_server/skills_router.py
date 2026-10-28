"""OpenHands Agent Server 的技能路由器。

该模块定义了技能操作的HTTPAPI端点。 业务逻辑委托给skills_service.py。
"""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, Field

from openhands.agent_server.skills_service import (
    ExposedUrlData,
    MarketplaceSkillInfo,
    discover_profile_skills,
    discover_public_skill_names,
    load_all_skills,
    service_disable_skill,
    service_enable_skill,
    service_get_installed_skill,
    service_get_marketplace_catalog,
    service_install_skill,
    service_list_installed_skills,
    service_uninstall_skill,
    service_update_skill,
    sync_public_skills,
)
from openhands.sdk.extensions.fetch import ExtensionFetchError
from openhands.sdk.marketplace.registration import MarketplaceRegistration
from openhands.sdk.skills import (
    InstalledSkillInfo,
    SkillFetchError,
    SkillInfo,
    SkillValidationError,
)
from openhands.sdk.skills.skill import DEFAULT_MARKETPLACE_PATH
from openhands.sdk.skills.utils import SKILL_NAME_PATTERN


skills_router = APIRouter(prefix="/skills", tags=["Skills"])

# 验证技能名称路径参数防止空字符串、路径遍历和无效字符
#
SkillNamePath = Annotated[
    str,
    Path(
        min_length=1,
        max_length=255,
        pattern=SKILL_NAME_PATTERN.pattern,
        description="Skill name (lowercase alphanumeric, hyphens)",
    ),
]


class ExposedUrl(BaseModel):
    """代表沙盒中暴露的 URL。"""

    name: str
    url: str
    port: int


class OrgConfig(BaseModel):
    """用于加载组织级技能的配置。"""

    repository: str = Field(description="Selected repository (e.g., 'owner/repo')")
    provider: str = Field(
        description="Git provider type: github, gitlab, azure, bitbucket"
    )
    org_repo_url: str = Field(
        description="Pre-authenticated Git URL for the organization repository. "
        "Contains sensitive credentials - handle with care and avoid logging."
    )
    org_name: str = Field(description="Organization name")


class SandboxConfig(BaseModel):
    """用于加载沙箱特定技能的配置。"""

    exposed_urls: list[ExposedUrl] = Field(
        default_factory=list,
        description="List of exposed URLs from the sandbox",
    )


class SkillsRequest(BaseModel):
    """请求主体加载技能。"""

    load_public: bool = Field(
        default=True, description="Load public skills from OpenHands/extensions repo"
    )
    load_user: bool = Field(
        default=True, description="Load user skills from ~/.openhands/skills/"
    )
    load_project: bool = Field(
        default=True, description="Load project skills from workspace"
    )
    load_org: bool = Field(default=True, description="Load organization-level skills")
    marketplace_path: str | None = Field(
        default=DEFAULT_MARKETPLACE_PATH,
        description=(
            "Relative marketplace JSON path for public skills. "
            "Set to null to load all public skills."
        ),
    )
    registered_marketplaces: list[MarketplaceRegistration] = Field(
        default_factory=list,
        description=(
            "Marketplace registrations for plugin-based skill loading. Registrations "
            "with auto_load=True or a list of plugin names add their skills to the "
            "public skills."
        ),
    )

    project_dir: str | None = Field(
        default=None, description="Workspace directory path for project skills"
    )
    org_configs: list[OrgConfig] | None = Field(
        default=None,
        description="Organization/user skill repositories to load concurrently",
    )
    sandbox_config: SandboxConfig | None = Field(
        default=None, description="Sandbox skills configuration"
    )


class SkillsResponse(BaseModel):
    """包含所有可用技能的响应。"""

    skills: list[SkillInfo]
    sources: dict[str, int] = Field(
        default_factory=dict,
        description="Count of skills loaded from each source",
    )


class SkillCatalogEntry(SkillInfo):
    """智能体 Profile launch 可加载的技能。"""

    origin: Literal["public", "user"] = Field(
        description=(
            "`public`: the public extensions catalog. `user`: the user's own "
            "skills, including marketplace installs."
        )
    )


class SkillCatalogResponse(BaseModel):
    """``GET /api/skills/catalog`` 的响应。"""

    skills: list[SkillCatalogEntry]


class SyncResponse(BaseModel):
    """技能同步操作的响应。"""

    status: Literal["success", "error"]
    message: str


# ---------------------------------------------------------------------------
# 已安装的技能管理模型
# ---------------------------------------------------------------------------


class InstallSkillRequest(BaseModel):
    """安装技能的请求正文。"""

    source: str = Field(
        min_length=1,
        description=(
            "Skill source - git URL, GitHub shorthand (github:owner/repo, "
            "optionally followed by the skill's path in the repository), or "
            "local path. Examples: "
            "'github:OpenHands/extensions/skills/github', "
            "'https://github.com/OpenHands/extensions.git' with repo_path "
            "'skills/github', '/path/to/skill'"
        ),
    )
    ref: str | None = Field(
        default=None,
        description="Optional branch, tag, or commit to install",
    )
    repo_path: str | None = Field(
        default=None,
        description="Subdirectory path within the repository (for monorepos)",
    )
    force: bool = Field(
        default=False,
        description="If true, overwrite existing installation",
    )


class InstalledSkillResponse(BaseModel):
    """包含已安装技能信息的响应。"""

    name: str = Field(description="Skill name")
    version: str = Field(default="", description="Skill version")
    description: str = Field(default="", description="Skill description")
    enabled: bool = Field(default=True, description="Whether the skill is enabled")
    source: str = Field(description="Original source (e.g., 'github:owner/repo')")
    resolved_ref: str | None = Field(
        default=None, description="Resolved git commit SHA"
    )
    repo_path: str | None = Field(
        default=None, description="Subdirectory path within the repository"
    )
    installed_at: str = Field(description="ISO 8601 timestamp of installation")
    install_path: str = Field(description="Path where the skill is installed")

    @classmethod
    def from_skill_info(cls, info: InstalledSkillInfo) -> "InstalledSkillResponse":
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


class InstalledSkillsListResponse(BaseModel):
    """包含已安装技能列表的响应。"""

    skills: list[InstalledSkillResponse]


class UpdateSkillStateRequest(BaseModel):
    """更新技能状态的请求正文（启用/禁用）。"""

    enabled: bool


class UpdateSkillStateResponse(BaseModel):
    """技能状态更新操作的响应。"""

    name: str
    enabled: bool


class UninstallSkillResponse(BaseModel):
    """技能卸载操作的响应。"""

    message: str


class UpdateSkillResponse(BaseModel):
    """技能更新操作的响应。"""

    message: str
    skill: InstalledSkillResponse


class MarketplaceCatalogResponse(BaseModel):
    """包含市场目录的响应。"""

    skills: list[MarketplaceSkillInfo]


def _merge_registered_marketplaces(
    server_registrations: list[MarketplaceRegistration],
    request_registrations: list[MarketplaceRegistration],
) -> list[MarketplaceRegistration]:
    registrations_by_name = {
        registration.name: registration for registration in server_registrations
    }
    registrations_by_name.update(
        {registration.name: registration for registration in request_registrations}
    )
    return list(registrations_by_name.values())


@skills_router.post("", response_model=SkillsResponse)
def get_skills(request: SkillsRequest, http_request: Request) -> SkillsResponse:
    """从所有配置的来源加载和合并技能。

    技能从多个来源加载并与以下内容合并
    优先级（对于重复名称，稍后覆盖之前的内容）：
    1. 最低级的沙盒技能 URLs
    2. 公共技能 - 来自 GitHub OpenHands/扩展存储库
    3. 用户技能 - 来自 ~/.openhands/skills/
    4. 组织技能 - 来自 {org}/.openhands 或同等水平
    5. 项目技能（最高）- 来自{工作区}/.openhands/skills/

    Args:
        request: SkillsRequest 包含要加载的源的配置。

    Returns:
        SkillsResponse 包含合并的技能和源计数。
    """
    # 将 Pydantic 模型转换为服务数据类型
    sandbox_urls = None
    if request.sandbox_config and request.sandbox_config.exposed_urls:
        sandbox_urls = [
            ExposedUrlData(name=url.name, url=url.url, port=url.port)
            for url in request.sandbox_config.exposed_urls
        ]

    org_repos: list[tuple[str, str]] = []
    if request.org_configs:
        org_repos = [(c.org_repo_url, c.org_name) for c in request.org_configs]

    config = getattr(http_request.app.state, "config", None)
    server_registrations = config.registered_marketplaces if config is not None else []
    registered_marketplaces = _merge_registered_marketplaces(
        server_registrations,
        request.registered_marketplaces,
    )

    # 致电服务人员
    result = load_all_skills(
        load_public=request.load_public,
        load_user=request.load_user,
        load_project=request.load_project,
        load_org=request.load_org,
        project_dir=request.project_dir,
        org_repos=org_repos,
        sandbox_exposed_urls=sandbox_urls,
        marketplace_path=request.marketplace_path,
        registered_marketplaces=registered_marketplaces,
    )

    skills_info = [skill.to_skill_info() for skill in result.skills]

    return SkillsResponse(skills=skills_info, sources=result.sources)


@skills_router.get("/catalog", response_model=SkillCatalogResponse)
def get_skill_catalog() -> SkillCatalogResponse:
    """列出智能体个人资料启动可以加载的技能。

    配置文件的 ``public_skills`` 和 ``disabled_skills`` 正是从此列表中选择。 项目技能
    仅在对话打开工作区时加载，因此不会列出。
    """
    public_names = discover_public_skill_names()
    return SkillCatalogResponse(
        skills=[
            SkillCatalogEntry(
                **skill.to_skill_info().model_dump(),
                origin="public" if skill.name in public_names else "user",
            )
            for skill in discover_profile_skills()
        ]
    )


@skills_router.post("/sync", response_model=SyncResponse)
def sync_skills() -> SyncResponse:
    """从 GitHub 存储库强制刷新公共技能。

    这会触发缓存技能存储库上的 git pull，以从 OpenHands/extensions 存储库获取最新技能
    。

    Returns:
        SyncResponse表示成功或失败。
    """
    success, message = sync_public_skills()
    return SyncResponse(
        status="success" if success else "error",
        message=message,
    )


# ---------------------------------------------------------------------------
# 已安装技能管理端点
# ---------------------------------------------------------------------------


@skills_router.post(
    "/install",
    response_model=InstalledSkillResponse,
    responses={
        400: {"description": "Failed to fetch skill source"},
        409: {"description": "Skill already installed (use force=true)"},
        422: {"description": "Invalid skill (missing SKILL.md, etc.)"},
    },
)
def install_skill_endpoint(request: InstallSkillRequest) -> InstalledSkillResponse:
    """从源安装技能。

    将技能从 git URL、GitHub 速记或本地路径安装到用户安装的技能目录 (~
    /.openhands/skills/installed/).

    Args:
        request: InstallSkillRequest 包含源代码和选项。

    Returns:
        InstalledSkillResponse 包含有关安装的详细信息。

    Raises:
        HTTPException 409: 如果技能已经安装且 force=False。 HTTPException 400: 如果获
        取技能源失败。
        HTTPException 422: 如果技能无效。
    """
    try:
        info = service_install_skill(
            source=request.source,
            ref=request.ref,
            repo_path=request.repo_path,
            force=request.force,
        )
        return InstalledSkillResponse.from_skill_info(info)
    except FileExistsError:
        raise HTTPException(
            status_code=409,
            detail="Skill already installed. Use force=true to overwrite.",
        )
    except (SkillFetchError, ExtensionFetchError):
        raise HTTPException(
            status_code=400,
            detail="Failed to fetch skill source. Check that the source is valid.",
        )
    except SkillValidationError:
        raise HTTPException(
            status_code=422,
            detail="Invalid skill. Ensure the source contains a valid SKILL.md.",
        )


@skills_router.get("/installed", response_model=InstalledSkillsListResponse)
def list_installed_skills_endpoint() -> InstalledSkillsListResponse:
    """列出所有已安装的技能。

    返回用户安装的技能目录中安装的所有技能的列表 (~/.openhands/skills/installed/).

    Returns:
        InstalledSkillsListResponse 包含已安装技能的列表。
    """
    skills = service_list_installed_skills()
    return InstalledSkillsListResponse(
        skills=[InstalledSkillResponse.from_skill_info(info) for info in skills]
    )


@skills_router.get(
    "/installed/{skill_name}",
    response_model=InstalledSkillResponse,
    responses={404: {"description": "Skill not installed"}},
)
def get_installed_skill_endpoint(skill_name: SkillNamePath) -> InstalledSkillResponse:
    """获取有关特定已安装技能的信息。

    Args:
        skill_name: 要获得的技能名称。

    Returns:
        InstalledSkillResponse 包含技能详细信息。

    Raises:
        HTTPException 404: 如果技能未安装。
    """
    info = service_get_installed_skill(name=skill_name)
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{skill_name}' is not installed",
        )
    return InstalledSkillResponse.from_skill_info(info)


@skills_router.patch(
    "/installed/{skill_name}",
    response_model=UpdateSkillStateResponse,
    responses={404: {"description": "Skill not installed"}},
)
def set_skill_enabled_endpoint(
    skill_name: SkillNamePath, request: UpdateSkillStateRequest
) -> UpdateSkillStateResponse:
    """启用或禁用已安装的技能。

    Args:
        skill_name: 要更新的技能名称。
        request: UpdateSkillStateRequest 处于启用状态。

    Returns:
        UpdateSkillStateResponse 表示新状态。

    Raises:
        HTTPException 404: 如果技能未安装。
    """
    fn = service_enable_skill if request.enabled else service_disable_skill
    if not fn(name=skill_name):
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{skill_name}' is not installed",
        )

    return UpdateSkillStateResponse(
        name=skill_name,
        enabled=request.enabled,
    )


@skills_router.delete(
    "/installed/{skill_name}",
    response_model=UninstallSkillResponse,
    responses={404: {"description": "Skill not installed"}},
)
def uninstall_skill_endpoint(skill_name: SkillNamePath) -> UninstallSkillResponse:
    """按名称卸载技能。

    从用户安装的技能目录中删除技能。

    Args:
        skill_name: 要卸载的技能名称。

    Returns:
        UninstallSkillResponse 带有卸载消息。

    Raises:
        HTTPException 404: 如果技能未安装。
    """
    success = service_uninstall_skill(name=skill_name)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{skill_name}' is not installed",
        )
    return UninstallSkillResponse(
        message=f"Skill '{skill_name}' uninstalled",
    )


@skills_router.post(
    "/installed/{skill_name}/refresh",
    response_model=UpdateSkillResponse,
    responses={
        400: {"description": "Failed to fetch the skill's recorded source"},
        404: {"description": "Skill not installed"},
    },
)
def refresh_skill_endpoint(skill_name: SkillNamePath) -> UpdateSkillResponse:
    """将已安装的技能刷新到最新版本。

    从原始来源重新获取技能并更新安装。

    Args:
        skill_name: 要刷新的技能名称。

    Returns:
        UpdateSkillResponse 更新了技能信息。

    Raises:
        HTTPException 400: 如果记录的源无法获取。 HTTPException 404: 如果技能未安装。
         HTTPException 422:
        源不再持有有效的技能。 刷新失败会使已安装的副本保持不变。
    """
    try:
        info = service_update_skill(name=skill_name)
    except (SkillFetchError, ExtensionFetchError):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Failed to fetch the source of skill '{skill_name}'. "
                "The installed copy was kept."
            ),
        )
    except SkillValidationError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The source of skill '{skill_name}' no longer holds a valid "
                "skill. The installed copy was kept."
            ),
        )
    if info is None:
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{skill_name}' is not installed",
        )
    return UpdateSkillResponse(
        message=f"Skill '{skill_name}' updated",
        skill=InstalledSkillResponse.from_skill_info(info),
    )


@skills_router.get("/marketplace", response_model=MarketplaceCatalogResponse)
def get_marketplace_catalog() -> MarketplaceCatalogResponse:
    """获取包含安装状态的市场目录。

    返回 OpenHands 扩展存储库市场中的可用技能列表及其安装状态。

    这使得前端应用程序能够显示“市场”选项卡
    with installable skills.

    Returns:
        MarketplaceCatalogResponse 包含可用技能列表。
    """
    return MarketplaceCatalogResponse(skills=service_get_marketplace_catalog())
