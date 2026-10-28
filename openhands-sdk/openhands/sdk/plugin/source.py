"""市场插件和技能的源路径处理。

支持本地路径 ./path /path ~/path file:///path) 和 GitHub URLs (
https://github.com/{owner}/{repo}/blob/{branch}/{path} )。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from openhands.sdk.git.cached_repo import try_cached_clone_or_update
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import (
    get_user_persistence_dir,
    is_absolute_path_source,
    is_local_path_source,
)
from openhands.sdk.utils.redact import redact_url_credentials


logger = get_logger(__name__)

GITHUB_URL_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/"
    r"(?:blob|tree)/(?P<branch>[^/]+)/(?P<path>.+)$"
)
DEFAULT_CACHE_DIR = get_user_persistence_dir() / "cache" / "git"


class GitHubURLComponents(NamedTuple):
    """GitHub blob/树 URL 的已解析组件。"""

    owner: str
    repo: str
    branch: str
    path: str


def parse_github_url(url: str) -> GitHubURLComponents | None:
    """将 GitHub URL 解析为组件，如果不是有效的 GitHub URL，则解析为 None。"""
    if match := GITHUB_URL_PATTERN.match(url):
        return GitHubURLComponents(
            match.group("owner"),
            match.group("repo"),
            match.group("branch"),
            match.group("path"),
        )
    return None


def is_local_path(source: str) -> bool:
    """检查源是否是本地路径（./, ../, /, ~, file://)."""
    return is_local_path_source(source)


def validate_source_path(source: str) -> str:
    """验证源路径格式。 如果无效则提高 ValueError。"""
    if is_local_path(source) or parse_github_url(source):
        return source
    raise ValueError(
        f"Invalid source path: {source!r}. Must be local path or GitHub URL."
    )


def resolve_source_path(
    source: str,
    base_path: Path | None = None,
    cache_dir: Path | None = None,
    update: bool = True,
) -> Path | None:
    """将源路径解析为绝对本地路径。

    Args:
        source: 源路径字符串（本地路径、文件：// URL 或 GitHub URL）。
        base_path: 用于解析相对路径的基目录。
        cache_dir: 用于缓存克隆的 GitHub 存储库的目录。
        update: 是否更新缓存的存储库（git pull）。

    Returns:
        已解析的绝对路径，如果 GitHub 克隆/更新失败，则为 None。 调用者应该优雅地处理
         None（e.g.，跳过并警告）。

    支持的源格式：
        - 本地路径：./path、../path、/absolute、~/home
        - 文件：// URLs 文件：///absolute/path
        - GitHub URLs:  https://github.com/{owner}/{repo}/blob/{branch}/{path}
    """
    # 处理文件：// URLs
    if source.startswith("file://"):
        return Path(source[7:])

    # 处理 GitHub URLs
    if gh := parse_github_url(source):
        cache = cache_dir or DEFAULT_CACHE_DIR
        repo_path = cache / "github.com" / gh.owner.lower() / gh.repo.lower()
        clone_url = f"https://github.com/{gh.owner}/{gh.repo}.git"

        if try_cached_clone_or_update(clone_url, repo_path, gh.branch, update):
            return repo_path / gh.path
        logger.warning(f"Failed to clone/update: {redact_url_credentials(source)}")
        return None

    path = Path(source).expanduser()
    if is_absolute_path_source(source):
        return path
    if base_path:
        return (base_path / path).resolve()
    return path.resolve()
