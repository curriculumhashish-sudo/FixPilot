"""OpenRouter 运行时元数据适配器。

查询 OpenRouter 的端点目录以确定 ``LLM`` 实际上配置的路由的上下文/输出限制，而不是模
型级别的目录值（这可能会夸大端点的上下文）。

See: https://github.com/OpenHands/software-agent-sdk/issues/4421
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from openhands.sdk.llm.utils.runtime_metadata import (
    RUNTIME_METADATA_TIMEOUT_SECONDS,
    ModelRuntimeMetadata,
)
from openhands.sdk.logger import get_logger


if TYPE_CHECKING:
    from openhands.sdk.llm.llm import LLM

logger = get_logger(__name__)

OPENROUTER_ENDPOINTS_BASE = "https://openrouter.ai/api/v1/models"


def _openrouter_model_id(llm: LLM) -> str | None:
    """返回端点、API 或 None 的 OpenRouter 模型 ID。

    首选 ``openrouter/<id>`` 前缀形式。 当基础 URL 标识 OpenRouter 并且模型已经看起来
    像 OpenRouter id (
    ``provider/model``) 时，将按原样使用。
    """
    model = llm.model or ""
    base_url = llm.base_url or ""
    if model.startswith("openrouter/"):
        return model[len("openrouter/") :]
    if "openrouter.ai" in base_url and "/" in model:
        return model
    return None


def _normalize(name: Any) -> str:
    if not isinstance(name, str):
        return ""
    return name.strip().casefold()


def _provider_routing(llm: LLM) -> dict[str, Any]:
    extra_body = llm.litellm_extra_body or {}
    provider = extra_body.get("provider")
    return provider if isinstance(provider, dict) else {}


def _eligible_endpoints(
    endpoints: list[dict[str, Any]], routing: dict[str, Any]
) -> list[dict[str, Any]]:
    """对端点列表进行过滤并排序为路由配置允许的路由。

    匹配 OpenRouter 的提供者选择语义：``only`` 和 ``ignore`` 是首先应用的 *资格* 过滤
    器，``order`` 对幸存者进行排名。
    ``only`` 覆盖 ``order``（当 ``only`` 存在时，顺序被忽略）。 当
    ``allow_fallbacks`` 为 False 且给出
    ``order`` 时，将引脚路由到第一个幸存的有序提供者； 否则排序的提供者优先，其余的幸
    存者被附加为回退方案。
    """
    only = [p for p in (routing.get("only") or [])]
    ignore = [p for p in (routing.get("ignore") or [])]
    order = [p for p in (routing.get("order") or [])]
    allow_fallbacks = routing.get("allow_fallbacks", True)

    only_set = {_normalize(p) for p in only}
    ignore_set = {_normalize(p) for p in ignore}

    # (1) 资格：保留`only`允许的路线，而不是`ignore`允许的路线。 两者中列出的路线均被排
    # 除。
    #
    eligible = [
        e
        for e in endpoints
        if (not only_set or _normalize(e.get("provider_name")) in only_set)
        and _normalize(e.get("provider_name")) not in ignore_set
    ]
    if not eligible:
        return []

    # (2) `only` 覆盖 `order`：设置 `only` 后，顺序不再适用。
    if only_set or not order:
        return eligible

    order_idx = {_normalize(name): i for i, name in enumerate(order)}
    present_order = [
        e for e in eligible if _normalize(e.get("provider_name")) in order_idx
    ]
    others = [
        e for e in eligible if _normalize(e.get("provider_name")) not in order_idx
    ]
    if not present_order:
        # 引用幸存提供者 None 的显式订单无法安全地解释； 让调用者回退到模型元数据而不是
        # 猜测引脚。
        #
        return []
    if allow_fallbacks:
        present_order.sort(key=lambda e: order_idx[_normalize(e.get("provider_name"))])
        return present_order + others
    # 固定到第一个幸存的订购提供商。
    present_order.sort(key=lambda e: order_idx[_normalize(e.get("provider_name"))])
    return present_order[:1]


def parse_openrouter_payload(
    payload: dict[str, Any],
    routing: dict[str, Any],
) -> ModelRuntimeMetadata | None:
    """将 OpenRouter 端点响应转换为运行时元数据。

    当无法安全地解释路由时返回 ``None``，因此调用者会退回到模型级元数据而不是猜测。
    """
    data = payload.get("data")
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, dict):
        return None
    endpoints = data.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        return None

    valid = [
        e
        for e in endpoints
        if isinstance(e, dict) and isinstance(e.get("context_length"), int)
    ]
    if not valid:
        return None

    eligible = _eligible_endpoints(valid, routing)
    if not eligible:
        # 配置引用目录中不存在的路由，或者固定/跳过所有内容。 不要猜测极限。
        #
        return None

    provider_names = [e.get("provider_name", "") for e in eligible]
    contexts = [e.get("context_length", 0) for e in eligible]

    if len(eligible) == 1:
        target = eligible[0]
        return ModelRuntimeMetadata(
            max_input_tokens=target.get("context_length"),
            source="openrouter_endpoints_api",
            candidate_providers=provider_names,
            selected_provider=target.get("provider_name"),
            confidence="exact",
        )

    # 多个符合条件的路由：路由可能会选择其中任何一个，因此运行时提供程序无法提前知道，并
    # 且不应隐含任何单个 ``selected_provider``。 输入上下文是最小值，除非每条路线都一致
    # （在这种情况下该值是准确的）。
    #
    contexts_equal = len(set(contexts)) == 1
    return ModelRuntimeMetadata(
        max_input_tokens=contexts[0] if contexts_equal else min(contexts),
        source="openrouter_endpoints_api",
        candidate_providers=provider_names,
        selected_provider=None,
        confidence="exact" if contexts_equal else "safe_lower_bound",
    )


def _fetch_sync(url: str, client: httpx.Client | None) -> dict[str, Any] | None:
    own_client = client is None
    effective = client or httpx.Client(timeout=RUNTIME_METADATA_TIMEOUT_SECONDS)
    try:
        response = effective.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:  # noqa: BLE001 - any failure falls back upstream
        logger.debug(f"OpenRouter runtime metadata lookup failed: {e}", exc_info=True)
        return None
    finally:
        if own_client:
            effective.close()


async def _fetch_async(
    url: str, client: httpx.AsyncClient | None
) -> dict[str, Any] | None:
    own_client = client is None
    effective = client or httpx.AsyncClient(timeout=RUNTIME_METADATA_TIMEOUT_SECONDS)
    try:
        response = await effective.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:  # noqa: BLE001 - any failure falls back upstream
        logger.debug(f"OpenRouter runtime metadata lookup failed: {e}", exc_info=True)
        return None
    finally:
        if own_client:
            await effective.aclose()


def resolve_openrouter_sync(
    llm: LLM, *, http_client: httpx.Client | None = None
) -> ModelRuntimeMetadata | None:
    model_id = _openrouter_model_id(llm)
    if not model_id:
        return None
    payload = _fetch_sync(
        f"{OPENROUTER_ENDPOINTS_BASE}/{model_id}/endpoints", http_client
    )
    if payload is None:
        return None
    return parse_openrouter_payload(payload, _provider_routing(llm))


async def aresolve_openrouter(
    llm: LLM, *, http_client: httpx.AsyncClient | None = None
) -> ModelRuntimeMetadata | None:
    model_id = _openrouter_model_id(llm)
    if not model_id:
        return None
    payload = await _fetch_async(
        f"{OPENROUTER_ENDPOINTS_BASE}/{model_id}/endpoints", http_client
    )
    if payload is None:
        return None
    return parse_openrouter_payload(payload, _provider_routing(llm))
