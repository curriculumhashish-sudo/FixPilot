"""测试基本文件编辑器操作。"""

from pathlib import Path

import pytest

from openhands.tools.file_editor import (
    FileEditorObservation,
    file_editor,
)
from openhands.tools.file_editor.editor import FileEditor
from openhands.tools.file_editor.exceptions import (
    EditorToolParameterInvalidError,
    EditorToolParameterMissingError,
    ToolError,
)
from openhands.tools.file_editor.utils.constants import (
    DIRECTORY_CONTENT_TRUNCATED_NOTICE,
    TEXT_FILE_CONTENT_TRUNCATED_NOTICE,
)
from tests.platform_utils import symlink_or_skip

from .conftest import (
    assert_successful_result,
)


@pytest.fixture
def editor(tmp_path):
    editor = FileEditor()
    # 设置包含测试文件的临时目录
    test_file = tmp_path / "test.txt"
    test_file.write_text("This is a test file.\nThis file is for testing purposes.")
    return editor, test_file


@pytest.fixture
def editor_python_file_with_tabs(tmp_path):
    editor = FileEditor()
    # 设置包含测试文件的临时目录
    test_file = tmp_path / "test.py"
    test_file.write_text('def test():\n\tprint("Hello, World!")')
    return editor, test_file


def test_file_editor_happy_path(temp_file):
    """测试基本的str_replace操作。"""
    old_str = "test file"
    new_str = "sample file"

    # 创建测试文件
    with open(temp_file, "w") as f:
        f.write("This is a test file.\nThis file is for testing purposes.")

    # 调用`file_editor`函数
    result = file_editor(
        command="str_replace",
        path=str(temp_file),
        old_str=old_str,
        new_str=new_str,
    )

    # 验证结果
    assert_successful_result(result, str(temp_file))
    assert (
        result.text is not None
        and "The file" in result.text
        and "has been edited" in result.text
    )
    assert result.text is not None and "This is a sample file." in result.text
    assert result.path == str(temp_file)
    assert result.prev_exist is True
    assert (
        result.old_content == "This is a test file.\nThis file is for testing purposes."
    )
    assert (
        result.new_content
        == "This is a sample file.\nThis file is for testing purposes."
    )

    # 确保文件内容已更新
    with open(temp_file) as f:
        content = f.read()
    assert "This is a sample file." in content


def test_file_editor_view_operation(temp_file):
    """使用包含特殊内容的文件测试视图操作。"""
    # 创建包含各种模式的内容
    xml_content = """This is a file with XML tags parsing logic...
match = re.search(
    r'<oh_aci_output_[0-9a-f]{32}>(.*?)</oh_aci_output_[0-9a-f]{32}>',
    result,
    re.DOTALL,
)
...More text here.
"""

    with open(temp_file, "w") as f:
        f.write(xml_content)

    result = file_editor(
        command="view",
        path=str(temp_file),
    )

    # 验证结果
    assert_successful_result(result, str(temp_file))
    assert (
        result.text is not None
        and "Here's the result of running `cat -n`" in result.text
    )
    assert (
        result.text is not None
        and "This is a file with XML tags parsing logic..." in result.text
    )
    assert result.text is not None and "match = re.search(" in result.text
    assert result.text is not None and "...More text here." in result.text


def test_successful_operations(temp_file):
    """测试成功的文件操作及其输出格式。"""
    # 创建测试文件
    content = "line 1\nline 2\nline 3\n"
    with open(temp_file, "w") as f:
        f.write(content)

    # 测试视图
    result = file_editor(
        command="view",
        path=str(temp_file),
    )
    assert_successful_result(result)
    assert (
        result.text is not None
        and "Here's the result of running `cat -n`" in result.text
    )
    assert result.text is not None and "line 1" in result.text

    # 测试 str_replace
    result = file_editor(
        command="str_replace",
        path=str(temp_file),
        old_str="line 2",
        new_str="replaced line",
    )
    assert_successful_result(result)
    assert result.text is not None and "has been edited" in result.text
    assert result.text is not None and "replaced line" in result.text

    # 测试插入件
    result = file_editor(
        command="insert",
        path=str(temp_file),
        insert_line=1,
        new_str="inserted line",
    )
    assert_successful_result(result)
    assert result.text is not None and "has been edited" in result.text
    assert result.text is not None and "inserted line" in result.text

    # 测试撤消
    result = file_editor(
        command="undo_edit",
        path=str(temp_file),
    )
    assert_successful_result(result)
    assert result.text is not None and "undone successfully" in result.text


def test_tab_expansion(temp_file):
    """测试文件操作中是否正确处理选项卡。"""
    # 创建一个带有选项卡的文件
    content = "no tabs\n\tindented\nline\twith\ttabs\n"
    with open(temp_file, "w") as f:
        f.write(content)

    # 测试视图命令
    result = file_editor(
        command="view",
        path=str(temp_file),
    )
    assert_successful_result(result)
    # 选项卡应保留在输出中
    assert result.text is not None and "\tindented" in result.text
    assert result.text is not None and "line\twith\ttabs" in result.text

    # 使用 old_str 中的选项卡测试 str_replace
    result = file_editor(
        command="str_replace",
        path=str(temp_file),
        old_str="line\twith\ttabs",
        new_str="replaced line",
    )
    assert_successful_result(result)
    assert result.text is not None and "replaced line" in result.text

    # 使用 new_str 中的选项卡测试 str_replace
    result = file_editor(
        command="str_replace",
        path=str(temp_file),
        old_str="replaced line",
        new_str="new\tline\twith\ttabs",
    )
    assert_successful_result(result)
    assert result.text is not None and "new\tline\twith\ttabs" in result.text

    # 测试带有标签的插入件
    result = file_editor(
        command="insert",
        path=str(temp_file),
        insert_line=1,
        new_str="\tindented\tline",
    )
    assert_successful_result(result)
    assert result.text is not None and "\tindented\tline" in result.text


def test_create_operation(temp_file):
    """测试文件创建操作。"""
    # 首先删除临时文件
    temp_file.unlink()

    content = "This is a new file.\nWith multiple lines."

    result = file_editor(
        command="create",
        path=str(temp_file),
        file_text=content,
    )

    assert_successful_result(result, str(temp_file))
    assert result.text is not None and "created successfully" in result.text
    assert result.prev_exist is False
    assert result.new_content == content

    # 验证文件已创建且内容正确
    with open(temp_file) as f:
        file_content = f.read()
    assert file_content == content


def test_view_operation_truncation(temp_file):
    """测试视图操作是否正确截断大文件。"""
    from openhands.tools.file_editor.utils.constants import (
        MAX_RESPONSE_LEN_CHAR,
        TEXT_FILE_CONTENT_TRUNCATED_NOTICE,
    )

    # 创建超出 str_replace_editor 截断限制的大文件
    large_content = "A" * (MAX_RESPONSE_LEN_CHAR + 1000)
    with open(temp_file, "w") as f:
        f.write(large_content)

    # 测试视图命令
    result = file_editor(
        command="view",
        path=str(temp_file),
    )

    assert_successful_result(result)
    assert result.text is not None

    # 检查是否存在截断通知
    assert TEXT_FILE_CONTENT_TRUNCATED_NOTICE in result.text

    # 内容应该在添加行号之前截断，因此最终输出会比 MAX_RESPONSE_LEN_CHAR 长，但由于格式
    # 化，原始内容被截断
    #
    assert "Here's the result of running `cat -n`" in result.text

    # 使用头尾截断，应包含开始和结束内容行号将在开始和结束处显示为“1\tA...”，并以“A”结束
    #
    assert "\tA" in result.text  # 应该有带有制表符格式的 A


def test_view_file(editor):
    editor, test_file = editor
    result = editor(command="view", path=str(test_file))
    assert isinstance(result, FileEditorObservation)
    assert f"Here's the result of running `cat -n` on {test_file}:" in result.text
    assert "1\tThis is a test file." in result.text
    assert "2\tThis file is for testing purposes." in result.text
    assert "3\t" not in result.text  # 无需额外线路


@pytest.mark.parametrize(
    ("content", "numbered_lines"),
    [
        ("hello", ["     1\thello"]),
        ("hello\n", ["     1\thello"]),
        ("hello\n\n", ["     1\thello", "     2\t"]),
        # `\x0c`（换页）和 `\u2028` 是 str.splitlines() 的换行符，但 read_file/insert/
        # view_range 的普通字符，因此它们不能移动行号。
        #
        ("a\x0cb\nc\n", ["     1\ta\x0cb", "     2\tc"]),
        (
            'const s = "a\u2028b";\ngamma\n',
            ['     1\tconst s = "a\u2028b";', "     2\tgamma"],
        ),
    ],
)
def test_view_line_numbers_match_file_lines(tmp_path, content, numbered_lines):
    test_file = tmp_path / "newlines.txt"
    test_file.write_text(content)

    result = file_editor(command="view", path=str(test_file))

    assert_successful_result(result, str(test_file))
    assert result.text is not None
    assert result.text.split("\n")[1:-1] == numbered_lines


def test_insert_line_number_matches_view_with_form_feed(tmp_path):
    """换页不得移动插入内容所在的行。

    `view` 数字 `int b;` 位于第 2 行，因此在第 2 行插入必须紧接其后，而不是在
    `int c;` 之后。
    """
    path = tmp_path / "formfeed.c"
    path.write_text("int a;\x0cint b;\nint c;\n")

    view = file_editor(command="view", path=str(path))
    assert view.text is not None
    assert view.text.split("\n")[1:-1] == ["     1\tint a;\x0cint b;", "     2\tint c;"]

    result = file_editor(
        command="insert", path=str(path), insert_line=2, new_str="int NEW;"
    )
    assert_successful_result(result, str(path))
    assert path.read_text() == "int a;\x0cint b;\nint c;\nint NEW;\n"


@pytest.mark.parametrize("content", ["a\nb", "a\nb\n", "a\nb\n\n", "a\n\n", "\n"])
def test_ranged_view_preserves_final_line(tmp_path, content):
    path = tmp_path / "range.txt"
    path.write_text(content)
    line_count = len(content.splitlines())
    full = file_editor(command="view", path=str(path))
    ranged = file_editor(command="view", path=str(path), view_range=[1, line_count])
    last = file_editor(
        command="view", path=str(path), view_range=[line_count, line_count]
    )
    assert full.text is not None
    assert ranged.text == full.text
    assert last.text is not None
    assert last.text.splitlines()[1:] == full.text.splitlines()[-1:]


def test_view_directory(editor):
    editor, test_file = editor
    parent_dir = test_file.parent
    expected_dir = parent_dir.as_posix()
    result = editor(command="view", path=str(parent_dir))
    assert (
        result.text
        == f"""Here's the files and directories up to 2 levels deep in {parent_dir}, excluding hidden items:
{expected_dir}/
{expected_dir}/test.txt"""  # noqa: E501
    )


def test_view_with_a_specific_range(editor):
    editor, test_file = editor

    # 将当前内容替换为内容：第 {line_number} 行
    _ = editor(
        command="str_replace",
        path=str(test_file),
        old_str="This is a test file.\nThis file is for testing purposes.",
        new_str="",
    )
    for i in range(0, 200):
        _ = editor(
            command="insert",
            path=str(test_file),
            insert_line=i,
            new_str=f"Line {i + 1}",
        )

    # 查看 50-100 范围内的文件
    result = editor(command="view", path=str(test_file), view_range=[50, 100])
    assert f"Here's the result of running `cat -n` on {test_file}:" in result.text
    assert "    49\tLine 49" not in result.text
    assert "    50\tLine 50" in result.text
    assert "   100\tLine 100" in result.text
    assert "101" not in result.text


def test_create_file(editor):
    editor, test_file = editor
    new_file = test_file.parent / "new_file.txt"
    result = editor(command="create", path=str(new_file), file_text="New file content")
    assert new_file.exists()
    assert new_file.read_text() == "New file content"
    assert "File created successfully" in result.text


def test_create_with_empty_string(editor):
    editor, test_file = editor
    new_file = test_file.parent / "empty_content.txt"
    result = editor(command="create", path=str(new_file), file_text="")
    assert new_file.exists()
    assert new_file.read_text() == ""
    assert "File created successfully" in result.text

    result = editor(command="view", path=str(new_file))
    assert result.text == (f"Here's the result of running `cat -n` on {new_file}:\n")


def test_create_with_none_file_text(editor):
    editor, test_file = editor
    new_file = test_file.parent / "none_content.txt"
    with pytest.raises(EditorToolParameterMissingError) as exc_info:
        editor(command="create", path=str(new_file), file_text=None)
    assert "file_text" in str(exc_info.value.message)


def test_str_replace_no_linting(editor):
    editor, test_file = editor
    result = editor(
        command="str_replace",
        path=str(test_file),
        old_str="test file",
        new_str="sample file",
    )
    assert isinstance(result, FileEditorObservation)

    # 测试str_replace命令
    assert (
        result.text
        == f"""The file {test_file} has been edited. Here's the result of running `cat -n` on a snippet of {test_file}:
     1\tThis is a sample file.
     2\tThis file is for testing purposes.
Review the changes and make sure they are as expected. Edit the file again if necessary."""  # noqa: E501
    )

    # 测试文件内容是否已更新
    assert "This is a sample file." in test_file.read_text()


def test_str_replace_multi_line_no_linting(editor):
    editor, test_file = editor
    result = editor(
        command="str_replace",
        path=str(test_file),
        old_str="This is a test file.\nThis file is for testing purposes.",
        new_str="This is a sample file.\nThis file is for testing purposes.",
    )
    assert isinstance(result, FileEditorObservation)

    # 测试str_replace命令
    assert (
        result.text
        == f"""The file {test_file} has been edited. Here's the result of running `cat -n` on a snippet of {test_file}:
     1\tThis is a sample file.
     2\tThis file is for testing purposes.
Review the changes and make sure they are as expected. Edit the file again if necessary."""  # noqa: E501
    )


def test_str_replace_multi_line_with_tabs_no_linting(editor_python_file_with_tabs):
    editor, test_file = editor_python_file_with_tabs
    result = editor(
        command="str_replace",
        path=str(test_file),
        old_str='def test():\n\tprint("Hello, World!")',
        new_str='def test():\n\tprint("Hello, Universe!")',
    )
    assert isinstance(result, FileEditorObservation)

    assert (
        result.text
        == f"""The file {test_file} has been edited. Here's the result of running `cat -n` on a snippet of {test_file}:
     1\tdef test():
     2\t\tprint("Hello, Universe!")
Review the changes and make sure they are as expected. Edit the file again if necessary."""  # noqa: E501
    )


def test_str_replace_error_multiple_occurrences(editor):
    editor, test_file = editor
    with pytest.raises(ToolError) as exc_info:
        editor(
            command="str_replace", path=str(test_file), old_str="test", new_str="sample"
        )
    assert "Multiple occurrences of old_str `test`" in str(exc_info.value.message)
    assert "[1, 2]" in str(exc_info.value.message)  # 应显示两个行号


def test_str_replace_error_multiple_multiline_occurrences(editor):
    editor, test_file = editor
    # 创建一个包含两个相同的多行块的文件
    multi_block = """def example():
    print("Hello")
    return True"""
    content = f"{multi_block}\n\nprint('separator')\n\n{multi_block}"
    test_file.write_text(content)

    with pytest.raises(ToolError) as exc_info:
        editor(
            command="str_replace",
            path=str(test_file),
            old_str=multi_block,
            new_str='def new():\n    print("World")',
        )
    error_msg = str(exc_info.value.message)
    assert "Multiple occurrences of old_str" in error_msg
    assert "[1, 7]" in error_msg  # 应显示正确的起始行号


def test_str_replace_nonexistent_string(editor):
    editor, test_file = editor
    with pytest.raises(ToolError) as exc_info:
        editor(
            command="str_replace",
            path=str(test_file),
            old_str="Non-existent Line",
            new_str="New Line",
        )
    assert "No replacement was performed" in str(exc_info)
    assert f"old_str `Non-existent Line` did not appear verbatim in {test_file}" in str(
        exc_info.value.message
    )


def test_str_replace_with_empty_new_str(editor):
    editor, test_file = editor
    test_file.write_text("Line 1\nLine to remove\nLine 3")
    result = editor(
        command="str_replace",
        path=str(test_file),
        old_str="Line to remove\n",
        new_str="",
    )
    assert isinstance(result, FileEditorObservation)
    assert test_file.read_text() == "Line 1\nLine 3"


def test_str_replace_with_empty_old_str(editor):
    editor, test_file = editor
    test_file.write_text("Line 1\nLine 2\nLine 3")
    with pytest.raises(ToolError) as exc_info:
        editor(
            command="str_replace",
            path=str(test_file),
            old_str="",
            new_str="New string",
        )
    assert (
        str(exc_info.value.message)
        == """No replacement was performed. Multiple occurrences of old_str `` in lines [1, 2, 3]. Please ensure it is unique."""  # noqa: E501
    )


def test_str_replace_with_none_old_str(editor):
    editor, test_file = editor
    with pytest.raises(EditorToolParameterMissingError) as exc_info:
        editor(
            command="str_replace",
            path=str(test_file),
            old_str=None,
            new_str="new content",
        )
    assert "old_str" in str(exc_info.value.message)


def test_insert_no_linting(editor):
    editor, test_file = editor
    result = editor(
        command="insert", path=str(test_file), insert_line=1, new_str="Inserted line"
    )
    assert isinstance(result, FileEditorObservation)
    assert "Inserted line" in test_file.read_text()
    assert (
        result.text
        == f"""The file {test_file} has been edited. Here's the result of running `cat -n` on a snippet of the edited file:
     1\tThis is a test file.
     2\tInserted line
     3\tThis file is for testing purposes.
Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."""  # noqa: E501
    )


def test_insert_invalid_line(editor):
    editor, test_file = editor
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        editor(
            command="insert",
            path=str(test_file),
            insert_line=10,
            new_str="Invalid Insert",
        )
    assert "Invalid `insert_line` parameter" in str(exc_info.value.message)
    assert "It should be within the range of allowed values:" in str(
        exc_info.value.message
    )


def test_insert_with_empty_string(editor):
    editor, test_file = editor
    result = editor(
        command="insert",
        path=str(test_file),
        insert_line=1,
        new_str="",
    )
    assert isinstance(result, FileEditorObservation)
    content = test_file.read_text().splitlines()
    assert "" in content
    assert len(content) == 3  # 原来2行加空行


def test_insert_chinese_text_into_english_file(editor):
    editor, test_file = editor
    result = editor(
        command="insert",
        path=str(test_file),
        insert_line=0,
        new_str="中文文本",
    )
    assert isinstance(result, FileEditorObservation)
    assert "中文文本" in test_file.read_text(encoding="utf-8")
    assert (
        result.text
        == f"""The file {test_file} has been edited. Here's the result of running `cat -n` on a snippet of the edited file:
     1\t中文文本
     2\tThis is a test file.
     3\tThis file is for testing purposes.
Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary."""  # noqa: E501
    )


def test_insert_with_none_new_str(editor):
    editor, test_file = editor
    with pytest.raises(EditorToolParameterMissingError) as exc_info:
        editor(
            command="insert",
            path=str(test_file),
            insert_line=1,
            new_str=None,
        )
    assert "new_str" in str(exc_info.value.message)


def test_undo_edit(editor):
    editor, test_file = editor
    # 进行要撤消的编辑
    result = editor(
        command="str_replace",
        path=str(test_file),
        old_str="test file",
        new_str="sample file",
    )
    # 撤消编辑
    result = editor(command="undo_edit", path=str(test_file))
    assert isinstance(result, FileEditorObservation)
    assert "Last edit to" in result.text
    assert "test file" in test_file.read_text()  # 恢复了原来的内容


def test_multiple_undo_edits(editor):
    editor, test_file = editor
    # 进行要撤消的编辑
    _ = editor(
        command="str_replace",
        path=str(test_file),
        old_str="test file",
        new_str="sample file v1",
    )
    # 进行另一次编辑以撤消
    _ = editor(
        command="str_replace",
        path=str(test_file),
        old_str="sample file v1",
        new_str="sample file v2",
    )
    # 撤消上次编辑
    result = editor(command="undo_edit", path=str(test_file))
    assert isinstance(result, FileEditorObservation)
    assert "Last edit to" in result.text
    assert "sample file v1" in test_file.read_text()  # 恢复之前的内容

    # 撤消第一次编辑
    result = editor(command="undo_edit", path=str(test_file))
    assert isinstance(result, FileEditorObservation)
    assert "Last edit to" in result.text
    assert "test file" in test_file.read_text()  # 恢复了原来的内容


def test_validate_path_invalid(editor):
    editor, test_file = editor
    invalid_file = test_file.parent / "nonexistent.txt"
    with pytest.raises(EditorToolParameterInvalidError):
        editor(command="view", path=str(invalid_file))


def test_create_existing_file_error(editor):
    editor, test_file = editor
    with pytest.raises(EditorToolParameterInvalidError):
        editor(command="create", path=str(test_file), file_text="New content")


def test_str_replace_missing_old_str(editor):
    editor, test_file = editor
    with pytest.raises(EditorToolParameterMissingError):
        editor(command="str_replace", path=str(test_file), new_str="sample")


def test_str_replace_new_str_and_old_str_same(editor):
    editor, test_file = editor
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        editor(
            command="str_replace",
            path=str(test_file),
            old_str="test file",
            new_str="test file",
        )
    assert (
        "No replacement was performed. `new_str` and `old_str` must be different."
        in str(exc_info.value.message)
    )


def test_insert_missing_line_param(editor):
    editor, test_file = editor
    with pytest.raises(EditorToolParameterMissingError):
        editor(command="insert", path=str(test_file), new_str="Missing insert line")


def test_undo_edit_no_history_error(editor):
    editor, test_file = editor
    empty_file = test_file.parent / "empty.txt"
    empty_file.write_text("")
    with pytest.raises(ToolError):
        editor(command="undo_edit", path=str(empty_file))


def test_view_directory_with_hidden_files(tmp_path):
    editor = FileEditor()

    # 创建一个包含一些测试文件的目录
    test_dir = tmp_path / "test_dir"
    test_dir.mkdir()
    (test_dir / "visible.txt").write_text("content1")
    (test_dir / ".hidden1").write_text("hidden1")
    (test_dir / ".hidden2").write_text("hidden2")

    # 创建一个包含文件的隐藏子目录
    hidden_subdir = test_dir / ".hidden_dir"
    hidden_subdir.mkdir()
    (hidden_subdir / "file.txt").write_text("content3")

    # 创建可见子目录
    visible_subdir = test_dir / "visible_dir"
    visible_subdir.mkdir()

    # 查看目录
    result = editor(command="view", path=str(test_dir))

    # 验证输出
    assert isinstance(result, FileEditorObservation)
    assert str(test_dir) in result.text
    assert "visible.txt" in result.text  # 显示可见文件
    assert "visible_dir" in result.text  # 显示可见目录
    assert ".hidden1" not in result.text  # 隐藏文件不显示
    assert ".hidden2" not in result.text
    assert ".hidden_dir" not in result.text
    assert (
        "3 hidden files/directories in this directory are excluded" in result.text
    )  # 仅显示当前目录中隐藏项目的数量
    assert "ls -la" in result.text  # 显示查看隐藏文件的命令


def test_view_symlinked_directory(tmp_path):
    editor = FileEditor()

    # 创建一个包含一些测试文件的目录
    source_dir = tmp_path / "source_dir"
    source_dir.mkdir()
    (source_dir / "file1.txt").write_text("content1")
    (source_dir / "file2.txt").write_text("content2")

    # 创建一个包含文件的子目录
    subdir = source_dir / "subdir"
    subdir.mkdir()
    (subdir / "file3.txt").write_text("content3")

    # 创建目录的符号链接
    symlink_dir = tmp_path / "symlink_dir"
    symlink_or_skip(source_dir, symlink_dir)

    # 查看符号链接目录
    result = editor(command="view", path=str(symlink_dir))

    # 验证是否通过符号链接列出了所有文件
    assert isinstance(result, FileEditorObservation)
    assert str(symlink_dir) in result.text
    assert "file1.txt" in result.text
    assert "file2.txt" in result.text
    assert "subdir" in result.text
    assert "file3.txt" in result.text


def test_view_large_directory_with_truncation(editor, tmp_path):
    editor, _ = editor
    # 创建包含许多文件的目录以触发截断
    large_dir = tmp_path / "large_dir"
    large_dir.mkdir()
    for i in range(1000):  # 1000 个文件应触发截断
        (large_dir / f"file_{i}.txt").write_text("content")

    result = editor(command="view", path=str(large_dir))
    assert isinstance(result, FileEditorObservation)
    assert DIRECTORY_CONTENT_TRUNCATED_NOTICE in result.text


def test_view_directory_on_hidden_path(tmp_path):
    """目录结构：
    .test_dir/ ├── visible1.txt ├── .hidden1 ├── visible_dir/ │ ├── visible2.txt │ └── .hidden2 └── .hidden_dir/
        ├── visible3.txt └── .hidden3
    """  # noqa: E501

    editor = FileEditor()

    # 创建一个目录，其中包含深度为 1 的测试文件
    hidden_test_dir = tmp_path / ".hidden_test_dir"
    hidden_test_dir.mkdir()
    (hidden_test_dir / "visible1.txt").write_text("content1")
    (hidden_test_dir / ".hidden1").write_text("hidden1")

    # 创建包含可见和隐藏文件的可见子目录
    visible_subdir = hidden_test_dir / "visible_dir"
    visible_subdir.mkdir()
    (visible_subdir / "visible2.txt").write_text("content2")
    (visible_subdir / ".hidden2").write_text("hidden2")

    # 创建一个包含可见和隐藏文件的隐藏子目录
    hidden_subdir = hidden_test_dir / ".hidden_dir"
    hidden_subdir.mkdir()
    (hidden_subdir / "visible3.txt").write_text("content3")
    (hidden_subdir / ".hidden3").write_text("hidden3")

    # 查看目录
    result = editor(command="view", path=str(hidden_test_dir))

    # 验证输出
    assert isinstance(result, FileEditorObservation)
    # 深度 1：显示可见文件/目录，不显示隐藏文件/目录
    assert "visible1.txt" in result.text
    assert "visible_dir" in result.text
    assert ".hidden1" not in result.text
    assert ".hidden_dir" not in result.text

    # 深度 2：显示 visible_dir 中的文件
    assert "visible2.txt" in result.text
    assert ".hidden2" not in result.text

    # 深度 2：hidden_dir 中的文件未显示
    assert "visible3.txt" not in result.text
    assert ".hidden3" not in result.text

    # 隐藏文件数仅包含深度1
    assert (
        "2 hidden files/directories in this directory are excluded" in result.text
    )  # 仅深度 1 处的 .hidden1 和 .hidden_dir


def test_view_large_file_with_truncation(editor, tmp_path):
    editor, _ = editor
    # 创建大文件以触发截断
    large_file = tmp_path / "large_test.txt"
    large_content = "Line 1\n" * 16000  # 16000行应该触发截断
    large_file.write_text(large_content)

    result = editor(command="view", path=str(large_file))
    assert isinstance(result, FileEditorObservation)
    assert TEXT_FILE_CONTENT_TRUNCATED_NOTICE in result.text


def test_validate_path_suggests_absolute_path(editor, tmp_path):
    editor, test_file = editor

    # 由于编辑器测试夹具没有设置 workspace_root，所以我们不应该得到建议
    #
    relative_path = test_file.name  # 这是相对路径
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        editor(command="view", path=relative_path)
    error_message = str(exc_info.value.message)
    assert "The path should be an absolute path" in error_message
    assert "Maybe you meant" not in error_message

    # 现在使用 workspace_root 创建一个编辑器
    workspace_editor = FileEditor(workspace_root=str(test_file.parent))

    # 我们现在应该得到建议
    with pytest.raises(EditorToolParameterInvalidError) as exc_info:
        workspace_editor(command="view", path=relative_path)
    error_message = str(exc_info.value.message)
    assert "The path should be an absolute path" in error_message
    assert "Maybe you meant" in error_message
    suggested_path = error_message.split("Maybe you meant ")[1].strip("?")
    assert Path(suggested_path).is_absolute()
    assert str(test_file.parent) in suggested_path


def test_str_replace_and_insert_snippet_output_on_a_large_file(editor):
    editor, test_file = editor

    # 将当前内容替换为内容：第 {line_number} 行
    _ = editor(
        command="str_replace",
        path=str(test_file),
        old_str="This is a test file.\nThis file is for testing purposes.",
        new_str="",
    )
    for i in range(0, 700):
        _ = editor(
            command="insert",
            path=str(test_file),
            insert_line=i,
            new_str=f"Line {i + 1}",
        )

    # 查看文件
    result = editor(command="view", path=str(test_file))
    assert "     1\tLine 1" in result.text
    assert "   500\tLine 500" in result.text

    # 将第 500 行的内容替换为“500 new”
    result = editor(
        command="str_replace",
        path=str(test_file),
        old_str="Line 500",
        new_str="500 new",
    )
    assert "   500\t500 new" in result.text

    # 删除行“500 new”
    result = editor(
        command="str_replace", path=str(test_file), old_str="500 new\n", new_str=""
    )
    assert "   499\tLine 499" in result.text
    assert "   500\tLine 501" in result.text

    # 在第500行插入内容
    result = editor(
        command="insert",
        path=str(test_file),
        insert_line=499,
        new_str="Inserted line at 500",
    )
    assert "   500\tInserted line at 500" in result.text
