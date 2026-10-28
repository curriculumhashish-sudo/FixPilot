"""测试旧版工具名称兼容性垫片。"""

import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Self
from unittest.mock import patch

import pytest
from litellm import ChatCompletionMessageToolCall
from litellm.types.utils import (
    Choices,
    Function,
    Message as LiteLLMMessage,
    ModelResponse,
)
from pydantic import SecretStr

from openhands.sdk.agent import Agent, utils as agent_utils
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.event import ActionEvent, AgentErrorEvent, ObservationEvent
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.tool import Action, Observation, Tool, ToolExecutor, register_tool
from openhands.sdk.tool.tool import ToolDefinition


if TYPE_CHECKING:
    from openhands.sdk.conversation.state import ConversationState


FILE_EDITOR_TOOL_NAME = "file_editor"
FILE_EDITOR_TOOL_SPEC = "FileEditorCompatTool"
TERMINAL_TOOL_NAME = "terminal"
TERMINAL_TOOL_SPEC = "TerminalCompatTool"


class _TerminalAction(Action):
    command: str


class _TerminalObservation(Observation):
    pass


class _TerminalExecutor(ToolExecutor[_TerminalAction, _TerminalObservation]):
    def __call__(
        self,
        action: _TerminalAction,
        conversation: LocalConversation | None = None,
    ) -> _TerminalObservation:
        working_dir = conversation.workspace.working_dir if conversation else None
        completed = subprocess.run(
            action.command,
            cwd=working_dir,
            capture_output=True,
            text=True,
            check=False,
            shell=True,
        )
        return _TerminalObservation.from_text(completed.stdout or completed.stderr)


class _TerminalTool(ToolDefinition[_TerminalAction, _TerminalObservation]):
    name = TERMINAL_TOOL_NAME

    @classmethod
    def create(cls, conv_state: "ConversationState | None" = None) -> Sequence[Self]:
        return [
            cls(
                description="Execute shell commands",
                action_type=_TerminalAction,
                observation_type=_TerminalObservation,
                executor=_TerminalExecutor(),
            )
        ]


class _FileEditorAction(Action):
    command: str
    path: str
    old_str: str | None = None
    new_str: str | None = None
    file_text: str | None = None
    insert_line: int | None = None
    view_range: list[int] | None = None


class _FileEditorObservation(Observation):
    pass


class _FileEditorExecutor(ToolExecutor[_FileEditorAction, _FileEditorObservation]):
    def __call__(
        self,
        action: _FileEditorAction,
        conversation: LocalConversation | None = None,
    ) -> _FileEditorObservation:
        path = Path(action.path)
        if action.command == "str_replace":
            if action.old_str is None:
                raise ValueError("old_str is required for str_replace")
            updated = path.read_text().replace(action.old_str, action.new_str or "", 1)
            path.write_text(updated)
            return _FileEditorObservation.from_text("replaced")
        if action.command == "view":
            return _FileEditorObservation.from_text(path.read_text())
        raise ValueError(f"Unsupported file_editor command: {action.command}")


class _FileEditorTool(ToolDefinition[_FileEditorAction, _FileEditorObservation]):
    name = FILE_EDITOR_TOOL_NAME

    @classmethod
    def create(cls, conv_state: "ConversationState | None" = None) -> Sequence[Self]:
        return [
            cls(
                description="Edit files",
                action_type=_FileEditorAction,
                observation_type=_FileEditorObservation,
                executor=_FileEditorExecutor(),
            )
        ]


register_tool(TERMINAL_TOOL_SPEC, _TerminalTool)
register_tool(FILE_EDITOR_TOOL_SPEC, _FileEditorTool)


def _make_agent(*tool_specs: str) -> Agent:
    llm = LLM(
        model="test-model",
        usage_id="test-llm",
        api_key=SecretStr("test-key"),
        base_url="http://test",
    )
    return Agent(llm=llm, tools=[Tool(name=tool_spec) for tool_spec in tool_specs])


def _model_response(tool_name: str, arguments: dict[str, object]) -> ModelResponse:
    return ModelResponse(
        id="mock-response-1",
        choices=[
            Choices(
                index=0,
                message=LiteLLMMessage(
                    role="assistant",
                    content="Using a tool.",
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id="call_1",
                            type="function",
                            function=Function(
                                name=tool_name,
                                arguments=json.dumps(arguments),
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        created=0,
        model="test-model",
        object="chat.completion",
    )


def _run_tool_call(
    tmp_path,
    *,
    tool_name: str,
    arguments: dict[str, object],
    tool_names: tuple[str, ...],
) -> list[object]:
    agent = _make_agent(*tool_names)
    conversation = Conversation(agent=agent, workspace=str(tmp_path))
    events: list[object] = []

    with patch(
        "openhands.sdk.llm.llm.litellm_completion",
        return_value=_model_response(tool_name, arguments),
    ):
        conversation.send_message(
            Message(role="user", content=[TextContent(text="Please help.")])
        )
        agent.step(conversation, on_event=events.append)

    return events


def test_bash_alias_executes_terminal_tool(tmp_path):
    events = _run_tool_call(
        tmp_path,
        tool_name="bash",
        arguments={"command": "echo hello"},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    observation_event = next(e for e in events if isinstance(e, ObservationEvent))

    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.tool_call.name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    assert getattr(action_event.action, "command") == "echo hello"
    assert "hello" in observation_event.observation.text


def test_str_replace_alias_infers_file_editor_command(tmp_path):
    test_file = tmp_path / "sample.py"
    test_file.write_text("value = 'old'\n")

    events = _run_tool_call(
        tmp_path,
        tool_name="str_replace",
        arguments={
            "path": str(test_file),
            "old_str": "'old'",
            "new_str": "'new'",
        },
        tool_names=(FILE_EDITOR_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == FILE_EDITOR_TOOL_NAME
    assert action_event.tool_call.name == FILE_EDITOR_TOOL_NAME
    assert action_event.action is not None
    assert getattr(action_event.action, "command") == "str_replace"
    assert test_file.read_text() == "value = 'new'\n"


def test_shell_tool_name_falls_back_to_terminal(tmp_path):
    events = _run_tool_call(
        tmp_path,
        tool_name="ls",
        arguments={},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    assert getattr(action_event.action, "command") == "ls"


@pytest.mark.parametrize("tool_name", ["cat /etc/passwd", "ls; echo pwned"])
def test_shell_tool_name_requires_exact_command_name(tmp_path, tool_name):
    events = _run_tool_call(
        tmp_path,
        tool_name=tool_name,
        arguments={},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]
    observations = [e for e in events if isinstance(e, ObservationEvent)]

    assert not observations
    assert action_event.tool_name == tool_name
    assert action_event.action is None
    assert errors
    assert errors[0].tool_name == tool_name


def test_grep_without_pattern_does_not_fall_back_to_terminal(tmp_path):
    events = _run_tool_call(
        tmp_path,
        tool_name="grep",
        arguments={"path": str(tmp_path)},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]
    observations = [e for e in events if isinstance(e, ObservationEvent)]

    assert not observations
    assert action_event.tool_name == "grep"
    assert action_event.action is None
    assert errors
    assert errors[0].tool_name == "grep"


def test_shell_tool_name_does_not_fall_back_without_terminal(tmp_path):
    events = _run_tool_call(
        tmp_path,
        tool_name="ls",
        arguments={},
        tool_names=(FILE_EDITOR_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]
    observations = [e for e in events if isinstance(e, ObservationEvent)]

    assert not observations
    assert action_event.tool_name == "ls"
    assert action_event.action is None
    assert errors
    assert errors[0].tool_name == "ls"


@pytest.mark.skipif(
    os.name == "nt",
    reason="covered by dedicated Windows command-generation tests",
)
def test_grep_arguments_can_fall_back_to_terminal(tmp_path):
    test_file = tmp_path / "needle.txt"
    test_file.write_text("needle\n")

    events = _run_tool_call(
        tmp_path,
        tool_name="grep",
        arguments={"pattern": "needle", "path": str(tmp_path)},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    observation_event = next(e for e in events if isinstance(e, ObservationEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    command = getattr(action_event.action, "command")
    assert command.startswith(
        ("rg ", '"rg" ', "grep ", '"grep" ', "python ", '"python" ')
    )
    assert "needle" in command
    assert "needle.txt" in observation_event.observation.text


def test_grep_terminal_command_prefers_ripgrep(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_utils.shutil,
        "which",
        lambda name: "/bin/tool" if name == "rg" else None,
    )

    command = agent_utils._build_grep_terminal_command(
        {"pattern": "needle", "path": str(tmp_path), "include": "*.py"}
    )

    assert command is not None
    assert command.startswith(("rg ", '"rg" '))
    assert "--sortr=modified" in command
    assert "*.py" in command


def test_grep_terminal_command_falls_back_to_grep(monkeypatch, tmp_path):
    monkeypatch.setattr(
        agent_utils.shutil,
        "which",
        lambda name: "/bin/grep" if name == "grep" else None,
    )

    command = agent_utils._build_grep_terminal_command(
        {"pattern": "needle", "path": str(tmp_path), "include": "*.py"}
    )

    assert command is not None
    assert command.startswith(("grep ", '"grep" '))
    assert "--include=*.py" in command
    assert "python -c" not in command


def test_grep_terminal_command_falls_back_to_python_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_utils.os, "name", "nt", raising=False)
    monkeypatch.setattr(agent_utils.shutil, "which", lambda _: None)

    command = agent_utils._build_grep_terminal_command(
        {"pattern": "needle", "path": str(tmp_path)}
    )

    assert command is not None
    assert command.startswith(("python ", '"python" '))
    assert "grep -RIn" not in command
    assert "\n" not in command


def test_security_risk_typo_normalized(tmp_path):
    """测试 security_risk 拼写错误在验证之前是否已标准化。"""
    events = _run_tool_call(
        tmp_path,
        tool_name="bash",
        arguments={"command": "echo hello", "security_rort": "LOW"},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    observation_event = next(e for e in events if isinstance(e, ObservationEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    assert "hello" in observation_event.observation.text


def test_file_editor_command_inferred_from_old_str(tmp_path):
    """测试当 old_str 存在时是否推断出 file_editor 命令。"""
    test_file = tmp_path / "sample.py"
    test_file.write_text("value = 'old'\n")

    events = _run_tool_call(
        tmp_path,
        tool_name="str_replace_editor",
        arguments={
            "path": str(test_file),
            "old_str": "'old'",
            "new_str": "'new'",
        },
        tool_names=(FILE_EDITOR_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == FILE_EDITOR_TOOL_NAME
    assert action_event.action is not None
    assert getattr(action_event.action, "command") == "str_replace"
    assert test_file.read_text() == "value = 'new'\n"


def test_file_editor_empty_args_emits_error(tmp_path):
    """测试带有空参数的 file_editor 是否会产生有用的错误。"""
    events = _run_tool_call(
        tmp_path,
        tool_name="file_editor",
        arguments={},
        tool_names=(FILE_EDITOR_TOOL_SPEC,),
    )

    errors = [e for e in events if isinstance(e, AgentErrorEvent)]
    observations = [e for e in events if isinstance(e, ObservationEvent)]

    assert not observations
    assert len(errors) == 1
    error_event = errors[0]
    assert "file_editor" in error_event.error
    assert "Cannot infer" in error_event.error or "command" in error_event.error.lower()
    # 不应该是原始 Pydantic 验证错误
    assert "Field required" not in error_event.error
    assert "validation errors" not in error_event.error


def test_str_replace_alias_error_message_shows_file_editor(tmp_path):
    """测试 str_replace 别名是否显示错误的“file_editor”，而不是“str_replace”。"""
    events = _run_tool_call(
        tmp_path,
        tool_name="str_replace",
        arguments={},  # 空参数应该会失败并出现有用的错误
        tool_names=(FILE_EDITOR_TOOL_SPEC,),
    )

    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert len(errors) == 1
    error_event = errors[0]
    # 该错误应引用“file_editor”（已解析的名称），而不是“str_replace”，因为 str_replace
    # 是 file_editor 的别名
    #
    assert "file_editor" in error_event.error
    assert "Cannot infer" in error_event.error
    # 不应该在错误消息中显示 str_replace，因为它解析为 file_editor
    assert "for tool 'str_replace'" not in error_event.error


def test_grep_pattern_with_shell_metacharacters_is_escaped(tmp_path):
    """验证 shlex.join() 防止 grep 模式中的 shell 注入。"""
    events = _run_tool_call(
        tmp_path,
        tool_name="grep",
        arguments={"pattern": "; rm -rf /", "path": str(tmp_path)},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    # shlex.join() 引用模式，防止 shell 注入
    assert "; rm -rf /" in getattr(action_event.action, "command")


def test_explicitly_registered_tool_not_hijacked_by_alias():
    """Regression: 显式注册的“bash”工具不应被劫持到终端。

    当显式注册名为“bash”的工具时，应保留它而不是别名为“terminal”。 这可以防止合法工具
    被兼容性填充程序悄悄覆盖。
    """
    from openhands.sdk.agent.utils import normalize_tool_call

    # 当 'bash' 与 'terminal' 一起显式注册时，normalize_tool_call 应保留 'bash'，而不是
    # 'terminal' 的别名
    #
    available_tools = {"bash", "terminal", "file_editor"}

    # 使用“bash”工具名称进行测试 - 不应该是别名，因为它已注册
    tool_name, args = normalize_tool_call(
        "bash", {"command": "echo hi"}, available_tools
    )
    assert tool_name == "bash", (
        "Explicitly registered 'bash' should not be aliased to terminal"
    )

    # 使用“ls”工具名称进行测试 - 仍应为回退方案，因为它已注册为不
    tool_name, args = normalize_tool_call("ls", {}, available_tools)
    assert tool_name == "terminal", "Unknown 'ls' should fallback to terminal"

    # 使用“str_replace”进行测试 - 应该使用别名（别名目标已注册）
    tool_name, args = normalize_tool_call(
        "str_replace", {"old_str": "x", "new_str": "y"}, available_tools
    )
    assert tool_name == "file_editor", "str_replace alias should map to file_editor"


def test_malformed_tool_name_str_replace_xml_tag(tmp_path):
    """测试格式错误的工具名称（例如“str_replace </parameter'”）是否已修复。

    这解决了 LLMs 发出 XML/HTML 标签片段的错误。 该修复提取第一个有效标识符并将其映射
    到正确的工具。
    """
    test_file = tmp_path / "sample.py"
    test_file.write_text("value = 'old'\n")

    events = _run_tool_call(
        tmp_path,
        tool_name="str_replace </parameter",  # 格式错误：附加了 XML 标签
        arguments={
            "path": str(test_file),
            "old_str": "'old'",
            "new_str": "'new'",
        },
        tool_names=(FILE_EDITOR_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors, f"Expected no errors but got: {errors}"
    assert action_event.tool_name == FILE_EDITOR_TOOL_NAME
    assert action_event.action is not None
    assert getattr(action_event.action, "command") == "str_replace"
    assert test_file.read_text() == "value = 'new'\n"


def test_malformed_tool_name_str_replace_function_tag(tmp_path):
    """测试格式错误的工具名称（例如“str_replace</function>”）是否已修复。"""
    test_file = tmp_path / "sample.py"
    test_file.write_text("value = 'old'\n")

    events = _run_tool_call(
        tmp_path,
        tool_name="str_replace</function>",  # 格式错误：附加了 XML 标签
        arguments={
            "path": str(test_file),
            "old_str": "'old'",
            "new_str": "'new'",
        },
        tool_names=(FILE_EDITOR_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors, f"Expected no errors but got: {errors}"
    assert action_event.tool_name == FILE_EDITOR_TOOL_NAME
    assert action_event.action is not None
    assert test_file.read_text() == "value = 'new'\n"


def test_malformed_tool_name_str_replace_editor_xml_tag(tmp_path):
    """测试格式错误的“str_replace_editor </tool_call>”名称是否已修复。"""
    test_file = tmp_path / "sample.py"
    test_file.write_text("value = 'old'\n")

    events = _run_tool_call(
        tmp_path,
        tool_name="str_replace_editor </tool_call>",  # 畸形
        arguments={
            "path": str(test_file),
            "old_str": "'old'",
            "new_str": "'new'",
        },
        tool_names=(FILE_EDITOR_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors, f"Expected no errors but got: {errors}"
    assert action_event.tool_name == FILE_EDITOR_TOOL_NAME
    assert action_event.action is not None
    assert test_file.read_text() == "value = 'new'\n"


def test_malformed_tool_name_bash_xml_tag(tmp_path):
    """测试格式错误的工具名称（例如“bash </request>”）是否已修复。"""
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello\n")

    events = _run_tool_call(
        tmp_path,
        tool_name="bash </request>",  # 格式错误：附加了 XML 标签
        arguments={"command": "cat hello.txt"},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    observation_event = next(e for e in events if isinstance(e, ObservationEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors, f"Expected no errors but got: {errors}"
    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    assert "hello" in observation_event.observation.text


def test_malformed_tool_name_no_fix_when_no_match():
    """测试与任何别名不匹配的真正格式错误的名称是否返回原始名称。"""
    from openhands.sdk.agent.utils import normalize_tool_call

    available_tools = {"terminal", "file_editor"}

    # “straight”不匹配任何别名或工具，因此它应该保持不变
    tool_name, args = normalize_tool_call("straight", {}, available_tools)
    assert tool_name == "straight", "Unknown malformed name should remain unchanged"

    # “xyz123 </invalid>”与任何已知别名都不匹配
    tool_name, args = normalize_tool_call("xyz123 </invalid>", {}, available_tools)
    assert tool_name == "xyz123 </invalid>", (
        "Non-matching malformed name should remain unchanged"
    )


def test_malformed_tool_name_alias_precedence():
    """测试别名是否能从格式错误的名称中正确解析。

    当像“str_replace </parameter'”这样的格式错误的名称被固定为“str_replace”时，它应该
    通过别名映射到“file_editor”。
    """
    from openhands.sdk.agent.utils import normalize_tool_call

    available_tools = {"terminal", "file_editor"}

    # 'str_replace </parameter' 固定为 'str_replace'，然后别名为 'file_editor'
    tool_name, args = normalize_tool_call(
        "str_replace </parameter",
        {"path": "/tmp/test", "old_str": "a", "new_str": "b"},
        available_tools,
    )
    assert tool_name == "file_editor", (
        "Malformed str_replace should map to file_editor via alias"
    )


def test_git_alias_executes_terminal_tool(tmp_path):
    """测试“git”工具名称是否别名为“terminal”。"""
    events = _run_tool_call(
        tmp_path,
        tool_name="git",
        arguments={"command": "status"},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.tool_call.name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    assert getattr(action_event.action, "command") == "git status"


def test_reset_alias_executes_terminal_tool(tmp_path):
    """测试“重置”工具名称是否别名为“终端”。"""
    events = _run_tool_call(
        tmp_path,
        tool_name="reset",
        arguments={"command": "clear"},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.tool_call.name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    assert getattr(action_event.action, "command") == "reset clear"


@pytest.mark.parametrize(
    ("tool_name", "command", "expected"),
    [
        ("git", "status", "git status"),
        ("git", "git status", "git status"),
        ("git", "git", "git"),
        ("git", "\tgit\tstatus", "\tgit\tstatus"),
        ("git", "github status", "git github status"),
        ("git", "gitk", "git gitk"),
        ("reset", "clear", "reset clear"),
        ("reset", "reset clear", "reset clear"),
    ],
)
def test_terminal_prefix_alias_only_adds_a_missing_executable(
    tool_name, command, expected
):
    normalized_tool_name, arguments = agent_utils.normalize_tool_call(
        tool_name, {"command": command}, {TERMINAL_TOOL_NAME}
    )

    assert normalized_tool_name == TERMINAL_TOOL_NAME
    assert arguments["command"] == expected


def test_shell_tool_name_git_falls_back_to_terminal(tmp_path):
    """测试不带参数的 'git' 是否回退到终端。"""
    events = _run_tool_call(
        tmp_path,
        tool_name="git",
        arguments={},
        tool_names=(TERMINAL_TOOL_SPEC,),
    )

    action_event = next(e for e in events if isinstance(e, ActionEvent))
    errors = [e for e in events if isinstance(e, AgentErrorEvent)]

    assert not errors
    assert action_event.tool_name == TERMINAL_TOOL_NAME
    assert action_event.action is not None
    assert getattr(action_event.action, "command") == "git"
