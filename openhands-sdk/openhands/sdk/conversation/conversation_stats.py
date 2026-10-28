from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, model_serializer

from openhands.sdk.llm.llm_registry import RegistryEvent
from openhands.sdk.llm.utils.metrics import Metrics
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class ConversationStats(BaseModel):
    """跟踪对话期间观察到的每个LLM的使用指标。"""

    usage_to_metrics: dict[str, Metrics] = Field(
        default_factory=dict,
        description="Active usage metrics tracked by the registry.",
    )

    _restored_usage_ids: set[str] = PrivateAttr(default_factory=set)

    @model_serializer(mode="wrap")
    def _serialize_with_context(self, serializer: Any, info: Any) -> dict[str, Any]:
        """序列化指标基于上下文。

        默认情况下，保留完整的指标历史记录，包括持久化的成本、response_latencies 和
        token_usages 列表。

        当上下文={'use_snapshot': True}被传递时，将Metrics转换为MetricsSnapshot格式，
        以最小化载荷大小以供网络传输。

        Args:
            serializer: Pydantic 的默认值序列化器
            info: 序列化信息包含上下文

        Returns:
            具有基于上下文的指标已序列化的字典
        """
        # 获取默认值序列化
        data = serializer(self)

        # 检查我们是否应该使用快照序列化
        context = info.context if info else None
        use_snapshot = context.get("use_snapshot", False) if context else False

        if use_snapshot and "usage_to_metrics" in data:
            # 将每个指标替换为其快照
            usage_to_snapshots = {}
            for usage_id, metrics in self.usage_to_metrics.items():
                snapshot = metrics.get_snapshot()
                usage_to_snapshots[usage_id] = snapshot.model_dump()

            data["usage_to_metrics"] = usage_to_snapshots

        return data

    def get_combined_metrics(self) -> Metrics:
        total_metrics = Metrics()
        for metrics in self.usage_to_metrics.values():
            total_metrics.merge(metrics)
        return total_metrics

    def get_metrics_for_usage(self, usage_id: str) -> Metrics:
        if usage_id not in self.usage_to_metrics:
            raise Exception(f"LLM usage does not exist {usage_id}")

        return self.usage_to_metrics[usage_id]

    def register_llm(self, event: RegistryEvent):
        # 聆听 LLM 个创作并跟踪其指标
        llm = event.llm
        usage_id = llm.usage_id

        # 使用费用存在但尚未恢复
        if (
            usage_id in self.usage_to_metrics
            and usage_id not in self._restored_usage_ids
        ):
            llm.restore_metrics(self.usage_to_metrics[usage_id])
            self._restored_usage_ids.add(usage_id)

        # 使用是新的，跟踪其指标
        if usage_id not in self.usage_to_metrics and llm.metrics:
            self.usage_to_metrics[usage_id] = llm.metrics
