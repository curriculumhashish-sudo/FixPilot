from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLM


def apply_defaults_if_absent(
    user_kwargs: dict[str, Any], defaults: dict[str, Any]
) -> dict[str, Any]:
    """当键不存在时，返回一个应用默认值的新字典。

    - 纯粹且确定性； 不改变输入
    - 仅当密钥丢失且默认值不为 None 时才应用默认值
    - 不改变用户提供的值
    """
    out = dict(user_kwargs)
    for key, value in defaults.items():
        if key not in out and value is not None:
            out[key] = value
    return out


def apply_extra_headers(user_kwargs: dict[str, Any], llm: LLM) -> dict[str, Any]:
    """返回一个应用了 LLM 额外标头的新字典。

    当调用者未设置自己的属性标头时传播 ``llm.extra_headers``，然后合并 OpenRouter 属
    性标头。 这些通过
    ``extra_headers``而不是``os.environ``进行，因此在多租户服务器中不会泄露对话（见
    issue #3138）。 用户提供的标头获胜。

    - 纯粹且确定性； 不改变输入
    """
    out = dict(user_kwargs)

    if llm.extra_headers is not None and "extra_headers" not in out:
        out["extra_headers"] = dict(llm.extra_headers)

    openrouter_headers = llm._openrouter_headers()
    if openrouter_headers:
        existing = out.get("extra_headers") or {}
        out["extra_headers"] = {**openrouter_headers, **existing}

    return out


def apply_extra_body(user_kwargs: dict[str, Any], llm: LLM) -> dict[str, Any]:
    """返回一个新的字典，其中传递了用户提供的 ``extra_body``。

    - 纯粹且确定性； 不改变输入
    """
    out = dict(user_kwargs)
    if llm.litellm_extra_body:
        out["extra_body"] = llm.litellm_extra_body
    return out


def is_openrouter(llm: LLM) -> bool:
    """返回此 LLM 是否路由通过 OpenRouter。

    匹配 ``openrouter/`` 模型前缀和 OpenRouter 运行时元数据解析器也关闭的
    ``openrouter.ai`` 基础 URL，因此两者就
    OpenRouter 的计算方式达成一致。
    """
    model = llm.model or ""
    base_url = llm.base_url or ""
    return model.startswith("openrouter/") or "openrouter.ai" in base_url
