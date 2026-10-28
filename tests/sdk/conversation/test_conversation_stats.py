import tempfile
import uuid
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, ConversationStats, LLMRegistry, RegistryEvent
from openhands.sdk.io.local import LocalFileStore
from openhands.sdk.llm.utils.metrics import Metrics


# 测试 UUIDs
TEST_CONVERSATION_ID = uuid.UUID("12345678-1234-5678-9abc-123456789abc")
CONV_MERGE_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
CONV_MERGE_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def mock_file_store():
    """创建模拟对象文件存储以进行测试。"""
    return LocalFileStore(root=tempfile.mkdtemp())


@pytest.fixture
def conversation_stats(mock_file_store):
    """创建一个 ConversationStats 实例用于测试。"""
    return ConversationStats()


@pytest.fixture
def mock_llm_registry():
    """创建正确模拟 LLM 注册的模拟对象 LLM 注册表。"""
    registry = LLMRegistry()
    return registry


@pytest.fixture
def connected_registry_and_stats(mock_llm_registry, conversation_stats):
    """正确连接 LLMRegistry 和 ConversationStats。"""
    # 订阅 LLM 注册表事件以跟踪指标
    mock_llm_registry.subscribe(conversation_stats.register_llm)
    return mock_llm_registry, conversation_stats


def test_get_combined_metrics(conversation_stats):
    """测试组合指标的计算是否正确。"""
    # 添加具有指标的多个使用组
    usage1 = "usage1"
    metrics1 = Metrics(model_name="gpt-4")
    metrics1.add_cost(0.05)
    metrics1.add_token_usage(
        prompt_tokens=100,
        completion_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=8000,
        response_id="resp1",
    )

    usage2 = "usage2"
    metrics2 = Metrics(model_name="gpt-3.5")
    metrics2.add_cost(0.02)
    metrics2.add_token_usage(
        prompt_tokens=200,
        completion_tokens=100,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=4000,
        response_id="resp2",
    )

    conversation_stats.usage_to_metrics[usage1] = metrics1
    conversation_stats.usage_to_metrics[usage2] = metrics2

    # 获取组合指标
    combined = conversation_stats.get_combined_metrics()

    # 验证组合指标
    assert combined.accumulated_cost == 0.07  # 0.05 + 0.02
    assert combined.accumulated_token_usage.prompt_tokens == 300  # 100 + 200
    assert combined.accumulated_token_usage.completion_tokens == 150  # 50 + 100
    assert combined.accumulated_token_usage.context_window == 8000  # 最大 8000 和 4000


def test_get_metrics_for_usage(conversation_stats):
    """测试是否正确检索特定用途的指标。"""
    # 添加带有指标的用法
    usage_id = "test-usage"
    metrics = Metrics(model_name="gpt-4")
    metrics.add_cost(0.05)
    conversation_stats.usage_to_metrics[usage_id] = metrics

    # 获取使用情况的指标
    retrieved_metrics = conversation_stats.get_metrics_for_usage(usage_id)

    # 验证指标
    assert retrieved_metrics.accumulated_cost == 0.05
    assert retrieved_metrics is metrics  # 应该是同一个对象

    # 测试获取不存在的使用情况的指标使用特定的异常消息模式而不是盲目的异常
    #
    with pytest.raises(Exception, match="LLM usage does not exist"):
        conversation_stats.get_metrics_for_usage("non-existent-usage")


def test_register_llm_with_new_usage(conversation_stats):
    """测试注册新的 LLM 用法。"""
    # 修补 LLM 类以避免实际的 API 调用
    with patch("openhands.sdk.llm.llm.litellm_completion"):
        llm = LLM(
            usage_id="new-service",
            model="gpt-4o",
            api_key=SecretStr("test_key"),
            num_retries=2,
            retry_min_wait=1,
            retry_max_wait=2,
        )

        # 为此用途创建一个注册表事件
        usage_id = "new-service"
        event = RegistryEvent(llm=llm)

        # 注册 LLM
        conversation_stats.register_llm(event)

        # 验证使用情况是否已注册
        assert usage_id in conversation_stats.usage_to_metrics
        assert conversation_stats.usage_to_metrics[usage_id] is llm.metrics


def test_register_llm_with_restored_metrics(conversation_stats):
    """测试使用恢复的指标注册 LLM 使用情况。"""
    # 创建恢复的指标
    usage_id = "restored-service"
    restored_metrics = Metrics(model_name="gpt-4")
    restored_metrics.add_cost(0.1)
    conversation_stats.usage_to_metrics = {usage_id: restored_metrics}

    # 修补 LLM 类以避免实际的 API 调用
    with patch("openhands.sdk.llm.llm.litellm_completion"):
        llm = LLM(
            usage_id=usage_id,
            model="gpt-4o",
            api_key=SecretStr("test_key"),
            num_retries=2,
            retry_min_wait=1,
            retry_max_wait=2,
        )

        # 创建注册表事件
        event = RegistryEvent(llm=llm)

        # 注册 LLM
        conversation_stats.register_llm(event)

        # 验证使用情况是否已通过恢复的指标进行注册
        assert usage_id in conversation_stats.usage_to_metrics
        assert conversation_stats.usage_to_metrics[usage_id] is llm.metrics
        assert llm.metrics is not None
        assert llm.metrics.accumulated_cost == 0.1  # 恢复成本

        assert usage_id in conversation_stats._restored_usage_ids


def test_llm_registry_notifications(connected_registry_and_stats):
    """测试 LLM 注册表通知是否更新使用指标。"""
    mock_llm_registry, conversation_stats = connected_registry_and_stats

    # 通过注册表创建一个新的LLM
    usage_id = "test-usage"

    # 直接创建LLM
    llm = LLM(
        usage_id=usage_id,
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 将 LLM 添加到注册表（这应该会触发通知）
    mock_llm_registry.add(llm)

    # 验证对话统计中已注册使用情况
    assert usage_id in conversation_stats.usage_to_metrics
    assert conversation_stats.usage_to_metrics[usage_id] is llm.metrics

    # 将一些指标添加到 LLM
    assert llm.metrics is not None
    llm.metrics.add_cost(0.05)
    llm.metrics.add_token_usage(
        prompt_tokens=100,
        completion_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=8000,
        response_id="resp1",
    )

    # 验证指标是否反映在对话统计信息中
    assert conversation_stats.usage_to_metrics[usage_id].accumulated_cost == 0.05
    assert (
        conversation_stats.usage_to_metrics[
            usage_id
        ].accumulated_token_usage.prompt_tokens
        == 100
    )
    assert (
        conversation_stats.usage_to_metrics[
            usage_id
        ].accumulated_token_usage.completion_tokens
        == 50
    )

    # 获取组合指标并验证
    combined = conversation_stats.get_combined_metrics()
    assert combined.accumulated_cost == 0.05
    assert combined.accumulated_token_usage.prompt_tokens == 100
    assert combined.accumulated_token_usage.completion_tokens == 50


def test_multiple_llm_usages(connected_registry_and_stats):
    """测试多个 LLM 用途的跟踪指标。"""
    mock_llm_registry, conversation_stats = connected_registry_and_stats

    # 通过注册表创建多个LLMs
    usage1 = "usage1"
    usage2 = "usage2"

    # 直接创建LLMs
    llm1 = LLM(
        usage_id=usage1,
        model="gpt-4o",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    llm2 = LLM(
        usage_id=usage2,
        model="gpt-3.5-turbo",
        api_key=SecretStr("test_key"),
        num_retries=2,
        retry_min_wait=1,
        retry_max_wait=2,
    )

    # 将 LLMs 添加到注册表中（这应该触发通知）
    mock_llm_registry.add(llm1)
    mock_llm_registry.add(llm2)

    # 为每个 LLM 添加不同的指标
    assert llm1.metrics is not None
    llm1.metrics.add_cost(0.05)
    llm1.metrics.add_token_usage(
        prompt_tokens=100,
        completion_tokens=50,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=8000,
        response_id="resp1",
    )

    assert llm2.metrics is not None
    llm2.metrics.add_cost(0.02)
    llm2.metrics.add_token_usage(
        prompt_tokens=200,
        completion_tokens=100,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=4000,
        response_id="resp2",
    )

    # 验证对话统计中已注册使用情况
    assert usage1 in conversation_stats.usage_to_metrics
    assert usage2 in conversation_stats.usage_to_metrics
    assert usage2 in conversation_stats.usage_to_metrics

    # 验证各个指标
    assert conversation_stats.usage_to_metrics[usage1].accumulated_cost == 0.05
    assert conversation_stats.usage_to_metrics[usage2].accumulated_cost == 0.02

    # 获取组合指标并验证
    combined = conversation_stats.get_combined_metrics()
    assert combined.accumulated_cost == 0.07  # 0.05 + 0.02
    assert combined.accumulated_token_usage.prompt_tokens == 300  # 100 + 200
    assert combined.accumulated_token_usage.completion_tokens == 150  # 50 + 100
    assert combined.accumulated_token_usage.context_window == 8000  # 最大 8000 和 4000


def test_register_llm_with_multiple_restored_usage_ids(conversation_stats):
    """
    测试重现 del self.restored_metrics 删除整个字典而不是特定用法的错误。
    """

    # 创建用于多种用途的恢复指标
    usage_id_1 = "usage-1"
    usage_id_2 = "usage-2"

    restored_metrics_1 = Metrics(model_name="gpt-4")
    restored_metrics_1.add_cost(0.1)

    restored_metrics_2 = Metrics(model_name="gpt-3.5")
    restored_metrics_2.add_cost(0.05)

    # 为两种用途设置恢复指标
    conversation_stats.usage_to_metrics = {
        usage_id_1: restored_metrics_1,
        usage_id_2: restored_metrics_2,
    }

    # 修补 LLM 类以避免实际的 API 调用
    with patch("openhands.sdk.llm.llm.litellm_completion"):
        # Register first LLM
        llm_1 = LLM(
            usage_id=usage_id_1,
            model="gpt-4o",
            api_key=SecretStr("test_key"),
            num_retries=2,
            retry_min_wait=1,
            retry_max_wait=2,
        )
        event_1 = RegistryEvent(llm=llm_1)
        conversation_stats.register_llm(event_1)

        # 验证首次使用是否已使用恢复的指标进行注册
        assert usage_id_1 in conversation_stats.usage_to_metrics
        assert llm_1.metrics is not None
        assert llm_1.metrics.accumulated_cost == 0.1

        # 注册第一次使用后，restored_metrics 仍不应包含 usage_id_2
        #
        assert usage_id_2 not in conversation_stats._restored_usage_ids

        # 注册第二个 LLM - 这也应该适用于恢复的指标
        llm_2 = LLM(
            usage_id=usage_id_2,
            model="gpt-3.5-turbo",
            api_key=SecretStr("test_key"),
            num_retries=2,
            retry_min_wait=1,
            retry_max_wait=2,
        )
        event_2 = RegistryEvent(llm=llm_2)
        conversation_stats.register_llm(event_2)

        # 验证第二次使用是否已使用恢复的指标进行注册
        assert usage_id_2 in conversation_stats.usage_to_metrics
        assert llm_2.metrics is not None
        assert llm_2.metrics.accumulated_cost == 0.05

        # 两种用途都标记为恢复后
        assert usage_id_2 in conversation_stats._restored_usage_ids
        assert len(conversation_stats._restored_usage_ids) == 2
