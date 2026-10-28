"""能力检测测试。

LiteLLM 从其上游获取 ``model_prices_and_context_window.json``
``main`` 在导入时的分支，所以需要打桩 LiteLLM 在 ``uv.lock`` 只锁定代码，但未锁定模型
数据库——和  SDK 不设置任何覆盖，仅在测试或生产环
境中使用。 因此，这些测试针对的是那些无需我们而改变的数据。

断言 SDK 拥有什么：它的覆盖列表、它的模型名称规范化以及路由包装器不会更改答案。 背后
没有 SDK 规则的裸能力值是上游要更改的，并且在此处固定一个会在它发生时失败（#
4877）。
"""

import pytest
from litellm import get_supported_openai_params
from litellm.utils import supports_vision

from openhands.sdk.llm.utils.model_features import (
    REASONING_EFFORT_MODEL_OVERRIDES,
    VISION_MODEL_OVERRIDES,
    _normalized_supported_openai_params,
    get_features,
    model_matches,
)
from openhands.sdk.llm.utils.model_info import get_litellm_model_info


@pytest.mark.parametrize(
    "name,pattern,expected",
    [
        ("gpt-4o", "gpt-4o", True),
        ("openai/gpt-4o", "gpt-4o", True),
        ("litellm_proxy/gpt-4o-mini", "gpt-4o", True),
        ("claude-3-7-sonnet-20250219", "claude-3-7-sonnet", True),
        ("o1-2024-12-17", "o1", True),
        ("grok-4-0709", "grok-4-0709", True),
        ("grok-4-0801", "grok-4-0709", False),
    ],
)
def test_model_matches(name, pattern, expected):
    assert model_matches(name, [pattern]) is expected


@pytest.mark.parametrize(
    "model,expected_reasoning",
    [
        ("o1-2024-12-17", True),
        ("o1", True),
        ("o3-mini", True),
        ("o3", True),
        # Anthropic Opus 4.5（仅限 dash 版本）
        ("claude-opus-4-5", True),
        ("nova-2-lite", False),
        # 双子座3家族
        ("gemini-3.1-pro-preview", True),
        ("gemini-3-flash-preview", True),
        # GPT-5家族
        ("gpt-5.2", True),
        ("gpt-5.4", True),
        ("gpt-4o", False),
        ("claude-3-5-sonnet", False),
        ("gemini-1.5-pro", False),
        # DeepSeek 推理者
        ("deepseek/deepseek-reasoner", True),
        # Moonshot Kimi 思维模型公开推理内容，但不接受 reasoning_effort 参数。
        #
        ("moonshot/kimi-k2.5", False),
        ("moonshot/kimi-k2-thinking", False),
        ("litellm_proxy/moonshot/kimi-k2-thinking", False),
        # Eval LiteLLM 代理包装器不应影响功能检测。
        ("litellm_proxy/gpt-5", True),
        ("litellm_proxy/claude-opus-4-5", True),
        ("litellm_proxy/gemini-3-flash-preview", True),
        ("claude-fable-5", True),
        ("anthropic/claude-fable-5", True),
        ("litellm_proxy/anthropic/claude-fable-5", True),
        ("kimi-k3", True),
        ("moonshot/kimi-k3", True),
        ("litellm_proxy/moonshot/kimi-k3", True),
        ("claude-opus-5", True),
        ("anthropic/claude-opus-5", True),
        ("litellm_proxy/anthropic/claude-opus-5", True),
        ("claude-opus-4-8", True),
        ("anthropic/claude-opus-4-8", True),
        ("bedrock/us.anthropic.claude-opus-4-8-v1:0", True),
        ("bedrock/eu.anthropic.claude-opus-4-8-v1:0", True),
        ("bedrock/apac.anthropic.claude-opus-4-8-v1:0", True),
        ("bedrock/global.anthropic.claude-opus-4-8-v1:0", True),
        # LiteLLM 具有部署路径前缀的代理（prod/、dev/、staging/、test/）
        ("litellm_proxy/prod/claude-opus-4-5-20251101", True),
        ("litellm_proxy/dev/claude-opus-4-5", True),
        ("litellm_proxy/staging/gpt-5", True),
        ("litellm_proxy/test/o1", True),
        ("unknown-model", False),
    ],
)
def test_reasoning_effort_support(model, expected_reasoning):
    features = get_features(model)
    assert features.supports_reasoning_effort == expected_reasoning


@pytest.mark.parametrize(
    "model",
    [
        "openrouter/moonshotai/kimi-k2.5",
        "openrouter/moonshotai/kimi-k2-thinking",
        "openrouter/deepseek/deepseek-r1",
        "openrouter/anthropic/claude-opus-4.5",
        "openrouter/openai/gpt-5",
    ],
)
def test_openrouter_reasoning_effort_follows_supported_params(model):
    supported_params = get_supported_openai_params(model=model) or []
    expected = "reasoning_effort" in supported_params

    assert get_features(model).supports_reasoning_effort == expected
    assert get_features(f"litellm_proxy/{model}").supports_reasoning_effort == expected


@pytest.mark.parametrize(
    "model,expected_extended_thinking",
    [
        # Anthropic扩展思维模型
        ("claude-sonnet-4-5", True),
        ("claude-sonnet-4-6", True),
        ("claude-haiku-4-5", True),
        # 提供商前缀变体
        ("anthropic/claude-sonnet-4-5", True),
        ("anthropic/claude-sonnet-4-6", True),
        ("anthropic/claude-haiku-4-5", True),
        # 不支持扩展思维的模型
        ("claude-3-7-sonnet", False),
        ("claude-sonnet-4", False),
        ("claude-opus-4-5", False),
        ("claude-opus-4-6", False),
        ("gpt-4o", False),
        ("o1", False),
        ("unknown-model", False),
    ],
)
def test_extended_thinking_support(model, expected_extended_thinking):
    """测试扩展思维模型是否被正确识别。"""
    features = get_features(model)
    assert features.supports_extended_thinking == expected_extended_thinking


@pytest.mark.parametrize(
    "model,expected_cache",
    [
        ("claude-3-5-sonnet", True),
        ("claude-3-7-sonnet", True),
        ("claude-3-haiku-20240307", True),
        ("claude-3-opus-20240229", True),
        # AWS 基岩模型 ID（提供商前缀）
        ("bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0", True),
        ("bedrock/anthropic.claude-3-haiku-20240307-v1:0", True),
        # Anthropic 4.5 和 4.6 变体（仅限破折号； 官方 ID 使用连字符）
        ("claude-haiku-4-5", True),
        ("us.anthropic.claude-haiku-4-5-20251001", True),
        ("bedrock/anthropic.claude-3-opus-20240229-v1:0", True),
        ("claude-sonnet-4-5", True),
        ("claude-sonnet-4-6", True),
        ("claude-opus-4-5", True),
        ("claude-opus-4-6", True),
        # Claude Fable 5 支持提示词跨模型名称形式的缓存。
        ("claude-fable-5", True),
        ("anthropic/claude-fable-5", True),
        ("litellm_proxy/anthropic/claude-fable-5", True),
        ("claude-haiku-5-5", True),
        ("anthropic/claude-haiku-5-5", True),
        ("litellm_proxy/anthropic/claude-haiku-5-5", True),
        ("claude-opus-5-5", True),
        ("anthropic/claude-opus-5-5", True),
        ("litellm_proxy/anthropic/claude-opus-5-5", True),
        # Claude Opus 5 支持提示词跨原始、直接提供者和代理前缀形式的缓存。
        #
        ("claude-opus-5", True),
        ("anthropic/claude-opus-5", True),
        ("litellm_proxy/anthropic/claude-opus-5", True),
        # claude-sonnet-5 与任何 claude-sonnet-4* 条目都不匹配，必须明确列出，与 claude-
        # fable-5 相同。
        #
        ("claude-sonnet-5", True),
        ("anthropic/claude-sonnet-5", True),
        ("litellm_proxy/anthropic/claude-sonnet-5", True),
        # 面向用户的模型名称（无提供商前缀）
        ("anthropic.claude-3-5-sonnet-20241022", True),
        ("anthropic.claude-3-haiku-20240307", True),
        ("anthropic.claude-3-opus-20240229", True),
        # Gemini 必须不使用显式 cache_control 标记：它们冻结静态前缀处的缓存并禁用
        # Google 的隐式缓存。
        #
        ("gemini-2.5-pro", False),
        ("gemini-3.1-pro-preview", False),
        ("litellm_proxy/gemini-3.1-pro-preview", False),
        ("gpt-4o", False),  # OpenAI 不支持显式提示词缓存
        ("gemini-1.5-pro", False),
        ("unknown-model", False),
    ],
)
def test_prompt_cache_support(model, expected_cache):
    features = get_features(model)
    assert features.supports_prompt_cache == expected_cache


@pytest.mark.parametrize(
    "model,expected_stop_words",
    [
        ("gpt-4o", True),
        ("gpt-4o-mini", True),
        ("claude-3-5-sonnet", True),
        ("gemini-1.5-pro", True),
        ("llama-3.1-70b", True),
        ("unknown-model", True),  # 大多数模型支持停用词
        ("bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0", True),
        # 不支持停用词的模型
        ("o1", False),
        ("o1-2024-12-17", False),
        ("grok-4-0709", False),
        ("grok-code-fast-1", False),
        ("xai/grok-4-0709", False),
        ("xai/grok-code-fast-1", False),
    ],
)
def test_stop_words_support(model, expected_stop_words):
    features = get_features(model)
    assert features.supports_stop_words == expected_stop_words


def test_get_features_with_provider_prefix():
    """测试 get_features 是否适用于提供者前缀。

    推理工作检测将提供程序解析委托给 LiteLLM（我们只剥离 `litellm_proxy/` 包装器）。
    """
    assert get_features("openai/gpt-4o").supports_reasoning_effort is False
    assert (
        get_features("anthropic/claude-3-5-sonnet").supports_reasoning_effort is False
    )
    assert get_features("litellm_proxy/gpt-4o").supports_reasoning_effort is False

    # 已知的具有推理能力的模型 ID 应该被识别。
    assert get_features("claude-sonnet-4-5").supports_reasoning_effort is True
    assert get_features("anthropic/claude-sonnet-4-5").supports_reasoning_effort is True


def test_get_features_case_insensitive():
    """测试 get_features 是否不区分大小写。"""
    features_lower = get_features("gpt-4o")
    features_upper = get_features("GPT-4O")
    features_mixed = get_features("Gpt-4O")

    assert (
        features_lower.supports_reasoning_effort
        == features_upper.supports_reasoning_effort
    )
    assert features_lower.supports_stop_words == features_upper.supports_stop_words
    assert (
        features_lower.supports_reasoning_effort
        == features_mixed.supports_reasoning_effort
    )


def test_get_features_with_version_suffixes():
    """测试 get_features 是否正确处理版本后缀。"""
    # 测试版本后缀是否正确处理
    base_features = get_features("claude-3-5-sonnet")
    versioned_features = get_features("claude-3-5-sonnet-20241022")

    assert (
        base_features.supports_reasoning_effort
        == versioned_features.supports_reasoning_effort
    )
    assert base_features.supports_stop_words == versioned_features.supports_stop_words
    assert (
        base_features.supports_prompt_cache == versioned_features.supports_prompt_cache
    )


def test_model_matches_multiple_patterns():
    """使用多种模式测试 model_matches。"""
    patterns = ["gpt-4", "claude-3", "gemini-"]

    assert model_matches("gpt-4o", patterns) is True
    assert model_matches("claude-3-5-sonnet", patterns) is True
    assert model_matches("gemini-1.5-pro", patterns) is True
    assert model_matches("llama-3.1-70b", patterns) is False


def test_model_matches_substring_semantics():
    """测试 model_matches 使用子字符串语义（无通配）。"""
    patterns = ["gpt-4o", "claude-3-5-sonnet"]

    assert model_matches("gpt-4o", patterns) is True
    assert model_matches("claude-3-5-sonnet", patterns) is True
    # 子字符串匹配：“gpt-4o”匹配“gpt-4o-mini”
    assert model_matches("gpt-4o-mini", patterns) is True
    assert model_matches("claude-3-haiku", patterns) is False


def test_get_features_unknown_model():
    """使用完全未知的模型测试 get_features。"""
    features = get_features("completely-unknown-model-12345")

    # 未知模型应具有默认特征值
    assert features.supports_reasoning_effort is False
    assert features.supports_prompt_cache is False
    assert features.supports_vision is False
    assert features.supports_stop_words is True  # 大多数模型支持停用词


def test_metadata_drives_adaptive_thinking_and_sampling():
    features = get_features(
        "anthropic/claude-sonnet-5",
        model_info={
            "litellm_provider": "anthropic",
            "supports_reasoning": True,
            "supports_adaptive_thinking": True,
            "supports_sampling_params": False,
            "supports_prompt_caching": True,
        },
    )

    assert features.supports_reasoning_effort is True
    assert features.thinking_mode == "adaptive"
    assert features.supports_extended_thinking is False
    assert features.supports_sampling_params is False
    assert features.supports_prompt_cache is True


def test_gemini_metadata_does_not_enable_explicit_prompt_cache():
    features = get_features(
        "litellm_proxy/gemini-3.1-pro-preview",
        model_info={
            "key": "gemini-3.1-pro-preview",
            "litellm_provider": "vertex_ai",
            "supports_prompt_caching": True,
        },
    )

    assert features.supports_prompt_cache is False


def test_sampling_support_uses_preserved_litellm_metadata():
    model_info = get_litellm_model_info(
        secret_api_key=None,
        base_url=None,
        model="anthropic/claude-sonnet-5",
    )
    assert model_info is not None

    features = get_features(
        "anthropic/claude-sonnet-5",
        model_info=model_info,
    )

    assert features.supports_sampling_params is False


def test_metadata_false_takes_precedence_over_name_fallbacks():
    features = get_features(
        "openai/gpt-5",
        model_info={
            "supports_reasoning": False,
            "supports_prompt_caching": False,
            "supported_endpoints": [],
        },
    )

    assert features.supports_reasoning_effort is False
    assert features.supports_prompt_cache is False
    assert features.supports_responses_api is False


def test_capability_overrides_take_precedence_over_metadata():
    features = get_features(
        "proxy/future-model",
        model_info={
            "supports_reasoning": False,
            "supports_adaptive_thinking": False,
            "supports_sampling_params": True,
            "supports_vision": False,
        },
        overrides={
            "supports_reasoning_effort": True,
            "thinking_mode": "adaptive",
            "supports_sampling_params": False,
            "supports_responses_api": True,
            "supports_vision": True,
        },
    )

    assert features.supports_reasoning_effort is True
    assert features.thinking_mode == "adaptive"
    assert features.supports_sampling_params is False
    assert features.supports_responses_api is True
    assert features.supports_vision is True


def test_responses_api_is_discovered_from_model_metadata():
    features = get_features(
        "proxy/future-model",
        model_info={"supported_endpoints": ["/v1/chat/completions", "/v1/responses"]},
    )

    assert features.supports_responses_api is True


def test_get_features_empty_model():
    """使用空模型或 None 模型测试 get_features。"""
    features_empty = get_features("")
    features_none = get_features(None)

    # 空模型应该有默认的特征值
    assert features_empty.supports_reasoning_effort is False
    assert features_none.supports_reasoning_effort is False
    assert features_empty.supports_vision is False
    assert features_none.supports_vision is False
    assert features_empty.supports_stop_words is True
    assert features_none.supports_stop_words is True


@pytest.mark.parametrize(
    "model",
    [
        "kimi-k3",
        "moonshot/kimi-k3",
        "litellm_proxy/moonshot/kimi-k3",
        "openhands/kimi-k3",
    ],
)
def test_kimi_k3_supports_vision(model: str):
    assert get_features(model).supports_vision is True


@pytest.mark.parametrize(
    "model",
    [
        "gpt-4o",
        "openai/gpt-4o",
        "litellm_proxy/openai/gpt-4o",
        "openhands/gpt-4o",
        "litellm_proxy/prod/openai/gpt-4o",
    ],
)
def test_litellm_vision_support_is_exposed_as_model_feature(model: str):
    assert get_features(model).supports_vision is True


def test_reasoning_effort_overrides_are_not_redundant():
    for pattern, litellm_model in REASONING_EFFORT_MODEL_OVERRIDES.items():
        params = _normalized_supported_openai_params(litellm_model)
        assert "reasoning_effort" not in params, (
            f"Remove {pattern!r}: LiteLLM now supports {litellm_model!r}"
        )


def test_vision_overrides_are_not_redundant():
    for pattern, litellm_model in VISION_MODEL_OVERRIDES.items():
        assert not supports_vision(litellm_model), (
            f"Remove {pattern!r}: LiteLLM now supports {litellm_model!r}"
        )


def test_model_matches_with_provider_pattern():
    """model_matches 在原始模型名称中使用子字符串，包括。 提供者前缀。"""
    assert model_matches("openai/gpt-4", ["openai/"])
    assert model_matches("anthropic/claude-3", ["anthropic/claude"])
    assert not model_matches("openai/gpt-4", ["anthropic/"])


def test_stop_words_grok_provider_prefixed():
    """测试 grok 模型不支持带或不带提供商前缀的停用词。"""  # noqa: E501
    assert get_features("xai/grok-4-0709").supports_stop_words is False
    assert get_features("grok-4-0709").supports_stop_words is False
    assert get_features("xai/grok-code-fast-1").supports_stop_words is False
    assert get_features("grok-code-fast-1").supports_stop_words is False


@pytest.mark.parametrize(
    "model",
    [
        "o1-mini",
        "o1-2024-12-17",
        "xai/grok-4-0709",
        "xai/grok-code-fast-1",
        "bedrock/openai.gpt-oss-120b-1:0",
        "bedrock/us.openai.gpt-5.6-sol",
        "bedrock/us.openai.gpt-6-sol",
        "bedrock/global.openai.gpt-6-luna",
        "bedrock/us.openai.gpt-6-astra",
    ],
)
def test_supports_stop_words_false_models(model):
    """测试不支持停用词的模型。"""
    features = get_features(model)
    assert features.supports_stop_words is False


@pytest.mark.parametrize(
    "model,expected_responses",
    [
        ("gpt-5.1", True),
        ("openai/gpt-5.1-codex-mini", True),
        ("gpt-5", True),
        ("gpt-5.2", True),
        ("openai/gpt-5-mini", True),
        # GPT-6族拒绝功能工具+reasoning_effort上的/v1/chat/completions； 通过
        # /v1/responses 路由（saas-deploy #1144）。
        #
        ("gpt-6-sol", True),
        ("gpt-6-luna", True),
        ("gpt-6-astra", True),
        ("openai/gpt-6-sol", True),
        ("litellm_proxy/gpt-6-luna", True),
        ("codex-mini-latest", True),
        ("openai/codex-mini-latest", True),
        ("gpt-4o", False),
        ("unknown-model", False),
    ],
)
def test_responses_api_support(model, expected_responses):
    features = get_features(model)
    assert features.supports_responses_api is expected_responses


def test_force_string_serializer_full_model_names():
    """确保完整模型名称与字符串序列化器的子字符串模式匹配。

    回归遗留 DeepSeek v3.2 和广泛 GLM 模式的覆盖范围； Kimi 仅应在提供商以 groq/ 为前
    缀时匹配。
    """
    assert get_features("DeepSeek-V3.2-Exp").force_string_serializer is True
    assert get_features("deepseek-v3.2-reasoner").force_string_serializer is True
    assert get_features("GLM-4.5").force_string_serializer is True
    # 与提供商无关的 Kimi 不应强制使用字符串序列化器
    assert get_features("Kimi K2-Instruct-0905").force_string_serializer is False
    # Groq 前缀的 Kimi 应该强制字符串序列化器
    assert get_features("groq/kimi-k2-instruct-0905").force_string_serializer is True


@pytest.mark.parametrize(
    "model",
    [
        "openhands/deepseek-v4.1-flash",
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
        "deepseek-chat",
    ],
)
def test_deepseek_v4_models_use_structured_content(model):
    """DeepSeek v4/v4.1 ids 接受结构化（列表）内容，而不是字符串。

    只有旧版 v3.2 系列需要字符串序列化器； 这些 id 必须保留列表内容，以便保留它们的图
    像部分 (#5360)。
    """
    assert get_features(model).force_string_serializer is False


@pytest.mark.parametrize(
    "model,expected_key",
    [
        # OpenAI 模型接受 prompt_cache_key 参数
        ("gpt-4o", True),
        ("openai/gpt-5.2", True),
        # 人择/双子座拒绝它 UnsupportedParamsError
        ("claude-opus-4-5-20251101", False),
        ("claude-sonnet-4-5-20250929", False),
        ("gemini/gemini-2.5-pro", False),
        # 未解析的别名 -> 安全默认值 False（调用仍然成功）
        ("prod/my-unknown-alias", False),
    ],
)
def test_prompt_cache_key_support(model, expected_key):
    """supports_prompt_cache_key 跟踪 LiteLLM 的 supported_openai_params。

    与 supports_prompt_cache 不同（Anthropic cache_control 断点）：Claude 模型支持
    cache_control，但
    必须不接收 prompt_cache_key。
    """
    features = get_features(model)
    assert features.supports_prompt_cache_key is expected_key


def test_prompt_cache_key_override():
    """能力覆盖可以强制 prompt_cache_key 开/关。"""
    assert (
        get_features(
            "prod/my-openai-alias",
            overrides={"supports_prompt_cache_key": True},
        ).supports_prompt_cache_key
        is True
    )
    assert (
        get_features(
            "gpt-4o", overrides={"supports_prompt_cache_key": False}
        ).supports_prompt_cache_key
        is False
    )


@pytest.mark.parametrize(
    "model,provider",
    [
        # openhands/ 别名： LiteLLM 无法解析裸名称，因此必须将真正的上游提供者（来自代理
        # 的 model_info）线程化到查找中。 这些先前在 #5328 之后回归到 False。
        #
        ("deepseek-chat", "deepseek"),
        ("minimax-m3", "minimax"),
        ("qwen3.8-max", "dashscope"),
        ("kimi-k2.7-code", "moonshot"),
        ("kimi-k3", "moonshot"),
        ("trinity-large-thinking", "openrouter"),
    ],
)
def test_prompt_cache_key_resolved_via_provider_hint(model, provider):
    """代理/别名模型从真实提供者解析 prompt_cache_key。

    回归 #5328 后续测试：``openhands/`` 和
    ``litellm_proxy/`` 命名空间被简化为一个裸名，LiteLLM 无法解析，因此
    ``get_supported_openai_params`` 返回
     ``None``，尽管上游提供者接受它。
    """
    features = get_features(model, model_info={"litellm_provider": provider})
    assert features.supports_prompt_cache_key is True


def test_prompt_cache_key_passthrough_provider_not_used():
    """litellm_proxy/openhands 提示过度报告，必须忽略。

    LiteLLM 返回 litellm_proxy 提供者下每个模型的完整 OpenAI 参数集（包括
    prompt_cache_key）——甚至 Claude。 使
    用它作为提示将重新引入 #5325 中修复的 400 UnsupportedParamsError。
    """
    features = get_features(
        "claude-opus-5-5", model_info={"litellm_provider": "litellm_proxy"}
    )
    assert features.supports_prompt_cache_key is False


def test_prompt_cache_key_no_provider_hint_falls_back():
    """如果没有 model_info，裸露的不可解析名称将保留安全的 False 默认值。

    这为无法提供提供者元数据的调用者保留了原始的安全行为（e.g. 没有代理的未知别名
    model_info）。
    """
    assert get_features("deepseek-chat").supports_prompt_cache_key is False
    assert get_features("claude-opus-5-5").supports_prompt_cache_key is False


def test_provider_hint_does_not_leak_into_reasoning_effort():
    """提供者提示只能移动 prompt_cache_key，而不是 reasoning_effort。

    回归 #5332 评论测试：提供者范围的参数查找扩大了整个集合（对于 DeepSeek，它还报告
    ``reasoning_effort``）。 将其线程插入共享
    ``supported_params`` 翻转
    ``supports_reasoning_effort`` False -> True 对于 ``deepseek-chat``，这使得
    ``select_chat_options`` emit ``reasoning_effort`` 并去除采样参数。 解析
    prompt_cache_key 分别保
    存 reasoning_effort 在裸名集上，因此只有预期的能力移动。
    """
    features = get_features(
        "deepseek-chat", model_info={"litellm_provider": "deepseek"}
    )
    # prompt_cache_key 通过提供者提示恢复...
    assert features.supports_prompt_cache_key is True
    # ... but reasoning_effort stays on the unhinted bare-name lookup.
    assert features.supports_reasoning_effort is False


@pytest.mark.parametrize(
    "model,expected_retention",
    [
        ("gpt-5.1", True),
        ("openai/gpt-5.1-codex-mini", True),
        ("gpt-5", True),
        # 新的 GPT-5.2 系列应支持延长保留时间
        ("gpt-5.2", True),
        ("openai/gpt-5.2-chat-latest", True),
        ("openai/gpt-5.2-pro", True),
        ("openai/gpt-5-mini", False),
        ("gpt-4o", False),
        ("openai/gpt-4.1", True),
        ("azure/gpt-4.1", False),
        ("litellm/gpt-4.1", True),
        ("litellm_proxy/gpt-4.1", True),
        ("litellm_proxy/openai/gpt-4.1", True),
        ("litellm_proxy/openai/gpt-5", True),
        ("azure/gpt-5.1", False),
        ("litellm_proxy/openai/gpt-5-mini", False),
        ("openai/gpt-5.1-mini", False),
        ("openai/gpt-5-mini-2025-08-07", False),
    ],
)
def test_prompt_cache_retention_support(model, expected_retention):
    features = get_features(model)
    assert features.supports_prompt_cache_retention is expected_retention

    # 搭载此测试以验证 force_string_serializer 设置正确
    assert get_features("GLM-4.5").force_string_serializer is True
    # 与提供商无关的 Kimi 不应强制使用字符串序列化器
    assert get_features("Kimi K2-Instruct-0905").force_string_serializer is False
    # Groq 前缀的 Kimi 应该强制字符串序列化器
    assert get_features("groq/kimi-k2-instruct-0905").force_string_serializer is True


@pytest.mark.parametrize(
    "model,expected_send_reasoning",
    [
        ("kimi-k2-thinking", True),
        ("kimi-k2-thinking-0905", True),
        ("Kimi-K2-Thinking", True),  # 不区分大小写
        ("moonshot/kimi-k2-thinking", True),  # 带有提供商前缀的
        ("kimi-k3", True),
        ("Kimi-K3", True),  # 不区分大小写
        ("moonshot/kimi-k3", True),  # 带有提供商前缀的
        ("litellm_proxy/moonshot/kimi-k3", True),  # 通过代理
        ("kimi-k2.5", True),
        ("Kimi-K2.5", True),  # 不区分大小写
        # DeepSeek 推理机模型
        ("deepseek/deepseek-reasoner", True),
        ("DeepSeek/deepseek-reasoner", True),
        # DeepSeek V4 Pro（双模思维）
        ("deepseek/deepseek-v4-pro", True),
        ("litellm_proxy/deepseek/deepseek-v4-pro", True),
        # DeepSeek V4 Flash（双模思维）
        ("deepseek/deepseek-v4-flash", True),
        ("litellm_proxy/deepseek/deepseek-v4-flash", True),
        # 应不匹配的型号
        ("deepseek/deepseek-chat", False),  # 不同的 DeepSeek 型号
        ("kimi-k2-instruct", False),  # 不同的变体
        ("gpt-4o", False),
        ("claude-3-5-sonnet", False),
        ("o1", False),
        ("unknown-model", False),
    ],
)
def test_send_reasoning_content_support(model, expected_send_reasoning):
    """测试 kimi-k2-thinking 等模型是否需要 send_reasoning_content。"""
    features = get_features(model)
    assert features.send_reasoning_content is expected_send_reasoning
