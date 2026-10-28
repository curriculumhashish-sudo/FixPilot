from __future__ import annotations

from collections.abc import Collection
from typing import Final

from litellm.exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    BudgetExceededError,
    ContentPolicyViolationError,
    ContextWindowExceededError,
    InternalServerError,
    OpenAIError,
    PermissionDeniedError,
)
from openai import APIError as OpenAIAPIError, RateLimitError as OpenAIRateLimitError

from .types import (
    LLMContextWindowExceedError,
    LLMMalformedConversationHistoryError,
    LLMRateLimitError,
)


# 最小的、与提供商无关的上下文-窗口检测
LONG_PROMPT_PATTERNS: Final[list[str]] = [
    "contextwindowexceedederror",
    "prompt is too long",
    "input length and `max_tokens` exceed context limit",
    "please reduce the length of",
    "exceeds the available context size",
    "context length exceeded",
    "input exceeds the context window",
    "context window exceeds limit",  # 极小极大提供商
]

# 这些表明发送给提供商的格式错误的工具使用/工具结果历史记录。 它们被单独跟踪，而不是与
# True 上下文-窗口错误一起，因此日志和智能体控制流可以保留这种区分，同时仍然路由到上下文
# 压缩-基恢复。
#
MALFORMED_HISTORY_PATTERNS: Final[list[str]] = [
    "tool_use ids were found without `tool_result` blocks immediately after",
    # Anthropic 反引号变体
    "`tool_use` ids were found without `tool_result` blocks immediately after",
    (
        "each `tool_use` block must have a corresponding `tool_result` block "
        "in the next message"
    ),
    "each tool_use must have a single result",
    "found multiple `tool_result` blocks with id:",
    "unexpected `tool_use_id` found in `tool_result` blocks",
    (
        "each `tool_result` block must have a corresponding `tool_use` block "
        "in the previous message"
    ),
    # 登月/基米变体
    "must be followed by tool messages responding to each 'tool_call_id'",
    # OpenAI 兼容提供者可以拒绝重播的助手工具调用，其参数无效 JSON。
    #
    "failed to parse tool call arguments as json",
]

# 当缓存内容低于提供商的最小 token 阈值（当前为 4096 token）时，Vertex AI (Gemini) 会拒
# 绝上下文缓存请求。 错误示例：“缓存内容为 1171 token。 启动缓存的最小词元数量是 4096。”
#  — `.lower()` 比较处理提供者之间的大小写变化，但不会匹配重写的消息； 如果 API 措辞发生
# 变化，请更新此模式。
#
PROMPT_CACHE_TOO_SMALL_PATTERNS: Final[list[str]] = [
    "minimum token count to start caching",
]

# 确定性的“您已用尽津贴”结果。 与瞬态 429 不同，这些将通过重试不恢复，直到限制重置或提高
# ，因此重试只会消耗退避时间。 调用者 (e.g. LLM 重试循环）使用它来跳过重试； 预算拒绝也
# 会停止模型回退方案。
#
QUOTA_EXHAUSTION_PATTERNS: Final[list[str]] = [
    "usage_limit_reached",
    "insufficient_quota",
]

AUTH_PATTERNS: Final[list[str]] = [
    "invalid api key",
    "unauthorized",
    "missing api key",
    "invalid authentication",
    "access denied",
]

CONTENT_POLICY_PATTERNS: Final[list[str]] = [
    "content_policy",
    "content filtering policy",
    "output blocked by content filtering",
]


def is_context_window_exceeded(exception: Exception) -> bool:
    if isinstance(exception, (ContextWindowExceededError, LLMContextWindowExceedError)):
        return True

    # 检查可能包含上下文窗口错误的 litellm/openai 异常类型。 APIConnectionError 可以包装
    # 提供者特定的错误 e.g., Minimax]，这些错误包含上下文窗口消息。
    #
    if not isinstance(
        exception,
        (BadRequestError, OpenAIError, APIConnectionError, InternalServerError),
    ):
        return False

    s = str(exception).lower()
    return any(p in s for p in LONG_PROMPT_PATTERNS)


def looks_like_malformed_conversation_history_error(exception: Exception) -> bool:
    if isinstance(exception, LLMMalformedConversationHistoryError):
        return True

    if not isinstance(
        exception,
        (BadRequestError, OpenAIError, APIConnectionError, InternalServerError),
    ):
        return False

    s = str(exception).lower()
    return any(p in s for p in MALFORMED_HISTORY_PATTERNS)


def is_prompt_cache_too_small(exception: Exception) -> bool:
    """如果错误表明提示词缓存内容太小，则返回 True。

    Vertex AI (Gemini) 需要最少数量 token（当前为 4096）才能创建上下文缓存。 当缓存内
    容低于此阈值时，API 返回 400 错误。 SDK
     应该检测到这一点，并且重试没有提示词缓存标记。
    """
    if not isinstance(exception, (BadRequestError, OpenAIError)):
        return False
    s = str(exception).lower()
    return any(p in s for p in PROMPT_CACHE_TOO_SMALL_PATTERNS)


def _has_rate_limit_code(exception: BaseException, codes: Collection[str]) -> bool:
    if not isinstance(exception, (OpenAIRateLimitError, LLMRateLimitError)):
        return False
    # LiteLLM 可以替换外部代码/主体，同时保留提供者异常为上下文； SDK 映射保留 LiteLLM
    # 作为显式原因。
    #
    current: BaseException | None = exception
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OpenAIAPIError) and (
            current.code in codes or current.type in codes
        ):
            return True
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return False


def is_budget_exceeded_error(exception: BaseException) -> bool:
    """在 SDK 错误映射之前或之后识别明确的预算拒绝。"""
    if isinstance(exception, BudgetExceededError):
        return True
    if not isinstance(exception, (OpenAIRateLimitError, LLMRateLimitError)):
        return False
    message = str(exception).lower()
    return (
        _has_rate_limit_code(exception, ("budget_exceeded",))
        or "budget_exceeded" in message
        or "budget has been exceeded" in message
    )


def is_quota_exhaustion_error(exception: BaseException) -> bool:
    """确定需要重置或增加限制的用尽配额。"""
    s = str(exception).lower()
    return (
        is_budget_exceeded_error(exception)
        or _has_rate_limit_code(exception, QUOTA_EXHAUSTION_PATTERNS)
        or any(p in s for p in QUOTA_EXHAUSTION_PATTERNS)
    )


def looks_like_auth_error(exception: Exception) -> bool:
    # 当提供者/LiteLLM 引发显式 401/403 时，信任键入的异常 - 其消息文本可能不包含下面的
    # 启发式模式。
    #
    if isinstance(exception, (AuthenticationError, PermissionDeniedError)):
        return True
    if not isinstance(exception, (BadRequestError, OpenAIError)):
        return False
    s = str(exception).lower()
    if any(p in s for p in AUTH_PATTERNS):
        return True
    # 一些提供商在消息文本中包含明确的状态代码
    for code in ("status 401", "status 403"):
        if code in s:
            return True
    return False


def is_content_policy_violation(exception: Exception) -> bool:
    if isinstance(exception, ContentPolicyViolationError):
        return True
    if not isinstance(exception, (BadRequestError, OpenAIError)):
        return False
    s = str(exception).lower()
    return any(p in s for p in CONTENT_POLICY_PATTERNS)


def is_transient_http_error(exception: BaseException) -> bool:
    """匹配提供者 HTTP 失败符合重试和模型回退方案。"""
    return isinstance(exception, APIError) and (
        exception.status_code in (408, 409, 429) or 500 <= exception.status_code < 600
    )
