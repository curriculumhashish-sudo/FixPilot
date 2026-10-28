import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, PropertyMock, patch

import pytest
from litellm.types.llms.base import BaseLiteLLMOpenAIResponseObject
from litellm.types.llms.openai import (
    GenericEvent,
    OutputTextDeltaEvent,
    ResponseAPIUsage,
    ResponseCompletedEvent,
    ResponsesAPIResponse,
    ResponsesAPIStreamEvents,
)
from openai.types.responses.response_function_tool_call import ResponseFunctionToolCall
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_text import ResponseOutputText
from openai.types.responses.response_reasoning_item import (
    ResponseReasoningItem,
    Summary,
)
from pydantic import SecretStr, ValidationError

from openhands.sdk.llm import LLM, LLMCallContext
from openhands.sdk.llm.exceptions import LLMNoResponseError, LLMTimeoutError
from openhands.sdk.llm.message import Message, ReasoningItemModel, TextContent
from openhands.sdk.llm.options.chat_options import select_chat_options
from openhands.sdk.llm.options.responses_options import select_responses_options


def build_responses_message_output(texts: list[str]) -> ResponseOutputMessage:
    parts = [
        ResponseOutputText(type="output_text", text=t, annotations=[]) for t in texts
    ]
    # 绕过测试中更严格的静态类型期望上下文； 运行时间很好
    return ResponseOutputMessage.model_construct(
        id="m1",
        type="message",
        role="assistant",
        status="completed",
        content=parts,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "ignored_part",
    [
        {"type": "future_part", "text": 42},
        SimpleNamespace(type="future_part", text=42),
        None,
        {"type": "output_text", "text": 0},
    ],
)
def test_responses_ignores_unused_or_empty_text_parts(ignored_part):
    message = Message.from_llm_responses_output(
        [
            {
                "type": "message",
                "content": [ignored_part, {"type": "output_text", "text": "hello"}],
            }
        ]
    )
    assert message.content == [TextContent(text="hello")]


@pytest.mark.parametrize("call_id", ["call_1", None])
def test_responses_generic_numeric_item_id_preserves_validation(call_id):
    output = [
        {
            "type": "function_call",
            "id": 42,
            "call_id": call_id,
            "name": "foo",
            "arguments": "{}",
        }
    ]
    if call_id is None:
        with pytest.raises(ValidationError):
            Message.from_llm_responses_output(output)
    else:
        message = Message.from_llm_responses_output(output)
        assert message.tool_calls is not None
        assert message.tool_calls[0].id == "call_1"
        assert message.tool_calls[0].responses_item_id == "42"


def test_from_llm_responses_output_parsing():
    # 构建类型化响应输出：辅助消息文本+函数调用+推理
    msg = build_responses_message_output(["Hello", "World"])  # 串联的
    fc = ResponseFunctionToolCall(
        type="function_call", name="do", arguments="{}", call_id="fc_1", id="fc_1"
    )
    reasoning = ResponseReasoningItem(
        id="rid",
        type="reasoning",
        summary=[
            Summary(type="summary_text", text="sum1"),
            Summary(type="summary_text", text="sum2"),
        ],
        content=None,
        encrypted_content=None,
        status="completed",
    )

    m = Message.from_llm_responses_output([msg, fc, reasoning])
    # 助理文字已加入
    assert m.role == "assistant"
    assert [c.text for c in m.content if isinstance(c, TextContent)] == ["Hello\nWorld"]
    # 工具调用归一化
    assert m.tool_calls and m.tool_calls[0].name == "do"
    # 推理映射
    assert isinstance(m.responses_reasoning_item, ReasoningItemModel)
    assert m.responses_reasoning_item.summary == ["sum1", "sum2"]


def test_normalize_responses_kwargs_policy():
    llm = LLM(model="gpt-5-mini", reasoning_effort="high")
    # 使用具有明确响应能力的模型 model_features

    # 启用加密推理并设置max_output_tokens以测试直通
    llm.enable_encrypted_reasoning = True
    llm.max_output_tokens = 128

    out = select_responses_options(
        llm, {"temperature": 0.3}, include=["text.output_text"], store=None
    )
    assert out["temperature"] == 0.3
    assert out["tool_choice"] == "auto"
    # include 应包含原始内容和 encrypted_content
    assert set(out["include"]) >= {"text.output_text", "reasoning.encrypted_content"}
    # 当None通过时将默认值存储为False
    assert out["store"] is False
    # 仅努力推理配置（未经验证的组织没有摘要）
    r = out["reasoning"]
    assert r["effort"] in {"low", "medium", "high", "none"}
    assert "summary" not in r  # 不包含摘要以支持未经验证的组织
    # max_output_tokens 保留
    assert out["max_output_tokens"] == 128


def test_responses_options_strip_sampling_when_metadata_rejects_it():
    llm = LLM(
        model="proxy/future-responses-model",
        api_mode="responses",
        temperature=0.7,
        capability_overrides={"supports_sampling_params": False},
    )

    out = select_responses_options(
        llm,
        {"temperature": 0.3, "top_p": 0.8, "top_k": 20},
        include=None,
        store=None,
    )

    assert "temperature" not in out
    assert "top_p" not in out
    assert "top_k" not in out


def test_normalize_responses_kwargs_with_summary():
    """设置时包含测试 reasoning_summary（已验证的组织）。"""
    llm = LLM(model="gpt-5-mini", reasoning_effort="high", reasoning_summary="detailed")

    out = select_responses_options(
        llm, {"temperature": 0.3}, include=["text.output_text"], store=None
    )
    # 设置摘要后，验证推理包括努力和摘要
    r = out["reasoning"]
    assert r["effort"] == "high"
    assert r["summary"] == "detailed"


def test_normalize_responses_kwargs_encrypted_reasoning_disabled():
    """测试加密推理是否包含在不中
    enable_encrypted_reasoning=False.
    """
    llm = LLM(model="gpt-4.1", reasoning_effort="medium")
    # 明确禁用加密推理（也是默认设置）
    llm.enable_encrypted_reasoning = False

    out = select_responses_options(llm, {}, include=["text.output_text"], store=None)
    # encrypted_content 应该不位于包含列表中
    assert "reasoning.encrypted_content" not in out.get("include", [])
    # 但原来的包含项应该仍然存在
    assert "text.output_text" in out["include"]


def test_responses_reasoning_options_not_sent_for_non_reasoning_model():
    llm = LLM(
        model="openai/gpt-4o-mini",
        reasoning_effort="high",
        reasoning_summary="detailed",
    )

    out = select_responses_options(
        llm,
        {},
        include=["message.output_text.logprobs"],
        store=None,
    )

    assert "reasoning" not in out
    assert out["include"] == ["message.output_text.logprobs"]


def test_responses_encrypted_reasoning_not_added_for_non_reasoning_model():
    llm = LLM(model="openai/gpt-4o-mini")

    out = select_responses_options(llm, {}, include=None, store=False)

    assert "include" not in out
    assert "reasoning" not in out


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_llm_responses_end_to_end(mock_responses_call):
    # 配置LLM
    llm = LLM(model="gpt-5-mini")
    # 消息：系统+用户
    sys = Message(role="system", content=[TextContent(text="inst")])
    user = Message(role="user", content=[TextContent(text="hi")])

    # 构建类型为 ResponsesAPIResponse 的用法
    msg = build_responses_message_output(["ok"])
    usage = ResponseAPIUsage(input_tokens=10, output_tokens=5, total_tokens=15)
    resp = ResponsesAPIResponse(
        id="r1",
        created_at=0,
        output=[msg],
        parallel_tool_calls=False,
        tool_choice="auto",
        top_p=None,
        tools=[],
        usage=usage,
        instructions="inst",
        status="completed",
    )

    mock_responses_call.return_value = resp

    result = llm.responses([sys, user])
    # 返回信息为助手文字
    assert result.message.role == "assistant"
    assert [c.text for c in result.message.content if isinstance(c, TextContent)] == [
        "ok"
    ]
    # 遥测应记录使用情况（一项）
    assert len(llm._telemetry.metrics.token_usages) == 1  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5.1-codex-mini",
        "openai/gpt-5.1-codex-mini",
    ],
)
def test_responses_reasoning_effort_none_not_sent_for_gpt_5_1(model):
    llm = LLM(model=model, reasoning_effort=None)
    out = select_responses_options(llm, {}, include=None, store=None)
    # 当reasoning_effort为None时，不应有“推理”键
    assert "reasoning" not in out


def test_chat_and_responses_options_prompt_cache_retention_gpt_5_plus_and_non_gpt():
    # 确认允许：5.1 codex mini 支持每个文档的延长保留
    llm_51_codex_mini = LLM(model="openai/gpt-5.1-codex-mini")
    opts_51_codex_mini_resp = select_responses_options(
        llm_51_codex_mini, {}, include=None, store=None
    )
    assert opts_51_codex_mini_resp.get("prompt_cache_retention") == "24h"

    # 新的 GPT-5.2 变体应包括 prompt_cache_retention
    llm_52 = LLM(model="openai/gpt-5.2")
    assert (
        select_chat_options(llm_52, {}, has_tools=False).get("prompt_cache_retention")
        == "24h"
    )
    assert (
        select_responses_options(llm_52, {}, include=None, store=None).get(
            "prompt_cache_retention"
        )
        == "24h"
    )

    llm_52_chat_latest = LLM(model="openai/gpt-5.2-chat-latest")
    assert (
        select_chat_options(llm_52_chat_latest, {}, has_tools=False).get(
            "prompt_cache_retention"
        )
        == "24h"
    )

    # GPT-5.1（非迷你）应包括prompt_cache_retention； 迷你变体不应该
    llm_51_mini = LLM(model="openai/gpt-5.1-mini")
    opts_51_mini_chat = select_chat_options(llm_51_mini, {}, has_tools=False)
    assert "prompt_cache_retention" not in opts_51_mini_chat

    opts_51_mini_resp = select_responses_options(
        llm_51_mini, {}, include=None, store=None
    )
    assert "prompt_cache_retention" not in opts_51_mini_resp

    llm_5_mini = LLM(model="openai/gpt-5-mini")
    opts_5_mini_chat = select_chat_options(llm_5_mini, {}, has_tools=False)
    assert "prompt_cache_retention" not in opts_5_mini_chat

    opts_5_mini_resp = select_responses_options(
        llm_5_mini, {}, include=None, store=None
    )
    assert "prompt_cache_retention" not in opts_5_mini_resp

    llm_41 = LLM(model="openai/gpt-4.1")
    opts_41_chat = select_chat_options(llm_41, {}, has_tools=False)
    assert opts_41_chat.get("prompt_cache_retention") == "24h"

    opts_41_resp = select_responses_options(llm_41, {}, include=None, store=None)
    assert opts_41_resp.get("prompt_cache_retention") == "24h"

    llm_41_azure = LLM(model="azure/gpt-4.1")
    opts_41_azure_chat = select_chat_options(llm_41_azure, {}, has_tools=False)
    assert "prompt_cache_retention" not in opts_41_azure_chat

    opts_41_azure_resp = select_responses_options(
        llm_41_azure, {}, include=None, store=None
    )
    assert "prompt_cache_retention" not in opts_41_azure_resp

    llm_51_azure = LLM(model="azure/gpt-5.1")
    opts_51_azure_chat = select_chat_options(llm_51_azure, {}, has_tools=False)
    assert "prompt_cache_retention" not in opts_51_azure_chat

    opts_51_azure_resp = select_responses_options(
        llm_51_azure, {}, include=None, store=None
    )
    assert "prompt_cache_retention" not in opts_51_azure_resp

    # 其他非GPT-5模型根本不应该包含它
    llm_other = LLM(model="gpt-4o")
    opts_other_chat = select_chat_options(llm_other, {}, has_tools=False)
    assert "prompt_cache_retention" not in opts_other_chat

    opts_other_resp = select_responses_options(llm_other, {}, include=None, store=None)
    assert "prompt_cache_retention" not in opts_other_resp


def test_responses_options_forwards_prompt_cache_key_when_set():
    """回归测试 #2904。"""
    llm = LLM(model="openai/gpt-5.1")
    assert (
        select_responses_options(
            llm,
            {},
            include=None,
            store=None,
            call_context=LLMCallContext(prompt_cache_key="conv-abc123"),
        ).get("prompt_cache_key")
        == "conv-abc123"
    )


def test_responses_options_omits_prompt_cache_key_when_unset():
    llm = LLM(model="openai/gpt-5.1")
    assert "prompt_cache_key" not in select_responses_options(
        llm, {}, include=None, store=None
    )


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_responses_retries_without_caching_on_prompt_cache_too_small(mock_responses):
    """当 Vertex AI 由于内容较小而拒绝缓存时，responses() 应该
    重试没有提示词缓存，同时保留调用者 kwargs。

    镜像 test_llm_completion.py 中的
    test_completion_retries_without_caching_on_prompt_cache_too_small，但执行响应 API
     路径。 这两
    种方法的签名（``include``、``store``位置参数）和``stream``的解析方式不同，因此它
    们需要独立的覆盖。
    """
    from litellm.exceptions import BadRequestError

    cache_error = BadRequestError(
        (
            "Vertex_aiException BadRequestError - "
            '{"error":{"code":400,'
            '"message":"The cached content is of 1171 tokens. '
            'The minimum token count to start caching is 4096.",'
            '"status":"INVALID_ARGUMENT"}}'
        ),
        model="gemini-3-flash",
        llm_provider="vertex_ai",
    )

    # 为成功的重试构建类型化的 ResponsesAPIResponse
    msg = build_responses_message_output(["Retry succeeded"])
    usage = ResponseAPIUsage(input_tokens=0, output_tokens=0, total_tokens=0)
    success_resp = ResponsesAPIResponse(
        id="r1",
        created_at=0,
        output=[msg],
        parallel_tool_calls=False,
        tool_choice="auto",
        top_p=None,
        tools=[],
        usage=usage,
        instructions="",
        status="completed",
    )
    mock_responses.side_effect = [cache_error, success_resp]

    # 选择支持提示词缓存的模型，is_caching_prompt_active()应该是True，重试分支可以通过
    # responses()路径访问。（Gemini不再使用显式缓存，所以在这里使用Anthropic模型。）
    #
    llm = LLM(
        model="claude-sonnet-4-20250514",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        caching_prompt=True,
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    messages = [
        Message(role="system", content=[TextContent(text="sys")]),
        Message(role="user", content=[TextContent(text="Hello")]),
    ]

    # 传递必须在重试中生存的调用者 kwargs。 ``metadata`` flows through
    # ``**kwargs``（不是命名参数），所以它是最干净的探针
    # ``_caller_kwargs`` 转发修复； ``store`` 练习重试调用签名上的位置参数路径。
    #
    response = llm.responses(
        messages,
        store=False,
        metadata={"trace_id": "abc-123"},
    )

    # 两次调用：第一次调用缓存处于活动状态（失败），第二次调用没有缓存（成功）。
    assert mock_responses.call_count == 2
    assert response.raw_response is success_resp

    # 调用者 kwargs 保留在重试上 - 如果没有 ``_caller_kwargs``，重试会默默地丢弃它们。
    #
    second_kwargs = mock_responses.call_args_list[1].kwargs
    assert second_kwargs.get("store") is False
    assert second_kwargs.get("metadata") == {"trace_id": "abc-123"}


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_aresponses", new_callable=AsyncMock)
async def test_aresponses_retries_without_caching_on_prompt_cache_too_small(
    mock_aresponses,
):
    """异步版本同步响应提示词-缓存太小重试测试。

    确保 aresponses() also 重试 without 提示词当 Vertex AI 因为缓存内容低于最小值而拒
    绝请求时，缓存 token 阈值，以及保留调
    用者 kwargs（位置参数） ``store`` 和
    ``**kwargs`` 元数据）。 镜子
    test_responses_retries_without_caching_on_prompt_cache_too_sm
    all。
    """
    from litellm.exceptions import BadRequestError

    cache_error = BadRequestError(
        (
            "Vertex_aiException BadRequestError - "
            '{"error":{"code":400,'
            '"message":"The cached content is of 1171 tokens. '
            'The minimum token count to start caching is 4096.",'
            '"status":"INVALID_ARGUMENT"}}'
        ),
        model="gemini-3-flash",
        llm_provider="vertex_ai",
    )

    msg = build_responses_message_output(["Retry succeeded"])
    usage = ResponseAPIUsage(input_tokens=0, output_tokens=0, total_tokens=0)
    success_resp = ResponsesAPIResponse(
        id="r1",
        created_at=0,
        output=[msg],
        parallel_tool_calls=False,
        tool_choice="auto",
        top_p=None,
        tools=[],
        usage=usage,
        instructions="",
        status="completed",
    )
    mock_aresponses.side_effect = [cache_error, success_resp]

    # Anthropic 模型，因此 is_caching_prompt_active() 是 True（Gemini 不再使用显式缓存）
    # ； 反映了上面的同步测试。
    #
    llm = LLM(
        model="claude-sonnet-4-20250514",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        caching_prompt=True,
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    messages = [
        Message(role="system", content=[TextContent(text="sys")]),
        Message(role="user", content=[TextContent(text="Hello")]),
    ]

    response = await llm.aresponses(
        messages,
        store=False,
        metadata={"trace_id": "abc-123"},
    )

    assert mock_aresponses.call_count == 2
    assert response.raw_response is success_resp

    second_kwargs = mock_aresponses.call_args_list[1].kwargs
    assert second_kwargs.get("store") is False
    assert second_kwargs.get("metadata") == {"trace_id": "abc-123"}


def _make_wrapped_response_stream_events(text: str = "Hello wrapped stream"):
    msg = build_responses_message_output([text])
    usage = ResponseAPIUsage(input_tokens=1, output_tokens=1, total_tokens=2)
    response = ResponsesAPIResponse(
        id="resp-wrapped-stream",
        created_at=0,
        output=[msg],
        parallel_tool_calls=False,
        tool_choice="auto",
        top_p=None,
        tools=[],
        usage=usage,
        instructions="",
        status="completed",
    )
    events = [
        OutputTextDeltaEvent(
            type=ResponsesAPIStreamEvents.OUTPUT_TEXT_DELTA,
            item_id="m1",
            output_index=0,
            content_index=0,
            delta=text,
        ),
        ResponseCompletedEvent(
            type=ResponsesAPIStreamEvents.RESPONSE_COMPLETED,
            response=response,
        ),
    ]
    return events, response


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_responses_streaming_accepts_wrapped_iterable(mock_responses):
    """响应流式传输不得需要 LiteLLM 的具体迭代器类。"""
    events, completed_response = _make_wrapped_response_stream_events()
    mock_responses.return_value = iter(events)

    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    received = []
    response = llm.responses(
        [Message(role="user", content=[TextContent(text="Hello")])],
        stream=True,
        on_token=received.append,
    )

    assert response.raw_response is completed_response
    assert [chunk.choices[0].delta.content for chunk in received] == [
        "Hello wrapped stream"
    ]


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_aresponses", new_callable=AsyncMock)
async def test_aresponses_streaming_accepts_sync_generator(mock_aresponses):
    """异步响应流式传输还必须容忍同步可迭代包装器。"""
    events, completed_response = _make_wrapped_response_stream_events()

    def _return_sync_generator(*args, **kwargs):
        return (event for event in events)

    mock_aresponses.side_effect = _return_sync_generator

    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    received = []
    response = await llm.aresponses(
        [Message(role="user", content=[TextContent(text="Hello")])],
        stream=True,
        on_token=received.append,
    )

    assert response.raw_response is completed_response
    assert [chunk.choices[0].delta.content for chunk in received] == [
        "Hello wrapped stream"
    ]


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_aresponses", new_callable=AsyncMock)
async def test_aresponses_streaming_accepts_async_generator(mock_aresponses):
    """回归 lmnr 0.7.47 返回 async_generator 包装器。"""
    events, completed_response = _make_wrapped_response_stream_events()

    async def _events():
        for event in events:
            yield event

    mock_aresponses.return_value = _events()

    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    received = []
    response = await llm.aresponses(
        [Message(role="user", content=[TextContent(text="Hello")])],
        stream=True,
        on_token=received.append,
    )

    assert response.raw_response is completed_response
    assert [chunk.choices[0].delta.content for chunk in received] == [
        "Hello wrapped stream"
    ]


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_aresponses", new_callable=AsyncMock)
async def test_aresponses_hung_stream_idle_timeout_retries(mock_aresponses):
    async def _events():
        await asyncio.Event().wait()
        yield

    mock_aresponses.side_effect = lambda **_: _events()
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        timeout=1,
        stream_idle_timeout=0.01,
        num_retries=2,
        retry_min_wait=0,
        retry_max_wait=0,
        retry_multiplier=0,
    )

    with pytest.raises(LLMTimeoutError, match="stream idle timeout"):
        await llm.aresponses(
            [Message(role="user", content=[TextContent(text="Hello")])],
            stream=True,
            on_token=lambda _: None,
        )

    assert mock_aresponses.call_count == 2


@pytest.mark.asyncio
async def test_aresponses_ignored_events_keep_stream_alive():
    stream_events, completed = _make_wrapped_response_stream_events()

    async def events():
        # 总持续时间超过空闲超时； 每个提供者事件都会重置它。
        for _ in range(6):
            await asyncio.sleep(0.1)
            yield SimpleNamespace(type="response.in_progress")
        yield stream_events[-1]

    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        timeout=2,
        stream_idle_timeout=0.5,
        num_retries=0,
    )
    chunks = []
    with patch(
        "openhands.sdk.llm.llm.litellm_aresponses",
        new_callable=AsyncMock,
        return_value=events(),
    ):
        result = await llm.aresponses(
            [
                Message(role="system", content=[TextContent(text="Be helpful")]),
                Message(role="user", content=[TextContent(text="Hello")]),
            ],
            stream=True,
            on_token=chunks.append,
        )

    assert result.raw_response is completed
    assert result.message.content == [TextContent(text="Hello wrapped stream")]
    assert chunks == []


def test_stream_delta_chunks_carry_the_output_item_id():
    """一个输出项的所有增量必须共享一个块 ID。

    更改后的块 ID 读取为重试 (``StreamContext._emit_delta``)，这会重置插槽并删除流屏
    蔽器所保存的文本。
    """
    llm = LLM(model="gpt-5-mini", usage_id="test-stream-id")

    ids = []
    for text in ("one ", "two ", "three"):
        event = OutputTextDeltaEvent(
            type=ResponsesAPIStreamEvents.OUTPUT_TEXT_DELTA,
            item_id="msg_abc",
            output_index=0,
            content_index=0,
            delta=text,
        )
        _, chunk = llm._process_stream_event(event, emit_deltas=True)
        assert chunk is not None
        ids.append(chunk.id)

    assert ids == ["msg_abc"] * 3

    # 不同的输出项是不同的流，因此它的 id 必须不同。
    other = OutputTextDeltaEvent(
        type=ResponsesAPIStreamEvents.OUTPUT_TEXT_DELTA,
        item_id="msg_def",
        output_index=1,
        content_index=0,
        delta="four",
    )
    _, chunk = llm._process_stream_event(other, emit_deltas=True)
    assert chunk is not None
    assert chunk.id == "msg_def"


@pytest.mark.parametrize("mode", ["sync", "async", "async-with-sync-stream"])
@pytest.mark.parametrize(
    "completion_source", ["yielded", "wrapper", "both", "initial", "missing"]
)
async def test_responses_stream_completion_state(mode, completion_source):
    events, yielded_response = _make_wrapped_response_stream_events("yielded")
    wrapper_events, wrapper_response = _make_wrapped_response_stream_events("wrapper")

    class CompletionStream:
        completed_response = (
            wrapper_events[-1] if completion_source == "initial" else None
        )

        def __iter__(self):
            if completion_source in ("yielded", "both"):
                yield from events
            if completion_source in ("wrapper", "both"):
                self.completed_response = wrapper_events[-1]
            elif completion_source == "initial":
                self.completed_response = None

        async def __aiter__(self):
            for event in self:
                yield event

    class SyncCompletionStream:
        def __init__(self):
            self.inner = CompletionStream()

        @property
        def completed_response(self):
            return self.inner.completed_response

        def __iter__(self):
            return iter(self.inner)

    stream = CompletionStream() if mode == "async" else SyncCompletionStream()
    llm = LLM(model="gpt-4o", api_key=SecretStr("test_key"), num_retries=0)
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    received = []

    async def invoke():
        if mode == "sync":
            with patch("openhands.sdk.llm.llm.litellm_responses", return_value=stream):
                return llm.responses(messages, stream=True, on_token=received.append)
        with patch(
            "openhands.sdk.llm.llm.litellm_aresponses",
            new_callable=AsyncMock,
            return_value=stream,
        ):
            return await llm.aresponses(messages, stream=True, on_token=received.append)

    if completion_source == "missing":
        with pytest.raises(LLMNoResponseError, match="without a completed response"):
            await invoke()
    else:
        response = await invoke()
        expected = (
            yielded_response if completion_source == "yielded" else wrapper_response
        )
        assert response.raw_response is expected
        assert [chunk.choices[0].delta.content for chunk in received] == (
            ["yielded"] if completion_source in ("yielded", "both") else []
        )


@pytest.mark.parametrize("mode", ["sync", "async", "async-with-sync-stream"])
@pytest.mark.parametrize(
    "event_type", [SimpleNamespace, BaseLiteLLMOpenAIResponseObject, GenericEvent]
)
async def test_responses_reconstructs_output_without_callback(mode, event_type):
    events, completed = _make_wrapped_response_stream_events()
    output_item = completed.output[0]
    completed.output = []
    events.insert(
        0,
        event_type(type=ResponsesAPIStreamEvents.OUTPUT_ITEM_DONE, item=output_item),
    )

    async def async_events():
        for event in events:
            yield event

    llm = LLM(model="gpt-4o", num_retries=0)
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    with patch.object(LLM, "requires_streaming", new_callable=PropertyMock) as required:
        required.return_value = True
        if mode != "sync":
            with patch(
                "openhands.sdk.llm.llm.litellm_aresponses",
                new_callable=AsyncMock,
                return_value=async_events() if mode == "async" else iter(events),
            ):
                result = await llm.aresponses(messages, stream=True)
        else:
            with patch(
                "openhands.sdk.llm.llm.litellm_responses", return_value=iter(events)
            ):
                result = llm.responses(messages, stream=True)
    assert result.raw_response is completed
    assert completed.output[0] is output_item
    assert result.message.content == [TextContent(text="Hello wrapped stream")]
