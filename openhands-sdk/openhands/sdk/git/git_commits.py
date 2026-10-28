"""API 用于显示 git 的历史记录的辅助工具：列出仓库的最近提交，以及检查单个提交更改的
全部内容（文件列表和文件内容）——即使一个提交删除的文件或自删除的文件，仍然可以显
示。
"""

import logging
import os
from pathlib import Path

from openhands.sdk.git.exceptions import (
    GitCommandError,
    GitPathError,
    GitRepositoryError,
)
from openhands.sdk.git.git_changes import _parse_name_status
from openhands.sdk.git.git_diff import (
    MAX_FILE_SIZE_FOR_GIT_DIFF,
    get_closest_git_repo,
)
from openhands.sdk.git.models import GitChange, GitCommit, GitCommitsPage, GitDiff
from openhands.sdk.git.utils import (
    GIT_EMPTY_TREE_HASH,
    _rev_parse,
    run_git_command,
    validate_git_repository,
)


logger = logging.getLogger(__name__)

DEFAULT_COMMIT_LIMIT = 50

# 每一条提交记录一条：全 sha、短 sha、作者名、作者日期（严格 ISO 8601）；主题 — 单词分隔
# （0x1F 不能出现在任何这些字段中） 主题不能包含换行符）。
#
_LOG_FORMAT = "%H%x1f%h%x1f%an%x1f%aI%x1f%s"


def get_git_commits(
    repo_path: str | Path, limit: int = DEFAULT_COMMIT_LIMIT
) -> GitCommitsPage:
    """列出存储库的最新提交（可从 HEAD 访问），
    最新的优先。

    故意地，分支的原始历史 —— 比如 Git 主机的“提交”页面 —— 而不是基于基础的范围：提交
    的工作必须始终可见，包括在对话相关的范围为空的情况下 (e.g。 位
    于其默认分支或完全推送分支上的无远程存储库）。

    Args:
        repo_path: git 存储库的路径。
        limit: 返回的最大提交数。

    Returns:
        GitCommitsPage 最多 ``limit`` 次提交，``has_more`` 告诉历史记录是否包含更多内
        容。

    Raises:
        GitRepositoryError: 如果该目录不是有效的 git 存储库。
        GitCommandError: 如果 git 命令失败。
    """
    validated_repo = validate_git_repository(repo_path)

    head = _rev_parse(validated_repo, "HEAD")
    if head is None:
        # Unborn/orphan HEAD：`git log HEAD` 将失败，并且此分支上没有提交任何内容要列出
        # 。
        #
        return GitCommitsPage(commits=[], has_more=False)

    # --no-show-signature：带有 log.showSignature=True 的存储库
    # 否则将 GPG 输出与格式化行交错。
    output = run_git_command(
        [
            "git",
            "--no-pager",
            "log",
            "--no-show-signature",
            f"--format={_LOG_FORMAT}",
            "-n",
            str(limit + 1),
            head,
        ],
        validated_repo,
    )

    commits: list[GitCommit] = []
    for line in output.splitlines() if output else []:
        fields = line.split("\x1f")
        if len(fields) != 5:
            logger.warning(f"Skipping malformed git log line: {line!r}")
            continue
        sha, short_sha, author, timestamp, subject = fields
        commits.append(
            GitCommit(
                sha=sha,
                short_sha=short_sha,
                subject=subject,
                author=author,
                timestamp=timestamp,
            )
        )

    return GitCommitsPage(commits=commits[:limit], has_more=len(commits) > limit)


def _resolve_commit(repo: Path, commit: str) -> str:
    """将 ``commit`` 解析为完整提交 SHA。

    Raises:
        GitCommandError: 如果 ``commit`` 没有在此命名提交
            存储库（保持严格，因此错误的 SHA 会显示为错误，而不是默默地呈现“无更改”）
            。
    """
    return run_git_command(
        ["git", "--no-pager", "rev-parse", "--verify", f"{commit}^{{commit}}"],
        repo,
    )


def get_commit_changes(repo_path: str | Path, commit: str) -> list[GitChange]:
    """获取通过单个提交更改的文件，而不是其第一个父级。

    Root 针对空树提交 diff，渲染为全部添加。 重命名遵循共享名称状态解析：DELETED（旧
    路径）+ ADDED（新路径）。

    Args:
        repo_path: git 存储库的路径。
        commit: 提交检查（SHA 或缩写）。

    Raises:
        GitRepositoryError: 如果该目录不是有效的 git 存储库。
        GitCommandError: 如果 ``commit`` 无法解析或 git 失败。
    """
    validated_repo = validate_git_repository(repo_path)
    sha = _resolve_commit(validated_repo, commit)
    parent = _rev_parse(validated_repo, f"{sha}^") or GIT_EMPTY_TREE_HASH

    output = run_git_command(
        ["git", "--no-pager", "diff", "--name-status", parent, sha],
        validated_repo,
    )
    return _parse_name_status(output.splitlines() if output else [])


def _show_file_at_rev(repo: Path, rev: str, relative_path: Path) -> str:
    """``rev``处``relative_path``的内容； 当文件为空字符串
    该侧不存在（相对于父级添加/删除）。

    Raises:
        GitPathError: 如果 blob 超过差异大小上限。
    """
    spec = f"{rev}:{relative_path.as_posix()}"
    try:
        size_output = run_git_command(
            ["git", "--no-pager", "cat-file", "-s", spec], repo
        )
    except GitCommandError:
        return ""

    try:
        size = int(size_output)
    except ValueError:
        size = 0
    if size > MAX_FILE_SIZE_FOR_GIT_DIFF:
        raise GitPathError(
            f"File too large for git diff: {size} bytes "
            f"(max: {MAX_FILE_SIZE_FOR_GIT_DIFF} bytes)"
        )

    try:
        return run_git_command(["git", "--no-pager", "show", spec], repo)
    except GitCommandError:
        return ""


def get_commit_file_diff(file_path: str | Path, commit: str) -> GitDiff:
    """获取由一次提交更改的单个文件的差异。

    双方都来自 git 对象 - 绝不来自磁盘 - 因此删除的提交（或之后删除的文件）仍然呈现。
     故意不进行磁盘上的存在检查。

    Args:
        file_path: 文件的路径，相对于当前工作
            目录（绝对路径赢得连接，镜像
            ``get_git_diff``).
        commit: 提交检查（SHA 或缩写）。

    Returns:
        GitDiff 其中 ``original`` 是提交的第一个父级的文件（根提交的空树），
        ``modified`` 是提交本身的文件。

    Raises:
        GitPathError: 如果文件位于存储库或一侧之外
            超过尺寸上限。
        GitRepositoryError: 如果路径不在 git 存储库内。
        GitCommandError: 如果 ``commit`` 没有解决。
    """
    path = Path(os.getcwd(), file_path).resolve()

    closest_git_repo = get_closest_git_repo(path)
    if not closest_git_repo:
        raise GitRepositoryError(f"File is not in a git repository: {path}")
    validated_repo = validate_git_repository(closest_git_repo)

    sha = _resolve_commit(validated_repo, commit)
    parent = _rev_parse(validated_repo, f"{sha}^") or GIT_EMPTY_TREE_HASH

    try:
        relative_path_from_repo = path.relative_to(validated_repo)
    except ValueError as e:
        raise GitPathError(f"File is not within git repository: {path}") from e

    original = _show_file_at_rev(validated_repo, parent, relative_path_from_repo)
    modified = _show_file_at_rev(validated_repo, sha, relative_path_from_repo)

    logger.info(f"Generated commit file diff for {path} at {sha}")
    return GitDiff(modified=modified, original=original)
