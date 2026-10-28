"""测试文件编辑器中的错误处理。"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from openhands.tools.file_editor.editor import FileEditor
from openhands.tools.file_editor.impl import file_editor

from .conftest import assert_error_result


def test_validation_error_formatting(tmp_path):
    """测试输出中的验证错误格式是否正确。"""
    missing_file = tmp_path / "nonexistent" / "file.txt"
    result = file_editor(
        command="view",
        path=str(missing_file),
    )
    assert_error_result(result)
    assert result.is_error and "does not exist" in result.text

    # 非视图命令的测试目录验证
    result = file_editor(
        command="str_replace",
        path=str(tmp_path),
        old_str="something",
        new_str="new",
    )
    assert_error_result(result)
    assert result.is_error and "directory and only the `view` command" in result.text


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only regression test")
def test_create_rejects_foreign_platform_absolute_paths(tmp_path, monkeypatch):
    """Create 应拒绝在此主机上不是绝对的绝对路径语法。"""
    monkeypatch.chdir(tmp_path)
    result = file_editor(command="create", path=r"C:\foo", file_text="hello")

    assert_error_result(result)
    assert "absolute path" in result.text
    assert not (tmp_path / r"C:\foo").exists()


def test_str_replace_error_handling(temp_file):
    """测试 str_replace 命令中的错误处理。"""
    # 创建测试文件
    content = "line 1\nline 2\nline 3\n"
    with open(temp_file, "w") as f:
        f.write(content)

    # 测试不存在的字符串
    result = file_editor(
        command="str_replace",
        path=temp_file,
        old_str="nonexistent",
        new_str="something",
    )
    assert_error_result(result)
    assert result.is_error and "did not appear verbatim" in result.text

    # 测试多次出现
    with open(temp_file, "w") as f:
        f.write("line\nline\nother")

    result = file_editor(
        command="str_replace",
        path=temp_file,
        old_str="line",
        new_str="new_line",
    )
    assert_error_result(result)
    assert result.is_error and "Multiple occurrences" in result.text
    assert result.is_error and "lines [1, 2]" in result.text


def test_view_range_validation(temp_file):
    """测试 view_range 参数的验证。"""
    # 创建测试文件
    content = "line 1\nline 2\nline 3\n"
    with open(temp_file, "w") as f:
        f.write(content)

    # 测试无效的范围格式
    result = file_editor(
        command="view",
        path=temp_file,
        view_range=[1],  # 应该是[开始，结束]
    )
    assert_error_result(result)
    assert result.is_error and "should be a list of two integers" in result.text

    # 测试越界范围：应夹紧到文件末尾并显示警告
    result = file_editor(
        command="view",
        path=temp_file,
        view_range=[1, 10],  # 文件只有 3 行
    )
    # 这应该会成功，但会显示警告
    assert not result.is_error
    assert (
        "NOTE: We only show up to 3 since there're only 3 lines in this file."
        in result.text
    )

    # 测试无效的范围顺序
    result = file_editor(
        command="view",
        path=temp_file,
        view_range=[3, 1],  # 开始前结束
    )
    assert_error_result(result)
    assert result.is_error and "should be greater than or equal to" in result.text


def test_insert_validation(temp_file):
    """在插入命令中测试验证。"""
    # 创建测试文件
    content = "line 1\nline 2\nline 3\n"
    with open(temp_file, "w") as f:
        f.write(content)

    # 测试插入负线
    result = file_editor(
        command="insert",
        path=temp_file,
        insert_line=-1,
        new_str="new line",
    )
    assert_error_result(result)
    assert result.is_error and "should be within the range" in result.text

    # 测试超出文件长度插入操作
    result = file_editor(
        command="insert",
        path=temp_file,
        insert_line=10,
        new_str="new line",
    )
    assert_error_result(result)
    assert result.is_error and "should be within the range" in result.text


def test_undo_validation(temp_file):
    """测试 undo_edit 验证。"""
    # 创建测试文件
    content = "line 1\nline 2\nline 3\n"
    with open(temp_file, "w") as f:
        f.write(content)

    # 尝试撤消而不进行任何先前的编辑
    result = file_editor(
        command="undo_edit",
        path=temp_file,
    )
    assert_error_result(result)
    assert result.is_error and "No edit history found" in result.text


def test_view_directory_permission_error_returns_error_observation():
    """目录视图应在 PermissionError 上返回错误观测结果。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        editor = FileEditor()
        with patch.object(
            editor,
            "_count_hidden_children",
            side_effect=PermissionError("denied"),
        ):
            result = editor.view(path)
        assert result.is_error
        assert "denied" in result.text


def test_view_subdirectory_permission_error_skips_inaccessible_dir():
    """应静默跳过子目录权限错误。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        sub = path / "sub"
        sub.mkdir()
        (path / "visible.txt").write_text("hello")

        # 在子目录上模拟 iterdir 并抛出 PermissionError。
        original_iterdir = Path.iterdir

        def patched_iterdir(self: Path):
            if self == sub:
                raise PermissionError("denied")
            return original_iterdir(self)

        editor = FileEditor()
        with patch.object(Path, "iterdir", patched_iterdir):
            result = editor.view(path)
        assert not result.is_error
        assert "visible.txt" in result.text
