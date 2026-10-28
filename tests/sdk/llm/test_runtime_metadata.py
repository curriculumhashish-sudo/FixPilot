"""测试提供者感知的运行时元数据解析。

涵盖了OpenRouter适配器（基于路由的上下文限制），LLMFacade方法，优先规则，TTL/负缓存，
并发去重，以及
``effective_max_input_tokens``保持副作用自由。

See: https://github.com/OpenHands/software-agent-sdk/issues/4421
"""

from __future__ import annotations

import asyncio
import threading

import httpx
import pytest

from openhands.sdk.llm import LLM, Message, ModelRuntimeMetadata, TextContent
from openhands.sdk.llm.utils import runtime_metadata as rm
from openhands.sdk.llm.utils.providers import openrouter as orm


PAYLOAD = {
    "data": {
        "id": "deepseek/deepseek-v4-flash-0731",
        "endpoints": [
            {
                "provider_name": "CoreWeave",
                "context_length": 262144,
                "max_completion_tokens": 262144,
            },
            {
                "provider_name": "Baseten",
                "context_length": 1048576,
                "max_completion_tokens": 1048576,
            },
            {
                "provider_name": "DeepInfra",
                "context_length": 1048576,
                "max_completion_tokens": 65536,
            },
        ],
    }
}


def _openrouter_llm(**overrides) -> LLM:
    return LLM(
        model=overrides.pop("model", "openrouter/deepseek/deepseek-v4-flash-0731"),
        litellm_extra_body=overrides.pop(
            "litellm_extra_body",
            {"provider": {"order": ["CoreWeave", "Baseten"], "allow_fallbacks": False}},
        ),
        **overrides,
    )


def _handler(payload=PAYLOAD, *, status: int = 200, body: str | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/endpoints" in request.url.path
        if status != 200:
            return httpx.Response(status, text=body or "boom")
        return httpx.Response(200, json=payload)

    return handler


def _async_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _sync_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _patch_async_factory(handler):
    """返回绑定到 MockTransport（处理程序）的 AsyncClient 工厂。

    在安装任何补丁之前捕获原始类，因此工厂不会递归到已修补的 ``httpx.AsyncClient``。
    """
    original = orm.httpx.AsyncClient

    def factory(*args, **kwargs):
        return original(transport=httpx.MockTransport(handler), **kwargs)

    return factory


# ---------------------------------------------------------------------------
# 解析/路由单元测试
# ---------------------------------------------------------------------------


def test_parse_pinned_order_returns_exact():
    md = orm.parse_openrouter_payload(
        PAYLOAD, {"order": ["CoreWeave", "Baseten"], "allow_fallbacks": False}
    )
    assert md is not None
    assert md.confidence == "exact"
    assert md.max_input_tokens == 262144
    assert md.selected_provider == "CoreWeave"
    assert md.candidate_providers == ["CoreWeave"]


def test_parse_allow_fallbacks_returns_safe_lower_bound():
    md = orm.parse_openrouter_payload(
        PAYLOAD, {"order": ["CoreWeave", "Baseten"], "allow_fallbacks": True}
    )
    assert md is not None
    assert md.confidence == "safe_lower_bound"
    assert md.max_input_tokens == 262144
    # 启用回退方案后，运行时提供程序无法提前获知，因此安全下限不得声明特定的提供程序。
    #
    assert md.selected_provider is None


def test_parse_no_routing_uses_all_endpoints():
    md = orm.parse_openrouter_payload(PAYLOAD, {})
    assert md is not None
    assert md.confidence == "safe_lower_bound"
    assert md.max_input_tokens == 262144
    assert md.selected_provider is None
    assert set(md.candidate_providers) == {"CoreWeave", "Baseten", "DeepInfra"}


def test_parse_provider_names_normalized_case_insensitively():
    payload = {
        "data": {
            "endpoints": [
                {"provider_name": "coreweave", "context_length": 262144},
                {"provider_name": "baseten", "context_length": 1048576},
            ]
        }
    }
    md = orm.parse_openrouter_payload(
        payload, {"order": ["COREWEAVE"], "allow_fallbacks": False}
    )
    assert md is not None
    assert md.confidence == "exact"
    assert md.max_input_tokens == 262144


def test_parse_unmatched_order_falls_back_to_none():
    # 引用目录中缺少的提供商的显式订单无法安全地解释； 应改用模型级元数据。
    #
    assert orm.parse_openrouter_payload(PAYLOAD, {"order": ["Nope"]}) is None
    assert orm.parse_openrouter_payload(PAYLOAD, {"only": ["Nope"]}) is None


def test_parse_ignore_removes_routes():
    md = orm.parse_openrouter_payload(
        PAYLOAD,
        {"order": ["CoreWeave"], "ignore": ["Baseten"], "allow_fallbacks": True},
    )
    # CoreWeave 保留； 巴斯坦被忽视； DeepInfra 添加回回退方案，但安全下限仍然是
    # CoreWeave 的 262144。
    #
    assert md is not None
    assert md.max_input_tokens == 262144


def test_parse_same_context_across_routes_is_exact():
    payload = {
        "data": {
            "endpoints": [
                {"provider_name": "A", "context_length": 1000},
                {"provider_name": "B", "context_length": 1000},
            ]
        }
    }
    md = orm.parse_openrouter_payload(payload, {})
    assert md is not None
    assert md.confidence == "exact"
    assert md.max_input_tokens == 1000


def test_parse_malformed_payload_returns_none():
    assert orm.parse_openrouter_payload({}, {}) is None
    assert orm.parse_openrouter_payload({"data": {}}, {}) is None
    assert orm.parse_openrouter_payload({"data": []}, {}) is None
    # 端点没有可用的 context_length。
    assert (
        orm.parse_openrouter_payload(
            {"data": {"endpoints": [{"provider_name": "A"}]}}, {}
        )
        is None
    )


def test_parse_list_shaped_data_supported():
    payload = {"data": [{"endpoints": PAYLOAD["data"]["endpoints"]}]}
    md = orm.parse_openrouter_payload(payload, {})
    assert md is not None
    assert md.max_input_tokens == 262144


def test_openrouter_model_id_normalization():
    llm = LLM(model="openrouter/deepseek/deepseek-v4-flash-0731")
    assert orm._openrouter_model_id(llm) == "deepseek/deepseek-v4-flash-0731"

    llm2 = LLM(
        model="deepseek/deepseek-v4-flash-0731", base_url="https://openrouter.ai/api/v1"
    )
    assert orm._openrouter_model_id(llm2) == "deepseek/deepseek-v4-flash-0731"

    # 非 OpenRouter 配置不会产生 id。
    llm3 = LLM(model="openai/gpt-4o")
    assert orm._openrouter_model_id(llm3) is None


# ---------------------------------------------------------------------------
# LLM 外观/缓存/优先级测试
# ---------------------------------------------------------------------------


def test_effective_unchanged_before_resolution():
    llm = _openrouter_llm()
    assert llm.resolved_runtime_metadata is None
    # 该属性不进行网络 I/O，因此该提供者报告的路由相关的限制（262144，见PAYLOAD）还不能
    # 生效——它会跳转到LiteLLM的静态元数据。 回退方案故意不被断言：它是上游数据，将其固定
    # 在此处使得该测试在 LiteLLM 学习模型的那天失败（#4877）。
    #
    assert llm.effective_max_input_tokens != 262144
    assert llm.resolved_runtime_metadata is None


def test_explicit_max_input_tokens_wins():
    llm = _openrouter_llm(max_input_tokens=131072)
    handler = _handler()
    client = _sync_client(handler)
    md = orm.resolve_openrouter_sync(llm, http_client=client)
    assert md is not None and md.max_input_tokens == 262144
    # 显式配置仍然高于发现的元数据。
    assert llm.effective_max_input_tokens == 131072


def test_async_resolution_updates_effective():
    llm = _openrouter_llm()

    async def go():
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(orm.httpx, "AsyncClient", _patch_async_factory(_handler()))
            return await llm.aresolve_runtime_metadata()

    md = asyncio.run(go())
    assert md is not None
    assert md.confidence == "exact"
    assert llm.effective_max_input_tokens == 262144


def test_acompletion_resolves_runtime_metadata(monkeypatch):
    """异步完成路径必须连接到运行时元数据解析中。

    如果没有 ``aresolve_runtime_metadata`` 的生产调用者，则永远不会填充缓存，并且
    ``effective_max_input_tokens`` 永远不会反映运行时路由（问题＃4421）。
    """
    from litellm.types.utils import (
        Choices,
        Message as LiteLLMMessage,
        ModelResponse,
        Usage,
    )

    llm = LLM(model="gpt-4o", api_key="test", usage_id="test-llm")
    resolved = {"calls": 0}
    orig_resolve = llm.aresolve_runtime_metadata

    async def recording(self, *, force: bool = False):
        resolved["calls"] += 1
        return await orig_resolve(force=force)

    monkeypatch.setattr(LLM, "aresolve_runtime_metadata", recording)

    async def fake_acompletion(*args, **kwargs):
        return ModelResponse(
            id="test",
            choices=[
                Choices(
                    finish_reason="stop",
                    message=LiteLLMMessage(content="ok", role="assistant"),
                )
            ],
            created=0,
            model="gpt-4o",
            object="chat.completion",
            usage=Usage(prompt_tokens=3, completion_tokens=2, total_tokens=5),
        )

    monkeypatch.setattr("openhands.sdk.llm.llm.litellm_acompletion", fake_acompletion)

    async def go():
        return await llm.acompletion(
            messages=[Message(role="user", content=[TextContent(text="hi")])]
        )

    assert asyncio.run(go()) is not None
    assert resolved["calls"] >= 1


def test_sync_and_async_agree():
    handler = _handler()
    llm_sync = _openrouter_llm()
    md_sync = orm.resolve_openrouter_sync(llm_sync, http_client=_sync_client(handler))
    md_async = asyncio.run(_aresolve(llm_sync, handler))
    assert md_sync == md_async


def _aresolve(llm, handler):
    async def go():
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(orm.httpx, "AsyncClient", _patch_async_factory(handler))
            return await llm.aresolve_runtime_metadata()

    return go()


def test_failure_negative_caches_then_refreshes(monkeypatch):
    llm = _openrouter_llm()
    calls = {"n": 0}

    def flaky_handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=PAYLOAD)

    async def go():
        monkeypatch.setattr(
            orm.httpx, "AsyncClient", _patch_async_factory(flaky_handler)
        )
        first = await llm.aresolve_runtime_metadata()
        # 在负缓存窗口内，不会发出第二个请求。
        second = await llm.aresolve_runtime_metadata()
        return first, second, calls["n"]

    first, second, count = asyncio.run(go())
    assert first is None
    assert second is None
    assert count == 1


def test_forced_resolution_bypasses_cache(monkeypatch):
    llm = _openrouter_llm()
    calls = {"n": 0}

    def counting_handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=PAYLOAD)

    async def go():
        monkeypatch.setattr(
            orm.httpx, "AsyncClient", _patch_async_factory(counting_handler)
        )
        await llm.aresolve_runtime_metadata()  # 缓存
        await llm.aresolve_runtime_metadata()  # 从缓存提供
        await llm.aresolve_runtime_metadata(force=True)  # 重新获取
        return calls["n"]

    assert asyncio.run(go()) == 2


def test_concurrent_resolution_deduplicates(monkeypatch):
    llm = _openrouter_llm()
    calls = {"n": 0}

    async def slow_handler(request):
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return httpx.Response(200, json=PAYLOAD)

    monkeypatch.setattr(orm.httpx, "AsyncClient", _patch_async_factory(slow_handler))
    rm._inflight.clear()

    async def go():
        results = await asyncio.gather(
            llm.aresolve_runtime_metadata(),
            llm.aresolve_runtime_metadata(),
            llm.aresolve_runtime_metadata(),
        )
        return results

    results = asyncio.run(go())
    assert all(r is not None and r.max_input_tokens == 262144 for r in results)
    assert calls["n"] == 1
    rm._inflight.clear()


def test_sync_resolver_inside_running_loop_falls_back():
    """同步解析器不得在运行循环内引发 asyncio.run()。"""
    llm = _openrouter_llm()

    async def go():
        # 这里存在一个正在运行的循环，因此同步解析器必须返回 None，而不尝试输入嵌套事件
        # 循环或发出请求。
        #
        return rm.resolve_provider_metadata_sync(llm)

    assert asyncio.run(go()) is None


def test_http_error_timeout_and_unsupported_fall_back(monkeypatch):
    # HTTP 500 -> None
    llm_err = _openrouter_llm()
    md = orm.resolve_openrouter_sync(
        llm_err, http_client=_sync_client(_handler(status=500))
    )
    assert md is None

    # 非OpenRouter模型->detect_provider返回None，无网络。
    llm_other = LLM(model="openai/gpt-4o")
    assert rm.detect_provider(llm_other) is None

    async def go():
        monkeypatch.setattr(
            orm.httpx, "AsyncClient", _patch_async_factory(_handler(status=500))
        )
        return await llm_err.aresolve_runtime_metadata()

    assert asyncio.run(go()) is None


def test_cached_metadata_ttl():
    md = ModelRuntimeMetadata(max_input_tokens=262144, source="test")
    now = rm.time.monotonic()
    assert rm.cached_metadata(md, now) is md
    # 已过期 -> None
    assert rm.cached_metadata(md, now - rm.RUNTIME_METADATA_TTL_SECONDS - 1) is None
    assert rm.cached_metadata(None, now) is None
    assert rm.cached_metadata(md, None) is None


def test_serialization_excludes_runtime_cache():
    llm = _openrouter_llm()
    llm._runtime_metadata = ModelRuntimeMetadata(max_input_tokens=262144, source="test")
    llm._runtime_metadata_fetched_at = 1.0
    dumped = llm.model_dump()
    assert "runtime_metadata" not in dumped
    assert "_runtime_metadata" not in dumped


def test_cache_key_depends_on_routing():
    llm_a = _openrouter_llm(litellm_extra_body={"provider": {"order": ["CoreWeave"]}})
    llm_b = _openrouter_llm(litellm_extra_body={"provider": {"order": ["Baseten"]}})
    assert rm.cache_key(llm_a) != rm.cache_key(llm_b)


# ---------------------------------------------------------------------------
# 回归审查者发现的测试
# ---------------------------------------------------------------------------


def test_parse_only_matches_returns_exact():
    """正 ``only`` 匹配会固定到该路线并且是准确的。"""
    md = orm.parse_openrouter_payload(PAYLOAD, {"only": ["CoreWeave"]})
    assert md is not None
    assert md.confidence == "exact"
    assert md.selected_provider == "CoreWeave"
    assert md.max_input_tokens == 262144


def test_detect_provider_prefix_requires_slash():
    """openrouterx/foo 不得被视为 OpenRouter 模型。"""
    assert rm.detect_provider(LLM(model="openrouterx/deepseek")) is None
    assert rm.detect_provider(LLM(model="not-openrouter")) is None
    assert (
        rm.detect_provider(LLM(model="openrouter/deepseek/deepseek-v4-flash-0731"))
        is not None
    )
    assert (
        rm.detect_provider(
            LLM(model="my-provider", base_url="https://openrouter.ai/api/v1")
        )
        is not None
    )


def test_model_copy_resets_cache_on_route_change():
    """更改路由必须删除旧密钥的所有缓存运行时元数据。"""
    llm = _openrouter_llm()
    llm._runtime_metadata = ModelRuntimeMetadata(max_input_tokens=262144, source="test")
    llm._runtime_metadata_fetched_at = rm.time.monotonic()
    llm._runtime_metadata_key = rm.cache_key(llm)
    assert llm.resolved_runtime_metadata is not None

    changed = llm.model_copy(
        update={"litellm_extra_body": {"provider": {"order": ["Baseten"]}}}
    )
    assert changed.resolved_runtime_metadata is None
    assert changed._runtime_metadata_key is None


def test_async_inflight_keyed_by_event_loop(monkeypatch):
    """动态重复数据删除的范围为事件循环，因此两个循环永远不会交叉等待。"""
    llm = _openrouter_llm()
    calls = {"n": 0}

    def counting_handler(request):
        calls["n"] += 1
        return httpx.Response(200, json=PAYLOAD)

    monkeypatch.setattr(
        orm.httpx, "AsyncClient", _patch_async_factory(counting_handler)
    )
    rm._inflight.clear()

    def go():
        return asyncio.run(rm.aresolve_provider_metadata(llm))

    a = go()
    b = go()
    rm._inflight.clear()
    assert a is not None and b is not None
    # 每个事件循环一个上游请求：循环 B 永远不会等待来自循环 A 的任务（这将跨越事件循环边
    # 界）。
    #
    assert calls["n"] == 2


def test_sync_resolution_generation_guards_stale_write(monkeypatch):
    """过时的（较早启动的）同步探针不得覆盖较新的结果。"""
    from openhands.sdk.llm import llm as llm_module

    start = threading.Event()
    release = threading.Event()
    calls = {"n": 0}
    llm = _openrouter_llm()

    def fake_resolver(_llm):
        calls["n"] += 1
        if calls["n"] == 1:
            start.set()
            release.wait(5)
            return ModelRuntimeMetadata(max_input_tokens=1000, source="stale")
        return ModelRuntimeMetadata(max_input_tokens=2000, source="newer")

    monkeypatch.setattr(llm_module, "resolve_provider_metadata_sync", fake_resolver)

    thread_result = {}

    def slow_call():
        thread_result["md"] = llm.resolve_runtime_metadata()

    t = threading.Thread(target=slow_call)
    t.start()
    assert start.wait(5)
    newer = llm.resolve_runtime_metadata()  # 颠簸生成，解析到 2000
    release.set()
    t.join(5)

    assert newer is not None and newer.max_input_tokens == 2000
    cached = rm.cached_metadata(llm._runtime_metadata, llm._runtime_metadata_fetched_at)
    assert cached is not None and cached.max_input_tokens == 2000
