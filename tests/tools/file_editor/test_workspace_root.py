from pathlib import Path

import pytest

from openhands.tools.file_editor.editor import FileEditor
from openhands.tools.file_editor.exceptions import (
    EditorToolParameterInvalidError,
)


def test_workspace_root_as_cwd(tmp_path):
    """测试 workspace_root 是否用作当前工作目录
    路径建议。"""
    # 创建工作区根
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    # 在工作区根目录中创建一个文件
    test_file = workspace_root / "test.txt"
    test_file.write_text("This is a test file")

    # 使用 workspace_root 初始化编辑器
    editor = FileEditor(workspace_root=str(workspace_root))

    # 测试相对路径建议是否使用 workspace_root
    relative_path = "test.txt"
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        editor(command="view", path=relative_path)

    error_message = str(exc_info.value.message)
    assert "The path should be an absolute path" in error_message
    assert "Maybe you meant" in error_message

    # 从错误消息中提取建议的路径
    suggested_path = error_message.split("Maybe you meant ")[1].strip("?")
    assert Path(suggested_path).is_absolute()
    assert str(workspace_root) in suggested_path

    # 使用不存在的文件进行测试
    non_existent_path = "non_existent.txt"
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        editor(command="view", path=non_existent_path)

    error_message = str(exc_info.value.message)
    assert "The path should be an absolute path" in error_message
    assert "Maybe you meant" not in error_message


def test_relative_workspace_root_do_not_raises_error(tmp_path, monkeypatch):
    """测试亲戚 workspace_root 引发 ValueError。"""
    # 设置目录结构
    current_dir = tmp_path / "current_dir"
    current_dir.mkdir()

    # 更改到当前目录
    monkeypatch.chdir(current_dir)

    # 使用相对的 workspace_root 初始化编辑器不应引发 ValueError
    editor = FileEditor(workspace_root="workspace")
    assert editor._cwd == str(current_dir / "workspace")


def test_suggestion_when_no_workspace_root(tmp_path, monkeypatch):
    """测试未提供 workspace_root 时是否不提出路径建议。"""
    # 在当前目录下创建临时文件
    current_dir = tmp_path / "current_dir"
    current_dir.mkdir()
    test_file = current_dir / "test.txt"
    test_file.write_text("This is a test file")

    # 将当前目录设置为我们的临时目录
    monkeypatch.chdir(current_dir)

    # 初始化不带 workspace_root 的编辑器
    editor = FileEditor()

    # 现有文件应该存在测试路径建议
    relative_path = "test.txt"
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        editor(command="view", path=relative_path)

    error_message = str(exc_info.value.message)
    assert "The path should be an absolute path" in error_message
    assert "Maybe you meant" in error_message
    assert str(current_dir) in error_message

    # 使用不存在的文件进行测试（也应该没有建议）
    non_existent_path = "non_existent.txt"
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        editor(command="view", path=non_existent_path)

    error_message = str(exc_info.value.message)
    assert "The path should be an absolute path" in error_message
    assert "Maybe you meant" not in error_message
