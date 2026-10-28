"""
测试重试 LLM 调用时遥测记录是否准确。

该测试确保，当 LLM 调用重试时，仅记录成功尝试的延迟和指标，而不记录所有失败尝试的总时
间加上成功尝试的时间。
"""

import time
from unittest.mock import patch

from litellm.exceptions import APIConnectionError
from litellm.types.utils import Choices, Message as LiteLLMMessage, ModelResponse, Usage
from pydantic import SecretStr

from openhands.sdk.llm import LLM, Message, TextContent


def create_mock_response(
    content: str = "Test response",
    response_id: str = "test-id",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
):
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
        usage=Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_telemetry_records_only_successful_attempt_latency(mock_litellm_completion):
    """
    测试当重试 LLM 调用时，遥测仅记录成功尝试的延迟，而不是所有尝试的累积时间。

    在修复之前，on_request 在重试逻辑之前被调用一次，导致延迟包括所有失败的尝试 + 等
    待时间。 修复后，每次重试尝试都会调用 on_request，因此仅记
    录成功尝试的延迟。
    """
    # 为失败和成功的尝试创建模拟对象个响应
    mock_response = create_mock_response("Success after retry")

    # 模拟 2 次失败，然后成功
    mock_litellm_completion.side_effect = [
        APIConnectionError(
            message="Connection failed 1",
            llm_provider="test_provider",
            model="test_model",
        ),
        APIConnectionError(
            message="Connection failed 2",
            llm_provider="test_provider",
            model="test_model",
        ),
        mock_response,  # 第三次尝试成功
    ]

    # 使用重试配置和最短的等待时间创建 LLM，以加快测试速度
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=3,
        retry_min_wait=1,  # 最短等待 1 秒
        retry_max_wait=1,  # 最长等待时间为 1 秒（与一致计时的最小等待时间相同）
        usage_id="test-service",
    )

    # 记录整个操作的开始时间
    operation_start = time.time()

    # 进行完成调用（将重试两次，然后成功）
    response = llm.completion(
        messages=[Message(role="user", content=[TextContent(text="Hello!")])],
    )

    # 记录总操作时间
    total_operation_time = time.time() - operation_start

    # 验证通话是否成功
    assert response.raw_response == mock_response
    assert mock_litellm_completion.call_count == 3

    # 获取指标来检查记录的延迟
    metrics = llm.metrics

    # 记录的延迟应该远小于总操作时间，因为它应该只包括成功的尝试，而不包括失败的尝试
    #
    recorded_latencies = [latency.latency for latency in metrics.response_latencies]

    # 应该只有一个延迟记录（对于成功的尝试）
    assert len(recorded_latencies) == 1

    recorded_latency = recorded_latencies[0]

    # 记录的延迟应明显小于总操作时间总操作时间包括：
    # - 第一次尝试（失败）+等待时间
    # - 第二次尝试（失败）+等待时间
    # - 第三次尝试（成功）
    #
    # 记录的延迟应仅包括第三次尝试
    assert recorded_latency < total_operation_time * 0.5, (
        f"Recorded latency ({recorded_latency:.3f}s) should be much less "
        f"than total operation time ({total_operation_time:.3f}s)"
    )

    # 记录的延迟应该相对较小（只是模拟对象调用时间），因为我们是模拟，所以它应该非常快（
    # 通常 < 100 毫秒）
    #
    assert recorded_latency < 0.5, (
        f"Recorded latency ({recorded_latency:.3f}s) should be < 0.5s for a mocked call"
    )


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_telemetry_on_request_called_per_retry(mock_litellm_completion):
    """
    测试每次重试尝试是否调用 telemetry.on_request()。

    这可确保每个重试都会重置请求计时器，因此仅记录成功尝试的延迟。

    我们通过检查 on_request() 设置的 _req_start 时间戳来验证这一点。 修复后，应为每个
    重试重置 _req_start。
    """
    # 跟踪 _req_start 值以查看何时调用 on_request
    req_start_values = []

    mock_response = create_mock_response("Success after one retry")

    # 创建一个副作用函数，在每次尝试后捕获 _req_start
    def mock_transport_call_side_effect(*args, **kwargs):
        # 捕获当前 _req_start 值（由 on_request 设置） 这在调用 on_request 之后在
        # _one_attempt 内运行
        #
        nonlocal req_start_values
        req_start_values.append(time.time())

        # 第一次调用失败，第二次成功
        if len(req_start_values) == 1:
            raise APIConnectionError(
                message="Connection failed",
                llm_provider="test_provider",
                model="test_model",
            )
        return mock_response

    mock_litellm_completion.side_effect = mock_transport_call_side_effect

    # 创建 LLM 个实例
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=1,
        usage_id="test-service",
    )

    # 进行完成调用
    response = llm.completion(
        messages=[Message(role="user", content=[TextContent(text="Test")])],
    )

    # 验证通话是否成功
    assert response.raw_response == mock_response

    # 应该尝试两次（一次失败，一次成功）
    assert len(req_start_values) == 2, (
        f"Expected 2 attempts, got {len(req_start_values)}"
    )

    # 验证两次尝试之间存在时间间隔（重试等待时间） 这证明每次尝试都调用了 on_request
    #
    time_gap = req_start_values[1] - req_start_values[0]
    assert time_gap >= 0.5, (
        "There should be a wait time between retry attempts "
        f"(gap: {time_gap:.3f}s, expected >= 0.5s due to 1 second retry wait)"
    )


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_telemetry_metrics_accurate_with_retries(mock_litellm_completion):
    """
    测试当重试发生时所有遥测指标（token、成本、延迟）是否准确。
    """
    # 创建具有特定 token 计数的响应
    mock_response = create_mock_response(
        "Success", prompt_tokens=100, completion_tokens=50
    )

    # 模拟一次失败然后成功
    mock_litellm_completion.side_effect = [
        APIConnectionError(
            message="Connection failed",
            llm_provider="test_provider",
            model="test_model",
        ),
        mock_response,
    ]

    # 创建 LLM 并进行成本跟踪
    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=1,
        usage_id="test-service",
        input_cost_per_token=0.001,
        output_cost_per_token=0.002,
    )

    # 进行完成调用
    response = llm.completion(
        messages=[Message(role="user", content=[TextContent(text="Test")])],
    )

    # 验证通话是否成功
    assert response.raw_response == mock_response

    # 获取指标
    metrics = llm.metrics

    # 词元用量应该只反映成功的尝试
    assert len(metrics.token_usages) == 1
    token_usage = metrics.token_usages[0]
    assert token_usage.prompt_tokens == 100
    assert token_usage.completion_tokens == 50

    # 成本应该只反映成功的尝试
    # 注意：成本计算取决于LiteLLM，所以我们只是验证它是正数
    assert metrics.accumulated_cost > 0

    # 延迟应该只反映成功的尝试（应该很小）
    assert len(metrics.response_latencies) == 1
    assert metrics.response_latencies[0].latency < 0.5


@patch("openhands.sdk.llm.llm.litellm_completion")
def test_telemetry_no_multiple_records_on_retry(mock_litellm_completion):
    """
    测试遥测不会为失败的尝试创建多个记录。

    只有成功的尝试才会产生遥测记录。
    """
    mock_response = create_mock_response("Success")

    # 模拟多次失败然后成功
    mock_litellm_completion.side_effect = [
        APIConnectionError(
            message="Fail 1", llm_provider="test_provider", model="test_model"
        ),
        APIConnectionError(
            message="Fail 2", llm_provider="test_provider", model="test_model"
        ),
        APIConnectionError(
            message="Fail 3", llm_provider="test_provider", model="test_model"
        ),
        mock_response,
    ]

    llm = LLM(
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=5,
        retry_min_wait=1,
        retry_max_wait=1,
        usage_id="test-service",
    )

    # 进行完成调用
    response = llm.completion(
        messages=[Message(role="user", content=[TextContent(text="Test")])],
    )

    assert response.raw_response == mock_response

    metrics = llm.metrics

    # 应该只有一个延迟记录（对于成功的尝试）
    assert len(metrics.response_latencies) == 1

    # 应该只有一个词元用量记录（对于成功的尝试）
    assert len(metrics.token_usages) == 1

    # 应该只有一个成本记录（对于成功的尝试）成本是累积的，所以我们只检查它是否为正
    #
    assert metrics.accumulated_cost > 0
