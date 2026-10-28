"""AgentSkills 来源的技能获取实用程序。

委托：mod:`openhands.sdk.extensions.fetch` 执行实际的获取逻辑，并将错误重新引发为：
class:`SkillFetchError` 以保
留现有的公共接口。
"""

from __future__ import annotations

from pathlib import Path

from openhands.sdk.extensions.fetch import (
    ExtensionFetchError,
    fetch_with_resolution as _ext_fetch_with_resolution,
)
from openhands.sdk.git.cached_repo import GitHelper
from openhands.sdk.utils.path import get_user_persistence_dir


DEFAULT_CACHE_DIR = get_user_persistence_dir() / "cache" / "skills"


class SkillFetchError(Exception):
    """当获取技能失败时引发。"""


def fetch_skill(
    source: str,
    cache_dir: Path | None = None,
    ref: str | None = None,
    update: bool = True,
    repo_path: str | None = None,
    git_helper: GitHelper | None = None,
) -> Path:
    """从源获取技能并返回本地路径。

    Args:
        source: 技能来源——gitURL、GitHub简写，或者本地路径。
        cache_dir: 用于缓存的目录。 默认为~/.openhands/cache/skills/.
        ref: 可选分支、标记或提交结账。
        update: 如果True和缓存存在，则更新它。
        repo_path: 存储库内的子目录路径。
        git_helper: GitHelper 实例（用于测试）。

    Returns:
        本地技能目录的路径。
    """
    path, _ = fetch_skill_with_resolution(
        source=source,
        cache_dir=cache_dir,
        ref=ref,
        update=update,
        repo_path=repo_path,
        git_helper=git_helper,
    )
    return path


def fetch_skill_with_resolution(
    source: str,
    cache_dir: Path | None = None,
    ref: str | None = None,
    update: bool = True,
    repo_path: str | None = None,
    git_helper: GitHelper | None = None,
) -> tuple[Path, str | None]:
    """获取技能并返回路径和已解决的提交 SHA。

    Args:
        source: 技能来源（gitURL、GitHub简写，或本地路径）。
        cache_dir: 用于缓存的目录。 默认为~/.openhands/cache/skills/.
        ref: 可选分支、标记或提交结账。
        update: 如果True和缓存存在，则更新它。
        repo_path: 存储库内的子目录路径。
        git_helper: GitHelper 实例（用于测试）。

    Returns:
        (path, resolved_ref) 的元组，其中 resolved_ref 是 git 源的提交 SHA，None 是本
        地路径。

    Raises:
        SkillFetchError: 如果获取技能失败。
    """
    resolved_cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    try:
        return _ext_fetch_with_resolution(
            source=source,
            cache_dir=resolved_cache_dir,
            ref=ref,
            update=update,
            repo_path=repo_path,
            git_helper=git_helper,
        )
    except ExtensionFetchError as exc:
        raise SkillFetchError("Failed to fetch skill") from exc
