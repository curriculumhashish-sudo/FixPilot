"""由 SDK、UI 和遥测技术共享的小型、隐私安全的故障合约。"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class FailureKind(StrEnum):
    AUTH = "auth"
    QUOTA = "quota"
    RATE_LIMIT = "rate_limit"
    CONFIG = "config"
    TRANSIENT = "transient"
    AGENT_ACTION = "agent_action"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


FailureAction = Literal["none", "retry", "settings"]


class ErrorClassification(BaseModel):
    """唯一跨越事件/API 边界的失败元数据。

    它是故意很小的。 ``detail`` 仅在本地进行检查，以将广泛的第三方错误映射到此封闭词
    汇表； 它永远不会被复制到这里或发送到遥测。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FailureKind
    retryable: bool
    user_action: FailureAction = "none"
    error_id: str | None = None


def _failure(
    kind: FailureKind, *, retryable: bool = False, user_action: FailureAction = "none"
) -> ErrorClassification:
    return ErrorClassification(kind=kind, retryable=retryable, user_action=user_action)


# ：预期的，智能体-可纠正的故障 - 智能体可以重试（例如：格式错误的工具调用或工具验证错误
# ）。
#
AGENT_OUTCOME = ErrorClassification(
    kind=FailureKind.AGENT_ACTION, retryable=True, user_action="retry"
)


def classify_error(code: str, detail: str = "") -> ErrorClassification:
    """根据键入的代码和本地提供程序元数据文本对已知故障进行分类。

    异常类，其名称本身就是权威的（``KeyError``，
    ``AssertionError``、SDK 特定错误，例如 ``LLMAuthenticationError``、
    ``MaxIterationsReached``, …) 首先检查 ****，因此 ``detail`` 中的附带措辞不能覆盖
    它们。 检查不透明/通用包装代码（
    ``OpenAIError``、``APIError``、``HTTPStatusError``、...）
    **在**详细启发式之后，因为单独的类名不是
    足够具体——需要详细的文本来区分身份验证、速率限制和瞬态。
    """
    # ── 权威的基于代码的分类（先检查）──────────
    if code in {"LLMAuthenticationError", "ACPAuthRequired"}:
        return _failure(FailureKind.AUTH, user_action="settings")
    if code in {"LLMRateLimitError"}:
        return _failure(FailureKind.RATE_LIMIT, retryable=True, user_action="retry")
    # 预算耗尽是配额的结果； 消费者可以引导用户提高配置的限制，而不是将其视为 SDK 失败。
    #
    if code in {"MaxBudgetReached"}:
        return _failure(FailureKind.QUOTA, user_action="settings")
    if code in {
        "LLMBadRequestError",
        "ACPInitError",
        "ACPSpawnError",
        "ACPPromptError",
        "NotFoundError",
        "LibTmuxException",
    }:
        return _failure(FailureKind.CONFIG, user_action="settings")
    # 上下文-窗口/对话历史记录错误可通过上下文压缩恢复，因此将它们分类为智能体结果，而不
    # 是诊断。
    #
    if code in {"LLMContextWindowExceedError", "LLMMalformedConversationHistoryError"}:
        return _failure(FailureKind.AGENT_ACTION, retryable=True, user_action="retry")
    # 运行限制和所有权损失是已知的产品结果，而不是诊断。
    if code in {"MaxIterationsReached", "ConversationOwnershipLostError"}:
        return _failure(FailureKind.AGENT_ACTION)
    if code in {
        "KeyError",
        "AssertionError",
        "PydanticSerializationError",
        "AttributeError",
        "TypeError",
    }:
        return _failure(FailureKind.INTERNAL)

    # ── 基于细节的分类（针对不透明/通用包装代码）──
    text = detail.casefold()

    if any(
        token in text
        for token in (
            "invalid api key",
            "incorrect api key",
            "authentication required",
            "invalid bearer token",
            "invalid proxy server token",
            "unauthorized",
            "error code: 401",
            'status": 401',
            "token_not_found",
            "api key is missing",
        )
    ):
        return _failure(FailureKind.AUTH, user_action="settings")
    if any(
        token in text
        for token in (
            "weekly usage limit",
            "daily quota",
            "session usage limit",
            "insufficient balance",
            "more credits",
            "budget has been exceeded",
        )
    ):
        return _failure(FailureKind.QUOTA, user_action="settings")
    if "rate limit" in text or "error code: 429" in text or 'status": 429' in text:
        return _failure(FailureKind.RATE_LIMIT, retryable=True, user_action="retry")
    if any(
        token in text
        for token in (
            "provider not provided",
            "no models loaded",
            "does not support thinking",
            "model is no longer available",
            "model not found",
            "invalid params",
            "inactive_service",
            "powershell is not available",
        )
    ):
        return _failure(FailureKind.CONFIG, user_action="settings")
    if any(
        token in text
        for token in (
            "timeout",
            "connection error",
            "connection closed",
            "service temporarily unavailable",
            "bad gateway",
            "cloudflare",
            "cannot connect",
            "name or service not known",
            "error code: 5",
        )
    ):
        return _failure(FailureKind.TRANSIENT, retryable=True, user_action="retry")
    if any(
        token in text
        for token in (
            "on_token callback",
            "duplicate tool names",
            "list_tools",
            "on_tools_changed",
            "surrogates not allowed",
        )
    ):
        return _failure(FailureKind.INTERNAL)

    # ── 回退方案基于代码的分类（通用包装代码）────────
    if code in {
        "LLMServiceUnavailableError",
        "LLMTimeoutError",
        "ReadTimeout",
        "LLMNoResponseError",
        "MCPTimeoutError",
        "BadGatewayError",
        "HTTPStatusError",
        "RequestError",
        "CloudflareError",
        "OpenAIError",
        "APIError",
        "BaseLLMException",
        "AnthropicError",
        "OpenRouterException",
        "OllamaError",
    }:
        return _failure(FailureKind.TRANSIENT, retryable=True, user_action="retry")

    return _failure(FailureKind.UNKNOWN)
