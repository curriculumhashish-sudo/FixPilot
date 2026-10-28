"""测试统计数据的 ConversationStateUpdateEvent 使用 MetricsSnapshot。"""

import uuid

import pytest
from pydantic import SecretStr

from openhands.sdk import LLM, Agent
from openhands.sdk.conversation.conversation_stats import ConversationStats
from openhands.sdk.conversation.state import ConversationState
from openhands.sdk.event.conversation_state import ConversationStateUpdateEvent
from openhands.sdk.io import InMemoryFileStore
from openhands.sdk.llm.utils.metrics import Metrics
from openhands.sdk.workspace import LocalWorkspace


@pytest.fixture
def state():
    """创建一个 ConversationState 进行测试。"""
    llm = LLM(model="gpt-4o-mini", api_key=SecretStr("test-key"), usage_id="test-llm")
    agent = Agent(llm=llm)
    workspace = LocalWorkspace(working_dir="/tmp/test")

    state = ConversationState(
        id=uuid.uuid4(),
        workspace=workspace,
        persistence_dir="/tmp/test/.state",
        agent=agent,
    )

    # 设置文件存储并启用自动保存，以便触发回调
    state._fs = InMemoryFileStore()
    state._autosave_enabled = True

    return state


def test_stats_update_event_uses_snapshot_not_full_metrics(state):
    """测试统计更新事件是否包含快照，而无需冗长的列表。"""
    callback_calls = []

    def callback(event: ConversationStateUpdateEvent):
        callback_calls.append(event)

    # 设置回调
    state.set_on_state_change(callback)

    # 创建包含多个成本条目的统计数据
    stats = ConversationStats()
    metrics = Metrics(model_name="gpt-4")

    # 添加多个成本条目来模拟长对话
    for i in range(10):
        metrics.add_cost(0.01)
        metrics.add_token_usage(
            prompt_tokens=100,
            completion_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            context_window=8000,
            response_id=f"resp{i}",
        )
        metrics.add_response_latency(1.5, f"resp{i}")

    stats.usage_to_metrics["default"] = metrics

    # 更改状态 - 应触发回调
    with state:
        state.stats = stats

    # 验证回调被调用
    assert len(callback_calls) == 1
    event = callback_calls[0]
    assert isinstance(event, ConversationStateUpdateEvent)
    assert event.key == "stats"

    # 事件值应该是一个字典（已经已序列化作为快照）
    stats_value = event.value
    assert isinstance(stats_value, dict)

    # 验证 stats_dict 是否具有我们期望的结构
    assert "usage_to_metrics" in stats_value
    assert "default" in stats_value["usage_to_metrics"]

    metrics_data = stats_value["usage_to_metrics"]["default"]

    # 修复后，这些列表应该不存在它们随着对话长度而增长并导致膨胀
    #
    assert "costs" not in metrics_data, "costs list should not be present"
    assert "response_latencies" not in metrics_data, (
        "response_latencies list should not be present"
    )
    assert "token_usages" not in metrics_data, "token_usages list should not be present"

    # 这些总是应该存在（快照数据）
    assert "accumulated_cost" in metrics_data
    assert metrics_data["accumulated_cost"] == pytest.approx(0.1)
    assert "accumulated_token_usage" in metrics_data
    assert metrics_data["accumulated_token_usage"]["prompt_tokens"] == 1000
    assert metrics_data["accumulated_token_usage"]["completion_tokens"] == 500


def test_stats_model_dump_preserves_full_history():
    """测试 model_dump() 是否保留持久化的完整指标历史记录。"""
    # 创建包含多个成本条目的统计数据
    stats = ConversationStats()
    metrics = Metrics(model_name="gpt-4")

    # 添加多个条目来模拟对话
    for i in range(5):
        metrics.add_cost(0.01)
        metrics.add_token_usage(
            prompt_tokens=100,
            completion_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            context_window=8000,
            response_id=f"resp{i}",
        )
        metrics.add_response_latency(1.5, f"resp{i}")

    stats.usage_to_metrics["default"] = metrics

    # 使用 model_dump() 而不使用上下文 - 应保留完整历史记录
    stats_dict = stats.model_dump(mode="json")

    assert "usage_to_metrics" in stats_dict
    assert "default" in stats_dict["usage_to_metrics"]

    metrics_data = stats_dict["usage_to_metrics"]["default"]

    # 完整转储应包含所有列表
    assert "costs" in metrics_data, "costs list should be present in full dump"
    assert "response_latencies" in metrics_data, (
        "response_latencies list should be present in full dump"
    )
    assert "token_usages" in metrics_data, (
        "token_usages list should be present in full dump"
    )

    # 验证列表中的条目数是否正确
    assert len(metrics_data["costs"]) == 5
    assert len(metrics_data["response_latencies"]) == 5
    assert len(metrics_data["token_usages"]) == 5

    # 验证累计值也存在
    assert "accumulated_cost" in metrics_data
    assert metrics_data["accumulated_cost"] == pytest.approx(0.05)


def test_stats_model_dump_with_snapshot_context_excludes_history():
    """测试 model_dump() 与 use_snapshot 上下文排除冗长的列表。"""
    # 创建包含多个成本条目的统计数据
    stats = ConversationStats()
    metrics = Metrics(model_name="gpt-4")

    # 添加多个条目来模拟对话
    for i in range(5):
        metrics.add_cost(0.01)
        metrics.add_token_usage(
            prompt_tokens=100,
            completion_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            context_window=8000,
            response_id=f"resp{i}",
        )
        metrics.add_response_latency(1.5, f"resp{i}")

    stats.usage_to_metrics["default"] = metrics

    # 将 model_dump() 与快照上下文一起使用 - 应排除列表
    stats_dict = stats.model_dump(mode="json", context={"use_snapshot": True})

    assert "usage_to_metrics" in stats_dict
    assert "default" in stats_dict["usage_to_metrics"]

    metrics_data = stats_dict["usage_to_metrics"]["default"]

    # 快照应不包含列表
    assert "costs" not in metrics_data, "costs list should not be in snapshot"
    assert "response_latencies" not in metrics_data, (
        "response_latencies list should not be in snapshot"
    )
    assert "token_usages" not in metrics_data, (
        "token_usages list should not be in snapshot"
    )

    # 验证累计值是否存在
    assert "accumulated_cost" in metrics_data
    assert metrics_data["accumulated_cost"] == pytest.approx(0.05)
    assert "accumulated_token_usage" in metrics_data
    assert metrics_data["accumulated_token_usage"]["prompt_tokens"] == 500
    assert metrics_data["accumulated_token_usage"]["completion_tokens"] == 250
