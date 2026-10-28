"""LocalConversation 中路径规则注入接缝的测试。

当智能体拉取一个路径匹配 PathTrigger 技能（“规则”）的文件时，规则内容会被追加到
ObservationEvent 的结果中
``extended_content`` 并通过 ``state.activated_path_rules`` 进行重复数据删除。
"""

from pathlib import Path

from openhands.sdk.agent import Agent
from openhands.sdk.context.agent_context import AgentContext
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event import ActionEvent, ObservationEvent
from openhands.sdk.llm import Message, MessageToolCall, TextContent
from openhands.sdk.skills import PathTrigger, Skill
from openhands.sdk.testing import TestLLM
from openhands.sdk.tool.builtins.finish import FinishObservation
from openhands.sdk.tool.builtins.invoke_skill import (
    InvokeSkillAction,
    InvokeSkillExecutor,
)
from openhands.sdk.tool.schema import Action


class _FileAction(Action):
    """最小路径承载操作（代表文件编辑器操作）。"""

    path: str
    command: str = "view"


class _NoPathAction(Action):
    """没有 ``path`` 字段的操作 (e.g. 终端命令）。"""

    command: str = "ls"


def _conversation(tmp_path: Path, rule: Skill) -> LocalConversation:
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


def _append_file_action(conv: LocalConversation, abs_path: str) -> ActionEvent:
    action_event = ActionEvent(
        thought=[TextContent(text="touch")],
        action=_FileAction(path=abs_path),
        tool_name="file_editor",
        tool_call_id="tc1",
        tool_call=MessageToolCall(
            id="tc1", name="file_editor", arguments="{}", origin="completion"
        ),
        llm_response_id="r1",
        source="agent",
    )
    with conv._state:
        conv._on_event(action_event)
    return action_event


def _observation_for(action_event: ActionEvent) -> ObservationEvent:
    return ObservationEvent(
        observation=FinishObservation(content=[TextContent(text="tool-result")]),
        action_id=action_event.id,
        tool_name=action_event.tool_name,
        tool_call_id=action_event.tool_call_id,
    )


def _inject(conv: LocalConversation, obs: ObservationEvent) -> ObservationEvent:
    result = conv._maybe_inject_path_rules(obs)
    assert isinstance(result, ObservationEvent)
    return result


def test_rule_injected_into_observation_on_matching_file_touch(tmp_path: Path) -> None:
    rule = Skill(
        name="api",
        content="Use zod for API validation.",
        trigger=PathTrigger(paths=["src/api/**/*.ts"]),
    )
    conv = _conversation(tmp_path, rule)
    try:
        action_event = _append_file_action(conv, str(tmp_path / "src" / "api" / "u.ts"))
        injected = _inject(conv, _observation_for(action_event))

        assert len(injected.extended_content) == 1
        assert "Use zod for API validation." in injected.extended_content[0].text
        # 规则内容到达工具结果后的LLM消息。
        texts = [getattr(c, "text", "") for c in injected.to_llm_message().content]
        assert any("tool-result" in t for t in texts)
        assert any("Use zod" in t for t in texts)
        # Dedup 状态记录了激活。
        assert conv._state.activated_path_rules == ["api"]
    finally:
        conv.close()


def test_rule_not_injected_for_nonmatching_path(tmp_path: Path) -> None:
    rule = Skill(
        name="api",
        content="Use zod.",
        trigger=PathTrigger(paths=["src/api/**/*.ts"]),
    )
    conv = _conversation(tmp_path, rule)
    try:
        action_event = _append_file_action(conv, str(tmp_path / "README.md"))
        injected = _inject(conv, _observation_for(action_event))
        assert injected.extended_content == []
        assert conv._state.activated_path_rules == []
    finally:
        conv.close()


def test_rule_injected_once_then_deduped(tmp_path: Path) -> None:
    rule = Skill(
        name="api",
        content="Use zod.",
        trigger=PathTrigger(paths=["src/api/**/*.ts"]),
    )
    conv = _conversation(tmp_path, rule)
    try:
        a1 = _append_file_action(conv, str(tmp_path / "src" / "api" / "a.ts"))
        first = _inject(conv, _observation_for(a1))
        assert len(first.extended_content) == 1

        a2 = _append_file_action(conv, str(tmp_path / "src" / "api" / "b.ts"))
        second = _inject(conv, _observation_for(a2))
        # 相同的规则已激活 -> 不再注入。
        assert second.extended_content == []
        assert conv._state.activated_path_rules == ["api"]
    finally:
        conv.close()


def test_injection_is_wired_through_on_event(tmp_path: Path) -> None:
    """该规则通过真实的回调链到达*已持久化*观测结果。"""
    rule = Skill(
        name="api",
        content="Use zod.",
        trigger=PathTrigger(paths=["src/api/**/*.ts"]),
    )
    conv = _conversation(tmp_path, rule)
    try:
        action_event = _append_file_action(conv, str(tmp_path / "src" / "api" / "u.ts"))
        with conv._state:
            conv._on_event(_observation_for(action_event))

        persisted = [
            e
            for e in conv.state.events
            if isinstance(e, ObservationEvent) and e.action_id == action_event.id
        ]
        assert persisted, "observation was not persisted"
        assert any("Use zod." in c.text for c in persisted[-1].extended_content)
        assert conv._state.activated_path_rules == ["api"]
    finally:
        conv.close()


def test_file_outside_workspace_is_not_matched(tmp_path: Path) -> None:
    rule = Skill(
        name="any",
        content="rule",
        trigger=PathTrigger(paths=["**/*.ts"]),
    )
    conv = _conversation(tmp_path, rule)
    try:
        # 工作区根目录之外的绝对路径 — 工作区的同级路径，因此在 POSIX 和 Windows 上它都
        # 是绝对 AND 外部路径。
        #
        action_event = _append_file_action(
            conv, str(tmp_path.parent / "outside" / "x.ts")
        )
        injected = _inject(conv, _observation_for(action_event))
        assert injected.extended_content == []
        assert conv._state.activated_path_rules == []
    finally:
        conv.close()


def test_symlinked_workspace_root_still_matches(tmp_path: Path) -> None:
    """即使操作路径和工作区根仅不同，规则也会触发
    通过符号链接 (e.g. macOS /tmp -> /private/tmp); resolve() 回退方案中
    ``_touched_rule_path`` 恢复工作区相对路径。"""
    real = tmp_path / "real_ws"
    real.mkdir()
    link = tmp_path / "link_ws"
    try:
        link.symlink_to(real)
    except OSError:
        import pytest

        pytest.skip("symlinks not supported on this platform")

    rule = Skill(
        name="api", content="Use zod.", trigger=PathTrigger(paths=["src/api/**/*.ts"])
    )
    conv = _conversation(link, rule)  # 工作区是符号链接形式
    try:
        # 操作报告已解析的（真实）路径 - 修复处理的不匹配。
        action_event = _append_file_action(conv, str(real / "src" / "api" / "u.ts"))
        injected = _inject(conv, _observation_for(action_event))
        assert any("Use zod." in c.text for c in injected.extended_content)
        assert conv._state.activated_path_rules == ["api"]
    finally:
        conv.close()


def test_non_path_action_does_not_inject(tmp_path: Path) -> None:
    """没有 ``path`` 字段的工具操作永远不会触发规则。"""
    rule = Skill(name="any", content="rule", trigger=PathTrigger(paths=["**/*"]))
    conv = _conversation(tmp_path, rule)
    try:
        action_event = ActionEvent(
            thought=[TextContent(text="run")],
            action=_NoPathAction(command="ls"),
            tool_name="terminal",
            tool_call_id="tc1",
            tool_call=MessageToolCall(
                id="tc1", name="terminal", arguments="{}", origin="completion"
            ),
            llm_response_id="r1",
            source="agent",
        )
        with conv._state:
            conv._on_event(action_event)
        injected = _inject(conv, _observation_for(action_event))
        assert injected.extended_content == []
        assert conv._state.activated_path_rules == []
    finally:
        conv.close()


def test_relative_path_action_matched_against_workspace(tmp_path: Path) -> None:
    """工作区相对操作路径按原样匹配。"""
    rule = Skill(
        name="api", content="Use zod.", trigger=PathTrigger(paths=["src/api/**/*.ts"])
    )
    conv = _conversation(tmp_path, rule)
    try:
        action_event = _append_file_action(conv, "src/api/users.ts")  # 亲戚
        injected = _inject(conv, _observation_for(action_event))
        assert any("Use zod." in c.text for c in injected.extended_content)
    finally:
        conv.close()


def test_observation_extended_content_serialization_round_trip() -> None:
    """注入的规则在事件日志持久化 + 重新加载中幸存下来，并保持不变
    在重建的 LLM 消息中的工具结果之后排序。"""
    obs = ObservationEvent(
        observation=FinishObservation(content=[TextContent(text="result")]),
        action_id="a",
        tool_name="t",
        tool_call_id="c",
        extended_content=[TextContent(text="RULE")],
    )
    back = ObservationEvent.model_validate_json(obs.model_dump_json())
    assert [c.text for c in back.extended_content] == ["RULE"]
    texts = [getattr(c, "text", "") for c in back.to_llm_message().content]
    assert "result" in texts and "RULE" in texts
    assert texts.index("RULE") > texts.index("result")  # 结果后附加规则


def test_fork_copies_activated_path_rules(tmp_path: Path) -> None:
    rule = Skill(
        name="api", content="Use zod.", trigger=PathTrigger(paths=["src/api/**/*.ts"])
    )
    conv = _conversation(tmp_path, rule)
    try:
        a = _append_file_action(conv, str(tmp_path / "src" / "api" / "u.ts"))
        with conv._state:
            conv._on_event(_observation_for(a))
        assert conv._state.activated_path_rules == ["api"]

        forked = conv.fork()
        try:
            assert forked._state.activated_path_rules == ["api"]
        finally:
            forked.close()
    finally:
        conv.close()


def test_path_rule_not_invocable_via_invoke_skill(tmp_path: Path) -> None:
    """路径规则只能通过文件触摸激活，而不能通过 invoke_skill 激活。"""
    rule = Skill(name="api", content="Use zod.", trigger=PathTrigger(paths=["**/*.ts"]))
    conv = _conversation(tmp_path, rule)
    try:
        obs = InvokeSkillExecutor()(InvokeSkillAction(name="api"), conv)
        assert obs.is_error
        assert "cannot be invoked directly" in obs.text
    finally:
        conv.close()


def test_no_injection_when_agent_has_no_context(tmp_path: Path) -> None:
    """当智能体没有 agent_context 时，接缝是安全的无操作。"""
    agent = Agent(
        llm=TestLLM.from_messages(
            [Message(role="assistant", content=[TextContent(text="ok")])],
            model="test-model",
        ),
        tools=[],
        include_default_tools=[],
        agent_context=None,
    )
    conv = LocalConversation(
        agent=agent,
        workspace=tmp_path,
        persistence_dir=tmp_path / "conversation",
        delete_on_close=True,
    )
    try:
        action_event = _append_file_action(conv, str(tmp_path / "src" / "api" / "u.ts"))
        injected = _inject(conv, _observation_for(action_event))
        assert injected.extended_content == []
    finally:
        conv.close()


def test_no_injection_when_action_not_correlated(tmp_path: Path) -> None:
    """action_id 不在事件日志中的观测结果不会产生任何路径。"""
    rule = Skill(name="any", content="rule", trigger=PathTrigger(paths=["**/*"]))
    conv = _conversation(tmp_path, rule)
    try:
        orphan = ObservationEvent(
            observation=FinishObservation(content=[TextContent(text="x")]),
            action_id="nonexistent-action-id",
            tool_name="file_editor",
            tool_call_id="tc9",
        )
        injected = _inject(conv, orphan)
        assert injected.extended_content == []
        assert conv._state.activated_path_rules == []
    finally:
        conv.close()
