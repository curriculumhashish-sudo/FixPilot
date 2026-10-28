"""使用临时目录和 bash 命令测试 git_diff.py 功能。"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from openhands.sdk.git.git_diff import get_closest_git_repo, get_git_diff
from openhands.sdk.git.models import GitDiff


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


def run_in_directory(temp_dir: str, func, *args, **kwargs):
    """在特定目录中运行函数的帮助程序。"""
    original_cwd = os.getcwd()
    try:
        os.chdir(temp_dir)
        return func(*args, **kwargs)
    finally:
        os.chdir(original_cwd)


def test_get_git_diff_new_file():
    """使用新文件测试 get_git_diff。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建一个新文件
        test_file = Path(temp_dir) / "new_file.txt"
        test_content = "This is a new file\nwith multiple lines\nof content."
        test_file.write_text(test_content)

        diff = run_in_directory(temp_dir, get_git_diff, "new_file.txt")

        assert isinstance(diff, GitDiff)
        assert diff.modified == test_content
        assert diff.original == ""  # 新文件的空字符串


def test_get_git_diff_modified_file():
    """使用修改后的文件测试 get_git_diff。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建并提交初始文件
        test_file = Path(temp_dir) / "modified_file.txt"
        original_content = "Original content\nLine 2\nLine 3"
        test_file.write_text(original_content)

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 修改文件
        modified_content = "Modified content\nLine 2 changed\nLine 3\nNew line 4"
        test_file.write_text(modified_content)

        diff = run_in_directory(temp_dir, get_git_diff, "modified_file.txt")

        assert isinstance(diff, GitDiff)
        assert diff.modified == modified_content
        # 没有与 HEAD 进行远程比较的存储库，因此提交的内容是差异的原始部分。
        #
        assert diff.original == original_content


def test_get_git_diff_deleted_file():
    """工作树删除的文件与其基本文本相对于 '' 进行比较。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建并提交初始文件
        test_file = Path(temp_dir) / "deleted_file.txt"
        original_content = "This file will be deleted\nLine 2\nLine 3"
        test_file.write_text(original_content)

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 删除文件
        os.remove(test_file)

        diff = run_in_directory(temp_dir, get_git_diff, "deleted_file.txt")

        assert diff.original == original_content
        assert diff.modified == ""


def test_get_git_diff_missing_path_that_is_a_directory_at_base():
    """作为基础目录的缺失路径不是文件差异。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        nested = Path(temp_dir) / "pkg"
        nested.mkdir()
        (nested / "a.txt").write_text("a")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)
        run_bash_command("rm -rf pkg", temp_dir)

        from openhands.sdk.git.exceptions import GitPathError

        with pytest.raises(GitPathError, match="File does not exist"):
            run_in_directory(temp_dir, get_git_diff, "pkg")
        with pytest.raises(GitPathError, match="File does not exist"):
            run_in_directory(temp_dir, get_git_diff, "never_existed.txt")


def test_get_git_diff_deleted_file_too_large():
    """已删除文件的基本文本保持相同的大小上限。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        big = Path(temp_dir) / "big.txt"
        big.write_text("a" * (1024 * 1024 + 1))
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)
        os.remove(big)

        from openhands.sdk.git.exceptions import GitPathError

        with pytest.raises(GitPathError, match="File too large"):
            run_in_directory(temp_dir, get_git_diff, "big.txt")


def test_get_git_diff_missing_file_outside_repo():
    """任何存储库之外的丢失路径仍会报告丢失文件。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        from openhands.sdk.git.exceptions import GitPathError

        with pytest.raises(GitPathError, match="File does not exist"):
            run_in_directory(temp_dir, get_git_diff, "nope.txt")


def test_get_git_diff_nested_path():
    """使用嵌套目录中的文件测试 get_git_diff。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建嵌套目录结构
        nested_dir = Path(temp_dir) / "src" / "utils"
        nested_dir.mkdir(parents=True)

        # 创建并提交初始文件
        test_file = nested_dir / "helper.py"
        original_content = "def helper():\n    return 'original'"
        test_file.write_text(original_content)

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 修改文件
        modified_content = (
            "def helper():\n    return 'modified'\n\ndef new_function():\n    pass"
        )
        test_file.write_text(modified_content)

        diff = run_in_directory(temp_dir, get_git_diff, "src/utils/helper.py")

        assert isinstance(diff, GitDiff)
        assert diff.modified == modified_content
        # 没有与 HEAD 进行远程比较的存储库，因此提交的内容是差异的原始部分。
        #
        assert diff.original == original_content


def test_get_git_diff_no_repository():
    """使用非 git 目录测试 get_git_diff。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 不要初始化 git repo
        test_file = Path(temp_dir) / "file.txt"
        test_file.write_text("Content")

        from openhands.sdk.git.exceptions import GitRepositoryError

        with pytest.raises(GitRepositoryError):
            run_in_directory(temp_dir, get_git_diff, "file.txt")


def test_get_git_diff_nonexistent_file():
    """使用不存在的文件测试 get_git_diff。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        from openhands.sdk.git.exceptions import GitPathError

        with pytest.raises(GitPathError, match="File does not exist"):
            run_in_directory(temp_dir, get_git_diff, "nonexistent.txt")


def test_get_closest_git_repo():
    """测试 get_closest_git_repo 辅助函数。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建嵌套目录结构
        nested_dir = Path(temp_dir) / "src" / "utils"
        nested_dir.mkdir(parents=True)

        # 测试从嵌套目录中查找 git repo
        git_repo = get_closest_git_repo(nested_dir)
        # 比较已解析的路径以避免 macOS 上的符号链接差异
        # 示例：/var 是 /private/var 的符号链接
        assert git_repo is not None
        assert git_repo.resolve() == Path(temp_dir).resolve()

        # 使用非 git 目录进行测试
        with tempfile.TemporaryDirectory() as non_git_dir:
            git_repo = get_closest_git_repo(Path(non_git_dir))
            assert git_repo is None


def test_git_diff_model_properties():
    """测试 GitDiff 模型属性和序列化。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建并提交初始文件
        test_file = Path(temp_dir) / "model_test.py"
        original_content = "# Original model test"
        test_file.write_text(original_content)

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 修改文件
        modified_content = "# Modified model test\nprint('Hello')"
        test_file.write_text(modified_content)

        diff = run_in_directory(temp_dir, get_git_diff, "model_test.py")

        # 测试模型属性
        assert isinstance(diff, GitDiff)
        assert isinstance(diff.modified, str)
        assert isinstance(diff.original, str)
        assert diff.modified == modified_content
        # 没有与 HEAD 进行远程比较的存储库，因此提交的内容是差异的原始部分。
        #
        assert diff.original == original_content

        # 测试序列化
        diff_dict = diff.model_dump()
        assert "modified" in diff_dict
        assert "original" in diff_dict
        assert diff_dict["modified"] == modified_content
        assert diff_dict["original"] == original_content


def test_git_diff_with_empty_file():
    """使用空文件测试 git diff。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建并提交空文件
        test_file = Path(temp_dir) / "empty.txt"
        test_file.write_text("")

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 将内容添加到文件中
        new_content = "Now has content"
        test_file.write_text(new_content)

        diff = run_in_directory(temp_dir, get_git_diff, "empty.txt")

        assert isinstance(diff, GitDiff)
        assert diff.modified == new_content
        assert diff.original == ""


def test_git_diff_with_special_characters():
    """使用包含特殊字符的文件测试 git diff。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建带有特殊字符的文件
        test_file = Path(temp_dir) / "special_chars.txt"
        original_content = (
            "Original: àáâãäå\n中文\n🚀 emoji\n\"quotes\" and 'apostrophes'"
        )
        test_file.write_text(original_content, encoding="utf-8")

        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        # 修改更多特殊字符
        modified_content = (
            "Modified: àáâãäå\n中文修改\n🎉 new emoji\n"
            "\"new quotes\" and 'new apostrophes'\n\ttabs and\nlines"
        )
        test_file.write_text(modified_content, encoding="utf-8")

        diff = run_in_directory(temp_dir, get_git_diff, "special_chars.txt")

        assert isinstance(diff, GitDiff)
        assert diff.modified == modified_content
        # 没有与 HEAD 进行远程比较的存储库，因此提交的内容是差异的原始部分。
        #
        assert diff.original == original_content


def test_git_diff_large_file_error():
    """使用太大的文件测试 git diff。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        # 创建大于 MAX_FILE_SIZE_FOR_GIT_DIFF (1MB) 的文件
        test_file = Path(temp_dir) / "large_file.txt"
        large_content = "x" * (1024 * 1024 + 1)  # 1MB + 1 字节
        test_file.write_text(large_content)

        from openhands.sdk.git.exceptions import GitPathError

        with pytest.raises(GitPathError):
            run_in_directory(temp_dir, get_git_diff, "large_file.txt")


def test_get_git_diff_ref_head_compares_against_latest_commit():
    """``ref='HEAD'`` 应该与最新提交进行比较，而不是与远程提交进行比较。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        target = Path(temp_dir) / "file.txt"

        # 第一次提交（这将是默认行为中空树回退方案的“原始”）。
        #
        target.write_text("v1\n")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'v1'", temp_dir)

        # 第二次提交变为 HEAD。
        target.write_text("v2\n")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'v2'", temp_dir)

        # 工作树编辑（未提交）。
        target.write_text("v3\n")

        diff = run_in_directory(temp_dir, get_git_diff, "file.txt", ref="HEAD")

        assert isinstance(diff, GitDiff)
        # original = HEAD's contents = v2 (NOT v1).
        assert diff.original == "v2"
        # modified = working-tree contents = v3.
        assert diff.modified == "v3"


def test_get_git_diff_invalid_ref_raises():
    """应该引发未解析的显式引用。"""
    from openhands.sdk.git.exceptions import GitCommandError

    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)
        (Path(temp_dir) / "f.txt").write_text("hi")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'init'", temp_dir)

        with pytest.raises(GitCommandError):
            run_in_directory(temp_dir, get_git_diff, "f.txt", ref="not-a-real-ref")


def test_get_git_diff_committed_branch_change_diffs_against_fork_point():
    """在分支上提交的更改必须与分支的分叉不同
    point — 匹配更改列表。 相反，与 HEAD 进行比较会将提交的内容呈现为空差异 (APP-2205
    )。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # 在 `main` 上安排 — 存储库，然后是具有已提交更改的分支。
        run_bash_command("git init -b main", temp_dir)
        run_bash_command("git config user.name 'Test User'", temp_dir)
        run_bash_command("git config user.email 'test@example.com'", temp_dir)
        target = Path(temp_dir) / "file.txt"
        target.write_text("base")
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'base'", temp_dir)
        run_bash_command("git checkout -b openhands/conv1", temp_dir)
        target.write_text("changed by agent")
        run_bash_command("git commit -am 'agent work'", temp_dir)

        # 法案
        diff = run_in_directory(temp_dir, get_git_diff, "file.txt")

        # 断言 — 原始内容是分叉点（主要）内容。
        assert diff.original == "base"
        assert diff.modified == "changed by agent"


@pytest.mark.parametrize(
    "content",
    [
        "  indented line\nbody\n",
        "body\n\n\n",
        "\n\nbody\n",
        "one\r\ntwo\r\n",
    ],
    ids=["leading-indent", "trailing-blank-lines", "leading-blank-lines", "crlf"],
)
def test_get_git_diff_unchanged_file_has_identical_sides(content):
    """未更改的文件在差异两侧保留其边缘空白。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        setup_git_repo(temp_dir)

        test_file = Path(temp_dir) / "unchanged.txt"
        test_file.write_bytes(content.encode())
        run_bash_command("git add .", temp_dir)
        run_bash_command("git commit -m 'Initial commit'", temp_dir)

        diff = run_in_directory(temp_dir, get_git_diff, "unchanged.txt", ref="HEAD")

        assert diff.original == diff.modified
        assert diff.modified == "\n".join(content.splitlines())
