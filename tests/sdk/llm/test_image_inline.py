"""http(s)图片URLs作为base64``data:``进行内联URLs的测试。"""

from __future__ import annotations

import asyncio
import base64
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr

from openhands.sdk.llm import LLM, ImageContent, Message, TextContent
from openhands.sdk.llm.utils import image_inline
from openhands.sdk.llm.utils.image_inline import (
    _CACHE,
    amaybe_inline_image_urls,
    maybe_inline_image_urls,
)
from openhands.sdk.llm.utils.model_features import get_features


_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def _clear_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


@pytest.fixture(autouse=True)
def _stub_dns_to_public_ip(monkeypatch: pytest.MonkeyPatch):
    """使SSRF主机解析默认返回公共IP。

    单独的测试可以覆盖此设置以执行环回/私有主机。
    """
    monkeypatch.setattr(
        image_inline, "_resolve_host_ips", lambda host, port: ["8.8.8.8"]
    )
    yield


def _stub_get(url: str, *, body: bytes = _TINY_PNG, content_type: str = "image/png"):
    """返回上下文管理器，模拟对象 httpx.Client.stream 为一 URL。"""

    class _StubResponse:
        is_redirect = False

        def __init__(self) -> None:
            self.headers = {
                "Content-Type": content_type,
                "Content-Length": str(len(body)),
            }

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, chunk_size: int = 65536):
            yield body

    class _StubClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> _StubClient:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        def close(self) -> None:
            return None

        def stream(self, method: str, request_url: str):
            assert method == "GET"
            assert request_url == url

            class _Stream:
                def __enter__(self) -> _StubResponse:
                    return _StubResponse()

                def __exit__(self, *exc: Any) -> None:
                    return None

            return _Stream()

    return patch.object(image_inline.httpx, "Client", _StubClient)


def test_no_op_when_inline_not_required():
    msg = Message(
        role="user",
        content=[ImageContent(image_urls=["https://example.com/x.png"])],
    )
    original_messages = [msg]
    out = maybe_inline_image_urls(
        original_messages, inline_required=False, vision_enabled=True
    )
    # 快速路径必须返回相同的列表对象——没有复制，没有重写。
    assert out is original_messages
    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert img.image_urls == ["https://example.com/x.png"]


def test_no_op_when_vision_disabled():
    msg = Message(
        role="user",
        content=[ImageContent(image_urls=["https://example.com/x.png"])],
    )
    out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=False)
    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert img.image_urls == ["https://example.com/x.png"]


def test_inlines_http_url_to_base64_data_url():
    url = "https://example.com/x.png"
    msg = Message(role="user", content=[ImageContent(image_urls=[url])])

    with _stub_get(url):
        out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    expected = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode("ascii")
    assert img.image_urls == [expected]
    # 输入不得发生突变。
    original = msg.content[0]
    assert isinstance(original, ImageContent)
    assert original.image_urls == [url]


def test_data_url_passes_through_unchanged():
    data_url = "data:image/png;base64,AAAA"
    msg = Message(role="user", content=[ImageContent(image_urls=[data_url])])

    # 不需要模拟对象 — 不得执行任何网络调用。
    out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert img.image_urls == [data_url]


def test_fetch_failure_falls_back_to_original_url():
    url = "https://example.com/broken.png"
    msg = Message(role="user", content=[ImageContent(image_urls=[url])])

    class _BoomClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        def close(self) -> None:
            return None

        def stream(self, method: str, request_url: str):
            raise httpx.ConnectError("boom")

    with patch.object(image_inline.httpx, "Client", _BoomClient):
        out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert img.image_urls == [url]


def test_non_image_content_type_falls_back_to_original_url():
    """带有 ``Content-Type: text/html`` 的 200 OK（soft-404/auth wall）必须
    不内联为 ``data:text/html;...`` — 而是发送原始 URL，并且上游产生其本机错误。
    """
    url = "https://example.com/soft-404.png"
    msg = Message(role="user", content=[ImageContent(image_urls=[url])])

    image_inline._CACHE.clear()
    with _stub_get(url, body=b"<html>not found</html>", content_type="text/html"):
        out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert img.image_urls == [url]


def test_no_extension_and_no_content_type_falls_back_to_original_url():
    """如果 URL 路径扩展和服务器 ``Content-Type`` 都是
    丢失，``_derive_mime_type`` 必须引发，以便调用者回退到原来的 URL — 否则软 404 /
    auth-wall 响应会偷偷溜过
    ``_ALLOWED_IMAGE_MIMES`` 守卫。
    """
    url = "https://example.com/path/with/no/extension"
    msg = Message(role="user", content=[ImageContent(image_urls=[url])])

    image_inline._CACHE.clear()
    with _stub_get(url, body=b"<html>not found</html>", content_type=""):
        out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert img.image_urls == [url]


def test_cache_reuses_result_across_calls():
    url = "https://example.com/x.png"
    msg1 = Message(role="user", content=[ImageContent(image_urls=[url])])
    msg2 = Message(role="user", content=[ImageContent(image_urls=[url])])

    call_counter = {"n": 0}

    class _CountingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        def close(self) -> None:
            return None

        def stream(self, method: str, request_url: str):
            call_counter["n"] += 1

            class _Resp:
                is_redirect = False

                def __init__(self) -> None:
                    self.headers = {
                        "Content-Type": "image/png",
                        "Content-Length": str(len(_TINY_PNG)),
                    }

                def raise_for_status(self) -> None:
                    return None

                def iter_bytes(self, chunk_size: int = 65536):
                    yield _TINY_PNG

            class _Stream:
                def __enter__(self) -> _Resp:
                    return _Resp()

                def __exit__(self, *exc: Any) -> None:
                    return None

            return _Stream()

    with patch.object(image_inline.httpx, "Client", _CountingClient):
        maybe_inline_image_urls([msg1], inline_required=True, vision_enabled=True)
        maybe_inline_image_urls([msg2], inline_required=True, vision_enabled=True)

    assert call_counter["n"] == 1


@pytest.mark.parametrize(
    "model",
    [
        "moonshot/kimi-k2.6",
        "litellm_proxy/moonshot/kimi-k2.6",
        "moonshot/kimi-k3",
        "litellm_proxy/moonshot/kimi-k3",
        "openhands/kimi-k3",
    ],
)
def test_model_features_marks_models_requiring_inline_images(model: str):
    assert get_features(model).requires_inline_image_data is True


def test_model_features_does_not_mark_other_moonshot_models():
    # 仅列出特定提供商/型号路线； Kimi的兄弟姐妹的标记必须保持不变，以继续像以前一样行为
    # 。
    #
    assert get_features("moonshot/kimi-k2.5").requires_inline_image_data is False
    assert get_features("moonshot/kimi-k2-thinking").requires_inline_image_data is False
    # Kimi K2.6 仅在其他云（bedrock/fireworks/azure）上托管，URLs 会被接受，且必须不自动
    # 内联。
    #
    assert (
        get_features("bedrock/moonshotai.kimi-k2.5").requires_inline_image_data is False
    )
    assert (
        get_features(
            "fireworks_ai/accounts/fireworks/models/kimi-k2.6"
        ).requires_inline_image_data
        is False
    )


def test_llm_inline_image_urls_override_wins_over_capability():
    """显式 LLM 字段必须覆盖功能默认值。"""
    url = "https://example.com/x.png"
    llm = LLM(
        model="anthropic/claude-sonnet-4-6",
        api_key=SecretStr("test-key"),
        inline_image_urls=True,
        usage_id="test",
    )
    message = Message(
        role="user",
        content=[TextContent(text="hi"), ImageContent(image_urls=[url])],
    )

    with (
        patch.object(LLM, "vision_is_active", return_value=True),
        _stub_get(url),
    ):
        formatted = llm.format_messages_for_llm([message])

    image_blocks = [
        item for item in formatted[0]["content"] if item.get("type") == "image_url"
    ]
    assert image_blocks
    sent_url = image_blocks[0]["image_url"]["url"]
    assert sent_url.startswith("data:image/png;base64,")


def test_llm_kimi_k2_6_auto_inlines_without_override():
    """当模型位于功能列表中时，无需覆盖。"""
    url = "https://example.com/x.png"
    llm = LLM(
        model="litellm_proxy/moonshot/kimi-k2.6",
        api_key=SecretStr("test-key"),
        usage_id="test",
    )
    message = Message(
        role="user",
        content=[ImageContent(image_urls=[url])],
    )

    with (
        patch.object(LLM, "vision_is_active", return_value=True),
        _stub_get(url),
    ):
        formatted = llm.format_messages_for_llm([message])

    image_blocks = [
        item for item in formatted[0]["content"] if item.get("type") == "image_url"
    ]
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize(
    "model",
    [
        "moonshot/kimi-k3",
        "litellm_proxy/moonshot/kimi-k3",
        "openhands/kimi-k3",
    ],
)
def test_llm_kimi_k3_auto_inlines_http_url(model: str):
    """K3 视觉请求下载公共 URLs 之前序列化。"""
    url = "https://example.com/x.png"
    llm = LLM(
        model=model,
        api_key=SecretStr("test-key"),
        usage_id="test",
    )
    message = Message(
        role="user",
        content=[ImageContent(image_urls=[url])],
    )

    with _stub_get(url):
        formatted = llm.format_messages_for_llm([message])

    image_blocks = [
        item for item in formatted[0]["content"] if item.get("type") == "image_url"
    ]
    expected = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode("ascii")
    assert image_blocks[0]["image_url"]["url"] == expected


def test_llm_inline_image_urls_false_disables_capability_default():
    """即使模型会自动选择加入，``inline_image_urls=False`` 也会选择退出。"""
    url = "https://example.com/x.png"
    llm = LLM(
        model="litellm_proxy/moonshot/kimi-k2.6",
        api_key=SecretStr("test-key"),
        inline_image_urls=False,
        usage_id="test",
    )
    message = Message(
        role="user",
        content=[ImageContent(image_urls=[url])],
    )

    class _ShouldNotBeCalled:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError(
                "httpx.Client must not be constructed when inline_image_urls=False"
            )

    with (
        patch.object(LLM, "vision_is_active", return_value=True),
        patch.object(image_inline.httpx, "Client", _ShouldNotBeCalled),
    ):
        formatted = llm.format_messages_for_llm([message])

    image_blocks = [
        item for item in formatted[0]["content"] if item.get("type") == "image_url"
    ]
    assert image_blocks[0]["image_url"]["url"] == url


def test_ssrf_blocks_loopback_literal(monkeypatch: pytest.MonkeyPatch):
    """不得获取 ``http://127.0.0.1/...`` URL。"""
    url = "http://127.0.0.1/secret.png"
    msg = Message(role="user", content=[ImageContent(image_urls=[url])])

    class _ShouldNotStream:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

        def close(self) -> None:
            return None

        def stream(self, method: str, request_url: str):
            raise AssertionError(
                f"SSRF check should have blocked the fetch for {request_url}"
            )

    with patch.object(image_inline.httpx, "Client", _ShouldNotStream):
        out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    # 获取被拒绝 → 保留原始 URL（尽力而为回退方案）。
    assert img.image_urls == [url]


def test_ssrf_blocks_private_host_via_dns(monkeypatch: pytest.MonkeyPatch):
    """不得获取解析为私有 IP 的主机名。"""
    monkeypatch.setattr(
        image_inline, "_resolve_host_ips", lambda host, port: ["10.0.0.5"]
    )
    url = "http://internal.example/secret.png"
    msg = Message(role="user", content=[ImageContent(image_urls=[url])])

    class _ShouldNotStream:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def close(self) -> None:
            return None

        def stream(self, method: str, request_url: str):
            raise AssertionError("SSRF check should have blocked private DNS result")

    with patch.object(image_inline.httpx, "Client", _ShouldNotStream):
        out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert img.image_urls == [url]


def test_ssrf_blocks_localhost_hostname():
    """``localhost`` 在没有 DNS 决议的情况下被拒绝。"""
    url = "http://localhost/secret.png"
    msg = Message(role="user", content=[ImageContent(image_urls=[url])])
    out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)
    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert img.image_urls == [url]


def test_reuses_single_client_across_multiple_urls():
    """多图像轮流共享单个 ``httpx.Client`` 用于连接池。"""
    url_a = "https://example.com/a.png"
    url_b = "https://example.com/b.png"
    msg = Message(
        role="user",
        content=[ImageContent(image_urls=[url_a, url_b])],
    )

    instantiations = {"n": 0}

    class _PoolingResp:
        is_redirect = False

        def __init__(self) -> None:
            self.headers = {
                "Content-Type": "image/png",
                "Content-Length": str(len(_TINY_PNG)),
            }

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, chunk_size: int = 65536):
            yield _TINY_PNG

    class _PoolingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            instantiations["n"] += 1

        def close(self) -> None:
            return None

        def stream(self, method: str, request_url: str):
            class _Stream:
                def __enter__(self) -> _PoolingResp:
                    return _PoolingResp()

                def __exit__(self, *exc: Any) -> None:
                    return None

            return _Stream()

    with patch.object(image_inline.httpx, "Client", _PoolingClient):
        out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    assert instantiations["n"] == 1, "expected a single shared httpx.Client"
    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    assert all(u.startswith("data:image/png;base64,") for u in img.image_urls)


def test_fetch_timeout_is_env_configurable(monkeypatch: pytest.MonkeyPatch):
    """``OH_INLINE_IMAGE_FETCH_TIMEOUT_S`` 覆盖默认值超时。"""
    monkeypatch.setenv("OH_INLINE_IMAGE_FETCH_TIMEOUT_S", "7.5")
    import importlib

    reloaded = importlib.reload(image_inline)
    try:
        assert reloaded.FETCH_TIMEOUT_S == 7.5
    finally:
        monkeypatch.delenv("OH_INLINE_IMAGE_FETCH_TIMEOUT_S", raising=False)
        importlib.reload(image_inline)


def test_async_inline_uses_thread_offload():
    """``amaybe_inline_image_urls`` 返回与同步遍相同的结果。"""
    url = "https://example.com/x.png"
    msg = Message(role="user", content=[ImageContent(image_urls=[url])])

    with _stub_get(url):
        out = asyncio.run(
            amaybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)
        )

    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    expected = "data:image/png;base64," + base64.b64encode(_TINY_PNG).decode("ascii")
    assert img.image_urls == [expected]


def test_ssrf_blocks_redirect_to_private_ip(monkeypatch: pytest.MonkeyPatch):
    """必须在重定向跃点上阻止从公共 URL 到私有 IP 的 302。

    ``_validate_url_target`` 在重定向跟随循环内被调用，因此重定向到
    ``http://10.0.0.5/secret.png`` 的公共源必须
    在没有流式传输私有主体的情况下被拒绝。
    """
    public_url = "https://example.com/redirect.png"
    private_url = "http://10.0.0.5/secret.png"

    # 第一次调用 (public_url) 解析为公共 IP； 第二个调用 (private_url) 解析为私有 IP，但
    #  ``_is_disallowed_ip`` 拒绝。
    #
    def _resolve(host: str, port: int) -> list[str]:
        return ["10.0.0.5"] if host == "10.0.0.5" else ["8.8.8.8"]

    monkeypatch.setattr(image_inline, "_resolve_host_ips", _resolve)

    streamed_urls: list[str] = []

    class _RedirectResp:
        is_redirect = True

        def __init__(self) -> None:
            self.headers = {"Location": private_url}

        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self, chunk_size: int = 65536):
            yield b""

    class _RedirectClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def close(self) -> None:
            return None

        def stream(self, method: str, request_url: str):
            streamed_urls.append(request_url)
            if request_url == private_url:
                raise AssertionError(
                    "SSRF check should have blocked the private redirect target "
                    "before any HTTP request was issued."
                )

            class _Stream:
                def __enter__(self) -> _RedirectResp:
                    return _RedirectResp()

                def __exit__(self, *exc: Any) -> None:
                    return None

            return _Stream()

    msg = Message(role="user", content=[ImageContent(image_urls=[public_url])])
    with patch.object(image_inline.httpx, "Client", _RedirectClient):
        out = maybe_inline_image_urls([msg], inline_required=True, vision_enabled=True)

    # 仅限首次公开 URL 实际上已经直播了。 私有重定向目标被拒绝了验证器在到达之前
    # ``stream``.
    #
    assert streamed_urls == [public_url]
    img = out[0].content[0]
    assert isinstance(img, ImageContent)
    # 获取在重定向中被拒绝 → 保留原始 URL。
    assert img.image_urls == [public_url]


def test_sync_and_async_formatters_produce_identical_output():
    """``aformat_messages_for_llm`` 必须匹配 ``format_messages_for_llm``。

    异步路径重复 ``_prepare_chat_messages``（深度复制 + 缓存 + 内联 + 调整大小），因
    此它可以 ``await`` 内联传递。 如果将
    来的准备通道添加到一条路径而不是另一条路径，则此测试可以防止静默漂移。
    """
    url = "https://example.com/x.png"
    llm = LLM(
        model="litellm_proxy/moonshot/kimi-k2.6",
        api_key=SecretStr("test-key"),
        usage_id="test",
    )
    message = Message(
        role="user",
        content=[TextContent(text="hi"), ImageContent(image_urls=[url])],
    )

    with (
        patch.object(LLM, "vision_is_active", return_value=True),
        _stub_get(url),
    ):
        sync_out = llm.format_messages_for_llm([message])
    with (
        patch.object(LLM, "vision_is_active", return_value=True),
        _stub_get(url),
    ):
        async_out = asyncio.run(llm.aformat_messages_for_llm([message]))

    assert sync_out == async_out


def test_responses_formatter_inlines_image_urls():
    """``format_messages_for_responses`` 重写图片 URLs base64。"""
    url = "https://example.com/x.png"
    llm = LLM(
        model="litellm_proxy/moonshot/kimi-k2.6",
        api_key=SecretStr("test-key"),
        usage_id="test",
    )
    message = Message(
        role="user",
        content=[TextContent(text="hi"), ImageContent(image_urls=[url])],
    )

    with (
        patch.object(LLM, "vision_is_active", return_value=True),
        _stub_get(url),
    ):
        _instructions, input_items = llm.format_messages_for_responses([message])

    # 响应 API 将非系统项目包装为带有内容数组的 ``message``。
    image_items: list[dict] = []
    for it in input_items:
        for c in it.get("content", []):
            if c.get("type") == "input_image":
                image_items.append(c)
    assert image_items, f"expected image input items, got {input_items!r}"
    assert image_items[0]["image_url"].startswith("data:image/png;base64,")
