"""测试 LiteLLM 代理 /v1/model/info 查找。

重点关注从代理响应中选择正确条目的匹配器。 代理接受由公共别名(`model_name`)或底层提供
者标识(`litellm_params.model`)发出的请求，以及S
DK's model_info查找必须相同——否则`model_info`设置在代理上的e.g将被覆盖。
`supports_vision: true` 对于模型
LiteLLM 还不知道上游）默默地无法到达客户端。

请参阅问题：LiteLLM proxy model_info 当代理使用短别名时查找会丢失（claude-opus-4-8 视
觉仍然关闭）。
"""

from unittest.mock import patch

import litellm
from litellm import model_cost

from openhands.sdk.llm.utils.model_info import (
    _get_model_info_from_litellm_proxy,
    _merge_raw_model_metadata,
    _register_proxy_alias_pricing,
    get_litellm_model_info,
)


_PROXY_RESPONSE = {
    "data": [
        # 别名条目：短公共名称、提供者前缀的基础 ID，加上 model_info 覆盖（促成此修复的
        # 情况）。
        #
        {
            "model_name": "claude-opus-4-8",
            "litellm_params": {"model": "anthropic/claude-opus-4-8"},
            "model_info": {"supports_vision": True},
        },
        # 普通条目：别名与提供商 ID 逐字匹配。
        {
            "model_name": "openrouter/some-model",
            "litellm_params": {"model": "openrouter/some-model"},
            "model_info": {"supports_vision": False},
        },
    ]
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _patched_httpx_get(*_a, **_kw):
    return _FakeResponse(_PROXY_RESPONSE)


def setup_function(_):
    # `_get_model_info_from_litellm_proxy` 是 lru_cached； 测试之间是清晰的，因此
    # cache_key 跨测试的重用不会掩盖行为。
    #
    _get_model_info_from_litellm_proxy.cache_clear()


def test_lookup_matches_by_model_name_alias():
    """现有行为：通过代理的公共别名来寻址。"""
    with patch("openhands.sdk.llm.utils.model_info.httpx.get", _patched_httpx_get):
        info = _get_model_info_from_litellm_proxy(
            secret_api_key="k",
            base_url="https://proxy.example",
            model="litellm_proxy/claude-opus-4-8",
            cache_key=1,
        )
    assert info == {"supports_vision": True}


def test_lookup_matches_by_litellm_params_model():
    """新行为：通过底层提供商 ID (`anthropic/...`) 进行寻址。

    这正是导致 `claude-opus-4-8` 目标检测失败的原因：代理暴露了模型为别名
    `claude-opus-4-8`，但 SDK 配置为
    `litellm_proxy/anthropic/claude-opus-4-8`，所以前缀匹配器（只检查 `model_name`）
    没有发现。
    """
    with patch("openhands.sdk.llm.utils.model_info.httpx.get", _patched_httpx_get):
        info = _get_model_info_from_litellm_proxy(
            secret_api_key="k",
            base_url="https://proxy.example",
            model="litellm_proxy/anthropic/claude-opus-4-8",
            cache_key=2,
        )
    assert info == {"supports_vision": True}


def test_lookup_returns_none_for_unknown_model():
    with patch("openhands.sdk.llm.utils.model_info.httpx.get", _patched_httpx_get):
        info = _get_model_info_from_litellm_proxy(
            secret_api_key="k",
            base_url="https://proxy.example",
            model="litellm_proxy/anthropic/not-a-real-model",
            cache_key=3,
        )
    assert info is None


def test_get_litellm_model_info_uses_proxy_match_for_provider_prefixed_id():
    """端到端：`get_litellm_model_info` 返回代理覆盖
    即使代理通告较短的别名，SDK 也会配置为提供者前缀 id。
    """
    with patch("openhands.sdk.llm.utils.model_info.httpx.get", _patched_httpx_get):
        info = get_litellm_model_info(
            secret_api_key="k",
            base_url="https://proxy.example",
            model="litellm_proxy/anthropic/claude-opus-4-8",
        )
    assert info is not None
    assert info.get("supports_vision") is True


def test_get_litellm_model_info_uses_proxy_for_openhands_provider_model():
    with patch("openhands.sdk.llm.utils.model_info.httpx.get", _patched_httpx_get):
        info = get_litellm_model_info(
            secret_api_key="k",
            base_url=None,
            model="openhands/claude-opus-4-8",
        )
    assert info is not None
    assert info.get("supports_vision") is True


def test_raw_registry_capabilities_survive_typed_model_info_projection():
    raw = {
        "future-model": {
            "supports_adaptive_thinking": True,
            "supports_sampling_params": False,
        }
    }
    with patch.dict("openhands.sdk.llm.utils.model_info.model_cost", raw, clear=True):
        info = _merge_raw_model_metadata(
            {"key": "future-model", "supports_reasoning": True}
        )

    assert info["supports_reasoning"] is True
    assert info["supports_adaptive_thinking"] is True
    assert info["supports_sampling_params"] is False


# --- 别名定价注册（问题#4816）---

# 每个测试都使用一个独特的自定义别名，因此 LiteLLM 的内部缓存（即使别名被从 `model_cost`
#  中移除后，也能记住之前注册的别名并将其标记为可定价）不能污染后续测试的价格可得性检查
# 。
#
_UNDERLYING = "claude-sonnet-4-5-20250929"


def _pop(alias):
    model_cost.pop(alias, None)


def test_register_proxy_alias_makes_alias_priceable():
    """注册自定义别名会将 cost_per_token 从提升翻转为一个值。"""
    alias = "prod/claude-sonnet-4-5-bedrock-a"
    _pop(alias)
    # 理智：别名在注册前不定价。
    try:
        litellm.cost_per_token(model=alias, prompt_tokens=1, completion_tokens=1)
        pre_raises = False
    except Exception:
        pre_raises = True
    assert pre_raises

    underlying = model_cost[_UNDERLYING]
    _register_proxy_alias_pricing(
        alias=alias,
        underlying_model_info=underlying,
        proxy_model_info=None,
    )
    cost = (0.0, 0.0)
    try:
        cost = litellm.cost_per_token(
            model=alias, prompt_tokens=100, completion_tokens=50
        )
        post_raises = False
    except Exception:
        post_raises = True

    assert not post_raises
    # (prompt_cost, completion_cost); 两者都必须非零。
    assert cost[0] > 0
    assert cost[1] > 0
    _pop(alias)


def test_register_proxy_alias_skips_already_priceable_models():
    """提供者前缀的真实模型本身就是昂贵的； 不要破坏。"""
    alias = "anthropic/claude-sonnet-4-5-20250929"
    before = dict(model_cost.get(alias, {}))
    _register_proxy_alias_pricing(
        alias=alias,
        underlying_model_info=model_cost[_UNDERLYING],
        proxy_model_info={"input_cost_per_token": 999},
    )
    # 条目未更改：注册被跳过。
    assert model_cost.get(alias, {}) == before


def test_register_proxy_proxy_overrides_win():
    """代理端定价优先于基础模型。"""
    alias = "prod/claude-sonnet-4-5-bedrock-b"
    _pop(alias)
    underlying = model_cost[_UNDERLYING]
    override = {"input_cost_per_token": 1.0, "output_cost_per_token": 2.0}
    _register_proxy_alias_pricing(
        alias=alias,
        underlying_model_info=underlying,
        proxy_model_info=override,
    )
    entry = model_cost[alias]
    assert entry["input_cost_per_token"] == 1.0
    assert entry["output_cost_per_token"] == 2.0
    # 底层缓存/最大/提供者字段仍然保留。
    assert entry["litellm_provider"] == underlying["litellm_provider"]
    _pop(alias)


def test_register_proxy_alias_bedrock_converse_provider_normalized():
    """bedrock_converse 提供商标签必须标准化为基岩。

    ``get_llm_provider`` 仅针对 LiteLLM 的内置 bedrock_converse 集中已存在的模型 ID
    解析
    ``bedrock_converse``； 具有该标签的未知别名 id 会升高，从而使跨度的价格为 0 美元
    。 注册``bedrock``使得
    ``cost_per_token`` 无需显式 ``custom_llm_provider`` 即可解析 (#4836)。
    """
    alias = "prod/claude-sonnet-4-5-bedrock-e"
    _pop(alias)
    # 理智：别名在注册前不定价。

    try:
        litellm.cost_per_token(model=alias, prompt_tokens=1, completion_tokens=1)
        pre_raises = False
    except Exception:
        pre_raises = True
    assert pre_raises

    # 代理端点 ``bedrock_converse`` (合并入口的 Anthropic-on-Bedrock 路径) 本应覆盖底层
    # 提供者。
    #

    underlying = model_cost["us.anthropic.claude-sonnet-4-5-20250929-v1:0"]
    assert underlying["litellm_provider"] == "bedrock_converse"
    _register_proxy_alias_pricing(
        alias=alias,
        underlying_model_info=underlying,
        proxy_model_info={"litellm_provider": "bedrock_converse"},
    )
    assert model_cost[alias]["litellm_provider"] == "bedrock"
    cost = (0.0, 0.0)
    try:
        cost = litellm.cost_per_token(
            model=alias, prompt_tokens=100, completion_tokens=50
        )
        post_raises = False
    except Exception:
        post_raises = True
    assert not post_raises
    assert cost[0] > 0
    assert cost[1] > 0
    _pop(alias)


def test_register_proxy_alias_no_pricing_logs_and_skips():
    """当无法得出定价时，别名将保持未注册状态（没有 $0 条目）。"""
    alias = "prod/claude-sonnet-4-5-bedrock-c"
    _pop(alias)
    _register_proxy_alias_pricing(
        alias=alias,
        underlying_model_info=None,
        proxy_model_info={"supports_vision": True},
    )
    assert alias not in model_cost


def test_get_model_info_from_proxy_registers_alias_pricing():
    """端到端：获取代理模型信息将别名注册到model_cost中。"""
    alias = "prod/claude-sonnet-4-5-bedrock-d"
    _pop(alias)
    proxy_response = {
        "data": [
            {
                "model_name": alias,
                "litellm_params": {"model": _UNDERLYING},
                "model_info": {"supports_vision": True},
            }
        ]
    }
    with patch(
        "openhands.sdk.llm.utils.model_info.httpx.get",
        lambda *_a, **_kw: _FakeResponse(proxy_response),
    ):
        _get_model_info_from_litellm_proxy.cache_clear()
        _get_model_info_from_litellm_proxy(
            secret_api_key="k",
            base_url="https://proxy.example",
            model=f"litellm_proxy/{alias}",
            cache_key=42,
        )
    assert alias in model_cost
    try:
        cost = litellm.cost_per_token(
            model=alias, prompt_tokens=100, completion_tokens=50
        )
    except Exception:
        cost = None
    assert cost is not None and cost[0] > 0
    _pop(alias)
