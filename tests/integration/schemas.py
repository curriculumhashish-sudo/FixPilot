"""
JSON 模式用于结构化集成测试结果。
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


TestType = Literal["integration", "behavior", "condenser"]


def json_serializer(obj):
    """JSON 序列化器对于默认情况下不可序列化的对象 JSON 代码"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class TokenUsageData(BaseModel):
    """词元用量测试实例的数据。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    context_window: int = 0

    def __add__(self, other: "TokenUsageData") -> "TokenUsageData":
        """将两个 TokenUsageData 实例添加在一起。"""
        return TokenUsageData(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            context_window=max(self.context_window, other.context_window),
        )


class TestResultData(BaseModel):
    """个人测试结果数据。"""

    success: bool
    reason: str | None = None
    skipped: bool = False


class TestInstanceResult(BaseModel):
    """单个测试实例的结果。"""

    instance_id: str
    test_result: TestResultData
    test_type: TestType
    required: bool  # True 用于集成测试，False 用于行为/冷凝器测试
    cost: float = 0.0
    token_usage: TokenUsageData | None = None
    error_message: str | None = None


class ModelTestResults(BaseModel):
    """单个模型的完整测试结果。"""

    # 元数据
    model_name: str
    run_suffix: str
    llm_config: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)

    # 测试执行数据
    test_instances: list[TestInstanceResult]

    # 统计汇总
    total_tests: int
    successful_tests: int
    skipped_tests: int
    success_rate: float
    total_cost: float
    total_token_usage: TokenUsageData | None = None

    # 特定类型的统计数据
    integration_tests_total: int = 0
    integration_tests_successful: int = 0
    integration_tests_success_rate: float = 0.0
    behavior_tests_total: int = 0
    behavior_tests_successful: int = 0
    behavior_tests_success_rate: float = 0.0

    # 附加元数据
    eval_note: str | None = None
    artifact_url: str | None = None
    status: str = "completed"

    @classmethod
    def from_eval_outputs(
        cls,
        eval_outputs: list[Any],  # 列表[EvalOutput]
        model_name: str,
        run_suffix: str,
        llm_config: dict[str, Any],
        eval_note: str | None = None,
        artifact_url: str | None = None,
    ) -> "ModelTestResults":
        """从 EvalOutput 对象列表创建 ModelTestResults。"""

        # 将 EvalOutput 对象转换为 TestInstanceResult
        test_instances = []
        for output in eval_outputs:
            # 转换词元用量（如果可用）
            token_usage = None
            if output.token_usage is not None:
                token_usage = TokenUsageData(
                    prompt_tokens=output.token_usage.prompt_tokens,
                    completion_tokens=output.token_usage.completion_tokens,
                    cache_read_tokens=output.token_usage.cache_read_tokens,
                    cache_write_tokens=output.token_usage.cache_write_tokens,
                    reasoning_tokens=output.token_usage.reasoning_tokens,
                    context_window=output.token_usage.context_window,
                )

            test_instances.append(
                TestInstanceResult(
                    instance_id=output.instance_id,
                    test_result=TestResultData(
                        success=output.test_result.success,
                        reason=output.test_result.reason,
                        skipped=output.test_result.skipped,
                    ),
                    test_type=output.test_type,
                    required=output.required,
                    cost=output.cost,
                    token_usage=token_usage,
                    error_message=output.error_message,
                )
            )

        # 计算汇总统计数据
        total_tests = len(test_instances)
        successful_tests = sum(1 for t in test_instances if t.test_result.success)
        skipped_tests = sum(1 for t in test_instances if t.test_result.skipped)
        # 从成功率计算中排除跳过的测试
        non_skipped_tests = total_tests - skipped_tests
        success_rate = (
            successful_tests / non_skipped_tests if non_skipped_tests > 0 else 0.0
        )
        total_cost = sum(t.cost for t in test_instances)

        # 计算总计词元用量
        total_token_usage = TokenUsageData()
        for t in test_instances:
            if t.token_usage is not None:
                total_token_usage = total_token_usage + t.token_usage

        # 计算特定类型的统计数据
        integration_tests = [t for t in test_instances if t.test_type == "integration"]
        behavior_tests = [t for t in test_instances if t.test_type == "behavior"]

        integration_tests_total = len(integration_tests)
        integration_tests_successful = sum(
            1 for t in integration_tests if t.test_result.success
        )
        integration_skipped = sum(1 for t in integration_tests if t.test_result.skipped)
        integration_non_skipped = integration_tests_total - integration_skipped
        integration_tests_success_rate = (
            integration_tests_successful / integration_non_skipped
            if integration_non_skipped > 0
            else 0.0
        )

        behavior_tests_total = len(behavior_tests)
        behavior_tests_successful = sum(
            1 for t in behavior_tests if t.test_result.success
        )
        behavior_skipped = sum(1 for t in behavior_tests if t.test_result.skipped)
        behavior_non_skipped = behavior_tests_total - behavior_skipped
        behavior_tests_success_rate = (
            behavior_tests_successful / behavior_non_skipped
            if behavior_non_skipped > 0
            else 0.0
        )

        return cls(
            model_name=model_name,
            run_suffix=run_suffix,
            llm_config=llm_config,
            test_instances=test_instances,
            total_tests=total_tests,
            successful_tests=successful_tests,
            skipped_tests=skipped_tests,
            success_rate=success_rate,
            total_cost=total_cost,
            total_token_usage=total_token_usage,
            integration_tests_total=integration_tests_total,
            integration_tests_successful=integration_tests_successful,
            integration_tests_success_rate=integration_tests_success_rate,
            behavior_tests_total=behavior_tests_total,
            behavior_tests_successful=behavior_tests_successful,
            behavior_tests_success_rate=behavior_tests_success_rate,
            eval_note=eval_note,
            artifact_url=artifact_url,
        )


class ConsolidatedResults(BaseModel):
    """所有模型的综合结果。"""

    # 元数据
    timestamp: datetime = Field(default_factory=datetime.now)
    total_models: int

    # 个别模型结果
    model_results: list[ModelTestResults]

    # 总体统计
    overall_success_rate: float
    total_cost_all_models: float
    # 注意：我们故意不跨模型聚合词元用量，因为
    # 不同的模型使用不同的分词器，使得跨模型 token 的求和变得毫无意义。 每个模型词元用量
    # 在 model_results 中可用。
    #

    @classmethod
    def from_model_results(
        cls, model_results: list[ModelTestResults]
    ) -> "ConsolidatedResults":
        """从 ModelTestResults 列表中创建 ConsolidatedResults。"""

        total_models = len(model_results)

        # 计算总体统计数据
        total_tests_all = sum(r.total_tests for r in model_results)
        total_successful_all = sum(r.successful_tests for r in model_results)
        total_skipped_all = sum(r.skipped_tests for r in model_results)
        # 从总体成功率计算中排除跳过的测试
        non_skipped_tests_all = total_tests_all - total_skipped_all
        overall_success_rate = (
            total_successful_all / non_skipped_tests_all
            if non_skipped_tests_all > 0
            else 0.0
        )
        total_cost_all_models = sum(r.total_cost for r in model_results)

        return cls(
            total_models=total_models,
            model_results=model_results,
            overall_success_rate=overall_success_rate,
            total_cost_all_models=total_cost_all_models,
        )
