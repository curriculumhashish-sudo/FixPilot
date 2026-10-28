"""交叉工具测试：Gemini 工具和 FileEditorTool 必须为同一个文件生成相同的资源密钥，以
便并行执行器正确地在工具边界处串行化访问。
"""

from pathlib import Path

from openhands.tools.file_editor.definition import FileEditorAction, FileEditorTool
from openhands.tools.gemini.edit.definition import EditAction, EditTool
from openhands.tools.gemini.read_file.definition import ReadFileAction, ReadFileTool
from openhands.tools.gemini.write_file.definition import WriteFileAction, WriteFileTool


def test_gemini_and_file_editor_produce_same_key(fake_conv_state):
    """Gemini 相对路径和 FileEditorTool 绝对路径相同
    文件必须产生相同的资源密钥。"""
    workspace = fake_conv_state.workspace.working_dir
    abs_path = str(Path(workspace) / "src" / "foo.py")

    # 具有相对路径的 Gemini 工具
    edit_tool = EditTool.create(conv_state=fake_conv_state)[0]
    read_tool = ReadFileTool.create(conv_state=fake_conv_state)[0]
    write_tool = WriteFileTool.create(conv_state=fake_conv_state)[0]

    gemini_edit_key = edit_tool.declared_resources(
        EditAction(file_path="src/foo.py", old_string="", new_string="x")
    ).keys[0]
    gemini_read_key = read_tool.declared_resources(
        ReadFileAction(file_path="src/foo.py")
    ).keys[0]
    gemini_write_key = write_tool.declared_resources(
        WriteFileAction(file_path="src/foo.py", content="x")
    ).keys[0]

    # FileEditorTool 具有绝对路径
    file_editor_tool = FileEditorTool.create(conv_state=fake_conv_state)[0]
    file_editor_key = file_editor_tool.declared_resources(
        FileEditorAction(command="view", path=abs_path)
    ).keys[0]

    # 所有人都必须同意
    assert gemini_edit_key == file_editor_key
    assert gemini_read_key == file_editor_key
    assert gemini_write_key == file_editor_key
