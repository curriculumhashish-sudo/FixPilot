"""测试编辑工具。"""

from pathlib import Path

from openhands.tools.gemini.edit.definition import EditAction, EditTool
from openhands.tools.gemini.edit.impl import EditExecutor


def test_edit_basic_replacement(tmp_path):
    """测试基本查找/替换。"""
    # 创建测试文件
    test_file = tmp_path / "test.py"
    test_file.write_text("def foo():\n    return 'old'\n")

    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(file_path="test.py", old_string="'old'", new_string="'new'")
    obs = executor(action)

    assert not obs.is_error
    assert not obs.is_new_file
    assert obs.replacements_made == 1
    assert test_file.read_text() == "def foo():\n    return 'new'\n"


def test_edit_multiple_replacements(tmp_path):
    """测试替换多次出现的情况。"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("foo bar foo baz foo\n")

    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(
        file_path="test.txt",
        old_string="foo",
        new_string="qux",
        expected_replacements=3,
    )
    obs = executor(action)

    assert not obs.is_error
    assert obs.replacements_made == 3
    assert test_file.read_text() == "qux bar qux baz qux\n"


def test_edit_mismatch_expected_count(tmp_path):
    """当替换计数与预期不匹配时出现测试错误。"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("foo bar foo\n")

    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(
        file_path="test.txt",
        old_string="foo",
        new_string="qux",
        expected_replacements=1,
    )
    obs = executor(action)

    assert obs.is_error
    assert "expected 1" in obs.text.lower()
    assert "found 2" in obs.text.lower()


def test_edit_create_new_file(tmp_path):
    """测试创建一个空 old_string 的新文件。"""
    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(
        file_path="new.py", old_string="", new_string="print('hello')\n"
    )
    obs = executor(action)

    assert not obs.is_error
    assert obs.is_new_file
    assert obs.replacements_made == 1

    # 验证文件已创建
    test_file = tmp_path / "new.py"
    assert test_file.exists()
    assert test_file.read_text() == "print('hello')\n"


def test_edit_create_existing_file_error(tmp_path):
    """尝试创建已存在的文件时出现测试错误。"""
    # 创建现有文件
    test_file = tmp_path / "existing.py"
    test_file.write_text("old content\n")

    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(
        file_path="existing.py", old_string="", new_string="new content\n"
    )
    obs = executor(action)

    assert obs.is_error
    assert "already exists" in obs.text.lower()


def test_edit_string_not_found(tmp_path):
    """未找到 old_string 时测试错误。"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world\n")

    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(
        file_path="test.txt", old_string="goodbye", new_string="farewell"
    )
    obs = executor(action)

    assert obs.is_error
    assert "could not find" in obs.text.lower()
    assert "0 occurrences" in obs.text.lower()


def test_edit_identical_strings(tmp_path):
    """当old_string和new_string相同时测试错误。"""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world\n")

    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(file_path="test.txt", old_string="hello", new_string="hello")
    obs = executor(action)

    assert obs.is_error
    assert "no changes" in obs.text.lower()
    assert "identical" in obs.text.lower()


def test_edit_file_not_found(tmp_path):
    """文件不存在时测试错误。"""
    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(file_path="nonexistent.txt", old_string="old", new_string="new")
    obs = executor(action)

    assert obs.is_error
    assert "not found" in obs.text.lower()


def test_edit_multiline_replacement(tmp_path):
    """测试替换多行文本。"""
    test_file = tmp_path / "test.py"
    test_file.write_text("def foo():\n    print('old')\n    return 1\n")

    executor = EditExecutor(workspace_root=str(tmp_path))
    action = EditAction(
        file_path="test.py",
        old_string="    print('old')\n    return 1",
        new_string="    print('new')\n    return 2",
    )
    obs = executor(action)

    assert not obs.is_error
    assert obs.replacements_made == 1
    assert test_file.read_text() == "def foo():\n    print('new')\n    return 2\n"


def test_declared_resources_locks_on_file_path(fake_conv_state):
    """declared_resources 返回用于每个文件锁定的文件路径密钥。"""
    tool = EditTool.create(conv_state=fake_conv_state)[0]
    absolute_path = Path(fake_conv_state.workspace.working_dir) / "a" / "b.py"
    action = EditAction(file_path=str(absolute_path), old_string="x", new_string="y")
    resources = tool.declared_resources(action)
    assert resources.declared is True
    assert len(resources.keys) == 1
    assert resources.keys[0] == f"file:{absolute_path.resolve()}"


def test_declared_resources_different_files_different_keys(fake_conv_state):
    """不同的文件路径产生不同的资源密钥。"""
    tool = EditTool.create(conv_state=fake_conv_state)[0]
    a = tool.declared_resources(
        EditAction(file_path="/a.py", old_string="", new_string="x")
    )
    b = tool.declared_resources(
        EditAction(file_path="/b.py", old_string="", new_string="x")
    )
    assert a.keys != b.keys


def test_declared_resources_relative_path_resolves_against_workspace(fake_conv_state):
    """相对路径必须针对 workspace_root 进行解析，而不是针对 CWD 进行解析。"""
    tool = EditTool.create(conv_state=fake_conv_state)[0]
    workspace = fake_conv_state.workspace.working_dir
    resources = tool.declared_resources(
        EditAction(file_path="src/foo.py", old_string="", new_string="x")
    )
    assert resources.keys[0] == f"file:{(Path(workspace) / 'src' / 'foo.py').resolve()}"
