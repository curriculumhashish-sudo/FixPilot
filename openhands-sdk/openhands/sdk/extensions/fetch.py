"""获取扩展实用程序。"""

import hashlib
from enum import StrEnum
from pathlib import Path

from openhands.sdk.git.cached_repo import GitHelper, try_cached_clone_or_update
from openhands.sdk.git.utils import extract_repo_name, is_git_url, normalize_git_url
from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import is_local_path_source
from openhands.sdk.utils.redact import redact_url_credentials


logger = get_logger(__name__)


class ExtensionFetchError(Exception):
    """获取扩展失败时引发。"""


class SourceType(StrEnum):
    """扩展源的分类。

    LOCAL -- 文件系统路径（绝对路径、主路径相对路径或点相对路径）。 GIT -- 任何 git-
    clonable URL（HTTPS、SSH、git:// 等
    ）。 GITHUB——``github:owner/repo[/path]``简写，扩展为HTTPSURL。
    """

    LOCAL = "local"
    GIT = "git"
    GITHUB = "github"


def _split_github_shorthand(source: str) -> tuple[str, str | None]:
    """将 ``github:owner/repo[/subpath]`` 拆分为 ``("owner/repo", subpath)``。

    Raises:
        ExtensionFetchError: 如果所有者或仓库丢失。
    """
    owner, _, rest = source.strip()[len("github:") :].partition("/")
    repo, _, subpath = rest.partition("/")
    if not owner or not repo:
        raise ExtensionFetchError(
            f"Invalid GitHub shorthand format: {source}. "
            f"Expected format: github:owner/repo[/path]"
        )
    return f"{owner}/{repo}", subpath.strip("/") or None


def parse_extension_source(source: str) -> tuple[SourceType, str]:
    """将扩展源解析为 (SourceType, url)。

    Args:
        source: 扩展源字符串。 可以是：
            - "GitHub:owner/repo" - GitHub 存储库简写
            - "GitHub:owner/repo/path" - 相同，命名子目录（fetch() 使用路径作为
            ``repo_path``）
            - “ https://github.com/owner/repo.git"  - 完整的 git URL
            - “git@github.com：所有者/repo.git” - SSH git URL
            - “/local/path" - 本地路径

    Returns:
        (source_type, normalized_url) 的元组，其中 source_type 是以下之一：
        - SourceType.GITHUB：GitHub存储库
        - SourceType.GIT：任何 git URL
        - SourceType.LOCAL：本地文件系统路径

    Examples:
        >>> parse_extension_source("github:owner/repo")
        (SourceType.GITHUB, " https://github.com/owner/repo.git" )
        >>> parse_extension_source("https://gitlab.com/org/repo.git")
        (SourceType.GIT, " https://gitlab.com/org/repo.git" )
        >>> parse_extension_source("/local/path")
        (SourceType.LOCAL, "/local/path")
    """
    source = source.strip()

    # GitHub 简写：GitHub:owner/repo[/subpath]
    if source.startswith("github:"):
        repo, _ = _split_github_shorthand(source)
        url = f"https://github.com/{repo}.git"
        return (SourceType.GITHUB, url)

    # Git URLs: 通过协议/方案检测，而不是枚举提供者。它处理 GitHub、GitLab、Bitbucket、
    # Codeberg、自托管实例等。
    #
    if is_git_url(source):
        url = normalize_git_url(source)
        return (SourceType.GIT, url)

    # 本地路径：以 /、~、. 开头，是 Windows 绝对路径，或包含不带 URL 方案的路径分隔符。
    #
    if is_local_path_source(source):
        return (SourceType.LOCAL, source)

    if "/" in source and "://" not in source:
        # 相对路径如“plugins/my-plugin”
        return (SourceType.LOCAL, source)

    raise ExtensionFetchError(
        f"Unable to parse extension source: {source}. "
        f"Expected formats: 'github:owner/repo', git URL, or local path"
    )


def resolve_extension_source(
    source: str, repo_path: str | None = None
) -> tuple[SourceType, str, str | None]:
    """解析源并解析显式或嵌入式存储库子路径。"""
    source_type, url = parse_extension_source(source)
    if source_type == SourceType.GITHUB:
        _, subpath = _split_github_shorthand(source)
        if subpath is not None:
            if repo_path:
                raise ExtensionFetchError(
                    f"GitHub shorthand {source} already names a subdirectory; "
                    "do not also pass repo_path"
                )
            repo_path = subpath
    return source_type, url, repo_path


def _resolve_local_source(url: str) -> Path:
    """将本地扩展源解析为路径。

    Args:
        url: 本地路径字符串（可能包含 ~ 表示主目录）。

    Returns:
        解析了扩展目录的绝对路径。

    Raises:
        ExtensionFetchError: 如果路径不存在。
    """
    local_path = Path(url).expanduser().resolve()
    if not local_path.exists():
        raise ExtensionFetchError(f"Local extension path does not exist: {local_path}")
    return local_path


def _apply_subpath(base_path: Path, subpath: str | None, context: str) -> Path:
    """将子路径应用于基本路径，验证其存在并保留在内部。

    Args:
        base_path: 根路径。
        subpath: 可选的子目录路径（可能有前导/尾随斜杠）。
        context: 错误消息的描述（e.g.，“扩展存储库”）。

    Returns:
        最终路径（如果没有子路径则为 base_path，否则为 base_path/subpath）。

    Raises:
        ExtensionFetchError: 如果子路径转义 base_path 或不存在。
    """
    if not subpath:
        return base_path

    final_path = base_path / subpath.strip("/")
    # 遏制：子路径不得通过“..”或符号链接爬出基础路径。
    resolved_base = base_path.resolve()
    if not final_path.resolve().is_relative_to(resolved_base):
        raise ExtensionFetchError(f"Subdirectory '{subpath}' escapes {context}")
    if not final_path.exists():
        raise ExtensionFetchError(f"Subdirectory '{subpath}' not found in {context}")
    return final_path


def fetch(
    source: str,
    cache_dir: Path,
    ref: str | None = None,
    update: bool = True,
    repo_path: str | None = None,
    git_helper: GitHelper | None = None,
) -> Path:
    """从源获取扩展并返回本地路径。

    Args:
        source: 扩展源——git URL、GitHub简写或本地路径。
        cache_dir: 用于缓存的目录。
        ref: 可选分支、标记或提交结账。
        update: 如果True和缓存存在，则更新它。
        repo_path: 存储库内的子目录路径。
        git_helper: GitHelper 实例（用于测试）。

    Returns:
        本地扩展目录的路径。
    """
    path, _ = fetch_with_resolution(
        source=source,
        cache_dir=cache_dir,
        ref=ref,
        update=update,
        repo_path=repo_path,
        git_helper=git_helper,
    )
    return path


def fetch_with_resolution(
    source: str,
    cache_dir: Path,
    ref: str | None = None,
    update: bool = True,
    repo_path: str | None = None,
    git_helper: GitHelper | None = None,
) -> tuple[Path, str | None]:
    """获取扩展并返回路径和已解析的提交 SHA。

    Args:
        source: 扩展源（git URL、GitHub 简写或本地路径）。
        cache_dir: 用于缓存的目录。
        ref: 可选分支、标记或提交结账。
        update: 如果True和缓存存在，则更新它。
        repo_path: 存储库内的子目录路径。
        git_helper: GitHelper 实例（用于测试）。

    Returns:
        (path, resolved_ref) 的元组，其中 resolved_ref 是 git 源的提交 SHA，None 是本
        地路径。

    Raises:
        ExtensionFetchError: 如果获取扩展失败。
    """
    source_type, url, repo_path = resolve_extension_source(source, repo_path)

    if source_type == SourceType.LOCAL:
        base_path = _resolve_local_source(url)
        return _apply_subpath(base_path, repo_path, f"local source '{source}'"), None

    git = git_helper if git_helper is not None else GitHelper()

    ext_path, resolved_ref = _fetch_remote_source_with_resolution(
        url, cache_dir, ref, update, repo_path, git, source
    )
    return ext_path, resolved_ref


def get_cache_path(source: str, cache_dir: Path) -> Path:
    """获取扩展源的缓存路径。

    基于源 URL 的哈希创建确定性路径。

    Args:
        source: 扩展源（URL 或路径）。
        cache_dir: 基本缓存目录。

    Returns:
        应缓存扩展的路径。
    """
    # 创建目录名称的源哈希
    source_hash = hashlib.sha256(source.encode()).hexdigest()[:16]

    # 提取存储库名称以获取人类可读的缓存目录名称
    readable_name = extract_repo_name(source)

    cache_name = f"{readable_name}-{source_hash}"
    return cache_dir / cache_name


def _fetch_remote_source_with_resolution(
    url: str,
    cache_dir: Path,
    ref: str | None,
    update: bool,
    subpath: str | None,
    git_helper: GitHelper,
    source: str,
) -> tuple[Path, str]:
    """获取远程扩展源并返回路径+已解析的提交SHA。

    Args:
        url: 使用 Git URL 获取。
        cache_dir: 缓存的基本目录。
        ref: 可选分支、标记或提交结账。
        update: 是否更新现有缓存。
        subpath: 存储库中的可选子目录。
        git_helper: GitHelper git 操作实例。
        source: 原始源字符串（用于错误消息）。

    Returns:
        包含（路径，resolved_ref）的元组，其中resolved_ref是SHA的提交。

    Raises:
        ExtensionFetchError: 如果获取失败或子路径无效。
    """
    repo_cache_path = get_cache_path(url, cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    result = try_cached_clone_or_update(
        url=url,
        repo_path=repo_cache_path,
        ref=ref,
        update=update,
        git_helper=git_helper,
    )

    if result is None:
        raise ExtensionFetchError(
            f"Failed to fetch extension from {redact_url_credentials(source)}"
        )

    # 获取已签出的实际提交 SHA
    try:
        resolved_ref = git_helper.get_head_commit(repo_cache_path)
    except Exception as e:
        logger.warning(
            f"Could not get commit SHA for {redact_url_credentials(source)}: {e}"
        )
        # 如果我们无法获得 SHA，则返回到请求的引用
        resolved_ref = ref or "HEAD"

    final_path = _apply_subpath(repo_cache_path, subpath, "extension repository")
    return final_path, resolved_ref
