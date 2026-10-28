from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openhands.sdk.llm.call_context import (
    apply_llm_call_context,
    resolve_llm_call_context,
)
from openhands.sdk.llm.options.common import (
    apply_defaults_if_absent,
    apply_extra_body,
    apply_extra_headers,
    is_openrouter,
)


if TYPE_CHECKING:
    from openhands.sdk.llm.call_context import LLMCallContext


def select_responses_options(
    llm,
    user_kwargs: dict[str, Any],
    *,
    include: list[str] | None,
    store: bool | None,
    call_context: LLMCallContext | None = None,
) -> dict[str, Any]:
    """_normalize_responses_kwargs 的行为保留提取。"""
    # 对非策略强制的密钥应用默认值
    # 注意：订阅模式不支持max_output_tokens
    defaults = {}
    if not llm.is_subscription:
        defaults["max_output_tokens"] = llm.effective_max_output_tokens
    out = apply_defaults_if_absent(user_kwargs, defaults)

    model_features = llm._model_features()
    if not llm.is_subscription and model_features.supports_sampling_params is False:
        out.pop("temperature", None)
        out.pop("top_p", None)
        out.pop("top_k", None)
    elif not llm.is_subscription and llm.temperature is not None:
        out.setdefault("temperature", llm.temperature)
    out["tool_choice"] = "auto"

    out = apply_extra_headers(out, llm)

    # 除非明确提供，否则存储默认为 False（无状态）
    if store is not None:
        out["store"] = bool(store)
    else:
        out.setdefault("store", False)

    # 仅当用户在 LLM 上启用加密推理且仅适用于无状态调用 (store=False) 时才包含加密推理。
    #  尊重用户的选择。
    # 注意：订阅模式不支持include和reasoning
    # （当这些参数存在时，Codex 订阅端点会默默地返回空输出）。
    #
    if not llm.is_subscription:
        include_list = list(include) if include is not None else []
        supports_reasoning = model_features.supports_reasoning_effort

        if (
            not out.get("store", False)
            and llm.enable_encrypted_reasoning
            and supports_reasoning
        ):
            if "reasoning.encrypted_content" not in include_list:
                include_list.append("reasoning.encrypted_content")
        if include_list:
            out["include"] = include_list

        if llm.reasoning_effort and supports_reasoning:
            out["reasoning"] = {"effort": llm.reasoning_effort}
            # 如果明确设置，则可以选择包含摘要（需要经过验证的组织）
            if llm.reasoning_summary:
                out["reasoning"]["summary"] = llm.reasoning_summary

    # 仅当型号支持时才发送 prompt_cache_retention
    # 注意：订阅模式不支持prompt_cache_retention
    if (
        not llm.is_subscription
        and model_features.supports_prompt_cache_retention
        and llm.prompt_cache_retention
    ):
        out["prompt_cache_retention"] = llm.prompt_cache_retention

    out = apply_extra_body(out, llm)
    context = resolve_llm_call_context(call_context)
    apply_llm_call_context(
        out,
        context,
        supports_prompt_cache_key=model_features.supports_prompt_cache_key,
        openrouter=is_openrouter(llm),
    )

    return out
