"""测试 LLM 完成功能、配置和指标跟踪。"""

import asyncio
from collections.abc import Sequence
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from litellm import ChatCompletionMessageToolCall, CustomStreamWrapper
from litellm.types.utils import (
    Choices,
    Delta,
    Function,
    Message as LiteLLMMessage,
    ModelResponse,
    ModelResponseStream,
    PromptTokensDetailsWrapper,
    StreamingChoices,
    Usage,
)
from pydantic import SecretStr

import openhands.sdk.llm.llm as llm_module
from openhands.sdk.llm import (
    LLM,
    Message,
    TextContent,
)
from openhands.sdk.tool.schema import Action
from openhands.sdk.tool.tool import ToolDefinition


def create_mock_response(content: str = "Test response", response_id: str = "test-id"):
    """用于创建结构正确的模拟对象响应的辅助函数。"""
    return ModelResponse(
        id=response_id,
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=LiteLLMMessage(content=content, role="assistant"),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion",
        system_fingerprint="test",
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.mark.parametrize("non_native", [False, True])
def test_opaque_provider_metadata_does_not_reject_valid_chat_text(non_native):
    # LiteLLM 尽管有注释，但在运行时接受不透明的提供程序值。
    provider_fields: dict[str, Any] = {"provider_specific_fields": ["extra"]}
    message = LiteLLMMessage(role="assistant", content="hello", **provider_fields)
    if non_native:
        response = create_mock_response("hello")
        response.choices[0].message = message
        llm = LLM(model="gpt-4o", native_tool_calling=False)
        response = llm.post_response_prompt_mock(response, nonfncall_msgs=[], tools=[])
        assert response.choices[0].message.provider_specific_fields == ["extra"]
        message = response.choices[0].message
    assert Message.from_llm_chat_message(message).content == [TextContent(text="hello")]


# 用于测试的辅助工具类
class _ArgsBasic(Action):
    """测试的基本动作。"""

    param: str


class _MockTool(ToolDefinition[_ArgsBasic, None]):
    """模拟对象用于 LLM 完成测试的工具。"""

    name: ClassVar[str] = "test_tool"

    @classmethod
    def create(cls, conv_state=None, **params) -> Sequence["_MockTool"]:
        return [cls(description="A test tool", action_type=_ArgsBasic)]


@pytest.fixture
def default_config():
    return LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )


async def test_litellm_modify_params_is_process_wide_and_calls_overlap(monkeypatch):
    active_calls = 0
    peak_active_calls = 0
    both_active = asyncio.Event()

    async def completion(**kwargs):
        nonlocal active_calls, peak_active_calls
        active_calls += 1
        peak_active_calls = max(peak_active_calls, active_calls)
        if active_calls == 2:
            both_active.set()
        try:
            await asyncio.wait_for(both_active.wait(), timeout=1)
            assert llm_module.litellm.modify_params is True
            return create_mock_response()
        finally:
            active_calls -= 1

    monkeypatch.setattr(llm_module, "litellm_acompletion", completion)
    first = LLM(model="gpt-4o", api_key="test")
    second = LLM(model="gpt-4o", api_key="test")
    messages = [Message(role="user", content=[TextContent(text="Hello")])]

    await asyncio.gather(
        first.acompletion(messages),
        second.acompletion(messages),
    )

    assert peak_active_calls == 2
    assert llm_module.litellm.modify_params is True


@pytest.mark.parametrize(
    "reasoning,provider_fields",
    [(None, None), ("", {}), ("reasoning", {"signature": "provider-signature"})],
)
def test_prompt_mock_preserves_reasoning_metadata(reasoning, provider_fields):
    raw_response = create_mock_response()
    raw_response.choices[0].message = LiteLLMMessage(
        role="assistant",
        content="<function=test_tool><parameter=param>value</parameter></function>",
        reasoning_content=reasoning,
        provider_specific_fields=provider_fields,
    )
    llm = LLM(model="gpt-4o", native_tool_calling=False, num_retries=0)
    with patch("openhands.sdk.llm.llm.litellm_completion", return_value=raw_response):
        result = llm.completion(
            messages=[Message(role="user", content=[TextContent(text="Run tool")])],
            tools=list(_MockTool.create()),
        )

    assert result.message.tool_calls
    assert result.message.tool_calls[0].name == "test_tool"
    assert result.message.reasoning_content == (reasoning or None)
    assert result.raw_response is raw_response
    output = raw_response.choices[0].message.model_dump()
    assert output.get("reasoning_content") == (reasoning or None)
    assert output.get("provider_specific_fields") == (provider_fields or None)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_basic(mock_completion):
    """测试基本的 LLM 完成功能。"""
    mock_response = create_mock_response("Test response")
    mock_completion.return_value = mock_response
    # 应用补丁后创建 LLM

    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 测试完成
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    response = llm.completion(messages=messages)

    # 检查响应是否为 LLMResponse，并包含预期的属性
    assert response.raw_response == mock_response
    assert response.message.role == "assistant"
    assert isinstance(response.message.content[0], TextContent)
    assert response.message.content[0].text == "Test response"
    assert response.metrics.model_name == "gpt-4o"
    mock_completion.assert_called_once()
    _, kwargs = mock_completion.call_args
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["custom_llm_provider"] == "openai"

    # 此外，验证预检查帮助程序是否识别提供者样式的工具（此处使用空的工具列表只是为了练习
    # 路径）
    #
    cc_tools = []
    assert not llm.should_mock_tool_calls(cc_tools)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_streaming_without_callback_degrades(mock_completion, default_config):
    """流式传输请求没有 on_token 回调降级为普通
    非流式传输完成而不是使运行崩溃 (#4014)。"""
    llm = default_config
    mock_completion.return_value = create_mock_response("Test response")

    messages = [Message(role="user", content=[TextContent(text="Hello")])]

    response = llm.completion(messages=messages, stream=True)

    # 没有流 kwarg 被转发到 LiteLLM — 调用运行在非流式传输范围内。
    assert mock_completion.call_args.kwargs.get("stream") in (None, False)
    assert isinstance(response.message.content[0], TextContent)
    assert response.message.content[0].text == "Test response"


@patch("openhands.sdk.llm.llm.litellm_completion")
@patch("openhands.sdk.llm.llm.litellm.stream_chunk_builder")
def test_llm_completion_streaming_with_callback(mock_stream_builder, mock_completion):
    """测试流式传输和 on_token 回调是否正常工作。"""

    # 创建流块
    chunk1 = ModelResponse(
        id="chatcmpl-test",
        choices=[
            StreamingChoices(
                finish_reason=None,
                index=0,
                delta=Delta(content="Hello", role="assistant"),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion.chunk",
    )

    chunk2 = ModelResponse(
        id="chatcmpl-test",
        choices=[
            StreamingChoices(
                finish_reason=None,
                index=0,
                delta=Delta(content=" world!", role=None),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion.chunk",
    )

    chunk3 = ModelResponse(
        id="chatcmpl-test",
        choices=[
            StreamingChoices(
                finish_reason="stop",
                index=0,
                delta=Delta(content=None, role=None),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion.chunk",
    )

    # 创建一个模拟对象流包装器
    mock_stream = MagicMock(spec=CustomStreamWrapper)
    mock_stream.__iter__.return_value = iter([chunk1, chunk2, chunk3])
    mock_completion.return_value = mock_stream

    # 模拟对象流构建器返回完整响应
    final_response = create_mock_response("Hello world!")
    mock_stream_builder.return_value = final_response

    # 创建LLM
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 跟踪回调接收到的块
    received_chunks = []

    def on_token(chunk):
        received_chunks.append(chunk)

    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    response = llm.completion(messages=messages, stream=True, on_token=on_token)

    # 验证每个块都调用了回调
    assert len(received_chunks) == 3
    assert received_chunks[0] == chunk1
    assert received_chunks[1] == chunk2
    assert received_chunks[2] == chunk3

    # 验证流构建器被调用来组装最终响应
    mock_stream_builder.assert_called_once()

    # 验证最终响应
    assert response.message.role == "assistant"
    assert isinstance(response.message.content[0], TextContent)
    assert response.message.content[0].text == "Hello world!"


@patch("openhands.sdk.llm.llm.litellm_completion")
@patch("openhands.sdk.llm.llm.litellm.stream_chunk_builder")
def test_llm_completion_streaming_with_tools(mock_stream_builder, mock_completion):
    """使用工具调用测试流式传输完成情况。"""

    # 使用工具调用创建流块
    chunk1 = ModelResponse(
        id="chatcmpl-test",
        choices=[
            StreamingChoices(
                finish_reason=None,
                index=0,
                delta=Delta(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        {
                            "index": 0,
                            "id": "call_123",
                            "type": "function",
                            "function": {"name": "test_tool", "arguments": ""},
                        }
                    ],
                ),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion.chunk",
    )

    chunk2 = ModelResponse(
        id="chatcmpl-test",
        choices=[
            StreamingChoices(
                finish_reason=None,
                index=0,
                delta=Delta(
                    content=None,
                    tool_calls=[
                        {
                            "index": 0,
                            "function": {"arguments": '{"param": "value"}'},
                        }
                    ],
                ),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion.chunk",
    )

    chunk3 = ModelResponse(
        id="chatcmpl-test",
        choices=[
            StreamingChoices(
                finish_reason="tool_calls",
                index=0,
                delta=Delta(content=None),
            )
        ],
        created=1234567890,
        model="gpt-4o",
        object="chat.completion.chunk",
    )

    # 创建模拟对象流
    mock_stream = MagicMock(spec=CustomStreamWrapper)
    mock_stream.__iter__.return_value = iter([chunk1, chunk2, chunk3])
    mock_completion.return_value = mock_stream

    # 模拟对象最终回复工具调用
    final_response = create_mock_response("I'll use the tool")
    final_response.choices[0].message.tool_calls = [  # type: ignore
        ChatCompletionMessageToolCall(
            id="call_123",
            type="function",
            function=Function(
                name="test_tool",
                arguments='{"param": "value"}',
            ),
        )
    ]
    mock_stream_builder.return_value = final_response

    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
    )

    received_chunks = []

    def on_token(chunk):
        received_chunks.append(chunk)

    messages = [Message(role="user", content=[TextContent(text="Use test_tool")])]
    tools = list(_MockTool.create())

    response = llm.completion(
        messages=messages, tools=tools, stream=True, on_token=on_token
    )

    # 验证已收到块
    assert len(received_chunks) == 3

    # 验证最终响应有工具调用
    assert response.message.tool_calls is not None
    assert len(response.message.tool_calls) == 1
    assert response.message.tool_calls[0].name == "test_tool"


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_with_tools(mock_completion):
    """使用工具测试 LLM 完成情况。"""
    mock_response = create_mock_response("I'll use the tool")
    mock_response.choices[0].message.tool_calls = [  # type: ignore
        ChatCompletionMessageToolCall(
            id="call_123",
            type="function",
            function=Function(
                name="test_tool",
                arguments='{"param": "value"}',
            ),
        )
    ]
    mock_completion.return_value = mock_response

    # 应用补丁后创建 LLM
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 使用工具完成测试
    messages = [Message(role="user", content=[TextContent(text="Use the test tool")])]

    tools_list = list(_MockTool.create())

    response = llm.completion(messages=messages, tools=tools_list)

    # 检查响应是否为 LLMResponse，并包含预期的属性
    assert response.raw_response == mock_response
    assert response.message.role == "assistant"
    assert isinstance(response.message.content[0], TextContent)
    assert response.message.content[0].text == "I'll use the tool"
    assert response.message.tool_calls is not None
    assert len(response.message.tool_calls) == 1
    assert response.message.tool_calls[0].id == "call_123"
    assert response.message.tool_calls[0].name == "test_tool"
    mock_completion.assert_called_once()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_error_handling(mock_completion):
    """测试LLM完成错误处理。"""
    # 模拟对象异常
    mock_completion.side_effect = Exception("Test error")

    # 应用补丁后创建 LLM
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    messages = [Message(role="user", content=[TextContent(text="Hello")])]

    # 应该传播异常
    with pytest.raises(Exception, match="Test error"):
        llm.completion(messages=messages)


def test_llm_token_counting_basic(default_config):
    """测试基本的 token 计数功能。"""
    llm = default_config

    # 用简单的消息进行测试
    messages = [
        Message(role="user", content=[TextContent(text="Hello")]),
        Message(role="assistant", content=[TextContent(text="Hi there!")]),
    ]

    # token 计数应返回一个非负整数
    token_count = llm.get_token_count(messages)
    assert isinstance(token_count, int)
    assert token_count >= 0


def test_llm_model_info_initialization(default_config):
    """测试模型信息初始化。"""
    llm = default_config

    # 模型信息初始化应该完成且没有错误
    llm._init_model_info_and_caps()

    # 对于未知模型，模型信息可能是 None，这很好
    assert llm.model_info is None or isinstance(llm.model_info, dict)


def test_llm_feature_detection(default_config):
    """测试各种特征检测方法。"""
    llm = default_config

    # 所有特征检测方法都应返回布尔值
    assert isinstance(llm.vision_is_active(), bool)
    assert isinstance(llm.native_tool_calling, bool)
    assert isinstance(llm.is_caching_prompt_active(), bool)


def test_llm_cost_tracking(default_config):
    """测试成本跟踪功能。"""
    llm = default_config

    initial_cost = llm.metrics.accumulated_cost

    # 添加一些成本
    llm.metrics.add_cost(1.5)

    assert llm.metrics.accumulated_cost == initial_cost + 1.5
    assert len(llm.metrics.costs) >= 1


def test_llm_latency_tracking(default_config):
    """测试延迟跟踪功能。"""
    llm = default_config

    initial_count = len(llm.metrics.response_latencies)

    # 添加一些延迟
    llm.metrics.add_response_latency(0.5, "test-response")

    assert len(llm.metrics.response_latencies) == initial_count + 1
    assert llm.metrics.response_latencies[-1].latency == 0.5


def test_llm_token_usage_tracking(default_config):
    """测试词元用量跟踪功能。"""
    llm = default_config

    initial_count = len(llm.metrics.token_usages)

    # 添加一些词元用量
    llm.metrics.add_token_usage(
        prompt_tokens=10,
        completion_tokens=5,
        cache_read_tokens=2,
        cache_write_tokens=1,
        context_window=4096,
        response_id="test-response",
    )

    assert len(llm.metrics.token_usages) == initial_count + 1

    # 检查累计词元用量
    accumulated = llm.metrics.accumulated_token_usage
    assert accumulated.prompt_tokens >= 10
    assert accumulated.completion_tokens >= 5


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_with_custom_params(mock_completion, default_config):
    """使用自定义参数测试 LLM 完成情况。"""
    mock_response = create_mock_response("Custom response")
    mock_completion.return_value = mock_response

    # 使用自定义参数创建配置
    custom_config = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        temperature=0.8,
        max_output_tokens=500,
        top_p=0.9,
    )

    llm = custom_config

    messages = [
        Message(role="user", content=[TextContent(text="Hello with custom params")])
    ]
    response = llm.completion(messages=messages)

    # 检查响应是否为 LLMResponse，并包含预期的属性
    assert response.raw_response == mock_response
    assert response.message.role == "assistant"
    assert isinstance(response.message.content[0], TextContent)
    assert response.message.content[0].text == "Custom response"
    mock_completion.assert_called_once()

    # 验证调用中是否使用了自定义参数
    call_kwargs = mock_completion.call_args[1]
    assert call_kwargs.get("temperature") == 0.8
    assert call_kwargs.get("max_completion_tokens") == 500
    assert call_kwargs.get("top_p") == 0.9


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_non_function_call_mode(mock_completion):
    """使用非函数调用模式（基于提示词的工具调用）测试 LLM 完成情况。"""
    # 创建一个看起来像非函数调用响应但包含文本格式的工具使用情况的模拟对象响应
    #
    mock_response = create_mock_response(
        "I'll help you with that.\n"
        "<function=test_tool>\n"
        "<parameter=param>test_value</parameter>\n"
        "</function>"
    )
    mock_completion.return_value = mock_response

    # 创建 LLM，并将 native_tool_calling 显式设置为 False 这会强制 LLM 使用基于提示词的
    # 工具调用，而不是本机 FC
    #
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        # 这是非功能调用模式的按键设置
        native_tool_calling=False,
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 验证函数调用未激活
    assert not llm.native_tool_calling

    # 使用工具完成测试 - 这应该触发非函数调用路径
    messages = [
        Message(
            role="user",
            content=[TextContent(text="Use the test tool with param 'test_value'")],
        )
    ]

    tools = list(_MockTool.create())

    # 验证工具应为模拟的（非函数调用路径）
    cc_tools = [t.to_openai_tool(add_security_risk_prediction=False) for t in tools]
    assert llm.should_mock_tool_calls(cc_tools)

    # 调用完成 - 这应该经过基于提示词的工具调用路径
    response = llm.completion(messages=messages, tools=tools)

    # 验证响应
    assert response is not None
    mock_completion.assert_called_once()
    # 该响应转换产生了 tool_call 访问消息通过 LLMResponse 接口
    #
    msg = response.message
    # 可选属性的防护：明确将 None 视为失败
    assert getattr(msg, "tool_calls", None) is not None, (
        "Expected tool_calls after post-mock"
    )
    # 此时，tool_calls应该是非None； 明确断言
    assert msg.tool_calls is not None
    tc = msg.tool_calls[0]

    assert tc.name == "test_tool"
    # 确保从助手内容中删除函数调用标记
    if msg.content:
        for content_item in msg.content:
            if isinstance(content_item, TextContent):
                assert "<function=" not in content_item.text

    # 验证是否在没有本机工具参数的情况下进行了调用（因为我们使用的是基于提示词的工具调用
    # ）
    #
    call_kwargs = mock_completion.call_args[1]
    # 在非函数调用模式下，工具不应传递给底层LLM
    assert call_kwargs.get("tools") is None

    # 验证消息是否已针对基于提示词的工具调用进行了修改
    call_messages = mock_completion.call_args[1]["messages"]
    # 由于提示词修改，消息应该与原始消息不同
    assert len(call_messages) >= len(messages)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_function_call_vs_non_function_call_mode(mock_completion):
    """测试函数调用模式和非函数调用模式的区别。"""
    mock_response = create_mock_response("Test response")
    mock_completion.return_value = mock_response

    tools = list(_MockTool.create())
    messages = [Message(role="user", content=[TextContent(text="Use the test tool")])]

    # 启用本机函数调用的测试（gpt-4o 的默认行为）
    llm_native = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        native_tool_calling=True,  # 显式启用本机函数调用
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 验证函数调用是否处于活动状态
    assert llm_native.native_tool_calling
    # 当本机函数调用处于活动状态时不应使用模拟对象工具

    # 禁用本机函数调用的测试
    llm_non_native = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        native_tool_calling=False,  # 显式禁用本机函数调用
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 验证函数调用未激活
    assert not llm_non_native.native_tool_calling

    # 调用两者并验证不同的行为
    mock_completion.reset_mock()
    response_native = llm_native.completion(messages=messages, tools=tools)
    native_call_kwargs = mock_completion.call_args[1]

    mock_completion.reset_mock()
    response_non_native = llm_non_native.completion(messages=messages, tools=tools)
    non_native_call_kwargs = mock_completion.call_args[1]

    # 两者都应该返回 LLMResponse 响应
    assert response_native.raw_response == mock_response
    assert response_native.message.role == "assistant"
    assert response_non_native.raw_response == mock_response
    assert response_non_native.message.role == "assistant"

    # 但底层调用应该不同：本机模式应该将工具传递给 LLM
    #
    assert isinstance(native_call_kwargs.get("tools"), list)
    assert native_call_kwargs["tools"][0]["type"] == "function"
    assert native_call_kwargs["tools"][0]["function"]["name"] == "test_tool"

    # 非本机模式不应传递工具（它们通过提示词处理）
    assert non_native_call_kwargs.get("tools") is None


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_streaming_preserves_cache_read_tokens(mock_completion):
    """测试 prompt_tokens_details 中的 cache_read_tokens 是否存在流式传输。

    回归测试：当流式传输通过 LiteLLM 代理时，代理发送最终仅供使用的块（空选择），其中
     prompt_tokens_details 包括
    cached_tokens。 如果SDK没有要求
    stream_options={"include_usage": True}, litellm's streaming handler
    默默地丢弃这个块并回退到 calculate_total_usage()，它只保留 prompt_tokens/
    completion_tokens — 完全丢失
    prompt_tokens_details.cached_tokens。

    该测试创建了包含一个使用仅有的最终分块（由LiteLLM代理发送）的流式传输块（如实际的
    stream_chunk_builder块），该块包含cached_toke
    ns=4000的使用仅有的最终分块。 它验证：
    1. stream_options={"include_usage": True} 传递给 litellm_completion
    2. cache_read_tokens 在响应指标中正确报告
    """
    # --- 模拟由 LiteLLM 代理发送的块 ---
    content_chunk = ModelResponseStream(
        id="chatcmpl-test",
        choices=[
            StreamingChoices(
                finish_reason=None,
                index=0,
                delta=Delta(content="Hello world", role="assistant"),
            )
        ],
        created=1234567890,
        model="minimax/MiniMax-M2.5",
        object="chat.completion.chunk",
    )

    finish_chunk = ModelResponseStream(
        id="chatcmpl-test",
        choices=[
            StreamingChoices(
                finish_reason="stop",
                index=0,
                delta=Delta(content=None, role=None),
            )
        ],
        created=1234567890,
        model="minimax/MiniMax-M2.5",
        object="chat.completion.chunk",
    )

    # 最终仅供使用的块（空选择）——这是当上游设置 stream_options={"include_usage": True}
    # 时代理发送的块。
    #
    usage_chunk = ModelResponseStream(
        id="chatcmpl-test",
        choices=[],
        created=1234567890,
        model="minimax/MiniMax-M2.5",
        object="chat.completion.chunk",
        usage=Usage(
            prompt_tokens=5000,
            completion_tokens=100,
            total_tokens=5100,
            prompt_tokens_details=PromptTokensDetailsWrapper(cached_tokens=4000),
        ),
    )

    mock_stream = MagicMock(spec=CustomStreamWrapper)
    mock_stream.__iter__.return_value = iter([content_chunk, finish_chunk, usage_chunk])
    mock_completion.return_value = mock_stream

    llm = LLM(
        usage_id="test-llm",
        model="minimax/MiniMax-M2.5",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    received_chunks = []
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    response = llm.completion(
        messages=messages, stream=True, on_token=received_chunks.append
    )

    # 仅供使用的块必须到达SDK（不被丢弃）
    assert len(received_chunks) == 3

    # stream_chunk_builder 必须保留 prompt_tokens_details。 ModelResponse 将“用法”存储为
    # 额外的（动态）字段，因此 Pyright 无法静态地看到它 — 转换为 Any 以进行属性访问。
    #
    raw_resp: Any = response.raw_response
    assert raw_resp.usage is not None
    assert raw_resp.usage.prompt_tokens == 5000
    assert raw_resp.usage.completion_tokens == 100
    assert raw_resp.usage.prompt_tokens_details is not None
    assert raw_resp.usage.prompt_tokens_details.cached_tokens == 4000

    # 遥测必须记录 prompt_tokens_details 中的 cache_read_tokens
    acc = response.metrics.accumulated_token_usage
    assert acc is not None
    assert acc.cache_read_tokens == 4000

    # 验证 stream_options={"include_usage": True} 已传递给 LiteLLM
    call_kwargs = mock_completion.call_args
    assert call_kwargs is not None
    actual_stream_options = call_kwargs.kwargs.get("stream_options") or call_kwargs[
        1
    ].get("stream_options")
    assert actual_stream_options == {"include_usage": True}, (
        f"Expected stream_options={{include_usage: True}}, got {actual_stream_options}"
    )


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_retries_without_caching_on_prompt_cache_too_small(
    mock_completion,
):
    """当 Vertex AI 由于内容较小而拒绝缓存时，重试无缓存。"""
    from litellm.exceptions import BadRequestError

    # 第一次调用引发“缓存太小”错误，第二次调用成功
    cache_error = BadRequestError(
        (
            "Vertex_aiException BadRequestError - "
            '{"error":{"code":400,'
            '"message":"The cached content is of 1171 tokens. '
            'The minimum token count to start caching is 4096.",'
            '"status":"INVALID_ARGUMENT"}}'
        ),
        model="gemini-3.5-flash",
        llm_provider="vertex_ai",
    )
    mock_response = create_mock_response("Retry succeeded")
    mock_completion.side_effect = [cache_error, mock_response]

    llm = LLM(
        model="claude-sonnet-4-20250514",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        caching_prompt=True,
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    # 通过 **kwargs 传递一个 kwarg 来验证 _caller_kwargs 在重试上的保存。
    response = llm.completion(messages=messages, metadata={"trace": "sync"})

    # 应该在重试之后成功，无需缓存
    assert response.raw_response == mock_response
    # 两次调用：第一次使用缓存（失败），第二次不使用缓存（成功）
    assert mock_completion.call_count == 2

    # 第一个调用 SHOULD 有 cache_control 个标记
    first_call_kwargs = mock_completion.call_args_list[0].kwargs
    first_messages = first_call_kwargs.get("messages", [])
    first_has_cache = any(
        "cache_control" in str(block)
        for msg in first_messages
        for block in (
            msg.get("content", []) if isinstance(msg.get("content"), list) else []
        )
    )
    assert first_has_cache, "First call should include cache_control markers"

    # 第二次调用应该不有 cache_control 标记
    second_call_kwargs = mock_completion.call_args_list[1].kwargs
    second_messages = second_call_kwargs.get("messages", [])
    second_has_cache = any(
        "cache_control" in str(block)
        for msg in second_messages
        for block in (
            msg.get("content", []) if isinstance(msg.get("content"), list) else []
        )
    )
    assert not second_has_cache, "Retry should not include cache_control markers"

    # 调用者 kwargs 保留在重试上 - 如果没有 _caller_kwargs，重试会默默地丢弃它们。
    #
    assert second_call_kwargs.get("metadata") == {"trace": "sync"}


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_acompletion", new_callable=AsyncMock)
async def test_acompletion_retries_without_caching_on_prompt_cache_too_small(
    mock_acompletion,
):
    """异步版本同步提示词-缓存太小重试测试。

    当 Vertex AI 由于内容较小而拒绝缓存时，acompletion() 应该重试而没有提示词缓存，同
    时保留调用者 kwargs。 镜子test_complet
    ion_retries_without_caching_on_prompt_cache_too_small。
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
        model="gemini-3.5-flash",
        llm_provider="vertex_ai",
    )
    mock_response = create_mock_response("Retry succeeded")
    mock_acompletion.side_effect = [cache_error, mock_response]

    llm = LLM(
        model="claude-sonnet-4-20250514",
        api_key=SecretStr("test_key"),
        usage_id="test-llm",
        caching_prompt=True,
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    # 通过 **kwargs 传递一个 kwarg 来验证 _caller_kwargs 在重试上的保存。
    response = await llm.acompletion(messages=messages, metadata={"trace": "abc"})

    # 应该在重试之后成功，无需缓存
    assert response.raw_response == mock_response
    # 两次调用：第一次使用缓存（失败），第二次不使用缓存（成功）
    assert mock_acompletion.call_count == 2

    # 第一个调用 SHOULD 有 cache_control 个标记
    first_call_kwargs = mock_acompletion.call_args_list[0].kwargs
    first_messages = first_call_kwargs.get("messages", [])
    first_has_cache = any(
        "cache_control" in str(block)
        for msg in first_messages
        for block in (
            msg.get("content", []) if isinstance(msg.get("content"), list) else []
        )
    )
    assert first_has_cache, "First call should include cache_control markers"

    # 第二次调用应该不有 cache_control 标记
    second_call_kwargs = mock_acompletion.call_args_list[1].kwargs
    second_messages = second_call_kwargs.get("messages", [])
    second_has_cache = any(
        "cache_control" in str(block)
        for msg in second_messages
        for block in (
            msg.get("content", []) if isinstance(msg.get("content"), list) else []
        )
    )
    assert not second_has_cache, "Retry should not include cache_control markers"

    # 调用者 kwargs 保留在重试上 - 如果没有 _caller_kwargs，重试会默默地丢弃它们。
    #
    assert second_call_kwargs.get("metadata") == {"trace": "abc"}


# ---------------------------------------------------------------------------
# 流式传输路径容差：SDK 必须接受任何可迭代的
# ``ModelResponseStream`` 块，而不仅仅是 ``litellm.CustomStreamWrapper``。 第三方
# LiteLLM 包装器 (e.g. 在 pinned 范围内的 lmnr 的 instrumentor 可以替换流式传输调用中的
# 容器类型，这些调用在 ``_transport_call`` / ``_atransport_call`` 中曾经触发 assert（
# issue #3972）。
# ---------------------------------------------------------------------------


def _make_streaming_chunks(text: str = "Hello world!"):
    """构建测试中使用的三块 ``ModelResponseStream`` 序列。"""
    chunks = [
        ModelResponseStream(
            id="chatcmpl-test",
            choices=[
                StreamingChoices(
                    finish_reason=None,
                    index=0,
                    delta=Delta(content="Hello", role="assistant"),
                )
            ],
            created=1234567890,
            model="gpt-4o",
            object="chat.completion.chunk",
        ),
        ModelResponseStream(
            id="chatcmpl-test",
            choices=[
                StreamingChoices(
                    finish_reason=None,
                    index=0,
                    delta=Delta(content=" world!", role=None),
                )
            ],
            created=1234567890,
            model="gpt-4o",
            object="chat.completion.chunk",
        ),
        ModelResponseStream(
            id="chatcmpl-test",
            choices=[
                StreamingChoices(
                    finish_reason="stop",
                    index=0,
                    delta=Delta(content=None, role=None),
                )
            ],
            created=1234567890,
            model="gpt-4o",
            object="chat.completion.chunk",
        ),
    ]
    assert "".join((c.choices[0].delta.content or "") for c in chunks) == text
    return chunks


@patch("openhands.sdk.llm.llm.litellm_completion")
@patch("openhands.sdk.llm.llm.litellm.stream_chunk_builder")
def test_streaming_accepts_plain_iterator(mock_stream_builder, mock_completion):
    """同步迭代器（无 ``CustomStreamWrapper``）仍必须驱动流式传输。

    回归测试问题 #3972：``_transport_call`` 用于断言
    ``isinstance(ret, CustomStreamWrapper)``; 当 lmnr 的 LiteLLM 工具用普通生成器替换
    包装器时，断言在处理任何块
    之前失败。
    """
    chunks = _make_streaming_chunks()
    mock_completion.return_value = iter(chunks)
    mock_stream_builder.return_value = create_mock_response("Hello world!")

    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    received: list[ModelResponseStream] = []
    response = llm.completion(
        messages=[Message(role="user", content=[TextContent(text="Hi")])],
        stream=True,
        on_token=received.append,
    )

    assert received == chunks
    mock_stream_builder.assert_called_once()
    assert response.message.role == "assistant"


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_acompletion", new_callable=AsyncMock)
@patch("openhands.sdk.llm.llm.litellm.stream_chunk_builder")
async def test_streaming_accepts_async_generator(mock_stream_builder, mock_acompletion):
    """异步发电机（不是 ``CustomStreamWrapper``）仍必须驱动流式传输。

    镜像问题 #3972 中 lmnr 包装器的确切行为：包装的调用返回
    ``process_streaming_coroutine()``（一个
    ``async_generator`` 对象），而不是 ``CustomStreamWrapper``。 SDK 必须透明地迭代它
    。
    """

    async def _chunks():
        for chunk in _make_streaming_chunks():
            yield chunk

    mock_acompletion.return_value = _chunks()
    mock_stream_builder.return_value = create_mock_response("Hello world!")

    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    received: list[ModelResponseStream] = []
    response = await llm.acompletion(
        messages=[Message(role="user", content=[TextContent(text="Hi")])],
        stream=True,
        on_token=received.append,
    )

    assert len(received) == 3
    mock_stream_builder.assert_called_once()
    assert response.message.role == "assistant"


@pytest.mark.asyncio
@patch("openhands.sdk.llm.llm.litellm_acompletion", new_callable=AsyncMock)
@patch("openhands.sdk.llm.llm.litellm.stream_chunk_builder")
async def test_streaming_accepts_sync_generator_in_async_path(
    mock_stream_builder, mock_acompletion
):
    """从异步传输层路径返回的同步生成器必须工作。

    针对 Engel 在 PR #3975 审查意见中提出问题的回归测试：lmnr 0.7.47 的LiteLLM包装器
    会包装
    ``litellm.completion``（同步），产生的同步生成器会经由 ``litellm_acompletion`` 向
    上传播。 因此，等待的值是一个普通的
     ``generator``（没有 ``__aiter__``）而不是异步生成器。 ``_atransport_call`` 必须
     在运行时检测到这一点，并通过普通的
     ``for`` 而不是 ``async for`` 进行迭代。
    """
    chunks = _make_streaming_chunks()

    def _return_sync_generator(*args, **kwargs):
        # 在 lmnr-异步情况下，``await litellm_acompletion(...)`` 计算为该值 — 一个普通的
        # 同步生成器。
        #
        return (c for c in chunks)

    mock_acompletion.side_effect = _return_sync_generator
    mock_stream_builder.return_value = create_mock_response("Hello world!")

    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    received: list[ModelResponseStream] = []
    response = await llm.acompletion(
        messages=[Message(role="user", content=[TextContent(text="Hi")])],
        stream=True,
        on_token=received.append,
    )

    assert received == chunks
    mock_stream_builder.assert_called_once()
    assert response.message.role == "assistant"
