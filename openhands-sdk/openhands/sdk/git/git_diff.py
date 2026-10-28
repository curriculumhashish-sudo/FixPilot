#!/usr/bin/env python3
"""在单个 git 文件中获取文件系统中最近的 git 存储库的 git diff"""

import json
import logging
import os
import sys
from pathlib import Path

from openhands.sdk.git.exceptions import (
    GitCommandError,
    GitPathError,
    GitRepositoryError,
)
from openhands.sdk.git.models import GitDiff
from openhands.sdk.git.utils import (
    get_valid_ref,
    run_git_command,
    validate_git_repository,
)


logger = logging.getLogger(__name__)


MAX_FILE_SIZE_FOR_GIT_DIFF = 1024 * 1024  # 1兆字节


def get_closest_git_repo(path: Path) -> Path | None:
    """通过向上目录树查找最近的 git 存储库。

    Args:
        path: 搜索的起始路径

    Returns:
        git 存储库根的路径，如果未找到则为 None
    """
    current_path = path.resolve()

    while True:
        git_path = current_path / ".git"
        if git_path.exists():  # 可以是文件（工作树）或目录
            logger.debug(f"Found git repository at: {current_path}")
            return current_path

        parent = current_path.parent
        if parent == current_path:  # 已到达文件系统根目录
            logger.debug(f"No git repository found for path: {path}")
            return None
        current_path = parent


def _base_file_size(repo: Path, ref: str, relative_path: Path) -> int | None:
    """文件 (blob) 的大小 ``relative_path`` 位于 ``ref`` 或 ``None``
    当 ``ref`` 在该路径上没有文件时。"""
    spec = f"{ref}:{relative_path.as_posix()}"
    try:
        object_type = run_git_command(
            ["git", "cat-file", "-t", spec], repo, expected_failure=True
        )
        if object_type != "blob":
            return None
        return int(run_git_command(["git", "cat-file", "-s", spec], repo))
    except (GitCommandError, ValueError):
        return None


def get_git_diff(relative_file_path: str | Path, ref: str | None = None) -> GitDiff:
    """获取单个文件的 git diff。

    Args:
        relative_file_path: 相对于当前工作目录的文件路径
        ref: 用于比较的可选显式引用 (e.g. ``"HEAD"`` 或
            提交哈希）。 当 ``None`` 时，与以前一样与自动检测的上游/默认分支进行比较
            。

    Returns:
        GitDiff 包含差异信息的对象

    Raises:
        GitPathError: 如果文件太大，或者既不在磁盘上也不存在
            在基本引用处（工作树删除与基本文本相对于 ``""`` 的差异）
        GitRepositoryError: 如果不在 git 存储库中
        GitCommandError: 如果 git 命令失败（包括 ``ref`` 为
            提供但未在存储库中解析）。
    """
    path = Path(os.getcwd(), relative_file_path).resolve()
    missing_error = GitPathError(f"File does not exist: {path}")

    # 磁盘中丢失的路径可能仍然是仅存在于基本引用中的工作树删除（或重命名的旧部分）。
    #
    deleted = not path.exists()

    # 检查文件大小
    try:
        file_size = 0 if deleted else os.path.getsize(path)
        if file_size > MAX_FILE_SIZE_FOR_GIT_DIFF:
            raise GitPathError(
                f"File too large for git diff: {file_size} bytes "
                f"(max: {MAX_FILE_SIZE_FOR_GIT_DIFF} bytes)"
            )
    except OSError as e:
        raise GitPathError(f"Cannot access file: {path}") from e

    # 找到git仓库
    closest_git_repo = get_closest_git_repo(path)
    if not closest_git_repo:
        if deleted:
            raise missing_error
        raise GitRepositoryError(f"File is not in a git repository: {path}")

    # 验证 git 存储库
    validated_repo = validate_git_repository(closest_git_repo)

    # 必须匹配 get_changes_in_repo 的基本选择（目的=“显示”），因此每个文件的差异与打开它
    # 的更改列表对齐。
    #
    current_rev = get_valid_ref(validated_repo, override=ref, purpose="display")
    if not current_rev:
        if deleted:
            raise missing_error
        logger.warning(f"No valid git reference found for {validated_repo}")
        return GitDiff(modified="", original="")

    # 获取 git repo 根目录的相对路径
    try:
        relative_path_from_repo = path.relative_to(validated_repo)
    except ValueError as e:
        raise GitPathError(f"File is not within git repository: {path}") from e

    if deleted:
        base_size = _base_file_size(
            validated_repo, current_rev, relative_path_from_repo
        )
        if base_size is None:
            raise missing_error
        if base_size > MAX_FILE_SIZE_FOR_GIT_DIFF:
            raise GitPathError(
                f"File too large for git diff: {base_size} bytes "
                f"(max: {MAX_FILE_SIZE_FOR_GIT_DIFF} bytes)"
            )

    # 获取旧内容（来自参考）
    try:
        # 逐字读取 blob 并将其规范化，就像下面修改的一侧一样，因此未更改的文件在两侧都会
        # 保留其边缘空白。
        #
        original = "\n".join(
            run_git_command(
                ["git", "show", f"{current_rev}:{relative_path_from_repo}"],
                validated_repo,
                strip=False,
            ).splitlines()
        )
    except GitCommandError:
        logger.debug(f"No old content found for {path} at ref {current_rev}")
        original = ""

    if deleted:
        logger.info(f"Generated git diff for deleted file {path}")
        return GitDiff(modified="", original=original)

    # 获取新内容（当前文件）
    try:
        with open(path, encoding="utf-8") as f:
            modified = "\n".join(f.read().splitlines())
    except (OSError, UnicodeDecodeError) as e:
        logger.error(f"Failed to read file {path}: {e}")
        modified = ""

    logger.info(f"Generated git diff for {path}")
    return GitDiff(
        modified=modified,
        original=original,
    )


if __name__ == "__main__":
    diff = get_git_diff(sys.argv[-1])
    print(json.dumps(diff))
