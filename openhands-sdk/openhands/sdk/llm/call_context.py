"""会话拥有的上下文在执行时应用于 LLM 调用。"""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class LLMCallContext:
    """LLM 后面的不可变运行时值调用一个对话。

    上下文属于对话，而不是：class:`LLM`。 将其显式传递给 LLM 调用仍然是首选路径。 范
    围当前值涵盖其公共接口尚不接受上下文的内部组件，例如上下文压缩器。
    """

    prompt_cache_key: str | None = None
    session_id: str | None = None

    def for_conversation(
        self,
        conversation_id: str,
        *,
        prompt_cache_key: str | None = None,
    ) -> LLMCallContext:
        """派生上下文进行对话，同时保留可继承字段。

        会话标识始终会被替换。 任何添加到这个数据类中的额外字段都会自动继承，除非这个
        方法明确赋予它们本地语义。
        """
        return replace(
            self,
            prompt_cache_key=prompt_cache_key or conversation_id,
            session_id=conversation_id,
        )


_CURRENT_LLM_CALL_CONTEXT: ContextVar[LLMCallContext | None] = ContextVar(
    "openhands_llm_call_context",
    default=None,
)


@contextmanager
def llm_call_context_scope(context: LLMCallContext) -> Iterator[None]:
    """使 ``context`` 可供此执行范围内的 LLM 调用使用。"""
    token = _CURRENT_LLM_CALL_CONTEXT.set(context)
    try:
        yield
    finally:
        _CURRENT_LLM_CALL_CONTEXT.reset(token)


def resolve_llm_call_context(
    explicit: LLMCallContext | None,
) -> LLMCallContext:
    """使用显式的、有范围的、然后为空的优先级来解析上下文。"""
    return explicit or _CURRENT_LLM_CALL_CONTEXT.get() or LLMCallContext()


def apply_llm_call_context(
    options: MutableMapping[str, Any],
    context: LLMCallContext,
    *,
    supports_prompt_cache_key: bool = False,
    openrouter: bool = False,
) -> None:
    """将 SDK 拥有的调用上下文应用于一处的提供者请求选项。

    ``prompt_cache_key`` 仅发送给接受它作为 OpenAI 参数的提供商（OpenAI 响应/聊天）。
     Anthropic 双子座以 400 拒绝
    ``UnsupportedParamsError`` 当 LiteLLM 验证非默认参数时。

    ``openrouter`` 选择 OpenRouter自身的亲和参数： OpenRouter sticky路由关闭
    ``session_id``因此，对话中的后续
    部分会回到端点抓住温暖提示词 cache. 没有它 OpenRouter 通过哈希开篇消息来推导路由
    键智能体将对话重写为紧凑形式，导致中途失去关联性。
    """
    if context.prompt_cache_key and supports_prompt_cache_key:
        options["prompt_cache_key"] = context.prompt_cache_key
    if context.session_id:
        existing = options.get("extra_headers") or {}
        options["extra_headers"] = {
            **existing,
            "x-litellm-session-id": context.session_id,
        }
        if openrouter:
            # 合并而不是替换：extra_body 可能已经携带呼叫者路由 (e.g. provider.only）必
            # 须生存。 来自呼叫者的显式 session_id 赢得了对话 ID。
            #
            extra_body = dict(options.get("extra_body") or {})
            extra_body.setdefault("session_id", context.session_id)
            options["extra_body"] = extra_body
