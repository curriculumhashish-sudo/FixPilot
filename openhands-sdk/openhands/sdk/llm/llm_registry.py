from collections.abc import Callable
from types import MappingProxyType
from typing import ClassVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from openhands.sdk.llm.llm import LLM
from openhands.sdk.logger import get_logger


logger = get_logger(__name__)


class RegistryEvent(BaseModel):
    llm: LLM

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True,
    )


class LLMRegistry:
    """用于按使用 ID 管理 LLM 个实例的最小 LLM 注册表。

    注册表提供了一种简单的方法来管理多个 LLM 实例，从而避免了需要重新配置 LLMs 的需求
    。

    的注册表也确保每个注册的 LLM 具有独立的指标，防止指标被共享 LLMs 通过创建的
    model_copy(). 这对于创建的场景非常重要上下文压缩器  LLM
    from an agent LLM, where each should track its own usage independently.
    """

    registry_id: str
    retry_listener: Callable[[int, int], None] | None

    def __init__(
        self,
        retry_listener: Callable[[int, int], None] | None = None,
    ):
        """初始化LLM注册表。

        Args:
            retry_listener: 重试事件的可选回调。
        """
        self.registry_id = str(uuid4())
        self.retry_listener = retry_listener
        self._usage_to_llm: dict[str, LLM] = {}
        # 跟踪指标对象 ID 以检测共享指标
        self._metrics_ids: set[int] = set()
        self.subscriber: Callable[[RegistryEvent], None] | None = None

    def subscribe(self, callback: Callable[[RegistryEvent], None]) -> None:
        """订阅注册表事件。

        Args:
            callback: 当 LLMs 创建或更新时调用的函数。
        """
        self.subscriber = callback

    def notify(self, event: RegistryEvent) -> None:
        """通知订阅者注册表事件。

        Args:
            event: 要通知的注册表事件。
        """
        if self.subscriber:
            try:
                self.subscriber(event)
            except Exception as e:
                logger.warning(f"Failed to emit event: {e}")

    @property
    def usage_to_llm(self) -> MappingProxyType[str, LLM]:
        """访问内部使用 ID 到 LLM 映射（只读视图）。"""

        return MappingProxyType(self._usage_to_llm)

    def _ensure_independent_metrics(self, llm: LLM) -> None:
        """确保 LLM 有独立的指标，不与其他 LLMs 共享。

        当 LLMs 通过 model_copy() 创建时，默认情况下，Pydantic 会浅拷贝私有属性，导致
        原始和拷贝的 LLM 共享同一个 Metrics
        对象。 该方法检测共享行为，并重置指标以确保每个LLM都能独立跟踪其使用情况。

        Args:
            llm: 要检查并可能重置指标的 LLM 实例。
        """
        # 如果需要，访问指标以触发延迟初始化
        metrics = llm.metrics
        metrics_id = id(metrics)

        # 检查此指标对象是否已被另一个 LLM 跟踪
        if metrics_id in self._metrics_ids:
            logger.debug(
                f"[LLM registry {self.registry_id}]: Detected shared metrics for "
                f"usage '{llm.usage_id}', resetting to independent metrics"
            )
            llm.reset_metrics()
            # 重置后获取新的指标ID
            metrics_id = id(llm.metrics)

        # 跟踪此指标对象 ID
        self._metrics_ids.add(metrics_id)

    def add(self, llm: LLM) -> None:
        """将 LLM 实例添加到注册表。

        此方法确保 LLM 在注册之前具有独立的度量。 如果LLM的指标与另一个注册的LLM（e.g
        .，由于model_copy()）共享，则会自动创建新的指标。

        Args:
            llm: 要注册的 LLM 实例。

        Raises:
            ValueError: 如果注册表中已经存在llm.usage_id。
        """
        usage_id = llm.usage_id
        if usage_id in self._usage_to_llm:
            message = (
                f"Usage ID '{usage_id}' already exists in registry. "
                "Use a different usage_id on the LLM or "
                "call get() to retrieve the existing LLM."
            )
            raise ValueError(message)

        # 注册前确保此 LLM 具有独立的指标
        self._ensure_independent_metrics(llm)

        self._usage_to_llm[usage_id] = llm
        self.notify(RegistryEvent(llm=llm))
        logger.debug(
            f"[LLM registry {self.registry_id}]: Added LLM for usage {usage_id}"
        )

    def get(self, usage_id: str) -> LLM:
        """从注册表获取 LLM 实例。

        Args:
            usage_id: LLM 使用槽的唯一标识符。

        Returns:
            LLM 实例。

        Raises:
            KeyError: 如果在注册表中没有找到usage_id。
        """
        if usage_id not in self._usage_to_llm:
            raise KeyError(
                f"Usage ID '{usage_id}' not found in registry. "
                "Use add() to register an LLM first."
            )

        logger.info(
            f"[LLM registry {self.registry_id}]: Retrieved LLM for usage {usage_id}"
        )
        return self._usage_to_llm[usage_id]

    def remove(self, usage_id: str) -> None:
        """从注册表中删除 LLM 实例（如果存在）。

        与：meth:`add` 和：meth:`get` 不同，当 ``usage_id`` 不存在时，这是一个无操作
        ，因此调用者可以使延迟缓存的槽无效，而无需先
        检查它。

        Args:
            usage_id: 使用槽从注册表掉落。
        """
        if self._usage_to_llm.pop(usage_id, None) is not None:
            logger.debug(
                f"[LLM registry {self.registry_id}]: Removed LLM for usage {usage_id}"
            )

    def list_usage_ids(self) -> list[str]:
        """列出所有已注册的使用 ID。"""

        return list(self._usage_to_llm.keys())
