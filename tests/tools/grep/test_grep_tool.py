"""测试 GrepTool 集成。"""

import os
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.tool.tool import DeclaredResources
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.grep import GrepAction, GrepObservation, GrepTool


def _create_test_conv_state(temp_dir: str) -> ConversationState:
    """创建测试对话状态的帮助程序。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return ConversationState.create(
        id=uuid4(),
        workspace=LocalWorkspace(working_dir=temp_dir),
        agent=agent,
    )


def test_grep_tool_initialization():
    """测试 GrepTool 初始化是否正确。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)

        assert len(tools) == 1
        tool = tools[0]
        assert tool.name == "grep"
        assert tool.executor is not None


def test_grep_tool_invalid_working_dir():
    """测试 GrepTool 是否会因工作目录无效而引发错误。"""
    try:
        conv_state = _create_test_conv_state("/nonexistent/directory")
        GrepTool.create(conv_state)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "not a valid directory" in str(e)


def test_grep_tool_basic_search():
    """测试基本 grep 搜索返回文件路径。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建测试文件
        (Path(temp_dir) / "app.py").write_text("print('hello')")
        (Path(temp_dir) / "utils.py").write_text("print('world')")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="print")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert isinstance(observation, GrepObservation)
        assert observation.is_error is False
        assert len(observation.matches) == 2  # 两个文件
        assert observation.pattern == "print"
        assert observation.search_path == str(Path(temp_dir).resolve())
        assert not observation.truncated

        # 检查匹配的文件路径
        for file_path in observation.matches:
            assert isinstance(file_path, str)
            assert file_path.endswith(".py")
            assert os.path.exists(file_path)


def test_grep_tool_case_insensitive():
    """测试 grep 是否不区分大小写。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / "test.py").write_text("PRINT('test')")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="print")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.matches) == 1


def test_grep_tool_include_filter():
    """测试包括文件模式过滤器。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / "test.py").write_text("test")
        (Path(temp_dir) / "test.js").write_text("test")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="test", include="*.py")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.matches) == 1
        assert observation.matches[0].endswith(".py")


def test_grep_tool_specific_directory():
    """测试在特定目录中搜​​索。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = Path(temp_dir) / "src"
        src_dir.mkdir()
        (src_dir / "source.py").write_text("print('source')")
        (Path(temp_dir) / "other.py").write_text("print('other')")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="print", path=str(src_dir))
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.matches) == 1
        assert observation.search_path == str(src_dir.resolve())
        assert str(src_dir.resolve()) in observation.matches[0]


def test_grep_tool_no_matches():
    """当没有文件包含该模式时进行测试。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / "app.py").write_text("def main():\n    return 0")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="nonexistent")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.matches) == 0
        assert not observation.truncated


def test_grep_tool_invalid_regex():
    """测试无效正则表达式的处理。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="[invalid")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is True
        assert "Invalid regex pattern" in observation.text


def test_grep_tool_invalid_directory():
    """测试在无效目录中的搜索。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="test", path="/nonexistent/path")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is True
        assert "not a valid directory" in observation.text


def test_grep_tool_hidden_files_excluded():
    """测试隐藏文件是否从结果中排除。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / "visible.py").write_text("test")
        (Path(temp_dir) / ".hidden.py").write_text("test")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="test")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.matches) == 1
        assert ".hidden" not in observation.matches[0]


def test_grep_tool_to_llm_content():
    """测试观测结果到 LLM 内容的转换。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / "test.py").write_text("test content")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="test")
        assert tool.executor is not None
        observation = tool.executor(action)

        content = observation.to_llm_content
        assert len(content) == 1
        text = content[0].text
        assert "Found 1 file(s) containing pattern" in text
        assert "test.py" in text


def test_grep_tool_to_llm_content_with_include():
    """测试LLM内容包括过滤器信息。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / "test.py").write_text("test")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="test", include="*.py")
        assert tool.executor is not None
        observation = tool.executor(action)

        content = observation.to_llm_content
        text = content[0].text
        assert "(filtered by '*.py')" in text


def test_grep_tool_to_llm_content_no_matches():
    """测试 LLM 内容是否不匹配。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        (Path(temp_dir) / "test.py").write_text("content")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="nonexistent")
        assert tool.executor is not None
        observation = tool.executor(action)

        content = observation.to_llm_content
        text = content[0].text
        assert "No files found containing pattern" in text


def test_grep_tool_to_llm_content_error():
    """测试 LLM 内容是否有错误。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="[invalid")
        assert tool.executor is not None
        observation = tool.executor(action)

        content = observation.to_llm_content
        assert len(content) == 2
        assert content[0].text == GrepObservation.ERROR_MESSAGE_HEADER
        text = content[1].text
        assert "Invalid regex pattern" in text


@pytest.mark.parametrize(
    "pattern, path, include",
    [
        ("log.*Error", None, None),
        ("function\\s+\\w+", "/some/custom/path", None),
        ("TODO", None, "*.py"),
        ("import", "/another/path", "*.{ts,tsx}"),
    ],
    ids=[
        "regex-no-path",
        "regex-custom-path",
        "simple-with-include",
        "custom-path-with-include",
    ],
)
def test_grep_tool_declared_resources(pattern, path, include):
    """测试 GrepTool 是否为所有后端声明并行安全资源。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern=pattern, path=path, include=include)
        resources = tool.declared_resources(action)

        assert isinstance(resources, DeclaredResources)
        assert resources.declared is True
        assert resources.keys == ()


def test_grep_tool_truncation():
    """测试结果中是否显示截断。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建 150 个文件
        for i in range(150):
            (Path(temp_dir) / f"file{i}.py").write_text("test")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GrepTool.create(conv_state)
        tool = tools[0]

        action = GrepAction(pattern="test")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.matches) == 100
        assert observation.truncated is True

        content = observation.to_llm_content
        text = content[0].text
        assert "truncated" in text.lower()
