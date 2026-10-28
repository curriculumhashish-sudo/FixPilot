class LLMError(Exception):
    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


# 一般响应解析/验证错误
class LLMMalformedActionError(LLMError):
    def __init__(self, message: str = "Malformed response") -> None:
        super().__init__(message)


class LLMNoActionError(LLMError):
    def __init__(self, message: str = "Agent must return an action") -> None:
        super().__init__(message)


class LLMResponseError(LLMError):
    def __init__(
        self, message: str = "Failed to retrieve action from LLM response"
    ) -> None:
        super().__init__(message)


# 函数调用转换/验证
class FunctionCallConversionError(LLMError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class FunctionCallValidationError(LLMError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class FunctionCallNotExistsError(LLMError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


# 提供商/运输相关
class LLMNoResponseError(LLMError):
    def __init__(
        self,
        message: str = (
            "LLM did not return a response. This is only seen in Gemini models so far."
        ),
    ) -> None:
        super().__init__(message)


class LLMContextWindowExceedError(LLMError):
    def __init__(
        self,
        message: str = (
            "Conversation history longer than LLM context window limit. "
            "Consider enabling a condenser or shortening inputs."
        ),
    ) -> None:
        super().__init__(message)


class LLMMalformedConversationHistoryError(LLMError):
    def __init__(
        self,
        message: str = (
            "Conversation history produced an invalid LLM request. "
            "Consider retrying with condensed history and investigating the "
            "event stream."
        ),
    ) -> None:
        super().__init__(message)


class LLMContextWindowTooSmallError(LLMError):
    """当模型的上下文窗口太小而 OpenHands 无法工作时引发。"""

    def __init__(
        self,
        context_window: int,
        min_required: int = 16384,
        message: str | None = None,
    ) -> None:
        if message is None:
            message = (
                f"The configured model has a context window of {context_window:,} "
                f"tokens, which is below the minimum of {min_required:,} tokens "
                "required for OpenHands to function properly.\n\n"
                "For local LLMs (Ollama, LM Studio, etc.), increase the context "
                "window.\n"
                "For cloud providers, verify you're using the correct model "
                "variant.\n\n"
                "For configuration instructions, see:\n"
                "  https://docs.openhands.dev/openhands/usage/llms/local-llms\n\n"
                "To override this check (not recommended), set the environment "
                "variable:\n"
                "  ALLOW_SHORT_CONTEXT_WINDOWS=true"
            )
        super().__init__(message)
        self.context_window = context_window
        self.min_required = min_required


class LLMAuthenticationError(LLMError):
    def __init__(self, message: str = "Invalid or missing API credentials") -> None:
        super().__init__(message)


class LLMRateLimitError(LLMError):
    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message)


class LLMTimeoutError(LLMError):
    def __init__(self, message: str = "LLM request timed out") -> None:
        super().__init__(message)


class LLMServiceUnavailableError(LLMError):
    def __init__(self, message: str = "LLM service unavailable") -> None:
        super().__init__(message)


class LLMBadRequestError(LLMError):
    def __init__(self, message: str = "Bad request to LLM provider") -> None:
        super().__init__(message)


class LLMContentPolicyViolationError(LLMBadRequestError):
    """提供者通过其内容过滤器阻止请求/响应。

    子类 LLMBadRequestError 为了兼容旧版本。 确定性在（消息，模型）：裸体重试重复调用
    同一个过滤器，因此恢复需要更改请求，而不是重新发送。
    """

    def __init__(
        self, message: str = "Output blocked by content filtering policy"
    ) -> None:
        super().__init__(message)


# 其他
class UserCancelledError(Exception):
    def __init__(self, message: str = "User cancelled the request") -> None:
        super().__init__(message)


class OperationCancelled(Exception):
    def __init__(self, message: str = "Operation was cancelled") -> None:
        super().__init__(message)
