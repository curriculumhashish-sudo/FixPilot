"""测试 FileEditorTool 子类。"""

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.tool import DeclaredResources
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.file_editor import (
    FileEditorAction,
    FileEditorObservation,
    FileEditorTool,
)


def _create_test_conv_state(temp_dir: str) -> ConversationState:
    """创建测试对话状态的帮助程序。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return ConversationState.create(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=temp_dir),
    )


def test_file_editor_tool_initialization():
    """测试 FileEditorTool 初始化是否正确。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        # 检查该工具是否具有正确的名称和属性
        assert tool.name == "file_editor"
        assert tool.executor is not None
        assert issubclass(tool.action_type, FileEditorAction)


def test_file_editor_tool_create_file():
    """测试 FileEditorTool 是否可以创建文件。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        test_file = os.path.join(temp_dir, "test.txt")

        # 创建一个创建文件的动作
        action = FileEditorAction(
            command="create",
            path=test_file,
            file_text="Hello, World!",
        )

        # 执行动作
        result = tool(action)

        # 检查结果
        assert result is not None
        assert isinstance(result, FileEditorObservation)
        assert not result.is_error
        assert os.path.exists(test_file)

        # 检查文件内容
        with open(test_file) as f:
            content = f.read()
        assert content == "Hello, World!"


def test_file_editor_tool_view_file():
    """测试 FileEditorTool 是否可以查看文件。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        test_file = os.path.join(temp_dir, "test.txt")

        # 创建测试文件
        with open(test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3")

        # 创建一个查看文件的动作
        action = FileEditorAction(command="view", path=test_file)

        # 执行动作
        result = tool(action)

        # 检查结果
        assert result is not None
        assert isinstance(result, FileEditorObservation)
        assert not result.is_error
        assert "Line 1" in result.text
        assert "Line 2" in result.text
        assert "Line 3" in result.text


def test_file_editor_tool_str_replace():
    """测试FileEditorTool是否可以进行字符串替换。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        test_file = os.path.join(temp_dir, "test.txt")

        # 创建测试文件
        with open(test_file, "w") as f:
            f.write("Hello, World!\nThis is a test.")

        # 创建一个动作来替换文本
        action = FileEditorAction(
            command="str_replace",
            path=test_file,
            old_str="World",
            new_str="Universe",
        )

        # 执行动作
        result = tool(action)

        # 检查结果
        assert result is not None
        assert isinstance(result, FileEditorObservation)
        assert not result.is_error

        # 检查文件内容
        with open(test_file) as f:
            content = f.read()
        assert "Hello, Universe!" in content


def test_file_editor_tool_to_openai_tool():
    """测试FileEditorTool可以转换为OpenAI工具格式。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        # 转换为OpenAI工具格式
        openai_tool = tool.to_openai_tool()

        # 检查格式
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "file_editor"
        assert "description" in openai_tool["function"]
        assert "parameters" in openai_tool["function"]


def test_file_editor_tool_view_directory():
    """测试 FileEditorTool 是否可以查看目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        # 创建一些测试文件
        test_file1 = os.path.join(temp_dir, "file1.txt")
        test_file2 = os.path.join(temp_dir, "file2.txt")

        with open(test_file1, "w") as f:
            f.write("File 1 content")
        with open(test_file2, "w") as f:
            f.write("File 2 content")

        # 创建一个查看目录的动作
        action = FileEditorAction(command="view", path=temp_dir)

        # 执行动作
        result = tool(action)

        # 检查结果
        assert result is not None
        assert isinstance(result, FileEditorObservation)
        assert not result.is_error
        assert "file1.txt" in result.text
        assert "file2.txt" in result.text


def test_file_editor_tool_includes_working_directory_in_description():
    """测试 FileEditorTool 的描述中是否包含工作目录信息。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        # 检查工具描述是否包含工作目录信息
        assert f"Your current working directory is: {temp_dir}" in tool.description
        assert (
            "When exploring project structure, start with this directory "
            "instead of the root filesystem."
        ) in tool.description

        # 验证原始描述是否仍然存在
        assert (
            "Custom editing tool for viewing, creating and editing files"
            in tool.description
        )


def test_file_editor_tool_openai_format_includes_working_directory():
    """测试 OpenAI 工具格式是否包含工作目录信息。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        # 转换为OpenAI工具格式
        openai_tool = tool.to_openai_tool()

        # 检查描述是否包含工作目录信息
        function_def = openai_tool["function"]
        assert "description" in function_def
        description = function_def["description"]
        assert f"Your current working directory is: {temp_dir}" in description
        assert (
            "When exploring project structure, start with this directory "
            "instead of the root filesystem."
        ) in description


@pytest.mark.parametrize(
    "command", ["view", "create", "str_replace", "insert", "undo_edit"]
)
def test_declared_resources_locks_on_file_path(command):
    """文件：{path} 上的每个命令锁都声明为=True。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tool = FileEditorTool.create(_create_test_conv_state(temp_dir))[0]
        action = FileEditorAction(command=command, path="/a.py")
        expected_path = Path("/a.py").resolve()
        assert tool.declared_resources(action) == DeclaredResources(
            keys=(f"file:{expected_path}",), declared=True
        )


def test_declared_resources_different_paths_produce_different_keys():
    with tempfile.TemporaryDirectory() as temp_dir:
        tool = FileEditorTool.create(_create_test_conv_state(temp_dir))[0]
        r1 = tool.declared_resources(
            FileEditorAction(command="str_replace", path="/a.py")
        )
        r2 = tool.declared_resources(
            FileEditorAction(command="str_replace", path="/b.py")
        )
        assert r1.keys != r2.keys


def test_declared_resources_same_path_same_key_across_commands():
    with tempfile.TemporaryDirectory() as temp_dir:
        tool = FileEditorTool.create(_create_test_conv_state(temp_dir))[0]
        r1 = tool.declared_resources(FileEditorAction(command="view", path="/a.py"))
        r2 = tool.declared_resources(
            FileEditorAction(command="str_replace", path="/a.py")
        )
        assert r1.keys == r2.keys


def test_declared_resources_normalizes_dotdot_paths():
    """解析为同一文件的带有“..”的路径会产生相同的密钥。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tool = FileEditorTool.create(_create_test_conv_state(temp_dir))[0]
        r1 = tool.declared_resources(FileEditorAction(command="view", path="/a/c.py"))
        r2 = tool.declared_resources(
            FileEditorAction(command="view", path="/a/b/../c.py")
        )
        assert r1.keys == r2.keys


def test_declared_resources_normalizes_dot_paths():
    """带有“.”的路径解析到同一文件会产生相同的密钥。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tool = FileEditorTool.create(_create_test_conv_state(temp_dir))[0]
        r1 = tool.declared_resources(FileEditorAction(command="view", path="/a/c.py"))
        r2 = tool.declared_resources(FileEditorAction(command="view", path="/a/./c.py"))
        assert r1.keys == r2.keys


def test_declared_resources_normalizes_relative_paths():
    """相对路径解析为绝对路径。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        tool = FileEditorTool.create(_create_test_conv_state(temp_dir))[0]
        r1 = tool.declared_resources(FileEditorAction(command="view", path="a.py"))
        expected_path = Path("a.py").resolve()
        assert r1.keys == (f"file:{expected_path}",)


def test_file_editor_tool_image_viewing_line_with_vision_enabled():
    """测试当 LLM 支持视觉时，是否包含图像观看线。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建具有视觉支持的LLM（gpt-4o-mini支持视觉）
        llm = LLM(
            model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_state = ConversationState.create(
            id=uuid4(),
            agent=agent,
            workspace=LocalWorkspace(working_dir=temp_dir),
        )

        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        # 检查图像查看线是否包含在描述中
        assert (
            "If `path` is an image file (.png, .jpg, .jpeg, .gif, .webp, .bmp)"
            in tool.description
        )
        assert "view` displays the image content" in tool.description


def test_file_editor_tool_image_viewing_line_with_vision_disabled():
    """测试当LLM不支持视觉时，图像观看线被排除。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建不带视觉支持的LLM（gpt-3.5-turbo不支持视觉）
        llm = LLM(
            model="gpt-3.5-turbo", api_key=SecretStr("test-key"), usage_id="test-llm"
        )
        agent = Agent(llm=llm, tools=[])
        conv_state = ConversationState.create(
            id=uuid4(),
            agent=agent,
            workspace=LocalWorkspace(working_dir=temp_dir),
        )

        tools = FileEditorTool.create(conv_state)
        tool = tools[0]

        # 检查图像查看线不包含在描述中
        assert "is an image file" not in tool.description
        assert "displays the image content" not in tool.description


def test_str_replace_fallback_preserves_new_str_whitespace():
    """当使用空白容忍回退方案时（old_str 不是逐字），
    必须保留 new_str 中有意义的前导/尾随空白。

    回归测试：之前回退方案剥离了 new_str 和 old_str，默默地删除了故意的空白 (e.g.
    Markdown 硬线中断），同时报告成功。
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tool = FileEditorTool.create(conv_state)[0]

        test_file = os.path.join(temp_dir, "test.md")
        with open(test_file, "w") as f:
            f.write("hello world\nsecond line\n")

        # old_str 中的前导空格 -> 精确匹配失败 -> 回退方案运行。 new_str 中的尾随空格是
        # 有意义的（Markdown 硬换行）。
        #
        action = FileEditorAction(
            command="str_replace",
            path=test_file,
            old_str=" hello world",
            new_str="HELLO WORLD  ",
        )
        result = tool(action)

        assert result is not None
        assert not result.is_error
        with open(test_file) as f:
            content = f.read()
        assert content == "HELLO WORLD  \nsecond line\n"


def test_str_replace_exact_match_preserves_new_str_whitespace():
    """完全匹配路径（无回退方案）也必须保留 new_str
    空白。 防止正常代码路径中的回归。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tool = FileEditorTool.create(conv_state)[0]

        test_file = os.path.join(temp_dir, "test.md")
        with open(test_file, "w") as f:
            f.write("hello world\nsecond line\n")

        action = FileEditorAction(
            command="str_replace",
            path=test_file,
            old_str="hello world",
            new_str="HELLO WORLD  ",
        )
        result = tool(action)

        assert result is not None
        assert not result.is_error
        with open(test_file) as f:
            content = f.read()
        assert content == "HELLO WORLD  \nsecond line\n"
