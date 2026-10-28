"""将对话事件桥接到遥测接收器上。

这里有两个属性是不可协商的：

* **总计。**每个公共方法都将其整个主体包装在 ``try/except`` 中。
  ``PubSub`` 隔离了订阅者的失败，但 ``EventService.subscribe_to_events`` 期待初始状态
  推送，只捕获
  ``TimeoutError``，因此在注册期间发生逃逸的异常会导致 * 启动 *。
* **非阻塞。** ``__call__`` 必须是 ``async def`` 才能满足
  ``Subscriber`` ABC，但其主体包含 **0 ``await``** — 它终止于同步 ``sink.emit``。
  ``PubSub.__call__`` 等待其订阅者，因此任何较慢的速度都会阻碍整个对话的事件扇出。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from openhands.agent_server.pub_sub import Subscriber
from openhands.agent_server.telemetry import models as m
from openhands.agent_server.telemetry.factory import DiagnosticEventFactory
from openhands.agent_server.telemetry.sanitizer import (
    COST_BOUNDS,
    COUNT_BOUNDS,
    DURATION_BOUNDS,
    TOKEN_BOUNDS,
    UNKNOWN_TOKEN,
    bucket,
    normalize_error_code,
    safe_token,
)
from openhands.agent_server.telemetry.sink import TelemetrySink
from openhands.sdk.conversation.state import ConversationExecutionStatus
from openhands.sdk.event import AgentErrorEvent, ConversationStateUpdateEvent, Event
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.sdk.event.conversation_state import FULL_STATE_KEY
from openhands.sdk.logger import get_logger
from openhands.sdk.utils import utc_now


__all__ = [
    "ConversationTelemetryContext",
    "TelemetrySubscriber",
]


logger = get_logger(__name__)

# 源自 SDK 枚举而不是硬编码，因此新的终端状态不能默默地停止报告。
#
_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset(
    s.value for s in ConversationExecutionStatus if s.is_terminal()
)
_RUNNING_STATUS: Final[str] = ConversationExecutionStatus.RUNNING.value
# ：当观察到运行但在没有最终状态的情况下结束时报告，e.g。 ：服务器在运行中停止。 绝不是
# 原始的非终端状态，这会将：之类的值放在名为 terminal_status 的字段中。
#
_INTERRUPTED_STATUS: Final[str] = "interrupted"
_FAILURE_STATUSES: Final[frozenset[str]] = _TERMINAL_STATUSES - {
    ConversationExecutionStatus.FINISHED.value
}
_EXECUTION_STATUS_KEY: Final[str] = "execution_status"
_STATS_KEY: Final[str] = "stats"


@dataclass(frozen=True, slots=True)
class ConversationTelemetryContext:
    """关于一次谈话的经过净化的事实，一开始就解决了。"""

    conversation_ref: str
    user_id: str | None
    llm_model_family: str
    agent_kind: str
    tool_count: int
    is_fork: bool
    has_agent_profile: bool
    workspace_kind: str
    confirmation_policy: str
    is_automation: bool = False


@dataclass(slots=True)
class TelemetrySubscriber(Subscriber[Event]):
    """发出单个对话的生命周期和失败事件。"""

    conversation_id: UUID
    sink: TelemetrySink
    factory: DiagnosticEventFactory
    context: ConversationTelemetryContext

    _started_at: datetime = field(default_factory=utc_now)
    _event_count: int = 0
    _terminal_emitted: bool = False
    _last_status: str | None = None
    _seeded: bool = False
    _run_observed: bool = False
    _total_tokens: int | None = None
    _total_cost: float | None = None

    async def __call__(self, event: Event) -> None:
        try:
            self._handle(event)
        except Exception:
            logger.debug("Telemetry subscriber failed to handle event", exc_info=True)

    def _handle(self, event: Event) -> None:
        self._event_count += 1

        match event:
            case AgentErrorEvent():
                self._emit_error_from_agent_event(event)
            case ConversationErrorEvent():
                self._emit_error_from_conversation_event(event)
            case ConversationStateUpdateEvent():
                self._handle_state_update(event)

    def _handle_state_update(self, event: ConversationStateUpdateEvent) -> None:
        # 从每项包含统计数据的更新中跟踪使用情况：在实时运行中，终端状态以裸字符串
        # ``execution_status`` 更新的形式到达，而最终 ``full_state`` 拍照则在最后。
        #
        self._capture_usage(event)
        status = _extract_status(event)
        if status is None:
            return
        self._last_status = status

        if not self._seeded:
            # 附加时间推送是一个基线，而不是一个过渡； 否则每次补液都会重新发出终止事件
            # 。
            #
            self._seeded = True
            self._terminal_emitted = status in _TERMINAL_STATUSES
            return

        if status == _RUNNING_STATUS:
            self._run_observed = True

        if status in _TERMINAL_STATUSES:
            self._emit_terminal(status)

    def emit_started(self) -> None:
        """注册时发出规范 ``conversation_created`` 一次。"""
        try:
            properties = m.ConversationStartedProperties(
                conversation_ref=self.context.conversation_ref,
                llm_model_family=self.context.llm_model_family,
                agent_kind=self.context.agent_kind,
                tool_count=self.context.tool_count,
                is_fork=self.context.is_fork,
                has_agent_profile=self.context.has_agent_profile,
                workspace_kind=self.context.workspace_kind,
                confirmation_policy=self.context.confirmation_policy,
                is_automation=self.context.is_automation,
            )
            self.sink.emit(
                self.factory.build(
                    m.EventName.CONVERSATION_CREATED,
                    properties,
                    user_id=self.context.user_id,
                    insert_id=(f"conversation_created:{self.context.conversation_ref}"),
                )
            )
        except Exception:
            logger.debug("Telemetry failed to emit conversation_created", exc_info=True)

    def _emit_terminal(self, status: str) -> None:
        if self._terminal_emitted:
            return
        self._terminal_emitted = True

        token = safe_token(status, default=UNKNOWN_TOKEN)
        elapsed = (utc_now() - self._started_at).total_seconds()
        properties = m.ConversationOutcomeProperties(
            conversation_ref=self.context.conversation_ref,
            terminal_status=token,
            duration_bucket=bucket(elapsed, DURATION_BOUNDS),
            event_count_bucket=bucket(self._event_count, COUNT_BOUNDS),
            total_tokens_bucket=bucket(self._total_tokens, TOKEN_BOUNDS),
            cost_bucket=bucket(self._total_cost, COST_BOUNDS),
            llm_model_family=self.context.llm_model_family,
        )
        # 中断的运行未完成，因此它没有“完成”。
        event_name = (
            m.EventName.CONVERSATION_FAILED
            if token in _FAILURE_STATUSES or token == _INTERRUPTED_STATUS
            else m.EventName.CONVERSATION_FINISHED
        )
        self.sink.emit(
            self.factory.build(event_name, properties, user_id=self.context.user_id)
        )

    def _capture_usage(self, event: ConversationStateUpdateEvent) -> None:
        """记录来自携带统计数据的状态更新的总代币/成本。

        ``stats`` 密钥更新（在每次 LLM 调用后发布）和
        ``full_state``快照携带``usage_to_metrics``，使用id到``MetricsSnapshot``的映射
        。 对它求和就得到了对话
        总数，这些总数被存储在终端事件中——原始数据永远不会被报告。 尽力而为：任何形状
        变化都会降级为 ``unknown`` 而不是升高。
        """
        try:
            key = getattr(event, "key", None)
            value = getattr(event, "value", None)
            if not isinstance(value, dict):
                return None
            if key == _STATS_KEY:
                stats = value
            elif key == FULL_STATE_KEY:
                stats = value.get("stats")
            else:
                return None
            if not isinstance(stats, dict):
                return None
            per_usage = stats.get("usage_to_metrics")
            if not isinstance(per_usage, dict):
                return None

            tokens = 0
            cost = 0.0
            for snapshot in per_usage.values():
                if not isinstance(snapshot, dict):
                    continue
                cost += float(snapshot.get("accumulated_cost") or 0.0)
                usage = snapshot.get("accumulated_token_usage")
                if isinstance(usage, dict):
                    tokens += int(usage.get("prompt_tokens") or 0)
                    tokens += int(usage.get("completion_tokens") or 0)
            self._total_tokens = tokens
            self._total_cost = cost
        except Exception:
            logger.debug("Could not read usage from state snapshot", exc_info=True)

    def _emit_error_from_agent_event(self, event: AgentErrorEvent) -> None:
        """报告工具级智能体错误。

        仅读取 ``tool_name``。 ``AgentErrorEvent.error`` 是脚手架的消息，通常包含工具
        输出、路径和模型文本，因此永远不会被触
        及。 ``classification`` 字段确定错误是预期的智能体结果还是诊断结果。
        """
        fingerprint = normalize_error_code("AgentError")
        classification = event.classification
        properties = m.ErrorProperties(
            conversation_ref=self.context.conversation_ref,
            error_class=fingerprint.error_class,
            error_category="tool_execution",
            error_fingerprint=fingerprint.error_fingerprint,
            is_first_party=True,
            is_terminal=False,
            error_telemetry=(
                "diagnostic"
                if classification is None
                or classification.kind in {"internal", "unknown"}
                else "outcome"
            ),
            tool_name=safe_token(getattr(event, "tool_name", None)),
        )
        self.sink.emit(
            self.factory.build(
                m.EventName.CONVERSATION_ERROR, properties, user_id=self.context.user_id
            )
        )

    def _emit_error_from_conversation_event(
        self, event: ConversationErrorEvent
    ) -> None:
        """报告对话级故障。

        仅读取 ``code`` — 它的文档字符串将其记录为“通常是一种类型”。 同级 ``detail``
        领域是自由形式的散文，从未被触及。
        """
        fingerprint = normalize_error_code(getattr(event, "code", None))
        classification = event.classification
        properties = m.ErrorProperties(
            conversation_ref=self.context.conversation_ref,
            error_class=fingerprint.error_class,
            error_category=fingerprint.error_category,
            error_fingerprint=fingerprint.error_fingerprint,
            is_first_party=True,
            is_terminal=True,
            error_telemetry=(
                "diagnostic"
                if classification is None
                or classification.kind in {"internal", "unknown"}
                else "outcome"
            ),
        )
        self.sink.emit(
            self.factory.build(
                m.EventName.CONVERSATION_ERROR, properties, user_id=self.context.user_id
            )
        )

    async def close(self) -> None:
        """仅当实际观察到运行时才发出终端事件。

        订阅者在每个 ``_start_event_service`` 路径上附加，包括当用户仅 * 打开 * 现有
        对话时的惰性附加。 在这里无条件发射产生了
        ``conversation_finished`` — 携带非终结符
        ``terminal_status`` 像 ``paused`` — 对于本次会话没有执行任何操作的对话，没有
        匹配的
        ``conversation_created``，并且在每个查看然后重新启动循环中再次进行相同的操作
        ``conversation_ref``.

        在观察到的运行上开启门禁，保持了崩溃中运行的安全网：``running`` 会继续报告，
        即使``interrupted`` 从未报告终端状态。

        故意 ** 不 ** 关闭 ``self.sink``：接收器在整个进程范围内共享，并且比每次对话
        的寿命都长。
        """
        try:
            if self._terminal_emitted or not self._run_observed:
                return
            self._emit_terminal(_INTERRUPTED_STATUS)
        except Exception:
            logger.debug("Telemetry subscriber failed to close", exc_info=True)


def _extract_status(event: ConversationStateUpdateEvent) -> str | None:
    """将 ``execution_status`` 从状态更新中拉出（如果存在）。"""
    key = getattr(event, "key", None)
    value: Any = getattr(event, "value", None)

    if key == _EXECUTION_STATUS_KEY and isinstance(value, str):
        return value
    if key == FULL_STATE_KEY and isinstance(value, dict):
        status = value.get(_EXECUTION_STATUS_KEY)
        if isinstance(status, str):
            return status
    return None
