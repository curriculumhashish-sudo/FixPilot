"""测试 LLM 指标类。"""

import pytest
from pydantic import ValidationError

from openhands.sdk.llm.utils.metrics import (
    Cost,
    Metrics,
    MetricsSnapshot,
    ResponseLatency,
    TokenUsage,
)


def test_cost_creation_valid():
    """测试创建有效的 Cost 实例。"""
    cost = Cost(cost=5.0, model="gpt-4o-mini")
    assert cost.cost == 5.0
    assert cost.model == "gpt-4o-mini"
    assert hasattr(cost, "timestamp")


def test_cost_creation_zero():
    """测试创建零成本的 Cost 实例。"""
    cost = Cost(cost=0.0, model="gpt-4o-mini")
    assert cost.cost == 0.0


def test_cost_creation_negative_fails():
    """测试负成本是否增加 ValidationError。"""
    with pytest.raises(ValidationError) as exc_info:
        Cost(cost=-1.0, model="gpt-4o-mini")

    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "greater_than_equal"
    assert "cost" in errors[0]["loc"]


def test_response_latency_creation_valid():
    """测试创建有效的 ResponseLatency 实例。"""
    latency = ResponseLatency(model="gpt-4o-mini", latency=1.5, response_id="test-123")
    assert latency.latency == 1.5
    assert latency.response_id == "test-123"
    assert latency.model == "gpt-4o-mini"


def test_response_latency_creation_zero():
    """测试创建零延迟的 ResponseLatency 实例。"""
    latency = ResponseLatency(model="gpt-4o-mini", latency=0.0, response_id="test-123")
    assert latency.latency == 0.0


def test_response_latency_creation_negative_fails():
    """测试负延迟是否增加 ValidationError。"""
    with pytest.raises(ValidationError) as exc_info:
        ResponseLatency(model="gpt-4o-mini", latency=-0.5, response_id="test-123")

    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "greater_than_equal"
    assert "latency" in errors[0]["loc"]


def test_token_usage_creation_valid():
    """测试创建有效的 TokenUsage 实例。"""
    usage = TokenUsage(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
        context_window=4096,
        per_turn_token=155,
        response_id="test-123",
    )
    assert usage.model == "gpt-4o-mini"
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50
    assert usage.cache_read_tokens == 10
    assert usage.cache_write_tokens == 5
    assert usage.context_window == 4096
    assert usage.per_turn_token == 155
    assert usage.response_id == "test-123"


def test_token_usage_creation_zeros():
    """测试创建一个具有零值的 TokenUsage 实例。"""
    usage = TokenUsage(
        model="gpt-4o-mini",
        prompt_tokens=0,
        completion_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=0,
        per_turn_token=0,
        response_id="test-123",
    )
    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_write_tokens == 0


def test_token_usage_negative_prompt_tokens_fails():
    """测试负值 prompt_tokens 会引发 ValidationError。"""
    with pytest.raises(ValidationError) as exc_info:
        TokenUsage(
            model="gpt-4o-mini",
            prompt_tokens=-1,
            completion_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=0,
            context_window=4096,
            per_turn_token=49,
            response_id="test-123",
        )

    errors = exc_info.value.errors()
    assert any(
        error["type"] == "greater_than_equal" and "prompt_tokens" in error["loc"]
        for error in errors
    )


def test_token_usage_negative_completion_tokens_fails():
    """测试负值 completion_tokens 会引发 ValidationError。"""
    with pytest.raises(ValidationError) as exc_info:
        TokenUsage(
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=-1,
            cache_read_tokens=0,
            cache_write_tokens=0,
            context_window=4096,
            per_turn_token=99,
            response_id="test-123",
        )

    errors = exc_info.value.errors()
    assert any(
        error["type"] == "greater_than_equal" and "completion_tokens" in error["loc"]
        for error in errors
    )


def test_token_usage_negative_cache_tokens_fails():
    """测试负缓存 token 升高 ValidationError。"""
    with pytest.raises(ValidationError):
        TokenUsage(
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            cache_read_tokens=-1,
            cache_write_tokens=0,
            context_window=4096,
            per_turn_token=149,
            response_id="test-123",
        )

    with pytest.raises(ValidationError):
        TokenUsage(
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            cache_read_tokens=0,
            cache_write_tokens=-1,
            context_window=4096,
            per_turn_token=149,
            response_id="test-123",
        )


def test_token_usage_addition():
    """测试 TokenUsage 个实例是否可以添加在一起。"""
    usage1 = TokenUsage(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
        context_window=4096,
        per_turn_token=155,
        response_id="test-1",
    )

    usage2 = TokenUsage(
        model="gpt-4o-mini",
        prompt_tokens=200,
        completion_tokens=75,
        cache_read_tokens=20,
        cache_write_tokens=10,
        context_window=4096,
        per_turn_token=285,
        response_id="test-2",
    )

    combined = usage1 + usage2

    assert combined.model == "gpt-4o-mini"
    assert combined.prompt_tokens == 300
    assert combined.completion_tokens == 125
    assert combined.cache_read_tokens == 30
    assert combined.cache_write_tokens == 15
    assert combined.context_window == 4096
    assert combined.per_turn_token == 285  # 用途 other.per_turn_token
    assert combined.response_id == "test-1"  # 应保留第一个 response_id


def test_metrics_creation_empty():
    """测试创建一个空的 Metrics 实例。"""
    metrics = Metrics()
    assert metrics.model_name == "default"
    assert metrics.accumulated_cost == 0.0
    assert metrics.accumulated_token_usage is not None
    assert metrics.accumulated_token_usage.prompt_tokens == 0
    assert metrics.costs == []
    assert metrics.response_latencies == []


def test_metrics_creation_with_model_name():
    """测试使用模型名称创建 Metrics 实例。"""
    metrics = Metrics(model_name="gpt-4o-mini")
    assert metrics.model_name == "gpt-4o-mini"
    assert metrics.accumulated_cost == 0.0
    assert metrics.accumulated_token_usage is not None
    assert metrics.accumulated_token_usage.prompt_tokens == 0


def test_metrics_add_cost():
    """测试增加指标成本。"""
    metrics = Metrics()
    metrics.add_cost(5.0)

    assert metrics.accumulated_cost == 5.0
    assert len(metrics.costs) == 1
    assert metrics.costs[0].cost == 5.0
    assert metrics.costs[0].model == "default"


def test_metrics_add_cost_with_model_name():
    """使用自定义模型名称测试增加成本。"""
    metrics = Metrics(model_name="gpt-4o-mini")
    metrics.add_cost(3.5)

    assert metrics.accumulated_cost == 3.5
    assert len(metrics.costs) == 1
    assert metrics.costs[0].cost == 3.5
    assert metrics.costs[0].model == "gpt-4o-mini"


def test_metrics_add_multiple_costs():
    """测试添加多个成本。"""
    metrics = Metrics()
    metrics.add_cost(2.0)
    metrics.add_cost(3.0)
    metrics.add_cost(1.5)

    assert metrics.accumulated_cost == 6.5
    assert len(metrics.costs) == 3


def test_metrics_add_response_latency():
    """测试向指标添加响应延迟。"""
    metrics = Metrics()
    metrics.add_response_latency(1.5, "test-123")

    assert len(metrics.response_latencies) == 1
    assert metrics.response_latencies[0].latency == 1.5
    assert metrics.response_latencies[0].response_id == "test-123"


def test_metrics_add_multiple_response_latencies():
    """测试添加多个响应延迟。"""
    metrics = Metrics()
    metrics.add_response_latency(1.0, "test-1")
    metrics.add_response_latency(2.5, "test-2")
    metrics.add_response_latency(0.8, "test-3")

    assert len(metrics.response_latencies) == 3
    assert metrics.response_latencies[1].latency == 2.5


def test_metrics_add_token_usage_first_time():
    """第一次测试添加词元用量。"""
    metrics = Metrics()
    metrics.add_token_usage(100, 50, 10, 5, 4096, "test-123")

    assert metrics.accumulated_token_usage is not None
    assert metrics.accumulated_token_usage.prompt_tokens == 100
    assert metrics.accumulated_token_usage.completion_tokens == 50
    assert metrics.accumulated_token_usage.cache_read_tokens == 10
    assert metrics.accumulated_token_usage.cache_write_tokens == 5
    assert metrics.accumulated_token_usage.context_window == 4096
    assert metrics.accumulated_token_usage.per_turn_token == 150
    assert metrics.accumulated_token_usage.response_id == ""


def test_metrics_add_token_usage_accumulate():
    """测试多次添加词元用量累加是否正确。"""
    metrics = Metrics()
    metrics.add_token_usage(100, 50, 10, 5, 4096, "test-1")
    metrics.add_token_usage(200, 75, 20, 10, 4096, "test-2")

    assert metrics.accumulated_token_usage is not None
    assert metrics.accumulated_token_usage.prompt_tokens == 300
    assert metrics.accumulated_token_usage.completion_tokens == 125
    assert metrics.accumulated_token_usage.cache_read_tokens == 30
    assert metrics.accumulated_token_usage.cache_write_tokens == 15
    assert metrics.accumulated_token_usage.per_turn_token == 275


def test_metrics_merge_empty_metrics():
    """测试与空指标的合并。"""
    metrics1 = Metrics()
    metrics1.add_cost(5.0)

    metrics2 = Metrics()

    metrics1.merge(metrics2)
    assert metrics1.accumulated_cost == 5.0


def test_metrics_merge_with_costs():
    """测试将指标与成本合并。"""
    metrics1 = Metrics()
    metrics1.add_cost(5.0)

    metrics2 = Metrics()
    metrics2.add_cost(3.0)

    metrics1.merge(metrics2)
    assert metrics1.accumulated_cost == 8.0
    assert len(metrics1.costs) == 2


def test_metrics_merge_with_token_usage():
    """测试与词元用量的合并指标。"""
    metrics1 = Metrics()
    metrics1.add_token_usage(100, 50, 10, 5, 4096, "test-1")

    metrics2 = Metrics()
    metrics2.add_token_usage(200, 75, 20, 10, 4096, "test-2")

    metrics1.merge(metrics2)
    assert metrics1.accumulated_token_usage is not None
    assert metrics1.accumulated_token_usage.prompt_tokens == 300
    assert metrics1.accumulated_token_usage.completion_tokens == 125


def test_metrics_merge_with_response_latencies():
    """测试合并指标与响应延迟。"""
    metrics1 = Metrics()
    metrics1.add_response_latency(1.0, "test-1")

    metrics2 = Metrics()
    metrics2.add_response_latency(2.0, "test-2")

    metrics1.merge(metrics2)
    assert len(metrics1.response_latencies) == 2
    assert metrics1.response_latencies[0].latency == 1.0
    assert metrics1.response_latencies[1].latency == 2.0


def test_metrics_get_method():
    """测试get方法返回正确的数据。"""
    metrics = Metrics(model_name="gpt-4o-mini")
    metrics.add_cost(5.0)
    metrics.add_token_usage(100, 50, 10, 5, 4096, "test-123")
    metrics.add_response_latency(1.5, "test-123")

    data = metrics.get()

    assert data["accumulated_cost"] == 5.0
    assert data["accumulated_token_usage"]["prompt_tokens"] == 100
    assert len(data["costs"]) == 1
    assert len(data["response_latencies"]) == 1


def test_metrics_diff_method():
    """测试 diff 方法是否正确计算差异。"""
    metrics1 = Metrics()
    metrics1.add_cost(10.0)
    metrics1.add_token_usage(500, 250, 50, 25, 4096, "test-1")

    metrics2 = Metrics()
    metrics2.add_cost(3.0)
    metrics2.add_token_usage(200, 100, 20, 10, 4096, "test-2")

    diff = metrics1.diff(metrics2)

    assert diff.accumulated_cost == 7.0  # 10.0 - 3.0
    assert diff.accumulated_token_usage is not None
    assert diff.accumulated_token_usage.prompt_tokens == 300  # 500 - 200
    assert diff.accumulated_token_usage.completion_tokens == 150  # 250 - 100


def test_metrics_diff_with_none_token_usage():
    """当一个指标具有 None 词元用量时测试 diff 方法。"""
    metrics1 = Metrics()
    metrics1.add_cost(10.0)
    metrics1.add_token_usage(500, 250, 50, 25, 4096, "test-1")

    metrics2 = Metrics()
    metrics2.add_cost(3.0)
    # 指标 2 中未添加词元用量

    diff = metrics1.diff(metrics2)

    assert diff.accumulated_cost == 7.0
    assert diff.accumulated_token_usage is not None
    assert diff.accumulated_token_usage.prompt_tokens == 500
    assert diff.accumulated_token_usage.completion_tokens == 250


def test_metrics_deep_copy():
    """测试deep_copy方法创建独立副本。"""
    metrics = Metrics(model_name="gpt-4o-mini")
    metrics.add_cost(5.0)
    metrics.add_token_usage(100, 50, 10, 5, 4096, "test-123")

    copied = metrics.deep_copy()

    # 验证副本具有相同的数据
    assert copied.model_name == metrics.model_name
    assert copied.accumulated_cost == metrics.accumulated_cost
    assert copied.accumulated_token_usage is not None
    assert metrics.accumulated_token_usage is not None
    assert (
        copied.accumulated_token_usage.prompt_tokens
        == metrics.accumulated_token_usage.prompt_tokens
    )

    # 验证他们是独立的
    copied.add_cost(2.0)
    assert copied.accumulated_cost == 7.0
    assert metrics.accumulated_cost == 5.0


def test_metrics_empty_state_operations():
    """对空指标的测试操作正常工作。"""
    metrics = Metrics()

    # 测试获取空指标
    data = metrics.get()
    assert data["accumulated_cost"] == 0.0
    assert data["accumulated_token_usage"] is not None

    # 使用空指标测试差异
    other = Metrics()
    diff = metrics.diff(other)
    assert diff.accumulated_cost == 0.0
    assert diff.accumulated_token_usage is not None

    # 测试与空指标的合并
    metrics.merge(other)
    assert metrics.accumulated_cost == 0.0
    assert metrics.accumulated_token_usage is not None


def test_metrics_accumulated_cost_negative_validation():
    """测试指标累积成本验证为负值（第 105 行）。"""
    # 创建具有负累积成本的指标实例
    with pytest.raises(
        ValidationError, match="Input should be greater than or equal to 0"
    ):
        Metrics(accumulated_cost=-1.0)


def test_metrics_merge_max_budget_from_other():
    """当 self 中的 max_budget_per_task 为 None 但 other 中设置时测试合并。"""
    # 创建不带 max_budget_per_task 的指标
    metrics1 = Metrics()
    assert metrics1.max_budget_per_task is None

    # 使用 max_budget_per_task 创建指标
    metrics2 = Metrics(max_budget_per_task=100.0)

    # 合并 - 应从其他复制 max_budget_per_task（第 182 行）
    metrics1.merge(metrics2)
    assert metrics1.max_budget_per_task == 100.0


def test_metrics_merge_accumulated_token_usage_none_self():
    """当 self.accumulated_token_usage 为 None 时测试合并（第 190 行）。"""
    # 创建指标并手动将 accumulated_token_usage 设置为 None
    metrics1 = Metrics()
    metrics1.accumulated_token_usage = None

    # 创建具有累积词元用量的指标
    metrics2 = Metrics()
    metrics2.add_token_usage(
        prompt_tokens=10,
        completion_tokens=5,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=100,
        response_id="test",
    )

    # 合并 - 应从其他复制 accumulated_token_usage（第 190 行）
    metrics1.merge(metrics2)
    assert metrics1.accumulated_token_usage is not None
    assert metrics1.accumulated_token_usage.prompt_tokens == 10
    assert metrics1.accumulated_token_usage.completion_tokens == 5


def test_metrics_diff_both_usage_none():
    """当 accumulated_token_usage 都是 None 时测试 diff 方法（第 276-277 行）。"""
    # 创建指标并手动将 accumulated_token_usage 设置为 None
    metrics1 = Metrics()
    metrics1.accumulated_token_usage = None
    metrics2 = Metrics()
    metrics2.accumulated_token_usage = None

    # 计算 diff - 应该处理 None （第 276-277 行）
    diff = metrics1.diff(metrics2)
    assert diff.accumulated_token_usage is None


def test_metrics_add_token_usage_none_accumulated_initial():
    """当 accumulated_token_usage 最初为 None 时测试 add_token_usage。"""
    # 创建指标并手动将 accumulated_token_usage 设置为 None
    metrics = Metrics()
    metrics.accumulated_token_usage = None

    # 添加用法 - 应触发第 172 行（如果分支）
    metrics.add_token_usage(
        prompt_tokens=10,
        completion_tokens=5,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=100,
        response_id="test",
    )

    # 应该已经设置了用法
    assert metrics.accumulated_token_usage is not None
    assert metrics.accumulated_token_usage.prompt_tokens == 10
    assert metrics.accumulated_token_usage.completion_tokens == 5


def test_metrics_diff_current_only_not_none():
    """当当前有使用但基线没有时测试 diff 方法（第 275 行）。"""
    # 创建使用情况指标
    metrics1 = Metrics()
    metrics1.add_token_usage(
        prompt_tokens=15,
        completion_tokens=8,
        cache_read_tokens=2,
        cache_write_tokens=1,
        context_window=200,
        response_id="test",
    )

    # 创建具有 None 使用情况的基线指标
    metrics2 = Metrics()
    metrics2.accumulated_token_usage = None

    # 计算差异 - 应复制 current_usage（第 275 行）
    diff = metrics1.diff(metrics2)
    assert diff.accumulated_token_usage is not None
    assert diff.accumulated_token_usage.prompt_tokens == 15
    assert diff.accumulated_token_usage.completion_tokens == 8
    assert diff.accumulated_token_usage.cache_read_tokens == 2
    assert diff.accumulated_token_usage.cache_write_tokens == 1


@pytest.mark.parametrize(
    "prompt_tokens, cache_read_tokens, expected",
    [
        # litellm/OpenAI 约定：prompt_tokens 已包含缓存读取。
        (100, 10, 0.10),
        (100, 0, 0.0),
        # cache_read == 提示词 -> 提示词是分母。
        (50, 50, 1.0),
        # ACP约定：输入不包括缓存的读取，因此它们是不相交的，分母是提示词 + cache_read。
        #
        (10, 90, 0.90),
        (0, 50, 1.0),  # 零提示词，所有缓存 -> 100% 命中（不是 None）
        # 没有什么可测量的 -> 未定义。
        (0, 0, None),
    ],
)
def test_cache_hit_rate_conventions(prompt_tokens, cache_read_tokens, expected):
    """cache_hit_rate 处理提供者约定和零输入。"""
    snapshot = MetricsSnapshot(
        accumulated_token_usage=TokenUsage(
            prompt_tokens=prompt_tokens, cache_read_tokens=cache_read_tokens
        )
    )
    if expected is None:
        assert snapshot.cache_hit_rate is None
    else:
        assert snapshot.cache_hit_rate == pytest.approx(expected)


def test_cache_hit_rate_reflects_accumulated_usage():
    """Metrics.cache_hit_rate 来自调用期间的累积使用情况。"""
    metrics = Metrics()
    metrics.add_token_usage(
        prompt_tokens=100,
        completion_tokens=10,
        cache_read_tokens=0,
        cache_write_tokens=0,
        context_window=4096,
        response_id="r1",
    )
    metrics.add_token_usage(
        prompt_tokens=100,
        completion_tokens=10,
        cache_read_tokens=40,
        cache_write_tokens=0,
        context_window=4096,
        response_id="r2",
    )
    # 累计提示词=200, cache_read=40 -> 40 / 200
    assert metrics.cache_hit_rate == pytest.approx(0.20)


def test_cache_hit_rate_none_without_usage():
    """尚未使用 -> 未定义，而不是误导性的 0% 或崩溃。"""
    assert MetricsSnapshot(accumulated_token_usage=None).cache_hit_rate is None
    assert Metrics().cache_hit_rate is None  # 新指标全为零


def test_cache_hit_rate_is_not_serialized():
    """派生利率不在已序列化模式范围内（无公共 API 更改）。"""
    snapshot = Metrics().get_snapshot()
    assert "cache_hit_rate" not in snapshot.model_dump()
    assert "cache_hit_rate" not in MetricsSnapshot.model_json_schema()["properties"]
