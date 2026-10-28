from unittest.mock import AsyncMock, patch

import pytest
from litellm.responses.streaming_iterator import (
    ResponsesAPIStreamingIterator,
    SyncResponsesAPIStreamingIterator,
)
from litellm.types.llms.openai import ResponsesAPIResponse
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from pydantic import SecretStr

from openhands.sdk.llm import LLM, LLMResponse, Message, TextContent
from openhands.sdk.llm.exceptions import LLMNoResponseError


def create_mock_response(
    content: str = "ok", response_id: str = "r-1"
) -> ModelResponse:
    return ModelResponse(
        id=response_id,
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(content=content, role="assistant"),
            )
        ],
        created=1,
        model="gpt-4o",
        object="chat.completion",
        system_fingerprint="t",
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )


def create_empty_choices_response(response_id: str = "empty-1") -> ModelResponse:
    return ModelResponse(
        id=response_id,
        choices=[],  # LLMNoResponseError 在重试边界内触发
        created=1,
        model="gpt-4o",
        object="chat.completion",
        usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1),
    )


@pytest.fixture
def base_llm() -> LLM:
    return LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
        temperature=0.0,  # 明确设置为测试温度突变行为
    )


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_no_response_retries_then_succeeds(mock_completion, base_llm: LLM) -> None:
    mock_completion.side_effect = [
        create_empty_choices_response("empty-1"),
        create_mock_response("success"),
    ]

    resp = base_llm.completion(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    assert isinstance(resp, LLMResponse)
    assert resp.message is not None
    assert mock_completion.call_count == 2  # 首字母 + 1 重试


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_no_response_exhausts_retries_bubbles_llm_no_response(
    mock_completion, base_llm: LLM
) -> None:
    # 总是返回空选项 -> LLMNoResponseError 仍在递增重试
    mock_completion.side_effect = [
        create_empty_choices_response("empty-1"),
        create_empty_choices_response("empty-2"),
    ]

    with pytest.raises(LLMNoResponseError):
        base_llm.completion(
            messages=[Message(role="user", content=[TextContent(text="hi")])]
        )

    # tenacity 总共运行函数 num_retries 次
    assert mock_completion.call_count == base_llm.num_retries


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_no_response_retry_bumps_temperature(mock_completion, base_llm: LLM) -> None:
    # 确保我们从 0.0 开始以触发重试上的 1.0 碰撞
    assert base_llm.temperature == 0.0

    mock_completion.side_effect = [
        create_empty_choices_response("empty-1"),
        create_mock_response("ok"),
    ]

    base_llm.completion(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    # 验证第二次调用时，温度是否已由 RetryMixin 升至 1.0
    assert mock_completion.call_count == 2
    # 从第二次调用中获取 kwargs
    _, second_kwargs = mock_completion.call_args_list[1]
    assert second_kwargs.get("temperature") == 1.0


# ------------------------------------------------------------------
# 异步完成测试
# ------------------------------------------------------------------


@pytest.mark.asyncio
@patch(
    "openhands.sdk.llm.llm.litellm_acompletion",
    new_callable=AsyncMock,
)
async def test_async_no_response_retry_bumps_temperature(
    mock_acompletion: AsyncMock, base_llm: LLM
) -> None:
    """异步完成后必须在重试 (B2 回归) 上施加温度冲击。"""
    assert base_llm.temperature == 0.0

    mock_acompletion.side_effect = [
        create_empty_choices_response("empty-1"),
        create_mock_response("ok"),
    ]

    resp = await base_llm.acompletion(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    assert isinstance(resp, LLMResponse)
    assert mock_acompletion.call_count == 2
    _, second_kwargs = mock_acompletion.call_args_list[1]
    assert second_kwargs.get("temperature") == 1.0


@pytest.mark.asyncio
@patch(
    "openhands.sdk.llm.llm.litellm_acompletion",
    new_callable=AsyncMock,
)
async def test_async_no_response_retries_then_succeeds(
    mock_acompletion: AsyncMock, base_llm: LLM
) -> None:
    mock_acompletion.side_effect = [
        create_empty_choices_response("empty-1"),
        create_mock_response("success"),
    ]

    resp = await base_llm.acompletion(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    assert isinstance(resp, LLMResponse)
    assert resp.message is not None
    assert mock_acompletion.call_count == 2


@pytest.mark.asyncio
@patch(
    "openhands.sdk.llm.llm.litellm_acompletion",
    new_callable=AsyncMock,
)
async def test_async_no_response_exhausts_retries(
    mock_acompletion: AsyncMock, base_llm: LLM
) -> None:
    mock_acompletion.side_effect = [
        create_empty_choices_response("empty-1"),
        create_empty_choices_response("empty-2"),
    ]

    with pytest.raises(LLMNoResponseError):
        await base_llm.acompletion(
            messages=[Message(role="user", content=[TextContent(text="hi")])]
        )

    assert mock_acompletion.call_count == base_llm.num_retries


# ------------------------------------------------------------------
# 异步反应测试
# ------------------------------------------------------------------


def create_mock_responses_api_response(
    text: str = "ok",
) -> ResponsesAPIResponse:
    return ResponsesAPIResponse(
        id="resp-1",
        created_at=1,
        output=[
            ResponseOutputMessage(
                id="msg-1",
                type="message",
                role="assistant",
                status="completed",
                content=[
                    ResponseOutputText(type="output_text", text=text, annotations=[])
                ],
            )
        ],
        model="gpt-4o",
        object="response",
    )


@pytest.mark.asyncio
@patch(
    "openhands.sdk.llm.llm.litellm_aresponses",
    new_callable=AsyncMock,
)
async def test_async_aresponses_retry_bumps_temperature(
    mock_aresponses: AsyncMock, base_llm: LLM
) -> None:
    """响应必须在重试 (B2 回归) 上应用温度冲击。"""
    assert base_llm.temperature == 0.0

    mock_aresponses.side_effect = [
        LLMNoResponseError("empty response"),
        create_mock_responses_api_response("ok"),
    ]

    resp = await base_llm.aresponses(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    assert isinstance(resp, LLMResponse)
    assert mock_aresponses.call_count == 2
    _, second_kwargs = mock_aresponses.call_args_list[1]
    assert second_kwargs.get("temperature") == 1.0


@pytest.mark.asyncio
@patch(
    "openhands.sdk.llm.llm.litellm_aresponses",
    new_callable=AsyncMock,
)
async def test_async_aresponses_retries_then_succeeds(
    mock_aresponses: AsyncMock, base_llm: LLM
) -> None:
    mock_aresponses.side_effect = [
        LLMNoResponseError("empty response"),
        create_mock_responses_api_response("success"),
    ]

    resp = await base_llm.aresponses(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    assert isinstance(resp, LLMResponse)
    assert resp.message is not None
    assert mock_aresponses.call_count == 2


@pytest.mark.asyncio
@patch(
    "openhands.sdk.llm.llm.litellm_aresponses",
    new_callable=AsyncMock,
)
async def test_async_aresponses_exhausts_retries(
    mock_aresponses: AsyncMock, base_llm: LLM
) -> None:
    mock_aresponses.side_effect = [
        LLMNoResponseError("empty-1"),
        LLMNoResponseError("empty-2"),
    ]

    with pytest.raises(LLMNoResponseError):
        await base_llm.aresponses(
            messages=[Message(role="user", content=[TextContent(text="hi")])]
        )

    assert mock_aresponses.call_count == base_llm.num_retries


# ------------------------------------------------------------------
# 同步响应测试（练习共享助手提取）
# ------------------------------------------------------------------


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_responses_retry_bumps_temperature(mock_responses, base_llm: LLM) -> None:
    """同步响应必须在重试上应用温度冲击
    _prepare_responses_params / _build_responses_call_kwargs 提取。"""
    assert base_llm.temperature == 0.0

    mock_responses.side_effect = [
        LLMNoResponseError("empty response"),
        create_mock_responses_api_response("ok"),
    ]

    resp = base_llm.responses(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    assert isinstance(resp, LLMResponse)
    assert mock_responses.call_count == 2
    _, second_kwargs = mock_responses.call_args_list[1]
    assert second_kwargs.get("temperature") == 1.0


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_responses_retries_then_succeeds(mock_responses, base_llm: LLM) -> None:
    mock_responses.side_effect = [
        LLMNoResponseError("empty response"),
        create_mock_responses_api_response("success"),
    ]

    resp = base_llm.responses(
        messages=[Message(role="user", content=[TextContent(text="hi")])]
    )

    assert isinstance(resp, LLMResponse)
    assert resp.message is not None
    assert mock_responses.call_count == 2


# ------------------------------------------------------------------
# 流式传输-路径重试测试（流在没有 ResponseCompletedEvent 的情况下完成）
# ------------------------------------------------------------------


class _FakeSyncStreamIterator(SyncResponsesAPIStreamingIterator):
    """用于测试流路径故障的最小同步流迭代器。

    镜子：class:`_FakeAsyncStreamIterator` 为同步
    ``responses``路径：继承自``SyncResponsesAPIStreamingIterator``，因此它通过
    ``responses._one_attempt``内的``isinstance``检查，但跳过重量级父级``__init__``。
    """

    def __init__(
        self,
        events: list,
        completed_response=None,
    ) -> None:
        # 故意跳过父级__init__； 我们只需要迭代和 completed_response 属性。
        #
        self._events = list(events)
        self.completed_response = completed_response

    def __iter__(self):
        return self

    def __next__(self):
        if not self._events:
            raise StopIteration
        return self._events.pop(0)


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_responses_stream_path_retry_bumps_temperature(mock_responses) -> None:
    """同步流式传输响应流路径测试的对应项：an
    在 LLMNoResponseError 边界内，如果没有完成的事件，迭代器重试会抛出重试。
    """
    streaming_llm = LLM(
        usage_id="test-stream-sync",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=0,
        retry_max_wait=0,
        temperature=0.0,
        stream=True,
    )

    mock_responses.side_effect = [
        _FakeSyncStreamIterator(events=[], completed_response=None),
        create_mock_responses_api_response("ok"),
    ]

    resp = streaming_llm.responses(
        messages=[Message(role="user", content=[TextContent(text="hi")])],
        on_token=lambda _chunk: None,
    )

    assert isinstance(resp, LLMResponse)
    assert mock_responses.call_count == 2
    _, second_kwargs = mock_responses.call_args_list[1]
    assert second_kwargs.get("temperature") == 1.0


class _FakeAsyncStreamIterator(ResponsesAPIStreamingIterator):
    """用于测试流路径故障的最小异步流迭代器。

    继承自``ResponsesAPIStreamingIterator``，因此它传递了
    ``isinstance`` 检查内部 ``aresponses._one_attempt``，但跳过重量级父级
    ``__init__``。
    """

    def __init__(
        self,
        events: list,
        completed_response=None,
    ) -> None:
        # 故意跳过父级__init__； 我们只需要迭代和 completed_response 属性。
        #
        self._events = list(events)
        self.completed_response = completed_response

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)


@pytest.mark.asyncio
@patch(
    "openhands.sdk.llm.llm.litellm_aresponses",
    new_callable=AsyncMock,
)
async def test_async_aresponses_stream_path_retry_bumps_temperature(
    mock_aresponses: AsyncMock,
) -> None:
    """当流式传输响应没有已完成的事件时，_finalize_stream_response
    LLMNoResponseError 位于重试边界内。 在重试，温度应该从0→1.0调高，就像非流式传输路
    径一样。
    """
    streaming_llm = LLM(
        usage_id="test-stream",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=0,
        retry_max_wait=0,
        temperature=0.0,
        stream=True,
    )

    # 第一调用：返回一个没有完成事件的迭代器 → _finalize_stream_response 引发
    # LLMNoResponseError 第二调用：返回一个有效的非流式传输响应（快速路径）
    #
    mock_aresponses.side_effect = [
        _FakeAsyncStreamIterator(events=[], completed_response=None),
        create_mock_responses_api_response("ok"),
    ]

    resp = await streaming_llm.aresponses(
        messages=[Message(role="user", content=[TextContent(text="hi")])],
        on_token=lambda _chunk: None,
    )

    assert isinstance(resp, LLMResponse)
    assert mock_aresponses.call_count == 2
    _, second_kwargs = mock_aresponses.call_args_list[1]
    assert second_kwargs.get("temperature") == 1.0
