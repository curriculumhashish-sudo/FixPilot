"""测试 GlobTool 子类。"""

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
from openhands.tools.glob import GlobAction, GlobObservation, GlobTool
from openhands.tools.glob.impl import GlobExecutor


def _create_test_conv_state(temp_dir: str) -> ConversationState:
    """创建测试对话状态的帮助程序。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    return ConversationState.create(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir=temp_dir),
    )


def test_glob_tool_initialization():
    """测试 GlobTool 初始化是否正确。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 检查该工具是否具有正确的名称和属性
        assert tool.name == "glob"
        assert tool.executor is not None
        assert tool.action_type == GlobAction
        assert tool.observation_type == GlobObservation


def test_glob_tool_invalid_working_dir():
    """测试 GlobTool 是否会因工作目录无效而引发错误。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm, tools=[])
    conv_state = ConversationState.create(
        id=uuid4(),
        agent=agent,
        workspace=LocalWorkspace(working_dir="/nonexistent/directory"),
    )

    try:
        GlobTool.create(conv_state)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "is not a valid directory" in str(e)


def test_glob_tool_find_files():
    """测试 GlobTool 是否可以找到具有模式的文件。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建测试文件
        test_files = [
            "test.py",
            "main.js",
            "config.json",
            "src/app.py",
            "src/utils.js",
            "tests/test_main.py",
        ]

        for file_path in test_files:
            full_path = Path(temp_dir) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(f"# Content of {file_path}")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 测试查找 Python 个文件
        action = GlobAction(pattern="**/*.py")
        assert tool.executor is not None
        assert tool.executor is not None
        observation = tool.executor(action)

        assert isinstance(observation, GlobObservation)
        assert observation.is_error is False
        assert len(observation.files) == 3  # test.py, src/app.py, tests/test_main.py
        assert observation.pattern == "**/*.py"
        assert observation.search_path == str(Path(temp_dir).resolve())
        assert not observation.truncated

        # 检查所有找到的文件是否为 Python 个文件
        for file_path in observation.files:
            assert file_path.endswith(".py")
            assert os.path.exists(file_path)


def test_glob_tool_specific_directory():
    """测试 GlobTool 是否可以在特定目录中搜索。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建测试文件
        src_dir = Path(temp_dir) / "src"
        src_dir.mkdir()
        (src_dir / "app.py").write_text("# App code")
        (src_dir / "utils.py").write_text("# Utils code")

        tests_dir = Path(temp_dir) / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("# Test code")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 测试仅在 src 目录中搜索
        action = GlobAction(pattern="*.py", path=str(src_dir))
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 2  # app.py, utils.py
        assert observation.search_path == str(src_dir.resolve())

        # 检查所有找到的文件是否都在 src 目录中
        for file_path in observation.files:
            assert str(src_dir.resolve()) in file_path


def test_glob_tool_no_matches():
    """测试 GlobTool 是否正常处理任何匹配项。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建单个文本文件
        (Path(temp_dir) / "readme.txt").write_text("Hello world")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 搜索 Python 个文件（应找到 None）
        action = GlobAction(pattern="**/*.py")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 0
        assert observation.pattern == "**/*.py"
        assert not observation.truncated


def test_glob_tool_invalid_directory():
    """测试 GlobTool 是否处理无效的搜索目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 在不存在的目录中搜索
        action = GlobAction(pattern="*.py", path="/nonexistent/directory")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is True
        assert "is not a valid directory" in observation.text
        assert len(observation.files) == 0


def test_glob_tool_complex_patterns():
    """测试 GlobTool 是否处理复杂的全局模式。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建具有各种扩展名的测试文件
        test_files = [
            "config.json",
            "config.yaml",
            "config.yml",
            "config.toml",
            "readme.md",
            "app.py",
        ]

        for file_path in test_files:
            (Path(temp_dir) / file_path).write_text(f"Content of {file_path}")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 配置文件的测试模式
        action = GlobAction(pattern="config.*")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 4  # 所有配置文件
        assert observation.pattern == "config.*"

        # 检查所有找到的文件是否具有预期的扩展名
        extensions = {Path(f).suffix for f in observation.files}
        assert extensions == {".json", ".yaml", ".yml", ".toml"}


def test_glob_tool_directories_excluded():
    """测试 GlobTool 是否从结果中排除目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建目录和文件
        (Path(temp_dir) / "src").mkdir()
        (Path(temp_dir) / "tests").mkdir()
        (Path(temp_dir) / "app.py").write_text("# App code")
        (Path(temp_dir) / "src" / "utils.py").write_text("# Utils code")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 搜索一切
        action = GlobAction(pattern="*")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        # 应该递归查找所有文件，但不是目录
        assert len(observation.files) == 2  # app.py 和 src/utils.py
        # 验证两个文件都存在
        file_names = [Path(f).name for f in observation.files]
        assert "app.py" in file_names
        assert "utils.py" in file_names
        # 验证不包含目录路径
        for file_path in observation.files:
            assert Path(file_path).is_file() or not Path(file_path).exists()


def test_glob_tool_to_llm_content():
    """测试 GlobObservation 是否正确转换为 LLM 内容。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建测试文件
        (Path(temp_dir) / "test1.py").write_text("# Test 1")
        (Path(temp_dir) / "test2.py").write_text("# Test 2")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 测试成功搜索
        action = GlobAction(pattern="*.py")
        assert tool.executor is not None
        observation = tool.executor(action)

        content = observation.to_llm_content
        assert len(content) == 1
        text_content = content[0].text
        assert "Found 2 file(s) matching pattern" in text_content
        assert "*.py" in text_content
        assert "test1.py" in text_content
        assert "test2.py" in text_content


def test_glob_tool_to_llm_content_no_matches():
    """测试 LLM 内容是否不匹配。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 搜索不存在的文件
        action = GlobAction(pattern="*.nonexistent")
        assert tool.executor is not None
        observation = tool.executor(action)

        content = observation.to_llm_content
        assert len(content) == 1
        text_content = content[0].text
        assert "No files found matching pattern" in text_content
        assert "*.nonexistent" in text_content


def test_glob_tool_to_llm_content_error():
    """测试 LLM 内容是否存在错误情况。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 在无效目录中搜索
        action = GlobAction(pattern="*.py", path="/invalid/path")
        assert tool.executor is not None
        observation = tool.executor(action)

        content = observation.to_llm_content
        assert len(content) == 2
        assert content[0].text == GlobObservation.ERROR_MESSAGE_HEADER
        text_content = content[1].text
        assert "is not a valid directory" in text_content


@pytest.mark.parametrize(
    "pattern, path",
    [
        ("**/*.py", None),
        ("*.txt", "/some/custom/path"),
        ("src/**/*.ts", None),
        ("config.*", "/another/path"),
    ],
    ids=[
        "recursive-no-path",
        "simple-custom-path",
        "nested-no-path",
        "wildcard-custom-path",
    ],
)
def test_glob_tool_declared_resources_with_ripgrep(pattern, path):
    """当 ripgrep 可用时，测试 GlobTool 是否声明没有资源。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        assert isinstance(tool.executor, GlobExecutor)
        if not tool.executor.is_parallel_safe():
            pytest.skip("ripgrep not installed")

        action = GlobAction(pattern=pattern, path=path)
        resources = tool.declared_resources(action)

        assert isinstance(resources, DeclaredResources)
        assert resources.declared is True
        assert resources.keys == ()


@pytest.mark.parametrize(
    "pattern, path",
    [
        ("**/*.py", None),
        ("*.txt", "/some/custom/path"),
        ("src/**/*.ts", None),
        ("config.*", "/another/path"),
    ],
    ids=[
        "recursive-no-path",
        "simple-custom-path",
        "nested-no-path",
        "wildcard-custom-path",
    ],
)
def test_glob_tool_declared_resources_without_ripgrep(pattern, path):
    """当 ripgrep 不可用时，测试 GlobTool 是否回退到工具范围互斥体。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        assert isinstance(tool.executor, GlobExecutor)
        tool.executor._ripgrep_available = False  # 力回退方案路径

        action = GlobAction(pattern=pattern, path=path)
        resources = tool.declared_resources(action)

        assert isinstance(resources, DeclaredResources)
        assert resources.declared is False
        assert resources.keys == ()


def test_glob_tool_truncation():
    """测试当匹配项太多时 GlobTool 是否会截断结果。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建超过 100 个文件
        for i in range(150):
            (Path(temp_dir) / f"file_{i:03d}.txt").write_text(f"Content {i}")

        conv_state = _create_test_conv_state(temp_dir)
        tools = GlobTool.create(conv_state)
        tool = tools[0]

        # 搜索所有文本文件
        action = GlobAction(pattern="*.txt")
        assert tool.executor is not None
        observation = tool.executor(action)

        assert observation.is_error is False
        assert len(observation.files) == 100  # 截断为 100
        assert observation.truncated is True

        # 检查LLM内容提到截断
        content = observation.to_llm_content
        text_content = content[0].text
        assert "Results truncated to first 100 files" in text_content
