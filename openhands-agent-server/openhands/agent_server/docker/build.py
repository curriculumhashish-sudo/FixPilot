#!/usr/bin/env python3
"""
智能体-服务器镜像的单入口构建助手。

- Targets: 二进制 | 二进制最小化 | 源码 | 源码最小化
- 通过 CUSTOM_TAGS 进行多重标记（逗号分隔）
- 用于自定义标签的 Git 标签和 semver 派生标签
- 分支范围的缓存键
- CI（推送）与本地（加载）行为
- 基于 sdist 的构建：使用 `uv build` 创建干净的构建上下文
- 一项：build(opts: BuildOptions)
- 自动检测 sdk_project_root（无手动参数）
- 没有留下任何本地工件（仅使用临时文件目录）
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import tomllib
from contextlib import chdir
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from openhands.sdk.logger import IN_CI, get_logger, rolling_log_view
from openhands.sdk.settings.acp_install_catalog import (
    DEFAULT_PREINSTALLED_ACP_PROVIDERS,
)
from openhands.sdk.settings.acp_providers import ACP_PROVIDERS
from openhands.sdk.workspace import PlatformType, TargetType


logger = get_logger(__name__)

VALID_TARGETS = {
    "binary",
    "binary-minimal",
    "source",
    "source-minimal",
    "base-image-minimal",
    "base-image",
    "builder",
}
# 相对于的相对路径 sdk_project_root无依赖的 ACP 安装 Dockerfile 的仓库 `acp-providers`
# stage COPYs 直接的。 这里重叠显示，以便为空上下文快速路径（`is_base_only`) 只能
# staging 这一个文件，而不是拉取整个 SDK 源代码树。
#
_ACP_INSTALL_CATALOG_RELPATH = Path(
    "openhands-sdk/openhands/sdk/settings/acp_install_catalog.py"
)
# Dockerfile的INSTALL_CAPABILITIES构建参数接受的`base-image`阶段的VSCodeWeb、浏览器和
# Docker块。 自本模块以来，由于 ACP_PROVIDERS 之外的其他仓库/运行时代码不需要这个集合。
#
AGENT_SERVER_CAPABILITIES = ("vscode", "browser", "docker")
_BUILDKIT_STEP_RE = re.compile(r"^#(?P<step>\d+)\s+(?P<message>.+)$")
_BUILDKIT_DONE_RE = re.compile(r"^DONE\s+(?P<seconds>\d+(?:\.\d+)?)s$")
_BUILDKIT_INLINE_DONE_RE = re.compile(
    r"^(?P<description>.+?)\s+(?P<seconds>\d+(?:\.\d+)?)s done$"
)
_SEMVER_RELEASE_RE = re.compile(
    r"^(?P<prefix>v)?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$"
)


# --- 帮手 ---


def _default_sdk_project_root() -> Path:
    """
    解析顶级 OpenHands uv 工作区根：

    订单：
      1) 从CWD向上走
      2) 从该文件位置向上走

    拒绝 site/dist-packages 中的任何内容（已安装的轮子）。
    """
    site_markers = ("site-packages", "dist-packages")

    def _is_workspace_root(d: Path) -> bool:
        """检测 d 是否是智能体-SDK 存储库 uv 工作区的根。"""
        _EXPECTED = (
            "openhands-sdk/pyproject.toml",
            "openhands-tools/pyproject.toml",
            "openhands-workspace/pyproject.toml",
            "openhands-agent-server/pyproject.toml",
        )

        py = d / "pyproject.toml"
        if not py.exists():
            return False
        try:
            cfg = tomllib.loads(py.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
        members = (
            cfg.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
            or []
        )
        # 接受所有子项目的显式 uv 成员或结构存在
        if members:
            norm = {str(Path(m)) for m in members}
            return {
                "openhands-sdk",
                "openhands-tools",
                "openhands-workspace",
                "openhands-agent-server",
            }.issubset(norm)
        return all((d / p).exists() for p in _EXPECTED)

    def _climb(start: Path) -> Path | None:
        cur = start.resolve()
        if not cur.is_dir():
            cur = cur.parent
        while True:
            if _is_workspace_root(cur):
                return cur
            if cur.parent == cur:
                return None
            cur = cur.parent

    def validate(p: Path, src: str) -> Path:
        if any(s in str(p) for s in site_markers):
            raise RuntimeError(
                f"{src}: points inside site-packages; need the source checkout."
            )
        root = _climb(p) or p
        if not _is_workspace_root(root):
            raise RuntimeError(
                f"{src}: couldn't find the OpenHands UV workspace root "
                f"starting at '{p}'.\n\n"
                "Expected setup (repo root):\n"
                "  pyproject.toml  # has [tool.uv.workspace] with members\n"
                "  openhands-sdk/pyproject.toml\n"
                "  openhands-tools/pyproject.toml\n"
                "  openhands-workspace/pyproject.toml\n"
                "  openhands-agent-server/pyproject.toml\n\n"
                "Fix:\n"
                "  - Run from anywhere inside the repo."
            )
        return root

    if root := _climb(Path.cwd()):
        return validate(root, "CWD discovery")

    try:
        here = Path(__file__).resolve()
        if root := _climb(here):
            return validate(root, "__file__ discovery")
    except NameError:
        pass

    # 最终的、面向用户的指南
    raise RuntimeError(
        "Could not resolve the OpenHands UV workspace root.\n\n"
        "Expected repo layout:\n"
        "  pyproject.toml  (with [tool.uv.workspace].members "
        "including openhands/* subprojects)\n"
        "  openhands-sdk/pyproject.toml\n"
        "  openhands-tools/pyproject.toml\n"
        "  openhands-workspace/pyproject.toml\n"
        "  openhands-agent-server/pyproject.toml\n\n"
        "Run this from inside the repo."
    )


def _run(
    cmd: list[str],
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """
    将 stdout 和 stderr 同时流式传输到滚动记录器中，
    while capturing FULL stdout/stderr.
    返回 CompletedProcess（stdout=<full>，stderr=<full>）。 失败时会引发
    CalledProcessError 输出和 st
    derr。
    """
    logger.info(f"$ {' '.join(cmd)} (cwd={cwd})")

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,  # 保持分开
        bufsize=1,  # 行缓冲
    )
    assert proc.stdout is not None and proc.stderr is not None

    out_lines: list[str] = []
    err_lines: list[str] = []

    def pump(stream, sink: list[str], log_fn, prefix: str) -> None:
        for line in stream:
            line = line.rstrip("\n")
            sink.append(line)
            log_fn(f"{prefix}{line}")

    with rolling_log_view(
        logger,
        header="$ " + " ".join(cmd) + (f" (cwd={cwd})" if cwd else ""),
    ):
        t_out = threading.Thread(
            target=pump, args=(proc.stdout, out_lines, logger.info, "[stdout] ")
        )
        t_err = threading.Thread(
            target=pump, args=(proc.stderr, err_lines, logger.warning, "[stderr] ")
        )
        t_out.start()
        t_err.start()
        t_out.join()
        t_err.join()

    rc = proc.wait()
    stdout = ("\n".join(out_lines) + "\n") if out_lines else ""
    stderr = ("\n".join(err_lines) + "\n") if err_lines else ""

    result = subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr=stderr)

    if rc != 0:
        # 包括失败时的完整输出
        raise subprocess.CalledProcessError(rc, cmd, output=stdout, stderr=stderr)

    return result


def _sanitize_branch(ref: str) -> str:
    ref = re.sub(r"^refs/heads/", "", ref or "unknown")
    return re.sub(r"[^a-zA-Z0-9.-]+", "-", ref).lower()


def _sanitize_ref_tag(ref_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "-", ref_name.strip())
    sanitized = sanitized.strip(".-")
    return sanitized or "unknown"


def _release_tag_aliases(version: str) -> list[str]:
    version = version.strip()
    if not version:
        return []

    match = _SEMVER_RELEASE_RE.fullmatch(version)
    if not match:
        return [_sanitize_ref_tag(version)]

    prefix = match.group("prefix") or ""
    major = match.group("major")
    minor = match.group("minor")
    patch = match.group("patch")
    return [
        f"{prefix}{major}",
        f"{prefix}{major}.{minor}",
        f"{prefix}{major}.{minor}.{patch}",
    ]


def _truncate_ident(repo: str, tag: str, budget: int) -> str:
    """
    截断 repo+tag 以适应预算，优先考虑标签保留。

    策略：
    1. 如果两者都适合：返回两者
    2. 如果标签适合但仓库不适合：截断仓库，保留完整标签
    3. 如果标签不适合：截断标签，丢弃存储库
    4. 如果没有标签：截断仓库
    """
    tag_suffix = f"_tag_{tag}" if tag else ""
    full_ident = repo + tag_suffix

    if len(full_ident) <= budget:
        return full_ident

    if not tag:
        return repo[:budget]

    if len(tag_suffix) <= budget:
        repo_budget = budget - len(tag_suffix)
        return repo[:repo_budget] + tag_suffix

    return tag_suffix[:budget]


def _base_slug(image: str, max_len: int = 64) -> str:
    """
    如果段头太长，请保留最容易识别的部分：
    - 存储库名称（最后一个路径段）
    - 标签（如果有）
    然后附加一个简短的摘要以确保唯一性。 使用现有分隔符保留格式：“_s_”表示“/'”，“
    _tag_”表示“:”。

    Example:
      'ghcr.io_s_org_s/very-long-repo_tag_v1.2.3-extra' -> 'very-long-repo_tag_v1.2.3-<digest>'
    """  # noqa: E501
    base_slug = image.replace("/", "_s_").replace(":", "_tag_")

    if len(base_slug) <= max_len:
        return base_slug

    digest = hashlib.sha256(base_slug.encode()).hexdigest()[:12]
    suffix = f"-{digest}"

    # 从 slug 形式解析组件
    if "_tag_" in base_slug:
        left, tag = base_slug.rsplit("_tag_", 1)  # 在最后分割：（最右边的标签）
    else:
        left, tag = base_slug, ""

    parts = left.split("_s_") if left else []
    repo = parts[-1] if parts else left  # 最后一个路径段是存储库

    # 适合预算，为摘要后缀保留空间
    visible_budget = max_len - len(suffix)
    assert visible_budget > 0, (
        f"max_len too small to fit digest suffix with length {len(suffix)}"
    )

    ident = _truncate_ident(repo, tag, visible_budget)
    return ident + suffix


def _git_info() -> tuple[str, str]:
    """
    获取当前工作目录的 git info (ref, sha)。

    SHA 的优先顺序：
    1. SDK_SHA - 显式覆盖（e.g.，用于子模块构建）
    2. GITHUB_SHA - GitHub 动作环境
    3. git rev-parse HEAD - 本地开发

    REF 的优先顺序：
    1. SDK_REF - 显式覆盖（e.g.，用于子模块构建）
    2. GITHUB_REF - GitHub 动作环境
    3. git symbolic-ref HEAD - 本地开发
    """
    sdk_root = _default_sdk_project_root()
    git_sha = os.environ.get("SDK_SHA") or os.environ.get("GITHUB_SHA")
    if not git_sha:
        try:
            git_sha = _run(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=str(sdk_root),
            ).stdout.strip()
        except subprocess.CalledProcessError:
            git_sha = "unknown"

    git_ref = os.environ.get("SDK_REF") or os.environ.get("GITHUB_REF")
    if not git_ref:
        try:
            git_ref = _run(
                ["git", "symbolic-ref", "-q", "--short", "HEAD"],
                cwd=str(sdk_root),
            ).stdout.strip()
        except subprocess.CalledProcessError:
            git_ref = "unknown"
    return git_ref, git_sha


def _package_version() -> str:
    """
    从 OpenHands-SDK 包中获取语义版本。 当 git-tag 派生的发布标签不可用时，这用作回退
    方案。
    """
    try:
        from importlib.metadata import version

        return version("openhands-sdk")
    except Exception:
        # 如果未安装软件包，请尝试从 pyproject.toml 读取
        try:
            sdk_root = _default_sdk_project_root()
            pyproject_path = sdk_root / "openhands-sdk" / "pyproject.toml"
            if pyproject_path.exists():
                cfg = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
                return cfg.get("project", {}).get("version", "unknown")
        except Exception:
            pass
        return "unknown"


_DEFAULT_GIT_REF, _DEFAULT_GIT_SHA = _git_info()
_DEFAULT_PACKAGE_VERSION = _package_version()


class BuildOptions(BaseModel):
    base_image: str = Field(default="python-node-runtime")
    custom_tags: str = Field(
        default="", description="Comma-separated list of custom tags."
    )
    image: str = Field(default="ghcr.io/openhands/agent-server")
    image_flavor: Literal["default", "slim", "minimal"] = Field(default="default")
    target: TargetType = Field(default="binary")
    platforms: list[PlatformType] = Field(default=["linux/amd64"])
    push: bool | None = Field(
        default=None, description="None=auto (CI push, local load)"
    )
    arch: str | None = Field(
        default=None,
        description="Architecture suffix (e.g., 'amd64', 'arm64') to append to tags",
    )
    include_base_tag: bool = Field(
        default=True,
        description=(
            "Whether to include the automatically generated base tag "
            "based on git SHA and base image name in all_tags output."
        ),
    )
    include_versioned_tag: bool = Field(
        default=False,
        description=(
            "Whether to include git tag-derived release tags (including semver "
            "aliases like v1 and v1.2) in all_tags output. Should only be True "
            "for release builds."
        ),
    )
    git_sha: str = Field(
        default=_DEFAULT_GIT_SHA,
        description="Git commit SHA.We will need it to tag the built image.",
    )
    git_ref: str = Field(default=_DEFAULT_GIT_REF)
    sdk_project_root: Path = Field(
        default_factory=_default_sdk_project_root,
        description="Path to OpenHands SDK root. Auto if None.",
    )
    prebuilt_sdist: Path | None = Field(
        default=None,
        description=(
            "Path to a pre-built SDK sdist tarball to reuse when creating the "
            "clean Docker build context. If unset, the SDK will run "
            "`uv build --sdist` itself."
        ),
    )
    sdk_version: str = Field(
        default=_DEFAULT_PACKAGE_VERSION,
        description=(
            "SDK package version. "
            "We will need it to tag the built image. "
            "Note this is only used if include_versioned_tag is True "
            "(e.g., at each release)."
        ),
    )
    install_acp_providers: str = Field(
        default=",".join(DEFAULT_PREINSTALLED_ACP_PROVIDERS),
        description=(
            "Comma-separated ACP provider keys (see ACP_PROVIDERS in "
            "openhands-sdk/openhands/sdk/settings/acp_providers.py) to bake "
            "into the image. Empty string installs none."
        ),
    )

    @field_validator("install_acp_providers")
    @classmethod
    def _valid_install_acp_providers(cls, v: str) -> str:
        unknown = [
            p for p in (t.strip() for t in v.split(",")) if p and p not in ACP_PROVIDERS
        ]
        if unknown:
            raise ValueError(
                f"Unknown ACP provider(s) in install_acp_providers: "
                f"{', '.join(unknown)}. Valid keys: {', '.join(ACP_PROVIDERS)}"
            )
        return v

    install_capabilities: str = Field(
        default="vscode,browser,docker",
        description=(
            "Comma-separated capability keys to bake into the `base-image` "
            "stage (VSCode Web, browser, Docker Engine). Empty "
            "string installs none."
        ),
    )

    @field_validator("install_capabilities")
    @classmethod
    def _valid_install_capabilities(cls, v: str) -> str:
        unknown = [
            p
            for p in (t.strip() for t in v.split(","))
            if p and p not in AGENT_SERVER_CAPABILITIES
        ]
        if unknown:
            raise ValueError(
                f"Unknown capability(ies) in install_capabilities: "
                f"{', '.join(unknown)}. "
                f"Valid keys: {', '.join(AGENT_SERVER_CAPABILITIES)}"
            )
        return v

    @property
    def short_sha(self) -> str:
        return self.git_sha[:7] if self.git_sha != "unknown" else "unknown"

    @property
    def long_sha(self) -> str:
        return self.git_sha if self.git_sha != "unknown" else "unknown"

    @field_validator("target")
    @classmethod
    def _valid_target(cls, v: str) -> str:
        if v not in VALID_TARGETS:
            raise ValueError(f"target must be one of {sorted(VALID_TARGETS)}")
        return v

    @property
    def custom_tag_list(self) -> list[str]:
        return [t.strip() for t in self.custom_tags.split(",") if t.strip()]

    @property
    def base_image_slug(self) -> str:
        return _base_slug(self.base_image)

    @property
    def branch_tag(self) -> str | None:
        if not self.git_ref or self.git_ref == "unknown":
            return None
        if self.git_ref.startswith("refs/tags/"):
            return None
        branch_ref = self.git_ref
        if branch_ref.startswith("refs/heads/"):
            branch_ref = branch_ref.removeprefix("refs/heads/")
        elif branch_ref.startswith("refs/"):
            return None
        return _sanitize_branch(branch_ref)

    @property
    def release_tag_source(self) -> str | None:
        if self.git_ref.startswith("refs/tags/"):
            tag = self.git_ref.removeprefix("refs/tags/")
            # 对于 semver 版本标签 (v1.2.3)，请使用 PEP 440 后面的 SDK 包版本（裸 semver
            # ，无“v”前缀）。
            #
            if _SEMVER_RELEASE_RE.fullmatch(tag):
                if self.sdk_version != "unknown":
                    return self.sdk_version
                # 防御：如果 sdk_version 不可用，则剥离“v”。
                return tag.removeprefix("v")
            # 非 semver 标签 (e.g. build-Docker) 按原样使用。
            return tag
        if self.sdk_version and self.sdk_version != "unknown":
            return self.sdk_version
        return None

    @property
    def versioned_tags(self) -> list[str]:
        """为每个自定义标签变体生成 git 标签派生标签。"""
        if not self.release_tag_source:
            return []
        return [
            f"{release_tag}-{custom_tag}{self.flavor_suffix}"
            for custom_tag in self.custom_tag_list
            for release_tag in _release_tag_aliases(self.release_tag_source)
        ]

    @property
    def flavor_suffix(self) -> str:
        return "" if self.image_flavor == "default" else f"-{self.image_flavor}"

    @property
    def base_tag(self) -> str:
        return f"{self.short_sha}-{self.base_image_slug}{self.flavor_suffix}"

    @property
    def cache_tags(self) -> tuple[str, str]:
        base = f"buildcache-{self.target}-{self.base_image_slug}{self.flavor_suffix}"
        if self.git_ref in ("main", "refs/heads/main"):
            return f"{base}-main", base
        elif self.git_ref != "unknown":
            return f"{base}-{_sanitize_branch(self.git_ref)}", base
        else:
            return base, base

    @property
    def all_tags(self) -> list[str]:
        tags: list[str] = []
        arch_suffix = f"-{self.arch}" if self.arch else ""

        for custom_tag in self.custom_tag_list:
            custom_tag = f"{custom_tag}{self.flavor_suffix}"
            tags.extend(
                [
                    f"{self.image}:{self.short_sha}-{custom_tag}{arch_suffix}",
                    f"{self.image}:{self.long_sha}-{custom_tag}{arch_suffix}",
                ]
            )
            if self.branch_tag:
                tags.append(f"{self.image}:{self.branch_tag}-{custom_tag}{arch_suffix}")

        if self.include_base_tag:
            tags.append(f"{self.image}:{self.base_tag}{arch_suffix}")
        if self.include_versioned_tag:
            for versioned_tag in self.versioned_tags:
                tags.append(f"{self.image}:{versioned_tag}{arch_suffix}")

        # 最小图像风格已经命名了它的二进制最小目标。
        if self.target != "binary" and not (
            self.target == "binary-minimal" and self.image_flavor == "minimal"
        ):
            tags = [f"{t}-{self.target}" for t in tags]
        return list(dict.fromkeys(tags))


class BuildTelemetry(BaseModel):
    build_context_seconds: float = 0.0
    buildx_wall_clock_seconds: float = 0.0
    cleanup_seconds: float = 0.0
    cache_import_seconds: float = 0.0
    cache_import_miss_count: int = 0
    cache_export_seconds: float = 0.0
    image_export_seconds: float = 0.0
    push_layers_seconds: float = 0.0
    export_manifest_seconds: float = 0.0
    cached_step_count: int = 0


class BuildResult(BaseModel):
    tags: list[str]
    telemetry: BuildTelemetry = Field(default_factory=BuildTelemetry)


class BuildCommandError(subprocess.CalledProcessError):
    def __init__(
        self,
        returncode: int,
        cmd: list[str],
        *,
        output: str,
        stderr: str,
        telemetry: BuildTelemetry,
    ) -> None:
        super().__init__(returncode, cmd, output=output, stderr=stderr)
        self.telemetry = telemetry


# --- 构建助手 ---


def _extract_tarball(tarball: Path, dest: Path) -> None:
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, "r:gz") as tar, chdir(dest):
        # 预先验证条目
        for m in tar.getmembers():
            name = m.name.lstrip("./")
            p = Path(name)
            if p.is_absolute() or ".." in p.parts:
                raise RuntimeError(f"Unsafe path in sdist: {m.name}")
        # Safe(-r) 提取：无符号链接/设备
        tar.extractall(path=".", filter="data")


def _make_build_context(
    sdk_project_root: Path,
    prebuilt_sdist: Path | None = None,
) -> Path:
    dockerfile_path = _get_dockerfile_path(sdk_project_root)
    tmp_root = Path(tempfile.mkdtemp(prefix="agent-build-", dir=None)).resolve()
    sdist_dir: Path | None = None
    try:
        if prebuilt_sdist is None:
            sdist_dir = Path(
                tempfile.mkdtemp(prefix="agent-sdist-", dir=None)
            ).resolve()
            _run(
                ["uv", "build", "--sdist", "--out-dir", str(sdist_dir.resolve())],
                cwd=str(sdk_project_root.resolve()),
            )
            sdists = sorted(sdist_dir.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime)
            logger.info(
                f"[build] Built {len(sdists)} sdists for "
                f"clean context: {', '.join(str(s) for s in sdists)}"
            )
            assert len(sdists) == 1, "Expected exactly one sdist"
            sdist = sdists[0]
        else:
            sdist = Path(prebuilt_sdist).expanduser().resolve()
            if not sdist.is_file():
                raise FileNotFoundError(f"Pre-built sdist not found at {sdist}")
            logger.info(f"[build] Reusing pre-built sdist for clean context: {sdist}")

        logger.debug(f"[build] Extracting sdist {sdist} to clean context {tmp_root}")
        _extract_tarball(sdist, tmp_root)

        # 断言只创建了一个文件夹
        entries = list(tmp_root.iterdir())
        assert len(entries) == 1 and entries[0].is_dir(), (
            "Expected single folder in sdist"
        )
        tmp_root = entries[0].resolve()
        # 将 Dockerfile 复制到位
        shutil.copy2(dockerfile_path, tmp_root / "Dockerfile")
        logger.debug(f"[build] Clean context ready at {tmp_root}")
        return tmp_root
    except Exception:
        shutil.rmtree(tmp_root, ignore_errors=True)
        raise
    finally:
        if sdist_dir is not None:
            shutil.rmtree(sdist_dir, ignore_errors=True)


def _active_buildx_driver() -> str | None:
    try:
        out = _run(["docker", "buildx", "inspect", "--bootstrap"]).stdout
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("Driver:"):
                return s.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def _default_local_cache_dir() -> Path:
    # 将缓存保留在存储库之外； 如果需要的话用 BUILD_CACHE_DIR 覆盖
    root = os.environ.get("BUILD_CACHE_DIR")
    if root:
        return Path(root).expanduser().resolve()
    xdg = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(xdg) / "openhands" / "buildx-cache"


def _get_dockerfile_path(sdk_project_root: Path) -> Path:
    dockerfile_path = (
        sdk_project_root
        / "openhands-agent-server"
        / "openhands"
        / "agent_server"
        / "docker"
        / "Dockerfile"
    )
    if not dockerfile_path.exists():
        raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")
    return dockerfile_path


def _round_seconds(value: float) -> float:
    return round(value, 3)


def _classify_buildkit_description(description: str) -> str | None:
    normalized = description.strip().lower()
    if normalized.startswith("importing cache manifest from "):
        return "cache_import"
    if normalized.startswith("exporting cache to "):
        return "cache_export"
    if normalized == "exporting to image":
        return "image_export"
    if normalized == "pushing layers":
        return "push_layers"
    if normalized.startswith("exporting manifest"):
        return "export_manifest"
    if normalized.startswith("exporting manifest list"):
        return "export_manifest"
    if normalized.startswith("exporting config"):
        return "export_manifest"
    return None


def _add_buildkit_duration(
    telemetry: BuildTelemetry, description: str, duration_seconds: float
) -> None:
    phase = _classify_buildkit_description(description)
    if phase == "cache_import":
        telemetry.cache_import_seconds += duration_seconds
    elif phase == "cache_export":
        telemetry.cache_export_seconds += duration_seconds
    elif phase == "image_export":
        telemetry.image_export_seconds += duration_seconds
    elif phase == "push_layers":
        telemetry.push_layers_seconds += duration_seconds
    elif phase == "export_manifest":
        telemetry.export_manifest_seconds += duration_seconds


def _parse_buildkit_telemetry(stderr: str) -> BuildTelemetry:
    telemetry = BuildTelemetry()
    step_descriptions: dict[str, str] = {}

    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        match = _BUILDKIT_STEP_RE.match(line)
        if not match:
            continue

        step = match.group("step")
        message = match.group("message").strip()

        if message == "CACHED":
            telemetry.cached_step_count += 1
            continue

        if message.startswith("ERROR:"):
            description = step_descriptions.get(step, "")
            if (
                _classify_buildkit_description(description) == "cache_import"
                and "not found" in message.lower()
            ):
                telemetry.cache_import_miss_count += 1
            continue

        if " ERROR:" in message:
            description = message.split(" ERROR:", 1)[0].strip()
            if (
                _classify_buildkit_description(description) == "cache_import"
                and "not found" in message.lower()
            ):
                telemetry.cache_import_miss_count += 1
            step_descriptions[step] = description
            continue

        done_match = _BUILDKIT_DONE_RE.match(message)
        if done_match:
            description = step_descriptions.get(step)
            if description:
                _add_buildkit_duration(
                    telemetry, description, float(done_match.group("seconds"))
                )
            continue

        inline_done_match = _BUILDKIT_INLINE_DONE_RE.match(message)
        if inline_done_match:
            _add_buildkit_duration(
                telemetry,
                inline_done_match.group("description"),
                float(inline_done_match.group("seconds")),
            )
            continue

        # 仅当尚未分类时才更新步骤描述。 这可以防止子操作（例如“准备导出构建缓存”）
        #
        # from overwriting the main operation (like "exporting cache to registry").
        new_desc = message.removesuffix(" ...").strip()
        existing_desc = step_descriptions.get(step)
        if (
            existing_desc is None
            or _classify_buildkit_description(existing_desc) is None
        ):
            step_descriptions[step] = new_desc

    telemetry.build_context_seconds = _round_seconds(telemetry.build_context_seconds)
    telemetry.buildx_wall_clock_seconds = _round_seconds(
        telemetry.buildx_wall_clock_seconds
    )
    telemetry.cleanup_seconds = _round_seconds(telemetry.cleanup_seconds)
    telemetry.cache_import_seconds = _round_seconds(telemetry.cache_import_seconds)
    telemetry.cache_export_seconds = _round_seconds(telemetry.cache_export_seconds)
    telemetry.image_export_seconds = _round_seconds(telemetry.image_export_seconds)
    telemetry.push_layers_seconds = _round_seconds(telemetry.push_layers_seconds)
    telemetry.export_manifest_seconds = _round_seconds(
        telemetry.export_manifest_seconds
    )
    return telemetry


# --- 单入口 ---


def build_with_telemetry(opts: BuildOptions) -> BuildResult:
    """构建智能体-服务器映像并返回标签以及相位遥测。"""
    dockerfile_path = _get_dockerfile_path(opts.sdk_project_root)
    push = opts.push
    if push is None:
        push = IN_CI

    tags = opts.all_tags
    cache_tag, cache_tag_base = opts.cache_tags

    telemetry = BuildTelemetry()
    build_context_started = time.monotonic()
    # 只有 base-image-minimal 有零上下文 dependency (no COPY 从构建中上下文，直接或间接
    # 的)。 基础镜像是不尽管看起来不符合这条快速路径，它仍然符合条件上下文-免费一目了然
    # ：它整合了  `builder` stage (for ) VSCode extensions), and `builder` 它自身 COPYs
    # the real SDK 源码从上下文。 这个依赖项在Dockerfile级别是无条件的，所以排除vscode
    # INSTALL_CAPABILITIES 缩小了结果图像，但没有这个构建-上下文成本或  `builder` 自己的
    # 构建时间（一个完整的 SDK venv 同步).
    #
    is_base_only = opts.target == "base-image-minimal"
    if is_base_only:
        ctx = Path(tempfile.mkdtemp(prefix="agent-base-ctx-"))
        shutil.copy2(dockerfile_path, ctx / "Dockerfile")
        # ACP的COPYs阶段COPY这个依赖的无依赖的镜像文件（见Dockerfile）——在相同的相对路径
        # 下阶段它，这样上下文就不用拉取REST的源的SDK。
        #
        catalog_dst = ctx / _ACP_INSTALL_CATALOG_RELPATH
        catalog_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(opts.sdk_project_root / _ACP_INSTALL_CATALOG_RELPATH, catalog_dst)
    else:
        ctx = _make_build_context(opts.sdk_project_root, opts.prebuilt_sdist)
    telemetry.build_context_seconds = _round_seconds(
        time.monotonic() - build_context_started
    )
    logger.info(f"[build] {'Empty' if is_base_only else 'Clean'} build context: {ctx}")

    args = [
        "docker",
        "buildx",
        "build",
        "--file",
        str(dockerfile_path),
        "--target",
        opts.target,
        "--build-arg",
        f"BASE_IMAGE={opts.base_image}",
        "--build-arg",
        f"OPENHANDS_BUILD_GIT_SHA={opts.git_sha}",
        "--build-arg",
        f"OPENHANDS_BUILD_GIT_REF={opts.git_ref}",
        "--build-arg",
        f"INSTALL_ACP_PROVIDERS={opts.install_acp_providers}",
        "--build-arg",
        f"INSTALL_CAPABILITIES={opts.install_capabilities}",
    ]
    if push:
        args += ["--platform", ",".join(opts.platforms), "--push"]
    else:
        args += ["--load"]

    for t in tags:
        args += ["--tag", t]

    # --------缓存策略--------
    driver = _active_buildx_driver() or "unknown"
    local_cache_dir = _default_local_cache_dir()
    cache_args: list[str] = []

    # 缓存导出模式：“max”（默认）、“min”或“off” 默认为“max”以保留现有行为； 在批量构建中
    # 设置为“关闭”以避免并行构建多个图像时发生争用
    #
    cache_export_mode = os.environ.get("OPENHANDS_BUILDKIT_CACHE_MODE", "max").lower()
    if cache_export_mode not in ("off", "max", "min"):
        logger.warning(
            f"[build] Invalid OPENHANDS_BUILDKIT_CACHE_MODE='{cache_export_mode}', "
            "defaulting to 'max'"
        )
        cache_export_mode = "max"

    if push:
        # 远程/CI 构建：始终从注册表缓存读取
        cache_args += [
            "--cache-from",
            f"type=registry,ref={opts.image}:{cache_tag}",
            "--cache-from",
            f"type=registry,ref={opts.image}:{cache_tag_base}-main",
        ]
        # 仅在显式启用时导出缓存（避免批量构建中的争用）
        if cache_export_mode in ("max", "min"):
            cache_args += [
                "--cache-to",
                f"type=registry,ref={opts.image}:{cache_tag},mode={cache_export_mode}",
            ]
            logger.info(
                f"[build] Cache: registry read + export mode={cache_export_mode}"
            )
        else:
            logger.info("[build] Cache: registry read only (export disabled)")
    else:
        # 本地/开发版本：如果驱动程序支持，则更喜欢本地目录缓存； 否则仅限内联。
        #
        if driver == "docker-container":
            local_cache_dir.mkdir(parents=True, exist_ok=True)
            cache_args += [
                "--cache-from",
                f"type=local,src={str(local_cache_dir)}",
                "--cache-to",
                f"type=local,dest={str(local_cache_dir)},mode=max",
            ]
            logger.info(
                f"[build] Cache: local dir at {local_cache_dir} (driver={driver})"
            )
        else:
            logger.warning(
                f"[build] WARNING: Active buildx driver is '{driver}', "
                "which does not support local dir caching. Fallback to INLINE CACHE\n"
                " Consider running the following commands to set up a "
                "compatible buildx environment:\n"
                "  1. docker buildx create --name openhands-builder "
                "--driver docker-container --use\n"
                "  2. docker buildx inspect --bootstrap\n"
            )
            # docker driver can't export caches; fall back to inline metadata only.
            cache_args += ["--build-arg", "BUILDKIT_INLINE_CACHE=1"]
            logger.info(f"[build] Cache: inline only (driver={driver})")

    args += cache_args + [str(ctx)]

    logger.info(
        f"[build] Building target='{opts.target}' image='{opts.image}' "
        f"custom_tags='{opts.custom_tags}' from base='{opts.base_image}' "
        f"for platforms='{opts.platforms if push else 'local-arch'}'"
    )
    logger.info(
        f"[build] Git ref='{opts.git_ref}' sha='{opts.git_sha}' "
        f"package_version='{opts.sdk_version}'"
    )
    logger.info(f"[build] Cache tag: {cache_tag}")

    buildx_started = time.monotonic()
    try:
        res = _run(args, cwd=str(ctx))
        telemetry.buildx_wall_clock_seconds = _round_seconds(
            time.monotonic() - buildx_started
        )
        parsed = _parse_buildkit_telemetry(res.stderr)
        parsed.build_context_seconds = telemetry.build_context_seconds
        parsed.buildx_wall_clock_seconds = telemetry.buildx_wall_clock_seconds
        telemetry = parsed
        sys.stdout.write(res.stdout or "")
    except subprocess.CalledProcessError as e:
        telemetry.buildx_wall_clock_seconds = _round_seconds(
            time.monotonic() - buildx_started
        )
        parsed = _parse_buildkit_telemetry(e.stderr or "")
        parsed.build_context_seconds = telemetry.build_context_seconds
        parsed.buildx_wall_clock_seconds = telemetry.buildx_wall_clock_seconds
        telemetry = parsed
        logger.error(f"[build] ERROR: Build failed with exit code {e.returncode}")
        logger.error(f"[build] Command: {' '.join(e.cmd)}")
        logger.error(f"[build] Full stdout:\n{e.output}")
        logger.error(f"[build] Full stderr:\n{e.stderr}")
        raise BuildCommandError(
            e.returncode,
            e.cmd,
            output=e.output or "",
            stderr=e.stderr or "",
            telemetry=telemetry,
        ) from e
    finally:
        cleanup_started = time.monotonic()
        logger.info(f"[build] Cleaning {ctx}")
        shutil.rmtree(ctx, ignore_errors=True)
        telemetry.cleanup_seconds = _round_seconds(time.monotonic() - cleanup_started)

    logger.info("[build] Done. Tags:")
    for t in tags:
        logger.info(f" - {t}")
    logger.info("[build] Telemetry: %s", telemetry.model_dump_json())
    return BuildResult(tags=tags, telemetry=telemetry)


def build(opts: BuildOptions) -> list[str]:
    """单个入口用于构建智能体服务器映像。"""
    return build_with_telemetry(opts).tags


# --- CLI 垫片 ---


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v else default


def main(argv: list[str]) -> int:
    # ---- argparse ----
    parser = argparse.ArgumentParser(
        description="Single-entry build helper for agent-server images."
    )
    parser.add_argument(
        "--base-image",
        default=_env("BASE_IMAGE", "python-node-runtime"),
        help="Base image to use (default from $BASE_IMAGE).",
    )
    parser.add_argument(
        "--custom-tags",
        default=_env("CUSTOM_TAGS", ""),
        help="Comma-separated custom tags (default from $CUSTOM_TAGS).",
    )
    parser.add_argument(
        "--image",
        default=_env("IMAGE", "ghcr.io/openhands/agent-server"),
        help="Image repo/name (default from $IMAGE).",
    )
    parser.add_argument(
        "--image-flavor",
        default=_env("IMAGE_FLAVOR", "default"),
        choices=("default", "slim", "minimal"),
        help="Image flavor (default from $IMAGE_FLAVOR).",
    )
    parser.add_argument(
        "--target",
        default=_env("TARGET", "binary"),
        choices=sorted(VALID_TARGETS),
        help="Build target (default from $TARGET).",
    )
    parser.add_argument(
        "--platforms",
        default=_env("PLATFORMS", "linux/amd64,linux/arm64"),
        help="Comma-separated platforms (default from $PLATFORMS).",
    )
    parser.add_argument(
        "--arch",
        default=_env("ARCH", ""),
        help=(
            "Architecture suffix for tags (e.g., 'amd64', 'arm64', default from $ARCH)."
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--push",
        action="store_true",
        help="Force push via buildx (overrides env).",
    )
    group.add_argument(
        "--load",
        action="store_true",
        help="Force local load (overrides env).",
    )
    parser.add_argument(
        "--sdk-project-root",
        type=Path,
        default=None,
        help="Path to OpenHands SDK root (default: auto-detect).",
    )
    parser.add_argument(
        "--prebuilt-sdist",
        type=Path,
        default=None,
        help="Path to a pre-built SDK sdist tarball to reuse for the build context.",
    )
    parser.add_argument(
        "--build-ctx-only",
        action="store_true",
        help="Only create the clean build context directory and print its path.",
    )
    parser.add_argument(
        "--versioned-tag",
        action="store_true",
        help=(
            "Include git tag-derived release tags (including semver aliases such "
            "as v1 and v1.2) in output. Should only be used for release builds."
        ),
    )
    parser.add_argument(
        "--install-acp-providers",
        # os.environ.get, not _env(): an explicit empty string here means
        # “安装 None”并且必须生存，但 _env() 将空白视为未设置。
        default=os.environ.get(
            "INSTALL_ACP_PROVIDERS", ",".join(DEFAULT_PREINSTALLED_ACP_PROVIDERS)
        ),
        help=(
            "Comma-separated ACP provider keys to bake into the image "
            "(default from $INSTALL_ACP_PROVIDERS; empty string installs none)."
        ),
    )
    parser.add_argument(
        "--install-capabilities",
        # os.environ.get, not _env(): an explicit empty string here means
        # “安装 None”并且必须生存，但 _env() 将空白视为未设置。
        default=os.environ.get("INSTALL_CAPABILITIES", "vscode,browser,docker"),
        help=(
            "Comma-separated capability keys to bake into the image "
            "(default from $INSTALL_CAPABILITIES; empty string installs none)."
        ),
    )

    args = parser.parse_args(argv)

    # ---- 解析 SDK 项目根 ----
    sdk_project_root = args.sdk_project_root
    if sdk_project_root is None:
        try:
            sdk_project_root = _default_sdk_project_root()
        except Exception as e:
            logger.error(str(e))
            return 1

    # ---- 仅构建 ctx 路径 ----
    if args.build_ctx_only:
        ctx = _make_build_context(sdk_project_root, args.prebuilt_sdist)
        logger.info(f"[build] Clean build context (kept for debugging): {ctx}")

        # 创建BuildOptions生成标签
        opts = BuildOptions(
            base_image=args.base_image,
            custom_tags=args.custom_tags,
            image=args.image,
            image_flavor=args.image_flavor,
            target=args.target,  # type: ignore
            platforms=[p.strip() for p in args.platforms.split(",") if p.strip()],  # type: ignore
            push=None,  # 与仅 build-ctx 无关
            sdk_project_root=sdk_project_root,
            prebuilt_sdist=args.prebuilt_sdist,
            arch=args.arch or None,
            include_versioned_tag=args.versioned_tag,
            install_acp_providers=args.install_acp_providers,
            install_capabilities=args.install_capabilities,
        )

        # 如果在 GitHub 操作中运行，则将输出直接写入 GITHUB_OUTPUT
        github_output = os.environ.get("GITHUB_OUTPUT")
        if github_output:
            with open(github_output, "a") as fh:
                fh.write(f"build_context={ctx}\n")
                fh.write(f"dockerfile={ctx / 'Dockerfile'}\n")
                fh.write(f"tags_csv={','.join(opts.all_tags)}\n")
                # 仅在使用时输出版本控制标签
                if opts.include_versioned_tag:
                    fh.write(f"versioned_tags_csv={','.join(opts.versioned_tags)}\n")
                else:
                    fh.write("versioned_tags_csv=\n")
                fh.write(f"base_image_slug={opts.base_image_slug}\n")
            logger.info("[build] Wrote outputs to $GITHUB_OUTPUT")

        # 还打印到标准输出以供调试/本地使用
        print(str(ctx))
        return 0

    # ---- 推送/加载分辨率（CLI 胜过 env，否则自动）----
    push: bool | None
    if args.push:
        push = True
    elif args.load:
        push = False
    else:
        push = (
            True
            if os.environ.get("PUSH") == "1"
            else False
            if os.environ.get("LOAD") == "1"
            else None
        )

    # ---- 正常构建路径 ----
    opts = BuildOptions(
        base_image=args.base_image,
        custom_tags=args.custom_tags,
        image=args.image,
        image_flavor=args.image_flavor,
        target=args.target,  # type: ignore
        platforms=[p.strip() for p in args.platforms.split(",") if p.strip()],  # type: ignore
        push=push,
        sdk_project_root=sdk_project_root,
        prebuilt_sdist=args.prebuilt_sdist,
        arch=args.arch or None,
        include_versioned_tag=args.versioned_tag,
        install_acp_providers=args.install_acp_providers,
        install_capabilities=args.install_capabilities,
    )
    tags = build(opts)

    # --- 公开 GitHub 操作的输出 ---
    def _write_gha_outputs(
        image: str,
        short_sha: str,
        versioned_tags: list[str],
        tags_list: list[str],
        include_versioned_tag: bool,
    ) -> None:
        """
        如果在 GitHub 操作中运行，请将步骤输出附加到 $GITHUB_OUTPUT。
        - image: 仓库/名称（无标签）
        - short_sha: 7 个字符 SHA
        - versioned_tags_csv: 以逗号分隔的版本标记列表（如果未启用则为空）
        - tags: 多行输出（每行一个）
        - tags_csv: 单行，逗号分隔
        """
        out_path = os.environ.get("GITHUB_OUTPUT")
        if not out_path:
            return
        with open(out_path, "a", encoding="utf-8") as fh:
            fh.write(f"image={image}\n")
            fh.write(f"short_sha={short_sha}\n")
            # 仅在使用时输出版本控制标签
            if include_versioned_tag:
                fh.write(f"versioned_tags_csv={','.join(versioned_tags)}\n")
            else:
                fh.write("versioned_tags_csv=\n")
            fh.write(f"tags_csv={','.join(tags_list)}\n")
            fh.write("tags<<EOF\n")
            fh.write("\n".join(tags_list) + "\n")
            fh.write("EOF\n")

    _write_gha_outputs(
        opts.image,
        opts.short_sha,
        opts.versioned_tags,
        tags,
        opts.include_versioned_tag,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
