"""测试联合输入/输出词元预算钳位。

一些提供商（特别是 Anthropic 模型的 AWS Bedrock）强制执行
``input_tokens + max_tokens <= context_window``. 在 BerriAI/litellm#17900 LiteLLM 的
默认值
``max_tokens`` 成为模型的完整版本之后
``max_output_tokens``（e.g。十四行诗 4.5 为 64k）。 对于 Bedrock 来说，这意味着任何上
面大约
``context_window - max_output_tokens`` 的输入都会失败，并显示“输入对于请求的模型来说
太长”，即使实际响应很小。

这些测试涵盖了添加到 ``LLM._finalize_completion_params`` 的请求时间限制。
"""

from __future__ import annotations

from unittest.mock import patch

from pydantic import SecretStr

from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.llm.llm import (
    JOINT_BUDGET_MIN_OUTPUT_TOKENS,
    JOINT_BUDGET_SAFETY_MARGIN_TOKENS,
)


def _make_llm(model: str, *, max_input_tokens: int = 200_000) -> LLM:
    llm = LLM(
        usage_id="test-llm",
        model=model,
        api_key=SecretStr("test"),
        max_input_tokens=max_input_tokens,
    )
    # 跨环境稳定：通过直接固定有效窗口，跳过 ``_init_model_info_and_caps`` 中发生的
    # LiteLLM 模型信息查找。 ``max_input_tokens=`` 已经喂食
    # ``effective_max_input_tokens``。
    #
    return llm


def test_bedrock_clamps_max_tokens_when_input_is_large():
    """具有 195k 输入 + 64k 请求输出的基岩必须被钳位。"""
    llm = _make_llm("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    call_kwargs = {"max_completion_tokens": 64_000}

    with patch("openhands.sdk.llm.llm.token_counter", return_value=195_000):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    # Headroom = 200_000 - 195_000 - 256 = 4_744; well above the floor.
    expected = 200_000 - 195_000 - JOINT_BUDGET_SAFETY_MARGIN_TOKENS
    assert out["max_completion_tokens"] == expected
    assert out["max_completion_tokens"] < 64_000


def test_bedrock_does_not_clamp_when_input_is_small():
    """具有小输入的基岩适合不变的完整 64k 输出预算。"""
    llm = _make_llm("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    call_kwargs = {"max_completion_tokens": 64_000}

    # 50k 输入 + 64k 输出 = 114k，远低于 200k 窗口。
    with patch("openhands.sdk.llm.llm.token_counter", return_value=50_000):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    assert out["max_completion_tokens"] == 64_000
    # 不需要相同的字典标识，但内容应保持不变。
    assert out == call_kwargs


def test_bedrock_floor_when_input_nearly_fills_window():
    """当净空 < 地板时，夹在地板上（并发出警告）。"""
    llm = _make_llm("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    call_kwargs = {"max_completion_tokens": 64_000}

    # 199.9k 输入仅留下约 100 token 的 True 净空，远低于地板。
    with patch("openhands.sdk.llm.llm.token_counter", return_value=199_900):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    assert out["max_completion_tokens"] == JOINT_BUDGET_MIN_OUTPUT_TOKENS


def test_anthropic_direct_is_never_clamped():
    """Anthropic 直接 API 具有独立的输入/输出预算——无限制。"""
    llm = _make_llm("claude-sonnet-4-5-20250929")
    call_kwargs = {"max_completion_tokens": 64_000}

    # 即使投入巨大，也不能限制非联合提供商。
    with patch("openhands.sdk.llm.llm.token_counter", return_value=195_000):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    assert out is call_kwargs
    assert out["max_completion_tokens"] == 64_000


def test_clamps_max_tokens_key_too():
    """钳位目标是存在的任何预算键（Azure / 思考使用 max_tokens）。"""  # noqa: E501
    llm = _make_llm("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    call_kwargs = {"max_tokens": 64_000}

    with patch("openhands.sdk.llm.llm.token_counter", return_value=195_000):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    assert "max_completion_tokens" not in out
    assert out["max_tokens"] == 200_000 - 195_000 - JOINT_BUDGET_SAFETY_MARGIN_TOKENS


def test_no_clamp_when_no_budget_key_present():
    """如果 max_tokens 和 max_completion_tokens 均未设置，则保留 kwargs。"""
    llm = _make_llm("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    call_kwargs = {"temperature": 0.0}

    with patch("openhands.sdk.llm.llm.token_counter", return_value=195_000):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    assert out == {"temperature": 0.0}


def test_user_supplied_smaller_budget_is_preserved():
    """如果来电者已经通过了合适的预算，请不要更改它。"""
    llm = _make_llm("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    call_kwargs = {"max_completion_tokens": 2_000}

    # 195k 输入 + 用户提供的 2k 输出 = 197k，仍然适合安全裕度后的 200k 窗口。 不宜夹住。
    #
    with patch("openhands.sdk.llm.llm.token_counter", return_value=195_000):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    assert out["max_completion_tokens"] == 2_000


def test_clamp_skipped_when_token_counter_raises():
    """如果计数失败，则返回到未夹紧的行为（并记录）。"""
    llm = _make_llm("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    call_kwargs = {"max_completion_tokens": 64_000}

    with patch(
        "openhands.sdk.llm.llm.token_counter",
        side_effect=RuntimeError("boom"),
    ):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    assert out["max_completion_tokens"] == 64_000


def test_finalize_completion_params_applies_clamp_end_to_end():
    """重现客户错误路径：Bedrock Sonnet 4.5 上的大量输入
    必须导致预算受限，而不是模型的完整 64k 输出。"""
    llm = _make_llm("bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    llm._effective_max_output_tokens = 64_000  # 镜像注册表将设置的内容

    messages = [Message(role="user", content=[TextContent(text="hello")])]
    formatted = llm.format_messages_for_llm(messages)

    with patch("openhands.sdk.llm.llm.token_counter", return_value=195_000):
        (
            _formatted,
            _cc_tools,
            _use_mock_tools,
            call_kwargs,
            _telemetry,
        ) = llm._finalize_completion_params(
            formatted_messages=formatted,
            tools=None,
            add_security_risk_prediction=False,
            kwargs={},
        )

    budget = call_kwargs.get("max_tokens") or call_kwargs.get("max_completion_tokens")
    assert budget is not None
    assert budget < 64_000
    # 应固定在净空高度（195k 输入远高于地板）。
    assert budget == 200_000 - 195_000 - JOINT_BUDGET_SAFETY_MARGIN_TOKENS


def test_no_clamp_when_context_window_unknown():
    """如果我们不知道上下文窗口，我们就无法安全地钳位。"""
    llm = LLM(
        usage_id="test-llm",
        model="bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        api_key=SecretStr("test"),
    )
    # 初始化后强制未知窗口。
    llm._effective_max_input_tokens = None
    call_kwargs = {"max_completion_tokens": 64_000}

    with patch("openhands.sdk.llm.llm.token_counter", return_value=195_000):
        out = llm._clamp_max_tokens_for_joint_budget(call_kwargs, [], [])

    assert out["max_completion_tokens"] == 64_000
