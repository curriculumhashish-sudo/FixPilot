"""测试 LLM 超时配置。"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from aiohttp import web
from litellm.exceptions import Timeout as LiteLLMTimeout
from pydantic import SecretStr

from openhands.sdk.agent import Agent
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.llm import LLM, Message, TextContent
from openhands.sdk.llm.exceptions import LLMTimeoutError


# 默认超时，以秒为单位（5 分钟）
DEFAULT_LLM_TIMEOUT_SECONDS = 300


class TestLLMTimeoutDefaults:
    """测试默认的 LLM 超时行为。"""

    def test_default_timeout_is_5_minutes(self):
        """测试默认 LLM 超时是否为 300 秒（5 分钟）。

        该测试确保 LLM 请求具有合理的默认超时，以防止无限挂起请求，这些请求可能导致运
        行时检测杀死活跃运行时。

        See: https://github.com/OpenHands/software-agent-sdk/issues/1633
        """
        llm = LLM(model="gpt-4o-mini", usage_id="test-llm")

        assert llm.timeout == DEFAULT_LLM_TIMEOUT_SECONDS, (
            f"Expected default timeout of {DEFAULT_LLM_TIMEOUT_SECONDS}s (5 minutes), "
            f"but got {llm.timeout}. "
            "A reasonable default timeout is needed to prevent LLM calls from "
            "hanging indefinitely and causing runtime idle detection issues."
        )
        assert llm.stream_idle_timeout == DEFAULT_LLM_TIMEOUT_SECONDS

    def test_stream_idle_timeout_defaults_to_configured_timeout(self):
        llm = LLM(model="gpt-4o-mini", usage_id="test-llm", timeout=600)
        assert llm.stream_idle_timeout == 600

    def test_stream_idle_timeout_can_be_disabled(self):
        llm = LLM(
            model="gpt-4o-mini",
            usage_id="test-llm",
            timeout=600,
            stream_idle_timeout=None,
        )
        assert llm.timeout == 600
        assert llm.stream_idle_timeout is None

    def test_timeout_can_be_overridden(self):
        """测试超时是否可以显式设置为自定义值。"""
        custom_timeout = 600  # 10分钟
        llm = LLM(model="gpt-4o-mini", usage_id="test-llm", timeout=custom_timeout)

        assert llm.timeout == custom_timeout

    def test_timeout_can_be_set_to_none_for_no_timeout(self):
        """测试超时是否可以显式设置为 None 以禁用超时。

        需要很长的 LLM 调用（e.g.，具有高思维预算的扩展推理）的用户可以通过将超时设置
        为 None 来显式禁用它。
        """
        llm = LLM(model="gpt-4o-mini", usage_id="test-llm", timeout=None)

        # 当明确设置为 None 时，应保留 None
        assert llm.timeout is None

    def test_timeout_validation_rejects_negative_values(self):
        """测试负超时值是否被拒绝。"""
        with pytest.raises(Exception):  # ValidationError 来自 Pydantic
            LLM(model="gpt-4o-mini", usage_id="test-llm", timeout=-1)

    def test_timeout_accepts_zero(self):
        """测试零超时是否有效（立即数超时）。"""
        llm = LLM(model="gpt-4o-mini", usage_id="test-llm", timeout=0)
        assert llm.timeout == 0


class TestLLMTimeoutPassthrough:
    """测试超时是否正确传递到 LiteLLM。"""

    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_default_timeout_passed_to_litellm(self, mock_completion):
        """测试默认的超时是否传递给 LiteLLM 完成调用。"""
        from litellm.types.utils import (
            Choices,
            Message as LiteLLMMessage,
            ModelResponse,
            Usage,
        )

        # 创建正确的模拟对象响应
        mock_response = ModelResponse(
            id="test-id",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=LiteLLMMessage(content="Test response", role="assistant"),
                )
            ],
            created=1234567890,
            model="gpt-4o-mini",
            object="chat.completion",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        mock_completion.return_value = mock_response

        llm = LLM(
            model="gpt-4o-mini",
            api_key=SecretStr("test_key"),
            usage_id="test-llm",
        )

        messages = [Message(role="user", content=[TextContent(text="Hello")])]
        llm.completion(messages=messages)

        # 验证超时已传递给 LiteLLM
        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args[1]

        assert "timeout" in call_kwargs, "timeout should be passed to litellm"
        assert call_kwargs["timeout"] == DEFAULT_LLM_TIMEOUT_SECONDS, (
            f"Expected timeout of {DEFAULT_LLM_TIMEOUT_SECONDS}s to be passed "
            f"to litellm, but got {call_kwargs['timeout']}"
        )

    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_custom_timeout_passed_to_litellm(self, mock_completion):
        """测试是否将自定义超时传递给 LiteLLM 完成调用。"""
        from litellm.types.utils import (
            Choices,
            Message as LiteLLMMessage,
            ModelResponse,
            Usage,
        )

        mock_response = ModelResponse(
            id="test-id",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=LiteLLMMessage(content="Test response", role="assistant"),
                )
            ],
            created=1234567890,
            model="gpt-4o-mini",
            object="chat.completion",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        mock_completion.return_value = mock_response

        custom_timeout = 120
        llm = LLM(
            model="gpt-4o-mini",
            api_key=SecretStr("test_key"),
            usage_id="test-llm",
            timeout=custom_timeout,
        )

        messages = [Message(role="user", content=[TextContent(text="Hello")])]
        llm.completion(messages=messages)

        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args[1]

        assert call_kwargs["timeout"] == custom_timeout

    @patch("openhands.sdk.llm.llm.litellm_completion")
    def test_none_timeout_passed_to_litellm(self, mock_completion):
        """测试 None 超时是否传递到 LiteLLM（没有超时）。"""
        from litellm.types.utils import (
            Choices,
            Message as LiteLLMMessage,
            ModelResponse,
            Usage,
        )

        mock_response = ModelResponse(
            id="test-id",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=LiteLLMMessage(content="Test response", role="assistant"),
                )
            ],
            created=1234567890,
            model="gpt-4o-mini",
            object="chat.completion",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        mock_completion.return_value = mock_response

        llm = LLM(
            model="gpt-4o-mini",
            api_key=SecretStr("test_key"),
            usage_id="test-llm",
            timeout=None,  # 明确设置为 None
        )

        messages = [Message(role="user", content=[TextContent(text="Hello")])]
        llm.completion(messages=messages)

        mock_completion.assert_called_once()
        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["timeout"] is None


@asynccontextmanager
async def _hung_chat_completion_server(
    *, keep_sending: bool = False
) -> AsyncIterator[tuple[str, list[int]]]:
    attempts: list[int] = []

    async def completion(request: web.Request) -> web.StreamResponse:
        await request.json()
        attempts.append(len(attempts) + 1)
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        chunk = {
            "id": f"chatcmpl-{attempts[-1]}",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "test-model",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hi"}}],
        }
        while True:
            await response.write(f"data: {json.dumps(chunk)}\n\n".encode())
            if not keep_sending:
                await asyncio.Event().wait()
            await asyncio.sleep(0.01)

    app = web.Application()
    app.router.add_post("/chat/completions", completion)
    runner = web.AppRunner(app, shutdown_timeout=0.01)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    address = runner.addresses[0]
    assert isinstance(address, tuple)
    port = address[1]
    assert isinstance(port, int)
    try:
        yield f"http://127.0.0.1:{port}", attempts
    finally:
        await runner.cleanup()


def _streaming_llm(base_url: str, **kwargs) -> LLM:
    return LLM(
        model="openai/test-model",
        api_key=SecretStr("test-key"),
        base_url=base_url,
        usage_id="timeout-test",
        stream=True,
        retry_min_wait=0,
        retry_max_wait=0,
        retry_multiplier=0,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_async_stream_idle_timeout_retries_real_http_stream() -> None:
    async with _hung_chat_completion_server() as (base_url, attempts):
        # 硬超时需要真正的余量：空闲触发路径在这里需要几秒钟（两次尝试第一个块），所以一
        # 个紧张的
        # `timeout` 将使外部硬超时在 CPU 争用下获胜，并且错误将显示为“硬超时”而不是“空闲
        # 超时”。
        #
        llm = _streaming_llm(
            base_url,
            timeout=30,
            stream_idle_timeout=0.05,
            num_retries=2,
        )

        with pytest.raises(LLMTimeoutError, match="idle timeout"):
            await llm.acompletion(
                messages=[Message(role="user", content=[TextContent(text="Hello")])],
                on_token=lambda _: None,
            )

    assert len(attempts) == 2


class _TransportTimeoutStream:
    """异步迭代器，其第一个块引发传输层级 TimeoutError。"""

    def __init__(self, message: str = "transport read timed out") -> None:
        self.message = message

    def __aiter__(self) -> "_TransportTimeoutStream":
        return self

    async def __anext__(self):
        raise TimeoutError(self.message)


@pytest.mark.asyncio
async def test_idle_timeout_disabled_preserves_transport_timeout() -> None:
    """对于 `stream_idle_timeout=None`，真实的 TimeoutError 必须通过。"""
    llm = LLM(
        model="gpt-4o-mini",
        usage_id="test-llm",
        timeout=300,
        stream_idle_timeout=None,
    )

    with pytest.raises(TimeoutError, match="transport read timed out") as exc_info:
        async for _ in llm._aiter_with_idle_timeout(_TransportTimeoutStream()):
            pass

    assert not isinstance(exc_info.value, LiteLLMTimeout)


@pytest.mark.asyncio
async def test_transport_timeout_is_not_relabelled_as_idle_timeout() -> None:
    """启用的空闲定时器不得声明传输层 TimeoutError。"""
    llm = LLM(
        model="gpt-4o-mini",
        usage_id="test-llm",
        timeout=300,
        stream_idle_timeout=5,
    )

    with pytest.raises(TimeoutError, match="transport read timed out") as exc_info:
        async for _ in llm._aiter_with_idle_timeout(_TransportTimeoutStream()):
            pass

    assert not isinstance(exc_info.value, LiteLLMTimeout)
    assert "idle timeout" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_idle_timeout_still_fires_for_stalled_stream() -> None:
    """空闲计时器本身仍然会引发空闲超时错误。"""
    llm = LLM(
        model="gpt-4o-mini",
        usage_id="test-llm",
        timeout=300,
        stream_idle_timeout=0.01,
    )

    async def stalled() -> AsyncIterator[None]:
        await asyncio.Event().wait()
        yield None

    with pytest.raises(LiteLLMTimeout, match="stream idle timeout after 0.01"):
        async for _ in llm._aiter_with_idle_timeout(stalled()):
            pass


@pytest.mark.asyncio
async def test_hard_timeout_keeps_attribution_over_idle_timeout() -> None:
    """外部硬超时不得报告为空闲超时。"""
    llm = LLM(
        model="gpt-4o-mini",
        usage_id="test-llm",
        timeout=1,
        stream_idle_timeout=30,
    )

    async def stalled() -> AsyncIterator[None]:
        await asyncio.Event().wait()
        yield None

    async def consume() -> None:
        async for _ in llm._aiter_with_idle_timeout(stalled()):
            pass

    wrapped = llm._async_hard_timeout_decorator()(consume)
    with pytest.raises(LiteLLMTimeout, match="hard timeout after 1 seconds"):
        await wrapped()


@pytest.mark.asyncio
@pytest.mark.parametrize("idle_timeout", [None, 30])
async def test_transport_timeout_survives_both_timeout_layers(
    idle_timeout: float | None,
) -> None:
    """无论设置如何，传输层 TimeoutError 都会以不变的方式到达调用者。"""
    llm = LLM(
        model="gpt-4o-mini",
        usage_id="test-llm",
        timeout=300,
        stream_idle_timeout=idle_timeout,
    )

    async def consume() -> None:
        async for _ in llm._aiter_with_idle_timeout(_TransportTimeoutStream()):
            pass

    wrapped = llm._async_hard_timeout_decorator()(consume)
    with pytest.raises(TimeoutError, match="transport read timed out") as exc_info:
        await wrapped()

    assert type(exc_info.value) is TimeoutError


@pytest.mark.asyncio
async def test_async_hard_timeout_expires_active_attempt() -> None:
    llm = _streaming_llm("http://127.0.0.1", timeout=0, num_retries=1)

    async def never_finishes() -> None:
        await asyncio.Event().wait()

    wrapped = llm._async_hard_timeout_decorator()(never_finishes)
    with pytest.raises(LiteLLMTimeout, match="hard timeout"):
        await wrapped()


class _TimedOutLLM(LLM):
    async def acompletion(self, *args, **kwargs):
        raise LLMTimeoutError("stream idle timeout")


@pytest.mark.asyncio
async def test_exhausted_stream_timeout_transitions_conversation_to_error(
    tmp_path,
) -> None:
    conversation = LocalConversation(
        agent=Agent(llm=_TimedOutLLM(model="test-model"), tools=[]),
        workspace=str(tmp_path),
        visualizer=None,
    )
    conversation.send_message("Hello")

    with pytest.raises(ConversationRunError):
        await conversation.arun()

    assert conversation.state.execution_status == ConversationExecutionStatus.ERROR
