"""使用临时目录和 bash 命令测试 git_changes.py 功能。"""  # noqa: E501

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from openhands.sdk.git.exceptions import GitCommandError, GitRepositoryError
from openhands.sdk.git.git_changes import get_changes_in_repo, get_git_changes
from openhands.sdk.git.models import GitChange, GitChangeStatus


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
    run_bash_command("git init", repo_dir)
    run_bash_command("git config user.name 'Test User'", repo_dir)
    run_bash_command("git config user.email 'test@example.com'", repo_dir)


def test_get_changes_in_repo_empty_repository():
    """使用空存储库测试 get_changes_in_repo。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        changes = get_changes_in_repo(temp_dir)
        assert changes == []


def test_get_changes_in_repo_new_files():
    """使用新文件测试 get_changes_in_repo。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建新文件
        (Path(temp_dir) / "file1.txt").write_text("Hello World")
        (Path(temp_dir) / "file2.py").write_text("print('Hello')")

        changes = get_changes_in_repo(temp_dir)

        assert len(changes) == 2

        # 按路径排序以实现一致的测试
        changes.sort(key=lambda x: str(x.path))

        assert changes[0].path == Path("file1.txt")
        assert changes[0].status == GitChangeStatus.ADDED

        assert changes[1].path == Path("file2.py")
        assert changes[1].status == GitChangeStatus.ADDED


def test_get_changes_in_repo_modified_files():
    """使用修改后的文件测试 get_changes_in_repo。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建并提交初始文件
        (Path(temp_dir) / "file1.txt").write_text("Initial content")
        (Path(temp_dir) / "file2.py").write_text("print('Initial')")

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 修改文件
        (Path(temp_dir) / "file1.txt").write_text("Modified content")
        (Path(temp_dir) / "file2.py").write_text("print('Modified')")

        changes = get_changes_in_repo(temp_dir)

        # 没有远程仓库（默认分支上）的仓库（HEAD）与 UPDATED 相比，所以修改过的文件会显
        # 示为 ADDED 整个仓库列表，而不是空树。
        #
        assert len(changes) == 2

        # 按路径排序以实现一致的测试
        changes.sort(key=lambda x: str(x.path))

        assert changes[0].path == Path("file1.txt")
        assert changes[0].status == GitChangeStatus.UPDATED

        assert changes[1].path == Path("file2.py")
        assert changes[1].status == GitChangeStatus.UPDATED


def test_get_changes_in_repo_deleted_files():
    """使用已删除的文件测试 get_changes_in_repo。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建并提交初始文件
        (Path(temp_dir) / "file1.txt").write_text("Content to delete")
        (Path(temp_dir) / "file2.py").write_text("print('To delete')")

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 删除文件
        os.remove(Path(temp_dir) / "file1.txt")
        os.remove(Path(temp_dir) / "file2.py")

        changes = get_changes_in_repo(temp_dir)

        # 没有远程比较的存储库与 HEAD 进行比较，因此已提交文件的删除是可见的。
        #
        assert len(changes) == 2

        changes.sort(key=lambda x: str(x.path))

        assert changes[0].path == Path("file1.txt")
        assert changes[0].status == GitChangeStatus.DELETED

        assert changes[1].path == Path("file2.py")
        assert changes[1].status == GitChangeStatus.DELETED


def test_get_changes_in_repo_mixed_changes():
    """使用混合文件更改测试 get_changes_in_repo。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建并提交初始文件
        (Path(temp_dir) / "existing.txt").write_text("Existing content")
        (Path(temp_dir) / "to_modify.py").write_text("print('Original')")
        (Path(temp_dir) / "to_delete.md").write_text("# To Delete")

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 进行混合更改
        (Path(temp_dir) / "new_file.txt").write_text("New file content")  # 已添加
        (Path(temp_dir) / "to_modify.py").write_text("print('Modified')")  # 修改
        os.remove(Path(temp_dir) / "to_delete.md")  # 已删除

        changes = get_changes_in_repo(temp_dir)

        # 没有与 HEAD 进行远程比较的存储库：未列出未更改的已提交文件 (existing.txt)，并
        # 且每种更改都会获取其真实状态。
        #
        assert len(changes) == 3

        # 转换为 dict 以便于测试
        changes_dict = {str(change.path): change.status for change in changes}

        assert changes_dict["new_file.txt"] == GitChangeStatus.ADDED
        assert changes_dict["to_modify.py"] == GitChangeStatus.UPDATED
        assert changes_dict["to_delete.md"] == GitChangeStatus.DELETED


def test_get_changes_in_repo_nested_directories():
    """使用嵌套目录中的文件测试 get_changes_in_repo。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建嵌套目录结构
        nested_dir = Path(temp_dir) / "src" / "utils"
        nested_dir.mkdir(parents=True)

        (nested_dir / "helper.py").write_text("def helper(): pass")
        (Path(temp_dir) / "src" / "main.py").write_text("import utils.helper")
        (Path(temp_dir) / "README.md").write_text("# Project")

        changes = get_changes_in_repo(temp_dir)

        assert len(changes) == 3

        # 转换为路径集以便于测试
        paths = {change.path.as_posix() for change in changes}

        assert "src/utils/helper.py" in paths
        assert "src/main.py" in paths
        assert "README.md" in paths

        # 所有应该添加的文件
        for change in changes:
            assert change.status == GitChangeStatus.ADDED


def test_get_changes_in_repo_subdirectory_paths_are_relative_to_it(tmp_path):
    """存储库的子目录仅列出其自身的更改。"""
    setup_git_repo(str(tmp_path))
    (tmp_path / "src").mkdir()
    (tmp_path / "README.md").write_text("hello\n")
    (tmp_path / "src" / "app.py").write_text("x = 1\n")
    (tmp_path / "src" / "old.py").write_text("old\n")
    run_bash_command("git add . && git commit -m init", str(tmp_path))

    (tmp_path / "README.md").write_text("edited\n")
    (tmp_path / "notes.txt").write_text("note\n")
    (tmp_path / "src" / "app.py").write_text("x = 2\n")
    (tmp_path / "src" / "old.py").unlink()
    (tmp_path / "src" / "new.py").write_text("new\n")

    changes = get_changes_in_repo(tmp_path / "src", ref="HEAD")

    assert sorted((str(c.path), c.status) for c in changes) == [
        ("app.py", GitChangeStatus.UPDATED),
        ("new.py", GitChangeStatus.ADDED),
        ("old.py", GitChangeStatus.DELETED),
    ]


def test_get_changes_in_repo_staged_and_unstaged():
    """使用分阶段和非分阶段更改测试 get_changes_in_repo。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建并提交初始文件
        (Path(temp_dir) / "file.txt").write_text("Initial")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 进行更改并进行一些更改
        (Path(temp_dir) / "file.txt").write_text("Modified")
        (Path(temp_dir) / "staged.txt").write_text("Staged content")
        (Path(temp_dir) / "unstaged.txt").write_text("Unstaged content")

        # 进行一些更改
        run_bash_command("git add staged.txt", temp_dir)

        changes = get_changes_in_repo(temp_dir)

        assert len(changes) == 3

        # 转换为 dict 以便于测试
        changes_dict = {str(change.path): change.status for change in changes}

        # 与HEAD比较：提交后修改的文件是UPDATED； 暂存和未跟踪的新文件是 ADDED。
        #
        assert changes_dict["file.txt"] == GitChangeStatus.UPDATED
        assert changes_dict["staged.txt"] == GitChangeStatus.ADDED
        assert changes_dict["unstaged.txt"] == GitChangeStatus.ADDED


def test_get_changes_in_repo_non_git_directory():
    """使用非 git 目录测试 get_changes_in_repo。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 不要初始化 git repo
        (Path(temp_dir) / "file.txt").write_text("Content")

        with pytest.raises(GitRepositoryError):
            get_changes_in_repo(temp_dir)


def test_get_changes_in_repo_nonexistent_directory():
    """使用不存在的目录测试 get_changes_in_repo。"""
    # 该函数将为不存在的目录引发异常
    with pytest.raises(GitRepositoryError):
        get_changes_in_repo("/nonexistent/directory")


def test_get_git_changes_function():
    """测试 get_git_changes 函数（主入口）。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建测试文件
        (Path(temp_dir) / "test1.txt").write_text("Test content 1")
        (Path(temp_dir) / "test2.py").write_text("print('Test 2')")

        # 使用显式路径调用 get_git_changes
        changes = get_git_changes(temp_dir)

        assert len(changes) == 2

        # 按路径排序以实现一致的测试
        changes.sort(key=lambda x: str(x.path))

        assert changes[0].path == Path("test1.txt")
        assert changes[0].status == GitChangeStatus.ADDED

        assert changes[1].path == Path("test2.py")
        assert changes[1].status == GitChangeStatus.ADDED


def test_get_git_changes_with_path_argument():
    """使用显式路径参数测试 get_git_changes。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建测试文件
        (Path(temp_dir) / "explicit_path.txt").write_text("Explicit path test")

        changes = get_git_changes(temp_dir)

        assert len(changes) == 1
        assert changes[0].path == Path("explicit_path.txt")
        assert changes[0].status == GitChangeStatus.ADDED


def test_git_change_model_properties():
    """测试 GitChange 模型属性和序列化。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建测试文件
        test_file = Path(temp_dir) / "model_test.py"
        test_file.write_text("# Model test file")

        changes = get_changes_in_repo(temp_dir)

        assert len(changes) == 1
        change = changes[0]

        # 测试模型属性
        assert isinstance(change, GitChange)
        assert isinstance(change.path, Path)
        assert isinstance(change.status, GitChangeStatus)
        assert change.path == Path("model_test.py")
        assert change.status == GitChangeStatus.ADDED

        # 测试序列化
        change_dict = change.model_dump()
        assert "path" in change_dict
        assert "status" in change_dict
        assert change_dict["status"] == GitChangeStatus.ADDED


def test_git_change_path_serializes_to_posix_and_deserializes():
    change = GitChange(
        status=GitChangeStatus.ADDED,
        path=Path("nested") / "file.py",
    )

    serialized = change.model_dump(mode="json")
    assert serialized["path"] == "nested/file.py"

    deserialized = GitChange.model_validate(serialized)
    assert deserialized.path == Path("nested/file.py")
    assert deserialized.status == GitChangeStatus.ADDED


def test_git_changes_with_gitignore():
    """测试 gitignore 文件是否受到尊重。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建.gitignore
        (Path(temp_dir) / ".gitignore").write_text("*.log\n__pycache__/\n")

        # 创建应该被忽略的文件
        (Path(temp_dir) / "debug.log").write_text("Log content")
        pycache_dir = Path(temp_dir) / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "module.pyc").write_text("Compiled python")

        # 创建不应被忽略的文件
        (Path(temp_dir) / "main.py").write_text("print('Main')")

        changes = get_changes_in_repo(temp_dir)

        # 应该只看到 .gitignore 和 main.py，而不是被忽略的文件
        paths = {str(change.path) for change in changes}

        assert ".gitignore" in paths
        assert "main.py" in paths
        assert "debug.log" not in paths
        assert "__pycache__/module.pyc" not in paths


def test_get_git_changes_skips_vanished_nested_repo():
    """测试 get_git_changes 是否跳过消失的嵌套存储库 (TOCTOU)。

    通过修补 get_changes_in_repo 来提升一个嵌套目录的 GitRepositoryError，模拟在全局
    扫描和
    validate_git_repository 之间消失的目录。
    """
    from unittest.mock import patch

    from openhands.sdk.git.exceptions import GitRepositoryError

    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 在主存储库中创建一个文件
        (Path(temp_dir) / "main.txt").write_text("main repo file")

        # 创建有效的嵌套存储库
        nested = Path(temp_dir) / "goodrepo"
        nested.mkdir()
        setup_git_repo(str(nested))
        (nested / "nested.txt").write_text("nested file")

        # 创建将“消失”的第二个嵌套存储库
        vanished = Path(temp_dir) / "vanished"
        vanished.mkdir()
        (vanished / ".git").mkdir()  # 足以让 glob 找到它

        # 补丁 get_changes_in_repo 为消失的目录筹集资金
        original_fn = get_changes_in_repo

        def patched_get_changes(repo_dir, ref=None):
            if str(Path(repo_dir).resolve()) == str(vanished.resolve()):
                raise GitRepositoryError(f"Directory does not exist: {repo_dir}")
            return original_fn(repo_dir, ref=ref)

        with patch(
            "openhands.sdk.git.git_changes.get_changes_in_repo",
            side_effect=patched_get_changes,
        ):
            changes = get_git_changes(temp_dir)

        paths = {c.path.as_posix() for c in changes}
        assert "main.txt" in paths
        assert "goodrepo/nested.txt" in paths
        # 消失的仓库应该被跳过，而不是崩溃
        assert all("vanished/" not in p for p in paths)


def test_get_changes_in_repo_rejects_broken_gitfile():
    """如果 git 无法解析 .git 文件，那么它是不够的。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / ".git").write_text("gitdir: /path/that/does/not/exist\n")

        with pytest.raises(GitRepositoryError):
            get_changes_in_repo(temp_dir)


def test_get_git_changes_skips_broken_nested_gitfile():
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "main.txt").write_text("main repo file")

        nested = Path(temp_dir) / "broken"
        nested.mkdir()
        (nested / ".git").write_text("gitdir: /path/that/does/not/exist\n")
        (nested / "nested.txt").write_text("nested file")

        changes = get_git_changes(temp_dir)

        paths = {c.path.as_posix() for c in changes}
        assert "main.txt" in paths
        assert all("broken/" not in p for p in paths)


def test_git_changes_with_binary_files():
    """使用二进制文件测试 git 更改检测。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建二进制文件（用字节模拟）
        binary_file = Path(temp_dir) / "image.png"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00")

        # 创建一个文本文件
        (Path(temp_dir) / "text.txt").write_text("Text content")

        changes = get_changes_in_repo(temp_dir)

        assert len(changes) == 2

        # 这两个文件都应该被检测为已添加
        paths = {str(change.path) for change in changes}
        assert "image.png" in paths
        assert "text.txt" in paths

        for change in changes:
            assert change.status == GitChangeStatus.ADDED


def test_get_changes_in_repo_ref_head_shows_only_uncommitted():
    """``ref='HEAD'`` 应该产生 git status 语义：工作树 vs HEAD。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 提交基线文件，以便 HEAD 存在。
        (Path(temp_dir) / "committed.txt").write_text("baseline")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'initial'", temp_dir)

        # 添加额外的提交。 如果没有 ref='HEAD'，这仍然会出现在变更集中（原始自动检测 +
        # 空树回退方案与空树进行比较）。 当 ref='HEAD' 时，它必须出现不。
        #
        (Path(temp_dir) / "second.txt").write_text("second commit")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'second'", temp_dir)

        # 现在创建一个未跟踪的文件 + 一个已修改的文件 vs HEAD。
        (Path(temp_dir) / "committed.txt").write_text("baseline modified")
        (Path(temp_dir) / "untracked.txt").write_text("new")

        changes = get_changes_in_repo(temp_dir, ref="HEAD")

        paths = {str(c.path) for c in changes}
        # 在 HEAD 提交的文件不得出现； 仅工作树发生变化。
        assert "second.txt" not in paths
        assert "committed.txt" in paths
        assert "untracked.txt" in paths


def test_get_changes_in_repo_invalid_ref_raises():
    """未解析的显式引用应引发 ``GitCommandError``。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "f.txt").write_text("hi")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'init'", temp_dir)

        with pytest.raises(GitCommandError):
            get_changes_in_repo(temp_dir, ref="definitely-not-a-real-ref")


def test_get_changes_in_repo_ref_head_on_empty_repo_returns_untracked_as_added():
    """``ref='HEAD'`` 在新初始化的存储库（无提交）上不得引发。

    重现新对话中的更改标签问题工作区运行时 ``git init``s the 工作区，the GUI 请求
    ``ref=HEAD`` 为了获取 git-status
    的语义，但 ``HEAD`` 没有解决。 未跟踪的文件应显示为 ADDED instead of bubbling up
    a ``GitCommandError``
    .
    """
    # 安排
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "untracked.txt").write_text("new")

        # 法案
        changes = get_changes_in_repo(temp_dir, ref="HEAD")

        # 断言
        assert changes == [
            GitChange(status=GitChangeStatus.ADDED, path=Path("untracked.txt"))
        ]


def test_get_changes_in_repo_ref_head_on_orphan_branch_returns_untracked_as_added():
    """``ref='HEAD'`` 在孤儿分支上（HEAD 未出生但其他分支
    有承诺）不得筹集。

    原始的空存储库修复使用 ``_repo_has_commits`` 来检测“任何地方都没有提交”并跳过
    ``rev-parse --verify HEAD^{commit}`` 步骤。 该检查在此处返回 ``True``（提交存在于
     ``main`` 上），因此如果没
    有额外的安全网，用户会看到相同的结果
    “更改”选项卡中的
    ``Git command failed: git --no-pager rev-parse --verify 'HEAD^{commit}'`` 400。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 在默认分支上进行提交，以便存储库“有提交”。
        (Path(temp_dir) / "committed.txt").write_text("on main")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'on main'", temp_dir)

        # 切换到孤立分支：HEAD 现在指向 refs/heads/orphan，该分支尚未作为提交存在。
        #
        run_bash_command("git checkout --orphan orphan", temp_dir)
        run_bash_command("git rm -rf --cached .", temp_dir)
        (Path(temp_dir) / "untracked.txt").write_text("new")

        # 行动/断言：不得提出 GitCommandError； 未跟踪的文件显示为已添加（镜像空存储库行
        # 为）。
        #
        changes = get_changes_in_repo(temp_dir, ref="HEAD")
        paths = {str(c.path) for c in changes}
        assert "untracked.txt" in paths


def test_get_changes_in_repo_invalid_non_head_ref_still_raises_after_fix():
    """``HEAD`` 回退方案不得吞并其他参考文献中的拼写错误。

    回归守卫新 ``except GitCommandError`` 中
    ``get_valid_ref``：仅当*覆盖*恰好为``"HEAD"``时才短路。 任何其他未解决的引用仍然
    必须引发错误（e.g. ``ref=mian``) 不
    会默默地呈现为“无更改”。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "f.txt").write_text("hi")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'init'", temp_dir)

        with pytest.raises(GitCommandError):
            get_changes_in_repo(temp_dir, ref="not-a-real-branch-name")


def test_get_git_changes_propagates_ref():
    """``get_git_changes`` 应该将 ref 传递给内部存储库查找。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "a.txt").write_text("a")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'init'", temp_dir)

        # 仅添加工作树。
        (Path(temp_dir) / "b.txt").write_text("b")

        changes = get_git_changes(temp_dir, ref="HEAD")
        paths = {str(c.path) for c in changes}
        assert paths == {"b.txt"}


def setup_cloned_repo(root: str) -> Path:
    """裸源（默认分支 ``main``），已提交 README，加上
    它的配置克隆 - 镜像存在跟踪引用和 ``origin/HEAD`` 的真实对话工作区。
    """
    origin = Path(root) / "origin.git"
    run_bash_command(f"git init --bare -b main {origin}", root)

    seed = Path(root) / "seed"
    seed.mkdir()
    run_bash_command("git init -b main", str(seed))
    run_bash_command("git config user.name 'Test User'", str(seed))
    run_bash_command("git config user.email 'test@example.com'", str(seed))
    (seed / "README.md").write_text("base")
    run_bash_command("git add .", str(seed))
    run_bash_command("git commit -m 'base'", str(seed))
    run_bash_command(f"git remote add origin {origin}", str(seed))
    run_bash_command("git push -u origin main", str(seed))

    clone = Path(root) / "clone"
    run_bash_command(f"git clone {origin} {clone}", root)
    run_bash_command("git config user.name 'Test User'", str(clone))
    run_bash_command("git config user.email 'test@example.com'", str(clone))
    return clone


def push_agent_branch(repo: Path) -> None:
    """使用一个已提交的文件创建 ``openhands/pr-branch`` 并推送它，
    将分支留在同步及其上游（PR 后状态）。"""
    run_bash_command("git checkout -b openhands/pr-branch", str(repo))
    (repo / "new.txt").write_text("pr change")
    run_bash_command("git add .", str(repo))
    run_bash_command("git commit -m 'agent pr work'", str(repo))
    run_bash_command("git push -u origin openhands/pr-branch", str(repo))


def test_get_changes_in_repo_committed_changes_stay_visible():
    """已提交但未推送的工作必须保持可见——Diff 视图用于
    智能体运行 ``git commit`` (APP-2205) 时变为空白。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        repo = setup_cloned_repo(temp_dir)
        (repo / "README.md").write_text("changed by agent")
        run_bash_command("git commit -am 'agent work'", str(repo))

        # 法案
        changes = get_changes_in_repo(repo)

        # 断言
        assert changes == [
            GitChange(status=GitChangeStatus.UPDATED, path=Path("README.md"))
        ]


def test_get_changes_in_repo_pushed_branch_shows_pr_diff():
    """完全推向上游的分支（PR流）必须与
    分叉点 - 将其与其自己的上游进行比较将使整个 PR 呈现为“无变化”。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        repo = setup_cloned_repo(temp_dir)
        push_agent_branch(repo)

        # 法案
        changes = get_changes_in_repo(repo)

        # 断言
        assert changes == [
            GitChange(status=GitChangeStatus.ADDED, path=Path("new.txt"))
        ]


def test_get_changes_in_repo_pushed_branch_with_tracked_edit_shows_only_edit():
    """跟踪工作树编辑使分支与自己的分支进行比较
    上游，因此预先存在的附加分支仅显示新编辑而不是其整个历史记录。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        repo = setup_cloned_repo(temp_dir)
        push_agent_branch(repo)
        (repo / "README.md").write_text("post-push edit")

        # 法案
        changes = get_changes_in_repo(repo)

        # 断言 - new.txt 已经在上游，因此仅显示编辑内容。
        assert changes == [
            GitChange(status=GitChangeStatus.UPDATED, path=Path("README.md"))
        ]


def test_get_changes_in_repo_untracked_file_does_not_hide_pushed_branch_diff():
    """未跟踪的文件永远不会出现在 ``git diff <ref>`` 中，因此它们不能
    对于基础选择来说，算作“脏”——杂散的临时文件不得重新隐藏完全推送的分支的工作。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        repo = setup_cloned_repo(temp_dir)
        push_agent_branch(repo)
        (repo / "scratch.log").write_text("junk")

        # 法案
        changes = get_changes_in_repo(repo)

        # 断言 — 分支的承诺工作仍然与分叉点不同； 未跟踪的文件本身作为附加内容出现。
        #
        changes_dict = {str(change.path): change.status for change in changes}
        assert changes_dict == {
            "new.txt": GitChangeStatus.ADDED,
            "scratch.log": GitChangeStatus.ADDED,
        }


def test_get_changes_in_repo_no_remote_worktree_shows_committed_changes():
    """GUI 的默认本地流：工作树分支从本地分叉出来
    ``main`` 在没有遥控器的存储库中。 提交的工作必须保持可见，而不是降级为整个存储库
    空树比较。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 安排
        repo = Path(temp_dir) / "repo"
        repo.mkdir()
        run_bash_command("git init -b main", str(repo))
        run_bash_command("git config user.name 'Test User'", str(repo))
        run_bash_command("git config user.email 'test@example.com'", str(repo))
        (repo / "app.txt").write_text("base")
        run_bash_command("git add .", str(repo))
        run_bash_command("git commit -m 'base'", str(repo))

        worktree = Path(temp_dir) / "worktree"
        run_bash_command(
            f"git worktree add -b openhands/conv1 {worktree} main", str(repo)
        )
        (worktree / "app.txt").write_text("changed by agent")
        run_bash_command("git commit -am 'agent work'", str(worktree))

        # 法案
        changes = get_changes_in_repo(worktree)

        # 断言
        assert changes == [
            GitChange(status=GitChangeStatus.UPDATED, path=Path("app.txt"))
        ]


def test_get_git_changes_keeps_paths_that_merely_share_a_nested_repo_prefix():
    """名为“foo”的嵌套存储库不得吞咽“foobar/”或“foo-config”。

    嵌套存储库过滤器比较路径祖先； 在字符串前缀上匹配时，会删除根仓库更改，这些更改的
    名称以嵌套仓库的名称开头，且这些更改会悄无声息地从结果中消失。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "README.md").write_text("base\n")
        run_bash_command("git add -A && git commit -m init", temp_dir)

        nested = Path(temp_dir) / "foo"
        nested.mkdir()
        setup_git_repo(str(nested))
        (nested / "nested.txt").write_text("nested\n")
        run_bash_command("git add -A && git commit -m init", str(nested))

        # 共享“foo”作为前缀但不在其中的根存储库更改
        (Path(temp_dir) / "foobar").mkdir()
        (Path(temp_dir) / "foobar" / "file.py").write_text("changed\n")
        (Path(temp_dir) / "foo-config.yaml").write_text("changed\n")
        (Path(temp_dir) / "README.md").write_text("changed\n")

        paths = {str(change.path) for change in get_git_changes(temp_dir)}

        assert "foobar/file.py" in paths
        assert "foo-config.yaml" in paths
        assert "README.md" in paths


def test_get_git_changes_still_excludes_paths_inside_a_nested_repo():
    """过滤器必须继续完成其工作：真正的嵌套更改将被排除在外。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "README.md").write_text("base\n")
        run_bash_command("git add -A && git commit -m init", temp_dir)

        nested = Path(temp_dir) / "foo"
        nested.mkdir()
        setup_git_repo(str(nested))
        (nested / "nested.txt").write_text("nested\n")
        run_bash_command("git add -A && git commit -m init", str(nested))
        (nested / "nested.txt").write_text("changed in nested\n")

        changes = get_git_changes(temp_dir)
        nested_entries = [c for c in changes if str(c.path) == "foo/nested.txt"]

        # 由嵌套存储库而不是父级报告一次。
        assert len(nested_entries) == 1


def test_get_git_changes_lists_repo_below_non_repo_directory():
    """保存存储库的普通目录列出了该存储库的更改。

    这是基于仓库的对话的``{base}/{repo}``布局：基础不是仓库本身，因此其更改必须来自其
    下方的仓库，带有目录名。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        repo = Path(temp_dir) / "proj"
        repo.mkdir()
        setup_git_repo(str(repo))
        (repo / "README.md").write_text("hello\n")
        run_bash_command("git add -A && git commit -m init", str(repo))
        (repo / "README.md").write_text("hello\nedit\n")
        (repo / "notes.txt").write_text("note\n")

        changes = get_git_changes(temp_dir, ref="HEAD")

        assert [(c.status, c.path.as_posix()) for c in changes] == [
            (GitChangeStatus.UPDATED, "proj/README.md"),
            (GitChangeStatus.ADDED, "proj/notes.txt"),
        ]


def test_get_git_changes_non_repo_without_repo_below_still_raises():
    """一个普通目录，除了下面有一个损坏的 ``.git`` 之外什么都没有，这不是存储库。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / "plain.txt").write_text("plain\n")
        broken = Path(temp_dir) / "broken"
        broken.mkdir()
        (broken / ".git").write_text("gitdir: /path/that/does/not/exist\n")

        with pytest.raises(GitRepositoryError):
            get_git_changes(temp_dir)
