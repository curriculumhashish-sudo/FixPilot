from dataclasses import dataclass, field
from typing import Any

import pytest
from litellm import get_optional_params

from openhands.sdk.llm import LLM, LLMCallContext
from openhands.sdk.llm.call_context import llm_call_context_scope
from openhands.sdk.llm.options.chat_options import select_chat_options
from openhands.sdk.llm.utils.model_features import ModelFeatures, get_features


@dataclass
class DummyLLM:
    model: str
    base_url: str | None = None
    model_canonical_name: str | None = None
    model_info: dict[str, Any] | None = None
    capability_overrides: dict[str, bool | str] = field(default_factory=dict)
    top_k: int | None = None
    top_p: float | None = 1.0
    temperature: float | None = 0.0
    max_output_tokens: int = 1024
    extra_headers: dict[str, str] | None = None
    reasoning_effort: str | None = None
    extended_thinking_budget: int | None = None
    litellm_extra_body: dict[str, Any] | None = None
    # 与LLM默认对齐； 仅针对支持它的型号发出
    prompt_cache_retention: str | None = "24h"
    openrouter_site_url: str = ""
    openrouter_app_name: str = ""

    def _openrouter_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.openrouter_site_url:
            headers["HTTP-Referer"] = self.openrouter_site_url
        if self.openrouter_app_name:
            headers["X-Title"] = self.openrouter_app_name
        return headers

    def _model_name_for_capabilities(self) -> str:
        return self.model_canonical_name or self.model

    def _model_features(self) -> ModelFeatures:
        return get_features(
            self._model_name_for_capabilities(),
            model_info=self.model_info,
            overrides=self.capability_overrides,
        )

    @property
    def effective_max_output_tokens(self) -> int:
        return self.max_output_tokens


def test_opus_4_5_uses_reasoning_effort_and_strips_temp_top_p():
    llm = DummyLLM(
        model="claude-opus-4-5-20251101",
        top_p=0.9,
        temperature=0.7,
        reasoning_effort="medium",
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    # LiteLLM 自动将 reasoning_effort 映射到 output_config
    assert out.get("reasoning_effort") == "medium"
    assert "output_config" not in out

    # LiteLLM 自动添加所需的 beta 标头
    assert "extra_headers" not in out or "anthropic-beta" not in out.get(
        "extra_headers", {}
    )

    # 剥离温度/top_p用于推理模型
    assert "temperature" not in out
    assert "top_p" not in out


def test_gpt5_uses_reasoning_effort_and_strips_temp_top_p():
    llm = DummyLLM(
        model="gpt-5-mini-2025-08-07",
        temperature=0.5,
        top_p=0.8,
        reasoning_effort="high",
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert out.get("reasoning_effort") == "high"
    assert "output_config" not in out
    headers = out.get("extra_headers") or {}
    assert "anthropic-beta" not in headers
    assert "temperature" not in out
    assert "top_p" not in out


def test_kimi_k2_thinking_does_not_send_reasoning_effort():
    llm = DummyLLM(
        model="litellm_proxy/moonshot/kimi-k2-thinking",
        temperature=1.0,
        reasoning_effort="high",
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert "reasoning_effort" not in out
    assert out.get("temperature") == 1.0


def test_kimi_k3_uses_reasoning_effort_and_strips_temp_top_p():
    llm = DummyLLM(
        model="litellm_proxy/moonshot/kimi-k3",
        temperature=1.0,
        top_p=0.9,
        reasoning_effort="high",
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert out.get("reasoning_effort") == "high"
    assert "temperature" not in out
    assert "top_p" not in out


def test_gemini_2_5_pro_without_reasoning_effort_preserves_temp_and_top_p():
    llm = DummyLLM(model="gemini-2.5-pro", reasoning_effort=None)
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert "reasoning_effort" not in out
    assert out.get("temperature") == 0.0
    assert out.get("top_p") == 1.0


def test_non_reasoning_model_preserves_temp_and_top_p():
    llm = DummyLLM(model="gpt-4o", temperature=0.6, top_p=0.7)
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    # 非推理模型应保留温度/top_p 默认值
    assert out.get("temperature") == 0.6
    assert out.get("top_p") == 0.7


def test_azure_renames_max_completion_tokens_to_max_tokens():
    llm = DummyLLM(model="azure/gpt-4o")
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert "max_completion_tokens" not in out
    assert out.get("max_tokens") == llm.max_output_tokens


def test_tools_removed_when_has_tools_false():
    llm = DummyLLM(model="gpt-4o")
    uk = {"tools": ["t1"], "tool_choice": "auto"}
    out = select_chat_options(llm, user_kwargs=uk, has_tools=False)

    assert "tools" not in out
    assert "tool_choice" not in out


def test_extra_body_is_forwarded():
    llm = DummyLLM(model="gpt-4o", litellm_extra_body={"x": 1})
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert out.get("extra_body") == {"x": 1}


def test_claude_sonnet_4_6_strips_temp_and_top_p():
    """测试 claude-sonnet-4-6 剥离温度和 top_p。

    这是针对问题 #2137 的回归测试，其中 Claude Sonnet 4.6 拒绝指定温度 AND top_p 的请
    求。
    """
    llm = DummyLLM(
        model="claude-sonnet-4-6",
        model_info={
            "supports_reasoning": True,
            "supports_adaptive_thinking": True,
        },
        top_p=1.0,  # SDK 默认
        temperature=0.1,  # 经常被基准测试覆盖
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    # 扩展思维模型应该去除温度/top_p以避免API错误
    assert "temperature" not in out
    assert "top_p" not in out
    assert "thinking" not in out
    assert "anthropic-beta" not in out.get("extra_headers", {})


def test_claude_sonnet_5_uses_metadata_backed_adaptive_thinking_contract():
    llm = DummyLLM(
        model="anthropic/claude-sonnet-5",
        top_k=40,
        top_p=0.9,
        temperature=0.7,
        reasoning_effort="max",
        extended_thinking_budget=20_000,
        model_info={
            "litellm_provider": "anthropic",
            "supports_reasoning": True,
            "supports_adaptive_thinking": True,
            "supports_sampling_params": False,
            "supports_prompt_caching": True,
        },
    )

    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert out["reasoning_effort"] == "max"
    assert "thinking" not in out
    assert "anthropic-beta" not in out.get("extra_headers", {})
    assert "temperature" not in out
    assert "top_p" not in out
    assert "top_k" not in out


def test_chat_options_resolve_capabilities_from_canonical_alias():
    llm = DummyLLM(
        model="litellm_proxy/customer-sonnet",
        model_canonical_name="anthropic/claude-sonnet-5",
        temperature=0.7,
        reasoning_effort="high",
        model_info={
            "supports_reasoning": True,
            "supports_adaptive_thinking": True,
            "supports_sampling_params": False,
        },
    )

    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert out["reasoning_effort"] == "high"
    assert "temperature" not in out
    assert "thinking" not in out


def test_chat_options_sampling_override_takes_precedence():
    llm = DummyLLM(
        model="litellm_proxy/future-reasoning-model",
        model_canonical_name="anthropic/claude-sonnet-5",
        top_k=40,
        top_p=0.9,
        temperature=0.7,
        reasoning_effort="high",
        model_info={
            "supports_reasoning": True,
            "supports_adaptive_thinking": True,
        },
        capability_overrides={"supports_sampling_params": True},
    )

    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert out["temperature"] == 0.7
    assert out["top_p"] == 0.9
    assert out["top_k"] == 40
    assert out["reasoning_effort"] == "high"


@pytest.mark.parametrize(
    "model,provider",
    [
        ("claude-sonnet-5", "anthropic"),
        ("us.anthropic.claude-sonnet-5-v1:0", "bedrock"),
        ("claude-opus-5", "anthropic"),
        ("us.anthropic.claude-opus-5-v1:0", "bedrock"),
    ],
)
def test_litellm_translates_claude_5_reasoning_to_adaptive_thinking(
    model: str, provider: str
):
    params = get_optional_params(
        model=model,
        custom_llm_provider=provider,
        reasoning_effort="high",
    )

    assert params["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in params["thinking"]


def test_bedrock_opus_4_8_strips_temp_top_p_without_thinking_block():
    llm = DummyLLM(
        model="bedrock/us.anthropic.claude-opus-4-8-v1:0",
        top_p=1.0,  # SDK 默认
        temperature=0.0,  # 经常被基准测试 (e.g. SWE-长凳）
        reasoning_effort="high",
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    assert "temperature" not in out
    assert "top_p" not in out
    assert out.get("reasoning_effort") == "high"
    # 必须不走传统的扩展思维道路。
    assert "thinking" not in out
    assert "anthropic-beta" not in out.get("extra_headers", {})


def test_extended_thinking_budget_clamped_below_max_tokens():
    """测试 thinking.budget_tokens 是否被钳位到 max_output_tokens - 1。"""
    # 情况1：extended_thinking_budget超过max_output_tokens
    llm = DummyLLM(
        model="claude-sonnet-4-5-20250929",
        max_output_tokens=1000,
        extended_thinking_budget=2000,
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    # budget_tokens 应限制为 max_output_tokens - 1 = 999
    assert out.get("thinking") == {
        "type": "enabled",
        "budget_tokens": 999,
    }
    assert out.get("max_tokens") == 1000

    # 情况2：extended_thinking_budget等于max_output_tokens
    llm = DummyLLM(
        model="claude-sonnet-4-5-20250929",
        max_output_tokens=1000,
        extended_thinking_budget=1000,
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    # budget_tokens 应限制为 max_output_tokens - 1 = 999
    assert out.get("thinking") == {
        "type": "enabled",
        "budget_tokens": 999,
    }
    assert out.get("max_tokens") == 1000

    # 情况 3：extended_thinking_budget 已经低于 max_output_tokens
    llm = DummyLLM(
        model="claude-sonnet-4-5-20250929",
        max_output_tokens=1000,
        extended_thinking_budget=500,
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)

    # budget_tokens 应保持原样
    assert out.get("thinking") == {
        "type": "enabled",
        "budget_tokens": 500,
    }
    assert out.get("max_tokens") == 1000


def test_chat_options_forwards_prompt_cache_key_when_set():
    """回归测试 #2904。"""
    llm = LLM(model="gpt-4o")
    assert (
        select_chat_options(
            llm,
            user_kwargs={},
            has_tools=True,
            call_context=LLMCallContext(prompt_cache_key="conv-abc123"),
        ).get("prompt_cache_key")
        == "conv-abc123"
    )


def test_chat_options_omits_prompt_cache_key_when_unset():
    llm = LLM(model="gpt-4o")
    assert "prompt_cache_key" not in select_chat_options(
        llm, user_kwargs={}, has_tools=True
    )


def test_chat_options_omits_prompt_cache_key_for_unsupported_provider():
    """人择/双子拒绝 `prompt_cache_key` 为 400； 不得发送。

    回归在 `drop_params: false` 的 LiteLLM 代理上运行时，对 Anthropic 模型上报告的
    UnsupportedParamsError 进行测试。 该参数是 OpenAI 特定的，并且必须受到提供者支持
    的限制，这与
    `supports_prompt_cache` 门控 Anthropic `cache_control` 断点。
    """
    for model in ("claude-opus-4-5-20251101", "gemini/gemini-2.5-pro"):
        llm = DummyLLM(model=model)
        with llm_call_context_scope(LLMCallContext(prompt_cache_key="conv-abc123")):
            out = select_chat_options(llm, user_kwargs={}, has_tools=True)
        assert "prompt_cache_key" not in out, model


def test_chat_options_forwards_prompt_cache_key_when_override_enabled():
    """功能覆盖可以强制 `prompt_cache_key` 打开以解决未解决的问题
    OpenAI 代理别名，LiteLLM's 注册表返回无支持参数。"""
    llm = DummyLLM(
        model="prod/my-openai-alias",
        capability_overrides={"supports_prompt_cache_key": True},
    )
    with llm_call_context_scope(LLMCallContext(prompt_cache_key="conv-abc123")):
        out = select_chat_options(llm, user_kwargs={}, has_tools=True)
    assert out.get("prompt_cache_key") == "conv-abc123"


def test_chat_options_injects_openrouter_headers_via_extra_headers():
    """OpenRouter 站点/应用程序必须按调用流动（问题#3138），而不是通过环境。"""
    llm = DummyLLM(
        model="openrouter/anthropic/claude-3-5-sonnet",
        openrouter_site_url="https://app.example.com/",
        openrouter_app_name="ExampleApp",
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=False)
    assert out["extra_headers"]["HTTP-Referer"] == "https://app.example.com/"
    assert out["extra_headers"]["X-Title"] == "ExampleApp"


def test_chat_options_user_extra_headers_win_over_openrouter_defaults():
    """用户提供的 extra_headers 必须覆盖每次调用的 OpenRouter 值。"""
    llm = DummyLLM(
        model="openrouter/anthropic/claude-3-5-sonnet",
        openrouter_site_url="https://app.example.com/",
        openrouter_app_name="ExampleApp",
        extra_headers={"X-Title": "UserOverride"},
    )
    out = select_chat_options(llm, user_kwargs={}, has_tools=False)
    assert out["extra_headers"]["X-Title"] == "UserOverride"
    # 站点 URL 仍然被注入，因为用户没有覆盖它
    assert out["extra_headers"]["HTTP-Referer"] == "https://app.example.com/"


def test_chat_options_omits_openrouter_headers_when_unset():
    """空网站/应用程序不得添加 extra_headers。"""
    llm = DummyLLM(model="gpt-4o")
    out = select_chat_options(llm, user_kwargs={}, has_tools=False)
    assert "extra_headers" not in out


def test_chat_options_sends_openrouter_session_id_for_affinity():
    """OpenRouter 键粘性路由关闭 `session_id`（问题#6164）。

    没有它，路由键就从消息的开头推导出来，智能体会重写这些消息，导致后续消息丢失温暖
    缓存。
    """
    llm = DummyLLM(model="openrouter/meta/muse-glimmer-30b")
    out = select_chat_options(
        llm,
        user_kwargs={},
        has_tools=True,
        call_context=LLMCallContext(session_id="conv-abc123"),
    )
    assert out["extra_body"]["session_id"] == "conv-abc123"
    # LiteLLM-内部跟踪标头与关联参数一起保留。
    assert out["extra_headers"]["x-litellm-session-id"] == "conv-abc123"


def test_chat_options_sends_openrouter_session_id_from_scope():
    """环境对话范围达到 OpenRouter 亲和力参数。"""
    llm = DummyLLM(model="openrouter/meta/muse-glimmer-30b")
    with llm_call_context_scope(LLMCallContext(session_id="conv-scoped")):
        out = select_chat_options(llm, user_kwargs={}, has_tools=True)
    assert out["extra_body"]["session_id"] == "conv-scoped"


def test_chat_options_sends_openrouter_session_id_from_base_url():
    """带有 openrouter.ai 基 URL 的裸 OpenRouter 模型 ID 也符合资格。"""
    llm = DummyLLM(model="meta/muse-glimmer-30b")
    llm.base_url = "https://openrouter.ai/api/v1"
    out = select_chat_options(
        llm,
        user_kwargs={},
        has_tools=True,
        call_context=LLMCallContext(session_id="conv-base-url"),
    )
    assert out["extra_body"]["session_id"] == "conv-base-url"


def test_chat_options_preserves_openrouter_provider_routing():
    """关联性必须合并到而不是取代调用者提供的路由。"""
    llm = DummyLLM(
        model="openrouter/meta/muse-glimmer-30b",
        litellm_extra_body={
            "provider": {"only": ["deepinfra"], "allow_fallbacks": False}
        },
    )
    out = select_chat_options(
        llm,
        user_kwargs={},
        has_tools=True,
        call_context=LLMCallContext(session_id="conv-abc123"),
    )
    assert out["extra_body"]["session_id"] == "conv-abc123"
    assert out["extra_body"]["provider"] == {
        "only": ["deepinfra"],
        "allow_fallbacks": False,
    }


def test_chat_options_explicit_session_id_wins_over_conversation_id():
    """呼叫者提供的关联 ID 不会被对话 ID 覆盖。"""
    llm = DummyLLM(
        model="openrouter/meta/muse-glimmer-30b",
        litellm_extra_body={"session_id": "caller-chosen"},
    )
    out = select_chat_options(
        llm,
        user_kwargs={},
        has_tools=True,
        call_context=LLMCallContext(session_id="conv-abc123"),
    )
    assert out["extra_body"]["session_id"] == "caller-chosen"


def test_chat_options_omits_openrouter_session_id_for_other_providers():
    """非 OpenRouter 提供者不得接收仅限 OpenRouter 的字段。"""
    for model in ("gpt-4o", "claude-opus-4-5-20251101", "gemini/gemini-2.5-pro"):
        llm = DummyLLM(model=model)
        out = select_chat_options(
            llm,
            user_kwargs={},
            has_tools=True,
            call_context=LLMCallContext(session_id="conv-abc123"),
        )
        assert "extra_body" not in out or "session_id" not in out.get(
            "extra_body", {}
        ), model


def test_chat_options_omits_openrouter_session_id_when_no_session():
    """没有对话 ID 意味着没有亲和力参数，即使在 OpenRouter 上也是如此。"""
    llm = DummyLLM(model="openrouter/meta/muse-glimmer-30b")
    out = select_chat_options(llm, user_kwargs={}, has_tools=True)
    assert "extra_body" not in out or "session_id" not in out.get("extra_body", {})
