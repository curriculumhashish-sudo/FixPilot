"""OpenHands Agent Server 的技能服务。

该模块包含技能加载和管理的业务逻辑，保持路由器清洁并专注于HTTP关注点。

技能来源：
- 公共技能：注册市场插件或GitHubOpenHands/扩展
- 用户技能：~/.openhands/skills/ 和~/.openhands/microagents/
- 项目技能：{工作区}/.openhands/skills/、.cursorrules、agents.md
- 组织技能：{org}/.openhands 或 {org}/openhands-config
- URLs：从沙盒环境暴露的技能

优先级（稍后覆盖之前）：
沙箱 < 注册市场/公共 < 用户 < 组织 < 项目
"""

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from pydantic import BaseModel, ValidationError

from openhands.sdk.logger import get_logger
from openhands.sdk.marketplace import Marketplace
from openhands.sdk.marketplace.registration import MarketplaceRegistration
from openhands.sdk.marketplace.registry import MarketplaceRegistry
from openhands.sdk.plugin import Plugin
from openhands.sdk.skills import (
    InstalledSkillInfo,
    Skill,
    disable_skill,
    enable_skill,
    get_installed_skill,
    install_skill,
    list_installed_skills,
    load_available_skills,
    load_marketplace_standalone_skills,
    uninstall_skill,
    update_skill,
)
from openhands.sdk.skills.skill import (
    DEFAULT_MARKETPLACE_PATH,
    PUBLIC_SKILLS_REF,
    PUBLIC_SKILLS_REPO,
    _invalidate_public_skills_cache,
    load_skills_from_dir,
)
from openhands.sdk.skills.utils import (
    get_skills_cache_dir,
    update_skills_repository,
)
from openhands.sdk.utils import sanitized_env
from openhands.sdk.utils.path import to_posix_path


logger = get_logger(__name__)


# 沙盒工作主机技能的内容模板
WORK_HOSTS_SKILL_CONTENT = (
    "The user has access to the following hosts for accessing "
    "a web application, each of which has a corresponding port:\n{hosts}"
)

# 沙盒前缀 URLs 应该暴露为 work_hosts 技能。 URLs 以该前缀开头的名称代表在沙箱中运行的
# web 应用程序或服务智能体应该有所了解。
#
SANDBOX_WORKER_URL_PREFIX = "WORKER_"


@dataclass
class ExposedUrlData:
    """从沙箱中暴露的 URL 的内部表示。"""

    name: str
    url: str
    port: int


@dataclass
class SkillLoadResult:
    """从所有来源加载技能的结果。"""

    skills: list[Skill]
    sources: dict[str, int]


def load_org_skills_from_url(
    org_repo_url: str,
    org_name: str,
    working_dir: str | Path | None = None,
) -> list[Skill]:
    """从组织存储库加载技能。

    该功能将组织级别的技能仓库克隆到临时目录，从 skills/ 和 microagents/ 目录加载技能
    ，并清理临时目录。

    org_repo_url 应该是应用程序服务器提供的预先验证的 Git URL（e.g.，包含凭据或 token
    ）。

    Note:
        这是一个阻塞 I/O 操作，由于 git 克隆超时，可能需要长达 120 秒的时间。 当从定
        义为 FastAPI 端点调用时
        `def`（不是 `async def`），FastAPI 自动在线程池中运行它以避免阻塞事件循环。
        不要直接从异步代码调用此函数而不将其包装在
        asyncio.to_thread() 中。

    Args:
        org_repo_url: 组织存储库的预验证 Git URL。
            这应该是一个包含身份验证的完整 Git URL。
        org_name: 组织名称（用于临时目录命名）。
        working_dir: git 操作的可选工作目录。 如果None，
            使用系统临时目录的子目录。

    Returns:
        从组织存储库加载的技能对象列表。 如果存储库不存在或加载失败，则返回空列表。
    """
    all_skills: list[Skill] = []

    # 确定用于克隆的唯一临时目录。 两个仓库可以共享相同的 org_name (e.g. {login}
    # /.openhands 和 {login}/.agents)，以及并发个会话可以克隆同一个组织，因此目录必须在
    # 每次调用中唯一，而不是仅从 org_name 中推导出来的。
    #
    if working_dir:
        base_dir = Path(working_dir) if isinstance(working_dir, str) else working_dir
        base_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(
            tempfile.mkdtemp(prefix=f"_org_skills_{org_name}_", dir=base_dir)
        )
    else:
        temp_dir = Path(tempfile.mkdtemp(prefix=f"openhands_org_skills_{org_name}_"))

    try:
        # 克隆组织存储库（浅克隆以提高效率）
        logger.info(f"Cloning organization skills repository for {org_name}")
        try:
            env = sanitized_env()
            env["GIT_TERMINAL_PROMPT"] = "0"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    org_repo_url,
                    str(temp_dir),
                ],
                check=True,
                capture_output=True,
                timeout=120,
                env=env,
            )
        except subprocess.CalledProcessError:
            # 存储库不存在或访问被拒绝 - 这是预期的情况。
            # 注意：我们故意不记录 stderr，因为它可能包含凭据。
            logger.debug(
                f"Organization repository not found or access denied for {org_name}"
            )
            return all_skills
        except subprocess.TimeoutExpired:
            logger.warning(
                f"Git clone timed out for organization repository {org_name}"
            )
            return all_skills

        logger.debug(f"Successfully cloned org repository to {temp_dir}")

        # 从技能/目录加载技能（首选）
        skills_dir = temp_dir / "skills"
        if skills_dir.exists():
            try:
                repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(
                    skills_dir
                )
                for skills_dict in [repo_skills, knowledge_skills, agent_skills]:
                    all_skills.extend(skills_dict.values())
                logger.debug(
                    f"Loaded {len(all_skills)} skills from org skills/ directory"
                )
            except Exception as e:
                logger.warning(f"Failed to load skills from {skills_dir}: {e}")

        # 从 microagents/ 目录加载技能（旧版支持）
        microagents_dir = temp_dir / "microagents"
        if microagents_dir.exists():
            seen_names = {s.name for s in all_skills}
            try:
                repo_skills, knowledge_skills, agent_skills = load_skills_from_dir(
                    microagents_dir
                )
                for skills_dict in [repo_skills, knowledge_skills, agent_skills]:
                    for name, skill in skills_dict.items():
                        if name not in seen_names:
                            all_skills.append(skill)
                            seen_names.add(name)
                        else:
                            logger.debug(
                                f"Skipping duplicate org skill '{name}' "
                                "from microagents/"
                            )
            except Exception as e:
                logger.warning(f"Failed to load skills from {microagents_dir}: {e}")

        logger.info("Loaded %d organization skills for %s", len(all_skills), org_name)

    except Exception as e:
        logger.warning(f"Failed to load organization skills for {org_name}: {e}")

    finally:
        # 清理临时目录
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                logger.debug(f"Cleaned up temp directory {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory {temp_dir}: {e}")

    return all_skills


def create_sandbox_skill(
    exposed_urls: list[ExposedUrlData],
) -> Skill | None:
    """从沙盒创建一个技能 URLs。

    该函数创建一个技能，该技能会告知智能体关于沙盒环境中暴露端口可用的网络应用和服务
    URLs.

    仅 URLs 以开头的名称 SANDBOX_WORKER_URL_PREFIX 这些也包括在内，因为它们代表了 web
     应用程序智能体应该有所了解。

    Args:
        exposed_urls: 包含名称、url 和端口的 ExposedUrlData 对象列表。

    Returns:
        一个 Skill 对象， work_hosts 如果有匹配项，则内容 URLs, 或 None 如果无关紧要
        的 URLs 已被提供。
    """
    if not exposed_urls:
        return None

    # 带有工作前缀的过滤器 URLs
    worker_urls = [
        url for url in exposed_urls if url.name.startswith(SANDBOX_WORKER_URL_PREFIX)
    ]

    if not worker_urls:
        return None

    # 构建主机内容
    hosts_lines = []
    for url_info in worker_urls:
        hosts_lines.append(f"* {url_info.url} (port {url_info.port})")

    hosts_content = "\n".join(hosts_lines)
    content = WORK_HOSTS_SKILL_CONTENT.format(hosts=hosts_content)

    return Skill(
        name="work_hosts",
        content=content,
        trigger=None,  # 始终活跃
        source=None,  # 以编程方式生成
    )


def merge_skills(skill_lists: list[list[Skill]]) -> list[Skill]:
    """优先合并多个技能列表。

    后面的列表会覆盖前面的重复名称列表。

    Args:
        skill_lists: 按优先顺序合并的技能列表列表。

    Returns:
        合并的技能列表已解决重复问题。
    """
    skills_by_name: dict[str, Skill] = {}

    for skill_list in skill_lists:
        for skill in skill_list:
            if skill.name in skills_by_name:
                logger.info(
                    f"Overriding skill '{skill.name}' from earlier source "
                    "with later source"
                )
            skills_by_name[skill.name] = skill

    return list(skills_by_name.values())


def load_registered_marketplace_skills(
    registered_marketplaces: list[MarketplaceRegistration],
) -> list[Skill]:
    """从自动加载插件加载技能和市场中的独立技能。"""
    if not registered_marketplaces:
        return []

    registry = MarketplaceRegistry(registered_marketplaces)
    all_skills: list[Skill] = []
    for registration in registry.get_auto_load_registrations():
        try:
            marketplace, marketplace_path = registry.get_marketplace(registration.name)
        except Exception:
            logger.warning(
                "Failed to load marketplace '%s'; continuing without it",
                registration.name,
                exc_info=True,
            )
            continue

        # 首先添加独立技能，最后合并层级。这样，添加插件可以让插件胜过同名的独立技能——符
        # 合目录的插件胜过独立技能的规则。
        #
        all_skills.extend(
            load_marketplace_standalone_skills(
                marketplace, marketplace_path, registration
            )
        )

        for entry in marketplace.plugins:
            if not registration.auto_loads_plugin(entry.name):
                continue
            try:
                source, ref, repo_path = marketplace.resolve_plugin_source(entry)
                plugin_path = Plugin.fetch(
                    source=source,
                    ref=ref,
                    repo_path=repo_path,
                )
                all_skills.extend(Plugin.load(plugin_path).get_all_skills())
            except Exception:
                logger.warning(
                    "Failed to load plugin '%s' from marketplace '%s'",
                    entry.name,
                    registration.name,
                    exc_info=True,
                )
    return all_skills


def load_all_skills(
    load_public: bool = True,
    load_user: bool = True,
    load_project: bool = True,
    load_org: bool = True,
    project_dir: str | None = None,
    org_repos: list[tuple[str, str]] | None = None,
    sandbox_exposed_urls: list[ExposedUrlData] | None = None,
    marketplace_path: str | None = DEFAULT_MARKETPLACE_PATH,
    registered_marketplaces: list[MarketplaceRegistration] | None = None,
) -> SkillLoadResult:
    """合并技巧：沙箱<市场<公共<用户<组织<项目。"""
    sources: dict[str, int] = {}
    skill_lists: list[list[Skill]] = []

    # 1. 加载沙箱技能（最低优先级）
    sandbox_skills: list[Skill] = []
    if sandbox_exposed_urls:
        sandbox_skill = create_sandbox_skill(sandbox_exposed_urls)
        if sandbox_skill:
            sandbox_skills.append(sandbox_skill)
    sources["sandbox"] = len(sandbox_skills)
    skill_lists.append(sandbox_skills)

    auto_load_registrations = [
        registration
        for registration in registered_marketplaces or []
        if registration.auto_load
    ]

    marketplace_skills: list[Skill] = []
    if load_public and auto_load_registrations:
        marketplace_skills = load_registered_marketplace_skills(auto_load_registrations)
    sources["registered_marketplaces"] = len(marketplace_skills)
    skill_lists.append(marketplace_skills)

    sdk_base = load_available_skills(
        work_dir=None,
        include_user=load_user,
        include_project=False,
        include_public=load_public,
        marketplace_path=marketplace_path,
    )
    sources["sdk_base"] = len(sdk_base)
    skill_lists.append(list(sdk_base.values()))

    # 4. 加载组织技能（一个或多个存储库合并为单层；
    # 稍后的存储库会覆盖早期的名称冲突）。
    org_skills: list[Skill] = []
    if load_org and org_repos:
        per_repo_skills: list[list[Skill]] = []
        for org_repo_url, org_name in org_repos:
            try:
                per_repo_skills.append(
                    load_org_skills_from_url(
                        org_repo_url=org_repo_url,
                        org_name=org_name,
                    )
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load organization skills for {org_name}: {e}"
                )
        org_skills = merge_skills(per_repo_skills)
        # 始终记录计数（包括 0），以便在请求组织加载时可以看到失败/空的组织加载。
        #
        logger.info(f"Loaded {len(org_skills)} organization skills")
    sources["org"] = len(org_skills)
    skill_lists.append(org_skills)

    # 5. 加载项目技能（最高优先级）
    project_skills = load_available_skills(
        work_dir=project_dir if load_project else None,
        include_user=False,
        include_project=load_project,
        include_public=False,
    )
    sources["project"] = len(project_skills)
    skill_lists.append(list(project_skills.values()))

    # 优先合并所有技能
    all_skills = merge_skills(skill_lists)

    logger.info("Loaded %d skills", len(all_skills))

    return SkillLoadResult(skills=all_skills, sources=sources)


def discover_profile_skills() -> list[Skill]:
    """技能目录 OpenHands 配置文件启动时使用 (#4017)。

    返回合并后的用户+公共技能——确定性来源
    :func:`load_all_skills`。 ``resolve_agent_profile`` 保留所有内容，除了
    该配置文件的 ``disabled_skills`` 拒绝列表。 ``load_all_skills`` 已经吸收并记录了
    源端的良性失败，所以这不会吞掉错误：意外失
    败会传播而不是无声地将配置调整到零技能智能体。

    组织/项目技能需要 auth/工作区上下文在解析时不可用，因此它们不在此目录中。 在拒绝
    名单下是安全的
    model: 目录中缺少的技能永远不会被禁用（它仍然存在）
    加载时打开，e.g。 项目技能延迟加载
    ``LocalConversation``) — 旧的允许列表反而会悬而未决，导致启动失败。
    """
    return list(
        load_all_skills(
            load_public=True,
            load_user=True,
            load_org=False,
            load_project=False,
        ).skills
    )


def discover_public_skill_names() -> set[str]:
    """:func:`discover_profile_skills` 公共层的名称。

    通过名称隐藏公共技能的用户技能属于用户层，就像在合并目录中一样。
    """
    names = load_available_skills(include_public=True)
    return set(names) - set(load_available_skills(include_user=True))


def sync_public_skills() -> tuple[bool, str]:
    """从 GitHub 存储库强制刷新公共技能。

    这会触发缓存技能存储库上的 git pull，以从 OpenHands/extensions 存储库获取最新技能
    。

    Returns:
        （成功：bool，消息：str）的元组。
    """
    try:
        cache_dir = get_skills_cache_dir()
        # strict：失败的获取不得报告为同步。 陈旧的
        # 克隆保留在磁盘上以进行离线技能加载。
        result = update_skills_repository(
            PUBLIC_SKILLS_REPO, PUBLIC_SKILLS_REF, cache_dir, strict=True
        )

        if result:
            _invalidate_public_skills_cache()
            _invalidate_catalog_cache()
            return (True, "Skills repository synced successfully")
        else:
            return (False, "Failed to sync skills repository")
    except Exception as e:
        logger.warning(f"Failed to sync skills repository: {e}")
        return (False, f"Sync failed: {str(e)}")


# ---------------------------------------------------------------------------
# 已安装技能管理（CRUD 运营）
# ---------------------------------------------------------------------------


def service_install_skill(
    source: str,
    ref: str | None = None,
    repo_path: str | None = None,
    force: bool = False,
    installed_dir: Path | None = None,
) -> InstalledSkillInfo:
    """从源安装技能。

    Args:
        source: 技能来源——gitURL、GitHub简写，或者本地路径。
            支持以下格式：
            - GitHub简写：GitHub:OpenHands/extensions/skills/github
            - git URL 加 repo_path:  https://github.com/OpenHands/extensions.git
            - 本地路径：/path/to/skill
        ref: 可选的分支、标记或提交安装。
        repo_path: 存储库内的子目录路径（对于 monorepos）。
        force: 如果为 True，则覆盖现有安装。
        installed_dir: 安装技能的目录。
            默认为~/.openhands/skills/installed/.

    Returns:
        InstalledSkillInfo 包含有关安装的详细信息。

    Raises:
        FileExistsError: 如果技能已安装并且force=False。
        SkillFetchError: 如果获取技能源失败。
        SkillValidationError: 如果技能无效。
    """
    return install_skill(
        source=source,
        ref=ref,
        repo_path=repo_path,
        force=force,
        installed_dir=installed_dir,
    )


def service_uninstall_skill(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称卸载技能。

    Args:
        name: 要卸载的技能名称。
        installed_dir: 安装技能的目录。
            默认为~/.openhands/skills/installed/.

    Returns:
        如果技能已卸载，则为 True；如果未安装，则为 False。
    """
    return uninstall_skill(name=name, installed_dir=installed_dir)


def service_enable_skill(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称启用已安装的技能。

    Args:
        name: 要启用的技能的名称。
        installed_dir: 安装技能的目录。
            默认为~/.openhands/skills/installed/.

    Returns:
        如果该技能已启用，则为 True；如果未找到该技能，则为 False。
    """
    return enable_skill(name=name, installed_dir=installed_dir)


def service_disable_skill(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称禁用已安装的技能。

    Args:
        name: 要禁用的技能名称。
        installed_dir: 安装技能的目录。
            默认为~/.openhands/skills/installed/.

    Returns:
        True 如果该技能被禁用，False 如果未找到。
    """
    return disable_skill(name=name, installed_dir=installed_dir)


def service_list_installed_skills(
    installed_dir: Path | None = None,
) -> list[InstalledSkillInfo]:
    """列出所有已安装的技能。

    自我修复：使元数据与磁盘上的内容保持一致。

    Args:
        installed_dir: 安装技能的目录。
            默认为~/.openhands/skills/installed/.

    Returns:
        所有已安装技能的 InstalledSkillInfo 对象列表。
    """
    return list_installed_skills(installed_dir=installed_dir)


def service_get_installed_skill(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledSkillInfo | None:
    """获取有关特定已安装技能的信息。

    Args:
        name: 要获得的技能名称。
        installed_dir: 安装技能的目录。
            默认为~/.openhands/skills/installed/.

    Returns:
        如果找到则为 InstalledSkillInfo，否则为 None。
    """
    return get_installed_skill(name=name, installed_dir=installed_dir)


def service_update_skill(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledSkillInfo | None:
    """将已安装的技能更新到最新版本。

    Args:
        name: 要更新的技能名称。
        installed_dir: 安装技能的目录。
            默认为~/.openhands/skills/installed/.

    Returns:
        如果成功则更新 InstalledSkillInfo，如果未找到技能则更新 None。
    """
    return update_skill(name=name, installed_dir=installed_dir)


class MarketplaceSkillInfo(BaseModel):
    """有关市场目录中技能的信息。"""

    name: str
    description: str | None
    source: str
    installed: bool


# ---------------------------------------------------------------------------
# 市场目录缓存
# ---------------------------------------------------------------------------
# 每次调用 service_get_marketplace_catalog 都会通过 update_skills_repository 触发 git
# fetch，这是一个需要数秒时间的网络绑定操作。 简短的 TTL 缓存可以避免每个打开的选项卡都
# 受到点击。
#
# 仅缓存目录结构（名称、描述、来源）； 的
# `installed` 字段始终从本地 FS 中新鲜派生，以便立即反映安装/卸载操作。 空结果不会被缓存
# ，成功的 sync_public_skills 会清除缓存。
#
# 线程安全并发缓存未命中（冷启动或 TTL 失效）可能会触发并行的 git fetch，但每次 fetch 都
# 是幂等的，并且会产生相同的结果（最后写入者获胜）。 对于这种低流量端点，如果没有明确的
# 锁，雷群风险是可以接受的。
#
# 类型：（时间戳、列表-（名称、描述、来源））或 None
_CatalogEntry = tuple[str, str | None, str]
_catalog_cache: tuple[float, list[_CatalogEntry]] | None = None
_CATALOG_TTL_SECONDS = 300  # 5分钟


def _invalidate_catalog_cache() -> None:
    """删除缓存的市场目录，以便下一次调用重新读取克隆。"""
    global _catalog_cache
    _catalog_cache = None


def service_get_marketplace_catalog(
    marketplace_path: str = DEFAULT_MARKETPLACE_PATH,
    installed_dir: Path | None = None,
) -> list[MarketplaceSkillInfo]:
    """获取包含安装状态的市场目录。

    从公共扩展存储库加载市场 JSON，并通过安装状态丰富每个条目。

    目录结构（名称、描述、源）被缓存为 _CATALOG_TTL_SECONDS，以避免每次调用时进行 git
     fetch。 的
    ``installed`` 字段始终从本地 FS 新鲜解析。

    Args:
        marketplace_path: 市场 JSON 文件的相对路径。
            默认为市场/default.json。
        installed_dir: 用于检查状态的已安装技能的目录。
            默认为~/.openhands/skills/installed/.

    Returns:
        MarketplaceSkillInfo 列表，包含技能详细信息和安装状态。
    """
    global _catalog_cache

    now = monotonic()
    if _catalog_cache is not None and now - _catalog_cache[0] < _CATALOG_TTL_SECONDS:
        entries = _catalog_cache[1]
    else:
        entries = _fetch_catalog_entries(marketplace_path)
        # 仅缓存非空结果，因此瞬时提取失败不会清空整个 TTL 的目录。
        #
        if entries:
            _catalog_cache = (now, entries)

    # 始终全新安装的检查 - 本地 FS 扫描，而不是网络调用。
    installed_names = {
        s.name for s in service_list_installed_skills(installed_dir=installed_dir)
    }
    return [
        MarketplaceSkillInfo(
            name=name, description=desc, source=src, installed=name in installed_names
        )
        for name, desc, src in entries
    ]


def _fetch_catalog_entries(marketplace_path: str) -> list[_CatalogEntry]:
    """从公共扩展存储库中获取市场目录条目。

    这是一条慢速路径：它执行 git fetch + 读取市场 JSON。 结果由调用者缓存。

    Returns:
        （名称、描述、源）元组列表，或出错时为空列表。
    """
    cache_dir = get_skills_cache_dir()
    repo_path = update_skills_repository(
        PUBLIC_SKILLS_REPO, PUBLIC_SKILLS_REF, cache_dir
    )

    if repo_path is None:
        logger.warning("Failed to access public skills repository")
        return []

    marketplace_file = repo_path / marketplace_path
    if not marketplace_file.exists():
        logger.warning(f"Marketplace file not found: {marketplace_file}")
        return []

    try:
        marketplace = Marketplace.load(repo_path)
    except (FileNotFoundError, ValueError) as e:
        # 回退方案从特定路径加载
        try:
            with open(marketplace_file, encoding="utf-8") as f:
                data = json.load(f)
            marketplace = Marketplace.model_validate(
                {**data, "path": to_posix_path(repo_path)}
            )
        except (json.JSONDecodeError, ValidationError, OSError) as e2:
            logger.warning(f"Failed to load marketplace: {e}, {e2}")
            return []

    # 从插件和技能构建目录。 插件优先：如果名称同时出现在插件和技能中，则使用插件版本（
    # 因为首先添加插件）。
    #
    entries: dict[str, _CatalogEntry] = {}

    for plugin in marketplace.plugins:
        source, ref, subpath = marketplace.resolve_plugin_source(plugin)
        # 为市场目录构建完整的源字符串。
        # 格式：“GitHub:owner/repo@ref/path” - SDK 的 install_skill
        # 可以解析此格式，因此前端可以将其直接传递到安装端点的源字段。
        #
        if ref:
            source = f"{source}@{ref}"
        if subpath:
            source = f"{source}/{subpath}"
        entries[plugin.name] = (plugin.name, plugin.description, source)

    for skill_entry in marketplace.skills:
        if skill_entry.name not in entries:
            entries[skill_entry.name] = (
                skill_entry.name,
                skill_entry.description,
                skill_entry.source,
            )

    return list(entries.values())
