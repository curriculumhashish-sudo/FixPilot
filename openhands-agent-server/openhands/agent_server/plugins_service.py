"""OpenHands Agent Server 的插件服务。

两个相关问题的业务逻辑，都反映了其对应的技能 (``skills_service.py``)，因此路由器始终
专注于 HTTP：

* 已安装插件管理 - SDK 的已安装插件子系统 (``openhands.sdk.plugin``) 上的薄包装器 -
加上列出本地可用的插件。
* *仅限插件*市场目录。 它仅返回来自 OpenHands 扩展市场的 True 个插件 — ``source`` 所
在的条目
  ``./plugins/`` — 每个都携带可附带的 ``PluginSource`` 坐标 (``source`` / ``ref`` /
  ``repo_path``
  ) 加上一个 ``installed`` 标志，因此前端可以驱动 *attach* 和 *install* 并显示安装状
  态。
"""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from time import monotonic

from pydantic import BaseModel, ValidationError

from openhands.sdk.logger import get_logger
from openhands.sdk.marketplace import Marketplace
from openhands.sdk.plugin import (
    CheckedPlugin,
    InstalledPluginInfo,
    Plugin,
    disable_plugin,
    enable_plugin,
    get_installed_plugin,
    install_plugin,
    list_installed_plugins,
    uninstall_plugin,
    update_plugin,
)
from openhands.sdk.plugin.strict_fetch import fetch_plugin_strict
from openhands.sdk.secret import SecretValue
from openhands.sdk.skills.skill import (
    DEFAULT_MARKETPLACE_PATH,
    PUBLIC_SKILLS_REF,
    PUBLIC_SKILLS_REPO,
)
from openhands.sdk.skills.utils import (
    get_skills_cache_dir,
    update_skills_repository,
)
from openhands.sdk.utils.path import to_posix_path


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 已安装插件管理
# ---------------------------------------------------------------------------


def service_install_plugin(
    source: str,
    ref: str | None = None,
    repo_path: str | None = None,
    force: bool = False,
    installed_dir: Path | None = None,
) -> InstalledPluginInfo:
    """将插件从源安装到installed-plugins目录中。"""
    return install_plugin(
        source=source,
        ref=ref,
        repo_path=repo_path,
        force=force,
        installed_dir=installed_dir,
    )


def service_fetch_plugin(
    source: str,
    ref: str | None = None,
    repo_path: str | None = None,
    secrets: Mapping[str, SecretValue] | None = None,
    timeout: int = 60,
) -> CheckedPlugin:
    """严格将插件获取到不可变插件缓存中。"""
    return fetch_plugin_strict(
        source=source,
        ref=ref,
        repo_path=repo_path,
        secrets=secrets,
        timeout=timeout,
        allow_local=True,
        use_cache=True,
    )


def service_uninstall_plugin(name: str, installed_dir: Path | None = None) -> bool:
    """按名称卸载插件。 如果未安装，则返回 False。"""
    return uninstall_plugin(name, installed_dir=installed_dir)


def service_enable_plugin(name: str, installed_dir: Path | None = None) -> bool:
    """启用已安装的插件。 如果未安装，则返回 False。"""
    return enable_plugin(name, installed_dir=installed_dir)


def service_disable_plugin(name: str, installed_dir: Path | None = None) -> bool:
    """禁用已安装的插件。 如果未安装，则返回 False。"""
    return disable_plugin(name, installed_dir=installed_dir)


def service_list_installed_plugins(
    installed_dir: Path | None = None,
) -> list[InstalledPluginInfo]:
    """列出所有已安装的插件（启用和禁用）。"""
    return list_installed_plugins(installed_dir=installed_dir)


def service_get_installed_plugin(
    name: str, installed_dir: Path | None = None
) -> InstalledPluginInfo | None:
    """获取特定安装的插件，或者 None 如果它未安装。"""
    return get_installed_plugin(name, installed_dir=installed_dir)


def service_update_plugin(
    name: str, installed_dir: Path | None = None
) -> InstalledPluginInfo | None:
    """更新已安装的插件，如果未安装则更新 None。"""
    return update_plugin(name, installed_dir=installed_dir)


def service_list_available_plugins(
    load_user: bool = True,
    load_project: bool = True,
    project_dir: str | None = None,
) -> list[Plugin]:
    """列出本地可用的插件（已启用的已安装+用户/项目目录）。

    ``load_available_plugins`` 由“有线安装 + 本地插件自动加载”票证 (
    ``openhands.sdk.plugin.discovery``) 提供。 它是延迟导入的，因此该模块在合并该票证
    之前干净地导入； 这个端点一旦落地就可以发挥作
    用。
    """
    from openhands.sdk.plugin import load_available_plugins  # type: ignore

    available = load_available_plugins(
        work_dir=project_dir,
        include_user=load_user,
        include_project=load_project,
    )
    return list(available.values())


# ---------------------------------------------------------------------------
# 插件内容（捆绑技能+文件列表）
# ---------------------------------------------------------------------------

# 目录从未在插件的文件树中列出。 Whole-repo 安装逐字复制获取的克隆（包括 ``.git``），这
# 将用存储库内部淹没列表。
#
_PLUGIN_FILES_EXCLUDED_DIRS = {".git"}
# 列出文件的上限，因此是一个病态插件（e.g. 大型存储库的整个存储库安装）无法膨胀 API 载荷
# 。
#
_PLUGIN_FILES_LIMIT = 2000


class PluginSkillSummary(BaseModel):
    """插件中捆绑的技能摘要。"""

    name: str
    description: str | None = None


def _list_plugin_files(root: Path) -> list[str]:
    """按排序的 POSIX、根相对路径列出插件目录的文件。

    使用 ``os.walk``，排除的目录在被进入之前会被修剪，而符号链接的目录则永远不会被跟
    随（真实插件会包含类似于
    ``.claude-plugin -> .plugin`` 的 manifest-dir 符号链接）。
    """
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _PLUGIN_FILES_EXCLUDED_DIRS]
        for filename in filenames:
            files.append((Path(dirpath) / filename).relative_to(root).as_posix())
    files.sort()
    return files[:_PLUGIN_FILES_LIMIT]


def service_plugin_contents(
    plugin: Plugin,
) -> tuple[list[PluginSkillSummary], list[str]]:
    """已加载插件的内容：捆绑技能+文件列表。

    技能包括命令派生技能 (``<plugin>:<command>``)，与插件对对话的实际贡献相匹配。
    """
    skills = [
        PluginSkillSummary(name=skill.name, description=skill.description)
        for skill in plugin.get_all_skills()
    ]
    return skills, _list_plugin_files(Path(plugin.path))


def service_load_plugin_contents(
    plugin_dir: str | Path,
) -> tuple[list[PluginSkillSummary], list[str]] | None:
    """加载插件目录的内容，如果无法加载，则加载 None。

    永不引发：损坏或消失的插件目录不得破坏嵌入这些内容的列表。
    """
    try:
        plugin = Plugin.load(plugin_dir)
    except Exception as e:
        logger.warning(f"Failed to load plugin contents from {plugin_dir}: {e}")
        return None
    return service_plugin_contents(plugin)


# ---------------------------------------------------------------------------
# 仅插件市场目录
# ---------------------------------------------------------------------------

# 的 OpenHands 扩展市场清单了技能和 True 它下的插件 ``plugins`` 数组，仅根据其来源路径区
# 分： True 插件位于  ``./plugins/`` 技能在时 ``./skills/``. 我们根据原始源进行筛选（)不
#   plugin.json  现在， 这些技能已经过时了。
#
_PLUGINS_SOURCE_PREFIX = "./plugins/"
# 当条目使用带有显式子路径的结构化源对象 (github/url) 时的等效前缀。
#
_PLUGINS_SUBPATH_PREFIX = "plugins/"


class MarketplacePluginInfo(BaseModel):
    """市场目录中的 True 插件，带有附加坐标。"""

    name: str
    description: str | None
    source: str
    ref: str | None = None
    repo_path: str | None = None
    installed: bool
    # 本地内容——当条目解析为本地市场克隆中的目录时填充； None 当内容在本地不可用时 (e.g.
    #  指向另一个存储库的结构化源）。
    #
    path: str | None = None
    skills: list[PluginSkillSummary] | None = None
    files: list[str] | None = None


# ---------------------------------------------------------------------------
# 市场目录缓存
# ---------------------------------------------------------------------------
# 镜像技能市场缓存：否则每次调用都会触发 git fetch（网络绑定，多秒）。 简短的 TTL 可以避
# 免在每个打开的选项卡上出现这种情况。 仅缓存目录结构； ``installed`` 始终源自本地 FS。
# 与技能缓存不同，*空*结果(e.g. 短暂的提取失败）被缓存不，因此一次不稳定的提取不会清空整
# 个目录TTL。
#
# 缓存条目是用 ``installed=False`` 存储的完整 MarketplacePluginInfo 对象（包括内容）；
# 通过浅层 ``model_copy`` 服务新鲜安装标志，因此 ``skills``/``files`` 列表在请求之间共享
#  —— 它们在构建后不会被修改。
#
# 类型：（时间戳，已安装的目录条目=False）或None
_plugin_catalog_cache: tuple[float, list[MarketplacePluginInfo]] | None = None
_PLUGIN_CATALOG_TTL_SECONDS = 300  # 5分钟


def service_get_plugins_marketplace_catalog(
    marketplace_path: str = DEFAULT_MARKETPLACE_PATH,
    installed_dir: Path | None = None,
) -> list[MarketplacePluginInfo]:
    """获取包含安装状态的仅限插件的市场目录。

    加载市场 JSON 于公共扩展仓库，仅保留 True 个插件（源代码位于 ``./plugins/``），并
    为每个插件附加其可附带的坐标和安装状态。

    目录结构被缓存为 ``_PLUGIN_CATALOG_TTL_SECONDS`` 以避免每次调用时进行 git fetch。
     ``installed`` 字段始终是
    最新解析的
    from the local FS.

    Args:
        marketplace_path: 市场 JSON 文件的相对路径。
        installed_dir: 用于检查状态的已安装插件的目录。
            默认为 ``~/.openhands/plugins/installed/``。

    Returns:
        MarketplacePluginInfo 列表，包含插件详细信息和安装状态。
    """
    global _plugin_catalog_cache

    now = monotonic()
    if (
        _plugin_catalog_cache is not None
        and now - _plugin_catalog_cache[0] < _PLUGIN_CATALOG_TTL_SECONDS
    ):
        entries = _plugin_catalog_cache[1]
    else:
        entries = _fetch_plugin_catalog_entries(marketplace_path)
        # 仅缓存非空结果，因此瞬时提取失败不会清空整个 TTL 的目录。
        #
        if entries:
            _plugin_catalog_cache = (now, entries)

    # 始终全新安装的检查 - 本地 FS 扫描，而不是网络调用。
    installed_names = {
        p.name for p in list_installed_plugins(installed_dir=installed_dir)
    }
    return [
        entry.model_copy(update={"installed": entry.name in installed_names})
        for entry in entries
    ]


def _is_true_plugin(raw_source: object) -> bool:
    """市场条目的 *raw* 源是否指向 True 插件。

    必须在原始源上运行之前 ``resolve_plugin_source`` 将相对路径重写为绝对路径（这会删
    除 ``./plugins/`` 前缀）。 字符串源在
    ``./plugins/`` 下时是 True 插件； 当其子路径位于 ``plugins/`` 下时结构化源对象。
    技能 (``./skills/``) 被排除在
    外。
    """
    if isinstance(raw_source, str):
        return raw_source.startswith(_PLUGINS_SOURCE_PREFIX)
    subpath = getattr(raw_source, "path", None) or ""
    return subpath.startswith(_PLUGINS_SUBPATH_PREFIX)


def _fetch_plugin_catalog_entries(
    marketplace_path: str,
) -> list[MarketplacePluginInfo]:
    """获取市场并仅保留 True 个插件。

    慢速路径：git fetch + 读取市场JSON。 返回目录条目
    with ``installed=False`` (the caller stamps the fresh value), enriched with
    本地内容（``path``/``skills``/``files``)，当条目解析为本地克隆内的目录时。 出错时
    返回空列表。
    """
    cache_dir = get_skills_cache_dir()
    repo_path = update_skills_repository(
        PUBLIC_SKILLS_REPO, PUBLIC_SKILLS_REF, cache_dir
    )

    if repo_path is None:
        logger.warning("Failed to access public extensions repository")
        return []

    # 主加载程序：``Marketplace.load`` 发现清单
    # ``.plugin/`` 或 ``.claude-plugin/`` — 真实的 OpenHands/扩展布局，其中
    # ``.plugin/marketplace.json`` 指向已发布的目录。 我们必须不控制
    # ``marketplace_path`` (``marketplaces/default.json``) 现有的
    # 第一：当前扩展存储库中不存在该文件，因此早期
    # 即使清单存在，返回那里也会将目录清空。 显式 ``marketplace_path`` 文件只是用于传送
    # 它的布局的回退方案，而不是 ``.plugin/`` 清单。
    #
    try:
        marketplace = Marketplace.load(repo_path)
    except (FileNotFoundError, ValueError) as e:
        marketplace_file = repo_path / marketplace_path
        if not marketplace_file.exists():
            logger.warning(
                f"Failed to load marketplace via manifest discovery ({e}); "
                f"fallback file not found: {marketplace_file}"
            )
            return []
        try:
            with open(marketplace_file, encoding="utf-8") as f:
                data = json.load(f)
            marketplace = Marketplace.model_validate(
                {**data, "path": to_posix_path(repo_path)}
            )
        except (json.JSONDecodeError, ValidationError, OSError) as e2:
            logger.warning(f"Failed to load marketplace: {e}, {e2}")
            return []

    entries: list[MarketplacePluginInfo] = []
    for plugin in marketplace.plugins:
        if not _is_true_plugin(plugin.source):
            continue
        # 解析为可附加的坐标。 对于本地 ./plugins/<name> 条目，这会产生带有 ref/
        # repo_path None 的绝对路径； 结构化的 github/url 源产生它们的 ref + 子路径。
        #
        source, ref, repo_path = marketplace.resolve_plugin_source(plugin)
        entry = MarketplacePluginInfo(
            name=plugin.name,
            description=plugin.description,
            source=source,
            ref=ref,
            repo_path=repo_path,
            installed=False,
        )
        # 本地 ./plugins/<name> 条目解析为缓存克隆内的目录，因此可以从磁盘加载其内容。
        # 结构化 github/url 源可能指向其他存储库 - 没有本地副本，因此它们的内容保留 None
        # 。
        #
        if ref is None and repo_path is None and Path(source).is_dir():
            contents = service_load_plugin_contents(source)
            if contents is not None:
                skills, files = contents
                entry = entry.model_copy(
                    update={
                        "path": to_posix_path(source),
                        "skills": skills,
                        "files": files,
                    }
                )
        entries.append(entry)

    return entries
