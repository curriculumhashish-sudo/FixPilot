"""类似集成的测试记录 LocalConversation 恢复语义。

这些测试旨在成为对话恢复的行为规范：

- 正常生命周期：开始 -> 发送/运行 -> 发送/运行 -> 关闭 -> 恢复 -> 发送/运行
- 如果智能体工具集发生更改，恢复必须将失败（工具是系统提示词的一部分）
- 如果其他智能体配置更改（LLM、上下文压缩器、技能），则恢复必须成功
"""

from __future__ import annotations

import json
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
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

from openhands.sdk import Agent
from openhands.sdk.context import AgentContext, KeywordTrigger, Skill
from openhands.sdk.context.condenser.llm_summarizing_condenser import (
    LLMSummarizingCondenser,
)
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.event import ActionEvent, MessageEvent
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.event.types import ROOT_PARENT_ID
from openhands.sdk.llm import LLM
from openhands.sdk.llm.utils.openhands_provider import (
    LITELLM_PROXY_PREFIX,
    OPENHANDS_LLM_PROXY_BASE_URL,
    OPENHANDS_PROVIDER_PREFIX,
)
from openhands.sdk.security.llm_analyzer import LLMSecurityAnalyzer
from openhands.sdk.security.risk import SecurityRisk
from openhands.sdk.tool import Tool, register_tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool
from tests.conftest import create_mock_litellm_response


pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="TerminalTool restore tests require the Unix terminal backend.",
)


register_tool("TerminalTool", TerminalTool)
register_tool("FileEditorTool", FileEditorTool)


class DifferentAgent(Agent):
    pass


@dataclass
class RestoreLifecycle:
    """可重复使用的工具，用于执行持久性/恢复生命周期。"""

    workspace_dir: Path
    persistence_base_dir: Path
    conversation_id: uuid.UUID | None = None

    def create_conversation(self, agent: Agent) -> LocalConversation:
        return LocalConversation(
            agent=agent,
            workspace=self.workspace_dir,
            persistence_dir=self.persistence_base_dir,
            conversation_id=self.conversation_id,
            visualizer=None,
        )

    def send_and_run(self, conversation: LocalConversation, message: str) -> None:
        conversation.send_message(message)
        conversation.run()

    def run_initial_session(self, agent: Agent) -> dict[str, Any]:
        conversation = self.create_conversation(agent)
        try:
            self.conversation_id = conversation.id
            self.send_and_run(conversation, "First message")
            self.send_and_run(conversation, "Second message")

            return {
                "conversation_id": conversation.id,
                "event_count": len(conversation.state.events),
            }
        finally:
            conversation.close()

    def base_state_path(self) -> Path:
        assert self.conversation_id is not None, "Call run_initial_session() first"
        return self.persistence_base_dir / self.conversation_id.hex / "base_state.json"

    def read_base_state(self) -> dict[str, Any]:
        return json.loads(self.base_state_path().read_text())

    def write_base_state(self, payload: dict[str, Any]) -> None:
        self.base_state_path().write_text(json.dumps(payload))

    def restore(self, agent: Agent) -> LocalConversation:
        assert self.conversation_id is not None, "Call run_initial_session() first"
        return self.create_conversation(agent)


def _agent(
    *,
    llm_model: str,
    tools: list[Tool],
    condenser_max_size: int,
    skill_name: str,
    skill_keyword: str,
    include_default_tools: list[str] | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    agent_type: type[Agent] = Agent,
) -> Agent:
    llm_kwargs: dict[str, Any] = {
        "model": llm_model,
        "api_key": SecretStr("test-key"),
        "usage_id": "test-llm",
    }
    if temperature is not None:
        llm_kwargs["temperature"] = temperature
    if reasoning_effort is not None:
        llm_kwargs["reasoning_effort"] = reasoning_effort

    llm = LLM(**llm_kwargs)

    condenser = LLMSummarizingCondenser(
        llm=llm,
        max_size=condenser_max_size,
        keep_first=2,
    )

    ctx = AgentContext(
        skills=[
            Skill(
                name=skill_name,
                content=f"Skill content for {skill_name}",
                trigger=KeywordTrigger(keywords=[skill_keyword]),
            )
        ]
    )

    agent_kwargs: dict[str, Any] = {
        "llm": llm,
        "tools": tools,
        "condenser": condenser,
        "agent_context": ctx,
    }
    if include_default_tools is not None:
        agent_kwargs["include_default_tools"] = include_default_tools

    return agent_type(**agent_kwargs)


def _tool_call_response(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    response_id: str,
    model: str = "gpt-4o-mini",
) -> ModelResponse:
    return ModelResponse(
        id=response_id,
        choices=[
            Choices(
                index=0,
                message=LiteLLMMessage(
                    role="assistant",
                    content=f"Calling {tool_name}",
                    tool_calls=[
                        ChatCompletionMessageToolCall(
                            id=f"{response_id}-call",
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
        model=model,
        object="chat.completion",
    )


def _rewrite_openhands_llms_to_legacy_proxy(value: Any) -> None:
    if isinstance(value, dict):
        model = value.get("model")
        if isinstance(model, str) and model.startswith(OPENHANDS_PROVIDER_PREFIX):
            model_name = model.removeprefix(OPENHANDS_PROVIDER_PREFIX)
            value["model"] = f"{LITELLM_PROXY_PREFIX}{model_name}"
            value["base_url"] = OPENHANDS_LLM_PROXY_BASE_URL
        for child in value.values():
            _rewrite_openhands_llms_to_legacy_proxy(child)
        return

    if isinstance(value, list):
        for child in value:
            _rewrite_openhands_llms_to_legacy_proxy(child)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_lifecycle_happy_path(mock_completion):
    """Baseline: 恢复应该加载之前的事件并允许进一步执行。"""

    captured_completion_kwargs: list[dict[str, Any]] = []

    def capture_completion(*_args: Any, **kwargs: Any):
        captured_completion_kwargs.append(kwargs)
        return create_mock_litellm_response(
            content="I'll help you with that.", finish_reason="stop"
        )

    mock_completion.side_effect = capture_completion

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        persisted_tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=persisted_tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        initial = lifecycle.run_initial_session(persisted_agent)

        # 工具 * 排序 * 故意与 persisted_tools 不同； 只要工具集相同，恢复就应该不区分顺
        # 序。
        #
        runtime_tools = [Tool(name="FileEditorTool"), Tool(name="TerminalTool")]
        runtime_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=runtime_tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
            temperature=0.42,
        )

        restored = lifecycle.restore(runtime_agent)
        try:
            assert restored.id == initial["conversation_id"]
            assert len(restored.state.events) == initial["event_count"]

            lifecycle.send_and_run(restored, "Third message")
            assert len(restored.state.events) > initial["event_count"]

            last_call = captured_completion_kwargs[-1]
            assert last_call["model"] == "gpt-4o-mini"
            assert last_call["temperature"] == 0.42
            assert "messages" in last_call
        finally:
            restored.close()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_preserves_security_risk_and_summary(mock_completion):
    """恢复应保留从工具调用参数派生的操作元数据。"""

    tool_arguments = {
        "command": "printf 'hello from restore test\\n'",
        "security_risk": "LOW",
        "summary": "Print hello from terminal",
    }

    responses = [
        _tool_call_response(
            tool_name="terminal",
            arguments=tool_arguments,
            response_id="response_action",
        ),
        create_mock_litellm_response(
            content="The terminal command finished.",
            response_id="response_follow_up",
            finish_reason="stop",
        ),
        create_mock_litellm_response(
            content="Restore still works.",
            response_id="response_restored",
            finish_reason="stop",
        ),
    ]

    def capture_completion(*_args: Any, **_kwargs: Any):
        return responses.pop(0)

    mock_completion.side_effect = capture_completion

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        persisted_tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=persisted_tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        persisted = lifecycle.create_conversation(persisted_agent)
        try:
            lifecycle.conversation_id = persisted.id
            persisted.set_security_analyzer(LLMSecurityAnalyzer())
            lifecycle.send_and_run(persisted, "Use the terminal tool once")
            initial_event_count = len(persisted.state.events)
        finally:
            persisted.close()

        runtime_tools = [Tool(name="FileEditorTool"), Tool(name="TerminalTool")]
        runtime_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=runtime_tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        restored = lifecycle.restore(runtime_agent)
        try:
            assert restored.id == lifecycle.conversation_id
            assert len(restored.state.events) == initial_event_count
            assert isinstance(restored.state.security_analyzer, LLMSecurityAnalyzer)

            action_events = [
                event
                for event in restored.state.events
                if isinstance(event, ActionEvent)
            ]
            assert len(action_events) == 1

            action_event = action_events[0]
            assert action_event.security_risk == SecurityRisk.LOW
            assert action_event.summary == tool_arguments["summary"]
            assert action_event.action is not None
            action_dump = action_event.action.model_dump()
            assert action_dump["command"] == tool_arguments["command"]
            assert "security_risk" not in action_dump
            assert "summary" not in action_dump

            restored_tool_call_args = json.loads(action_event.tool_call.arguments)
            assert (
                restored_tool_call_args["security_risk"]
                == tool_arguments["security_risk"]
            )
            assert restored_tool_call_args["summary"] == tool_arguments["summary"]

            lifecycle.send_and_run(restored, "Third message")
            assert len(restored.state.events) > initial_event_count
        finally:
            restored.close()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_fails_when_removing_tools(mock_completion):
    """当运行时工具删除已持久化工具时，恢复必须失败。"""

    mock_completion.return_value = create_mock_litellm_response(
        content="I'll help you with that.", finish_reason="stop"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        persisted_tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=persisted_tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )
        lifecycle.run_initial_session(persisted_agent)

        runtime_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=[Tool(name="TerminalTool")],
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        with pytest.raises(
            ValueError, match="tools were removed mid-conversation"
        ) as exc:
            lifecycle.restore(runtime_agent)

        assert "removed:" in str(exc.value)
        assert "FileEditorTool" in str(exc.value)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_succeeds_when_adding_tools(mock_completion):
    """当运行时工具添加新工具时，恢复必须成功。

    允许添加工具——只拒绝删除工具。
    """

    mock_completion.return_value = create_mock_litellm_response(
        content="I'll help you with that.", finish_reason="stop"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        persisted_tools = [Tool(name="TerminalTool")]
        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=persisted_tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )
        lifecycle.run_initial_session(persisted_agent)

        runtime_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=[Tool(name="TerminalTool"), Tool(name="FileEditorTool")],
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        conversation = lifecycle.restore(runtime_agent)
        assert conversation is not None


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_fails_when_agent_class_changes(mock_completion):
    """当已持久化和运行时智能体类型不同时，恢复必须失败。"""

    mock_completion.return_value = create_mock_litellm_response(
        content="I'll help you with that.", finish_reason="stop"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )
        lifecycle.run_initial_session(persisted_agent)

        runtime_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
            agent_type=DifferentAgent,
        )

        with pytest.raises(ValueError) as exc:
            lifecycle.restore(runtime_agent)

        assert "persisted agent is of type" in str(exc.value)
        assert "self is of type" in str(exc.value)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_fails_when_default_tools_removed(mock_completion):
    """include_default_tools 移除内置工具时，恢复必须失败。"""

    mock_completion.return_value = create_mock_litellm_response(
        content="I'll help you with that.", finish_reason="stop"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
            include_default_tools=["FinishTool", "ThinkTool"],
        )
        lifecycle.run_initial_session(persisted_agent)

        runtime_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
            include_default_tools=["FinishTool"],
        )

        with pytest.raises(
            ValueError, match="tools were removed mid-conversation"
        ) as exc:
            lifecycle.restore(runtime_agent)

        assert "removed:" in str(exc.value)
        assert "think" in str(exc.value)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_succeeds_when_default_tools_added(mock_completion):
    """如果 include_default_tools 添加内置工具，则恢复必须成功。

    允许添加工具——只拒绝删除工具。
    """

    mock_completion.return_value = create_mock_litellm_response(
        content="I'll help you with that.", finish_reason="stop"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
            include_default_tools=["FinishTool"],
        )
        lifecycle.run_initial_session(persisted_agent)

        runtime_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
            include_default_tools=["FinishTool", "ThinkTool"],
        )

        conversation = lifecycle.restore(runtime_agent)
        assert conversation is not None


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_succeeds_when_llm_condenser_and_skills_change(
    mock_completion,
):
    """当仅非破坏性智能体配置更改时，恢复应该成功。"""

    mock_completion.return_value = create_mock_litellm_response(
        content="Acknowledged.", finish_reason="stop"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]

        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )
        initial = lifecycle.run_initial_session(persisted_agent)

        runtime_agent = _agent(
            llm_model="gpt-4o",
            tools=tools,
            condenser_max_size=120,
            skill_name="skill-v2",
            skill_keyword="beta",
        )

        restored = lifecycle.restore(runtime_agent)
        try:
            assert restored.id == initial["conversation_id"]
            assert len(restored.state.events) == initial["event_count"]

            assert restored.agent.llm.model == "gpt-4o"
            assert isinstance(restored.agent.condenser, LLMSummarizingCondenser)
            assert restored.agent.condenser.max_size == 120

            restored.send_message("beta: please use the new skill")
            last_event = restored.state.events[-1]
            assert isinstance(last_event, MessageEvent)
            assert last_event.source == "user"
            assert last_event.activated_skills == ["skill-v2"]

            restored.run()
            assert len(restored.state.events) > initial["event_count"]
        finally:
            restored.close()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_openhands_provider_restore_writes_public_model_shape(mock_completion):
    captured_completion_kwargs: list[dict[str, Any]] = []

    def capture_completion(*_args: Any, **kwargs: Any):
        captured_completion_kwargs.append(kwargs)
        return create_mock_litellm_response(
            content="Acknowledged.", finish_reason="stop"
        )

    mock_completion.side_effect = capture_completion

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        agent = _agent(
            llm_model="openhands/claude-opus-4-8",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        lifecycle.run_initial_session(agent)

        base_state = lifecycle.read_base_state()
        llm_payload = base_state["agent"]["llm"]
        assert llm_payload["model"] == "openhands/claude-opus-4-8"
        assert "base_url" not in llm_payload

        assert captured_completion_kwargs[-1]["model"] == "claude-opus-4-8"
        assert captured_completion_kwargs[-1]["custom_llm_provider"] == "litellm_proxy"
        assert (
            captured_completion_kwargs[-1]["api_base"] == OPENHANDS_LLM_PROXY_BASE_URL
        )


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_conversation_restore_rewrites_legacy_openhands_proxy_snapshot(
    mock_completion,
):
    captured_completion_kwargs: list[dict[str, Any]] = []

    def capture_completion(*_args: Any, **kwargs: Any):
        captured_completion_kwargs.append(kwargs)
        return create_mock_litellm_response(
            content="Acknowledged.", finish_reason="stop"
        )

    mock_completion.side_effect = capture_completion

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        persisted_agent = _agent(
            llm_model="openhands/claude-opus-4-8",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )
        initial = lifecycle.run_initial_session(persisted_agent)

        legacy_base_state = lifecycle.read_base_state()
        _rewrite_openhands_llms_to_legacy_proxy(legacy_base_state["agent"])
        lifecycle.write_base_state(legacy_base_state)

        runtime_agent = _agent(
            llm_model="openhands/claude-opus-4-8",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        restored = lifecycle.restore(runtime_agent)
        try:
            assert restored.id == initial["conversation_id"]
            assert len(restored.state.events) == initial["event_count"]
            assert restored.agent.llm.model == "openhands/claude-opus-4-8"

            restored_base_state = lifecycle.read_base_state()
            restored_llm_payload = restored_base_state["agent"]["llm"]
            assert restored_llm_payload["model"] == "openhands/claude-opus-4-8"
            assert "base_url" not in restored_llm_payload

            lifecycle.send_and_run(restored, "Third message")
            assert captured_completion_kwargs[-1]["model"] == "claude-opus-4-8"
            assert (
                captured_completion_kwargs[-1]["custom_llm_provider"] == "litellm_proxy"
            )
            assert (
                captured_completion_kwargs[-1]["api_base"]
                == OPENHANDS_LLM_PROXY_BASE_URL
            )
        finally:
            restored.close()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_restore_reasoning_effort_none_strips_temperature(mock_completion):
    """推理模型应接受 reasoning_effort 并忽略温度/top_p。"""

    captured_completion_kwargs: list[dict[str, Any]] = []

    def capture_completion(*_args: Any, **kwargs: Any):
        captured_completion_kwargs.append(kwargs)
        return create_mock_litellm_response(
            content="Acknowledged.", finish_reason="stop"
        )

    mock_completion.side_effect = capture_completion

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]

        persisted_agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )
        initial = lifecycle.run_initial_session(persisted_agent)

        runtime_agent = _agent(
            llm_model="o3-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
            temperature=0.33,
            reasoning_effort="none",
        )

        restored = lifecycle.restore(runtime_agent)
        try:
            assert restored.id == initial["conversation_id"]
            assert len(restored.state.events) == initial["event_count"]

            lifecycle.send_and_run(restored, "Third message")

            last_call = captured_completion_kwargs[-1]
            assert last_call["model"] == "o3-mini"
            assert last_call["reasoning_effort"] == "none"
            assert "temperature" not in last_call
            assert "top_p" not in last_call
        finally:
            restored.close()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_restore_pre_event_tree_conversation_with_artifact_tail_keeps_history(
    mock_completion,
):
    """恢复事件树前的对话，其尾部是启动工件
    必须保留完整的历史记录（#4057）。

    较旧的智能体服务器（事件树之前）编写的事件没有 ``parent_id``，也从不已持久化
    ``leaf_event_id``。 我们从*真实*运行中重现该形状：从
    每个事件中剥离``parent_id``并删除树HEAD标记
    ``base_state``，然后将较新的服务器在中断启动期间写入尾部的非树工件类型附加到尾部
    （a
    ``ConversationStateUpdateEvent``携带``parent_id``）。 在恢复时，智能体必须加载整
    个先前历史并链接到其真实尾部，而不是在
    下一个事件上False ``__root__`` 或者是或phans掉一切。
    """
    mock_completion.return_value = create_mock_litellm_response(
        content="Acknowledged.", finish_reason="stop"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        # 1) 通过实际运行会话来生成真实的事件日志。
        lifecycle.run_initial_session(agent)
        assert lifecycle.conversation_id is not None
        events_dir = (
            lifecycle.persistence_base_dir / lifecycle.conversation_id.hex / "events"
        )
        event_files = sorted(
            events_dir.glob("event-*.json"),
            key=lambda p: int(p.name.split("-")[1]),
        )
        assert len(event_files) >= 3
        original_ids = [json.loads(p.read_text())["id"] for p in event_files]

        # 2) 降级到事件前树形状：从每个事件中剥离 parent_id 并删除旧服务器从未写入的树
        # HEAD 标记。
        #
        for p in event_files:
            data = json.loads(p.read_text())
            data.pop("parent_id", None)
            p.write_text(json.dumps(data))
        base_state = lifecycle.read_base_state()
        base_state.pop("leaf_event_id", None)
        base_state.pop("head_is_empty", None)
        lifecycle.write_base_state(base_state)

        # 3) 附加中断启动工件：一个非树事件，较新的服务器链接到旧尾部（它带有 parent_id
        # ）。
        #
        artifact = ConversationStateUpdateEvent(
            parent_id=original_ids[-1], key="execution_status", value="idle"
        )
        artifact_path = events_dir / f"event-{len(event_files):05d}-{artifact.id}.json"
        artifact_path.write_text(artifact.model_dump_json(exclude_none=True))

        # 4) 在当前（树感知）代码下恢复。
        restored = lifecycle.restore(agent)
        try:
            # 整个先前的历史记录都是活动分支（没有孤立的分支）； 非树神器不在其上。
            #
            active_ids = [e.id for e in restored.state.active_branch()]
            assert active_ids == original_ids

            # 继续链接到真正的遗留尾部，而不是 False __root__。
            restored.send_message("Third message")
            new_event = restored.state.events[-1]
            assert new_event.parent_id == original_ids[-1]
            assert new_event.parent_id != ROOT_PARENT_ID
            reachable = {e.id for e in restored.state.events.path_to_root(new_event.id)}
            assert set(original_ids).issubset(reachable)
        finally:
            restored.close()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_restore_event_tree_conversation_keeps_history(mock_completion):
    """对前事件树情况的控制：正常的 1.33.0+ 恢复不受影响。

    事件树服务器的对话已持久化（事件携带 ``parent_id``，
    ``base_state`` 持续 ``leaf_event_id``) 被恢复 *，而没有 * 任何降级，并且必须保留
    其完整历史记录并链接到真实的尾部。 因为
    ``leaf_event_id`` 设置为 ``_resolve_active_leaf`` 直接返回，并且遗留恢复路径 #
    4057 的修复触及的路径从不进入——这
    确保了正常恢复保持完整。
    """
    mock_completion.return_value = create_mock_litellm_response(
        content="Acknowledged.", finish_reason="stop"
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        lifecycle = RestoreLifecycle(
            workspace_dir=base / "workspace",
            persistence_base_dir=base / "persist",
        )
        lifecycle.workspace_dir.mkdir(parents=True, exist_ok=True)
        lifecycle.persistence_base_dir.mkdir(parents=True, exist_ok=True)

        tools = [Tool(name="TerminalTool"), Tool(name="FileEditorTool")]
        agent = _agent(
            llm_model="gpt-4o-mini",
            tools=tools,
            condenser_max_size=80,
            skill_name="skill-v1",
            skill_keyword="alpha",
        )

        lifecycle.run_initial_session(agent)
        assert lifecycle.conversation_id is not None
        events_dir = (
            lifecycle.persistence_base_dir / lifecycle.conversation_id.hex / "events"
        )
        event_files = sorted(
            events_dir.glob("event-*.json"),
            key=lambda p: int(p.name.split("-")[1]),
        )
        assert len(event_files) >= 3
        original_ids = [json.loads(p.read_text())["id"] for p in event_files]

        # 这是现代（事件树）磁盘形状 - 叶已持久化和事件携带 parent_id（对比上面的事件树
        # 前测试）。 没有降级，没有注入工件。
        #
        assert "leaf_event_id" in lifecycle.read_base_state()
        assert json.loads(event_files[0].read_text()).get("parent_id") is None
        assert json.loads(event_files[-1].read_text()).get("parent_id") is not None

        restored = lifecycle.restore(agent)
        try:
            # HEAD 是已持久化叶子； 整个历史是活跃的分支。
            assert restored.state.leaf_event_id == original_ids[-1]
            active_ids = [e.id for e in restored.state.active_branch()]
            assert active_ids == original_ids

            # 继续将链条连接到真正的尾巴上，与修复之前完全相同。
            restored.send_message("Third message")
            new_event = restored.state.events[-1]
            assert new_event.parent_id == original_ids[-1]
            assert new_event.parent_id != ROOT_PARENT_ID
            reachable = {e.id for e in restored.state.events.path_to_root(new_event.id)}
            assert set(original_ids).issubset(reachable)
        finally:
            restored.close()
