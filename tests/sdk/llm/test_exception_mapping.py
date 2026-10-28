import httpx
from litellm.exceptions import (
    AuthenticationError,
    BadRequestError,
    ContentPolicyViolationError,
    InternalServerError,
    PermissionDeniedError,
)

from openhands.sdk.llm.exceptions import (
    LLMAuthenticationError,
    LLMBadRequestError,
    LLMContentPolicyViolationError,
    LLMMalformedConversationHistoryError,
    map_provider_exception,
)


MODEL = "test-model"
PROVIDER = "test-provider"


def test_map_auth_error_from_bad_request():
    e = BadRequestError("Invalid API key provided", MODEL, PROVIDER)
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMAuthenticationError)


def test_map_auth_error_from_openai_error():
    # OpenAIError 有奇怪的行为； 创建一个 BadRequestError 来包装类似身份验证的消息，因为
    # 提供商通常通过 LiteLLM 中的 BadRequestError 路由身份验证问题
    #
    e = BadRequestError("status 401 Unauthorized: missing API key", MODEL, PROVIDER)
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMAuthenticationError)


def test_map_typed_authentication_error_without_pattern_match():
    # 从 LiteLLM 键入 401，其消息文本不包含任何身份验证启发式模式 - 仍应通过 isinstance
    # 检查进行映射。
    #
    e = AuthenticationError("Bearer token expired", PROVIDER, MODEL)
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMAuthenticationError)


def test_map_typed_permission_denied_error():
    response = httpx.Response(
        status_code=403,
        request=httpx.Request("POST", "https://example.test"),
    )
    e = PermissionDeniedError("Region not allowed", PROVIDER, MODEL, response)
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMAuthenticationError)


def test_map_malformed_tool_history_bad_request():
    e = BadRequestError(
        (
            'AnthropicException - {"type":"error","error":{"type":'
            '"invalid_request_error","message":"messages.134: `tool_use` '
            "ids were found without `tool_result` blocks immediately after: "
            "toolu_01Aye4s5HrR2uXwXFYgtQi4H. Each `tool_use` block must have "
            'a corresponding `tool_result` block in the next message."}}'
        ),
        MODEL,
        PROVIDER,
    )
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMMalformedConversationHistoryError)


def test_map_openai_tool_argument_parse_internal_server_error():
    e = InternalServerError(
        (
            "OpenAIException - Failed to parse tool call arguments as JSON: "
            "invalid string: missing closing quote"
        ),
        PROVIDER,
        MODEL,
    )
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMMalformedConversationHistoryError)


def test_map_typed_content_policy_violation():
    e = ContentPolicyViolationError(
        "Output blocked by content filtering policy", MODEL, PROVIDER
    )
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMContentPolicyViolationError)
    # LLMBadRequestError 的子类型保留了对现有处理器的兼容性。
    assert isinstance(mapped, LLMBadRequestError)


def test_map_content_policy_violation_text_fallback():
    # 代理/别名提供者可能会将类型化的类扁平化为普通的 400。
    e = BadRequestError(
        "AnthropicException - Output blocked by content filtering policy",
        MODEL,
        PROVIDER,
    )
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMContentPolicyViolationError)


def test_map_generic_bad_request():
    e = BadRequestError("Some client-side error not related to auth", MODEL, PROVIDER)
    mapped = map_provider_exception(e)
    assert isinstance(mapped, LLMBadRequestError)
    # 通用 400 必须不被错误分类为内容策略。
    assert not isinstance(mapped, LLMContentPolicyViolationError)


def test_passthrough_unknown_exception():
    class MyCustom(Exception):
        pass

    e = MyCustom("random")
    mapped = map_provider_exception(e)
    assert mapped is e
