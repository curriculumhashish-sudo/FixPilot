"""每层可能会丢弃的内容：停止的运行时可以重建的路径。"""

import os
import subprocess
from pathlib import Path
from typing import Final

from openhands.sdk.utils.command import sanitized_env


# $HOME下的可重建缓存：XDG工具（uv、pip、yarn、go）使用.cache，
# npm ignores XDG and uses .npm.
CACHE_DIRS: Final[tuple[str, ...]] = (".cache", ".npm")


def caches(home: Path) -> list[Path]:
    # 词法分析者：符号链接缓存仍然被丢弃（未链接，从未跟踪）。
    return [home / name for name in CACHE_DIRS if os.path.lexists(home / name)]


def ignored_dirs(workspace: Path) -> list[Path]:
    """Git 忽略了工作区的目录以及直接在其内部签出的目录。"""
    workspace = workspace.resolve()
    repos = [workspace, *(git.parent for git in workspace.glob("*/.git"))]
    return [
        path
        for repo in repos
        if (repo / ".git").exists()
        for path in git_ignored_dirs(repo)
        if path.parent.resolve().is_relative_to(workspace)
    ]


def git_ignored_dirs(repo: Path) -> list[Path]:
    result = subprocess.run(
        [
            "git",
            "--no-optional-locks",
            # 存储库自己的配置是智能体-可写的； fsmonitor 会运行它。
            "-c",
            "core.fsmonitor=false",
            "-C",
            str(repo),
            "ls-files",
            "-z",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--directory",
        ],
        env=sanitized_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        return []
    candidates = sorted(
        path
        for entry in result.stdout.split("\0")
        if entry.endswith("/")
        and (path := repo / entry.rstrip("/")).is_dir()
        and not path.is_symlink()
        and not _holds_checkout(path)
    )
    # `dir/**/*` 模式列出 dir/ 及其每个子目录； 摆脱父母已经占据了REST。
    #
    kept: list[Path] = []
    for path in candidates:
        if not any(path.is_relative_to(parent) for parent in kept):
            kept.append(path)
    return kept


def _holds_checkout(path: Path) -> bool:
    """包含克隆的被忽略的目录是某人的工作，而不是构建输出。

    限制为三个级别，因此不会遍历较大的 node_modules。
    """
    return any(
        next(path.glob(pattern), None) is not None
        for pattern in (".git", "*/.git", "*/*/.git")
    )
