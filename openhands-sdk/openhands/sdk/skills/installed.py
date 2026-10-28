"""已安装 OpenHands SDK 的技能管理。

公共API用于管理安装在用户主目录中的AgentSkills。 所有繁重的工作都委托给
``InstallationManager``。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from openhands.sdk.extensions.installation import (
    InstallationInfo,
    InstallationInterface,
    InstallationManager,
)
from openhands.sdk.logger import get_logger
from openhands.sdk.skills.exceptions import SkillValidationError
from openhands.sdk.skills.skill import Skill
from openhands.sdk.skills.utils import find_skill_md
from openhands.sdk.utils.path import get_user_persistence_dir, to_posix_path


if TYPE_CHECKING:
    from openhands.sdk.marketplace import Marketplace, MarketplaceRegistration


logger = get_logger(__name__)

# 公共类型别名 - 保持现有导入站点正常运行。
InstalledSkillInfo = InstallationInfo

DEFAULT_INSTALLED_SKILLS_DIR = get_user_persistence_dir() / "skills" / "installed"


def get_installed_skills_dir() -> Path:
    """获取已安装技能的默认目录。"""
    return DEFAULT_INSTALLED_SKILLS_DIR


# ---------------------------------------------------------------------------
# 内部帮手
# ---------------------------------------------------------------------------


def _load_skill_from_dir(skill_root: Path, strict: bool = True) -> Skill:
    """从根目录加载技能。"""
    skill_md = find_skill_md(skill_root)
    if not skill_md:
        raise SkillValidationError(f"Skill directory is missing SKILL.md: {skill_root}")
    try:
        return Skill.load(skill_md, strict=strict)
    except yaml.YAMLError as e:
        raise SkillValidationError(f"Invalid frontmatter in {skill_md}: {e}") from e


def load_marketplace_standalone_skills(
    marketplace: Marketplace,
    marketplace_path: Path,
    registration: MarketplaceRegistration,
) -> list[Skill]:
    """加载市场的自动加载独立技能。

    ``marketplace.skills`` 插件自动加载路径的镜像：每个注册的技能在市场库（或远程源）
    相对于的相对路径中解析并加载。 无法解析的来源和缺少的技能
    SKILL.md 将被跳过并发出警告，因此一个错误的条目永远不会阻止 REST。
    """
    from openhands.sdk.plugin import resolve_source_path

    skills: list[Skill] = []
    for entry in marketplace.skills:
        if not registration.auto_loads_skill(entry.name):
            continue
        skill_dir = resolve_source_path(entry.source, base_path=marketplace_path)
        if skill_dir is None:
            logger.warning(
                "Skill '%s' from marketplace '%s' could not be resolved; skipping",
                entry.name,
                registration.name,
            )
            continue
        try:
            skills.append(_load_skill_from_dir(skill_dir, strict=False))
        except Exception:
            logger.warning(
                "Failed to load skill '%s' from marketplace '%s'",
                entry.name,
                registration.name,
                exc_info=True,
            )
    return skills


class SkillInstallationInterface(InstallationInterface[Skill]):
    @staticmethod
    def load_from_dir(extension_dir: Path) -> Skill:
        return _load_skill_from_dir(extension_dir)


def _resolve_installed_dir(installed_dir: Path | None) -> Path:
    return installed_dir if installed_dir is not None else DEFAULT_INSTALLED_SKILLS_DIR


def _manager(installed_dir: Path) -> InstallationManager[Skill]:
    return InstallationManager(
        installation_dir=installed_dir,
        installation_interface=SkillInstallationInterface(),
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def install_skill(
    source: str,
    ref: str | None = None,
    repo_path: str | None = None,
    installed_dir: Path | None = None,
    force: bool = False,
) -> InstalledSkillInfo:
    """从源安装技能。

    Args:
        source: 技能来源——gitURL、GitHub简写，或者本地路径。
        ref: 可选的分支、标记或提交安装。
        repo_path: 存储库内的子目录路径（对于 monorepos）。
        installed_dir: 安装技能的目录。
            默认为 ``~/.openhands/skills/installed/``。
        force: 如果为 True，则覆盖现有安装。

    Returns:
        InstalledSkillInfo 包含有关安装的详细信息。
    """
    return _manager(_resolve_installed_dir(installed_dir)).install(
        source, ref=ref, repo_path=repo_path, force=force
    )


def uninstall_skill(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称卸载技能。

    Returns:
        如果技能已卸载，则为 True；如果未安装，则为 False。
    """
    return _manager(_resolve_installed_dir(installed_dir)).uninstall(name)


def enable_skill(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称启用已安装的技能。"""
    return _manager(_resolve_installed_dir(installed_dir)).enable(name)


def disable_skill(
    name: str,
    installed_dir: Path | None = None,
) -> bool:
    """按名称禁用已安装的技能。"""
    return _manager(_resolve_installed_dir(installed_dir)).disable(name)


def list_installed_skills(
    installed_dir: Path | None = None,
) -> list[InstalledSkillInfo]:
    """列出所有已安装的技能。

    自我修复：使元数据与磁盘上的内容保持一致。
    """
    return _manager(_resolve_installed_dir(installed_dir)).list_installed()


def load_installed_skills(
    installed_dir: Path | None = None,
) -> list[Skill]:
    """将所有启用的已安装技能加载为 ``Skill`` 对象。"""
    return _manager(_resolve_installed_dir(installed_dir)).load_installed()


def get_installed_skill(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledSkillInfo | None:
    """获取有关特定已安装技能的信息。"""
    return _manager(_resolve_installed_dir(installed_dir)).get(name)


def update_skill(
    name: str,
    installed_dir: Path | None = None,
) -> InstalledSkillInfo | None:
    """将已安装的技能更新到最新版本。"""
    return _manager(_resolve_installed_dir(installed_dir)).update(name)


def install_skills_from_marketplace(
    marketplace_path: str | Path,
    installed_dir: Path | None = None,
    force: bool = False,
) -> list[InstalledSkillInfo]:
    """安装 marketplace.json 文件中定义的所有技能。

    Args:
        marketplace_path: 包含目录的路径
            ``.plugin/marketplace.json``.
        installed_dir: 安装技能的目录。
            默认为 ``~/.openhands/skills/installed/``。
        force: 如果为 True，则覆盖现有安装。

    Returns:
        已成功安装技能的 InstalledSkillInfo 列表。
    """
    from openhands.sdk.marketplace import Marketplace
    from openhands.sdk.plugin import resolve_source_path

    marketplace_path = Path(marketplace_path)
    installed_dir = _resolve_installed_dir(installed_dir)

    marketplace = Marketplace.load(marketplace_path)
    installed: list[InstalledSkillInfo] = []

    skill_dirs: list[tuple[str, Path]] = []

    for entry in marketplace.skills:
        resolved = resolve_source_path(
            entry.source, base_path=marketplace_path, update=True
        )
        if resolved and resolved.exists():
            skill_dirs.append((entry.name, resolved))
        else:
            logger.warning(f"Failed to resolve skill '{entry.name}'")

    for plugin in marketplace.plugins:
        if isinstance(plugin.source, str):
            source = plugin.source
        elif plugin.source.repo:
            source = f"https://github.com/{plugin.source.repo}.git"
        elif plugin.source.url:
            source = plugin.source.url
        else:
            logger.warning(f"Plugin '{plugin.name}' has unsupported source")
            continue

        resolved = resolve_source_path(source, base_path=marketplace_path, update=True)
        if not resolved or not resolved.exists():
            logger.warning(f"Failed to resolve plugin '{plugin.name}'")
            continue

        skills_dir = resolved / "skills"
        if not skills_dir.exists():
            continue

        for skill_path in sorted(skills_dir.iterdir()):
            if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
                skill_dirs.append((skill_path.name, skill_path))

    logger.info(f"Found {len(skill_dirs)} skills to install from marketplace")

    for name, path in skill_dirs:
        try:
            info = install_skill(
                to_posix_path(path), installed_dir=installed_dir, force=force
            )
            installed.append(info)
            logger.info(f"Installed skill '{info.name}'")
        except FileExistsError:
            logger.info(f"Skill '{name}' already installed (use force=True)")
        except Exception as e:
            logger.warning(f"Failed to install skill '{name}': {e}")

    logger.info(f"Installed {len(installed)} skills")
    return installed
