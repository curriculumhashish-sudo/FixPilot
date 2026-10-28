from __future__ import annotations

import asyncio
import copy
import json
import os
import threading
import warnings
from collections.abc import (
    AsyncIterable,
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    Sequence,
)
from contextvars import ContextVar
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    Self,
    TypeVar,
    get_args,
    get_origin,
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    SecretStr,
    computed_field,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from openhands.sdk.llm._response_stream import (
    OutputItemEvent,
    ResponseStreamEvent,
    async_response_events,
    completed_response as get_completed_response,
    response_events,
)
from openhands.sdk.llm._tokenizer import (
    ChatTemplateTokenizer,
    chat_template_tokenizer,
    count_tokenized_output,
    load_chat_template_tokenizer,
)
from openhands.sdk.llm.exceptions.classifier import is_transient_http_error
from openhands.sdk.llm.fallback_strategy import FallbackStrategy
from openhands.sdk.llm.utils.model_info import get_litellm_model_info
from openhands.sdk.llm.utils.runtime_metadata import (
    ModelRuntimeMetadata,
    aresolve_provider_metadata,
    cache_key as runtime_metadata_cache_key,
    cached_metadata,
    in_negative_cache,
    resolve_provider_metadata_sync,
    store_result,
)
from openhands.sdk.settings.metadata import SettingProminence, field_meta
from openhands.sdk.utils.deprecation import warn_deprecated
from openhands.sdk.utils.pydantic_secrets import serialize_secret, validate_secret


if TYPE_CHECKING:  # type hints only, avoid runtime import cycle
    from openhands.sdk.llm.auth import SupportedVendor
    from openhands.sdk.llm.auth.openai import OpenAIAuthMethod
    from openhands.sdk.llm.call_context import LLMCallContext
    from openhands.sdk.tool.tool import ToolDefinition

from openhands.sdk.llm.auth.openai import transform_for_subscription


with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import litellm

from typing import Final, cast

from litellm import (
    ChatCompletionToolParam,
    ResponseInputParam,
    acompletion as litellm_acompletion,
    completion as litellm_completion,
)
from litellm.exceptions import (
    APIConnectionError,
    BadGatewayError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout as LiteLLMTimeout,
)
from litellm.responses.main import (
    aresponses as litellm_aresponses,
    responses as litellm_responses,
)
from litellm.types.llms.openai import (
    OutputTextDeltaEvent,
    ReasoningSummaryTextDeltaEvent,
    RefusalDeltaEvent,
    ResponseCompletedEvent,
    ResponsesAPIResponse,
    ResponsesAPIStreamEvents,
)
from litellm.types.utils import (
    Delta,
    ModelResponse,
    ModelResponseStream,
    StreamingChoices,
)
from litellm.utils import (
    create_pretrained_tokenizer,
    token_counter,
)
from tenacity import retry_if_exception, retry_if_exception_type

from openhands.sdk.llm.exceptions import (
    LLMContextWindowTooSmallError,
    LLMNoResponseError,
    is_prompt_cache_too_small,
    is_quota_exhaustion_error,
    looks_like_auth_error,
    map_provider_exception,
)

# OpenHands 公用事业
from openhands.sdk.llm.llm_response import LLMResponse
from openhands.sdk.llm.message import (
    Message,
)
from openhands.sdk.llm.mixins.non_native_fc import NonNativeToolCallingMixin
from openhands.sdk.llm.options.chat_options import select_chat_options
from openhands.sdk.llm.options.responses_options import select_responses_options
from openhands.sdk.llm.streaming import (
    AnyTokenCallbackType,
    TokenCallbackType,
    _invoke_token_callback,
)
from openhands.sdk.llm.utils.image_inline import (
    amaybe_inline_image_urls,
    maybe_inline_image_urls,
)
from openhands.sdk.llm.utils.image_resize import maybe_resize_messages_for_provider
from openhands.sdk.llm.utils.litellm_provider import LLMProvider
from openhands.sdk.llm.utils.metrics import Metrics
from openhands.sdk.llm.utils.model_features import ModelFeatures, get_features
from openhands.sdk.llm.utils.openhands_provider import (
    LiteLLMCallKwargs,
    canonicalize_openhands_llm_payload,
    litellm_call_kwargs,
)
from openhands.sdk.llm.utils.retry_mixin import RetryMixin
from openhands.sdk.llm.utils.telemetry import Telemetry
from openhands.sdk.llm.utils.vertex_preflight import assert_vertex_sdk_available
from openhands.sdk.logger import ENV_LOG_DIR, get_logger


logger = get_logger(__name__)

litellm.modify_params = True

_serialized_is_subscription = ContextVar(
    "serialized_is_subscription",
    default=False,
)

__all__ = ["LLM"]


# 我们重试的例外情况
LLM_RETRY_EXCEPTIONS: Final[tuple[type[Exception], ...]] = (
    APIConnectionError,
    BadGatewayError,
    RateLimitError,
    ServiceUnavailableError,
    LiteLLMTimeout,
    InternalServerError,
    LLMNoResponseError,
)

# OpenHands 正常运行所需的最小上下文窗口大小。 基于典型用法：系统提示词 (~2k) + 对话历史
# 记录 (~4k)
# + 工具定义 (~2k) + 工作内存 (~8k) = 至少~16k。
MIN_CONTEXT_WINDOW_TOKENS: Final[int] = 16384

# 环境变量覆盖最小上下文窗口检查
ENV_ALLOW_SHORT_CONTEXT_WINDOWS: Final[str] = "ALLOW_SHORT_CONTEXT_WINDOWS"

# 当模型信息仅提供“max_tokens”（不明确）时，默认最大输出 token。 一些提供商使用“
# max_tokens”表示总数上下文窗口，而不是输出限制。 此上限可防止请求超出上下文窗口的输出。
#  16384 是适用于大多数模型的安全默认值（GPT-4o：16k，Claude：8k）。
#
DEFAULT_MAX_OUTPUT_TOKENS_CAP: Final[int] = 16384

# 一些提供商（特别是 Anthropic 模型的 AWS Bedrock）强制执行
# ``input_tokens + max_tokens <= context_window`` 在单个共享窗口上。 对于这些提供者，我
# 们在请求时限制每个请求的输出预算，因此我们注入的默认值``max_tokens``（默认为模型的完整
# ``max_output_tokens``——e.g。 Sonnet 4.5 的 64k）无法将大输入请求推过上下文窗口。 请参
# 阅 BerriAI/litellm#17900 了解导致此清单的上游默认更改。
#
JOINT_BUDGET_SAFETY_MARGIN_TOKENS: Final[int] = 256
JOINT_BUDGET_MIN_OUTPUT_TOKENS: Final[int] = 1024
# 已知可强制执行联合输入/输出的提供者名称前缀词元预算。 保留为狭窄的允许列表，因此具有独
# 立输入/输出窗口的直接提供者（Anthropic、OpenAI 等）不会受到影响。 我们按前缀匹配，因为
#  LiteLLM 同时使用 ``bedrock``（原始提供者推断）和
# ``bedrock_converse``（Anthropic-基岩路线，通过模型注册表浮出水面）相同的底层 API。
#
_JOINT_BUDGET_PROVIDER_PREFIXES: Final[tuple[str, ...]] = ("bedrock",)

# 机密-LLM 上的轴承字段。 作为单一事实来源，以便需要步行的调用者机密 (e.g. 保存路径上的
# 密码感知解密）留在同步和下面的序列化器中。
#
LLM_SECRET_FIELDS: Final[tuple[str, ...]] = (
    "api_key",
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
)

LLM_PROFILE_SCHEMA_VERSION: Final[int] = 1

_T = TypeVar("_T")


def __getattr__(name: str) -> Any:
    """提供调用上下文的已弃用预重构导入路径。"""
    if name == "LLMCallContext":
        warn_deprecated(
            "openhands.sdk.llm.llm.LLMCallContext",
            deprecated_in="1.42.1",
            removed_in="2.0.0",
            details="Import LLMCallContext from openhands.sdk.llm instead.",
            stacklevel=2,
        )
        from openhands.sdk.llm.call_context import LLMCallContext

        return LLMCallContext
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class LLM(BaseModel, RetryMixin, NonNativeToolCallingMixin):
    """OpenHands 智能体的语言模型接口。

    LLM类提供了一个统一的接口，用于通过LiteLLM库与各种语言模型进行交互。 它处理模型配
    置、API 身份验证、重试逻辑和工具调用功能。

    Attributes:
        model: 型号名称（e.g.，“gpt-5.6”）。
        api_key: 身份验证的 API 键。
        base_url: 自定义 API 基础 URL。
        num_retries: 失败请求的尝试次数为重试。
        timeout: 请求超时（以秒为单位）。

    Example:
        ```python
        from openhands.sdk import LLM
        from pydantic import SecretStr

        llm = LLM(
            model="gpt-5.6",
            api_key=SecretStr("your-api-key"),
            usage_id="my-agent"
        )
        # 与智能体或对话一起使用
        ```
    """

    # =========================================================================
    # 配置字段
    # =========================================================================

    model: str = Field(
        default="gpt-5.6",
        description="Model name.",
        json_schema_extra=field_meta(SettingProminence.CRITICAL),
    )
    api_key: str | SecretStr | None = Field(
        default=None,
        description="API key.",
        json_schema_extra=field_meta(
            SettingProminence.CRITICAL,
            label="API Key",
        ),
    )
    provider_connection_id: str | None = Field(
        default=None,
        description=(
            "Optional provider connection whose shared API key and base URL "
            "are resolved and applied each time this LLM profile is loaded "
            "(read-at-use). When set, the profile stores no inline api_key or "
            "base_url of its own."
        ),
        json_schema_extra=field_meta(SettingProminence.MAJOR),
    )
    auth_type: Literal["api_key", "subscription"] = Field(
        default="api_key",
        description="Authentication mode for the LLM.",
        json_schema_extra=field_meta(
            SettingProminence.CRITICAL,
            label="Authentication",
        ),
    )
    subscription_vendor: Literal["openai"] | None = Field(
        default=None,
        description="Subscription provider for subscription-backed LLM access.",
        json_schema_extra=field_meta(
            SettingProminence.CRITICAL,
            label="Subscription provider",
            depends_on=("auth_type",),
        ),
    )
    base_url: str | None = Field(
        default=None,
        description="Custom base URL.",
        json_schema_extra=field_meta(SettingProminence.MAJOR),
    )
    api_version: str | None = Field(
        default=None,
        description="API version (e.g., Azure).",
        json_schema_extra=field_meta(),
    )

    aws_access_key_id: str | SecretStr | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )
    aws_secret_access_key: str | SecretStr | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )
    aws_session_token: str | SecretStr | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )
    aws_region_name: str | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )
    aws_profile_name: str | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )
    aws_role_name: str | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )
    aws_session_name: str | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )
    aws_bedrock_runtime_endpoint: str | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )

    # OpenRouter使用HTTP-Referer作为应用标识进行排名。 保持稳定，除非 OpenRouter 应用属
    # 性被迁移。
    #
    openrouter_site_url: str = Field(
        default="https://docs.all-hands.dev/",
        json_schema_extra=field_meta(),
    )
    openrouter_app_name: str = Field(
        default="OpenHands",
        json_schema_extra=field_meta(),
    )

    num_retries: int = Field(default=5, ge=0, json_schema_extra=field_meta())
    retry_multiplier: float = Field(default=8.0, ge=0, json_schema_extra=field_meta())
    retry_min_wait: int = Field(default=8, ge=0, json_schema_extra=field_meta())
    retry_max_wait: int = Field(default=64, ge=0, json_schema_extra=field_meta())

    timeout: int | None = Field(
        default=300,
        ge=0,
        description=(
            "HTTP and hard per-attempt timeout in seconds. Default is 300s "
            "(5 minutes). Set to None to disable the hard timeout."
        ),
        json_schema_extra=field_meta(),
    )
    stream_idle_timeout: float | None = Field(
        default=300,
        ge=0,
        description=(
            "Maximum seconds between chunks in an asynchronous streaming "
            "response. Default is 300s (5 minutes); set to None to disable."
        ),
        json_schema_extra=field_meta(),
    )

    max_message_chars: int = Field(
        default=30_000,
        ge=1,
        description="Approx max chars in each event/content sent to the LLM.",
        json_schema_extra=field_meta(),
    )

    temperature: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Sampling temperature for response generation. "
            "Defaults to None (uses provider default temperature). "
            "Set to 0.0 for deterministic outputs, "
            "or higher values (0.7-1.0) for more creative responses."
        ),
        json_schema_extra=field_meta(),
    )
    top_p: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Nucleus sampling parameter. "
            "Defaults to None (uses provider default). "
            "Set to a value between 0 and 1 to control diversity of outputs."
        ),
        json_schema_extra=field_meta(),
    )
    top_k: float | None = Field(default=None, ge=0, json_schema_extra=field_meta())

    max_input_tokens: int | None = Field(
        default=None,
        ge=1,
        description="The maximum number of input tokens. "
        "Note that this is currently unused, and the value at runtime is actually"
        " the total tokens in OpenAI (e.g. 128,000 tokens for GPT-4).",
        json_schema_extra=field_meta(),
    )
    max_output_tokens: int | None = Field(
        default=None,
        ge=1,
        description="The maximum number of output tokens. This is sent to the LLM.",
        json_schema_extra=field_meta(),
    )
    model_canonical_name: str | None = Field(
        default=None,
        description=(
            "Optional canonical model name for feature registry lookups. "
            "The OpenHands SDK maintains a model feature registry that "
            "maps model names to capabilities (e.g., vision support, "
            "prompt caching, responses API support). When using proxied or "
            "aliased model identifiers, set this field to the canonical "
            "model name (e.g., 'openai/gpt-4o') to ensure correct "
            "capability detection. If not provided, the 'model' field "
            "will be used for capability lookups."
        ),
        json_schema_extra=field_meta(),
    )
    api_mode: Literal["auto", "chat", "responses"] = Field(
        default="auto",
        description=(
            "LLM API endpoint mode. 'auto' resolves from model metadata and "
            "SDK fallbacks; use 'chat' or 'responses' to override endpoint "
            "selection for proxy aliases and newly released models."
        ),
        json_schema_extra=field_meta(),
    )
    capability_overrides: dict[str, bool | str] = Field(
        default_factory=dict,
        description=(
            "Explicit model capability overrides. Supported keys include "
            "supports_reasoning_effort, thinking_mode (adaptive, manual, none, "
            "or unknown), supports_sampling_params, supports_prompt_cache, "
            "supports_stop_words, supports_responses_api, supports_vision, and "
            "supports_prompt_cache_retention. Overrides take precedence over "
            "LiteLLM metadata and SDK fallbacks."
        ),
        json_schema_extra=field_meta(),
    )
    extra_headers: dict[str, str] | None = Field(
        default=None,
        description="Optional HTTP headers to forward to LiteLLM requests.",
        json_schema_extra=field_meta(),
    )
    input_cost_per_token: float | None = Field(
        default=None,
        ge=0,
        description="The cost per input token. This will available in logs for user.",
        json_schema_extra=field_meta(),
    )
    output_cost_per_token: float | None = Field(
        default=None,
        ge=0,
        description="The cost per output token. This will available in logs for user.",
        json_schema_extra=field_meta(),
    )
    ollama_base_url: str | None = Field(
        default=None,
        json_schema_extra=field_meta(),
    )

    stream: bool = Field(
        default=False,
        description=(
            "Enable streaming responses from the LLM. "
            "When enabled, the provided `on_token` callback in .completions "
            "and .responses will be invoked for each chunk of tokens."
        ),
        json_schema_extra=field_meta(),
    )
    drop_params: bool = Field(default=True, json_schema_extra=field_meta())
    disable_vision: bool | None = Field(
        default=None,
        description="If model is vision capable, this option allows to disable image "
        "processing (useful for cost reduction).",
        json_schema_extra=field_meta(),
    )
    disable_stop_word: bool | None = Field(
        default=False,
        description="Disable using of stop word.",
        json_schema_extra=field_meta(),
    )
    caching_prompt: bool = Field(
        default=True,
        description="Enable caching of prompts.",
        json_schema_extra=field_meta(),
    )
    log_completions: bool = Field(
        default=False,
        description="Enable logging of completions.",
        json_schema_extra=field_meta(),
    )
    log_completions_folder: str = Field(
        default=os.path.join(ENV_LOG_DIR, "completions"),
        description="The folder to log LLM completions to. "
        "Required if log_completions is True.",
        json_schema_extra=field_meta(),
    )
    custom_tokenizer: str | None = Field(
        default=None,
        description="A custom tokenizer to use for token counting.",
        json_schema_extra=field_meta(),
    )
    native_tool_calling: bool = Field(
        default=True,
        description="Whether to use native tool calling.",
        json_schema_extra=field_meta(),
    )
    force_string_serializer: bool | None = Field(
        default=None,
        description=(
            "Force using string content serializer when sending to LLM API. "
            "If None (default), auto-detect based on model. "
            "Useful for providers that do not support list content, "
            "like HuggingFace and Groq."
        ),
        json_schema_extra=field_meta(),
    )
    inline_image_urls: bool | None = Field(
        default=None,
        description=(
            "If True, fetch any http(s) image URL in outgoing messages and "
            "inline it as a base64 ``data:`` URL before sending. If None "
            "(default), auto-detect based on model (some APIs such as "
            "Moonshot's public Kimi endpoint reject URL-formatted images "
            "and require base64). Set this explicitly when the model is "
            "reached through a proxy alias that hides the underlying "
            "provider (e.g. ``litellm_proxy/<custom-alias>``). Note: "
            "inlining only runs when ``vision_is_active()`` is True, so "
            "the alias must still be recognised as vision-capable by the "
            "SDK feature registry or proxy model metadata."
        ),
        json_schema_extra=field_meta(),
    )
    reasoning_effort: (
        Literal["low", "medium", "high", "xhigh", "none"] | SkipJsonSchema[str] | None
    ) = Field(
        default="high",
        description=(
            "Provider-neutral reasoning effort. Common values include 'none', "
            "'minimal', 'low', 'medium', 'high', 'xhigh', and 'max'. The SDK "
            "accepts future provider values and lets LiteLLM translate them."
        ),
        json_schema_extra=field_meta(),
    )
    reasoning_summary: Literal["auto", "concise", "detailed"] | None = Field(
        default=None,
        description="The level of detail for reasoning summaries. "
        "This is a string that can be one of 'auto', 'concise', or 'detailed'. "
        "Requires verified OpenAI organization. Only sent when explicitly set.",
        json_schema_extra=field_meta(),
    )
    enable_encrypted_reasoning: bool = Field(
        default=True,
        description="If True, ask for ['reasoning.encrypted_content'] "
        "in Responses API include.",
        json_schema_extra=field_meta(),
    )
    # 提示词缓存保留根据聊天选项中的模型功能进行过滤。
    prompt_cache_retention: str | None = Field(
        default="24h",
        description=(
            "Retention policy for prompt cache. Only sent for supported models "
            "(GPT-5+ and GPT-4.1, excluding Azure deployments); explicitly "
            "stripped for all others."
        ),
        json_schema_extra=field_meta(),
    )
    extended_thinking_budget: int | None = Field(
        default=200_000,
        description=(
            "Legacy token budget for models confirmed to use manual Anthropic "
            "extended thinking. Ignored for adaptive-thinking models. Prefer "
            "reasoning_effort for new integrations."
        ),
        json_schema_extra=field_meta(),
    )
    seed: int | None = Field(
        default=None,
        description="The seed to use for random number generation.",
        json_schema_extra=field_meta(),
    )
    usage_id: str = Field(
        default="default",
        serialization_alias="usage_id",
        description=(
            "Unique usage identifier for the LLM. Used for registry lookups, "
            "telemetry, and spend tracking."
        ),
        json_schema_extra=field_meta(),
    )
    litellm_extra_body: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Additional key-value pairs to pass to litellm's extra_body parameter. "
            "This is useful for custom inference endpoints that need additional "
            "parameters for configuration, routing, or advanced features. "
            "NOTE: Not all LLM providers support extra_body parameters. Some providers "
            "(e.g., OpenAI) may reject requests with unrecognized options. "
            "This is commonly supported by: "
            "- LiteLLM proxy servers (routing metadata, tracing) "
            "- vLLM endpoints (return_token_ids, etc.) "
            "- Custom inference clusters "
            "Examples: "
            "- Proxy routing: {'trace_version': '1.0.0', 'tags': ['agent:my-agent']} "
            "- vLLM features: {'return_token_ids': True}"
        ),
        json_schema_extra=field_meta(),
    )

    fallback_strategy: FallbackStrategy | None = Field(
        default=None,
        description=(
            "Optional fallback strategy for trying alternate LLMs on transient "
            "failure. Construct with FallbackStrategy(fallback_llms=[...])."
            "Excluded from serialization; must be reconfigured after load."
        ),
        exclude=True,
    )

    # =========================================================================
    # 内部字段（从转储中排除）
    # =========================================================================
    retry_listener: SkipJsonSchema[
        Callable[[int, int, BaseException | None], None] | None
    ] = Field(
        default=None,
        exclude=True,
    )
    _metrics: Metrics | None = PrivateAttr(default=None)
    # 仅限运行时的私有属性
    _model_info: Any = PrivateAttr(default=None)
    _tokenizer: dict[str, object] | None = PrivateAttr(default=None)
    _chat_template_tokenizer: ChatTemplateTokenizer | None = PrivateAttr(default=None)
    _telemetry: Telemetry | None = PrivateAttr(default=None)
    _is_subscription: bool = PrivateAttr(default=False)
    _subscription_credential_store: Any = PrivateAttr(default=None)
    _subscription_credentials: Any = PrivateAttr(default=None)
    _provider_info: LLMProvider | None = PrivateAttr(default=None)
    _effective_max_input_tokens: int | None = PrivateAttr(default=None)
    _effective_max_output_tokens: int | None = PrivateAttr(default=None)
    # 提供者感知的运行时元数据延迟解析（请参阅
    # `utils/runtime_metadata.py`). `fetched_at`和`negative_until`是用于正/负缓存的单调
    # 时间戳；
    # 每次查找 * 开始 *，`generation` 会被更新，这样就不会有 `resolve_runtime_metadata`
    # 生成的新探针覆盖较早开始较晚结束的探针的结果。
    #
    _runtime_metadata: ModelRuntimeMetadata | None = PrivateAttr(default=None)
    _runtime_metadata_fetched_at: float | None = PrivateAttr(default=None)
    _runtime_metadata_negative_until: float | None = PrivateAttr(default=None)
    _runtime_metadata_key: tuple[str, str, str] | None = PrivateAttr(default=None)
    # 用于运行时元数据解析的单次飞行/过时验证。 每个
    # *启动*记录该记录所属的生成版本（见上文）。 a
    # 已完成的探测仅在该一代仍然是最新的情况下才会发布其结果，因此较慢的较早启动的探测永
    # 远不会覆盖较新的探测。
    #
    _runtime_metadata_generation: int = PrivateAttr(default=0)
    # 保护上面的运行时元数据缓存字段。 同步解析器可以由工作器线程驱动，并且异步解析器还
    # 可以存储结果，因此读取/检查和存储保持原子性。 ClassVar（共享）； 关键部分很小并且
    # 从不覆盖网络 I/O。
    #
    _runtime_metadata_lock: ClassVar[threading.Lock] = threading.Lock()
    # 可选回调，返回新解析的 API 键。 设置后，身份验证失败（HTTP 401，e.g. LiteLLM 报告
    # 为 ``token_not_found_in_db`` 的轮换/修复托管代理密钥）会触发该密钥的一次重新解析，
    # 然后触发一个重试调用。 这是对陈旧凭据达到沙箱运行时智能体的近期缓解措施； 持久修复
    # 仅供参考凭据交付 (#4288)。 保持为 PrivateAttr，因此它永远不会已序列化进入对话状态
    # 。
    #
    _api_key_refresh_hook: Callable[[], str | SecretStr | None] | None = PrivateAttr(
        default=None
    )
    # 递归防护：在刷新的副本上设置，以便仍然失败的密钥不会循环。 每次调用链中，有一个刷
    # 新和一个重试。
    #
    _auth_refresh_attempted: bool = PrivateAttr(default=False)
    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="ignore", arbitrary_types_allowed=True
    )

    # =========================================================================
    # 验证器
    # =========================================================================
    @model_validator(mode="before")
    @classmethod
    def _capture_serialized_is_subscription(cls, data):
        if isinstance(data, dict):
            _serialized_is_subscription.set(bool(data.get("is_subscription")))
        return data

    @field_validator(
        "api_key", "aws_access_key_id", "aws_secret_access_key", "aws_session_token"
    )
    @classmethod
    def _validate_secrets(cls, v: str | SecretStr | None, info) -> SecretStr | None:
        return validate_secret(v, info)

    @model_validator(mode="before")
    @classmethod
    def _coerce_inputs(cls, data):
        if not isinstance(data, dict):
            return data
        d = dict(data)

        model_val = d.get("model")
        if not model_val:
            raise ValueError("model must be specified in LLM")

        if "stream_idle_timeout" not in d:
            d["stream_idle_timeout"] = d.get("timeout", 300)

        # Azure 默认版本
        if model_val.startswith("azure") and not d.get("api_version"):
            d["api_version"] = "2024-12-01-preview"

        # 修复 base_url 为直接 OpenAI - API 需要 /v1 后缀如果 base_url 是“
        # https://api.openai.com",  设置为 None 以使用 LiteLLM 默认值
        #
        if model_val.startswith("openai/"):
            base = d.get("base_url")
            if base == "https://api.openai.com" or base == "https://api.openai.com/":
                d["base_url"] = None  # 让 LiteLLM 使用其默认值，其中包括 /v1

        return d

    @model_validator(mode="after")
    def _post_init(self):
        # 注意：AWS 凭据和 OpenRouter 站点/应用程序标识符为不
        # 写到这里的``os.environ``。 在多租户 Agent Server 中这样做会让一个对话的凭据通
        # 过共享进程环境渗透到另一个对话中（请参阅问题 #3138）。 相反，AWS 凭据按每次调
        # 用流过 ``_aws_kwargs()``，OpenRouter ``HTTP-Referer`` / ``X-Title`` 标头按每次
        # 调用流过 ``_openrouter_headers()``。
        #

        # 指标+遥测接线。 守护两者：这个验证器重新运行 LLM 传递给另一个 Pydantic 模型
        # (e.g. RegistryEvent), and replacing _telemetry would silently drop any 回调来
        # 电者已通过 telemetry.set_*_callback().
        #
        if self._metrics is None:
            self._metrics = Metrics(model_name=self.model)

        if self._telemetry is None:
            self._telemetry = Telemetry(
                model_name=self.model,
                log_enabled=self.log_completions,
                log_dir=self.log_completions_folder if self.log_completions else None,
                input_cost_per_token=self.input_cost_per_token,
                output_cost_per_token=self.output_cost_per_token,
                metrics=self._metrics,
            )

        # 分词器
        if self.custom_tokenizer:
            self._chat_template_tokenizer = load_chat_template_tokenizer(
                self.custom_tokenizer
            )
            if self._chat_template_tokenizer is None:
                try:
                    self._tokenizer = create_pretrained_tokenizer(self.custom_tokenizer)
                except Exception:
                    logger.debug(
                        "Unable to load LiteLLM tokenizer for %s",
                        self.custom_tokenizer,
                        exc_info=True,
                    )
                    self._tokenizer = None

        self._refresh_litellm_metadata()

        logger.debug(
            f"LLM ready: model={self.model} base_url={self.base_url} "
            f"reasoning_effort={self.reasoning_effort} "
            f"temperature={self.temperature}"
        )
        return self

    def _refresh_litellm_metadata(self) -> None:
        call_kwargs = self._litellm_call_kwargs()
        self._provider_info = LLMProvider.from_model(
            model=call_kwargs["model"],
            api_base=call_kwargs["api_base"],
        )
        self._init_model_info_and_caps()

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        # Pydantic 无需重新运行验证器即可复制私有属性，即使对于深层复制也是如此，因此路
        # 由字段更新必须重建派生元数据。
        #
        copied = super().model_copy(update=update, deep=deep)
        route_changed = update is not None and any(
            k in update for k in ("model", "base_url", "litellm_extra_body")
        )
        if route_changed:
            copied._refresh_litellm_metadata()
            copied._reset_runtime_metadata_for_key()
        return copied

    def _openrouter_headers(self) -> dict[str, str]:
        """构建 OpenRouter HTTP-Referer / X-Title 标头以供每次调用使用。

        当两个字段均未设置时，返回一个空字典。 通过
        ``extra_headers`` 因此 LiteLLM 在 OpenRouter 请求上转发它们，而无需我们改变
        ``os.environ``（这会在多租
        户服务器中的对话中泄漏； 请参阅问题#3138）。
        """
        headers: dict[str, str] = {}
        if self.openrouter_site_url:
            headers["HTTP-Referer"] = self.openrouter_site_url
        if self.openrouter_app_name:
            headers["X-Title"] = self.openrouter_app_name
        return headers

    def _aws_kwargs(self) -> dict[str, str]:
        """为 AWS 参数构建 kwargs 字典以传递给 LiteLLM 调用。"""
        kw: dict[str, str] = {}
        if self.aws_access_key_id:
            assert isinstance(self.aws_access_key_id, SecretStr)
            kw["aws_access_key_id"] = self.aws_access_key_id.get_secret_value()
        if self.aws_secret_access_key:
            assert isinstance(self.aws_secret_access_key, SecretStr)
            kw["aws_secret_access_key"] = self.aws_secret_access_key.get_secret_value()
        if self.aws_session_token:
            assert isinstance(self.aws_session_token, SecretStr)
            kw["aws_session_token"] = self.aws_session_token.get_secret_value()
        if self.aws_region_name:
            kw["aws_region_name"] = self.aws_region_name
        if self.aws_profile_name:
            kw["aws_profile_name"] = self.aws_profile_name
        if self.aws_role_name:
            kw["aws_role_name"] = self.aws_role_name
        if self.aws_session_name:
            kw["aws_session_name"] = self.aws_session_name
        if self.aws_bedrock_runtime_endpoint:
            kw["aws_bedrock_runtime_endpoint"] = self.aws_bedrock_runtime_endpoint
        return kw

    def _retry_listener_fn(
        self, attempt_number: int, num_retries: int, _err: BaseException | None
    ) -> None:
        if self.retry_listener is not None:
            self.retry_listener(attempt_number, num_retries, _err)
        # 注意：不要在这里调用Telemetry.on_error。
        # 此函数针对每次重试失败（在下一次尝试之前）运行，这会创建嘈杂的重复错误日志。
        # completion()/responses() 异常处理程序在重试耗尽后调用 Telemetry.on_error（最终
        # 失败），这就是我们想要记录的内容。
        #

    # =========================================================================
    # 序列化器
    # =========================================================================
    @field_serializer(*LLM_SECRET_FIELDS, when_used="always")
    def _serialize_secrets(self, v: SecretStr | None, info):
        return serialize_secret(v, info)

    # =========================================================================
    # 公开 API
    # =========================================================================
    @property
    def metrics(self) -> Metrics:
        """获取此 LLM 实例的使用指标。

        Returns:
            包含词元用量、成本和其他统计信息的 Metrics 对象。

        Example:
            ```python
            cost = llm.metrics.accumulated_cost
            print(f"Total cost: ${cost}")
            ```
        """
        if self._metrics is None:
            self._metrics = Metrics(model_name=self.model)
        return self._metrics

    @property
    def telemetry(self) -> Telemetry:
        """获取此 LLM 实例的遥测处理程序。

        Returns:
            用于管理日志记录和指标的遥测对象回调。

        Example:
            ```python
            llm.telemetry.set_log_completions_callback(my_callback)
            ```
        """
        if self._telemetry is None:
            self._telemetry = Telemetry(
                model_name=self.model,
                log_enabled=self.log_completions,
                log_dir=self.log_completions_folder if self.log_completions else None,
                input_cost_per_token=self.input_cost_per_token,
                output_cost_per_token=self.output_cost_per_token,
                metrics=self.metrics,
            )
        return self._telemetry

    @computed_field(
        return_type=bool,
        description=(
            "Whether this LLM uses subscription-based authentication. "
            "Serialized so that subscription-specific request handling "
            "survives transport to a remote agent-server."
        ),
    )
    @property
    def is_subscription(self) -> bool:
        """检查此 LLM 是否使用基于订阅的身份验证。"""
        return self._is_subscription

    @is_subscription.setter
    def is_subscription(self, value: bool) -> None:
        self._is_subscription = value

    @property
    def requires_streaming(self) -> bool:
        """提供者是否要求所有请求的stream=True。

        当底层端点拒绝非流式传输请求时设置； 调用者必须保持流式传输启用，并且不能要求
         on_token 回调，因为响应在内部耗尽。
        """
        return self._is_subscription

    @model_validator(mode="wrap")
    @classmethod
    def _restore_is_subscription(cls, data, handler):
        token = _serialized_is_subscription.set(False)
        try:
            llm = handler(data)
            if _serialized_is_subscription.get():
                llm._is_subscription = True
            return llm
        finally:
            _serialized_is_subscription.reset(token)

    def restore_metrics(self, metrics: Metrics) -> None:
        # 仅由 ConversationStats 用于播种指标
        self._metrics = metrics
        # 将遥测数据保留在同步中，以便恢复后 LLM 调用记录到恢复的指标对象中，而不是 __
        # init__ 中的过时指标对象。
        #
        if self._telemetry is not None:
            self._telemetry.metrics = metrics

    def reset_metrics(self) -> None:
        """将指标和遥测重置为新实例。

        这是用于的 LLMRegistry 确保每个注册的 LLM 具有独立的指标，防止指标被共享 LLMs
         通过创建的 model_copy().

        当 LLM 复制 (e.g., 以创建上下文压缩器 LLM 从智能体 LLM) 时，Pydantic's
        model_copy() 默认进行浅拷贝，导致原始
        和复制的 LLM 共享同一个 Metrics 对象。 该方法允许注册表立即创建新的指标和监控
        数据，这样即使调用者没有首先访问 ``metrics`` 和
        /``telemetry``，复制的 LLM 也能准备好进行下一次完成调用。
        """
        self._metrics = Metrics(model_name=self.model)
        self._telemetry = Telemetry(
            model_name=self.model,
            log_enabled=self.log_completions,
            log_dir=self.log_completions_folder if self.log_completions else None,
            input_cost_per_token=self.input_cost_per_token,
            output_cost_per_token=self.output_cost_per_token,
            metrics=self._metrics,
        )

    def _handle_error(
        self,
        error: Exception,
        fallback_call_fn: Callable[[LLM], LLMResponse],
    ) -> LLMResponse:
        """处理完成/响应中的错误：尝试回退方案，然后映射并引发。

        必须从 except 块内调用。 要么返回 LLMResponse（回退方案成功），要么重新抛出（
        映射或原始）。
        """
        assert self._telemetry is not None
        self._telemetry.on_error(error)
        if self.fallback_strategy and self.fallback_strategy.should_fallback(error):
            result = self.fallback_strategy.try_fallback(
                primary_model=self.model,
                primary_error=error,
                primary_metrics=self.metrics,
                call_fn=fallback_call_fn,
            )
            if result is not None:
                return result
        mapped = map_provider_exception(error)
        if mapped is not error:
            raise mapped from error
        raise

    async def _ahandle_error(
        self,
        error: Exception,
        fallback_call_fn: Callable[[LLM], LLMResponse],
    ) -> LLMResponse:
        """异步：meth:`_handle_error` 的变体。

        *fallback_call_fn* 是同步（它调用回退方案LLM 的同步``completion``
        /``responses``)，因此回退方案尝试通过：func:`asyncio.loop.run_in_executor` 卸
        载到线程以避免阻塞事件循环。
        """
        assert self._telemetry is not None
        self._telemetry.on_error(error)
        if self.fallback_strategy and self.fallback_strategy.should_fallback(error):
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self.fallback_strategy.try_fallback,
                self.model,
                error,
                self.metrics,
                fallback_call_fn,
            )
            if result is not None:
                return result
        mapped = map_provider_exception(error)
        if mapped is not error:
            raise mapped from error
        raise

    # =========================================================================
    # 身份验证刷新（401 上刷新）
    # =========================================================================
    def set_api_key_refresh_hook(
        self, hook: Callable[[], str | SecretStr | None] | None
    ) -> None:
        """注册一个回调，在 401 上重新解析此 LLM 的 API 键。

        当完成/响应调用因身份验证错误而失败时，将调用一次钩子以获取新密钥； 如果它返
        回一个新值，则使用该键重试一次调用。 这可以缓解过时的托管/代理凭据到达沙箱运
        行时智能体 (e.g. 在服务器端托管密钥轮换或修复之后），否则第一次调用将失败并显
        示 ``401 token_not_found_in_db``。

        钩子必须是无阻塞的/便宜的； 在异步路径上，它在工作器线程中调用。 它被存储为私
        有属性并且永远不会已序列化进入会话状态。
        """
        self._api_key_refresh_hook = hook

    def _resolve_refreshed_api_key(self, error: Exception) -> SecretStr | None:
        """将新的 API 键返回到重试，或 ``None`` 跳过刷新。

        除非所有条件都成立，否则返回 ``None``：错误看起来像是身份验证失败，配置了刷新
        钩子，没有在当前调用链中尝试过刷新，这个 LLM 使用
        ``api_key`` 认证，并且钩子返回的密钥与当前密钥不同。
        """
        if self._auth_refresh_attempted:
            return None
        if self._api_key_refresh_hook is None:
            return None
        if self.auth_type != "api_key":
            return None
        if not looks_like_auth_error(error):
            return None
        try:
            new_key = self._api_key_refresh_hook()
        except Exception:
            # 片状钩子不能掩盖原始的身份验证错误； 记录并跳过刷新，以便调用者看到真正的
            # 401。
            #
            logger.warning(
                "API key refresh hook raised; skipping refresh and "
                "surfacing the original authentication error.",
                exc_info=True,
            )
            return None
        if new_key is None:
            return None
        new_secret = new_key if isinstance(new_key, SecretStr) else SecretStr(new_key)
        if not new_secret.get_secret_value():
            return None
        current = self._get_api_key_value()
        if current is not None and current == new_secret.get_secret_value():
            # 返回相同（仍被拒绝）密钥的刷新是无用的； 跳过重试并显示原始错误。
            #
            return None
        return new_secret

    def _auth_refreshed_llm(self, new_api_key: SecretStr) -> LLM:
        """使用刷新的密钥和递归防护集复制此 LLM。"""
        refreshed = self.model_copy(update={"api_key": new_api_key})
        refreshed._auth_refresh_attempted = True
        return refreshed

    # =========================================================================
    # 用于完成/完成/响应/响应的共享助手
    # =========================================================================

    def _make_retry_decorator(
        self,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """使用此 LLM 的重试设置返回配置的重试装饰器。

        用尽的津贴跳过退避。 提供商配额错误可能会回落； 如果不尝试其他模式，明确的预
        算拒绝就会停止。
        """
        retry_condition = (
            retry_if_exception_type(LLM_RETRY_EXCEPTIONS)
            | retry_if_exception(is_transient_http_error)
        ) & retry_if_exception(lambda e: not is_quota_exhaustion_error(e))
        return self.retry_decorator(
            num_retries=self.num_retries,
            retry_exceptions=retry_condition,
            retry_min_wait=self.retry_min_wait,
            retry_max_wait=self.retry_max_wait,
            retry_multiplier=self.retry_multiplier,
            retry_listener=self._retry_listener_fn,
        )

    def _timeout_error(self, detail: str, seconds: float) -> LiteLLMTimeout:
        return LiteLLMTimeout(
            message=f"LLM {detail} after {seconds:g} seconds",
            model=self.model,
            llm_provider=self._infer_litellm_provider() or "unknown",
        )

    def _async_hard_timeout_decorator(
        self,
    ) -> Callable[[Callable[..., Awaitable[_T]]], Callable[..., Awaitable[_T]]]:
        def decorate(
            function: Callable[..., Awaitable[_T]],
        ) -> Callable[..., Awaitable[_T]]:
            async def wrapped(*args: Any, **kwargs: Any) -> _T:
                if self.timeout is None:
                    return await function(*args, **kwargs)
                timeout_context = asyncio.timeout(self.timeout)
                try:
                    async with timeout_context:
                        return await function(*args, **kwargs)
                except TimeoutError as error:
                    if not timeout_context.expired():
                        raise
                    raise self._timeout_error("hard timeout", self.timeout) from error

            return wrapped

        return decorate

    async def _anext_with_idle_timeout(
        self, iterator: AsyncIterator[_T], timeout: float
    ) -> _T:
        """等待一个块，仅转换此空闲计时器自己的到期时间。

        使用 ``asyncio.timeout`` 代替 ``asyncio.wait_for``，以便
        由传输层本身引发的 ``TimeoutError``（例如提供者端读取超时）保留其原始身份，而
        不是被重新标记为空闲超时。
        """
        timeout_context = asyncio.timeout(timeout)
        try:
            async with timeout_context:
                return await anext(iterator)
        except TimeoutError as error:
            if not timeout_context.expired():
                raise
            raise self._timeout_error("stream idle timeout", timeout) from error

    async def _aiter_with_idle_timeout(
        self, stream: AsyncIterable[_T]
    ) -> AsyncIterable[_T]:
        timeout = self.stream_idle_timeout
        iterator = aiter(stream)
        while True:
            try:
                if timeout is None:
                    item = await anext(iterator)
                else:
                    item = await self._anext_with_idle_timeout(iterator, timeout)
            except StopAsyncIteration:
                return
            yield item

    def _build_completion_result(self, resp: ModelResponse) -> LLMResponse:
        """将原始：class:`ModelResponse` 转换为：class:`LLMResponse`。"""
        first_choice = resp["choices"][0]
        message = Message.from_llm_chat_message(first_choice["message"])
        return LLMResponse(
            message=message,
            metrics=self.metrics.get_snapshot(),
            raw_response=resp,
        )

    def _build_responses_result(self, resp: ResponsesAPIResponse) -> LLMResponse:
        """将原始：class:`ResponsesAPIResponse` 转换为：class:`LLMResponse`。"""
        message = Message.from_llm_responses_output(resp.output)
        return LLMResponse(
            message=message,
            metrics=self.metrics.get_snapshot(),
            raw_response=resp,
        )

    def _build_responses_call_kwargs(
        self,
        input_items: list[dict[str, Any]],
        instructions: str | None,
        resp_tools: list[Any] | None,
        final_kwargs: dict[str, Any],
        auth_values: tuple[str | None, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """为 litellm_responses / litellm_aresponses 构建共享 kwargs 字典。"""
        typed_input: ResponseInputParam | str = (
            cast(ResponseInputParam, input_items) if input_items else ""
        )
        provider_info = self._provider_info
        assert provider_info is not None
        api_key_value, subscription_headers = (
            auth_values if auth_values is not None else self._get_litellm_auth_values()
        )
        if subscription_headers:
            final_kwargs = {
                **final_kwargs,
                "extra_headers": {
                    **(final_kwargs.get("extra_headers") or {}),
                    **subscription_headers,
                },
            }
        return {
            **provider_info.as_litellm_call_kwargs(api_key=api_key_value),
            "input": typed_input,
            "instructions": instructions,
            "tools": resp_tools,
            "api_base": provider_info.api_base,
            "api_version": self.api_version,
            "timeout": self.timeout,
            "drop_params": self.drop_params,
            "seed": self.seed,
            **self._aws_kwargs(),
            **final_kwargs,
        }

    def _process_stream_event(
        self, event: ResponseStreamEvent, *, emit_deltas: bool = True
    ) -> tuple[object | None, ModelResponseStream | None]:
        """从响应流事件中提取输出项和增量块。

        Args:
            event: 单个响应流式传输事件。
            emit_deltas: 当 ``False`` 增量块从未构建时 — 跳过
                当没有流回调接收它时的分配。

        Returns:
            (output_item, delta_chunk) — 其中一个或两个都可以是 ``None``。
        """
        output_item: object | None = None
        delta_chunk: ModelResponseStream | None = None

        # 收集成品输出项目
        if (
            isinstance(event, OutputItemEvent)
            and event.type == ResponsesAPIStreamEvents.OUTPUT_ITEM_DONE
        ):
            output_item = event.item

        if emit_deltas and isinstance(
            event,
            (
                OutputTextDeltaEvent,
                RefusalDeltaEvent,
                ReasoningSummaryTextDeltaEvent,
            ),
        ):
            delta = event.delta
            if delta:
                # ModelResponseStream 为每个实例创建一个新的 id，更改后的块 id 读取为重
                # 试 (StreamContext._emit_delta)。
                #
                delta_chunk = ModelResponseStream(
                    id=event.item_id,
                    choices=[StreamingChoices(delta=Delta(content=delta))],
                )

        return output_item, delta_chunk

    def _finalize_stream_response(
        self,
        completed_response: ResponseCompletedEvent | None,
        collected_output_items: list[Any],
    ) -> ResponsesAPIResponse:
        """验证并修补来自响应流的完整响应。

        Raises:
            LLMNoResponseError: 如果流已完成但未完成
                响应或意外事件类型。
        """
        if completed_response is None:
            raise LLMNoResponseError(
                "Responses stream finished without a completed response"
            )
        if not isinstance(completed_response, ResponseCompletedEvent):
            raise LLMNoResponseError(
                f"Unexpected completed event: {type(completed_response)}"
            )

        completed_resp = completed_response.response
        # 使用从流中收集的项目修补空输出
        if not completed_resp.output and collected_output_items:
            completed_resp.output = collected_output_items

        assert self._telemetry is not None
        self._telemetry.on_response(
            completed_resp,
            provider_info=self._provider_info,
        )
        return completed_resp

    def _prepare_completion_params(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None,
        add_security_risk_prediction: bool,
        kwargs: dict[str, Any],
        call_context: LLMCallContext | None = None,
    ) -> tuple[
        list[dict[str, Any]],
        list[ChatCompletionToolParam],
        bool,
        dict[str, Any],
        dict[str, Any],
    ]:
        """:meth:`completion` 的共享设置。

        Returns:
            (formatted_messages, cc_tools, use_mock_tools, call_kwargs,
             telemetry_ctx)
        """
        formatted_messages = self.format_messages_for_llm(messages)
        return self._finalize_completion_params(
            formatted_messages,
            tools,
            add_security_risk_prediction,
            kwargs,
            call_context=call_context,
        )

    async def _aprepare_completion_params(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None,
        add_security_risk_prediction: bool,
        kwargs: dict[str, Any],
        call_context: LLMCallContext | None = None,
    ) -> tuple[
        list[dict[str, Any]],
        list[ChatCompletionToolParam],
        bool,
        dict[str, Any],
        dict[str, Any],
    ]:
        """异步：meth:`_prepare_completion_params` 的变体。

        使用：meth:`aformat_messages_for_llm`，因此（可能阻塞的）图像内联传递被卸载到
        工作线程线程，而不是在事件循环上运行。
        """
        formatted_messages = await self.aformat_messages_for_llm(messages)
        return self._finalize_completion_params(
            formatted_messages,
            tools,
            add_security_risk_prediction,
            kwargs,
            call_context=call_context,
        )

    def _finalize_completion_params(
        self,
        formatted_messages: list[dict[str, Any]],
        tools: Sequence[ToolDefinition] | None,
        add_security_risk_prediction: bool,
        kwargs: dict[str, Any],
        call_context: LLMCallContext | None = None,
    ) -> tuple[
        list[dict[str, Any]],
        list[ChatCompletionToolParam],
        bool,
        dict[str, Any],
        dict[str, Any],
    ]:
        """根据已格式化的消息最终确定聊天完成参数。

        :meth:`_prepare_completion_params` 和：meth:`_aprepare_completion_params` 的
        共享后格式
        化步骤：工具转换、模拟对象-工具提示词替换、kwargs 标准化和遥测上下文。
        """
        # 防御性副本——此方法会改变 kwargs (e.g. kwargs["tools"]) 并且调用者不应该观察这
        # 些副作用。
        #
        kwargs = dict(kwargs)

        # 2) 选择函数调用策略
        use_native_fc = self.native_tool_calling
        original_fncall_msgs = copy.deepcopy(formatted_messages)

        # 在此将工具对象转换为 ChatCompletionToolParam 一次
        cc_tools: list[ChatCompletionToolParam] = []
        if tools:
            cc_tools = [
                t.to_openai_tool(
                    add_security_risk_prediction=add_security_risk_prediction,
                )
                for t in tools
            ]

        use_mock_tools = self.should_mock_tool_calls(cc_tools)
        if use_mock_tools:
            logger.debug(
                "LLM.completion: mocking function-calling via prompt "
                f"for model {self.model}"
            )
            formatted_messages, kwargs = self.pre_request_prompt_mock(
                formatted_messages,
                cc_tools or [],
                kwargs,
                include_security_params=add_security_risk_prediction,
            )

        # 3) 规范化提供者参数
        # 仅当本机 FC 处于活动状态时才传递工具
        kwargs["tools"] = cc_tools if (bool(cc_tools) and use_native_fc) else None
        has_tools_flag = bool(cc_tools) and use_native_fc
        # 行为保留：委托给 select_chat_options
        call_kwargs = select_chat_options(
            self, kwargs, has_tools=has_tools_flag, call_context=call_context
        )

        # 3a) 联合投入/产出预算限制 (e.g. 基岩-Anthropic)
        call_kwargs = self._clamp_max_tokens_for_joint_budget(
            call_kwargs,
            formatted_messages,
            [] if use_mock_tools else cc_tools,
        )

        # 4) 遥测请求上下文（始终包含指标 context_window）
        # 始终传递 context_window，以便即使禁用日志记录也会跟踪指标。
        #
        telemetry = self.telemetry
        telemetry_ctx: dict[str, Any] = {
            "context_window": self.effective_max_input_tokens or 0
        }
        if telemetry.log_enabled:
            telemetry_ctx.update(
                {
                    "messages": formatted_messages[:],  # 已经很简单的小字典
                    "tools": tools,
                    "kwargs": {k: v for k, v in call_kwargs.items()},
                }
            )
            if tools and not use_native_fc:
                telemetry_ctx["raw_messages"] = original_fncall_msgs

        return (
            formatted_messages,
            cc_tools,
            use_mock_tools,
            call_kwargs,
            telemetry_ctx,
        )

    def _prepare_responses_params(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None,
        include: list[str] | None,
        store: bool | None,
        add_security_risk_prediction: bool,
        kwargs: dict[str, Any],
        call_context: LLMCallContext | None = None,
    ) -> tuple[
        str | None,
        list[dict[str, Any]],
        list[Any] | None,
        dict[str, Any],
        dict[str, Any],
    ]:
        """:meth:`responses` 的共享设置。

        Returns:
            （指令，input_items，resp_tools，call_kwargs，
             telemetry_ctx)
        """
        instructions, input_items = self.format_messages_for_responses(messages)
        return self._finalize_responses_params(
            instructions,
            input_items,
            tools,
            include,
            store,
            add_security_risk_prediction,
            kwargs,
            call_context=call_context,
        )

    async def _aprepare_responses_params(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None,
        include: list[str] | None,
        store: bool | None,
        add_security_risk_prediction: bool,
        kwargs: dict[str, Any],
        call_context: LLMCallContext | None = None,
    ) -> tuple[
        str | None,
        list[dict[str, Any]],
        list[Any] | None,
        dict[str, Any],
        dict[str, Any],
    ]:
        """异步：meth:`_prepare_responses_params` 的变体。

        使用：meth:`aformat_messages_for_responses` 因此图像内联
        pass runs off the event loop.
        """
        instructions, input_items = await self.aformat_messages_for_responses(messages)
        return self._finalize_responses_params(
            instructions,
            input_items,
            tools,
            include,
            store,
            add_security_risk_prediction,
            kwargs,
            call_context=call_context,
        )

    def _finalize_responses_params(
        self,
        instructions: str | None,
        input_items: list[dict[str, Any]],
        tools: Sequence[ToolDefinition] | None,
        include: list[str] | None,
        store: bool | None,
        add_security_risk_prediction: bool,
        kwargs: dict[str, Any],
        call_context: LLMCallContext | None = None,
    ) -> tuple[
        str | None,
        list[dict[str, Any]],
        list[Any] | None,
        dict[str, Any],
        dict[str, Any],
    ]:
        """根据已格式化的输入完成响应参数。

        共享：meth:`_prepare_responses_params` 和：meth:`_aprepare_responses_params`
        的后格式化步
        骤。
        """
        # 防御性副本 — select_responses_options 可能会变异 kwargs。
        kwargs = dict(kwargs)

        # 将工具对象转换为响应 ToolParam（响应路径始终支持功能工具）
        #
        resp_tools = (
            [
                t.to_responses_tool(
                    add_security_risk_prediction=add_security_risk_prediction,
                )
                for t in tools
            ]
            if tools
            else None
        )

        # 一致地标准化/覆盖响应 kwargs
        call_kwargs = select_responses_options(
            self, kwargs, include=include, store=store, call_context=call_context
        )

        # 请求上下文的遥测 (始终包括 context_window 的指标)。始终通过 context_window，即
        # 使日志未启用，也能追踪指标。
        #
        telemetry = self.telemetry
        telemetry_ctx: dict[str, Any] = {
            "context_window": self.effective_max_input_tokens or 0
        }
        if telemetry.log_enabled:
            telemetry_ctx.update(
                {
                    "llm_path": "responses",
                    "instructions": instructions,
                    "input": input_items[:],
                    "tools": tools,
                    "kwargs": {k: v for k, v in call_kwargs.items()},
                }
            )

        return instructions, input_items, resp_tools, call_kwargs, telemetry_ctx

    def _validate_chat_response(
        self,
        resp: ModelResponse,
        *,
        use_mock_tools: bool,
        formatted_messages: list[dict[str, Any]],
        cc_tools: list[ChatCompletionToolParam],
        add_security_risk_prediction: bool,
    ) -> ModelResponse:
        """对重试边界内的聊天完成响应进行后处理。

        原始（pre-模拟对象）响应由内部消耗
        ``Telemetry.on_response`` 并且不会返回给调用者。

        Raises:
            LLMNoResponseError: 如果回应没有选择
                （双子座有时会返回空选择； 在重试边界内提升可确保重试）。
        """
        raw_resp: ModelResponse | None = None
        if use_mock_tools:
            raw_resp = copy.deepcopy(resp)
            resp = self.post_response_prompt_mock(
                resp,
                nonfncall_msgs=formatted_messages,
                tools=cc_tools,
                include_security_params=add_security_risk_prediction,
            )

        # 6) 遥测
        assert self._telemetry is not None
        self._telemetry.on_response(
            resp,
            raw_resp=raw_resp,
            provider_info=self._provider_info,
        )

        # 确保至少有一项选择。 双子座有时会返回空的选择； 在这里，我们在这里
        # LLMNoResponseError 以重试的边界，因此它被重试。
        #
        if not resp.get("choices") or len(resp["choices"]) < 1:
            raise LLMNoResponseError(
                "Response choices is less than 1. Response: " + str(resp)
            )
        return resp

    def generate(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        include: list[str] | None = None,
        store: bool | None = None,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs,
    ) -> LLMResponse:
        """使用配置的 API 模式生成响应。"""
        if self.uses_responses_api():
            return self.responses(
                messages=messages,
                tools=tools,
                include=include,
                store=store,
                add_security_risk_prediction=add_security_risk_prediction,
                on_token=on_token,
                call_context=call_context,
                **kwargs,
            )
        return self.completion(
            messages=messages,
            tools=tools,
            add_security_risk_prediction=add_security_risk_prediction,
            on_token=on_token,
            call_context=call_context,
            **kwargs,
        )

    async def agenerate(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        include: list[str] | None = None,
        store: bool | None = None,
        add_security_risk_prediction: bool = False,
        on_token: AnyTokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs,
    ) -> LLMResponse:
        """异步：meth:`generate` 的变体。"""
        if self.uses_responses_api():
            return await self.aresponses(
                messages=messages,
                tools=tools,
                include=include,
                store=store,
                add_security_risk_prediction=add_security_risk_prediction,
                on_token=on_token,
                call_context=call_context,
                **kwargs,
            )
        return await self.acompletion(
            messages=messages,
            tools=tools,
            add_security_risk_prediction=add_security_risk_prediction,
            on_token=on_token,
            call_context=call_context,
            **kwargs,
        )

    # =========================================================================
    # 聊天完成 API
    # =========================================================================

    def completion(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs,
    ) -> LLMResponse:
        """从语言模型生成补全。

        这是通过 Completion API 从模型获取响应的方法。 它处理消息格式化、工具调用和响
        应处理。

        Args:
            messages: 对话消息列表。
            tools: 模型可用的可选工具列表。
            add_security_risk_prediction: 将 security_risk 字段添加到工具模式。
            on_token: 流式传输 token 可选回调。
            **kwargs: 附加参数传递给 LLM API。

        Returns:
            LLMResponse 包含模型的响应和元数据。

        Note:
            摘要字段始终添加到工具模式中，以提高智能体操作的透明度和可解释性。
        """
        # 解析提供者感知的运行时元数据 (e.g. OpenRouter路线限制）在第一次完成之前所以
        # ``effective_max_input_tokens``/
        # ``effective_max_output_tokens`` 反映在此调用中稍后运行的任何上下文管理的实际运
        # 行时路由。 结果被缓存（1h TTL）并在失败时进行负缓存，并且对于没有运行时元数据
        # 的提供者来说，探测是无操作的。
        #
        self.resolve_runtime_metadata()

        _caller_kwargs = kwargs.copy()
        enable_streaming = bool(kwargs.get("stream", False)) or self.stream
        if enable_streaming and on_token is None:
            # 当在没有连接回调的情况下请求流式传输时，优雅地降级为非流式传输，而不是使运
            # 行崩溃。 参见#4014。
            #
            logger.debug(
                "Streaming requested without an on_token callback; "
                "falling back to a non-streaming completion."
            )
            enable_streaming = False
            kwargs.pop("stream", None)
        elif enable_streaming:
            kwargs["stream"] = True

        (
            formatted_messages,
            cc_tools,
            use_mock_tools,
            call_kwargs,
            telemetry_ctx,
        ) = self._prepare_completion_params(
            messages,
            tools,
            add_security_risk_prediction,
            kwargs,
            call_context=call_context,
        )

        @self._make_retry_decorator()
        def _one_attempt(**retry_kwargs: Any) -> ModelResponse:
            assert self._telemetry is not None
            self._telemetry.on_request(telemetry_ctx=telemetry_ctx)
            final_kwargs = {**call_kwargs, **retry_kwargs}
            resp = self._transport_call(
                messages=formatted_messages,
                **final_kwargs,
                enable_streaming=enable_streaming,
                on_token=on_token,
            )
            resp = self._validate_chat_response(
                resp,
                use_mock_tools=use_mock_tools,
                formatted_messages=formatted_messages,
                cc_tools=cc_tools,
                add_security_risk_prediction=add_security_risk_prediction,
            )
            return resp

        try:
            return self._build_completion_result(_one_attempt())
        except Exception as e:
            # 如果提示词缓存内容小于提供商的最小 token 阈值 (e.g., Vertex AI 需要 ≥4096
            # token)，则重试不提示词缓存标记。
            #
            if is_prompt_cache_too_small(e) and self.is_caching_prompt_active():
                logger.warning(
                    "Prompt cache content too small for provider minimum, "
                    "retrying without prompt caching"
                )
                no_cache_llm = self.model_copy(update={"caching_prompt": False})
                return no_cache_llm.completion(
                    messages,
                    tools,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    **_caller_kwargs,
                )
            # 如果凭据被拒绝 (401) 并且刷新挂钩可以提供新密钥，则重新解析它并重试调用一
            # 次。
            #
            refreshed_key = self._resolve_refreshed_api_key(e)
            if refreshed_key is not None:
                logger.warning(
                    "Authentication error; refreshing API key and retrying once."
                )
                return self._auth_refreshed_llm(refreshed_key).completion(
                    messages,
                    tools,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    call_context=call_context,
                    **_caller_kwargs,
                )
            return self._handle_error(
                e,
                lambda fb: fb.completion(
                    messages,
                    tools,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    call_context=call_context,
                    **_caller_kwargs,
                ),
            )

    # =========================================================================
    # 异步聊天完成 API
    # =========================================================================
    async def acompletion(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        add_security_risk_prediction: bool = False,
        on_token: AnyTokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs,
    ) -> LLMResponse:
        """异步：meth:`completion` 的变体。

        在底层使用 ``litellm.acompletion``，释放事件循环
        while waiting for the LLM provider response.
        """
        # 解析提供者感知的运行时元数据 (e.g. OpenRouter 路由限制）在智能体-服务器异步路
        # 径上第一次完成之前
        # ``effective_max_input_tokens``反映实际运行路线。 结果被缓存（1小时 TTL)，失败
        # 时被负缓存，对于没有运行时元数据的提供者，探针是无操作的，因此重复调用是便宜的
        # 。
        #
        await self.aresolve_runtime_metadata()

        _caller_kwargs = kwargs.copy()
        enable_streaming = bool(kwargs.get("stream", False)) or self.stream
        if enable_streaming and on_token is None:
            # 当在没有连接回调的情况下请求流式传输时，优雅地降级为非流式传输，而不是使运
            # 行崩溃。 参见#4014。
            #
            logger.debug(
                "Streaming requested without an on_token callback; "
                "falling back to a non-streaming completion."
            )
            enable_streaming = False
            kwargs.pop("stream", None)
        elif enable_streaming:
            kwargs["stream"] = True

        (
            formatted_messages,
            cc_tools,
            use_mock_tools,
            call_kwargs,
            telemetry_ctx,
        ) = await self._aprepare_completion_params(
            messages,
            tools,
            add_security_risk_prediction,
            kwargs,
            call_context=call_context,
        )

        @self._make_retry_decorator()
        @self._async_hard_timeout_decorator()
        async def _one_attempt(**retry_kwargs: Any) -> ModelResponse:
            assert self._telemetry is not None
            self._telemetry.on_request(telemetry_ctx=telemetry_ctx)
            final_kwargs = {**call_kwargs, **retry_kwargs}
            resp = await self._atransport_call(
                messages=formatted_messages,
                **final_kwargs,
                enable_streaming=enable_streaming,
                on_token=on_token,
            )
            resp = self._validate_chat_response(
                resp,
                use_mock_tools=use_mock_tools,
                formatted_messages=formatted_messages,
                cc_tools=cc_tools,
                add_security_risk_prediction=add_security_risk_prediction,
            )
            return resp

        try:
            return self._build_completion_result(await _one_attempt())
        except Exception as e:
            # 如果提示词缓存内容小于提供商的最小 token 阈值 (e.g., Vertex AI 需要 ≥4096
            # token)，则重试不提示词缓存标记。
            #
            if is_prompt_cache_too_small(e) and self.is_caching_prompt_active():
                logger.warning(
                    "Prompt cache content too small for provider minimum, "
                    "retrying without prompt caching"
                )
                no_cache_llm = self.model_copy(update={"caching_prompt": False})
                return await no_cache_llm.acompletion(
                    messages,
                    tools,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    **_caller_kwargs,
                )
            # 如果凭据被拒绝 (401) 并且刷新挂钩可以提供新密钥，则重新解析它（脱离事件循
            # 环）和重试一次。
            #
            loop = asyncio.get_running_loop()
            refreshed_key = await loop.run_in_executor(
                None, self._resolve_refreshed_api_key, e
            )
            if refreshed_key is not None:
                logger.warning(
                    "Authentication error; refreshing API key and retrying once."
                )
                return await self._auth_refreshed_llm(refreshed_key).acompletion(
                    messages,
                    tools,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    call_context=call_context,
                    **_caller_kwargs,
                )
            # 回退方案是同步； 由于回退方案 LLM 的同步路径接受 TokenCallbackType，因此强
            # 制转换 token 回调。
            #
            _fb_token = cast("TokenCallbackType | None", on_token)
            return await self._ahandle_error(
                e,
                lambda fb: fb.completion(
                    messages,
                    tools,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=_fb_token,
                    call_context=call_context,
                    **_caller_kwargs,
                ),
            )

    # =========================================================================
    # 回复 API (v1)
    # =========================================================================
    def responses(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        include: list[str] | None = None,
        store: bool | None = None,
        add_security_risk_prediction: bool = False,
        on_token: TokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs,
    ) -> LLMResponse:
        """通过 LiteLLM 使用 OpenAI 响应 API 的替代调用路径。

        [] -> (指令，输入[]) 并返回LLMResponse。

        Args:
            messages: 对话消息列表
            tools: 模型可用的可选工具列表
            include: 要包含在响应中的可选字段列表
            store: 是否存储对话内容
            add_security_risk_prediction: 将 security_risk 字段添加到工具模式
            on_token: 流式传输增量的可选回调
            **kwargs: 传递给 API 的附加参数

        Note:
            摘要字段始终添加到工具模式中，以提高智能体操作的透明度和可解释性。
        """
        # 在第一个请求之前解析提供者感知的运行时元数据
        # ``effective_max_input_tokens``/``effective_max_output_tokens``反映后续上下文管
        # 理时的实际运行路线。 缓存（1h TTL）/负缓存； 对于没有运行时元数据的提供者来说
        # ，无操作。
        #
        self.resolve_runtime_metadata()

        _caller_kwargs = kwargs.copy()
        user_enable_streaming = bool(kwargs.get("stream", False)) or self.stream
        if user_enable_streaming and on_token is None and not self.requires_streaming:
            # 当在没有连接回调的情况下请求流式传输时，优雅地降级为非流式传输，而不是使运
            # 行崩溃。 需要流式传输的提供者可以豁免 — 他们在内部耗尽流而无需 on_token 回
            # 调。 请参阅requires_streaming和#4014。
            #
            logger.debug(
                "Streaming requested without an on_token callback; "
                "falling back to a non-streaming responses call."
            )
            user_enable_streaming = False
            kwargs.pop("stream", None)
        elif user_enable_streaming:
            kwargs["stream"] = True

        (
            instructions,
            input_items,
            resp_tools,
            call_kwargs,
            telemetry_ctx,
        ) = self._prepare_responses_params(
            messages,
            tools,
            include,
            store,
            add_security_risk_prediction,
            kwargs,
            call_context=call_context,
        )

        @self._make_retry_decorator()
        def _one_attempt(**retry_kwargs: Any) -> ResponsesAPIResponse:
            assert self._telemetry is not None
            self._telemetry.on_request(telemetry_ctx=telemetry_ctx)
            final_kwargs = {**call_kwargs, **retry_kwargs}
            litellm_kwargs = self._build_responses_call_kwargs(
                input_items, instructions, resp_tools, final_kwargs
            )
            ret = litellm_responses(**litellm_kwargs)

            if isinstance(ret, ResponsesAPIResponse):
                if user_enable_streaming:
                    logger.warning(
                        "Responses streaming was requested, but the "
                        "provider returned a non-streaming response; "
                        "no on_token deltas will be emitted."
                    )
                self._telemetry.on_response(
                    ret,
                    provider_info=self._provider_info,
                )
                return ret

            # 当stream=True时，LiteLLM返回一个流式传输迭代器而不是单个
            # ResponsesAPIResponse。 第三方包装器可以用另一个可迭代器替换LiteLLM的具体迭
            # 代器，因此按协议排出。
            #
            if final_kwargs.get("stream", False):
                stream_callback = on_token if user_enable_streaming else None
                # 收集流式传输事件的输出项目。 一些端点（e.g.，Codex 订阅）将输出项作为
                # 单独的事件发送，但最终的 response.completed 事件的输出=[]。 我们在这里
                # 累积它们，并根据需要修补完整的响应。
                #
                collected_output_items: list[object] = []
                completed_response = get_completed_response(ret)
                if not isinstance(ret, Iterable):
                    raise TypeError(f"Expected a response stream, got {type(ret)}")
                for event in response_events(ret):
                    if isinstance(event, ResponseCompletedEvent):
                        completed_response = event
                    output_item, delta_chunk = self._process_stream_event(
                        event, emit_deltas=stream_callback is not None
                    )
                    if output_item is not None:
                        collected_output_items.append(output_item)
                    if stream_callback is not None and delta_chunk is not None:
                        stream_callback(delta_chunk)

                completed_response = get_completed_response(ret, completed_response)
                return self._finalize_stream_response(
                    completed_response, collected_output_items
                )

            raise AssertionError(f"Expected ResponsesAPIResponse, got {type(ret)}")

        try:
            return self._build_responses_result(_one_attempt())
        except Exception as e:
            # 如果提示词缓存内容小于提供商的最小 token 阈值 (e.g., Vertex AI 需要 ≥4096
            # token)，则重试不提示词缓存标记。
            #
            if is_prompt_cache_too_small(e) and self.is_caching_prompt_active():
                logger.warning(
                    "Prompt cache content too small for provider minimum, "
                    "retrying without prompt caching"
                )
                no_cache_llm = self.model_copy(update={"caching_prompt": False})
                return no_cache_llm.responses(
                    messages,
                    tools,
                    include,
                    store,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    **_caller_kwargs,
                )
            # 如果凭据被拒绝 (401) 并且刷新挂钩可以提供新密钥，则重新解析它并重试调用一
            # 次。
            #
            refreshed_key = self._resolve_refreshed_api_key(e)
            if refreshed_key is not None:
                logger.warning(
                    "Authentication error; refreshing API key and retrying once."
                )
                return self._auth_refreshed_llm(refreshed_key).responses(
                    messages,
                    tools,
                    include,
                    store,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    call_context=call_context,
                    **_caller_kwargs,
                )
            return self._handle_error(
                e,
                lambda fb: fb.responses(
                    messages,
                    tools,
                    include,
                    store,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    call_context=call_context,
                    **_caller_kwargs,
                ),
            )

    # =========================================================================
    # 异步回应 API
    # =========================================================================
    async def aresponses(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        include: list[str] | None = None,
        store: bool | None = None,
        add_security_risk_prediction: bool = False,
        on_token: AnyTokenCallbackType | None = None,
        call_context: LLMCallContext | None = None,
        **kwargs,
    ) -> LLMResponse:
        """异步：meth:`responses` 的变体。

        在底层使用 ``litellm.aresponses``，释放事件循环
        while waiting for the LLM provider response.
        """
        # 请参阅：meth：`acompletion`：在第一个请求之前解析提供者感知的运行时元数据，以
        # 便上下文管理读取运行时（而不是模型级）限制。 进程内没有阻塞网络 I/O。
        #
        await self.aresolve_runtime_metadata()

        _caller_kwargs = kwargs.copy()
        user_enable_streaming = bool(kwargs.get("stream", False)) or self.stream
        if user_enable_streaming and on_token is None and not self.requires_streaming:
            # 当在没有连接回调的情况下请求流式传输时，优雅地降级为非流式传输，而不是使运
            # 行崩溃。 需要流式传输的提供者可以豁免 — 他们在内部耗尽流而无需 on_token 回
            # 调。 请参阅requires_streaming和#4014。
            #
            logger.debug(
                "Streaming requested without an on_token callback; "
                "falling back to a non-streaming responses call."
            )
            user_enable_streaming = False
            kwargs.pop("stream", None)
        elif user_enable_streaming:
            kwargs["stream"] = True

        (
            instructions,
            input_items,
            resp_tools,
            call_kwargs,
            telemetry_ctx,
        ) = await self._aprepare_responses_params(
            messages,
            tools,
            include,
            store,
            add_security_risk_prediction,
            kwargs,
            call_context=call_context,
        )

        @self._make_retry_decorator()
        @self._async_hard_timeout_decorator()
        async def _one_attempt(
            **retry_kwargs: Any,
        ) -> ResponsesAPIResponse:
            assert self._telemetry is not None
            self._telemetry.on_request(telemetry_ctx=telemetry_ctx)
            final_kwargs = {**call_kwargs, **retry_kwargs}
            auth_values = await self._aget_litellm_auth_values()
            litellm_kwargs = self._build_responses_call_kwargs(
                input_items,
                instructions,
                resp_tools,
                final_kwargs,
                auth_values=auth_values,
            )
            ret = await litellm_aresponses(**litellm_kwargs)

            if isinstance(ret, ResponsesAPIResponse):
                if user_enable_streaming:
                    logger.warning(
                        "Responses streaming was requested, but the "
                        "provider returned a non-streaming response; "
                        "no on_token deltas will be emitted."
                    )
                self._telemetry.on_response(
                    ret,
                    provider_info=self._provider_info,
                )
                return ret

            # 当stream=True时，LiteLLM返回一个流式传输迭代器而不是单个
            # ResponsesAPIResponse。 第三方包装器可以用另一个同步或异步可迭代器替换
            # LiteLLM 的具体迭代器，因此按协议排出。
            #
            if final_kwargs.get("stream", False):
                stream_cb = on_token if user_enable_streaming else None
                # 收集流式传输事件的输出项目。 一些端点（e.g.，Codex 订阅）将输出项作为
                # 单独的事件发送，但最终的 response.completed 事件的输出=[]。 我们在这里
                # 累积它们，并根据需要修补完整的响应。
                #
                collected_output_items: list[object] = []
                completed_response = get_completed_response(ret)
                if isinstance(ret, AsyncIterable):
                    async for event in async_response_events(
                        self._aiter_with_idle_timeout(ret)
                    ):
                        if isinstance(event, ResponseCompletedEvent):
                            completed_response = event
                        output_item, delta_chunk = self._process_stream_event(
                            event, emit_deltas=stream_cb is not None
                        )
                        if output_item is not None:
                            collected_output_items.append(output_item)
                        if stream_cb is not None and delta_chunk is not None:
                            await _invoke_token_callback(stream_cb, delta_chunk)
                else:
                    if not isinstance(ret, Iterable):
                        raise TypeError(f"Expected a response stream, got {type(ret)}")
                    loop = asyncio.get_running_loop()
                    events = await loop.run_in_executor(
                        None, list, response_events(ret)
                    )
                    for event in events:
                        if isinstance(event, ResponseCompletedEvent):
                            completed_response = event
                        output_item, delta_chunk = self._process_stream_event(
                            event, emit_deltas=stream_cb is not None
                        )
                        if output_item is not None:
                            collected_output_items.append(output_item)
                        if stream_cb is not None and delta_chunk is not None:
                            await _invoke_token_callback(stream_cb, delta_chunk)

                completed_response = get_completed_response(ret, completed_response)
                return self._finalize_stream_response(
                    completed_response, collected_output_items
                )

            raise AssertionError(f"Expected ResponsesAPIResponse, got {type(ret)}")

        try:
            return self._build_responses_result(await _one_attempt())
        except Exception as e:
            # 如果提示词缓存内容小于提供商的最小 token 阈值 (e.g., Vertex AI 需要 ≥4096
            # token)，则重试不提示词缓存标记。
            #
            if is_prompt_cache_too_small(e) and self.is_caching_prompt_active():
                logger.warning(
                    "Prompt cache content too small for provider minimum, "
                    "retrying without prompt caching"
                )
                no_cache_llm = self.model_copy(update={"caching_prompt": False})
                return await no_cache_llm.aresponses(
                    messages,
                    tools,
                    include,
                    store,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    **_caller_kwargs,
                )
            # 如果凭据被拒绝 (401) 并且刷新挂钩可以提供新密钥，则重新解析它（脱离事件循
            # 环）和重试一次。
            #
            loop = asyncio.get_running_loop()
            refreshed_key = await loop.run_in_executor(
                None, self._resolve_refreshed_api_key, e
            )
            if refreshed_key is not None:
                logger.warning(
                    "Authentication error; refreshing API key and retrying once."
                )
                return await self._auth_refreshed_llm(refreshed_key).aresponses(
                    messages,
                    tools,
                    include,
                    store,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=on_token,
                    call_context=call_context,
                    **_caller_kwargs,
                )
            _fb_token = cast("TokenCallbackType | None", on_token)
            return await self._ahandle_error(
                e,
                lambda fb: fb.responses(
                    messages,
                    tools,
                    include,
                    store,
                    add_security_risk_prediction=add_security_risk_prediction,
                    on_token=_fb_token,
                    call_context=call_context,
                    **_caller_kwargs,
                ),
            )

    # =========================================================================
    # 传输层 + 帮助者
    # =========================================================================

    def _litellm_call_kwargs(self) -> LiteLLMCallKwargs:
        return litellm_call_kwargs(self.model, self.base_url)

    def _infer_litellm_provider(self) -> str | None:
        provider_info = self._provider_info
        if provider_info is None:
            return None
        return provider_info.name

    def _infer_model_info_provider(self) -> str | None:
        if self._model_info is not None:
            provider = self._model_info.get("litellm_provider")
            if isinstance(provider, str) and provider:
                return provider

        return self._infer_litellm_provider()

    def _get_api_key_value(self) -> str | None:
        if self.api_key is None:
            return None
        assert isinstance(self.api_key, SecretStr)
        return self.api_key.get_secret_value()

    def _subscription_headers_from_credentials(
        self, auth: Any, credentials: Any
    ) -> dict[str, str]:
        account_id = auth.extract_chatgpt_account_id(credentials)
        if not account_id:
            return {}
        return {"chatgpt-account-id": account_id}

    def _subscription_api_key_from_credentials(self, credentials: Any) -> str:
        return credentials.access_token

    def _normalize_litellm_api_key_value(self, api_key_value: str | None) -> str | None:
        provider_info = self._provider_info
        if provider_info is None:
            return api_key_value
        return provider_info.api_key_for_litellm(api_key_value)

    def _get_litellm_auth_values(self) -> tuple[str | None, dict[str, str]]:
        api_key_value: str | None = None
        extra_headers: dict[str, str] = {}
        if self.is_subscription:
            from openhands.sdk.llm.auth.openai import OpenAISubscriptionAuth

            auth = OpenAISubscriptionAuth(
                credential_store=self._subscription_credential_store
            )
            credentials = self._subscription_credentials
            if credentials is None or credentials.is_expired():
                credentials = auth.refresh_if_needed_sync()
            if credentials is None:
                credentials = self._subscription_credentials
            if credentials is None:
                raise ValueError("OpenAI subscription login is required")
            api_key_value = self._subscription_api_key_from_credentials(credentials)
            extra_headers = self._subscription_headers_from_credentials(
                auth, credentials
            )
        elif self.api_key:
            api_key_value = self._get_api_key_value()

        return self._normalize_litellm_api_key_value(api_key_value), extra_headers

    def _get_litellm_api_key_value(self) -> str | None:
        api_key_value, _ = self._get_litellm_auth_values()
        return api_key_value

    async def _aget_litellm_auth_values(self) -> tuple[str | None, dict[str, str]]:
        if not self.is_subscription:
            return self._get_litellm_auth_values()

        from openhands.sdk.llm.auth.openai import OpenAISubscriptionAuth

        auth = OpenAISubscriptionAuth(
            credential_store=self._subscription_credential_store
        )
        credentials = await auth.refresh_if_needed()
        if credentials is None:
            credentials = self._subscription_credentials
        if credentials is None:
            raise ValueError("OpenAI subscription login is required")
        api_key_value = self._normalize_litellm_api_key_value(
            self._subscription_api_key_from_credentials(credentials)
        )
        return api_key_value, self._subscription_headers_from_credentials(
            auth, credentials
        )

    async def _aget_litellm_api_key_value(self) -> str | None:
        api_key_value, _ = await self._aget_litellm_auth_values()
        return api_key_value

    def _prepare_transport_kwargs(
        self,
        *,
        messages: list[dict[str, Any]],
        enable_streaming: bool,
        auth_values: tuple[str | None, dict[str, str]] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """构建 LiteLLM (a) 完成调用的关键字参数。"""
        provider_info = self._provider_info
        assert provider_info is not None
        assert_vertex_sdk_available(provider_info.name)

        # 当流式传输时，请求最终块中的使用情况，以便 LiteLLM 的流式传输处理程序不会默默
        # 地丢弃详细的 token 故障（prompt_tokens_details 和 cached_tokens 等）。
        #
        if enable_streaming:
            kwargs.setdefault("stream_options", {"include_usage": True})
        api_key_value, subscription_headers = (
            auth_values if auth_values is not None else self._get_litellm_auth_values()
        )
        if subscription_headers:
            kwargs["extra_headers"] = {
                **(kwargs.get("extra_headers") or {}),
                **subscription_headers,
            }
        return {
            **provider_info.as_litellm_call_kwargs(api_key=api_key_value),
            "api_base": provider_info.api_base,
            "api_version": self.api_version,
            "timeout": self.timeout,
            "drop_params": self.drop_params,
            "seed": self.seed,
            "messages": messages,
            # SDK 拥有重试，因此预算拒绝会立即到达其分类器。
            "max_retries": 0,
            **self._aws_kwargs(),
            **kwargs,
        }

    def _transport_call(
        self,
        *,
        messages: list[dict[str, Any]],
        enable_streaming: bool = False,
        on_token: TokenCallbackType | None = None,
        **kwargs,
    ) -> ModelResponse:
        ret = litellm_completion(
            **self._prepare_transport_kwargs(
                messages=messages, enable_streaming=enable_streaming, **kwargs
            )
        )
        if enable_streaming and on_token is not None:
            chunks: list[ModelResponseStream] = []
            stream = cast(Iterable[ModelResponseStream], ret)
            for chunk in stream:
                on_token(chunk)
                chunks.append(chunk)
            ret = litellm.stream_chunk_builder(chunks, messages=messages)

        assert isinstance(ret, ModelResponse), (
            f"Expected ModelResponse, got {type(ret)}"
        )
        return ret

    async def _atransport_call(
        self,
        *,
        messages: list[dict[str, Any]],
        enable_streaming: bool = False,
        on_token: AnyTokenCallbackType | None = None,
        **kwargs,
    ) -> ModelResponse:
        """异步：meth:`_transport_call` 的变体。"""
        auth_values = await self._aget_litellm_auth_values()
        ret = await litellm_acompletion(
            **self._prepare_transport_kwargs(
                messages=messages,
                enable_streaming=enable_streaming,
                auth_values=auth_values,
                **kwargs,
            )
        )
        if enable_streaming and on_token is not None:
            chunks: list[ModelResponseStream] = []
            # 一些 LiteLLM 包装器（lmnr 0.7.47 的检测器）从 ``litellm_acompletion`` 交还
            # 一个普通的同步生成器
            #
            if isinstance(ret, AsyncIterable):
                stream = cast(AsyncIterable[ModelResponseStream], ret)
                async for chunk in self._aiter_with_idle_timeout(stream):
                    await _invoke_token_callback(on_token, chunk)
                    chunks.append(chunk)
            else:
                loop = asyncio.get_running_loop()
                synced_chunks: list[ModelResponseStream] = await loop.run_in_executor(
                    None, list, cast(Iterable[ModelResponseStream], ret)
                )
                for chunk in synced_chunks:
                    await _invoke_token_callback(on_token, chunk)
                    chunks.append(chunk)
            ret = litellm.stream_chunk_builder(chunks, messages=messages)

        assert isinstance(ret, ModelResponse), (
            f"Expected ModelResponse, got {type(ret)}"
        )
        return ret

    # =========================================================================
    # 功能、格式和信息
    # =========================================================================
    def _model_name_for_capabilities(self) -> str:
        """返回功能查找的规范名称（e.g.，视觉支持）。"""
        return self.model_canonical_name or self.model

    def _model_features(self) -> ModelFeatures:
        """为每个请求路径一致地解析功能。"""
        return get_features(
            self._model_name_for_capabilities(),
            model_info=self._model_info,
            overrides=self.capability_overrides,
        )

    def _provider_has_joint_token_budget(self) -> bool:
        """提供者是否强制输入 + max_tokens <= context_window。

        一些提供程序（特别是 Anthropic 模型的 AWS Bedrock）在输入和请求的输出之间共享
        单个 token 窗口。 直接提供者（Anthropic
        、OpenAI等）具有独立的输入/输出窗口。
        """
        provider = self._infer_model_info_provider() or ""
        return any(provider.startswith(p) for p in _JOINT_BUDGET_PROVIDER_PREFIXES)

    def _clamp_max_tokens_for_joint_budget(
        self,
        call_kwargs: dict[str, Any],
        formatted_messages: list[dict[str, Any]],
        cc_tools: list[ChatCompletionToolParam],
    ) -> dict[str, Any]:
        """限制联合窗口提供商的每个请求的输出预算。

        对于像 Bedrock-Anthropic 这样的提供者，``input_tokens + max_tokens`` 不得超过
        上下文窗口。
        ``max_tokens`` 的默认注入值是模型的完整 ``max_output_tokens`` (e.g. 64k 对于
        Sonnet 4.5)，对于任
        何输入长度超过大约 ``context_window - max_output_tokens`` 的情况，都会因为“请
        求的模型输入太长”而失败——即使实际响
        应会很小。 夹住实际剩余的净空，并设置安全裕度和下限，这样我们就不会发送``0``
        。

        对于非联合提供商，参数是独立的预算，我们不影响 kwargs。
        """
        if not self._provider_has_joint_token_budget():
            return call_kwargs

        context_window = self.effective_max_input_tokens
        if not context_window:
            return call_kwargs

        # 这两个键可能会出现，具体取决于路由（Azure /扩展思维使用``max_tokens``； 其他一
        # 切都使用``max_completion_tokens``）。
        #
        budget_key = next(
            (k for k in ("max_tokens", "max_completion_tokens") if k in call_kwargs),
            None,
        )
        if budget_key is None:
            return call_kwargs
        current_budget = call_kwargs.get(budget_key)
        if not isinstance(current_budget, int) or current_budget <= 0:
            return call_kwargs

        try:
            input_tokens = int(
                token_counter(
                    model=self.model,
                    messages=formatted_messages,
                    tools=cc_tools or None,
                    custom_tokenizer=self._tokenizer,
                )
            )
        except Exception:
            logger.debug(
                "Joint-budget clamp: token_counter failed for %s; "
                "leaving max_tokens unchanged",
                self.model,
                exc_info=True,
            )
            return call_kwargs

        headroom = context_window - input_tokens - JOINT_BUDGET_SAFETY_MARGIN_TOKENS
        clamped = max(min(current_budget, headroom), JOINT_BUDGET_MIN_OUTPUT_TOKENS)

        if clamped >= current_budget:
            return call_kwargs

        if headroom < JOINT_BUDGET_MIN_OUTPUT_TOKENS:
            logger.warning(
                "Input tokens (%s) leave only %s tokens of headroom in the %s "
                "context window for %s; sending the floor of %s. The provider "
                "may still reject this request -- consider condensing history.",
                input_tokens,
                max(headroom, 0),
                context_window,
                self.model,
                JOINT_BUDGET_MIN_OUTPUT_TOKENS,
            )
        else:
            logger.debug(
                "Clamping %s from %s to %s for %s "
                "(input_tokens=%s, context_window=%s, joint-budget provider)",
                budget_key,
                current_budget,
                clamped,
                self.model,
                input_tokens,
                context_window,
            )
        return {**call_kwargs, budget_key: clamped}

    def _init_model_info_and_caps(self) -> None:
        self._model_info = get_litellm_model_info(
            secret_api_key=self.api_key,
            base_url=self.base_url,
            model=self._model_name_for_capabilities(),
        )

        self._effective_max_input_tokens = self.max_input_tokens
        if (
            self._effective_max_input_tokens is None
            and self._model_info is not None
            and isinstance(self._model_info.get("max_input_tokens"), int)
        ):
            self._effective_max_input_tokens = self._model_info.get("max_input_tokens")

        # 验证上下文窗口尺寸
        self._validate_context_window_size()

        effective_max_output_tokens = self.max_output_tokens
        if effective_max_output_tokens is None:
            if any(
                m in self.model
                for m in [
                    "claude-3-7-sonnet",
                    "claude-sonnet-4",
                    "kimi-k2-thinking",
                ]
            ):
                effective_max_output_tokens = (
                    64000  # 实用上限（LiteLLM 可能允许 128k 带标头）
                )
                logger.debug(
                    f"Setting effective max_output_tokens to "
                    f"{effective_max_output_tokens} "
                    f"for {self.model}"
                )
            elif self._model_info is not None:
                if isinstance(self._model_info.get("max_output_tokens"), int):
                    effective_max_output_tokens = self._model_info.get(
                        "max_output_tokens"
                    )
                    # 守卫：如果 max_output_tokens >= 上下文窗口，
                    # 要求许多输出token将为输入和严格的提供者留下零空间（e.g。 AWS
                    # Bedrock）将拒绝每个呼叫。 将其减半，以便输入有空间。 我们检查
                    # max_input_tokens 和 max_tokens，因为其中任何一个都可能代表上下文窗
                    # 口，具体取决于提供商。
                    #
                    context_window = (
                        self.effective_max_input_tokens
                        or self._model_info.get("max_tokens")
                    )
                    if (
                        context_window is not None
                        and effective_max_output_tokens is not None
                        and effective_max_output_tokens >= context_window
                    ):
                        capped = effective_max_output_tokens // 2
                        logger.debug(
                            "Capping max_output_tokens from %s to %s "
                            "for %s (max_output_tokens >= context "
                            "window %s)",
                            effective_max_output_tokens,
                            capped,
                            self.model,
                            context_window,
                        )
                        effective_max_output_tokens = capped
                    if (
                        self.base_url is not None
                        and not self.model.startswith("litellm_proxy/")
                        and effective_max_output_tokens is not None
                        and effective_max_output_tokens > DEFAULT_MAX_OUTPUT_TOKENS_CAP
                    ):
                        logger.debug(
                            "Capping max_output_tokens from %s to %s for %s "
                            "(model metadata may exceed provider limit)",
                            effective_max_output_tokens,
                            DEFAULT_MAX_OUTPUT_TOKENS_CAP,
                            self.model,
                        )
                        effective_max_output_tokens = DEFAULT_MAX_OUTPUT_TOKENS_CAP
                elif isinstance(self._model_info.get("max_tokens"), int):
                    # “max_tokens”不明确：一些提供商将其用于总计上下文窗口，而不是输出限
                    # 制。 对其进行限制以避免请求超出上下文窗口的输出。
                    #
                    max_tokens_value = self._model_info.get("max_tokens")
                    assert isinstance(max_tokens_value, int)  # for type checker
                    effective_max_output_tokens = min(
                        max_tokens_value, DEFAULT_MAX_OUTPUT_TOKENS_CAP
                    )
                    if max_tokens_value > DEFAULT_MAX_OUTPUT_TOKENS_CAP:
                        logger.debug(
                            "Capping max_output_tokens from %s to %s for %s "
                            "(max_tokens may be context window, not output)",
                            max_tokens_value,
                            effective_max_output_tokens,
                            self.model,
                        )

        if "o3" in self.model:
            o3_limit = 100000
            if (
                effective_max_output_tokens is None
                or effective_max_output_tokens > o3_limit
            ):
                effective_max_output_tokens = o3_limit
                logger.debug(
                    "Clamping effective max_output_tokens to %s for %s",
                    effective_max_output_tokens,
                    self.model,
                )

        self._effective_max_output_tokens = effective_max_output_tokens

    def _validate_context_window_size(self) -> None:
        """验证上下文窗口对于 OpenHands 来说足够大。"""
        # 允许通过环境变量覆盖
        if os.environ.get(ENV_ALLOW_SHORT_CONTEXT_WINDOWS, "").lower() in (
            "true",
            "1",
            "yes",
        ):
            return

        # 未知上下文窗口 - 无法验证
        if self.effective_max_input_tokens is None:
            return

        # 检查最低要求
        if self.effective_max_input_tokens < MIN_CONTEXT_WINDOW_TOKENS:
            raise LLMContextWindowTooSmallError(
                self.effective_max_input_tokens, MIN_CONTEXT_WINDOW_TOKENS
            )

    def vision_is_active(self) -> bool:
        return not self.disable_vision and self._model_features().supports_vision

    def is_caching_prompt_active(self) -> bool:
        """检查当前型号是否支持并启用提示词缓存。

        Returns:
            boolean: True 如果提示词缓存受支持并为给定启用
                模型。
        """
        if not self.caching_prompt:
            return False
        return self.caching_prompt and self._model_features().supports_prompt_cache

    def uses_responses_api(self) -> bool:
        """该模型是否使用 OpenAI 响应 API 路径。"""

        if self.api_mode != "auto":
            return self.api_mode == "responses"
        return self._model_features().supports_responses_api

    @property
    def model_info(self) -> dict | None:
        """返回模型信息字典。"""
        return self._model_info

    @property
    def effective_max_input_tokens(self) -> int | None:
        """已解决运行时使用的上下文窗口。

        ``max_input_tokens`` 仍然是用户配置的值并且始终获胜。 当未设置时，使用先前已
        解决的提供者感知运行时限制（此属性不进行网络 I/O），并
        回退到从模型元数据中发现的值。
        """
        if self.max_input_tokens:
            return self.max_input_tokens
        cached = cached_metadata(
            self._runtime_metadata, self._runtime_metadata_fetched_at
        )
        if cached is not None and cached.max_input_tokens is not None:
            return cached.max_input_tokens
        return self._effective_max_input_tokens

    @property
    def effective_max_output_tokens(self) -> int | None:
        """解决了运行时使用的输出 token 限制。

        ``max_output_tokens`` 仍然是用户配置的值并且始终获胜。 此属性不执行网络 I/O，
        并回退到从模型元数据发现的值。 运行时（提供者）解析
        仅细化输入/上下文限制，从不细化输出限制，因此在这里不需要调用任何输出 token（
        见 issue #4421）。
        """
        return self.max_output_tokens or self._effective_max_output_tokens

    # =========================================================================
    # 运行时（提供商感知）元数据
    # =========================================================================
    def resolve_runtime_metadata(
        self, *, force: bool = False
    ) -> ModelRuntimeMetadata | None:
        """同步解决提供者感知的运行时限制（惰性+缓存）。

        Discovery 在构建期间从不运行。 不支持的提供者和无法解析的路由返回 ``None``，
        因此调用者会退回到静态模型元数据。 成功的结果会被缓存
        ``RUNTIME_METADATA_TTL_SECONDS``; 失败会被短暂地负缓存。

        首选智能体-服务器事件循环上的：meth:`aresolve_runtime_metadata`，它在进程内执
        行无阻塞网络 I/O。 一个正在飞行中的并发解
        决方案不能被一个陈旧的（早启动的）探针覆盖：每个探针都携带一个生成版本，只有
        最新的生成版本才能发布结果。
        """
        # LLM 可以通过同步路径在线程之间共享，因此缓存读取/检查和存储必须是原子的。 网络
        # 探测器本身在锁之外运行，因此速度较慢的端点无法阻止其他线程读取缓存。
        #
        with self._runtime_metadata_lock:
            if not force:
                cached = cached_metadata(
                    self._runtime_metadata, self._runtime_metadata_fetched_at
                )
                if cached is not None:
                    return cached
                if in_negative_cache(self._runtime_metadata_negative_until):
                    return None
            generation = self._runtime_metadata_generation + 1
            self._runtime_metadata_generation = generation

        metadata = resolve_provider_metadata_sync(self)
        self._store_runtime_metadata(metadata, generation)
        return metadata

    async def aresolve_runtime_metadata(
        self, *, force: bool = False
    ) -> ModelRuntimeMetadata | None:
        """异步：meth:`resolve_runtime_metadata` 的变体。

        并发对同一路由的调用已进行重复数据删除，因此仅发出一个上游请求。 如果调用者正
        在配置上下文压缩器或上下文管理，请在计算 token 阈值之前解析。

        因为智能体-服务器可能驱动从多个事件循环共享的``LLM``，结果只有在同时没有*新的
        *解决（通过同步路径在另一个线程启动，或强制重新解决）时才发布。
        """
        if not force:
            cached = cached_metadata(
                self._runtime_metadata, self._runtime_metadata_fetched_at
            )
            if cached is not None:
                return cached
            if in_negative_cache(self._runtime_metadata_negative_until):
                return None

        with self._runtime_metadata_lock:
            generation = self._runtime_metadata_generation + 1
            self._runtime_metadata_generation = generation

        metadata = await aresolve_provider_metadata(self)
        self._store_runtime_metadata(metadata, generation)
        return metadata

    def _store_runtime_metadata(
        self, metadata: ModelRuntimeMetadata | None, generation: int
    ) -> None:
        fetched_at, negative_until, resolved = store_result(metadata)
        # 锁定，因此并发同步解析器（其探针在锁之外运行）无法观察撕裂/交错缓存状态。
        # Generation 防止陈旧的（较早开始的）探测覆盖较新决议的结果：只有最新一代可以发
        # 布。
        #
        with self._runtime_metadata_lock:
            if generation != self._runtime_metadata_generation:
                # 被更新的决议取代； 放弃这个结果。
                return
            self._runtime_metadata_fetched_at = fetched_at
            self._runtime_metadata_negative_until = negative_until
            if resolved is not None:
                self._runtime_metadata = resolved
            self._runtime_metadata_key = runtime_metadata_cache_key(self)

    def _reset_runtime_metadata_for_key(self) -> None:
        """当路由（缓存键）更改时，删除运行时元数据缓存。"""
        with self._runtime_metadata_lock:
            self._runtime_metadata = None
            self._runtime_metadata_fetched_at = None
            self._runtime_metadata_negative_until = None
            self._runtime_metadata_key = None
            self._runtime_metadata_generation += 1

    @property
    def resolved_runtime_metadata(self) -> ModelRuntimeMetadata | None:
        """当前缓存运行时元数据，不触发发现。"""
        return cached_metadata(
            self._runtime_metadata, self._runtime_metadata_fetched_at
        )

    # =========================================================================
    # 从上一课中保留的实用程序
    # =========================================================================
    def _apply_prompt_caching(self, messages: list[Message]) -> None:
        """将缓存断点应用于消息。

        对于Anthropic的前缀缓存，我们标记特定的内容块：
        1. 系统消息：将第一个块（静态提示词）标记为缓存。 如果有两个块（静态+动态），
        则仅标记第一个块以启用跨会话缓存共享。
        2. 最后的用户/工具消息：标记缓存以扩展缓存前缀。
        """
        if len(messages) > 0 and messages[0].role == "system":
            sys_content = messages[0].content
            if len(sys_content) >= 2:
                # 两块结构：静态（索引0）+动态（索引1） 只标记静态块； 确保动态未标记
                #
                sys_content[0].cache_prompt = True
                sys_content[1].cache_prompt = False
            elif len(sys_content) == 1:
                # 单个块：标记为缓存
                sys_content[0].cache_prompt = True

        # 第二个断点：标记最后一个用户/工具消息，以便缓存的前缀每回合都会扩展。
        # Anthropic-仅； Gemini 被排除在 PROMPT_CACHE_MODELS 之外，因为它的缓存无法以这
        # 种方式扩展。
        #
        for message in reversed(messages):
            if message.role in ("user", "tool"):
                message.content[-1].cache_prompt = True  # 消息内容中的最后一项
                break

    def _inline_required(self) -> bool:
        """判断 http(s) 图片 URLs 是否必须下载并内联。"""
        if self.inline_image_urls is not None:
            return self.inline_image_urls
        return self._model_features().requires_inline_image_data

    def _begin_chat_messages(
        self, messages: list[Message]
    ) -> tuple[list[Message], bool]:
        """深度复制 ``messages`` 并应用提示词缓存标志。

        由同步和异步聊天格式路径共享。 返回分离的消息列表和已解决的``vision_enabled``
        标志，以便调用者可以插入自己的同步或异步内联图像传递，而不重
        复样板代码。
        """
        messages = copy.deepcopy(messages)
        if self.is_caching_prompt_active():
            self._apply_prompt_caching(messages)
        return messages, self.vision_is_active()

    def _prepare_chat_messages(self, messages: list[Message]) -> list[Message]:
        """应用缓存+内联+调整大小传递，返回分离的消息。"""
        messages, vision_enabled = self._begin_chat_messages(messages)
        # 在行（）URL → data:), 然后缩放 (data: → 更小的数据：)。 只在缩放阶段操作
        # ``data:image/*``  URLs因此，链式操作为我们提供了“免费”的大图保护，用于嵌入的图
        # 片。
        #
        messages = maybe_inline_image_urls(
            messages,
            inline_required=self._inline_required(),
            vision_enabled=vision_enabled,
        )
        messages = maybe_resize_messages_for_provider(
            messages,
            provider=self._infer_model_info_provider(),
            vision_enabled=vision_enabled,
        )
        return messages

    def _to_chat_dicts(self, messages: list[Message]) -> list[dict]:
        model_features = self._model_features()
        cache_enabled = self.is_caching_prompt_active()
        vision_enabled = self.vision_is_active()
        function_calling_enabled = self.native_tool_calling
        force_string_serializer = (
            self.force_string_serializer
            if self.force_string_serializer is not None
            else model_features.force_string_serializer
        )
        send_reasoning_content = model_features.send_reasoning_content
        return [
            message.to_chat_dict(
                cache_enabled=cache_enabled,
                vision_enabled=vision_enabled,
                function_calling_enabled=function_calling_enabled,
                force_string_serializer=force_string_serializer,
                send_reasoning_content=send_reasoning_content,
            )
            for message in messages
        ]

    def format_messages_for_llm(self, messages: list[Message]) -> list[dict]:
        """格式化 Message 对象以供 LLM 使用。"""
        return self._to_chat_dicts(self._prepare_chat_messages(messages))

    async def aformat_messages_for_llm(self, messages: list[Message]) -> list[dict]:
        """异步运行阻塞内联/调整大小传递闭环的变体。

        保留在同步和 ``_prepare_chat_messages`` 中：添加的任何新消息准备过程也必须添
        加到此处（并且在
        ``aformat_messages_for_responses``)，因为 ``await`` 不能在同步帮助器内部使用
        。
        """
        messages, vision_enabled = self._begin_chat_messages(messages)
        messages = await amaybe_inline_image_urls(
            messages,
            inline_required=self._inline_required(),
            vision_enabled=vision_enabled,
        )
        messages = maybe_resize_messages_for_provider(
            messages,
            provider=self._infer_model_info_provider(),
            vision_enabled=vision_enabled,
        )
        return self._to_chat_dicts(messages)

    def _prepare_responses_messages(self, messages: list[Message]) -> list[Message]:
        """分离消息并可选择删除推理项。"""
        msgs = copy.deepcopy(messages)

        # 订阅模式（store=False）：从之前的助理轮次中剥离推理项目。 Codex 端点没有持久化
        # 项，因此在后续请求中引用它们的 ID 会导致 404。
        #
        if self.is_subscription:
            for m in msgs:
                if m.role == "assistant" and m.responses_reasoning_item is not None:
                    m.responses_reasoning_item = None
        return msgs

    def _build_responses_payload(
        self, msgs: list[Message]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        vision_active = self.vision_is_active()
        instructions: str | None = None
        input_items: list[dict[str, Any]] = []
        system_chunks: list[str] = []

        for m in msgs:
            val = m.to_responses_value(vision_enabled=vision_active)
            if isinstance(val, str):
                s = val.strip()
                if s:
                    if self.is_subscription:
                        system_chunks.append(s)
                    else:
                        instructions = (
                            s
                            if instructions is None
                            else f"{instructions}\n\n---\n\n{s}"
                        )
            elif val:
                input_items.extend(val)

        if self.is_subscription:
            return transform_for_subscription(system_chunks, input_items)
        return instructions, input_items

    def format_messages_for_responses(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """为 OpenAI 响应 API 准备（指令，输入 []）。

        - 跳过提示词缓存标志和字符串序列化器问题
        - 使用 Message.to_responses_value 获取指令（系统）或输入项（其他）
        - 将系统指令连接成单个指令字符串
        - 对于订阅模式，系统提示词被添加到用户内容之前
        - 当活动模型需要时，将内联图像 http(s) URLs 作为 base64
        """
        msgs = self._prepare_responses_messages(messages)
        msgs = maybe_inline_image_urls(
            msgs,
            inline_required=self._inline_required(),
            vision_enabled=self.vision_is_active(),
        )
        return self._build_responses_payload(msgs)

    async def aformat_messages_for_responses(
        self, messages: list[Message]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """异步变体，在环外运行阻塞内联传递。

        保留在同步和 ``format_messages_for_responses`` 中：添加到此处的任何新消息准备
        过程也必须添加到此处。
        """
        msgs = self._prepare_responses_messages(messages)
        msgs = await amaybe_inline_image_urls(
            msgs,
            inline_required=self._inline_required(),
            vision_enabled=self.vision_is_active(),
        )
        return self._build_responses_payload(msgs)

    def get_token_count(
        self,
        messages: list[Message],
        tools: Sequence[ToolDefinition] | None = None,
        add_security_risk_prediction: bool = False,
    ) -> int:
        logger.debug(
            "Message objects now include serialized tool calls in token counting"
        )
        formatted_messages = self.format_messages_for_llm(messages)
        cc_tools = [
            tool.to_openai_tool(
                add_security_risk_prediction=add_security_risk_prediction,
            )
            for tool in tools or []
        ]
        use_mock_tools = self.should_mock_tool_calls(cc_tools)
        if use_mock_tools:
            tool_call_state: dict[str, Any] = {}
            formatted_messages, _ = self.pre_request_prompt_mock(
                formatted_messages,
                cc_tools,
                tool_call_state,
                include_security_params=add_security_risk_prediction,
            )
            cc_tools = []

        template_count = self._get_chat_template_token_count(
            formatted_messages, cc_tools
        )
        if template_count is not None:
            return template_count

        try:
            return int(
                token_counter(
                    model=self.model,
                    messages=formatted_messages,
                    tools=cc_tools or None,
                    custom_tokenizer=self._tokenizer,
                )
            )
        except Exception as e:
            logger.error(
                f"Error getting token count for model {self.model}\n{e}"
                + (
                    f"\ncustom_tokenizer: {self.custom_tokenizer}"
                    if self.custom_tokenizer
                    else ""
                ),
                exc_info=True,
            )
            return 0

    def _get_chat_template_token_count(
        self,
        formatted_messages: list[dict],
        tools: list[ChatCompletionToolParam],
    ) -> int | None:
        """当分词器聊天模板可用时，使用分词器聊天模板计数 token。

        LiteLLM 的通用 token 计数器估计 OpenAI 式聊天/工具开销。 通常，本地OpenAI-兼
        容服务器在分词之前会应用模型 tokenizer
         的聊天模板，这在工具模式被渲染成提示词后会显著不同。 如果调用者配置了支持
         ``apply_chat_template`` 的分词器，则更喜欢使用精确渲染
        的提示词形状进行上下文压缩器 token 检查，否则回退到 LiteLLM。
        """
        tokenizer = chat_template_tokenizer(
            self._chat_template_tokenizer or self._tokenizer
        )
        if tokenizer is None:
            return None

        try:
            template_messages = self._messages_for_chat_template(formatted_messages)
            kwargs: dict[str, Any] = {
                "tokenize": True,
                "add_generation_prompt": True,
            }
            if tools:
                kwargs["tools"] = tools
            tokenized = tokenizer.apply_chat_template(template_messages, **kwargs)
            return count_tokenized_output(tokenized, tokenizer)
        except Exception:
            logger.warning(
                "Chat-template token counting failed for %d messages and %d tools; "
                "falling back to LiteLLM",
                len(formatted_messages),
                len(tools or []),
                exc_info=True,
            )
            return None

    @staticmethod
    def _messages_for_chat_template(messages: list[dict]) -> list[dict]:
        template_messages = copy.deepcopy(messages)
        for message in template_messages:
            content = message.get("content")
            if isinstance(content, list):
                text_parts: list[str] = []
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "text":
                        text_parts = []
                        break
                    text_parts.append(str(block.get("text", "")))
                if text_parts:
                    message["content"] = "".join(text_parts)

            for tool_call in message.get("tool_calls") or []:
                function = tool_call.get("function")
                if not isinstance(function, dict):
                    continue
                arguments = function.get("arguments")
                if not isinstance(arguments, str):
                    continue
                try:
                    parsed_arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed_arguments, dict):
                    function["arguments"] = parsed_arguments
        return template_messages

    @classmethod
    def from_persisted(cls, data: Any, *, context: dict[str, Any] | None = None) -> LLM:
        """加载已持久化 LLM 配置文件载荷，应用模式迁移。"""
        if not isinstance(data, dict):
            return cls.model_validate(data, context=context)

        payload = dict(data)
        version = payload.get("schema_version", 0) or 0
        if type(version) is not int:
            raise ValueError("LLM profile schema_version must be an integer")
        if version > LLM_PROFILE_SCHEMA_VERSION:
            raise ValueError(
                "LLM profile schema_version "
                f"{version} is newer than supported version "
                f"{LLM_PROFILE_SCHEMA_VERSION}"
            )

        payload.pop("schema_version", None)
        payload = canonicalize_openhands_llm_payload(payload)
        llm = cls.model_validate(payload, context=context)
        if llm.auth_type == "subscription":
            from openhands.sdk.llm.auth.openai import (
                create_subscription_llm_from_config,
            )

            return create_subscription_llm_from_config(llm)
        return llm

    def to_persisted(self, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """序列化此 LLM 用于配置文件持久化。"""
        data = self.model_dump(mode="json", exclude_none=True, context=context)
        if data.get("auth_type") == "subscription":
            data.pop("api_key", None)
            data.pop("base_url", None)
            data.pop("extra_headers", None)
        data["schema_version"] = LLM_PROFILE_SCHEMA_VERSION
        return data

    # =========================================================================
    # 序列化帮手
    # =========================================================================
    @classmethod
    def load_from_json(
        cls, json_path: str, *, context: dict[str, Any] | None = None
    ) -> LLM:
        """从 JSON 文件加载 LLM 实例。

        Args:
            json_path: 包含 LLM 配置的 JSON 文件的路径。
            context: 可选验证上下文 (e.g., ``{"cipher": cipher}``
                用于解密存储在 REST 中的机密）。

        Returns:
            根据 JSON 配置构造的 LLM 实例。
        """
        with open(json_path) as f:
            data = json.load(f)
        return cls.from_persisted(data, context=context)

    @classmethod
    def load_from_env(cls, prefix: str = "LLM_") -> LLM:
        TRUTHY = {"true", "1", "yes", "on"}

        def _unwrap_type(t: Any) -> Any:
            origin = get_origin(t)
            if origin is None:
                return t
            args = [a for a in get_args(t) if a is not type(None)]
            return args[0] if args else t

        def _cast_value(raw: str, t: Any) -> Any:
            t = _unwrap_type(t)
            if t is SecretStr:
                return SecretStr(raw)
            if t is bool:
                return raw.lower() in TRUTHY
            if t is int:
                try:
                    return int(raw)
                except ValueError:
                    return None
            if t is float:
                try:
                    return float(raw)
                except ValueError:
                    return None
            origin = get_origin(t)
            if (origin in (list, dict, tuple)) or (
                isinstance(t, type) and issubclass(t, BaseModel)
            ):
                try:
                    return json.loads(raw)
                except Exception:
                    pass
            return raw

        data: dict[str, Any] = {}
        fields: dict[str, Any] = {
            name: f.annotation
            for name, f in cls.model_fields.items()
            if not getattr(f, "exclude", False)
        }

        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue
            field_name = key[len(prefix) :].lower()
            if field_name not in fields:
                continue
            v = _cast_value(value, fields[field_name])
            if v is not None:
                data[field_name] = v
        llm = cls(**data)
        if llm.auth_type == "subscription":
            from openhands.sdk.llm.auth.openai import (
                create_subscription_llm_from_config,
            )

            return create_subscription_llm_from_config(llm)
        return llm

    @classmethod
    def subscription_login(
        cls,
        vendor: SupportedVendor,
        model: str,
        force_login: bool = False,
        open_browser: bool = True,
        auth_method: OpenAIAuthMethod = "browser",
        **llm_kwargs,
    ) -> LLM:
        """使用订阅服务进行身份验证并返回 LLM 实例。

        此方法提供订阅访问 LLM 通过聊天订阅可用的模型e.g., ChatGPT Plus/Pro) 而不是
        API credits. 它处理了凭据缓存 tok
        en 刷新，以及OAuth登录流程。

        目前支持的供应商：
        - “OpenAI”：ChatGPT Codex 型号的 Plus/Pro 订阅

        支持的 OpenAI 型号：
        - GPT-5.6
        - gpt-5.6-溶胶
        - gpt-5.6-terra
        - gpt-5.6-月神
        - GPT-5.5
        - gpt-5.4
        - GPT-5.4-迷你

        Args:
            vendor: 供应商/提供商。 目前仅支持“OpenAI”。
            model: 要使用的模型。 必须得到供应商的支持
                订阅服务。
            force_login: 如果为 True，即使有效，也始终执行全新登录
                凭据存在。
            open_browser: 是否自动打开浏览器
                OAuth 登录流程。
            auth_method: 使用的登录方法：“浏览器”或“device_code”。
            **llm_kwargs: 要传递给 LLM 构造函数的其他参数。

        Returns:
            配置为基于订阅的访问的 LLM 实例。

        Raises:
            ValueError: 如果供应商或型号不受支持。
            RuntimeError: 如果身份验证失败。

        Example:
            ```python
            from openhands.sdk import LLM

            # 第一次：打开浏览器进行OAuth登录
            llm = LLM.subscription_login(vendor="openai", model="gpt-5.6")

            # 后续调用：重用缓存的凭据
            llm = LLM.subscription_login(vendor="openai", model="gpt-5.6")
            ```
        """
        from openhands.sdk.llm.auth.openai import subscription_login

        return subscription_login(
            vendor=vendor,
            model=model,
            force_login=force_login,
            open_browser=open_browser,
            auth_method=auth_method,
            **llm_kwargs,
        )
