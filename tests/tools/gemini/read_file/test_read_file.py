"""测试 read_file 工具。"""

from pathlib import Path

from openhands.tools.gemini.read_file.definition import ReadFileAction, ReadFileTool
from openhands.tools.gemini.read_file.impl import ReadFileExecutor


def test_read_file_basic(tmp_path):
    """测试读取基本文件。"""
    # 创建测试文件
    test_file = tmp_path / "test.txt"
    test_file.write_text("line 1\nline 2\nline 3\n")

    # 执行read_file
    executor = ReadFileExecutor(workspace_root=str(tmp_path))
    action = ReadFileAction(file_path="test.txt")
    obs = executor(action)

    assert not obs.is_error
    assert obs.file_path == str(test_file)
    assert "line 1" in obs.file_content
    assert "line 2" in obs.file_content
    assert "line 3" in obs.file_content
    assert not obs.is_truncated


def test_read_file_with_offset(tmp_path):
    """测试读取带有偏移量的文件。"""
    # 创建一个包含多行的测试文件
    test_file = tmp_path / "test.txt"
    lines = [f"line {i}\n" for i in range(1, 21)]
    test_file.write_text("".join(lines))

    # 带偏移量读取
    executor = ReadFileExecutor(workspace_root=str(tmp_path))
    action = ReadFileAction(file_path="test.txt", offset=10, limit=5)
    obs = executor(action)

    assert not obs.is_error
    assert "line 11" in obs.file_content
    assert "line 15" in obs.file_content
    assert "line 10" not in obs.file_content
    assert "line 16" not in obs.file_content


def test_read_file_truncation(tmp_path):
    """测试大文件是否被截断。"""
    # 创建一个大文件
    test_file = tmp_path / "large.txt"
    lines = [f"line {i}\n" for i in range(1, 2000)]
    test_file.write_text("".join(lines))

    # 无限制读取（应应用默认 MAX_LINES_PER_READ）
    executor = ReadFileExecutor(workspace_root=str(tmp_path))
    action = ReadFileAction(file_path="large.txt")
    obs = executor(action)

    assert not obs.is_error
    assert obs.is_truncated
    assert obs.total_lines == 1999
    assert obs.lines_shown is not None


def test_read_file_not_found(tmp_path):
    """测试读取不存在的文件。"""
    executor = ReadFileExecutor(workspace_root=str(tmp_path))
    action = ReadFileAction(file_path="nonexistent.txt")
    obs = executor(action)

    assert obs.is_error
    assert "not found" in obs.text.lower()


def test_read_file_directory(tmp_path):
    """测试读取目录会返回错误。"""
    # 创建目录
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()

    executor = ReadFileExecutor(workspace_root=str(tmp_path))
    action = ReadFileAction(file_path="testdir")
    obs = executor(action)

    assert obs.is_error
    assert "directory" in obs.text.lower()


def test_read_file_absolute_path(tmp_path):
    """使用绝对路径测试读取。"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content\n")

    executor = ReadFileExecutor(workspace_root=str(tmp_path))
    action = ReadFileAction(file_path=str(test_file))
    obs = executor(action)

    assert not obs.is_error
    assert "content" in obs.file_content


def test_read_file_offset_beyond_length(tmp_path):
    """测试读取偏移量超出文件长度。"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("line 1\nline 2\n")

    executor = ReadFileExecutor(workspace_root=str(tmp_path))
    action = ReadFileAction(file_path="test.txt", offset=100)
    obs = executor(action)

    assert obs.is_error
    assert "beyond" in obs.text.lower()


def test_declared_resources_locks_on_file_path(fake_conv_state):
    """declared_resources 返回用于每个文件锁定的文件路径密钥。"""
    tool = ReadFileTool.create(conv_state=fake_conv_state)[0]
    absolute_path = Path(fake_conv_state.workspace.working_dir) / "a" / "b.py"
    action = ReadFileAction(file_path=str(absolute_path))
    resources = tool.declared_resources(action)
    assert resources.declared is True
    assert len(resources.keys) == 1
    assert resources.keys[0] == f"file:{absolute_path.resolve()}"


def test_declared_resources_different_files_different_keys(fake_conv_state):
    """不同的文件路径产生不同的资源密钥。"""
    tool = ReadFileTool.create(conv_state=fake_conv_state)[0]
    a = tool.declared_resources(ReadFileAction(file_path="/a.py"))
    b = tool.declared_resources(ReadFileAction(file_path="/b.py"))
    assert a.keys != b.keys


def test_declared_resources_relative_path_resolves_against_workspace(fake_conv_state):
    """相对路径必须针对 workspace_root 进行解析，而不是针对 CWD 进行解析。"""
    tool = ReadFileTool.create(conv_state=fake_conv_state)[0]
    workspace = fake_conv_state.workspace.working_dir
    resources = tool.declared_resources(ReadFileAction(file_path="src/foo.py"))
    assert resources.keys[0] == f"file:{(Path(workspace) / 'src' / 'foo.py').resolve()}"
