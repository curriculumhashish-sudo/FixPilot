"""用于远程插件源的插件获取实用程序。

委托：mod:`openhands.sdk.extensions.fetch` 执行实际的获取逻辑，并将错误重新引发为：
class:`PluginFetchError` 以
保留现有的公共接口。
"""

from __future__ import annotations

import re
from pathlib import Path

from openhands.sdk.extensions.fetch import (
    ExtensionFetchError,
    SourceType,
    fetch_with_resolution as _ext_fetch_with_resolution,
    parse_extension_source,
)
from openhands.sdk.git.cached_repo import GitHelper
from openhands.sdk.plugin.paths import get_pinned_plugin_cache_path
from openhands.sdk.utils.path import get_user_persistence_dir


DEFAULT_CACHE_DIR = get_user_persistence_dir() / "cache" / "plugins"
_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class PluginFetchError(Exception):
    """获取插件失败时引发。"""


def _cached_pinned_plugin(
    source: str, cache_dir: Path, ref: str, repo_path: str | None
) -> Path | None:
    try:
        source_type, url = parse_extension_source(source)
    except ExtensionFetchError:
        return None
    if source_type == SourceType.LOCAL:
        return None

    cached_root = get_pinned_plugin_cache_path(url, cache_dir, ref.lower())
    if not cached_root.is_dir():
        return None
    if repo_path is None:
        return cached_root

    candidate = cached_root / repo_path.strip("/")
    if candidate.is_dir() and candidate.resolve().is_relative_to(cached_root.resolve()):
        return candidate
    return None


def fetch_plugin(
    source: str,
    cache_dir: Path | None = None,
    ref: str | None = None,
    update: bool = True,
    repo_path: str | None = None,
    git_helper: GitHelper | None = None,
) -> Path:
    """从远程源获取插件并返回本地缓存路径。

    Args:
        source: 插件源 - 可以是：
            - 任何 git URL（GitHub、GitLab、Bitbucket、Codeberg、自托管等）e.g., "
            https://gitlab.com/org/repo",  "git@bitbucket.org:team/repo.git"
            - "GitHub:owner/repo" - GitHub 简写（方便语法）
            - “/local/path" - 本地路径（按原样返回）
        cache_dir: 用于缓存的目录。 默认为~/.openhands/cache/plugins/
        ref: 可选分支、标记或提交结账。
        update: 如果True和缓存存在，则更新它。 如果 False，则按原样使用缓存版本。
        repo_path: git 存储库中的子目录路径
            （e.g., 'plugins/my-plugin' 用于 monorepos）。 仅与 git 源相关，与本地路
            径无关。 如果指定，返回的路径将指
            向该子目录而不是存储库根目录。
        git_helper: GitHelper 实例（用于测试）。 默认为全局实例。

    Returns:
        本地插件目录的路径（为 Plugin.load() 做好准备）。 如果指定 repo_path，则返回
        该子目录的路径。

    Raises:
        PluginFetchError: 如果获取失败或者repo_path不存在。
    """
    path, _ = fetch_plugin_with_resolution(
        source=source,
        cache_dir=cache_dir,
        ref=ref,
        update=update,
        repo_path=repo_path,
        git_helper=git_helper,
    )
    return path


def fetch_plugin_with_resolution(
    source: str,
    cache_dir: Path | None = None,
    ref: str | None = None,
    update: bool = True,
    repo_path: str | None = None,
    git_helper: GitHelper | None = None,
) -> tuple[Path, str | None]:
    """获取插件并返回路径和已解析的提交 SHA。

    这与 fetch_plugin() 类似，但也返回已签出的实际提交 SHA。 这对于持久化很有用 - 存
    储已解决的 SHA 确保对话恢复获得完全相同的插件版本。

    Args:
        source: 插件源（有关格式，请参阅 fetch_plugin）。
        cache_dir: 用于缓存的目录。 默认为~/.openhands/cache/plugins/
        ref: 可选分支、标记或提交结账。
        update: 如果True和缓存存在，则更新它。 如果 False，则按原样使用缓存版本。
        repo_path: git 存储库中的子目录路径。
        git_helper: GitHelper 实例（用于测试）。 默认为全局实例。

    Returns:
        (path, resolved_ref) 的元组，其中：
        - path: 本地插件目录的路径
        - resolved_ref: 提交 SHA 已签出（None 表示本地源）

    Raises:
        PluginFetchError: 如果获取失败或者repo_path不存在。
    """
    resolved_cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    if ref is not None and _FULL_SHA_RE.fullmatch(ref):
        cached = _cached_pinned_plugin(source, resolved_cache_dir, ref, repo_path)
        if cached is not None:
            return cached, ref.lower()

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
        msg = re.sub(r"\bextension\b", "plugin", str(exc))
        msg = re.sub(r"\bExtension\b", "Plugin", msg)
        raise PluginFetchError(msg) from exc
