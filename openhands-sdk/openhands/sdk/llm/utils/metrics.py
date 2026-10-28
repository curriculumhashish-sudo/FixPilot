import copy
import time
from typing import final

from pydantic import BaseModel, Field, field_validator, model_validator


class Cost(BaseModel):
    model: str
    cost: float = Field(ge=0.0, description="Cost must be non-negative")
    timestamp: float = Field(default_factory=time.time)

    @field_validator("cost")
    @classmethod
    def validate_cost(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Cost cannot be negative")
        return v


class ResponseLatency(BaseModel):
    """跟踪每次完成调用的往返时间的指标。"""

    model: str
    latency: float = Field(ge=0.0, description="Latency must be non-negative")
    response_id: str

    @field_validator("latency")
    @classmethod
    def validate_latency(cls, v: float) -> float:
        return max(0.0, v)


class TokenUsage(BaseModel):
    """每次完成调用的指标跟踪详细信息词元用量。"""

    model: str = Field(default="")
    prompt_tokens: int = Field(
        default=0, ge=0, description="Prompt tokens must be non-negative"
    )
    completion_tokens: int = Field(
        default=0, ge=0, description="Completion tokens must be non-negative"
    )
    cache_read_tokens: int = Field(
        default=0, ge=0, description="Cache read tokens must be non-negative"
    )
    cache_write_tokens: int = Field(
        default=0, ge=0, description="Cache write tokens must be non-negative"
    )
    reasoning_tokens: int = Field(
        default=0, ge=0, description="Reasoning tokens must be non-negative"
    )
    context_window: int = Field(
        default=0, ge=0, description="Context window must be non-negative"
    )
    per_turn_token: int = Field(
        default=0, ge=0, description="Per turn tokens must be non-negative"
    )
    response_id: str = Field(default="")

    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """将两个 TokenUsage 实例添加在一起。"""
        return TokenUsage(
            model=self.model,
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            context_window=max(self.context_window, other.context_window),
            per_turn_token=other.per_turn_token,
            response_id=self.response_id,
        )


class MetricsSnapshot(BaseModel):
    """某个时间点的指标快照。

    不包括单独成本、延迟或 token 使用情况的列表。
    """

    model_name: str = Field(default="default", description="Name of the model")
    accumulated_cost: float = Field(
        default=0.0, ge=0.0, description="Total accumulated cost, must be non-negative"
    )
    max_budget_per_task: float | None = Field(
        default=None, description="Maximum budget per task"
    )
    accumulated_token_usage: TokenUsage | None = Field(
        default=None, description="Accumulated token usage across all calls"
    )

    @property
    def cache_hit_rate(self) -> float | None:
        """从缓存提供的累积输入 token 的比例 (0.0-1.0)。

        None 当没有可测量的输入时。 litellm/OpenAI 计数 ``prompt_tokens`` 内的缓存读
        取（分母）； ACP 分别报告它们，因此
        当 ``cache_read_tokens`` 超过 ``prompt_tokens`` 时，分母就是它们的总和。
        """
        usage = self.accumulated_token_usage
        if usage is None:
            return None
        prompt, cache_read = usage.prompt_tokens, usage.cache_read_tokens
        denom = prompt + cache_read if cache_read > prompt else prompt
        if denom <= 0:
            return None
        return cache_read / denom


@final
class Metrics(MetricsSnapshot):
    """Metrics类可以记录运行和评估过程中的各种指标。
    我们追踪：
      - accumulated_cost 和成本
      - max_budget_per_task（预算限制）
      - 列表 ResponseLatency
      - TokenUsage 列表（每个调用一个）。
    """

    costs: list[Cost] = Field(
        default_factory=list, description="List of individual costs"
    )
    response_latencies: list[ResponseLatency] = Field(
        default_factory=list, description="List of response latencies"
    )
    token_usages: list[TokenUsage] = Field(
        default_factory=list, description="List of token usage records"
    )

    @field_validator("accumulated_cost")
    @classmethod
    def validate_accumulated_cost(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Total cost cannot be negative.")
        return v

    @model_validator(mode="after")
    def initialize_accumulated_token_usage(self) -> "Metrics":
        if self.accumulated_token_usage is None:
            self.accumulated_token_usage = TokenUsage(
                model=self.model_name,
                prompt_tokens=0,
                completion_tokens=0,
                cache_read_tokens=0,
                cache_write_tokens=0,
                reasoning_tokens=0,
                context_window=0,
                response_id="",
            )
        return self

    def get_snapshot(self) -> MetricsSnapshot:
        """获取当前指标的快照，无需详细列表。"""
        return MetricsSnapshot(
            model_name=self.model_name,
            accumulated_cost=self.accumulated_cost,
            max_budget_per_task=self.max_budget_per_task,
            accumulated_token_usage=copy.deepcopy(self.accumulated_token_usage)
            if self.accumulated_token_usage
            else None,
        )

    def add_cost(self, value: float) -> None:
        if value < 0:
            raise ValueError("Added cost cannot be negative.")
        self.accumulated_cost += value
        self.costs.append(Cost(cost=value, model=self.model_name))

    def add_response_latency(self, value: float, response_id: str) -> None:
        self.response_latencies.append(
            ResponseLatency(
                latency=max(0.0, value), model=self.model_name, response_id=response_id
            )
        )

    def add_token_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
        context_window: int,
        response_id: str,
        reasoning_tokens: int = 0,
    ) -> None:
        """添加单次使用记录。"""
        # token 每回合用于计算上下文使用情况。
        per_turn_token = prompt_tokens + completion_tokens

        usage = TokenUsage(
            model=self.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            context_window=context_window,
            per_turn_token=per_turn_token,
            response_id=response_id,
        )
        self.token_usages.append(usage)

        # 使用 __add__ 运算符更新累积的词元用量
        new_usage = TokenUsage(
            model=self.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            context_window=context_window,
            per_turn_token=per_turn_token,
            response_id="",
        )
        if self.accumulated_token_usage is None:
            self.accumulated_token_usage = new_usage
        else:
            self.accumulated_token_usage = self.accumulated_token_usage + new_usage

    def merge(self, other: "Metrics") -> None:
        """将“其他”指标合并到此指标中。"""
        self.accumulated_cost += other.accumulated_cost

        # 如果已设置而此未设置，则保留 max_budget_per_task 与其他设置
        if self.max_budget_per_task is None and other.max_budget_per_task is not None:
            self.max_budget_per_task = other.max_budget_per_task

        self.costs += other.costs
        self.token_usages += other.token_usages
        self.response_latencies += other.response_latencies

        # 使用 __add__ 运算符合并累积的词元用量
        if self.accumulated_token_usage is None:
            self.accumulated_token_usage = other.accumulated_token_usage
        elif other.accumulated_token_usage is not None:
            self.accumulated_token_usage = (
                self.accumulated_token_usage + other.accumulated_token_usage
            )

    def get(self) -> dict:
        """返回字典中的指标。"""
        return {
            "accumulated_cost": self.accumulated_cost,
            "max_budget_per_task": self.max_budget_per_task,
            "accumulated_token_usage": self.accumulated_token_usage.model_dump()
            if self.accumulated_token_usage
            else None,
            "costs": [cost.model_dump() for cost in self.costs],
            "response_latencies": [
                latency.model_dump() for latency in self.response_latencies
            ],
            "token_usages": [usage.model_dump() for usage in self.token_usages],
        }

    def log(self) -> str:
        """记录指标。"""
        metrics = self.get()
        logs = ""
        for key, value in metrics.items():
            logs += f"{key}: {value}\n"
        return logs

    def deep_copy(self) -> "Metrics":
        """创建 Metrics 对象的深层副本。"""
        return copy.deepcopy(self)

    def diff(self, baseline: "Metrics") -> "Metrics":
        """计算当前指标与基线之间的差异。

        这对于跟踪委托等特定操作的指标非常有用。

        Args:
            baseline: 表示基线状态的指标对象

        Returns:
            一个新的 Metrics 对象，仅包含自基线以来的差异
        """
        result = Metrics(model_name=self.model_name)

        # 计算成本差异
        result.accumulated_cost = self.accumulated_cost - baseline.accumulated_cost

        # 仅包括在基准之后添加的成本
        if baseline.costs:
            last_baseline_timestamp = baseline.costs[-1].timestamp
            result.costs = [
                cost for cost in self.costs if cost.timestamp > last_baseline_timestamp
            ]
        else:
            result.costs = self.costs.copy()

        # 仅包括在基线之后添加的响应延迟
        result.response_latencies = self.response_latencies[
            len(baseline.response_latencies) :
        ]

        # 仅包括在基线之后添加的 token 个用法
        result.token_usages = self.token_usages[len(baseline.token_usages) :]

        # 计算累计词元用量差异
        base_usage = baseline.accumulated_token_usage
        current_usage = self.accumulated_token_usage

        if current_usage is not None and base_usage is not None:
            result.accumulated_token_usage = TokenUsage(
                model=self.model_name,
                prompt_tokens=current_usage.prompt_tokens - base_usage.prompt_tokens,
                completion_tokens=current_usage.completion_tokens
                - base_usage.completion_tokens,
                cache_read_tokens=current_usage.cache_read_tokens
                - base_usage.cache_read_tokens,
                cache_write_tokens=current_usage.cache_write_tokens
                - base_usage.cache_write_tokens,
                reasoning_tokens=current_usage.reasoning_tokens
                - base_usage.reasoning_tokens,
                context_window=current_usage.context_window,
                per_turn_token=0,
                response_id="",
            )
        elif current_usage is not None:
            result.accumulated_token_usage = current_usage
        else:
            result.accumulated_token_usage = None

        return result

    def __repr__(self) -> str:
        return f"Metrics({self.get()}"
