import tempfile
from pathlib import Path

import pytest

from openhands.sdk.tool.schema import TextContent
from openhands.tools.file_editor.definition import (
    FileEditorObservation,
)
from openhands.tools.file_editor.editor import FileEditor


@pytest.fixture
def temp_file():
    """创建一个临时文件用于测试。"""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        path = Path(f.name)

    try:
        yield path
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


@pytest.fixture
def temp_dir():
    """创建一个临时目录用于测试。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def editor():
    """创建一个 FileEditor 实例用于测试。"""
    return FileEditor()


@pytest.fixture
def editor_with_test_file(tmp_path):
    """使用测试文件创建 FileEditor 实例。"""
    editor = FileEditor()
    test_file = tmp_path / "test.txt"
    test_file.write_text("This is a test file.\nThis file is for testing purposes.")
    return editor, test_file


@pytest.fixture
def editor_python_file_with_tabs(tmp_path):
    """使用包含选项卡的 Python 测试文件创建 FileEditor 实例。"""
    editor = FileEditor()
    test_file = tmp_path / "test.py"
    test_file.write_text('def test():\n\tprint("Hello, World!")')
    return editor, test_file


def assert_successful_result(
    result: FileEditorObservation, expected_path: str | None = None
):
    """断言结果成功（无错误）。"""
    assert isinstance(result, FileEditorObservation)
    assert not result.is_error
    if expected_path:
        assert result.path == expected_path


def assert_error_result(
    result: FileEditorObservation, expected_error_substring: str | None = None
):
    """断言结果包含错误。"""
    assert isinstance(result, FileEditorObservation)
    assert result.is_error
    if expected_error_substring:
        content_text = (
            result.content
            if isinstance(result.content, str)
            else "".join([c.text for c in result.content if isinstance(c, TextContent)])
        )
        assert expected_error_substring in content_text


def create_test_file(path: Path, content: str):
    """帮助程序创建具有给定内容的测试文件。"""
    path.write_text(content)
    return path
