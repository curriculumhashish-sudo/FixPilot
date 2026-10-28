#!/usr/bin/env python3
"""获取当前工作目录相对于远程源的 git 更改
if possible.
"""

import glob
import json
import logging
import os
from pathlib import Path

from openhands.sdk.git.exceptions import (
    GitCommandError,
    GitError,
    GitRepositoryError,
)
from openhands.sdk.git.models import GitChange, GitChangeStatus
from openhands.sdk.git.utils import (
    get_valid_ref,
    run_git_command,
    validate_git_repository,
)


logger = logging.getLogger(__name__)


def _map_git_status_to_enum(status: str) -> GitChangeStatus:
    """将 git 状态代码映射到 GitChangeStatus 枚举值。"""
    status_mapping = {
        "M": GitChangeStatus.UPDATED,
        "A": GitChangeStatus.ADDED,
        "D": GitChangeStatus.DELETED,
        "U": GitChangeStatus.UPDATED,  # 未合并的文件被视为已更新
    }
    if status not in status_mapping:
        raise ValueError(f"Unknown git status: {status}")
    return status_mapping[status]


def _parse_name_status(changed_files: list[str]) -> list[GitChange]:
    """将 ``git diff --name-status`` 输出行解析为 GitChange 对象。

    重命名分为DELETED（旧路径）+ADDED（新路径）； 仅复制表面新路径作为ADDED。
    """
    changes: list[GitChange] = []
    for line in changed_files:
        if not line.strip():
            logger.warning("Empty line in git diff output, skipping")
            continue

        # 处理 git diff --name-status 的不同输出格式根据 git 配置，格式可以是：
        # * "A file.txt"
        # * "A       file.txt"
        # * “R100 old_file.txt new_file.txt”（用相似度百分比重命名）
        parts = line.split()
        if len(parts) < 2:
            logger.error(f"Unexpected git diff line format: {line}")
            raise GitCommandError(
                message=f"Unexpected git diff output format: {line}",
                command=["git", "diff", "--name-status"],
                exit_code=0,
                stderr="Invalid output format",
            )

        status = parts[0].strip()

        # 处理重命名操作（状态以“R”开头，后跟相似百分比）
        #
        if status.startswith("R") and len(parts) == 3:
            # 重命名：转换为删除（旧路径）+添加（新路径）
            old_path = parts[1].strip()
            new_path = parts[2].strip()
            changes.append(
                GitChange(
                    status=GitChangeStatus.DELETED,
                    path=Path(old_path),
                )
            )
            changes.append(
                GitChange(
                    status=GitChangeStatus.ADDED,
                    path=Path(new_path),
                )
            )
            logger.debug(f"Found git rename: {old_path} -> {new_path}")
            continue

        # 处理复制操作（状态以“C”开头，后跟相似百分比）
        #
        elif status.startswith("C") and len(parts) == 3:
            # 复制：仅添加新路径（保留原来的路径）
            new_path = parts[2].strip()
            changes.append(
                GitChange(
                    status=GitChangeStatus.ADDED,
                    path=Path(new_path),
                )
            )
            logger.debug(f"Found git copy: -> {new_path}")
            continue

        # 处理常规操作（M、A、D 等）
        elif len(parts) == 2:
            path = parts[1].strip()
        else:
            logger.error(f"Unexpected git diff line format: {line}")
            raise GitCommandError(
                message=f"Unexpected git diff output format: {line}",
                command=["git", "diff", "--name-status"],
                exit_code=0,
                stderr="Invalid output format",
            )

        if status == "??":
            status = "A"
        elif status == "*":
            status = "M"

        # 检查有效的单字符状态代码
        if status in {"M", "A", "D", "U"}:
            try:
                changes.append(
                    GitChange(
                        status=_map_git_status_to_enum(status),
                        path=Path(path),
                    )
                )
                logger.debug(f"Found git change: {status} {path}")
            except ValueError as e:
                logger.error(f"Unknown git status '{status}' for file {path}")
                raise GitCommandError(
                    message=f"Unknown git status: {status}",
                    command=["git", "diff", "--name-status"],
                    exit_code=0,
                    stderr=f"Unknown status code: {status}",
                ) from e
        else:
            logger.error(f"Unexpected git status '{status}' for file {path}")
            raise GitCommandError(
                message=f"Unexpected git status: {status}",
                command=["git", "diff", "--name-status"],
                exit_code=0,
                stderr=f"Unexpected status code: {status}",
            )
    return changes


def get_changes_in_repo(
    repo_dir: str | Path, ref: str | None = None
) -> list[GitChange]:
    """获取存储库中相对于引用的 git 更改。

    默认情况下，与自动检测到的远程分支进行比较。 通行证
    ``ref="HEAD"`` 来获取 ``git status`` 样式的差异（工作树 + 索引与最新提交）。

    Args:
        repo_dir: git 存储库的路径，或其中的目录的路径。
            仅列出该目录下的更改以及相对于该目录的路径。
        ref: 用于比较的可选显式引用 (e.g. ``"HEAD"`` 或
            提交哈希）。 当 ``None`` 时，行为与以前一样并与上游/默认分支进行比较。

    Returns:
        表示更改的 GitChange 对象列表

    Raises:
        GitRepositoryError: 如果该目录不是有效的 git 存储库
        GitCommandError: 如果 git 命令失败（包括 ``ref`` 为
            提供但未在存储库中解析）。
    """
    # 首先验证存储库
    validated_repo = validate_git_repository(repo_dir)

    # 这些更改将呈现给用户 (e.g. 在这种情况下，GUI的差异视图]，因此自动检测基线：保留已
    # 提交和已推送的工作，而不是隐藏在空基线后面。
    #
    ref = get_valid_ref(validated_repo, override=ref, purpose="display")
    if not ref:
        logger.warning(f"No valid git reference found for {validated_repo}")
        return []

    # 使用安全 git 命令获取更改的文件。 ``--relative`` 将差异限制为 ``repo_dir`` 并打印
    # 相对于它的路径，与
    # ``git ls-files --others`` 下面，因此存储库的子目录不会混合存储库相对路径和子目录相
    # 对路径。
    #
    try:
        changed_files_output = run_git_command(
            ["git", "--no-pager", "diff", "--name-status", "--relative", ref],
            validated_repo,
        )
        changed_files = (
            changed_files_output.splitlines() if changed_files_output else []
        )
    except GitCommandError as e:
        logger.error(f"Failed to get git diff for {validated_repo}: {e}")
        raise
    changes = _parse_name_status(changed_files)

    # 获取未跟踪的文件
    try:
        untracked_output = run_git_command(
            ["git", "--no-pager", "ls-files", "--others", "--exclude-standard"],
            validated_repo,
        )
        untracked_files = untracked_output.splitlines() if untracked_output else []
    except GitCommandError as e:
        logger.error(f"Failed to get untracked files for {validated_repo}: {e}")
        untracked_files = []
    for path in untracked_files:
        if path.strip():
            changes.append(
                GitChange(
                    status=GitChangeStatus.ADDED,
                    path=Path(path.strip()),
                )
            )
            logger.debug(f"Found untracked file: {path}")

    logger.info(f"Found {len(changes)} total git changes in {validated_repo}")
    return changes


def get_git_changes(cwd: str | Path, ref: str | None = None) -> list[GitChange]:
    git_dirs = {
        os.path.dirname(f)[2:]
        for f in glob.glob("./*/.git", root_dir=cwd, recursive=True)
    }

    # 首先尝试工作区目录。 一个本身不是仓库的目录，却包含了它下面的仓库（仓库支持的对话
    # 的``{base}/{repo}``布局）本身不产生任何更改。
    #
    base_error: GitRepositoryError | None = None
    try:
        changes = get_changes_in_repo(cwd, ref=ref)
    except GitRepositoryError as e:
        if not git_dirs:
            raise
        base_error = e
        changes = []

    # 过滤掉嵌套存储库之一内的任何更改。 它比较的是路径祖先，而不是字符串前缀：名为“foo”
    # 的嵌套仓库不能吞掉名为“foobar/file.py”或“foo-config.yaml”的根仓库更改，尽管它们只
    # 是以“foo”为前缀。
    #
    changes = [
        change
        for change in changes
        if not any(Path(change.path).is_relative_to(git_dir) for git_dir in git_dirs)
    ]

    # 从 git 目录添加更改
    found_nested_repo = False
    for git_dir in git_dirs:
        try:
            git_dir_changes = get_changes_in_repo(str(Path(cwd, git_dir)), ref=ref)
        except GitError:
            logger.warning(
                f"Skipping nested git directory {git_dir}: not a valid repository"
            )
            continue
        found_nested_repo = True
        for change in git_dir_changes:
            # 使用更新的路径创建新的 GitChange
            updated_change = GitChange(
                status=change.status,
                path=Path(git_dir) / change.path,
            )
            changes.append(updated_change)

    # 该目录及其下面的任何内容都不是存储库。
    if base_error is not None and not found_nested_repo:
        raise base_error

    changes.sort(key=lambda change: str(change.path))

    return changes


if __name__ == "__main__":
    try:
        changes = get_git_changes(os.getcwd())
        # 将 GitChange 对象转换为 JSON 序列化的字典
        changes_dict = [
            {
                "status": change.status.value,
                "path": str(change.path),
            }
            for change in changes
        ]
        print(json.dumps(changes_dict))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
