from __future__ import annotations

from litellm.exceptions import (
    APIConnectionError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout as LiteLLMTimeout,
)

from .classifier import (
    is_content_policy_violation,
    is_context_window_exceeded,
    looks_like_auth_error,
    looks_like_malformed_conversation_history_error,
)
from .types import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMContentPolicyViolationError,
    LLMContextWindowExceedError,
    LLMMalformedConversationHistoryError,
    LLMRateLimitError,
    LLMServiceUnavailableError,
    LLMTimeoutError,
)


def map_provider_exception(exception: Exception) -> Exception:
    """
    将提供程序/LiteLLM 异常映射到 SDK 类型的异常。

    如果没有映射适用，则返回原始异常。
    """
    # 上下文窗口超出第一（正常重试中优先级最高）
    if is_context_window_exceeded(exception):
        return LLMContextWindowExceedError(str(exception))

    # 尽管恢复路径仍然使用上下文压缩，但格式错误的提示词历史记录与上下文窗口耗尽不同。
    #
    if looks_like_malformed_conversation_history_error(exception):
        return LLMMalformedConversationHistoryError(str(exception))

    # 类似 Auth 的错误通常显示为带有特定文本的 BadRequest/OpenAIError
    if looks_like_auth_error(exception):
        return LLMAuthenticationError(str(exception))

    if isinstance(exception, RateLimitError):
        return LLMRateLimitError(str(exception))

    if isinstance(exception, LiteLLMTimeout):
        return LLMTimeoutError(str(exception))

    # 连接和服务端可用性问题 → 服务不可用
    if isinstance(
        exception, (APIConnectionError, ServiceUnavailableError, InternalServerError)
    ):
        return LLMServiceUnavailableError(str(exception))

    # 内容策略块是确定性的 4xx； 将它们与一般的错误请求区分开来，以便智能体可以软恢复而
    # 不是硬错误。
    #
    if is_content_policy_violation(exception):
        return LLMContentPolicyViolationError(str(exception))

    # 通用客户端 4xx 错误
    if isinstance(exception, BadRequestError):
        return LLMBadRequestError(str(exception))

    # 未知：让调用者重新引发原始错误
    return exception
