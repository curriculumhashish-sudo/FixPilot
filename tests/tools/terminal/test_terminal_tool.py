"""测试 TerminalTool 子类。"""

import platform
import tempfile
from uuid import uuid4

import pytest
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.llm import LLM
from openhands.sdk.workspace import LocalWorkspace
from openhands.tools.terminal import (
    TerminalAction,
    TerminalObservation,
    TerminalTool,
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


def test_bash_tool_initialization():
    """测试 TerminalTool 初始化是否正确。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = TerminalTool.create(conv_state)
        tool = tools[0]

        # 检查该工具是否具有正确的名称和属性
        assert tool.name == "terminal"
        assert tool.executor is not None
        assert tool.action_type == TerminalAction


def test_bash_tool_with_username():
    """测试 TerminalTool 使用用户名正确初始化。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = TerminalTool.create(conv_state, username="testuser")
        tool = tools[0]

        # 检查该工具是否具有正确的名称和属性
        assert tool.name == "terminal"
        assert tool.executor is not None
        assert tool.action_type == TerminalAction


def test_bash_tool_execution():
    """测试TerminalTool可以执行命令。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = TerminalTool.create(conv_state)
        tool = tools[0]

        # 创建一个动作
        action = TerminalAction(command="echo 'Hello, World!'")

        # 执行动作
        result = tool(action)

        # 检查结果
        assert result is not None
        assert isinstance(result, TerminalObservation)
        assert "Hello, World!" in result.text


def test_bash_tool_working_directory():
    """测试 TerminalTool 是否尊重工作目录。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = TerminalTool.create(conv_state)
        tool = tools[0]

        # 创建一个操作来检查当前目录
        action = TerminalAction(command="pwd")

        # 执行动作
        result = tool(action)

        # 检查工作目录是否正确
        assert isinstance(result, TerminalObservation)
        assert temp_dir in result.text


def test_bash_tool_to_openai_tool():
    """测试TerminalTool可以转换为OpenAI工具格式。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tools = TerminalTool.create(conv_state)
        tool = tools[0]

        # 转换为OpenAI工具格式
        openai_tool = tool.to_openai_tool()

        # 检查格式
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "terminal"
        assert "description" in openai_tool["function"]
        assert "parameters" in openai_tool["function"]


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="This test uses POSIX shell environment variable syntax.",
)
def test_terminal_tool_client_env_is_session_scoped_and_schema_hidden(monkeypatch):
    """测试客户端环境配置是否到达 shell，而不成为操作输入。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        monkeypatch.setenv("OH_CLIENT_ENV_TEST", "parent-value")
        conv_state = _create_test_conv_state(temp_dir)
        tools = TerminalTool.create(
            conv_state,
            terminal_type="subprocess",
            env={"OH_CLIENT_ENV_TEST": "client-value"},
        )
        tool = tools[0]
        assert tool.executor is not None

        properties = tool.action_type.model_json_schema()["properties"]
        assert "env" not in properties

        action = TerminalAction(command='printf "%s" "$OH_CLIENT_ENV_TEST"')
        result = tool(action)
        assert isinstance(result, TerminalObservation)
        assert "client-value" in result.text
        assert "parent-value" not in result.text

        tool(TerminalAction(command="", reset=True))
        result_after_reset = tool(action)
        assert isinstance(result_after_reset, TerminalObservation)
        assert "client-value" in result_after_reset.text

        tool.executor.close()


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="This test uses POSIX shell environment variable syntax.",
)
def test_terminal_tool_does_not_expose_observability_credentials(monkeypatch):
    credentials = (
        "LMNR_PROJECT_API_KEY",
        "OTEL_HEADERS",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_EXPORTER_OTLP_TRACES_HEADERS",
    )
    for key in credentials:
        monkeypatch.setenv(key, f"host-secret-{key}")
    monkeypatch.setenv("OH_SECRET_KEY", "host-cipher-key")
    monkeypatch.setenv("OTEL_ENDPOINT", "https://collector.example.test")

    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        tool = TerminalTool.create(
            conv_state,
            terminal_type="subprocess",
            env={"OTEL_HEADERS": "client-secret", "OH_SECRET_KEY": "client-key"},
        )[0]
        assert tool.executor is not None
        try:
            names = (*credentials, "OH_SECRET_KEY")
            values = " ".join(f"${{{name}-unset}}" for name in names)
            result = tool(TerminalAction(command=f'printf "%s\\n" {values}'))
            assert isinstance(result, TerminalObservation)
            assert result.text.count("unset") >= len(names)
            assert (
                "https://collector.example.test"
                in tool(TerminalAction(command='printf "%s" "$OTEL_ENDPOINT"')).text
            )
            for secret in (
                "host-secret-",
                "host-cipher-key",
                "client-secret",
                "client-key",
            ):
                assert secret not in result.text
        finally:
            tool.executor.close()


def test_terminal_tool_client_env_rejects_invalid_names():
    """测试客户端环境键必须是有效的 shell 环境名称。"""
    with tempfile.TemporaryDirectory() as temp_dir:
        conv_state = _create_test_conv_state(temp_dir)
        with pytest.raises(ValueError, match="Invalid terminal environment"):
            TerminalTool.create(conv_state, env={"INVALID-NAME": "value"})
