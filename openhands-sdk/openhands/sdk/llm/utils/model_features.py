import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal

from litellm import get_supported_openai_params
from litellm.utils import supports_vision as litellm_supports_vision

from openhands.sdk.llm.utils.openhands_provider import OPENHANDS_PROVIDER_PREFIX


def model_matches(model: str | None, patterns: Iterable[str]) -> bool:
    """如果任何模式作为子字符串出现在原始模型名称中，则返回 True。

    匹配语义：
    - 对完整原始模型字符串进行不区分大小写的子字符串搜索
    """
    raw = (model or "").strip().lower()
    for pat in patterns:
        token = pat.strip().lower()
        if token in raw:
            return True
    return False


def apply_ordered_model_rules(model: str | None, rules: list[str]) -> bool:
    """应用有序的包含/排除模型规则来确定最终支持。

    规则语义：
    - 每个条目都是一个子字符串 token。 '！'前缀标记排除规则。
    - 与原始模型字符串匹配的不区分大小写的子字符串。
    - 按顺序评价； 最后匹配的规则获胜。
    - 如果没有规则匹配，则返回 False。
    """
    raw = (model or "").strip().lower()
    decided: bool | None = None
    for rule in rules:
        token = rule.strip().lower()
        if not token:
            continue
        is_exclude = token.startswith("!")
        core = token[1:] if is_exclude else token
        if core and core in raw:
            decided = not is_exclude
    return bool(decided)


@dataclass(frozen=True)
class ModelFeatures:
    supports_reasoning_effort: bool
    thinking_mode: Literal["adaptive", "manual", "none", "unknown"]
    supports_sampling_params: bool | None
    supports_extended_thinking: bool
    supports_prompt_cache: bool
    supports_prompt_cache_key: bool
    supports_stop_words: bool
    supports_responses_api: bool
    force_string_serializer: bool
    send_reasoning_content: bool
    supports_prompt_cache_retention: bool
    # True 当模型的 API 拒绝 http(s) image URLs 仅接受 base64 ``data:``  URLs. 参见
    # REQUIRES_INLINE_IMAGE_DATA_MODELS.
    #
    requires_inline_image_data: bool
    # 来自 LiteLLM 元数据加上 SDK 覆盖的有效功能。
    supports_vision: bool


LITELLM_PROXY_PREFIX = "litellm_proxy/"

# LiteLLM 代理配置中使用的常见部署路径前缀
DEPLOYMENT_PREFIXES = ("prod/", "dev/", "staging/", "test/")


def _normalize_model_for_litellm(model: str | None) -> str | None:
    """在查询 LiteLLM 元数据之前删除 SDK/代理路由前缀。"""
    if not model:
        return None

    normalized = model.strip().lower()
    for provider_prefix in (LITELLM_PROXY_PREFIX, OPENHANDS_PROVIDER_PREFIX):
        if normalized.startswith(provider_prefix):
            normalized = normalized.removeprefix(provider_prefix)
            break

    # 去除部署前缀（e.g.、“prod/”、“dev/”、“staging/”、“test/”）
    for prefix in DEPLOYMENT_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
            break

    if normalized == "kimi-k3":
        return "moonshot/kimi-k3"

    return normalized


# 描述 SDK/代理路由层而不是实际服务请求的上游的提供者标签。 LiteLLM 返回这些参数的完整
# OpenAI 参数集（包括 Anthropic 模型的 ``prompt_cache_key``），因此它们绝不能用作参数解
# 析的 ``custom_llm_provider`` 提示 - 这样做会重新引入 #5325 中的 400
# UnsupportedParamsError。
#
_PASSTHROUGH_PROVIDERS: frozenset[str] = frozenset({"litellm_proxy", "openhands"})


def _real_litellm_provider(
    model_info: Mapping[str, Any] | None,
) -> str | None:
    """返回为请求提供服务的上游提供商（如果已知）。

    对于 ``openhands/`` 和 ``litellm_proxy/`` 别名，模型通过代理路由，因此 LiteLLM 无
    法解析裸模型名称，并且
    ``get_supported_openai_params`` 返回 ``None``。 代理的模型信息携带真实的上游提供
    商（e.g. ``deepseek``、
    ``anthropic``）中
    ``litellm_provider``; 将其线程化到查找中可以恢复正确的参数检测。 直通标签（
    ``litellm_proxy``/``openhands``)
    被丢弃，因为 LiteLLM 过度报告了对它们的支持。
    """
    if model_info is None:
        return None
    provider = model_info.get("litellm_provider")
    if not isinstance(provider, str):
        return None
    provider = provider.strip().lower()
    if not provider or provider in _PASSTHROUGH_PROVIDERS:
        return None
    return provider


@cache
def _normalized_supported_openai_params(
    model: str | None, provider_hint: str | None = None
) -> frozenset[str]:
    """返回规范化模型名称的 LiteLLM 支持的 OpenAI 参数。

    ``provider_hint`` 是代理/别名模型的真正上游提供者（参见
    ``_real_litellm_provider``）。 当裸名不可解析——即
    ``openhands/``和``litellm_proxy/``别名的情况——则使用提示，以使参数支持反映实际提
    供请求的提供商，而不是默认为``False`` (
    #5328跟进)。

    NOTE: 提供者范围内的查找拓宽了整个参数集（e.g. 为了
    DeepSeek它还报告了``reasoning_effort``）。 只想恢复 ``prompt_cache_key`` 的调用者
    不得将提示集提供给不相关的功能
    - 使用 ``_supports_prompt_cache_key_param`` 而不是直接读取该集。 参见
    ``get_features``。
    """
    normalized = _normalize_model_for_litellm(model)
    if not normalized:
        return frozenset()

    params = get_supported_openai_params(
        model=normalized,
        custom_llm_provider=None,
    )
    if not params and provider_hint:
        params = get_supported_openai_params(
            model=normalized,
            custom_llm_provider=provider_hint,
        )
    return frozenset(params or ())


def _supports_prompt_cache_key_param(
    model: str | None, provider_hint: str | None
) -> bool:
    """服务提供者是否接受 ``prompt_cache_key`` 参数。

    首先从裸名参数集解析； 仅当无法解析时（代理/别名模型），它才会咨询提供者范围内的
    集合。 将提示范围限定为这一单一功能可以防止更广泛的提供者范围的参数集泄漏到不相关
    的功能中，例如
    ``supports_reasoning_effort``（#5332 审查后续）。
    """
    if "prompt_cache_key" in _normalized_supported_openai_params(model):
        return True
    if provider_hint is None:
        return False
    return "prompt_cache_key" in _normalized_supported_openai_params(
        model, provider_hint
    )


REASONING_EFFORT_MODEL_OVERRIDES = {
    "kimi-k3": "moonshot/kimi-k3",
}


EXTENDED_THINKING_MODELS: list[str] = [
    # Anthropic Claude 模型具有有用的智能体性能提升。
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
]

PROMPT_CACHE_MODELS: list[str] = [
    "claude-3-7-sonnet",
    "claude-sonnet-3-7-latest",
    "claude-3-5-sonnet",
    "claude-3-5-haiku",
    "claude-3-haiku-20240307",
    "claude-3-opus-20240229",
    "claude-sonnet-4",
    "claude-opus-4",
    # Anthropic Claude 4变种（官方ID使用连字符）
    "claude-haiku-4-5",
    "claude-sonnet-4-5",
    "claude-sonnet-4-6",
    "claude-opus-4-5",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-opus-4-8",
    "claude-haiku-5-5",
    # https://platform.claude.com/docs/en/build-with-claude/prompt-caching
    "claude-opus-5",
    # Claude Sonnet 5 支持提示词缓存，但上面的任何“claude-sonnet-4*”条目均未涵盖； 如果
    # 没有这个，每个输入 token 都不会缓存，这会取消该层在智能体工作负载上的价格优势。
    #
    "claude-sonnet-5",
    # https://www.anthropic.com/news/claude-fable-5
    "claude-fable-5",
    # 不添加 Gemini：显式 cache_control 标记会冻结其缓存于静态前缀，并禁用 Google 的隐式
    # 缓存在增长的主体 (~6-14x 成本)。 Gemini 使用隐式前缀缓存。
    #
]

# 支持顶级 prompt_cache_retention 参数的模型
# 来源：OpenAI 提示词缓存文档（扩展保留），其中列出：
#   - GPT-5.2
#   - GPT-5.1
#   - gpt-5.1-法典
#   - gpt-5.1-codex-mini
#   - gpt-5.1-聊天-最新
#   - GPT-5
#   - gpt-5-法典
# 注意：OpenAI 文档还列出了 gpt-4.1，但 Azure 拒绝
# prompt_cache_retention 用于 Azure 部署。 我们通常允许 GPT-4.1（e.g.、OpenAI/LiteLLM）
# 并明确排除 Azure。 使用有序的包含/排除规则（最后获胜）自然地表达异常。
#
PROMPT_CACHE_RETENTION_MODELS: list[str] = [
    # 广泛允许 GPT-5 系列（涵盖 gpt-5.2 和变体）
    "gpt-5",
    # 允许 OpenAI/LiteLLM 样式标识符使用 GPT-4.1
    "gpt-4.1",
    # 默认排除所有迷你变体
    "!mini",
    # 重新允许明确记录的支持的迷你变体
    "gpt-5.1-codex-mini",
    # Azure OpenAI 不支持 prompt_cache_retention
    "!azure/",
]

SUPPORTS_STOP_WORDS_FALSE_MODELS: list[str] = [
    # O 系列家族不支持停用词
    "o1",
    "o3",
    # grok-4 具体型号名称（basename）
    "grok-4-0709",
    "grok-code-fast-1",
    # DeepSeek R1家族
    "deepseek-r1-0528",
    # Bedrock 上的 OpenAI 模型（gpt-oss、gpt-5.x、gpt-6）拒绝 stopSequences
    "openai.gpt-",
]

# 默认情况下应使用 OpenAI 响应 API 路径的模型
# 注意：model_matches 使用不区分大小写的子字符串匹配，因此是一个裸家族
# token 如“gpt-5”/“gpt-6”涵盖所有变体（mini、sol、luna、astra，...）。
RESPONSES_API_MODELS: list[str] = [
    # OpenAI GPT-5 系列（包括迷你变体）
    "gpt-5",
    # OpenAI GPT-6 家族（gpt-6-sol、gpt-6-luna、gpt-6-astra，...）。 这些拒绝功能工具+
    # /v1/chat/completions上的reasoning_effort； /v1/responses两者都支持。 请参阅 saas-
    # deploy #1144。
    #
    "gpt-6",
    # OpenAI 法典（使用响应 API）
    "codex-mini-latest",
]

# 序列化器需要字符串的模型，这些模型不支持结构化内容格式[{"type":"text","text":"..."}]，
# 需要纯字符串
# 注意：model_matches 使用不区分大小写的子字符串匹配，而不是通配符。
#       将这些条目保留为不带通配符的裸子字符串。
FORCE_STRING_SERIALIZER_MODELS: list[str] = [
    # 只有旧版 DeepSeek v3.2 系列需要仅字符串内容。 较新的 v4/v4.1 id 接受结构化列表内容
    # ，并且匹配裸露的“deepseek”子字符串会将它们字符串序列化并删除图像部分。
    #
    "deepseek-v3.2",  # e.g., DeepSeek-V3.2-Exp, deepseek-v3.2-reasoner
    "glm",  # e.g., GLM-4.5 / GLM-4.6
    # Kimi K2-Instruct 仅在 Groq 上需要字符串序列化
    "groq/kimi-k2-instruct",  # 显式提供者前缀 ID
    # MiniMax-M2 via OpenRouter 拒绝数组内容，并且 ChatCompletionToolMessage.content 的“
    # 输入应该是有效的字符串”
    #
    "openrouter/minimax",
]

# 我们应该在消息输入中发送完整推理内容的模型
#
SEND_REASONING_CONTENT_MODELS: list[str] = [
    "kimi-k3",
    "kimi-k2-thinking",
    "kimi-k2.5",
    "kimi-k2.6",
    "openrouter/minimax-m2",  # MiniMax-M2 经由 OpenRouter（交错思维）
    "deepseek/deepseek-reasoner",
    "deepseek/deepseek-v4-pro",  # 双模式（思考/非思考）
    "deepseek/deepseek-v4-flash",  # 双模式（思考/非思考）
    "deepseek/deepseek-v4.1-flash",  # 双模式（思考/非思考）
]

# 匹配 token -> 视觉元数据覆盖的规范 LiteLLM ID。
VISION_MODEL_OVERRIDES: dict[str, str] = {}


@cache
def _model_supports_vision(model: str | None) -> bool:
    """返回 LiteLLM 是否将模型标记为可视的。"""
    normalized = _normalize_model_for_litellm(model)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return bool(normalized and litellm_supports_vision(normalized))


# API 拒绝 http(s) 图像 URLs，只接受 base64
# ``data:``  URLs (或特定供应商的文件标识) 当这个匹配时， SDK 获取每个图像 URL 并将其嵌
# 入其中 ``data:{mime};base64,...`` 在发送之前。 仅包括在生产运行中已验证此限制的模型（
# 请参阅 kimi-k2.6 的问题 #3155）。
#
# 注意：这是故意缩小的。 同一提供商可以托管相同的
# 不同上游端口后端的模型 URLs (e.g。 bedrock/moonshotai.kimi-k2.5, fireworks_ai/.
# ../kimi-k2.6)，所以我们根据具体的模型ID匹配，而不是根据提供者的名称。
#
REQUIRES_INLINE_IMAGE_DATA_MODELS: tuple[str, ...] = (
    # Moonshot 公开 Kimi API： https://platform.kimi.ai/docs/guide/use-kimi-vision-model
    # > URL格式的图片：不支持，目前仅支持
    # > Base64编码的图像内容和通过文件ID上传的图像/视频
    "moonshot/kimi-k2.6",
    "moonshot/kimi-k3",
    # OpenHands K3 路线使用相同的 Moonshot 图像输入合约。
    "openhands/kimi-k3",
)


def _optional_bool(source: Mapping[str, Any] | None, key: str) -> bool | None:
    if source is None:
        return None
    value = source.get(key)
    return value if isinstance(value, bool) else None


def _resolved_bool(
    key: str,
    *,
    overrides: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None,
    fallback: bool,
    metadata_key: str | None = None,
) -> bool:
    """解析布尔能力而不丢失显式 ``False``。"""
    override = _optional_bool(overrides, key)
    if override is not None:
        return override
    discovered = _optional_bool(metadata, metadata_key or key)
    if discovered is not None:
        return discovered
    return fallback


def _thinking_mode(
    model: str | None,
    model_info: Mapping[str, Any] | None,
    overrides: Mapping[str, Any] | None,
) -> Literal["adaptive", "manual", "none", "unknown"]:
    if overrides is not None:
        override = overrides.get("thinking_mode")
        if override in {"adaptive", "manual", "none", "unknown"}:
            return override

    adaptive = _optional_bool(model_info, "supports_adaptive_thinking")
    if adaptive is True:
        return "adaptive"

    supports_reasoning = _optional_bool(model_info, "supports_reasoning")
    if supports_reasoning is False:
        return "none"
    if model_matches(model, EXTENDED_THINKING_MODELS):
        return "manual"
    if supports_reasoning is True:
        return "unknown"
    return "none"


def _supports_explicit_prompt_cache(
    model: str | None,
    model_info: Mapping[str, Any] | None,
    overrides: Mapping[str, Any] | None,
) -> bool:
    override = _optional_bool(overrides, "supports_prompt_cache")
    if override is not None:
        return override

    metadata_value = _optional_bool(model_info, "supports_prompt_caching")
    if metadata_value is False:
        return False
    if metadata_value is True:
        provider = str((model_info or {}).get("litellm_provider", "")).lower()
        registry_key = str((model_info or {}).get("key", "")).lower()
        # 此功能涵盖显式 cache_control，而不是隐式缓存。
        if (
            provider == "anthropic"
            or "claude" in (model or "").lower()
            or "claude" in registry_key
            or "anthropic" in registry_key
        ):
            return True

    return model_matches(model, PROMPT_CACHE_MODELS)


def _supports_responses_api(
    model: str | None,
    model_info: Mapping[str, Any] | None,
    overrides: Mapping[str, Any] | None,
) -> bool:
    override = _optional_bool(overrides, "supports_responses_api")
    if override is not None:
        return override

    endpoints = (model_info or {}).get("supported_endpoints")
    if isinstance(endpoints, (list, tuple)):
        if "/v1/responses" in endpoints:
            return True
        # 提供的端点列表是权威的，包括其遗漏。
        return False
    return model_matches(model, RESPONSES_API_MODELS)


def get_features(
    model: str | None,
    model_info: Mapping[str, Any] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> ModelFeatures:
    """从覆盖、元数据和回退方案解析模型特征。"""
    provider_hint = _real_litellm_provider(model_info)
    # 使用此处设置的裸名称参数，以便提供程序提示（仅需要恢复代理模型的 prompt_cache_key
    # ）不会泄漏到 reasoning_effort 检测中。 prompt_cache_key 通过下面的
    # _supports_prompt_cache_key_param 单独解决（#5332 审核后续）。
    #
    supported_params = _normalized_supported_openai_params(model)
    supports_reasoning_effort = _resolved_bool(
        "supports_reasoning_effort",
        overrides=overrides,
        metadata=model_info,
        metadata_key="supports_reasoning",
        fallback=(
            model_matches(model, REASONING_EFFORT_MODEL_OVERRIDES)
            or "reasoning_effort" in supported_params
        ),
    )
    thinking_mode = _thinking_mode(model, model_info, overrides)
    supports_sampling_params = _optional_bool(overrides, "supports_sampling_params")
    if supports_sampling_params is None:
        supports_sampling_params = _optional_bool(
            model_info, "supports_sampling_params"
        )
    return ModelFeatures(
        supports_reasoning_effort=supports_reasoning_effort,
        thinking_mode=thinking_mode,
        supports_sampling_params=supports_sampling_params,
        supports_extended_thinking=thinking_mode == "manual",
        supports_prompt_cache=_supports_explicit_prompt_cache(
            model, model_info, overrides
        ),
        supports_prompt_cache_key=_resolved_bool(
            "supports_prompt_cache_key",
            overrides=overrides,
            metadata=model_info,
            fallback=_supports_prompt_cache_key_param(model, provider_hint),
        ),
        supports_stop_words=_resolved_bool(
            "supports_stop_words",
            overrides=overrides,
            metadata=model_info,
            fallback=not model_matches(model, SUPPORTS_STOP_WORDS_FALSE_MODELS),
        ),
        supports_responses_api=_supports_responses_api(model, model_info, overrides),
        force_string_serializer=model_matches(model, FORCE_STRING_SERIALIZER_MODELS),
        send_reasoning_content=model_matches(model, SEND_REASONING_CONTENT_MODELS),
        # 扩展 prompt_cache_retention 支持遵循有序的包含/排除规则。
        supports_prompt_cache_retention=_resolved_bool(
            "supports_prompt_cache_retention",
            overrides=overrides,
            metadata=model_info,
            fallback=apply_ordered_model_rules(model, PROMPT_CACHE_RETENTION_MODELS),
        ),
        requires_inline_image_data=model_matches(
            model, REQUIRES_INLINE_IMAGE_DATA_MODELS
        ),
        supports_vision=_resolved_bool(
            "supports_vision",
            overrides=overrides,
            metadata=model_info,
            fallback=_model_supports_vision(model),
        ),
    )
