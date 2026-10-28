"""单元测试用于提前停止公用事业。"""

from typing import cast

from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible.action import ActionEvent
from openhands.sdk.llm import MessageToolCall, TextContent
from openhands.tools.file_editor.definition import CommandLiteral, FileEditorAction
from openhands.tools.terminal.definition import TerminalAction
from tests.integration.early_stopper import (
    BashCommandPruner,
    CompositeEarlyStopper,
    EarlyStopResult,
    FileEditPruner,
)


def create_file_editor_event(command: CommandLiteral, path: str) -> ActionEvent:
    """用 FileEditorAction 创建一个真实的 ActionEvent。"""
    action = FileEditorAction(command=command, path=path)
    return ActionEvent(
        source="agent",
        thought=[TextContent(text=f"Performing {command} on {path}")],
        action=action,
        tool_name="file_editor",
        tool_call_id=f"call_{command}_{path.replace('/', '_')}",
        tool_call=MessageToolCall(
            id=f"call_{command}_{path.replace('/', '_')}",
            name="file_editor",
            arguments=f'{{"command": "{command}", "path": "{path}"}}',
            origin="completion",
        ),
        llm_response_id="test_response_id",
    )


def create_terminal_event(command: str) -> ActionEvent:
    """用 TerminalAction 创建一个真实的 ActionEvent。"""
    action = TerminalAction(command=command)
    return ActionEvent(
        source="agent",
        thought=[TextContent(text=f"Running command: {command}")],
        action=action,
        tool_name="terminal",
        tool_call_id=f"call_terminal_{hash(command)}",
        tool_call=MessageToolCall(
            id=f"call_terminal_{hash(command)}",
            name="terminal",
            arguments=f'{{"command": "{command}"}}',
            origin="completion",
        ),
        llm_response_id="test_response_id",
    )


class TestFileEditPruner:
    """测试 FileEditPruner。"""

    def test_no_events_returns_no_stop(self):
        """空事件列表不应触发停止。"""
        pruner = FileEditPruner()
        result = pruner.check([])
        assert result.should_stop is False
        assert result.reason is None

    def test_view_command_not_blocked(self):
        """查看命令不应触发停止。"""
        pruner = FileEditPruner()
        event = create_file_editor_event(command="view", path="/test.py")
        result = pruner.check(cast(list[Event], [event]))
        assert result.should_stop is False

    def test_create_command_triggers_stop(self):
        """创建命令应触发停止。"""
        pruner = FileEditPruner()
        event = create_file_editor_event(command="create", path="/new_file.py")
        result = pruner.check(cast(list[Event], [event]))
        assert result.should_stop is True
        assert result.reason is not None
        assert "create" in result.reason
        assert "new_file.py" in result.reason

    def test_str_replace_triggers_stop(self):
        """str_replace 命令应触发停止。"""
        pruner = FileEditPruner()
        event = create_file_editor_event(command="str_replace", path="/test.py")
        result = pruner.check(cast(list[Event], [event]))
        assert result.should_stop is True
        assert result.reason is not None
        assert "str_replace" in result.reason

    def test_custom_forbidden_commands(self):
        """应尊重自定义禁止命令。"""
        # 注意：“undo_edit”是有效的FileEditorAction命令
        pruner = FileEditPruner(forbidden_commands=["undo_edit"])
        event = create_file_editor_event(command="undo_edit", path="/test.py")
        result = pruner.check(cast(list[Event], [event]))
        assert result.should_stop is True

    def test_non_matching_event_not_stopped(self):
        """非文件编辑器事件不应触发停止。"""
        pruner = FileEditPruner()
        # 终端事件不应触发文件编辑修剪器
        event = create_terminal_event(command="ls -la")
        result = pruner.check(cast(list[Event], [event]))
        assert result.should_stop is False


class TestBashCommandPruner:
    """测试 BashCommandPruner。"""

    def test_no_events_returns_no_stop(self):
        """空事件不应触发停止。"""
        pruner = BashCommandPruner(forbidden_patterns=["rm -rf"])
        result = pruner.check([])
        assert result.should_stop is False

    def test_forbidden_pattern_triggers_stop(self):
        """禁止的命令模式应触发停止。"""
        pruner = BashCommandPruner(forbidden_patterns=["rm -rf"])
        event = create_terminal_event(command="rm -rf /important")
        result = pruner.check(cast(list[Event], [event]))
        assert result.should_stop is True
        assert result.reason is not None
        assert "rm -rf" in result.reason

    def test_safe_command_not_stopped(self):
        """安全命令不应触发停止。"""
        pruner = BashCommandPruner(forbidden_patterns=["rm -rf"])
        event = create_terminal_event(command="ls -la")
        result = pruner.check(cast(list[Event], [event]))
        assert result.should_stop is False


class TestCompositeEarlyStopper:
    """测试 CompositeEarlyStopper。"""

    def test_empty_stoppers_never_stops(self):
        """空的停止清单永远不应该停止。"""
        composite = CompositeEarlyStopper(stoppers=[])
        result = composite.check([])
        assert result.should_stop is False

    def test_stops_on_first_match(self):
        """应停在第一个匹配的塞子上。"""
        # 创建两个修剪器
        file_pruner = FileEditPruner()
        bash_pruner = BashCommandPruner(forbidden_patterns=["dangerous"])

        composite = CompositeEarlyStopper(stoppers=[file_pruner, bash_pruner])

        # 通过文件编辑进行测试
        event = create_file_editor_event(command="create", path="/test.py")
        result = composite.check(cast(list[Event], [event]))
        assert result.should_stop is True

    def test_no_match_continues(self):
        """如果没有匹配的塞子，则不应停止。"""
        file_pruner = FileEditPruner()
        composite = CompositeEarlyStopper(stoppers=[file_pruner])

        # 终端事件不应触发文件编辑修剪器
        event = create_terminal_event(command="ls -la")
        result = composite.check(cast(list[Event], [event]))
        assert result.should_stop is False


class TestEarlyStopResult:
    """测试 EarlyStopResult 模型。"""

    def test_default_values(self):
        """测试默认值。"""
        result = EarlyStopResult(should_stop=False)
        assert result.should_stop is False
        assert result.reason is None

    def test_with_reason(self):
        """测试有道理。"""
        result = EarlyStopResult(should_stop=True, reason="Test reason")
        assert result.should_stop is True
        assert result.reason == "Test reason"
