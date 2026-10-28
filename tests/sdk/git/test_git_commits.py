"""使用临时存储库和 bash 命令测试 git_commits.py。"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from openhands.sdk.git.exceptions import GitCommandError, GitPathError
from openhands.sdk.git.git_commits import (
    get_commit_changes,
    get_commit_file_diff,
    get_git_commits,
)
from openhands.sdk.git.git_diff import MAX_FILE_SIZE_FOR_GIT_DIFF
from openhands.sdk.git.models import GitChangeStatus


def run_bash_command(command: str, cwd: str) -> subprocess.CompletedProcess:
    """在指定目录下运行bash命令。"""
    return subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def setup_git_repo(repo_dir: str) -> None:
    """使用基本配置初始化 git 存储库。"""
    run_bash_command("git init -b main", repo_dir)
    run_bash_command("git config user.name 'Test User'", repo_dir)
    run_bash_command("git config user.email 'test@example.com'", repo_dir)


def commit_file(repo_dir: str, name: str, content: str, message: str) -> str:
    """写入``name``，用``message``提交，然后返回提交SHA。"""
    (Path(repo_dir) / name).write_text(content)
    run_bash_command("git add .", repo_dir)
    run_bash_command(f"git commit -m '{message}'", repo_dir)
    return run_bash_command("git rev-parse HEAD", repo_dir).stdout.strip()


def test_get_git_commits_lists_full_history_newest_first():
    """该列表是分支最近的简单历史记录 - 提交保持可见
    无论推送/基础状态如何（最初的投诉是工作消失）。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)
        commit_file(temp_dir, "a.txt", "one", "first commit")
        commit_file(temp_dir, "a.txt", "two", "second commit")

        # 法案
        page = get_git_commits(temp_dir)

        # 断言 - 最新的在前，没有任何内容被排除，没有任何内容被截断。
        assert [commit.subject for commit in page.commits] == [
            "second commit",
            "first commit",
        ]
        assert page.has_more is False


def test_get_git_commits_populates_commit_fields():
    """每个提交都携带 GUI 渲染的元数据（sha、short sha、
    主题、作者、ISO 时间戳）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)
        sha = commit_file(temp_dir, "a.txt", "one", "add a")

        # 法案
        commit = get_git_commits(temp_dir).commits[0]

        # 断言
        assert commit.sha == sha
        assert sha.startswith(commit.short_sha)
        assert commit.subject == "add a"
        assert commit.author == "Test User"
        assert datetime.fromisoformat(commit.timestamp) is not None


def test_get_git_commits_caps_at_limit_with_has_more():
    """超过 ``limit`` 的历史记录将受到限制并被标记。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)
        commit_file(temp_dir, "a.txt", "one", "first commit")
        commit_file(temp_dir, "a.txt", "two", "second commit")

        # 法案
        page = get_git_commits(temp_dir, limit=1)

        # 断言
        assert [commit.subject for commit in page.commits] == ["second commit"]
        assert page.has_more is True


def test_get_git_commits_empty_repo_returns_empty_page():
    """一个新初始化的存储库（未出生的HEAD）会产生一个空页面，而不是一个
    错误。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)

        # 法案
        page = get_git_commits(temp_dir)

        # 断言
        assert page.commits == []
        assert page.has_more is False


def test_get_commit_changes_reports_the_commits_own_files():
    """提交的更改列表包含每个文件及其真实状态 - 并且仅
    提交的文件触及，而不是整个工作树。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排 — 基本提交，然后是一个编辑、添加和删除的提交。
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "to_modify.txt").write_text("original")
        (Path(temp_dir) / "to_delete.txt").write_text("doomed")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'base'", temp_dir)

        (Path(temp_dir) / "to_modify.txt").write_text("changed")
        (Path(temp_dir) / "added.txt").write_text("new")
        run_bash_command("git rm -q to_delete.txt", temp_dir)
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'mixed'", temp_dir)
        sha = run_bash_command("git rev-parse HEAD", temp_dir).stdout.strip()

        # 法案
        changes = get_commit_changes(temp_dir, sha)

        # 断言
        changes_by_path = {str(change.path): change.status for change in changes}
        assert changes_by_path == {
            "to_modify.txt": GitChangeStatus.UPDATED,
            "added.txt": GitChangeStatus.ADDED,
            "to_delete.txt": GitChangeStatus.DELETED,
        }


def test_get_commit_changes_root_commit_lists_all_files_as_added():
    """根提交没有父级，因此它与空树不同。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "a.txt").write_text("a")
        (Path(temp_dir) / "b.txt").write_text("b")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'root'", temp_dir)
        sha = run_bash_command("git rev-parse HEAD", temp_dir).stdout.strip()

        # 法案
        changes = get_commit_changes(temp_dir, sha)

        # 断言
        assert {str(change.path) for change in changes} == {"a.txt", "b.txt"}
        assert all(change.status == GitChangeStatus.ADDED for change in changes)


def test_get_commit_changes_unknown_sha_raises():
    """无法解析的提交表现为错误，而不是“无更改”。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)
        commit_file(temp_dir, "a.txt", "a", "base")

        # 行动+断言
        with pytest.raises(GitCommandError):
            get_commit_changes(temp_dir, "deadbeefdeadbeef")


def test_get_commit_file_diff_returns_parent_and_commit_content():
    """差异面是提交父级处的文件与提交处的文件。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)
        commit_file(temp_dir, "file.txt", "before", "base")
        sha = commit_file(temp_dir, "file.txt", "after", "edit")
        # 稍后的工作树编辑不得泄漏到提交的差异中。
        (Path(temp_dir) / "file.txt").write_text("working tree noise")

        # 法案
        diff = get_commit_file_diff(Path(temp_dir) / "file.txt", sha)

        # 断言
        assert diff.original == "before"
        assert diff.modified == "after"


def test_get_commit_file_diff_renders_deleted_file_from_git_objects():
    """被提交删除的文件不再存在于磁盘上，但它的差异
    仍必须呈现（原始 = 父内容，修改 = 空）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)
        commit_file(temp_dir, "doomed.txt", "contents", "base")
        run_bash_command("git rm -q doomed.txt", temp_dir)
        run_bash_command("git commit -m 'delete'", temp_dir)
        sha = run_bash_command("git rev-parse HEAD", temp_dir).stdout.strip()

        # 法案
        diff = get_commit_file_diff(Path(temp_dir) / "doomed.txt", sha)

        # 断言
        assert diff.original == "contents"
        assert diff.modified == ""


def test_get_commit_file_diff_rejects_oversize_blob():
    """大小上限适用于 git blob（没有磁盘上的文件
    测量已删除的文件）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        setup_git_repo(temp_dir)
        big = "x" * (MAX_FILE_SIZE_FOR_GIT_DIFF + 1)
        sha = commit_file(temp_dir, "big.txt", big, "big file")

        # 行动+断言
        with pytest.raises(GitPathError):
            get_commit_file_diff(Path(temp_dir) / "big.txt", sha)
