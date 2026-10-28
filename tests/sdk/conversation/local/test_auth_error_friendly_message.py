"""LLMAuthenticationError 应展示一个用户友好的消息。

回归测试：
  https://github.com/OpenHands/software-agent-sdk/issues/3411

当用户拥有无效/过期的 API 密钥时，原始 LiteLLM 错误 (e.g. 完整的 AnthropicException
JSON) 必须不出现在发送到 UI 的
ConversationErrorEvent 详细信息中。 相反，应该发出清晰的、可操作的消息，同时仍然引发
ConversationRunError，以便服务器日志不受影
响。
"""

import asyncio
import tempfile

import pytest

from openhands.sdk.agent import Agent
from openhands.sdk.conversation import Conversation, LocalConversation
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.llm import Message, TextContent
from openhands.sdk.llm.exceptions import LLMAuthenticationError
from openhands.sdk.testing import TestLLM


_RAW_LITELLM_ERROR = (
    "litellm.AuthenticationError: AnthropicException - "
    '{"type":"error","error":{"type":"authentication_error",'
    '"message":"invalid x-api-key"},'
    '"request_id":"req_011CbTfF4jtKVAB95FSH6ESb"}'
)
_FRIENDLY_SUBSTRING = "invalid or has expired"


def _make_auth_failing_conversation(tmpdir: str) -> LocalConversation:
    llm = TestLLM.from_messages([LLMAuthenticationError(_RAW_LITELLM_ERROR)])
    agent = Agent(llm=llm, tools=[])
    conv = Conversation(agent=agent, persistence_dir=tmpdir, workspace=tmpdir)
    assert isinstance(conv, LocalConversation)
    conv.send_message(Message(role="user", content=[TextContent(text="hello")]))
    return conv


# ---------------------------------------------------------------------------
# 同步路径（运行）
# ---------------------------------------------------------------------------


def test_auth_error_run_raises_conversation_run_error():
    """ConversationRunError 仍会引发，因此服务器日志不受影响。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = _make_auth_failing_conversation(tmpdir)
        with pytest.raises(ConversationRunError) as exc_info:
            conv.run()
        assert isinstance(exc_info.value.__cause__, LLMAuthenticationError)


def test_auth_error_run_emits_friendly_detail():
    """ConversationErrorEvent.detail 是用户可读的，而不是原始的 LiteLLM 字符串。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = _make_auth_failing_conversation(tmpdir)
        with pytest.raises(ConversationRunError):
            conv.run()

        error_events = [
            e for e in conv.state.events if isinstance(e, ConversationErrorEvent)
        ]
        assert error_events, "Expected at least one ConversationErrorEvent"

        auth_error_event = next(
            (e for e in error_events if e.code == "LLMAuthenticationError"), None
        )
        assert auth_error_event is not None, (
            "Expected a ConversationErrorEvent with code='LLMAuthenticationError'"
        )
        assert _FRIENDLY_SUBSTRING in auth_error_event.detail, (
            f"Expected friendly message in detail, got: {auth_error_event.detail!r}"
        )
        assert _RAW_LITELLM_ERROR not in auth_error_event.detail, (
            "Raw litellm error string must not appear in the UI-facing detail"
        )


# ---------------------------------------------------------------------------
# 异步路径（运行）
# ---------------------------------------------------------------------------


def test_auth_error_arun_raises_conversation_run_error():
    """异步路径：ConversationRunError仍然被提出。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = _make_auth_failing_conversation(tmpdir)
        with pytest.raises(ConversationRunError) as exc_info:
            asyncio.run(conv.arun())
        assert isinstance(exc_info.value.__cause__, LLMAuthenticationError)


def test_auth_error_arun_emits_friendly_detail():
    """异步路径：ConversationErrorEvent.detail是用户可读的。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        conv = _make_auth_failing_conversation(tmpdir)
        with pytest.raises(ConversationRunError):
            asyncio.run(conv.arun())

        error_events = [
            e for e in conv.state.events if isinstance(e, ConversationErrorEvent)
        ]
        assert error_events, "Expected at least one ConversationErrorEvent"

        auth_error_event = next(
            (e for e in error_events if e.code == "LLMAuthenticationError"), None
        )
        assert auth_error_event is not None, (
            "Expected a ConversationErrorEvent with code='LLMAuthenticationError'"
        )
        assert _FRIENDLY_SUBSTRING in auth_error_event.detail
        assert _RAW_LITELLM_ERROR not in auth_error_event.detail
