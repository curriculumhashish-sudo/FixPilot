from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from litellm.exceptions import (
    RateLimitError,
)
from litellm.types.llms.openai import ResponseAPIUsage, ResponsesAPIResponse
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_text import ResponseOutputText
from pydantic import SecretStr

from openhands.sdk import ConversationStats, RegistryEvent
from openhands.sdk.llm import LLM, LLMResponse, Message, MessageToolCall, TextContent
from openhands.sdk.llm._tokenizer import load_chat_template_tokenizer
from openhands.sdk.llm.exceptions import LLMNoResponseError
from openhands.sdk.llm.options.responses_options import select_responses_options
from openhands.sdk.llm.utils.metrics import Metrics, TokenUsage
from openhands.sdk.llm.utils.telemetry import Telemetry
from openhands.sdk.tool.builtins.finish import FinishTool

# 导入常用测试实用程序
from tests.conftest import create_mock_litellm_response


@pytest.fixture
def default_llm():
    return LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        usage_id="default-test-llm",
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )


def test_llm_init_with_default_config(default_llm):
    """使用测试夹具使用默认配置测试 LLM 初始化。"""
    assert default_llm.model == "gpt-4o"
    assert (
        default_llm.api_key is not None
        and default_llm.api_key.get_secret_value() == "test_key"
    )
    assert isinstance(default_llm.metrics, Metrics)
    assert default_llm.metrics.model_name == "gpt-4o"


@pytest.mark.parametrize("api_mode", ["chat", "responses"])
def test_generate_dispatches_to_configured_api(default_llm, api_mode):
    llm = default_llm.model_copy(update={"api_mode": api_mode})
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    response = Mock(spec=LLMResponse)

    with (
        patch.object(LLM, "completion", return_value=response) as completion,
        patch.object(LLM, "responses", return_value=response) as responses,
    ):
        assert llm.generate(messages, store=False) is response

    if api_mode == "responses":
        responses.assert_called_once_with(
            messages=messages,
            tools=None,
            include=None,
            store=False,
            add_security_risk_prediction=False,
            on_token=None,
            call_context=None,
        )
        completion.assert_not_called()
    else:
        completion.assert_called_once_with(
            messages=messages,
            tools=None,
            add_security_risk_prediction=False,
            on_token=None,
            call_context=None,
        )
        responses.assert_not_called()


@pytest.mark.parametrize("api_mode", ["chat", "responses"])
@pytest.mark.asyncio
async def test_agenerate_dispatches_to_configured_api(default_llm, api_mode):
    llm = default_llm.model_copy(update={"api_mode": api_mode})
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    response = Mock(spec=LLMResponse)

    with (
        patch.object(
            LLM, "acompletion", AsyncMock(return_value=response)
        ) as completion,
        patch.object(LLM, "aresponses", AsyncMock(return_value=response)) as responses,
    ):
        assert await llm.agenerate(messages, store=False) is response

    if api_mode == "responses":
        responses.assert_awaited_once_with(
            messages=messages,
            tools=None,
            include=None,
            store=False,
            add_security_risk_prediction=False,
            on_token=None,
            call_context=None,
        )
        completion.assert_not_awaited()
    else:
        completion.assert_awaited_once_with(
            messages=messages,
            tools=None,
            add_security_risk_prediction=False,
            on_token=None,
            call_context=None,
        )
        responses.assert_not_awaited()


@patch("openhands.sdk.llm.utils.model_info.httpx.get")
def test_base_url_for_openhands_provider(mock_get):
    """测试当传输层使用代理时 openhands/ 是否保持公开状态。"""
    # 模拟对象模型信息获取以避免实际 HTTP 调用生产
    mock_get.return_value = Mock(json=lambda: {"data": []})

    llm = LLM(
        model="openhands/claude-sonnet-4-20250514",
        api_key=SecretStr("test-key"),
        usage_id="test-openhands-llm",
    )
    assert llm.model == "openhands/claude-sonnet-4-20250514"
    assert llm.base_url is None
    mock_get.assert_called_once_with(
        "https://llm-proxy.app.all-hands.dev/v1/model/info",
        headers={"Authorization": "Bearer test-key"},
    )


@patch("openhands.sdk.llm.utils.model_info.httpx.get")
def test_base_url_for_openhands_provider_with_explicit_none(mock_get):
    """测试显式 None 是否保留公共配置，而不是已持久化传输层配置。"""
    # 模拟对象模型信息获取以避免实际 HTTP 调用生产
    mock_get.return_value = Mock(json=lambda: {"data": []})

    llm = LLM(
        model="openhands/claude-sonnet-4-20250514",
        api_key=SecretStr("test-key"),
        usage_id="test-openhands-llm",
        base_url=None,
    )
    assert llm.model == "openhands/claude-sonnet-4-20250514"
    assert llm.base_url is None


@patch("openhands.sdk.llm.utils.model_info.httpx.get")
@patch("openhands.sdk.llm.llm.litellm_completion")
def test_openhands_provider_translates_only_for_litellm(mock_completion, mock_get):
    mock_get.return_value = Mock(json=lambda: {"data": []})
    mock_completion.return_value = create_mock_litellm_response("ok")

    llm = LLM(
        model="openhands/claude-haiku-4-5-20251001",
        api_key=SecretStr("test-key"),
        usage_id="test-openhands-transport",
        num_retries=0,
    )

    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    llm.completion(messages=messages)

    assert llm.model == "openhands/claude-haiku-4-5-20251001"
    assert llm.base_url is None
    _, kwargs = mock_completion.call_args
    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    assert kwargs["custom_llm_provider"] == "litellm_proxy"
    assert kwargs["api_base"] == "https://llm-proxy.app.all-hands.dev"
    persisted = llm.to_persisted()
    assert persisted["model"] == "openhands/claude-haiku-4-5-20251001"
    assert "base_url" not in persisted


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_digitalocean_provider_routes_to_openai_compatible_endpoint(mock_completion):
    mock_completion.return_value = create_mock_litellm_response("ok")

    llm = LLM(
        model="digitalocean/glm-5.3",
        api_key=SecretStr("do-key"),
        usage_id="test-digitalocean",
        num_retries=0,
    )
    llm.completion(messages=[Message(role="user", content=[TextContent(text="Hi")])])

    _, kwargs = mock_completion.call_args
    assert kwargs["model"] == "glm-5.3"
    assert kwargs["custom_llm_provider"] == "openai"
    assert kwargs["api_base"] == "https://inference.do-ai.run/v1"
    assert llm.to_persisted()["model"] == "digitalocean/glm-5.3"


@patch("openhands.sdk.llm.utils.model_info.httpx.get")
def test_kimi_k2_5_uses_provider_defaults(mock_get):
    """测试 kimi-k2.5 使用提供商默认值 (None) 作为温度和 top_p。"""
    mock_get.return_value = Mock(json=lambda: {"data": []})

    llm = LLM(
        model="moonshot/kimi-k2.5",
        api_key=SecretStr("test-key"),
        usage_id="test-kimi-llm",
    )
    # 温度和 top_p 都应为 None（使用提供商默认值）
    assert llm.temperature is None
    assert llm.top_p is None

    # 明确的价值观仍应得到尊重
    llm_explicit = LLM(
        model="moonshot/kimi-k2.5",
        api_key=SecretStr("test-key"),
        usage_id="test-kimi-llm-explicit",
        top_p=0.8,
        temperature=0.5,
    )
    assert llm_explicit.top_p == 0.8
    assert llm_explicit.temperature == 0.5


@patch("openhands.sdk.llm.utils.model_info.httpx.get")
def test_base_url_for_openhands_provider_with_custom_url(mock_get):
    """测试 openhands/ 提供者在提供时是否尊重自定义 base_url。"""
    # 模拟对象模型信息获取以避免实际的 HTTP 调用
    mock_get.return_value = Mock(json=lambda: {"data": []})

    custom_url = "https://custom-proxy.example.com/"
    llm = LLM(
        model="openhands/claude-sonnet-4-20250514",
        api_key=SecretStr("test-key"),
        usage_id="test-openhands-llm",
        base_url=custom_url,
    )
    assert llm.base_url == custom_url
    # 应使用自定义 URL 进行调用
    mock_get.assert_called_once()


def test_token_usage_add():
    """测试 TokenUsage 个实例是否可以添加在一起。"""
    # 创建两个 TokenUsage 实例
    usage1 = TokenUsage(
        model="model1",
        prompt_tokens=10,
        completion_tokens=5,
        cache_read_tokens=3,
        cache_write_tokens=2,
        response_id="response-1",
    )

    usage2 = TokenUsage(
        model="model2",
        prompt_tokens=8,
        completion_tokens=6,
        cache_read_tokens=2,
        cache_write_tokens=4,
        response_id="response-2",
    )

    # 将它们加在一起
    combined = usage1 + usage2

    # 验证结果
    assert combined.model == "model1"  # 应该从第一个实例开始就保留模型
    assert combined.prompt_tokens == 18  # 10 + 8
    assert combined.completion_tokens == 11  # 5 + 6
    assert combined.cache_read_tokens == 5  # 3 + 2
    assert combined.cache_write_tokens == 6  # 2 + 4
    assert combined.response_id == "response-1"  # 应保留第一个实例中的 response_id


def test_metrics_merge_accumulated_token_usage():
    """测试累积的词元用量是否在两个指标之间正确合并
    实例。"""
    # 创建两个 Metrics 实例
    metrics1 = Metrics(model_name="model1")
    metrics2 = Metrics(model_name="model2")

    # 为每个添加词元用量
    metrics1.add_token_usage(10, 5, 3, 2, 1000, "response-1")
    metrics2.add_token_usage(8, 6, 2, 4, 1000, "response-2")

    # 验证初始累计词元用量
    metrics1_data = metrics1.get()
    accumulated1 = metrics1_data["accumulated_token_usage"]
    assert accumulated1["prompt_tokens"] == 10
    assert accumulated1["completion_tokens"] == 5
    assert accumulated1["cache_read_tokens"] == 3
    assert accumulated1["cache_write_tokens"] == 2

    metrics2_data = metrics2.get()
    accumulated2 = metrics2_data["accumulated_token_usage"]
    assert accumulated2["prompt_tokens"] == 8
    assert accumulated2["completion_tokens"] == 6
    assert accumulated2["cache_read_tokens"] == 2
    assert accumulated2["cache_write_tokens"] == 4

    # 将指标2合并到指标1中
    metrics1.merge(metrics2)

    # 验证合并累计词元用量
    merged_data = metrics1.get()

    merged_accumulated = merged_data["accumulated_token_usage"]
    assert merged_accumulated["prompt_tokens"] == 18  # 10 + 8
    assert merged_accumulated["completion_tokens"] == 11  # 5 + 6
    assert merged_accumulated["cache_read_tokens"] == 5  # 3 + 2
    assert merged_accumulated["cache_write_tokens"] == 6  # 2 + 4


def test_metrics_diff():
    """测试指标 diff 是否正确计算两个之间的差异
    指标。"""
    # 创建基线指标
    baseline = Metrics(model_name="test-model")
    baseline.add_cost(1.0)
    baseline.add_token_usage(10, 5, 2, 1, 1000, "baseline-response")
    baseline.add_response_latency(0.5, "baseline-response")

    # 使用附加数据创建当前指标
    current = Metrics(model_name="test-model")
    current.merge(baseline)  # 从基线开始
    current.add_cost(2.0)  # 添加更多成本
    current.add_token_usage(15, 8, 3, 2, 1000, "current-response")  # 添加更多 token
    current.add_response_latency(0.8, "current-response")  # 添加更多延迟

    # 计算差异
    diff = current.diff(baseline)

    # 验证 diff 仅包含附加数据
    diff_data = diff.get()
    assert diff_data["accumulated_cost"] == 2.0  # 只需支付额外费用
    assert len(diff_data["costs"]) == 1  # 仅输入额外费用
    assert len(diff_data["token_usages"]) == 1  # 仅附加词元用量
    assert len(diff_data["response_latencies"]) == 1  # 仅额外的延迟

    # 验证累积的词元用量差异
    accumulated_diff = diff_data["accumulated_token_usage"]
    assert accumulated_diff["prompt_tokens"] == 15  # 仅附加token
    assert accumulated_diff["completion_tokens"] == 8
    assert accumulated_diff["cache_read_tokens"] == 3
    assert accumulated_diff["cache_write_tokens"] == 2


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_with_mock(mock_completion):
    """使用模拟的 LiteLLM 测试 LLM 完成情况。"""
    mock_response = create_mock_litellm_response("Test response")
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

    assert isinstance(response, LLMResponse)
    assert response.raw_response == mock_response
    mock_completion.assert_called_once()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_retry_on_rate_limit(mock_completion):
    """测试 LLM 重试的速率限制错误。"""
    mock_response = create_mock_litellm_response("Success after retry")

    mock_completion.side_effect = [
        RateLimitError(
            message="Rate limit exceeded",
            llm_provider="test_provider",
            model="test_model",
        ),
        mock_response,
    ]

    # 应用补丁后创建 LLM
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 测试完成重试
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    response = llm.completion(messages=messages)

    assert isinstance(response, LLMResponse)
    assert response.raw_response == mock_response
    assert mock_completion.call_count == 2  # 第一次调用失败，第二次成功


def test_llm_cost_calculation(default_llm):
    """测试 LLM 成本计算和指标跟踪。"""
    llm = default_llm

    # 测试成本添加
    initial_cost = llm.metrics.accumulated_cost
    llm.metrics.add_cost(1.5)
    assert llm.metrics.accumulated_cost == initial_cost + 1.5

    # 测试费用验证
    with pytest.raises(ValueError, match="Added cost cannot be negative"):
        llm.metrics.add_cost(-1.0)


def test_llm_token_counting(default_llm):
    """测试 LLM token 计数功能。"""
    llm = default_llm

    # 使用 dict 消息进行测试
    messages = [
        Message(role="user", content=[TextContent(text="Hello")]),
        Message(role="assistant", content=[TextContent(text="Hi there!")]),
    ]

    # token 如果模型不支持，计数可能会返回 0，但不应出错
    token_count = llm.get_token_count(messages)
    assert isinstance(token_count, int)
    assert token_count >= 0


@patch("openhands.sdk.llm.llm.token_counter")
def test_llm_token_counting_includes_tools(mock_token_counter, default_llm):
    """测试 LLM token 将工具模式向前计数到 LiteLLM。"""
    mock_token_counter.return_value = 123
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    tools = list(FinishTool.create())

    token_count = default_llm.get_token_count(
        messages,
        tools=tools,
        add_security_risk_prediction=True,
    )

    assert token_count == 123
    _, kwargs = mock_token_counter.call_args
    assert len(kwargs["tools"]) == 1
    assert kwargs["tools"][0]["function"]["name"] == "finish"
    assert "message" in kwargs["tools"][0]["function"]["parameters"]["properties"]


def test_llm_load_chat_template_tokenizer_prefers_transformers(monkeypatch):
    """聊天模板分词器在可用时使用 Transformer。"""

    class FakeTokenizer:
        chat_template = "template"

        def apply_chat_template(self, messages, **kwargs):
            return []

    class FakeAutoTokenizer:
        loaded_identifier = None

        @classmethod
        def from_pretrained(cls, identifier):
            cls.loaded_identifier = identifier
            return FakeTokenizer()

    class FakeTransformers:
        AutoTokenizer = FakeAutoTokenizer

    def fake_import_module(name):
        if name == "transformers":
            return FakeTransformers
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "openhands.sdk.llm._tokenizer.importlib.import_module", fake_import_module
    )

    tokenizer = load_chat_template_tokenizer("model-with-template")

    assert isinstance(tokenizer, FakeTokenizer)
    assert FakeAutoTokenizer.loaded_identifier == "model-with-template"


@patch("openhands.sdk.llm.llm.create_pretrained_tokenizer")
def test_llm_custom_tokenizer_falls_back_without_transformers(
    mock_create_pretrained_tokenizer, monkeypatch
):
    fallback_tokenizer = {
        "type": "huggingface_tokenizer",
        "tokenizer": object(),
    }
    mock_create_pretrained_tokenizer.return_value = fallback_tokenizer

    def fake_import_module(name):
        if name == "transformers":
            raise ModuleNotFoundError(name)
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "openhands.sdk.llm._tokenizer.importlib.import_module", fake_import_module
    )

    llm = LLM(
        model="openai/qwen-test",
        api_key=SecretStr("test_key"),
        custom_tokenizer="Qwen/Qwen3-test",
    )

    assert llm._chat_template_tokenizer is None
    assert llm._tokenizer == fallback_tokenizer


@patch("openhands.sdk.llm.llm.create_pretrained_tokenizer")
def test_llm_custom_tokenizer_falls_back_without_apply_chat_template(
    mock_create_pretrained_tokenizer, monkeypatch
):
    fallback_tokenizer = {
        "type": "huggingface_tokenizer",
        "tokenizer": object(),
    }
    mock_create_pretrained_tokenizer.return_value = fallback_tokenizer

    class FakeAutoTokenizer:
        @classmethod
        def from_pretrained(cls, identifier):
            return object()

    class FakeTransformers:
        AutoTokenizer = FakeAutoTokenizer

    def fake_import_module(name):
        if name == "transformers":
            return FakeTransformers
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "openhands.sdk.llm._tokenizer.importlib.import_module", fake_import_module
    )

    llm = LLM(
        model="openai/qwen-test",
        api_key=SecretStr("test_key"),
        custom_tokenizer="Qwen/Qwen3-test",
    )

    assert llm._chat_template_tokenizer is None
    assert llm._tokenizer == fallback_tokenizer


@patch("openhands.sdk.llm.llm.create_pretrained_tokenizer")
def test_llm_custom_tokenizer_allows_apply_chat_template_without_declared_template(
    mock_create_pretrained_tokenizer, monkeypatch
):
    mock_create_pretrained_tokenizer.return_value = {
        "type": "huggingface_tokenizer",
        "tokenizer": object(),
    }

    class FakeTokenizer:
        chat_template = None

        def apply_chat_template(self, messages, **kwargs):
            return []

    class FakeAutoTokenizer:
        @classmethod
        def from_pretrained(cls, identifier):
            return FakeTokenizer()

    class FakeTransformers:
        AutoTokenizer = FakeAutoTokenizer

    def fake_import_module(name):
        if name == "transformers":
            return FakeTransformers
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(
        "openhands.sdk.llm._tokenizer.importlib.import_module", fake_import_module
    )

    llm = LLM(
        model="openai/qwen-test",
        api_key=SecretStr("test_key"),
        custom_tokenizer="gpt2",
    )

    assert isinstance(llm._chat_template_tokenizer, FakeTokenizer)
    mock_create_pretrained_tokenizer.assert_not_called()


@patch("openhands.sdk.llm.llm.token_counter")
def test_llm_token_counting_prefers_chat_template_tokenizer(
    mock_token_counter, default_llm
):
    """当分词器支持时，token 计数使用 apply_chat_template。"""

    class FakeChatTemplateTokenizer:
        def __init__(self):
            self.calls = []

        def apply_chat_template(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return list(range(321))

    tokenizer = FakeChatTemplateTokenizer()
    default_llm._chat_template_tokenizer = tokenizer
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    tools = list(FinishTool.create())

    token_count = default_llm.get_token_count(
        messages,
        tools=tools,
        add_security_risk_prediction=True,
    )

    assert token_count == 321
    mock_token_counter.assert_not_called()
    applied_messages, kwargs = tokenizer.calls[0]
    assert applied_messages[0]["role"] == "user"
    assert applied_messages[0]["content"] == "Hello"
    assert kwargs["tokenize"] is True
    assert kwargs["add_generation_prompt"] is True
    assert kwargs["tools"][0]["function"]["name"] == "finish"
    assert "message" in kwargs["tools"][0]["function"]["parameters"]["properties"]


@patch("openhands.sdk.llm.llm.token_counter")
def test_llm_chat_template_token_counting_parses_tool_call_arguments(
    mock_token_counter, default_llm
):
    """HF 聊天模板可能需要辅助工具调用参数作为对象。"""

    class FakeChatTemplateTokenizer:
        def __init__(self):
            self.messages = None

        def apply_chat_template(self, messages, **_kwargs):
            self.messages = messages
            return list(range(12))

    tokenizer = FakeChatTemplateTokenizer()
    default_llm._chat_template_tokenizer = tokenizer
    messages = [
        Message(
            role="assistant",
            tool_calls=[
                MessageToolCall(
                    id="call_1",
                    name="finish",
                    arguments='{"message": "done"}',
                    origin="completion",
                )
            ],
        )
    ]

    token_count = default_llm.get_token_count(messages)

    assert token_count == 12
    mock_token_counter.assert_not_called()
    assert tokenizer.messages is not None
    function = tokenizer.messages[0]["tool_calls"][0]["function"]
    assert function["arguments"] == {"message": "done"}


def test_llm_count_tokenized_output_handles_encoding_objects(default_llm):
    """token 计数手柄拥抱面 BatchEncoding/编码形状。"""

    class FakeEncoding:
        def __init__(self):
            self.ids = list(range(321))

    class FakeBatchEncoding:
        def __init__(self):
            self.encodings = [FakeEncoding()]

        def get(self, key):
            if key == "input_ids":
                return list(range(321))
            return None

    class FakeChatTemplateTokenizer:
        def apply_chat_template(self, messages, **kwargs):
            return FakeBatchEncoding()

    default_llm._chat_template_tokenizer = FakeChatTemplateTokenizer()
    messages = [Message(role="user", content=[TextContent(text="Hello")])]

    assert default_llm.get_token_count(messages) == 321


@patch("openhands.sdk.llm.llm.token_counter")
def test_llm_token_counting_falls_back_when_chat_template_fails(
    mock_token_counter, default_llm
):
    """损坏的分词器聊天模板应回退到 LiteLLM 计数。"""

    class BrokenChatTemplateTokenizer:
        def apply_chat_template(self, messages, **kwargs):
            raise RuntimeError("template unavailable")

    default_llm._chat_template_tokenizer = BrokenChatTemplateTokenizer()
    mock_token_counter.return_value = 123
    messages = [Message(role="user", content=[TextContent(text="Hello")])]

    token_count = default_llm.get_token_count(messages)

    assert token_count == 123
    mock_token_counter.assert_called_once()


@pytest.mark.parametrize(
    "tokenized,expected",
    [
        pytest.param([1, 2, 3], 3, id="ids"),
        pytest.param([], 0, id="empty"),
        pytest.param([[1, 2, 3]], 3, id="batched-ids"),
        pytest.param({"input_ids": [1, 2, 3]}, 3, id="mapping"),
        pytest.param(SimpleNamespace(shape=(1, 3)), 3, id="tensor-shape"),
        pytest.param(SimpleNamespace(ids=[1, 2, 3]), 3, id="encoding"),
        pytest.param(
            SimpleNamespace(encodings=[SimpleNamespace(ids=[1, 2, 3])]),
            3,
            id="batch-encodings",
        ),
        pytest.param([SimpleNamespace(ids=[1, 2, 3])], 3, id="encoding-sequence"),
        pytest.param("rendered prompt", 3, id="rendered-string"),
        pytest.param(object(), 17, id="unsupported-falls-back"),
    ],
)
def test_chat_template_token_result_shapes(default_llm, tokenized, expected):
    class Tokenizer:
        def apply_chat_template(self, messages, **kwargs):
            return tokenized

        def encode(self, text):
            assert text == "rendered prompt"
            return SimpleNamespace(ids=[1, 2, 3])

    default_llm._chat_template_tokenizer = Tokenizer()
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    with patch("openhands.sdk.llm.llm.token_counter", return_value=17):
        assert default_llm.get_token_count(messages) == expected


@pytest.mark.parametrize("failure", ["missing-factory", "import-error", "load-error"])
def test_optional_tokenizer_loading_falls_back(monkeypatch, failure):
    class BrokenFactory:
        @classmethod
        def from_pretrained(cls, identifier):
            raise OSError("Tokenizer unavailable")

    def import_transformers(name):
        if failure == "import-error":
            raise RuntimeError("Optional module initialization failed")
        if failure == "missing-factory":
            return SimpleNamespace()
        return SimpleNamespace(AutoTokenizer=BrokenFactory)

    monkeypatch.setattr(
        "openhands.sdk.llm._tokenizer.importlib",
        SimpleNamespace(import_module=import_transformers),
    )
    with patch("openhands.sdk.llm.llm.create_pretrained_tokenizer", return_value=None):
        llm = LLM(model="gpt-4o", custom_tokenizer="local-fixture")
    with patch("openhands.sdk.llm.llm.token_counter", return_value=23):
        assert (
            llm.get_token_count(
                [Message(role="user", content=[TextContent(text="Hello")])]
            )
            == 23
        )


@patch("openhands.sdk.llm.llm.token_counter")
def test_llm_token_counting_mocks_tools_for_non_native_models(mock_token_counter):
    """当禁用本机工具调用时，测试 token 计数提示词-模拟对象个工具。"""
    mock_token_counter.return_value = 456
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        usage_id="non-native-token-count-llm",
        native_tool_calling=False,
        caching_prompt=False,
    )
    messages = [
        Message(role="system", content=[TextContent(text="System prompt")]),
        Message(role="user", content=[TextContent(text="Hello")]),
    ]

    token_count = llm.get_token_count(
        messages,
        tools=list(FinishTool.create()),
        add_security_risk_prediction=True,
    )

    assert token_count == 456
    _, kwargs = mock_token_counter.call_args
    assert kwargs["tools"] is None
    formatted_messages = kwargs["messages"]
    system_text = formatted_messages[0]["content"][0]["text"]
    assert "You have access to the following functions" in system_text
    assert "---- BEGIN FUNCTION #1: finish ----" in system_text
    assert "<parameter=security_risk>LOW</parameter>" in system_text


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_forwards_extra_headers_to_litellm(mock_completion):
    mock_response = create_mock_litellm_response("ok")
    mock_completion.return_value = mock_response

    headers = {"anthropic-beta": "context-1m-2025-08-07"}  # 启用1M 上下文
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        extra_headers=headers,
        num_retries=0,
    )

    messages = [Message(role="user", content=[TextContent(text="Hi")])]
    _ = llm.completion(messages=messages)

    assert mock_completion.call_count == 1
    _, kwargs = mock_completion.call_args
    # 用户提供的 extra_headers 必须达到 LiteLLM。 LLM 也可能注入 OpenRouter HTTP-Referer
    #  / X-Title 默认值（issue #3138），因此仅需验证用户头信息是转发字典的子集。
    #
    forwarded = kwargs.get("extra_headers") or {}
    assert headers.items() <= forwarded.items()


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_llm_responses_forwards_extra_headers_to_litellm(mock_responses):
    # 为每个 LiteLLM 类型构建一个最小但有效的 ResponsesAPIResponse 个实例使用 OpenAI 类
    # 型构建类型化消息输出以满足 LiteLLM 模式
    #
    msg = ResponseOutputMessage.model_construct(
        id="m1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text="ok", annotations=[])],
    )
    usage = ResponseAPIUsage(input_tokens=0, output_tokens=0, total_tokens=0)
    resp = ResponsesAPIResponse(
        id="resp123",
        created_at=0,
        output=[msg],
        usage=usage,
        parallel_tool_calls=False,
        tool_choice="auto",
        top_p=None,
        tools=[],
        instructions="",
        status="completed",
    )

    mock_responses.return_value = resp

    headers = {"anthropic-beta": "context-1m-2025-08-07"}
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        extra_headers=headers,
        num_retries=0,
    )

    messages = [
        Message(role="system", content=[TextContent(text="sys")]),
        Message(role="user", content=[TextContent(text="Hi")]),
    ]
    _ = llm.responses(messages=messages)

    assert mock_responses.call_count == 1
    _, kwargs = mock_responses.call_args
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["custom_llm_provider"] == "openai"
    # 参见test_llm_forwards_extra_headers_to_litellm了解相同的原理。
    forwarded = kwargs.get("extra_headers") or {}
    assert headers.items() <= forwarded.items()


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_completion_does_not_forward_bedrock_api_key(mock_completion):
    mock_response = create_mock_litellm_response("ok")
    mock_completion.return_value = mock_response

    llm = LLM(
        usage_id="test-llm",
        model="us.anthropic.claude-3-sonnet-20240229-v1:0",
        api_key=SecretStr("sk-ant-not-a-bedrock-key"),
        num_retries=0,
    )

    provider_info = llm._provider_info
    assert provider_info is not None

    messages = [Message(role="user", content=[TextContent(text="Hi")])]
    _ = llm.completion(messages=messages)

    assert mock_completion.call_count == 1
    _, kwargs = mock_completion.call_args
    assert kwargs["model"] == provider_info.model
    if provider_info.name is not None:
        assert kwargs["custom_llm_provider"] == provider_info.name
    assert "api_key" not in kwargs


def test_llm_initializes_transport_provider_info():
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=0,
    )

    provider_info = llm._provider_info
    assert provider_info is not None
    assert provider_info.name == "openai"
    assert provider_info.model == "gpt-4o"


@pytest.mark.parametrize("deep", [False, True])
def test_llm_model_copy_refreshes_provider_for_model_update(deep: bool):
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=0,
    )

    copied = llm.model_copy(
        update={"model": "anthropic/claude-3-5-sonnet-20241022"},
        deep=deep,
    )
    response = create_mock_litellm_response("ok")
    messages = [Message(role="user", content=[TextContent(text="Hi")])]

    with (
        patch(
            "openhands.sdk.llm.llm.litellm_completion",
            return_value=response,
        ) as mock_completion,
        patch(
            "openhands.sdk.llm.utils.telemetry.litellm_completion_cost",
            return_value=0.1,
        ) as mock_cost,
    ):
        copied.completion(messages=messages)

    assert copied.model == "anthropic/claude-3-5-sonnet-20241022"
    completion_kwargs = mock_completion.call_args.kwargs
    assert completion_kwargs["model"] == "claude-3-5-sonnet-20241022"
    assert completion_kwargs["custom_llm_provider"] == "anthropic"
    cost_kwargs = mock_cost.call_args.kwargs
    assert cost_kwargs["model"] == "claude-3-5-sonnet-20241022"
    assert cost_kwargs["custom_llm_provider"] == "anthropic"


def test_llm_model_copy_refreshes_provider_for_base_url_update():
    llm = LLM(
        usage_id="test-llm",
        model="unknown-model",
        base_url="https://old.example.com",
        api_key=SecretStr("test_key"),
        num_retries=0,
    )

    copied = llm.model_copy(update={"base_url": "https://new.example.com"})
    kwargs = copied._prepare_transport_kwargs(messages=[], enable_streaming=False)

    assert copied.base_url == "https://new.example.com"
    assert kwargs["model"] == "unknown-model"
    assert kwargs["api_base"] == "https://new.example.com"


@pytest.mark.parametrize(
    ("model", "base_url"),
    [
        # OpenAI-兼容本地端点：常见的自定义基础情况。
        ("openai/local-model", "http://localhost:8000/v1"),
        # LiteLLM 会在提供者解析期间将“/v1" 附加到自定义的 Misstral 基； SDK 仍必须原封
        # 不动地转发用户的价值。
        #
        ("mistral/mistral-small-latest", "https://myproxy.example.com"),
    ],
)
def test_llm_forwards_custom_base_url_as_is(model: str, base_url: str):
    llm = LLM(
        usage_id="test-llm",
        model=model,
        base_url=base_url,
        api_key=SecretStr("test_key"),
        num_retries=0,
    )

    kwargs = llm._prepare_transport_kwargs(messages=[], enable_streaming=False)

    assert kwargs["api_base"] == base_url


def test_llm_forwards_none_api_base_when_no_base_url():
    # LiteLLM 知道许多提供者的默认基础 (e.g. 米斯塔拉尔）。 SDK 不得将它们烘焙到调用中；
    #  api_base 保持 None，因此 LiteLLM 继续解析每次调用的环境变量/默认值，与 main 上的
    # 完全相同。
    #
    llm = LLM(
        usage_id="test-llm",
        model="mistral/mistral-small-latest",
        api_key=SecretStr("test_key"),
        num_retries=0,
    )

    kwargs = llm._prepare_transport_kwargs(messages=[], enable_streaming=False)

    assert kwargs["api_base"] is None


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_merges_llm_extra_headers_with_extended_thinking_default(
    mock_completion,
):
    mock_response = create_mock_litellm_response("ok")
    mock_completion.return_value = mock_response

    llm = LLM(
        usage_id="test-llm",
        model="claude-sonnet-4-5-20250514",
        api_key=SecretStr("test_key"),
        extra_headers={"X-Trace": "1"},
        extended_thinking_budget=1000,
        num_retries=0,
    )

    messages = [Message(role="user", content=[TextContent(text="Hi")])]
    _ = llm.completion(messages=messages)

    assert mock_completion.call_count == 1
    _, kwargs = mock_completion.call_args
    headers = kwargs.get("extra_headers") or {}
    # 预期行为：
    # - 不提供每次调用标头。
    # - 应使用LLM.extra_headers。
    # - 扩展思维默认值（Anthropic-beta）应该合并进来。
    # - 结果保留默认和配置的标头。
    assert headers.get("anthropic-beta") == "interleaved-thinking-2025-05-14"
    assert headers.get("X-Trace") == "1"


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_call_time_extra_headers_override_config_and_defaults(
    mock_completion,
):
    mock_response = create_mock_litellm_response("ok")
    mock_completion.return_value = mock_response

    llm = LLM(
        usage_id="test-llm",
        model="claude-sonnet-4-5-20250514",
        api_key=SecretStr("test_key"),
        # 配置设置了冲突的标头
        extra_headers={"anthropic-beta": "context-1m-2025-08-07", "X-Trace": "1"},
        extended_thinking_budget=1000,
        num_retries=0,
    )

    messages = [Message(role="user", content=[TextContent(text="Hi")])]
    # 预期行为：
    # - 每次调用标头应替换任何 LLM.extra_headers。
    # - 扩展思维默认值仍应合并进来。
    # - 在发生冲突时，每次调用标头获胜（Anthropic-beta => custom-beta）。
    call_headers = {"anthropic-beta": "custom-beta", "Header-Only": "H"}
    _ = llm.completion(messages=messages, extra_headers=call_headers)

    assert mock_completion.call_count == 1
    _, kwargs = mock_completion.call_args
    headers = kwargs.get("extra_headers") or {}
    assert headers.get("anthropic-beta") == "custom-beta"
    assert headers.get("Header-Only") == "H"
    # LLM.config 当用户指定自己的标头时，不应合并标头（我们明确添加的默认值除外）
    #
    assert "X-Trace" not in headers


@patch("openhands.sdk.llm.llm.litellm_responses")
def test_responses_call_time_extra_headers_override_config(mock_responses):
    # 构建最小有效响应响应
    msg = ResponseOutputMessage.model_construct(
        id="m1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text="ok", annotations=[])],
    )
    usage = ResponseAPIUsage(input_tokens=0, output_tokens=0, total_tokens=0)
    resp = ResponsesAPIResponse(
        id="resp123",
        created_at=0,
        output=[msg],
        usage=usage,
        parallel_tool_calls=False,
        tool_choice="auto",
        top_p=None,
        tools=[],
        instructions="",
        status="completed",
    )
    mock_responses.return_value = resp

    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        extra_headers={"X-Trace": "1"},
        num_retries=0,
    )

    messages = [Message(role="user", content=[TextContent(text="Hi")])]
    # 预期行为：
    # - 每次调用标头应替换响应路径的任何 LLM.extra_headers。
    # - 当前未在响应路径上添加 Anthropic 默认值。
    call_headers = {"Header-Only": "H"}
    _ = llm.responses(messages=messages, extra_headers=call_headers)

    assert mock_responses.call_count == 1
    _, kwargs = mock_responses.call_args
    headers = kwargs.get("extra_headers") or {}
    assert headers.get("Header-Only") == "H"
    assert "X-Trace" not in headers


def test_llm_vision_support(default_llm):
    """测试LLM视觉支持检测。"""
    llm = default_llm

    # 视觉支持检测应该没有错误
    vision_active = llm.vision_is_active()
    assert isinstance(vision_active, bool)


def test_llm_function_calling_support(default_llm):
    """TestLLM函数调用支持检测。"""
    llm = default_llm

    # 函数调用支持检测应该没有错误
    native_tool_calling = llm.native_tool_calling
    assert isinstance(native_tool_calling, bool)


def test_llm_function_calling_enabled_by_default():
    """测试所有模型是否默认启用函数调用。"""
    # 使用已知模型进行测试
    llm_known = LLM(
        model="gpt-4o", api_key=SecretStr("test_key"), usage_id="test-known"
    )
    assert llm_known.native_tool_calling is True

    # 使用未知模型进行测试 - 默认情况下仍应启用
    llm_unknown = LLM(
        model="some-unknown-model-xyz",
        api_key=SecretStr("test_key"),
        usage_id="test-unknown",
    )
    assert llm_unknown.native_tool_calling is True


def test_llm_function_calling_can_be_disabled():
    """测试用户可以通过以下方式选择退出函数调用
    native_tool_calling=False."""
    # 使用通常具有函数调用的已知模型进行测试
    llm_disabled = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        native_tool_calling=False,
        usage_id="test-disabled",
    )
    assert llm_disabled.native_tool_calling is False

    # 使用禁用函数调用的未知模型进行测试
    llm_unknown_disabled = LLM(
        model="some-unknown-model-xyz",
        api_key=SecretStr("test_key"),
        native_tool_calling=False,
        usage_id="test-unknown-disabled",
    )
    assert llm_unknown_disabled.native_tool_calling is False


def test_llm_force_string_serializer_auto_detect():
    """测试 force_string_serializer 在 None 时根据模型自动检测。"""
    # 使用需要字符串序列化的旧 DeepSeek 系列进行测试
    llm_deepseek = LLM(
        model="DeepSeek-V3.2-Exp",
        api_key=SecretStr("test_key"),
        usage_id="test-deepseek",
    )
    # 应为 None 且 LLM 级别（自动检测）
    assert llm_deepseek.force_string_serializer is None
    # 格式化消息时，应根据模型特性设置为True
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    formatted = llm_deepseek.format_messages_for_llm(messages)
    # 格式化消息应应用 force_string_serializer 对于 DeepSeek 模型，内容应为字符串（不是
    # 列表）
    #
    assert len(formatted) == 1
    assert isinstance(formatted[0]["content"], str)

    # 使用不需要字符串序列化的模型进行测试
    llm_gpt = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        usage_id="test-gpt",
        caching_prompt=False,  # 禁用缓存
        native_tool_calling=False,  # 禁用工具调用
        disable_vision=True,  # 禁用视觉来测试简单的字符串大小写
    )
    assert llm_gpt.force_string_serializer is None
    # 当没有特殊功能的 GPT 格式化消息时，默认使用字符串
    formatted_gpt = llm_gpt.format_messages_for_llm(messages)
    assert len(formatted_gpt) == 1
    assert isinstance(formatted_gpt[0]["content"], str)


def test_llm_force_string_serializer_override():
    """可以显式设置测试 force_string_serializer 以覆盖自动检测。"""
    # 对于通常不需要的模型设置 force_string_serializer=True
    llm_force_true = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        force_string_serializer=True,
        usage_id="test-force-true",
    )
    assert llm_force_true.force_string_serializer is True
    # force_string_serializer=True should force string serialization
    messages = [
        Message(
            role="user",
            content=[TextContent(text="Test")],
        )
    ]
    formatted = llm_force_true.format_messages_for_llm(messages)
    assert isinstance(formatted[0]["content"], str)

    # 对于通常需要的模型显式设置 force_string_serializer=False 使用支持缓存的模型来测试
    # 列表序列化
    #
    llm_force_false = LLM(
        model="anthropic/claude-sonnet-4-20250514",  # 支持缓存
        api_key=SecretStr("test_key"),
        force_string_serializer=False,
        caching_prompt=True,  # 启用缓存以触发列表序列化
        usage_id="test-force-false",
    )
    assert llm_force_false.force_string_serializer is False
    # 启用缓存时 force_string_serializer=False, 应使用列表
    messages_cache = [
        Message(
            role="user",
            content=[TextContent(text="Test")],
        )
    ]
    formatted_cache = llm_force_false.format_messages_for_llm(messages_cache)
    assert isinstance(formatted_cache[0]["content"], list)


def test_llm_caching_support(default_llm):
    """测试LLM提示词缓存支持检测。"""
    llm = default_llm

    # 缓存支持检测应该没有错误
    caching_active = llm.is_caching_prompt_active()
    assert isinstance(caching_active, bool)


@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-opus-5-5"])
@pytest.mark.parametrize("prefix", ["", "anthropic/", "litellm_proxy/anthropic/"])
@pytest.mark.parametrize("caching_prompt", [True, False])
def test_claude_55_cache_markers_without_metadata(model, prefix, caching_prompt):
    with patch("openhands.sdk.llm.llm.get_litellm_model_info", return_value=None):
        llm = LLM(
            model=f"{prefix}{model}",
            api_key=SecretStr("test-key"),
            caching_prompt=caching_prompt,
        )
    formatted = llm.format_messages_for_llm(
        [
            Message(
                role="system",
                content=[TextContent(text="Static instructions")],
            ),
            Message(role="user", content=[TextContent(text="Hello")]),
        ]
    )
    content = formatted[0]["content"]
    markers = (
        [block["cache_control"] for block in content if "cache_control" in block]
        if isinstance(content, list)
        else []
    )
    assert markers == ([{"type": "ephemeral"}] if caching_prompt else [])


def test_llm_string_representation(default_llm):
    """测试 LLM 字符串表示形式。"""
    llm = default_llm

    str_repr = str(llm)
    # Pydantic 模型在 str() 中不显示“LLM(”前缀，仅显示字段值
    assert "gpt-4o" in str_repr
    assert "model=" in str_repr

    repr_str = repr(llm)
    # repr() 显示“LLM(”前缀，str() 不显示
    assert "LLM(" in repr_str
    assert "gpt-4o" in repr_str


def test_llm_local_detection_based_on_model_name(default_llm):
    """测试LLM基于模型名称的本地模型检测。"""
    llm = default_llm

    # 测试基本模型配置
    assert llm.model == "gpt-4o"
    assert llm.temperature is None  # 使用提供商默认值

    # 使用本地主机进行测试 base_url
    local_llm = LLM(
        model="gpt-4o",
        base_url="http://localhost:8000",
        usage_id="test-llm",
    )
    assert local_llm.base_url == "http://localhost:8000"

    # 使用ollama模型进行测试
    ollama_llm = LLM(
        model="ollama/llama2",
        usage_id="test-llm",
        max_input_tokens=16384,
    )
    assert ollama_llm.model == "ollama/llama2"


def test_llm_local_detection_based_on_base_url():
    """基于base_url测试局部模型检测。"""
    # 使用本地主机进行测试 base_url
    local_llm = LLM(
        model="gpt-4o", base_url="http://localhost:8000", usage_id="test-llm"
    )
    assert local_llm.base_url == "http://localhost:8000"

    # 使用 127.0.0.1 进行测试 base_url
    local_llm_ip = LLM(
        model="gpt-4o", base_url="http://127.0.0.1:8000", usage_id="test-llm"
    )
    assert local_llm_ip.base_url == "http://127.0.0.1:8000"

    # 使用远程模型进行测试
    remote_llm = LLM(
        model="gpt-4o", base_url="https://api.openai.com/v1", usage_id="test-llm"
    )
    assert remote_llm.base_url == "https://api.openai.com/v1"


def test_llm_openhands_provider_rewrite(default_llm):
    """测试不同消息类型的 LLM 消息格式。"""
    llm = default_llm

    # 使用列表中的单个 Message 对象进行测试
    message = [Message(role="user", content=[TextContent(text="Hello")])]
    formatted = llm.format_messages_for_llm(message)
    assert isinstance(formatted, list)
    assert len(formatted) == 1
    assert isinstance(formatted[0], dict)

    # 使用 Message 对象列表进行测试
    messages = [
        Message(role="user", content=[TextContent(text="Hello")]),
        Message(role="assistant", content=[TextContent(text="Hi there!")]),
    ]
    formatted = llm.format_messages_for_llm(messages)
    assert isinstance(formatted, list)
    assert len(formatted) == 2
    assert all(isinstance(msg, dict) for msg in formatted)


def test_metrics_copy():
    """测试是否可以正确复制指标。"""
    original = Metrics(model_name="test-model")
    original.add_cost(1.0)
    original.add_token_usage(10, 5, 2, 1, 1000, "test-response")
    original.add_response_latency(0.5, "test-response")

    # 创建副本
    copied = original.deep_copy()

    # 验证副本具有相同的数据
    original_data = original.get()
    copied_data = copied.get()

    assert original_data["accumulated_cost"] == copied_data["accumulated_cost"]
    assert len(original_data["costs"]) == len(copied_data["costs"])
    assert len(original_data["token_usages"]) == len(copied_data["token_usages"])
    assert len(original_data["response_latencies"]) == len(
        copied_data["response_latencies"]
    )

    # 验证它们是独立的（修改一个不会影响另一个）
    copied.add_cost(2.0)
    assert original.accumulated_cost != copied.accumulated_cost


def test_metrics_log():
    """测试指标记录功能。"""
    metrics = Metrics(model_name="test-model")
    metrics.add_cost(1.5)
    metrics.add_token_usage(10, 5, 2, 1, 1000, "test-response")

    log_output = metrics.log()
    assert isinstance(log_output, str)
    assert "accumulated_cost" in log_output
    assert "1.5" in log_output


def test_llm_config_validation():
    """测试 LLM 配置验证。"""
    # 测试最小有效的配置
    llm = LLM(model="gpt-4o", usage_id="test-llm")
    assert llm.model == "gpt-4o"

    # 使用完整配置进行测试
    full_llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        base_url="https://api.openai.com/v1",
        temperature=0.7,
        max_output_tokens=1000,
        num_retries=3,
        retry_min_wait=1,
        retry_max_wait=10,
    )
    assert full_llm.temperature == 0.7
    assert full_llm.max_output_tokens == 1000


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_llm_no_response_error(mock_completion):
    """测试 LLMNoResponseError 的处理。"""
    from litellm.types.utils import ModelResponse, Usage

    # 模拟对象使用正确的 ModelResponse 进行空响应
    mock_response = ModelResponse(
        id="test-id",
        choices=[],  # 空选项应触发 LLMNoResponseError
        created=1234567890,
        model="gpt-4o",
        object="chat.completion",
        usage=Usage(prompt_tokens=10, completion_tokens=0, total_tokens=10),
    )
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

    # 测试空响应会引发 LLMNoResponseError
    messages = [Message(role="user", content=[TextContent(text="Hello")])]
    with pytest.raises(LLMNoResponseError):
        llm.completion(messages=messages)


def test_response_latency_tracking(default_llm):
    """测试指标中的响应延迟跟踪。"""
    metrics = Metrics(model_name="test-model")

    # 添加一些延迟
    metrics.add_response_latency(0.5, "response-1")
    metrics.add_response_latency(1.2, "response-2")
    metrics.add_response_latency(0.8, "response-3")

    latencies = metrics.response_latencies
    assert len(latencies) == 3
    assert latencies[0].latency == 0.5
    assert latencies[1].latency == 1.2
    assert latencies[2].latency == 0.8

    # 测试负延迟转换为0
    metrics.add_response_latency(-0.1, "response-4")
    assert metrics.response_latencies[-1].latency == 0.0


def test_token_usage_context_window():
    """使用上下文窗口跟踪测试词元用量。"""
    usage = TokenUsage(
        model="test-model",
        prompt_tokens=100,
        completion_tokens=50,
        context_window=4096,
        response_id="test-response",
    )

    assert usage.context_window == 4096
    assert usage.per_turn_token == 0  # 默认值

    # 测试添加保留 max 上下文窗口
    usage2 = TokenUsage(
        model="test-model",
        prompt_tokens=200,
        completion_tokens=75,
        context_window=8192,
        response_id="test-response-2",
    )

    combined = usage + usage2
    assert combined.context_window == 8192  # 应该取最大值
    assert combined.prompt_tokens == 300
    assert combined.completion_tokens == 125


# 遥测测试


def test_telemetry_cost_calculation_header_exception():
    """测试遥测成本计算处理标头解析异常。"""
    # 创建一个带有会导致异常的标头的模拟对象响应
    mock_response = Mock()
    mock_response.headers = {"x-litellm-cost": "invalid-float"}

    metrics = Metrics()
    telemetry = Telemetry(model_name="test-model", metrics=metrics)

    # 模拟对象捕获调试消息的记录器
    with patch("openhands.sdk.llm.utils.telemetry.logger") as mock_logger:
        # 模拟对象 litellm_completion_cost 返回有效成本
        with patch(
            "openhands.sdk.llm.utils.telemetry.litellm_completion_cost",
            return_value=0.001,
        ):
            cost = telemetry._compute_cost(mock_response)

            # 应回退到 LiteLLM 成本计算器
            assert cost == 0.001

            # 应该记录标头解析失败的调试消息（第 139 行）
            mock_logger.debug.assert_called_once()
            assert "Failed to get cost from LiteLLM headers:" in str(
                mock_logger.debug.call_args
            )


def test_enable_encrypted_reasoning_respects_flag_and_defaults_true():
    """
    仅在以下情况下才应包含加密推理：
    - 该请求是无状态的（store=False），并且
    - LLM.enable_encrypted_reasoning 为 True（默认）。

    没有基于模型的自动行为； 严格尊重国旗。
    """
    # 默认行为：标志为 True
    llm_default = LLM(
        model="openai/gpt-5-mini",
        api_key=SecretStr("test_key"),
        usage_id="test-llm-default",
    )
    assert llm_default.enable_encrypted_reasoning is True

    normalized_default = select_responses_options(
        llm_default, {}, include=None, store=None
    )
    assert "reasoning.encrypted_content" in normalized_default.get("include", [])

    # 显式 False 即使对于 GPT 个系列也会禁用加密推理
    llm_disabled = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        enable_encrypted_reasoning=False,
        usage_id="test-llm-disabled",
    )
    assert llm_disabled.enable_encrypted_reasoning is False
    normalized_disabled = select_responses_options(
        llm_disabled, {}, include=None, store=None
    )
    assert "reasoning.encrypted_content" not in normalized_disabled.get("include", [])

    # 当store=True（有状态）时，不包括加密推理
    normalized_stateful = select_responses_options(
        llm_default, {}, include=None, store=True
    )
    assert "reasoning.encrypted_content" not in normalized_stateful.get("include", [])


@patch("openhands.sdk.llm.llm.LLM._transport_call")
def test_unmapped_model_with_logging_enabled(mock_transport):
    """测试启用日志记录的未映射模型不会导致验证错误。

    这是一个集成测试 905 号问题，未映射的模型（不在 LiteLLM 的
    model_prices_and_context_window.json 中）的
    max_input_tokens=None，启用日志时会导致验证错误，因为 context_window 被设置为
    None。
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建一个未映射模型并启用日志记录的 LLM
        llm = LLM(
            model="openai/UnmappedTestModel",
            api_key=SecretStr("test-key"),
            base_url="https://test.example.com/v1",
            log_completions=True,
            log_completions_folder=tmpdir,
        )

        # 验证 max_input_tokens 为 None（未映射模型）
        assert llm.max_input_tokens is None

        # 模拟对象传输层通话
        mock_response = create_mock_litellm_response(
            "Test response", model="UnmappedTestModel"
        )
        mock_transport.return_value = mock_response

        # 这不应引发验证错误
        response = llm.completion(
            messages=[Message(role="user", content=[TextContent(text="test")])]
        )

        assert response is not None
        assert isinstance(response, LLMResponse)

        # 验证词元用量已正确记录且 context_window=0
        metrics = llm.metrics.get()
        assert len(metrics["token_usages"]) == 1
        token_usage = metrics["token_usages"][0]
        assert isinstance(token_usage["context_window"], int)
        # 当 max_input_tokens 为 None 时应默认为 0
        assert token_usage["context_window"] == 0


# 上下文窗口验证测试


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_llm_raises_error_on_small_context_window(mock_get_model_info):
    """测试当上下文窗口太小时 LLM 是否会引发错误。"""
    from openhands.sdk.llm.exceptions import LLMContextWindowTooSmallError
    from openhands.sdk.llm.llm import MIN_CONTEXT_WINDOW_TOKENS

    mock_get_model_info.return_value = {"max_input_tokens": 2048}

    with pytest.raises(LLMContextWindowTooSmallError) as exc_info:
        LLM(
            model="ollama/test-model",
            api_key=SecretStr("test-key"),
            usage_id="test-llm",
        )

    assert exc_info.value.context_window == 2048
    assert exc_info.value.min_required == MIN_CONTEXT_WINDOW_TOKENS
    assert "docs.openhands.dev" in str(exc_info.value)


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_llm_respects_allow_short_context_windows_env_var(mock_get_model_info):
    """测试 ALLOW_SHORT_CONTEXT_WINDOWS 环境变量绕过验证。"""
    import os

    from openhands.sdk.llm.llm import ENV_ALLOW_SHORT_CONTEXT_WINDOWS

    mock_get_model_info.return_value = {"max_input_tokens": 2048}

    # 设置环境变量
    with patch.dict(os.environ, {ENV_ALLOW_SHORT_CONTEXT_WINDOWS: "true"}):
        # 不应该提高
        llm = LLM(
            model="ollama/test-model",
            api_key=SecretStr("test-key"),
            usage_id="test-llm",
        )
        assert llm.max_input_tokens is None
        assert llm.effective_max_input_tokens == 2048


# LLM model_copy 测试


def test_llm_model_copy_preserves_configuration():
    """测试 model_copy 是否保留 LLM 配置。"""
    # 使用自定义配置创建原始 LLM
    original = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="original-llm",
        temperature=0.5,
        max_output_tokens=1000,
        caching_prompt=False,
    )

    # 复制并更新 usage_id
    copied = original.model_copy(update={"usage_id": "copied-llm"})

    # 验证配置是否已保留
    assert copied.model == original.model
    assert copied.temperature == original.temperature
    assert copied.max_output_tokens == original.max_output_tokens
    assert copied.caching_prompt == original.caching_prompt

    # 验证 usage_id 已更新
    assert copied.usage_id == "copied-llm"
    assert original.usage_id == "original-llm"


def test_llm_reset_metrics():
    """测试 reset_metrics 创建新的指标和遥测实例。"""
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )

    # 访问指标以触发延迟初始化
    original_metrics = llm.metrics
    original_telemetry = llm.telemetry
    original_metrics.add_cost(1.0)

    # 重置指标
    llm.reset_metrics()

    # 验证是否创建了新指标
    assert llm._metrics is not None
    assert llm._telemetry is not None
    assert llm.metrics is not original_metrics
    assert llm.telemetry is not original_telemetry
    assert llm.metrics.accumulated_cost == 0.0


def test_issue_2459_restore_metrics_syncs_telemetry():
    """恢复指标必须更新遥测的参考以避免不同步。

    restore_metrics()之后，llm.telemetry.metrics必须与llm.metrics指向同一个对象。 否
    则，恢复后 LLM 会将记录令牌/
    成本调用到过时的指标对象中，并且会计数据会丢失。

    See: https://github.com/OpenHands/software-agent-sdk/issues/2459
    """
    llm = LLM(
        model="gpt-4o-mini",
        api_key=SecretStr("test-key"),
    )

    # 强制遥测创建（在恢复之前模拟正常初始化）
    _ = llm.telemetry

    restored = Metrics(model_name=llm.model)
    llm.restore_metrics(restored)

    assert llm.metrics is restored
    assert llm.telemetry.metrics is restored
    assert llm.telemetry.metrics is llm.metrics


@pytest.fixture
def llm():
    """创建最小的 SDK LLM 进行测试。"""
    return LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-service",
    )


def test_cost_recorded_in_restored_metrics(llm):
    """恢复后通过遥测添加的成本必须计入恢复的指标中。"""
    restored = Metrics(model_name="openai/gpt-4o")
    restored.add_cost(5.00)
    llm.restore_metrics(restored)

    llm.telemetry.metrics.add_cost(0.50)

    assert llm.metrics.accumulated_cost == 5.50
    assert len(llm.metrics.costs) == 2


def test_stale_metrics_not_updated(llm):
    """原始（恢复前）指标不得产生新成本。"""
    original_metrics = llm.metrics

    restored = Metrics(model_name="openai/gpt-4o")
    restored.add_cost(2.00)
    llm.restore_metrics(restored)

    llm.telemetry.metrics.add_cost(0.75)

    assert original_metrics.accumulated_cost == 0.0
    assert llm.metrics.accumulated_cost == 2.75


def test_restore_metrics_telemetry_none():
    """当遥测尚未初始化时，restore_metrics() 不得崩溃。"""
    llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-service",
    )
    llm._telemetry = None

    restored = Metrics(model_name="openai/gpt-4o")
    restored.add_cost(1.00)
    llm.restore_metrics(restored)

    assert llm.metrics is restored
    assert llm.metrics.accumulated_cost == 1.00


def test_conversation_stats_restore_then_track():
    """端到端：ConversationStats 恢复指标，然后跟踪新成本。"""
    saved_metrics = Metrics(model_name="openai/gpt-4o")
    saved_metrics.add_cost(10.00)

    stats = ConversationStats(usage_to_metrics={"agent": saved_metrics})

    with patch("openhands.sdk.llm.llm.litellm_completion"):
        llm = LLM(
            model="openai/gpt-4o",
            api_key=SecretStr("test-key"),
            usage_id="agent",
        )
        event = RegistryEvent(llm=llm)
        stats.register_llm(event)

        assert llm.metrics.accumulated_cost == 10.00

        # 模拟新的 LLM 响应，通过遥测增加成本
        llm.telemetry.metrics.add_cost(0.25)

        assert llm.metrics.accumulated_cost == 10.25
        assert stats.get_combined_metrics().accumulated_cost == 10.25


def test_telemetry_callback_preserved_across_revalidation():
    """遥测回调必须在验证器在 LLM 上重新运行后继续存在。

    将 LLM 包装在另一个 Pydantic 模型中 (e.g. RegistryEvent) 重新运行 LLM 的
    `mode="after"` 验证器。 在此修复
    之前，_set_env_side_effects 无条件重建 _telemetry，默默地删除通过 telemetry.set_*
    _callback() 连接的任何
    回调 — 这破坏了实时统计数据流式传输
    from the agent server (no `key="stats"` events were ever emitted after
    第一个智能体步骤）。
    """
    llm = LLM(
        model="openai/gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="agent",
    )
    fired: list[bool] = []
    llm.telemetry.set_stats_update_callback(lambda: fired.append(True))
    telemetry_before = llm._telemetry

    RegistryEvent(llm=llm)

    assert llm._telemetry is telemetry_before
    assert llm.telemetry._stats_update_callback is not None
    llm.telemetry._stats_update_callback()
    assert fired == [True]


# max_output_tokens 上限测试


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_max_output_tokens_capped_when_using_max_tokens_fallback(mock_get_model_info):
    """测试回落到 max_tokens 时 max_output_tokens 是否受到限制。

    某些提供程序（e.g.、OpenRouter）将 max_tokens 设置为上下文窗口大小而不是输出限制
    。 如果没有上限，这可能会请求超出上下文窗口的输出。

    See: https://github.com/OpenHands/software-agent-sdk/pull/2264
    """
    from openhands.sdk.llm.llm import DEFAULT_MAX_OUTPUT_TOKENS_CAP

    # 模拟 max_tokens = 上下文窗口 (200k) 但未设置 max_output_tokens 的模型
    #
    mock_get_model_info.return_value = {
        "max_tokens": 200000,  # 这是上下文窗口，不是输出限制
        "max_output_tokens": None,
        "max_input_tokens": 200000,
    }

    llm = LLM(
        model="openrouter/anthropic/claude-3-haiku",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )

    # 配置保持未设置状态； 有效运行时间值有上限。
    assert llm.max_output_tokens is None
    effective_max_output_tokens = llm.effective_max_output_tokens
    assert effective_max_output_tokens is not None
    assert effective_max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS_CAP
    assert effective_max_output_tokens < 200000


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_max_output_tokens_uses_actual_value_when_available(mock_get_model_info):
    """测试是否使用实际的 max_output_tokens（如果可用）。"""
    # 使用适当的 max_output_tokens 模拟模型
    mock_get_model_info.return_value = {
        "max_tokens": 8192,
        "max_output_tokens": 8192,
        "max_input_tokens": 200000,
    }

    llm = LLM(
        model="anthropic/claude-3-5-sonnet-latest",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )

    # 应使用实际有效max_output_tokens，不封顶
    assert llm.max_output_tokens is None
    assert llm.effective_max_output_tokens == 8192


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_max_output_tokens_capped_when_model_info_exceeds_default_cap(
    mock_get_model_info,
):
    """自定义网关的高 LiteLLM max_output_tokens 元数据受到限制。"""
    from openhands.sdk.llm.llm import DEFAULT_MAX_OUTPUT_TOKENS_CAP

    mock_get_model_info.return_value = {
        "max_tokens": 262144,
        "max_output_tokens": 131072,
        "max_input_tokens": 262144,
    }

    llm = LLM(
        model="moonshot/kimi-k2.5",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
        base_url="https://qianfan.example.com/v1",
    )

    assert llm.max_output_tokens is None
    assert llm.effective_max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS_CAP


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_max_output_tokens_not_capped_without_custom_base_url(mock_get_model_info):
    """直接 API（无 base_url）保留 LiteLLM 的实数 max_output_tokens。"""
    mock_get_model_info.return_value = {
        "max_output_tokens": 64000,
        "max_tokens": 64000,
        "max_input_tokens": 200000,
    }
    llm = LLM(
        model="claude-opus-4-5",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )
    assert llm.effective_max_output_tokens == 64000


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_max_output_tokens_small_max_tokens_not_capped(mock_get_model_info):
    """测试小 max_tokens 回退方案是否没有不必要的上限。"""
    from openhands.sdk.llm.llm import DEFAULT_MAX_OUTPUT_TOKENS_CAP

    # 模拟 max_tokens 较小的模型（实际输出限制）
    mock_get_model_info.return_value = {
        "max_tokens": 4096,  # 这是实际的输出限制
        "max_output_tokens": None,
        "max_input_tokens": None,
    }

    llm = LLM(
        model="openrouter/test/small-model",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )

    # 应使用实际有效值，因为它低于上限
    assert llm.max_output_tokens is None
    assert llm.effective_max_output_tokens == 4096
    assert llm.effective_max_output_tokens < DEFAULT_MAX_OUTPUT_TOKENS_CAP


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_explicit_max_output_tokens_not_overridden(mock_get_model_info):
    """测试显式设置 max_output_tokens 是否受到尊重。"""
    mock_get_model_info.return_value = {
        "max_tokens": 262144,
        "max_output_tokens": 131072,
        "max_input_tokens": 262144,
    }

    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
        max_output_tokens=32768,  # 明确设置高于上限
    )

    # 应尊重明确的价值
    assert llm.max_output_tokens == 32768
    assert llm.effective_max_output_tokens == 32768


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_max_output_tokens_capped_when_equal_to_context_window(
    mock_get_model_info,
):
    """max_output_tokens == 上下文窗口留下零输入余量。

    严格的提供者 (e.g. AWS 基岩）当 max_output_tokens 填满整个上下文窗口时拒绝所有呼
    叫。
    """
    mock_get_model_info.return_value = {
        "max_output_tokens": 262144,
        "max_input_tokens": 262144,
    }

    llm = LLM(
        model="litellm_proxy/test-model-equal-windows",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )

    assert llm.max_output_tokens is None
    assert llm.effective_max_output_tokens == 131072
    assert llm.max_input_tokens is None
    assert llm.effective_max_input_tokens == 262144


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_max_output_tokens_capped_when_equal_to_max_tokens(
    mock_get_model_info,
):
    """max_output_tokens == max_tokens 也应该减半。

    有些注册表只提供max_tokens（上下文窗口）而没有max_input_tokens。 守卫仍然应该开枪
    。
    """
    mock_get_model_info.return_value = {
        "max_output_tokens": 131072,
        "max_tokens": 131072,
        "max_input_tokens": None,
    }

    llm = LLM(
        model="litellm_proxy/test-model-max-tokens-only",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )

    assert llm.max_output_tokens is None
    assert llm.effective_max_output_tokens == 131072 // 2


@patch("openhands.sdk.llm.llm.get_litellm_model_info")
def test_max_output_tokens_not_capped_when_below_context_window(
    mock_get_model_info,
):
    """max_output_tokens < 上下文窗口应按原样使用。"""
    mock_get_model_info.return_value = {
        "max_output_tokens": 8192,
        "max_input_tokens": 200000,
    }

    llm = LLM(
        model="anthropic/claude-3-5-sonnet-latest",
        api_key=SecretStr("test-key"),
        usage_id="test-llm",
    )

    assert llm.max_output_tokens is None
    assert llm.effective_max_output_tokens == 8192


# LLM 注册表测试
