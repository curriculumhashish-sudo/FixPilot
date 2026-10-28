"""测试 write_file 工具。"""

from pathlib import Path

from openhands.tools.gemini.write_file.definition import WriteFileAction, WriteFileTool
from openhands.tools.gemini.write_file.impl import WriteFileExecutor


def test_write_file_create_new(tmp_path):
    """测试创建一个新文件。"""
    executor = WriteFileExecutor(workspace_root=str(tmp_path))
    action = WriteFileAction(file_path="new.txt", content="hello world\n")
    obs = executor(action)

    assert not obs.is_error
    assert obs.is_new_file
    assert obs.file_path == str(tmp_path / "new.txt")
    assert obs.old_content is None
    assert obs.new_content == "hello world\n"

    # 验证文件已创建
    assert (tmp_path / "new.txt").exists()
    assert (tmp_path / "new.txt").read_text() == "hello world\n"


def test_write_file_overwrite_existing(tmp_path):
    """测试覆盖现有文件。"""
    # 创建现有文件
    test_file = tmp_path / "existing.txt"
    test_file.write_text("old content\n")

    executor = WriteFileExecutor(workspace_root=str(tmp_path))
    action = WriteFileAction(file_path="existing.txt", content="new content\n")
    obs = executor(action)

    assert not obs.is_error
    assert not obs.is_new_file
    assert obs.old_content == "old content\n"
    assert obs.new_content == "new content\n"

    # 验证文件是否被覆盖
    assert test_file.read_text() == "new content\n"


def test_write_file_create_directories(tmp_path):
    """测试创建父目录。"""
    executor = WriteFileExecutor(workspace_root=str(tmp_path))
    action = WriteFileAction(file_path="subdir/nested/file.txt", content="content\n")
    obs = executor(action)

    assert not obs.is_error
    assert obs.is_new_file

    # 验证目录和文件已创建
    assert (tmp_path / "subdir" / "nested" / "file.txt").exists()
    assert (tmp_path / "subdir" / "nested" / "file.txt").read_text() == "content\n"


def test_write_file_directory_error(tmp_path):
    """测试写入目录路径会返回错误。"""
    # 创建目录
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()

    executor = WriteFileExecutor(workspace_root=str(tmp_path))
    action = WriteFileAction(file_path="testdir", content="content\n")
    obs = executor(action)

    assert obs.is_error
    assert "directory" in obs.text.lower()


def test_write_file_absolute_path(tmp_path):
    """测试用绝对路径编写。"""
    test_file = tmp_path / "test.txt"

    executor = WriteFileExecutor(workspace_root=str(tmp_path))
    action = WriteFileAction(file_path=str(test_file), content="content\n")
    obs = executor(action)

    assert not obs.is_error
    assert test_file.exists()
    assert test_file.read_text() == "content\n"


def test_write_file_empty_content(tmp_path):
    """测试写空内容。"""
    executor = WriteFileExecutor(workspace_root=str(tmp_path))
    action = WriteFileAction(file_path="empty.txt", content="")
    obs = executor(action)

    assert not obs.is_error
    assert obs.is_new_file
    assert (tmp_path / "empty.txt").exists()
    assert (tmp_path / "empty.txt").read_text() == ""


def test_declared_resources_locks_on_file_path(fake_conv_state):
    """declared_resources 返回用于每个文件锁定的文件路径密钥。"""
    tool = WriteFileTool.create(conv_state=fake_conv_state)[0]
    absolute_path = Path(fake_conv_state.workspace.working_dir) / "a" / "b.py"
    action = WriteFileAction(file_path=str(absolute_path), content="x")
    resources = tool.declared_resources(action)
    assert resources.declared is True
    assert len(resources.keys) == 1
    assert resources.keys[0] == f"file:{absolute_path.resolve()}"


def test_declared_resources_different_files_different_keys(fake_conv_state):
    """不同的文件路径产生不同的资源密钥。"""
    tool = WriteFileTool.create(conv_state=fake_conv_state)[0]
    a = tool.declared_resources(WriteFileAction(file_path="/a.py", content="x"))
    b = tool.declared_resources(WriteFileAction(file_path="/b.py", content="x"))
    assert a.keys != b.keys


def test_declared_resources_relative_path_resolves_against_workspace(fake_conv_state):
    """相对路径必须针对 workspace_root 进行解析，而不是针对 CWD 进行解析。"""
    tool = WriteFileTool.create(conv_state=fake_conv_state)[0]
    workspace = fake_conv_state.workspace.working_dir
    resources = tool.declared_resources(
        WriteFileAction(file_path="src/foo.py", content="x")
    )
    assert resources.keys[0] == f"file:{(Path(workspace) / 'src' / 'foo.py').resolve()}"
