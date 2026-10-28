"""端到端检查路径规则是否在 REAL 文件编辑器操作上触发。

注入接缝从操作的 ``path`` 字段 (``local_conversation._touched_rule_path``) 读取触摸路
径。 这些测试使用实际
``FileEditorAction`` / ``FileEditorObservation`` 来自 OpenHands-tools，因此该字段的重
命名（这将默默地对整个
功能进行无操作）被捕获。
"""

from pathlib import Path

from openhands.sdk.agent import Agent
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event import ActionEvent, ObservationEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.skills import PathTrigger, Skill
from openhands.sdk.testing import TestLLM
from openhands.tools.file_editor import FileEditorAction, FileEditorObservation
from openhands.tools.file_editor.definition import CommandLiteral


def _conversation(tmp_path: Path) -> LocalConversation:
    rule = Skill(
        name="api",
        content="Use zod for API validation.",
        trigger=PathTrigger(paths=["src/api/**/*.ts"]),
    )
    agent = Agent(
        llm=TestLLM.from_messages(
            [Message(role="assistant", content=[TextContent(text="ok")])],
            model="test-model",
        ),
        tools=[],
        include_default_tools=[],
        agent_context=AgentContext(skills=[rule]),
    )
    return LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )


def _action_event(path: str, command: CommandLiteral = "view") -> ActionEvent:
    return ActionEvent(
        thought=[TextContent(text="touch")],
        action=FileEditorAction(command=command, path=path),
        tool_name="str_replace_editor",
        tool_call_id="tc1",
        tool_call=MessageToolCall(
            id="tc1", name="str_replace_editor", arguments="{}", origin="completion"
        ),
        llm_response_id="r1",
        source="agent",
    )


def test_real_file_editor_action_triggers_path_rule(tmp_path: Path) -> None:
    """匹配路径上的真实 FileEditorAction 会注入规则。"""
    conv = _conversation(tmp_path)
    try:
        action_event = _action_event(str(tmp_path / "src" / "api" / "users.ts"))
        with conv._state:
            conv._on_event(action_event)

        obs = ObservationEvent(
            observation=FileEditorObservation(
                command="view", content=[TextContent(text="<file contents>")]
            ),
            action_id=action_event.id,
            tool_name="str_replace_editor",
            tool_call_id="tc1",
        )
        with conv._state:
            conv._on_event(obs)

        persisted = [
            e
            for e in conv.state.events
            if isinstance(e, ObservationEvent) and e.action_id == action_event.id
        ]
        assert persisted, "observation not persisted"
        assert any(
            "Use zod for API validation." in c.text
            for c in persisted[-1].extended_content
        )
        assert conv._state.activated_path_rules == ["api"]
    finally:
        conv.close()


def test_real_file_editor_action_nonmatching_path(tmp_path: Path) -> None:
    conv = _conversation(tmp_path)
    try:
        action_event = _action_event(str(tmp_path / "README.md"))
        with conv._state:
            conv._on_event(action_event)
        obs = ObservationEvent(
            observation=FileEditorObservation(command="view"),
            action_id=action_event.id,
            tool_name="str_replace_editor",
            tool_call_id="tc1",
        )
        with conv._state:
            conv._on_event(obs)

        persisted = next(
            e
            for e in conv.state.events
            if isinstance(e, ObservationEvent) and e.action_id == action_event.id
        )
        assert persisted.extended_content == []
        assert conv._state.activated_path_rules == []
    finally:
        conv.close()


def test_real_file_editor_create_command_triggers_rule(tmp_path: Path) -> None:
    """规则也会在 ``create`` 上触发（击败 Claude Code 的写入/创建间隙）。"""
    conv = _conversation(tmp_path)
    try:
        action_event = _action_event(
            str(tmp_path / "src" / "api" / "new.ts"), command="create"
        )
        with conv._state:
            conv._on_event(action_event)
        obs = ObservationEvent(
            observation=FileEditorObservation(command="create", prev_exist=False),
            action_id=action_event.id,
            tool_name="str_replace_editor",
            tool_call_id="tc1",
        )
        with conv._state:
            conv._on_event(obs)

        persisted = next(
            e
            for e in conv.state.events
            if isinstance(e, ObservationEvent) and e.action_id == action_event.id
        )
        assert any("Use zod" in c.text for c in persisted.extended_content)
    finally:
        conv.close()
