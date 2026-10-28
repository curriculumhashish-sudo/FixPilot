from unittest.mock import patch

import pytest
from litellm.exceptions import APIConnectionError
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from pydantic import SecretStr

from openhands.sdk.llm import LLM, LLMResponse, Message, TextContent
from openhands.sdk.llm.exceptions import LLMServiceUnavailableError


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


@pytest.fixture
def default_config():
    return LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_retries_api_connection_error(
    mock_litellm_completion, default_config
):
    """测试 APIConnectionError 是否正确重试。"""
    mock_response = create_mock_response("Retry successful")

    # 模拟对象将 litellm_completion 提高到 APIConnectionError 状态，然后返回一个成功响应
    #
    mock_litellm_completion.side_effect = [
        APIConnectionError(
            message="API connection error",
            llm_provider="test_provider",
            model="test_model",
        ),
        mock_response,
    ]

    # 创建LLM实例并调用完成
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
        usage_id="test-service",
    )
    response = llm.completion(
        messages=[Message(role="user", content=[TextContent(text="Hello!")])],
    )

    # 验证重试是否成功
    assert isinstance(response, LLMResponse)
    assert response.raw_response == mock_response
    assert mock_litellm_completion.call_count == 2  # 初始呼叫 + 1 重试


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_max_retries_api_connection_error(
    mock_litellm_completion, default_config
):
    """测试 APIConnectionError 是否遵守最大重试并映射到 SDK 错误。"""
    # 模拟对象 litellm_completion 多次提高 APIConnectionError
    mock_litellm_completion.side_effect = [
        APIConnectionError(
            message="API connection error 1",
            llm_provider="test_provider",
            model="test_model",
        ),
        APIConnectionError(
            message="API connection error 2",
            llm_provider="test_provider",
            model="test_model",
        ),
        APIConnectionError(
            message="API connection error 3",
            llm_provider="test_provider",
            model="test_model",
        ),
    ]

    # 创建LLM实例并调用完成
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
        usage_id="test-service",
    )

    # 在耗尽所有重试后，完成应引发 SDK 类型错误

    with pytest.raises(LLMServiceUnavailableError) as excinfo:
        llm.completion(
            messages=[Message(role="user", content=[TextContent(text="Hello!")])],
        )

    # 验证是否尝试了正确的重试次实际行为是总共尝试了 num_retries 次
    #
    assert mock_litellm_completion.call_count == default_config.num_retries

    # 异常应包含连接错误信息
    assert "API connection error" in str(excinfo.value)

    # 确保原始提供者异常被保留为原因
    assert isinstance(excinfo.value.__cause__, APIConnectionError)


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_no_retry_on_success(mock_litellm_completion, default_config):
    """测试成功的调用不会触发重试。"""
    mock_response = create_mock_response("Success on first try")
    mock_litellm_completion.return_value = mock_response

    # 创建LLM实例并调用完成
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
        usage_id="test-service",
    )
    response = llm.completion(
        messages=[Message(role="user", content=[TextContent(text="Hello!")])],
    )

    # 验证不需要重试
    assert isinstance(response, LLMResponse)
    assert response.raw_response == mock_response
    assert mock_litellm_completion.call_count == 1  # 仅初始呼叫


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_completion_no_retry_on_non_retryable_error(
    mock_litellm_completion, default_config
):
    """测试不可重试的错误不会触发重试。"""
    # 模拟对象不可重试的错误 (e.g., ValueError)
    mock_litellm_completion.side_effect = ValueError("Invalid input")

    # 创建LLM实例并调用完成
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
        usage_id="test-service",
    )

    # 完成后应立即引发 ValueError，而无需重试
    with pytest.raises(ValueError) as excinfo:
        llm.completion(
            messages=[Message(role="user", content=[TextContent(text="Hello!")])],
        )

    # 验证是否未尝试重试
    assert mock_litellm_completion.call_count == 1  # 仅初始呼叫
    assert "Invalid input" in str(excinfo.value)


def test_retry_configuration_validation():
    """测试重试配置是否已正确验证。"""
    # 用零进行测试重试
    llm_no_retry = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=0,
        usage_id="test-llm",
    )
    assert llm_no_retry.num_retries == 0

    # 使用自定义重试设置进行测试
    llm_custom = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=5,
        retry_min_wait=2,
        retry_max_wait=10,
        retry_multiplier=2.0,
    )
    assert llm_custom.num_retries == 5
    assert llm_custom.retry_min_wait == 2
    assert llm_custom.retry_max_wait == 10
    assert llm_custom.retry_multiplier == 2.0


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_retry_listener_callback(mock_litellm_completion, default_config):
    """测试重试监听器回调在重试期间被调用。"""
    retry_calls = []

    def retry_listener(attempt: int, max_attempts: int, _err: BaseException | None):
        retry_calls.append((attempt, max_attempts, _err))

    mock_response = create_mock_response("Success after retry")

    mock_litellm_completion.side_effect = [
        APIConnectionError(
            message="Connection failed",
            llm_provider="test_provider",
            model="test_model",
        ),
        mock_response,
    ]

    # 使用重试侦听器创建 LLM 实例
    llm = LLM(
        usage_id="test-llm",
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
        retry_listener=retry_listener,
    )
    response = llm.completion(
        messages=[Message(role="user", content=[TextContent(text="Hello!")])],
    )

    # 验证重试监听器是否被调用
    assert isinstance(response, LLMResponse)
    assert response.raw_response == mock_response
    assert len(retry_calls) >= 1  # 应记录至少一次重试次尝试

    # 检查重试侦听器是否收到正确的参数
    if retry_calls:
        attempt, max_attempts, err = retry_calls[0]
        assert isinstance(attempt, int)
        assert isinstance(max_attempts, int)
        assert isinstance(err, APIConnectionError)
        assert attempt >= 1
        assert max_attempts == default_config.num_retries
