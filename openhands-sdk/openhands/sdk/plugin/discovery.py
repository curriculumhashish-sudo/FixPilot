"""发现 OpenHands SDK 的本地可用插件。

镜像 ``skills/skill.py`` 中的用户/项目技能发现，但运行于
``Plugin`` 个对象（通过 ``Plugin.load`` 加载）而不是技能。

这些函数构建了自动加载到交互式环境中的 *ambient* 插件集
conversations (see ``LocalConversation._ensure_plugins_loaded``): 找到插件
在用户的主目录中，在项目/工作空间目录中，以及通过 ``install_plugin`` /
``enable_plugin`` 管理的启用的已安装插件。 这是安装/本地技
能如何自动加载的插件模拟。
"""

from __future__ import annotations

from pathlib import Path

from openhands.sdk.logger import get_logger
from openhands.sdk.plugin.installed import (
    get_installed_plugins_dir,
    load_installed_plugins,
)
from openhands.sdk.plugin.plugin import Plugin
from openhands.sdk.skills.skill import _find_git_repo_root
from openhands.sdk.utils.path import get_user_persistence_dir


logger = get_logger(__name__)


# 用户级插件目录，按优先顺序排列（名称冲突时较早的获胜）。 镜子USER_SKILLS_DIRS.
#
USER_PLUGINS_DIRS = [
    Path.home() / ".agents" / "plugins",
    get_user_persistence_dir() / "plugins",
]

# 在每个搜索根下扫描项目级插件子目录。
PROJECT_PLUGINS_SUBDIRS = [
    Path(".agents") / "plugins",
    Path(".openhands") / "plugins",
]


def _load_plugins_from_dir(plugins_dir: Path, skip_dirs: set[Path]) -> list[Plugin]:
    """加载 ``plugins_dir`` 中的每个插件子目录。

    镜像 ``Plugin.load_all`` 但跳过 ``skip_dirs`` 中的任何目录。 这是必需的，因为已安
    装的插件存储位于
    ``~/.openhands/plugins/installed`` — 一个 ``~/.openhands/plugins`` 的子类 — 且不
    得加载为插件（因为
    它没有 manifest，所以会被误加载为名为“已安装”的假插件）。 加载单个插件失败的情况
    会被记录并跳过。
    """
    if not plugins_dir.is_dir():
        return []

    plugins: list[Plugin] = []
    for item in sorted(plugins_dir.iterdir()):
        if not item.is_dir():
            continue
        if item.resolve() in skip_dirs:
            continue
        try:
            plugins.append(Plugin.load(item))
        except Exception as e:
            logger.warning(f"Failed to load plugin from {item}: {e}")
    return plugins


def _merge_plugins_by_name(
    new_plugins: list[Plugin],
    seen_names: set[str],
    out: list[Plugin],
    source_label: str,
) -> None:
    """将 ``new_plugins`` 附加到 ``out``，跳过 ``seen_names`` 中已有的名称。

    较早的调用者优先处理重复的名称（适当改变 ``seen_names`` 和 ``out``）。
    """
    for plugin in new_plugins:
        if plugin.name in seen_names:
            logger.warning(
                f"Skipping duplicate plugin '{plugin.name}' from {source_label}"
            )
            continue
        seen_names.add(plugin.name)
        out.append(plugin)


def load_user_plugins() -> list[Plugin]:
    """从用户的主目录加载插件以及启用的已安装插件。

    扫描 ``~/.agents/plugins``，然后扫描 ``~/.openhands/plugins``（较早的名称冲突胜出
    ），然后附加已启用的已安装插件
    ``~/.openhands/plugins/installed``（优先级低于目录插件）。 已安装的商店被排除在目
    录扫描之外，因此它本身不会作为插件加载。

    镜子``load_user_skills``. 如果未找到任何内容或加载失败，则返回空列表。
    """
    all_plugins: list[Plugin] = []
    seen_names: set[str] = set()
    # 通过 get_installed_plugins_dir() （不是捕获的常量）解析，以便跳过跟踪
    # load_installed_plugins() 读取的相同安装存储。
    #
    installed_dir = get_installed_plugins_dir().resolve()

    for plugins_dir in USER_PLUGINS_DIRS:
        found = _load_plugins_from_dir(plugins_dir, skip_dirs={installed_dir})
        _merge_plugins_by_name(found, seen_names, all_plugins, str(plugins_dir))

    # 启用已安装的插件（优先级低于目录插件）。
    try:
        for plugin in load_installed_plugins():
            if plugin.name not in seen_names:
                seen_names.add(plugin.name)
                all_plugins.append(plugin)
    except Exception as e:
        logger.warning(f"Failed to load installed plugins: {e}")

    logger.debug(
        f"Loaded {len(all_plugins)} user plugins: {[p.name for p in all_plugins]}"
    )
    return all_plugins


def load_project_plugins(work_dir: str | Path) -> list[Plugin]:
    """从项目特定的目录加载插件。

    扫描 ``{root}/.agents/plugins`` 和 ``{root}/.openhands/plugins`` 中的工作目录和（
    如果不同）封闭的 Git
     存储库根目录，如果名称冲突，则工作目录优先。

    镜子``load_project_skills``. 如果未找到任何内容或加载失败，则返回空列表。
    """
    work_dir = Path(work_dir)

    all_plugins: list[Plugin] = []
    seen_names: set[str] = set()

    git_root = _find_git_repo_root(work_dir)

    # 工作目录优先（更多本地规则覆盖 repo-root 规则）。
    search_roots: list[Path] = [work_dir]
    if git_root is not None and git_root != work_dir:
        search_roots.append(git_root)

    for root in search_roots:
        for subdir in PROJECT_PLUGINS_SUBDIRS:
            plugins_dir = root / subdir
            found = _load_plugins_from_dir(plugins_dir, skip_dirs=set())
            _merge_plugins_by_name(found, seen_names, all_plugins, str(plugins_dir))

    logger.debug(
        f"Loaded {len(all_plugins)} project plugins: {[p.name for p in all_plugins]}"
    )
    return all_plugins


def load_available_plugins(
    work_dir: str | Path | None = None,
    *,
    include_user: bool = False,
    include_project: bool = False,
) -> dict[str, Plugin]:
    """以一致的优先级加载和合并本地可用的插件。

    优先级（稍后通过字典更新覆盖之前的内容）：
        用户（最低）→项目（最高）

    用户集已折叠在已启用的已安装插件中（用户集内最低）。 这是构建合并到对话、镜像
    ``load_available_skills`` 中的 *ambient* 插件集
    的单一入口点。

    Args:
        work_dir: 项目插件的项目/工作目录。 当None时，
            无论 ``include_project`` 如何，都会跳过项目插件。
        include_user: 加载用户级插件（``~/.agents/plugins``等）和
            启用已安装的插件。
        include_project: 加载项目级插件（需要 ``work_dir``）。

    Returns:
        字典映射插件名称 → 插件，优先级较高的源优先于优先级较低的源。
    """
    available: dict[str, Plugin] = {}

    if include_user:
        try:
            for plugin in load_user_plugins():
                available[plugin.name] = plugin
        except Exception as e:
            logger.warning(f"Failed to load user plugins: {e}")

    if include_project and work_dir:
        try:
            for plugin in load_project_plugins(work_dir):
                available[plugin.name] = plugin
        except Exception as e:
            logger.warning(f"Failed to load project plugins: {e}")

    return available
