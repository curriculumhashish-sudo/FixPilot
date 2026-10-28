"""RemoteWorkspace 的存储库克隆和管理实用程序。

该模块提供了用于克隆 git 存储库并在使用 RemoteWorkspace 或其子类时为克隆存储库生成上
下文字符串的实用程序。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openhands.sdk.logger import get_logger
from openhands.sdk.utils.path import to_posix_path
from openhands.sdk.utils.redact import (
    redact_url_credentials,
    redact_url_credentials_in_text,
)


logger = get_logger(__name__)


# 在几秒钟内克隆超时（每个存储库 5 分钟）
CLONE_TIMEOUT = 300


class GitProvider(str, Enum):
    """支持的 git 托管提供商。"""

    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    AZURE_DEVOPS = "azure_devops"


# 将提供程序映射到沙箱设置中使用的机密名称
PROVIDER_TOKEN_NAMES: dict[GitProvider, str] = {
    GitProvider.GITHUB: "github_token",
    GitProvider.GITLAB: "gitlab_token",
    GitProvider.BITBUCKET: "bitbucket_token",
    GitProvider.AZURE_DEVOPS: "azure_devops_token",
}

# 将 URL 模式映射到提供者以进行自动检测
PROVIDER_URL_PATTERNS: dict[str, GitProvider] = {
    "github.com": GitProvider.GITHUB,
    "gitlab.com": GitProvider.GITLAB,
    "bitbucket.org": GitProvider.BITBUCKET,
    "dev.azure.com": GitProvider.AZURE_DEVOPS,
}

# 子域属于提供商的主机后缀 ({org}.visualstudio.com)
PROVIDER_URL_SUFFIXES: dict[str, GitProvider] = {
    ".visualstudio.com": GitProvider.AZURE_DEVOPS,
}


def _provider_for_host(hostname: str) -> GitProvider | None:
    """返回其自己的主机的提供者（如果有）。"""
    provider = PROVIDER_URL_PATTERNS.get(hostname)
    if provider is None:
        for suffix, suffix_provider in PROVIDER_URL_SUFFIXES.items():
            if hostname.endswith(suffix):
                return suffix_provider
    return provider


def _provider_hosts(provider: GitProvider) -> list[str]:
    """提供商的公共主机，没有任何前导点。"""
    return [
        host.lstrip(".")
        for mapping in (PROVIDER_URL_PATTERNS, PROVIDER_URL_SUFFIXES)
        for host, host_provider in mapping.items()
        if host_provider == provider
    ]


def _detect_provider_from_url(url: str) -> GitProvider | None:
    """从 URL 模式中检测 git 提供程序。

    使用了正确的 URL 解析来防止 False 正面的恶意 URLs，如 '
    https://github.com.evil.com/repo'.  用户信息被忽略，
    所以  https://org@dev.azure.com/...'  形式的 Azure DevOps 被识别。

    Args:
        url: 存储库 URL 或所有者/存储库格式

    Returns:
        如果未识别，则检测到 GitProvider 或 None
    """
    try:
        parsed = urllib.parse.urlparse(url)
        hostname = (parsed.hostname or "").lower()
        # 处理 git@ 格式：git@github.com:owner/repo
        if not hostname and url.startswith("git@"):
            hostname = url.split("@")[1].split(":")[0].lower()
        return _provider_for_host(hostname)
    except Exception:
        pass
    return None


def _is_short_url_format(url: str) -> bool:
    """检查 URL 是否是短“所有者/存储库”格式（无协议）。"""
    return "://" not in url and not url.startswith("git@")


class RepoSource(BaseModel):
    """用于克隆的存储库源规范。

    在自动化设置期间克隆存储库，并从每个克隆的存储库自动加载技能（AGENTS.md、.agents/
    skills/ 等）。

    提供者字段指定存储库属于哪个 git 托管服务，这决定了使用哪个身份验证 token 进行克
    隆。

    对于 URLs 和  https://github.com/... ，提供者将自动检测。 对于短格式（所有者/存储
    库），提供者字段是必需的。

    Examples:
        >>> # 完整 URL - 提供商自动检测
        >>> RepoSource(url="https://github.com/owner/repo")
        >>> RepoSource(url="https://gitlab.com/owner/repo", ref="main")

        >>> # 短格式 - 提供者必填
        >>> RepoSource(url="owner/repo", provider="github")
        >>> RepoSource(url="owner/repo", provider="gitlab", ref="v1.0.0")
    """

    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        ...,
        description=(
            "Repository URL. Can be a full URL (https://github.com/owner/repo) "
            "or short format (owner/repo). Short format requires 'provider' field."
        ),
    )
    ref: str | None = Field(
        default=None,
        description="Optional branch, tag, or commit SHA to checkout.",
    )
    provider: Literal["github", "gitlab", "bitbucket", "azure_devops"] | None = Field(
        default=None,
        description=(
            "Git hosting provider (github, gitlab, bitbucket, azure_devops). "
            "Required for short URL format (owner/repo). "
            "Auto-detected for full URLs."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_string_input(cls, data: Any) -> Any:
        """允许仅传递 URL 字符串而不是完整对象。"""
        if isinstance(data, str):
            return {"url": data}
        return data

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """验证 URL 格式并将 HTTP 标准化为 HTTPS。"""
        # 允许所有者/存储库格式（e.g.、“所有者/存储库”、“my-org/my-repo.git”）
        owner_repo_pattern = re.compile(r"^[\w-]+/[\w.-]+$")
        if owner_repo_pattern.match(v):
            return v
        # 为了安全起见，将 HTTP 标准化为 HTTPS（token 注入需要 HTTPS）
        if v.startswith("http://"):
            logger.warning(
                "Converting HTTP URL to HTTPS for security: "
                f"{redact_url_credentials_in_text(v)}"
            )
            v = "https://" + v[7:]
        # 允许 HTTPS、git@ 和 file:// URLs (file:// 用于测试)
        if v.startswith(("https://", "git@", "file://")):
            return v
        raise ValueError(
            "URL must be 'owner/repo' format or a valid git URL (https:// or git@)"
        )

    @model_validator(mode="after")
    def validate_provider_required_for_short_urls(self) -> RepoSource:
        """需要明确的提供程序来处理不明确的短 URL 格式。"""
        if not _is_short_url_format(self.url):
            # 完整 URL - 可以自动检测提供商
            return self

        # 短格式 - 检查提供商是否已指定或可检测
        if self.provider == GitProvider.AZURE_DEVOPS.value:
            raise ValueError(
                "Azure DevOps repositories need a full URL such as "
                "https://dev.azure.com/org/project/_git/repo"
            )
        detected = _detect_provider_from_url(self.url)
        if not detected and not self.provider:
            raise ValueError(
                f"Short URL format '{self.url}' requires explicit 'provider' field. "
                'Use: {"url": "owner/repo", "provider": "github"} '
                "or provide a full URL like https://github.com/owner/repo"
            )
        return self

    def get_provider(self) -> GitProvider:
        """获取此存储库的 git 提供程序。"""
        if self.provider:
            return GitProvider(self.provider)

        detected = _detect_provider_from_url(self.url)
        if detected:
            return detected

        # 如果验证通过，则不会发生这种情况
        raise ValueError(f"Cannot determine provider for URL: {self.url}")

    def get_token_name(self) -> str:
        """获取此存储库的身份验证 token 的机密名称。"""
        return PROVIDER_TOKEN_NAMES[self.get_provider()]


@dataclass
class RepoMapping:
    """克隆存储库的映射信息。"""

    url: str
    dir_name: str
    local_path: str
    ref: str | None = None


@dataclass
class CloneResult:
    """存储库克隆操作的结果。"""

    success_count: int
    failed_repos: list[str]
    repo_mappings: dict[str, RepoMapping] = field(default_factory=dict)


def _is_commit_sha(ref: str | None) -> bool:
    """检查 ref 是否看起来像 git commit SHA。"""
    if not ref:
        return False
    return bool(re.match(r"^[0-9a-f]{7,40}$", ref, re.IGNORECASE))


def _extract_repo_name(url: str) -> str:
    """从 URL 中提取存储库名称以用作目录名称。

    Examples:
        >>> _extract_repo_name("owner/repo")
        '回购'
        >>> _extract_repo_name("https://github.com/owner/repo.git")
        '回购'
        >>> _extract_repo_name("git@github.com:owner/repo.git")
        '回购'
    """
    # 删除结尾的 .git （带或不带结尾斜杠）
    url = re.sub(r"\.git/?$", "", url)

    # 处理 git@host:owner/repo 格式
    if url.startswith("git@"):
        url = url.split(":")[-1]

    # 句柄 https://host/owner/repo 格式
    if "://" in url:
        url = url.split("://")[-1]

    # Windows 文件：// URLs 通常包含以反斜杠分隔的本地路径。
    url = to_posix_path(url)

    # 获取最后一个路径组件（存储库名称）
    parts = url.rstrip("/").split("/")
    return parts[-1] if parts else "repo"


def _sanitize_dir_name(name: str) -> str:
    """清理用作目录名称的字符串。

    用下划线替换无效字符并确保名称安全。
    """
    # 替换文件路径中有问题的字符
    sanitized = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", name)
    # 删除前导/尾随点和空格
    sanitized = sanitized.strip(". ")
    # 确保非空
    return sanitized if sanitized else "repo"


def _get_unique_dir_name(base_name: str, existing_dirs: set[str]) -> str:
    """获取唯一的目录名称，如果需要的话附加 _N。

    Args:
        base_name: 所需的目录名称
        existing_dirs: 已使用的目录名称集

    Returns:
        唯一的目录名称（base_name 或 base_name_1、base_name_2 等）
    """
    if base_name not in existing_dirs:
        return base_name

    # 查找下一个可用后缀
    counter = 1
    while f"{base_name}_{counter}" in existing_dirs:
        counter += 1
    return f"{base_name}_{counter}"


# 提供程序配置：(base_url, token_format) token_format 使用 {token} 占位符
#
_PROVIDER_CONFIG: dict[GitProvider, tuple[str, str]] = {
    GitProvider.GITHUB: ("github.com", "{token}@"),
    GitProvider.GITLAB: ("gitlab.com", "oauth2:{token}@"),
    GitProvider.BITBUCKET: ("bitbucket.org", "x-token-auth:{token}@"),
    # Azure DevOps 忽略用户。 PATs and Entra token 两者都作为密码使用。
    GitProvider.AZURE_DEVOPS: ("dev.azure.com", "oauth2:{token}@"),
}


def _build_clone_url(
    url: str,
    provider: GitProvider,
    token: str | None,
    *,
    explicit_provider: bool = False,
) -> str:
    """基于存储库 URL 和提供者构建经过身份验证的克隆 URL。

    token 被注入到提供者的公共主机中，或者当调用者显式设置 `provider` 时注入到 URL 自
    己的主机中（自托管实例）。
    """
    config = _PROVIDER_CONFIG.get(provider)
    if not config:
        return url

    base_url, token_format = config
    auth_prefix = token_format.format(token=token) if token else ""

    # 处理所有者/存储库格式 - 构造完整的 URL
    is_short_format = "://" not in url and "/" in url and not url.startswith("git@")
    if is_short_format:
        return f"https://{auth_prefix}{base_url}/{url}.git"

    if not token:
        return url

    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or parsed.password or not hostname:
        return url
    if _provider_for_host(hostname) != provider:
        # 自动检测的提供程序源自 URL，因此它无法授权另一个主机 - 并且永远不会与其公共主
        # 机相似。
        #
        lookalike = any(
            f".{host}." in f".{hostname}" for host in _provider_hosts(provider)
        )
        if not explicit_provider or lookalike:
            return url
    if parsed.username:
        # Azure DevOps 命名组织为用户 URLs。 保留它，并提供 token 作为其密码。
        #
        auth_prefix = f"{parsed.username}:{token}@"

    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    return urllib.parse.urlunparse(parsed._replace(netloc=f"{auth_prefix}{netloc}"))


# 按名称获取 token 的函数类型（e.g.、“github_token”-> token 值）
TokenFetcher = Callable[[str], str | None]


def _build_clone_command(clone_url: str, dest: Path, ref: str | None) -> list[str]:
    """构建 git clone 命令。"""
    # SHA refs 需要完整克隆； 分支/标签可以使用浅克隆
    if _is_commit_sha(ref):
        return ["git", "clone", clone_url, str(dest)]

    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd.extend(["--branch", ref])
    cmd.extend([clone_url, str(dest)])
    return cmd


def _checkout_sha(dest: Path, sha: str) -> bool:
    """完整克隆后签出特定的 SHA。 成功则返回 True。

    失败时，清理克隆目录以防止孤立目录阻止重试尝试。

    Note: 我们不使用 `--` 分隔符，因为 sha 参数已验证
    _is_commit_sha() 为 7+ 十六进制字符，使得标志注入不可能。
    """
    result = subprocess.run(
        ["git", "-C", str(dest), "checkout", sha],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        logger.warning(f"[clone] Failed to checkout {sha}: {result.stderr}")
        # 清理以防止孤立目录阻止重试次尝试
        shutil.rmtree(dest, ignore_errors=True)
        return False
    return True


def _clone_single_repo(repo: RepoSource, dest: Path, token: str | None) -> bool:
    """克隆单个存储库。 成功则返回 True。"""
    try:
        provider = repo.get_provider()
        clone_url = _build_clone_url(
            repo.url, provider, token, explicit_provider=repo.provider is not None
        )
        provider_str = provider.value
    except ValueError:
        # 未检测到提供者 (e.g., 文件：// URLs) - 请使用 URL
        clone_url = repo.url
        provider_str = "local"

    display_url = redact_url_credentials(repo.url)
    logger.info(f"[clone] Cloning {display_url} ({provider_str}) -> {dest.name}/")

    cmd = _build_clone_command(clone_url, dest, repo.ref)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=CLONE_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"[clone] Timed out: {display_url}")
        return False

    if result.returncode != 0:
        logger.warning(
            f"[clone] Failed: {redact_url_credentials_in_text(result.stderr)}"
        )
        return False

    # 对于 SHA 引用，我们进行了完整克隆并需要检查特定提交
    if _is_commit_sha(repo.ref) and repo.ref:
        if not _checkout_sha(dest, repo.ref):
            return False

    logger.info(f"[clone] Success: {display_url} -> {dest.name}/")
    return True


class _TokenCache:
    """提供者 token 的简单缓存以避免重复的 API 调用。"""

    def __init__(self, fetcher: TokenFetcher | None):
        self._fetcher = fetcher
        self._cache: dict[str, str | None] = {}

    def get(self, token_name: str) -> str | None:
        if token_name not in self._cache:
            try:
                self._cache[token_name] = (
                    self._fetcher(token_name) if self._fetcher else None
                )
            except Exception as e:
                logger.warning(f"Failed to fetch token '{token_name}': {e}")
                self._cache[token_name] = None
        return self._cache[token_name]


def clone_repos(
    repos: list[RepoSource],
    target_dir: Path,
    token_fetcher: TokenFetcher | None = None,
) -> CloneResult:
    """将存储库克隆到目标目录。

    Args:
        repos: RepoSource 个配置列表（每个配置指定提供者）
        target_dir: 将存储库克隆到的目录
        token_fetcher: 可调用的名称为 token (e.g., 'github_token')
            并返回 token 值，如果不可用则返回 None

    Returns:
        CloneResult 包含成功计数、失败存储库和存储库映射
    """
    if not repos:
        logger.info("[clone] No repositories to clone")
        return CloneResult(success_count=0, failed_repos=[], repo_mappings={})

    # 按 URL 对存储库进行重复数据删除以防止出现孤立目录
    seen_urls: set[str] = set()
    unique_repos: list[RepoSource] = []
    for repo in repos:
        if repo.url and repo.url not in seen_urls:
            seen_urls.add(repo.url)
            unique_repos.append(repo)
        elif repo.url:
            logger.warning(
                f"[clone] Skipping duplicate URL: {redact_url_credentials(repo.url)}"
            )

    if not unique_repos:
        logger.info("[clone] No repositories to clone after deduplication")
        return CloneResult(success_count=0, failed_repos=[], repo_mappings={})

    logger.info(f"[clone] Cloning {len(unique_repos)} repository(ies)...")
    target_dir.mkdir(parents=True, exist_ok=True)

    tokens = _TokenCache(token_fetcher)
    used_dirs: set[str] = set()
    failed: list[str] = []
    mappings: dict[str, RepoMapping] = {}

    for repo in unique_repos:
        try:
            if not repo.url:
                logger.warning("[clone] Skipping repo with empty URL")
                continue

            # 确定唯一的目录名称
            base_name = _sanitize_dir_name(_extract_repo_name(repo.url))
            dir_name = _get_unique_dir_name(base_name, used_dirs)
            used_dirs.add(dir_name)
            dest = target_dir / dir_name

            # 使用特定于提供者的 token 进行克隆（如果提供者未知则为 None）
            try:
                token = tokens.get(repo.get_token_name())
            except ValueError:
                # 无提供者（e.g，文件：// URLs）- 不使用token
                token = None
            success = _clone_single_repo(repo, dest, token)

            if success:
                mappings[repo.url] = RepoMapping(
                    url=repo.url,
                    dir_name=dir_name,
                    local_path=str(dest),
                    ref=repo.ref,
                )
            else:
                failed.append(redact_url_credentials(repo.url))
        except Exception as e:
            # 不要让一个糟糕的仓库停止整个批次
            display_url = redact_url_credentials(repo.url) if repo.url else "<unknown>"
            logger.warning(f"[clone] Error processing {display_url}: {e}")
            failed.append(display_url)

    logger.info(f"[clone] Cloned {len(mappings)}/{len(unique_repos)} repositories")
    if failed:
        logger.warning(f"[clone] Failed: {', '.join(failed)}")

    return CloneResult(
        success_count=len(mappings),
        failed_repos=failed,
        repo_mappings=mappings,
    )


def get_repos_context(repo_mappings: dict[str, RepoMapping]) -> str:
    """生成描述智能体克隆存储库的上下文字符串。

    Args:
        repo_mappings: URLs 对应 RepoMapping 对象的字典

    Returns:
        带有存储库映射的 Markdown 格式的字符串，如果没有存储库则为空字符串。
    """
    if not repo_mappings:
        return ""

    lines = [
        "## Cloned Repositories",
        "",
        "The following repositories have been cloned to your workspace:",
        "",
    ]

    for url, mapping in repo_mappings.items():
        ref_str = f" (ref: {mapping.ref})" if mapping.ref else ""
        lines.append(f"- `{url}`{ref_str} → `{mapping.local_path}/`")

    lines.append("")
    return "\n".join(lines)
