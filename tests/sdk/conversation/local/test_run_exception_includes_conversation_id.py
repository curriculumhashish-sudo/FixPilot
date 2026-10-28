import tempfile

import pytest

from openhands.sdk.agent.base import AgentBase
from openhands.sdk.conversation import Conversation
from openhands.sdk.conversation.exceptions import ISSUE_URL, ConversationRunError
from openhands.sdk.conversation.impl.local_conversation import (
    _agent_already_surfaced_error,
)
from openhands.sdk.conversation.types import (
    ConversationCallbackType,
    ConversationTokenCallbackType,
)
from openhands.sdk.event import MessageEvent
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.llm import LLM, Message, TextContent


class FailingAgent(AgentBase):
    def step(
        self,
        conversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ):  # noqa: D401, ARG002
        """故意未能模拟意外的运行时错误。"""
        raise ValueError("boom")


class SelfEmittingFailingAgent(AgentBase):
    """它表面其自身的类型 ACPAgent，然后提升 ConversationErrorEvent。

    ACPAgent._emit_turn_error 发出详细的、分类的
    ``ConversationErrorEvent(source="agent")`` 并重新加注，以便运行循环终止。 然后，
    运行循环不得附加第二个通用副本。
    """

    def step(
        self,
        conversation,
        on_event: ConversationCallbackType,
        on_token: ConversationTokenCallbackType | None = None,
    ):  # noqa: D401, ARG002
        """呈现丰富类型的错误，然后引发底层异常。"""
        on_event(
            ConversationErrorEvent(
                source="agent",
                code="ACPPromptError",
                detail="[-32603] Internal error: model 'x' not found",
            )
        )
        raise ValueError("Internal error")


def test_run_raises_conversation_run_error_with_id():
    llm = LLM(model="gpt-4o-mini", api_key=None, usage_id="test-llm")
    agent = FailingAgent(llm=llm, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)

        with pytest.raises(ConversationRunError) as excinfo:
            conv.run()

        err = excinfo.value
        # 携带会话id
        assert getattr(err, "conversation_id", None) == conv.id
        # 消息应包含 id 以在日志/回溯中可见
        assert str(conv.id) in str(err)
        # 通过链接保留原始异常
        assert isinstance(getattr(err, "original_exception", None), ValueError)
        assert err.conversation_error is not None
        assert err.conversation_error.code == "ValueError"
        assert err.conversation_error.detail == "boom"


def test_run_error_includes_persistence_dir_and_issue_url():
    """测试 ConversationRunError 是否包含 persistence_dir 和问题 URL。"""
    llm = LLM(model="gpt-4o-mini", api_key=None, usage_id="test-llm")
    agent = FailingAgent(llm=llm, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)

        with pytest.raises(ConversationRunError) as excinfo:
            conv.run()

        err = excinfo.value
        error_message = str(err)

        # 应设置 persistence_dir
        assert err.persistence_dir is not None
        # persistence_dir 应包含对话 ID（十六进制）
        assert conv.id.hex in err.persistence_dir
        # persistence_dir 应该在错误消息中
        assert err.persistence_dir in error_message
        # 问题 URL 应该出现在错误消息中
        assert ISSUE_URL in error_message
        # 应该提及对话日志
        assert "Conversation logs are stored at:" in error_message
        # 应该提到提交错误报告
        assert "file a bug report" in error_message


class TestAgentAlreadySurfacedError:
    """单元测试用于运行循环重复数据删除防护。"""

    def test_empty_events(self):
        assert _agent_already_surfaced_error([]) is False

    def test_latest_error_is_agent_sourced(self):
        events = [
            ConversationErrorEvent(source="agent", code="ACPPromptError", detail="d"),
        ]
        assert _agent_already_surfaced_error(events) is True

    def test_latest_error_is_environment_sourced(self):
        events = [
            ConversationErrorEvent(source="environment", code="ValueError", detail="d"),
        ]
        assert _agent_already_surfaced_error(events) is False

    def test_uses_most_recent_error_event(self):
        # 如果智能体错误之后出现较晚的环境错误，则最新的错误获胜。
        events = [
            ConversationErrorEvent(source="agent", code="ACPPromptError", detail="a"),
            ConversationErrorEvent(source="environment", code="ValueError", detail="b"),
        ]
        assert _agent_already_surfaced_error(events) is False

    def test_scans_past_trailing_non_error_events(self):
        # 智能体错误之后的非错误事件不得隐藏它。
        events = [
            ConversationErrorEvent(source="agent", code="ACPPromptError", detail="a"),
            MessageEvent(
                source="agent",
                llm_message=Message(
                    role="assistant", content=[TextContent(text="trailing")]
                ),
            ),
        ]
        assert _agent_already_surfaced_error(events) is True

    def test_since_excludes_stale_prior_run_events(self):
        # 源="智能体在同一个对话中的后续运行中，前一次运行的错误不能掩盖新的、无关的异常
        # 事件state.events accumulates across runs).
        #
        stale_agent_event = ConversationErrorEvent(
            source="agent", code="ACPPromptError", detail="from prior run"
        )
        events = [stale_agent_event]
        since = len(events)  # 新一轮开始 - 尚未添加任何事件
        assert _agent_already_surfaced_error(events, since) is False

    def test_since_still_finds_current_run_agent_event(self):
        stale_agent_event = ConversationErrorEvent(
            source="agent", code="ACPPromptError", detail="from prior run"
        )
        current_run_agent_event = ConversationErrorEvent(
            source="agent", code="ACPAuthRequired", detail="from current run"
        )
        events = [stale_agent_event, current_run_agent_event]
        since = 1  # 陈旧事件后开始新的运行
        assert _agent_already_surfaced_error(events, since) is True


def test_run_does_not_duplicate_agent_emitted_error():
    """当智能体出现其自己的类型错误并重新引发时，运行循环
    不得附加通用 str(exc) 重复项，否则会在显示最近错误的客户端中破坏它。
    """
    llm = LLM(model="gpt-4o-mini", api_key=None, usage_id="test-llm")
    agent = SelfEmittingFailingAgent(llm=llm, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, workspace=tmpdir)
        with pytest.raises(ConversationRunError) as excinfo:
            conv.run()

        errors = [e for e in conv.state.events if isinstance(e, ConversationErrorEvent)]
        assert len(errors) == 1, f"expected one error event, got {errors}"
        assert errors[0].source == "agent"
        assert errors[0].code == "ACPPromptError"
        assert "model 'x' not found" in errors[0].detail
        assert excinfo.value.conversation_error is errors[0]


def test_run_emits_generic_error_when_agent_did_not():
    """Control: 引发 WITHOUT 自发射的智能体仍然可以运行
    循环的通用 ConversationErrorEvent（常规智能体行为不变）。"""
    llm = LLM(model="gpt-4o-mini", api_key=None, usage_id="test-llm")
    agent = FailingAgent(llm=llm, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        conv = Conversation(agent=agent, workspace=tmpdir)
        with pytest.raises(ConversationRunError):
            conv.run()

        errors = [e for e in conv.state.events if isinstance(e, ConversationErrorEvent)]
        assert len(errors) == 1
        assert errors[0].source == "environment"
        assert errors[0].code == "ValueError"


def test_run_error_without_persistence_dir():
    """测试 ConversationRunError 在没有 persistence_dir 的情况下也能工作。"""
    llm = LLM(model="gpt-4o-mini", api_key=None, usage_id="test-llm")
    agent = FailingAgent(llm=llm, tools=[])

    with tempfile.TemporaryDirectory() as tmpdir:
        # 未设置 persistence_dir
        conv = Conversation(agent=agent, workspace=tmpdir)

        with pytest.raises(ConversationRunError) as excinfo:
            conv.run()

        err = excinfo.value
        error_message = str(err)

        # persistence_dir 应该是 None
        assert err.persistence_dir is None
        # 当没有 persistence_dir 时，问题 URL 应该在错误消息中包含不
        assert ISSUE_URL not in error_message
        # 应该仍然有对话 ID
        assert str(conv.id) in error_message
