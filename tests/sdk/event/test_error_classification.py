import pytest

from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.error_classification import (
    ErrorClassification,
    FailureKind,
    classify_error,
)
from openhands.sdk.event.llm_convertible import AgentErrorEvent


@pytest.mark.parametrize(
    ("code", "detail", "kind"),
    [
        ("OpenAIError", "Incorrect API key provided", "auth"),
        ("APIError", "This request requires more credits", "quota"),
        ("OpenAIError", "Error code: 429", "rate_limit"),
        ("MaxBudgetReached", "", "quota"),
        ("OpenRouterException", "", "transient"),
        (
            "LLMBadRequestError",
            "LLM Provider NOT provided",
            "config",
        ),
        (
            "NoCondensationAvailableException",
            "Streaming requires an on_token callback",
            "internal",
        ),
        (
            "PydanticSerializationError",
            "surrogates not allowed",
            "internal",
        ),
        ("UnexpectedProviderError", "", "unknown"),
        # 运行限制是已知的产品结果，而不是诊断。
        ("MaxIterationsReached", "Agent reached maximum iterations", "agent_action"),
        ("ConversationOwnershipLostError", "", "agent_action"),
        # 上下文-窗口错误可通过上下文压缩恢复。
        ("LLMContextWindowExceedError", "", "agent_action"),
        ("LLMMalformedConversationHistoryError", "", "agent_action"),
    ],
)
def test_conversation_error_classifies_sensitive_detail_without_serializing_it(
    code: str, detail: str, kind: str
) -> None:
    event = ConversationErrorEvent(source="environment", code=code, detail=detail)

    assert event.classification is not None
    assert event.classification.kind == kind
    if detail:
        assert detail not in event.classification.model_dump_json()


@pytest.mark.parametrize(
    ("code", "detail", "expected_kind"),
    [
        # 基于代码的分类必须胜过附带的细节措辞。
        ("KeyError", "'timeout_seconds'", "internal"),
        ("AssertionError", "Tool result not found for call id abc123", "internal"),
        ("TypeError", "connection error during call", "internal"),
        ("AttributeError", "model not found in registry", "internal"),
        # 请求 ID 中的裸露“429”必须不分类为 rate_limit。
        ("HTTPStatusError", "Connection reset for request req_814295af", "transient"),
        # 在转瞬即逝的消息中，如果代码是已知的转瞬即逝包装器，则“未找到”不能 CONFIG，但
        # 对于未知代码，“模型未找到”是 CONFIG。
        #
        ("UnexpectedError", "model not found", "config"),
    ],
)
def test_code_based_classification_takes_priority_over_detail(
    code: str, detail: str, expected_kind: str
) -> None:
    assert classify_error(code, detail).kind == expected_kind


def test_agent_error_event_defaults_to_unknown() -> None:
    """如果没有明确的分类，AgentErrorEvent 就是 UNKNOWN（诊断）。"""
    event = AgentErrorEvent(
        error="something went wrong",
        tool_name="bash",
        tool_call_id="call-1",
    )
    assert event.classification is not None
    assert event.classification.kind == FailureKind.UNKNOWN
    assert event.classification.retryable is False


def test_agent_error_event_preserves_explicit_classification() -> None:
    """显式提供的分类不会被验证器覆盖。"""
    explicit = ErrorClassification(
        kind=FailureKind.AGENT_ACTION, retryable=True, user_action="retry"
    )
    event = AgentErrorEvent(
        error="validation failed",
        tool_name="bash",
        tool_call_id="call-1",
        classification=explicit,
    )
    assert event.classification is explicit
