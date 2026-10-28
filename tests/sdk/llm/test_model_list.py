import sys
from unittest.mock import patch

import litellm
from pydantic import SecretStr

from openhands.sdk.llm.utils.unverified_models import (
    _list_bedrock_foundation_models,
    get_supported_llm_models,
    get_unverified_models,
)
from openhands.sdk.llm.utils.verified_models import (
    VERIFIED_MODELS,
    VERIFIED_OPENAI_MODELS,
    VERIFIED_OPENHANDS_MODELS,
)


def test_organize_models_and_providers():
    models = [
        "openai/gpt-5.6",
        "anthropic/claude-sonnet-5",
        "gpt-5.3-codex",
        "gpt-6-astra",
        "devstral-2512",
        "mistral/devstral-2512",
        "anthropic.claude-3-5",  # 忽略 Anthropic 的点分隔符
        "unknown-model",
        "custom-provider/custom-model",  # 无效的提供者 -> 存储在“其他”下
        "us.anthropic.claude-3-5-sonnet-20241022-v2:0",  # 无效的提供商前缀
        "1024-x-1024/gpt-image-1.5",  # 无效的提供商前缀
        "openai/another-model",
    ]

    with patch(
        "openhands.sdk.llm.utils.unverified_models.get_supported_llm_models",
        return_value=models,
    ):
        result = get_unverified_models()

        assert "openai" in result
        assert "anthropic" not in result  # 不包括经过验证的模型
        assert "mistral" not in result
        assert "other" in result

        assert len(result["openai"]) == 1
        assert "another-model" in result["openai"]

        assert len(result["other"]) == 4
        assert "unknown-model" in result["other"]
        assert "custom-provider/custom-model" in result["other"]
        assert "us.anthropic.claude-3-5-sonnet-20241022-v2:0" in result["other"]
        assert "1024-x-1024/gpt-image-1.5" in result["other"]


def test_list_bedrock_models_without_boto3(monkeypatch):
    """如果 boto3 丢失，应该发出警告并返回空列表。"""
    # 假装boto3未安装
    monkeypatch.setitem(sys.modules, "boto3", None)

    # 模拟对象调用验证警告的记录器
    with patch("openhands.sdk.llm.utils.unverified_models.logger") as mock_logger:
        result = _list_bedrock_foundation_models("us-east-1", "key", "secret")

    assert result == []
    mock_logger.warning.assert_called_once_with(
        "boto3 is not installed. To use Bedrock models,"
        "install with: openhands-sdk[boto3]"
    )


def test_list_bedrock_models_with_boto3(monkeypatch):
    """如果存在 boto3，则应返回带前缀的基岩模型 ID。"""

    class FakeClient:
        def list_foundation_models(self, **kwargs):
            return {"modelSummaries": [{"modelId": "anthropic.claude-3"}]}

    class FakeBoto3:
        def client(self, *args, **kwargs):
            return FakeClient()

    # 注入假boto3
    monkeypatch.setitem(sys.modules, "boto3", FakeBoto3())

    result = _list_bedrock_foundation_models("us-east-1", "key", "secret")

    assert result == ["bedrock/anthropic.claude-3"]


def test_openhands_models_all_have_provider_list():
    """VERIFIED_OPENHANDS_MODELS 中的每个模型还必须至少出现在一个
    特定于提供者的列表，以便 UI 可以在其实际提供者下显示它。

    Exception: 仅可通过 OpenHands 提供商获得的模型
    (e.g. ``trinity-large-thinking``) 不会暴露在任何其他提供商之下。
    """
    openhands_only_models = {"trinity-large-thinking"}

    provider_models = set()
    for provider, models in VERIFIED_MODELS.items():
        if provider == "openhands":
            continue
        provider_models.update(models)

    missing = [
        m
        for m in VERIFIED_OPENHANDS_MODELS
        if m not in provider_models and m not in openhands_only_models
    ]
    assert not missing, (
        f"Models in VERIFIED_OPENHANDS_MODELS missing from any provider list: {missing}"
    )


def test_gpt_5_6_models_are_verified_for_openai():
    assert {
        "gpt-5.6",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-6-astra",
    }.issubset(VERIFIED_OPENAI_MODELS)


def test_kimi_k3_and_claude_opus_5_are_verified():
    assert "kimi-k3" in VERIFIED_MODELS["moonshot"]
    assert "kimi-k3" in VERIFIED_OPENHANDS_MODELS
    assert "claude-opus-5" in VERIFIED_MODELS["anthropic"]
    assert "claude-opus-5" in VERIFIED_OPENHANDS_MODELS


def test_openrouter_is_a_verified_provider():
    """OpenRouter 必须是经过验证的提供商（与 openai/openhands 一起），因此
    提供商选择器将其显示为已在本地后端验证。 它的条目是带有命名空间的 id，并且去掉了
    ``openrouter/`` 前缀。
    """
    assert "openrouter" in VERIFIED_MODELS
    # 选择器将 VERIFIED_MODELS 中的任何键视为经过验证的提供者，因此 OpenRouter 部分需要
    # 一个非空列表来渲染模型。
    #
    assert VERIFIED_MODELS["openrouter"]
    assert "anthropic/claude-opus-5" in VERIFIED_MODELS["openrouter"]
    assert "openai/gpt-6-astra" in VERIFIED_MODELS["openrouter"]
    # 条目必须是真实的目录 ID（没有像 ``openai/gpt-5.6`` 这样的仅别名 ID）。
    assert "openai/gpt-5.6-sol" in VERIFIED_MODELS["openrouter"]
    # 条目不得带有 openrouter/ 前缀（它是提供商密钥）。
    assert not any(m.startswith("openrouter/") for m in VERIFIED_MODELS["openrouter"])


def test_openrouter_models_remain_discoverable_without_litellm_catalog(monkeypatch):
    monkeypatch.setattr(
        litellm,
        "model_list",
        ["deepseek/deepseek-chat", "bedrock/anthropic.claude-3"],
    )
    monkeypatch.setattr(litellm, "model_cost", {})

    models = get_supported_llm_models()

    assert "openrouter/deepseek/deepseek-chat" in models
    assert "deepseek/deepseek-chat" in models
    assert "bedrock/anthropic.claude-3" not in models
    assert "openrouter/openai/gpt-5.6" not in models
    assert "openrouter" not in get_unverified_models()


def test_bedrock_ids_without_bedrock_prefix_are_excluded(monkeypatch):
    """LiteLLM 在基岩下文件基岩 ID，例如 ``deepseek.r1-v1:0``
    提供者； 它们不得像其他提供商的型号一样泄漏到列表中。"""
    monkeypatch.setattr(litellm, "model_list", ["deepseek/deepseek-chat"])
    monkeypatch.setattr(
        litellm,
        "model_cost",
        {
            "deepseek.r1-v1:0": {"litellm_provider": "bedrock_converse"},
            "anthropic.claude-v2:1": {"litellm_provider": "bedrock"},
            "us.anthropic.claude-3-5-haiku-20241022-v1:0": {
                "litellm_provider": "bedrock_converse"
            },
            "bedrock_mantle/openai.gpt-oss-120b": {
                "litellm_provider": "bedrock_mantle"
            },
            "deepseek/deepseek-chat": {"litellm_provider": "deepseek"},
            "claude-3-5-haiku-20241022": {"litellm_provider": "anthropic"},
        },
    )

    models = get_supported_llm_models()

    assert "deepseek/deepseek-chat" in models
    assert "claude-3-5-haiku-20241022" in models
    assert not any(".claude-" in m or m.startswith("deepseek.") for m in models)
    assert not any(m.startswith("bedrock") for m in models)


def test_bedrock_models_from_aws_are_kept_when_credentials_are_set(monkeypatch):
    monkeypatch.setattr(litellm, "model_list", [])
    monkeypatch.setattr(
        litellm,
        "model_cost",
        {"deepseek.r1-v1:0": {"litellm_provider": "bedrock_converse"}},
    )
    with patch(
        "openhands.sdk.llm.utils.unverified_models._list_bedrock_foundation_models",
        return_value=["bedrock/deepseek.r1-v1:0"],
    ):
        models = get_supported_llm_models(
            "us-east-1", SecretStr("key"), SecretStr("secret")
        )

    assert "bedrock/deepseek.r1-v1:0" in models
    assert "deepseek.r1-v1:0" not in models


def test_nemotron_3_super_uses_full_infra_name():
    """已验证的 Nemotron Super 条目必须与基础型号名称匹配
    (``nemotron-3-super-120b-a12b``) 和短别名不应列出。
    """
    full_name = "nemotron-3-super-120b-a12b"
    assert full_name in VERIFIED_MODELS["nvidia"]
    assert full_name in VERIFIED_OPENHANDS_MODELS
    for provider, models in VERIFIED_MODELS.items():
        assert "nemotron-3-super" not in models, (
            f"Short alias 'nemotron-3-super' should not be in provider {provider!r}"
        )


def test_openhands_haiku_uses_full_infra_name():
    """OpenHands 代理为某些 Anthropic 模型提供过时的快照
    (``claude-haiku-4-5-20251001``); 代理不知道的裸别名不得在 OpenHands 提供程序下提
    供。
    """
    assert "claude-haiku-4-5" not in VERIFIED_OPENHANDS_MODELS
    # VERIFIED_ANTHROPIC_MODELS 保留带日期的名称； 直接-Anthropic BYOK 就可以了。
    assert "claude-haiku-4-5-20251001" in VERIFIED_MODELS["anthropic"]


def test_verified_lists_keep_two_latest_versions_per_line():
    """检查每个提供商的管理规则：一个的两个最新版本
    行存在，并且之前的版本消失（请参阅模块文档字符串和 ``llm/utils/AGENTS.md``）。 当
    新版本发布时更新该表。
    """
    expectations = {
        "openai": ({"gpt-6-astra", "gpt-5.6"}, {"gpt-5.5", "gpt-5.4", "gpt-4o", "o3"}),
        "anthropic": (
            {
                "claude-opus-5-5",
                "claude-opus-5",
                "claude-sonnet-5-5",
                "claude-sonnet-5",
                "claude-haiku-5-5",
            },
            {"claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-4-6"},
        ),
        "mistral": (
            {"devstral-2512", "devstral-medium-2512"},
            {"devstral-medium-2507"},
        ),
        "gemini": ({"gemini-4-argon", "gemini-3.8-flash"}, {"gemini-3.6-flash"}),
        "deepseek": ({"deepseek-v4-pro", "deepseek-v3.2-reasoner"}, set()),
        "moonshot": ({"kimi-k3", "kimi-k2.7-code"}, {"kimi-k2.6"}),
        "minimax": (
            {"minimax-m3.1-flash", "minimax-m3", "minimax-m2.7"},
            {"minimax-m2.5"},
        ),
        "glm": ({"glm-5.3", "glm-5.2"}, {"glm-5.1"}),
        "nvidia": ({"nemotron-3.5-lightning-30b-a3b", "nemotron-3-nano"}, set()),
        "qwen": ({"qwen3.8-max", "qwen3.7-max"}, {"qwen3-max", "qwen3-6-plus"}),
        # OpenRouter 路由其他供应商的模型，因此条目是命名空间 id (
        # ``anthropic/claude-opus-5``)，而不是裸露的模型名称。
        #
        "openrouter": (
            {"anthropic/claude-opus-5", "openai/gpt-6-astra"},
            {"anthropic/claude-opus-4-7"},
        ),
        "digitalocean": (
            {"anthropic-claude-opus-5.5", "anthropic-claude-opus-5"},
            {"anthropic-claude-opus-4.8", "openai-gpt-6-astra"},
        ),
    }
    assert set(expectations) == set(VERIFIED_MODELS) - {"openhands"}
    for provider, (present, absent) in expectations.items():
        models = set(VERIFIED_MODELS[provider])
        assert present <= models, f"{provider}: missing {present - models}"
        assert not (absent & models), f"{provider}: stale {absent & models}"
    assert {"gpt-6-astra", "gpt-5.6", "claude-opus-5-5", "claude-opus-5"} <= set(
        VERIFIED_OPENHANDS_MODELS
    )
    assert not {"gpt-5.5", "claude-opus-4-8", "claude-opus-4-7", "minimax-m2.5"} & set(
        VERIFIED_OPENHANDS_MODELS
    )


def test_trinity_model_is_openhands_only():
    """trinity-large-thinking 只能通过 OpenHands 提供者获得
    并且不得列在任何其他提供商下。
    """
    assert "trinity-large-thinking" in VERIFIED_OPENHANDS_MODELS
    assert "trinity" not in VERIFIED_MODELS
    for provider, models in VERIFIED_MODELS.items():
        if provider == "openhands":
            continue
        assert "trinity-large-thinking" not in models, (
            f"trinity-large-thinking should not be in provider list {provider!r}"
        )
