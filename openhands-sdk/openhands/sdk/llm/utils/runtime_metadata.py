""":class:`~openhands.sdk.llm.LLM` 的提供者感知运行时元数据解析。

静态模型目录（LiteLLM 模型元数据）描述了模型的名义限制，这并不总是配置的提供者在运行
时实际服务的限制。 OpenRouter 是典型的例子：目录以 1M-token
 上下文来广告 `deepseek/deepseek-v4-flash-0731`，但是 CoreWeave 这样的端点仅支持 262k
  token。

该模块延迟解析路由感知限制，使用 TTL 缓存它们，并在出现任何错误时回退到现有元数据。
这是一个用于元数据兼容性的狭窄层 LiteLLM 仍不提供，一旦 LiteLLM
提供等效的提供者-端点元数据，就应该移除（或委托）。

See: https://github.com/OpenHands/software-agent-sdk/issues/4421
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLM

logger = get_logger(__name__)

# 成功解决的运行时更新保持新鲜的时间有多长。
RUNTIME_METADATA_TTL_SECONDS = 3600
# 在失败/负面解决方案后抑制重新发现需要多长时间，以便每一步都不会受到不稳定的提供商或封
# 闭的网络漏洞的影响。
#
RUNTIME_METADATA_NEGATIVE_TTL_SECONDS = 300
# 有界上游探针； 元数据发现绝不能阻止完成。
RUNTIME_METADATA_TIMEOUT_SECONDS = 10.0


class ModelRuntimeMetadata(BaseModel):
    """解决了单个 ``LLM`` 配置的路由感知限制。

    包括来源信息，使调用者能够判断值是否为已锁定路由的精确极限、跨可选路由的保守上限
    ，还是回退方案来表示模型级别的元数据。
    """

    max_input_tokens: int | None = None
    source: str
    candidate_providers: list[str] = Field(default_factory=list)
    selected_provider: str | None = None
    confidence: Literal["exact", "safe_lower_bound", "model_level", "unknown"] = (
        "unknown"
    )


# 异步适配器：返回路由相关的元数据或 None，当提供者不支持或不可解析时（因此调用者会回退
# 到模型级别的元数据）。
#
ProviderResolver = Callable[["LLM"], Coroutine[Any, Any, ModelRuntimeMetadata | None]]


def _provider_config(llm: LLM) -> dict[str, Any]:
    """返回 ``litellm_extra_body`` 的路由块（如果有）。"""
    extra_body = llm.litellm_extra_body or {}
    provider = extra_body.get("provider")
    return provider if isinstance(provider, dict) else {}


def cache_key(llm: LLM) -> tuple[str, str, str]:
    """描述配置路由的稳定密钥。

    解析为相同提供程序/模式和路由配置的两个 ``LLM`` 实例共享一个缓存条目； 不同的路由
    首选项则不会。
    """
    model = llm.model or ""
    base_url = llm.base_url or ""
    provider = _provider_config(llm)
    try:
        provider_json = json.dumps(provider, sort_keys=True, default=str)
    except TypeError:  # 防御性地； 路由配置是 JSON-可序列化
        provider_json = repr(sorted(provider.items()))
    return (model, base_url, provider_json)


# ---------------------------------------------------------------------------
# 缓存/负缓存助手，例如存储在 LLM 上的实例状态
# ---------------------------------------------------------------------------


def cached_metadata(
    metadata: ModelRuntimeMetadata | None,
    fetched_at: float | None,
) -> ModelRuntimeMetadata | None:
    """返回仍然新鲜的缓存元数据，否则 None（没有网络 I/O）。"""
    if metadata is None or fetched_at is None:
        return None
    if time.monotonic() - fetched_at < RUNTIME_METADATA_TTL_SECONDS:
        return metadata
    return None


def in_negative_cache(negative_until: float | None) -> bool:
    if negative_until is None:
        return False
    return time.monotonic() < negative_until


def store_result(
    metadata: ModelRuntimeMetadata | None,
    now: float | None = None,
) -> tuple[float | None, float | None, ModelRuntimeMetadata | None]:
    """探测后计算新的（fetched_at，negative_until，元数据）状态。

    返回状态字段，以便调用者可以在实例上持久化它们。
    """
    now = now if now is not None else time.monotonic()
    if metadata is not None:
        return (now, None, metadata)
    return (None, now + RUNTIME_METADATA_NEGATIVE_TTL_SECONDS, None)


# ---------------------------------------------------------------------------
# 派遣
# ---------------------------------------------------------------------------


def _openrouter_resolver() -> ProviderResolver:
    # 延迟导入，因此该模块在没有 httpx 的情况下仍可导入，因此除非使用 OpenRouter 模型，
    # 否则适配器的依赖项不会加载。
    #
    from openhands.sdk.llm.utils.providers.openrouter import aresolve_openrouter

    return aresolve_openrouter


def detect_provider(llm: LLM) -> ProviderResolver | None:
    model = llm.model or ""
    base_url = llm.base_url or ""
    if model.startswith("openrouter/") or "openrouter.ai" in base_url:
        return _openrouter_resolver()
    return None


async def _safe_resolve(
    resolver: ProviderResolver, llm: LLM
) -> ModelRuntimeMetadata | None:
    """运行解析器，将任何意外错误映射到 ``None``。

    传输/解析失败绝不能中止真正的 LLM 请求； 调用者转而使用模型级元数据。 取消总是传
    播，以便调用者可以尊重 ``await`` 取消。
    """
    try:
        return await resolver(llm)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 - any failure falls back upstream
        logger.warning(
            "runtime metadata resolution failed for %s (provider: %s); falling "
            "back to model-level metadata: %s",
            llm.model,
            llm.base_url,
            e,
            exc_info=True,
        )
        return None


_inflight: dict[
    tuple[asyncio.AbstractEventLoop, tuple[str, str, str]],
    asyncio.Task[ModelRuntimeMetadata | None],
] = {}


async def aresolve_provider_metadata(
    llm: LLM,
) -> ModelRuntimeMetadata | None:
    """解决提供者感知的运行时元数据，删除重复的并发调用。

    对于不受支持的提供程序或无法解析的路由，返回 ``None``，以便调用者回退到静态模型元
    数据。

    除了路线之外，飞行中的任务还通过 *事件循环* 进行键控，以便两个线程各自运行自己的
    循环（驱动共享的受支持方式）
    ``LLM``) 从不等待附加到另一个循环的任务。
    """
    resolver = detect_provider(llm)
    if resolver is None:
        return None

    key = cache_key(llm)
    inflight_key = (asyncio.get_running_loop(), key)
    pending = _inflight.get(inflight_key)
    if pending is not None and not pending.done():
        # 同一航线的并发分辨率且事件循环已在飞行中； 等待它而不是发出重复的上游请求。
        #
        return await pending

    task = asyncio.create_task(_safe_resolve(resolver, llm))
    _inflight[inflight_key] = task
    try:
        return await task
    finally:
        if _inflight.get(inflight_key) is task:
            del _inflight[inflight_key]


def resolve_provider_metadata_sync(llm: LLM) -> ModelRuntimeMetadata | None:
    """同步：func:`aresolve_provider_metadata` 的变体。

    在专用事件循环中运行异步适配器。 正在运行的调用者事件循环 (e.g. 智能体-服务器异步
    路径）应使用异步变体； 如果检测到，则返回 ``None``，以便调用者回
    退到模型级元数据而不是引发 ``RuntimeError``。
    """
    resolver = detect_provider(llm)
    if resolver is None:
        return None

    # 无法从已拥有正在运行的事件循环的线程输入 asyncio.run()。 更喜欢优雅的回退方案而不
    # 是让调用者崩溃。
    #
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        logger.warning(
            "resolve_provider_metadata_sync() called from a running event loop; "
            "use aresolve_runtime_metadata() instead. Falling back to model metadata."
        )
        return None

    async def _run() -> ModelRuntimeMetadata | None:
        return await _safe_resolve(resolver, llm)

    return asyncio.run(_run())
