from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from openhands.sdk.event.base import Event
from openhands.sdk.event.llm_convertible import ActionEvent
from openhands.sdk.logger import get_logger
from openhands.sdk.security.risk import SecurityRisk
from openhands.sdk.utils.models import (
    DiscriminatedUnionMixin,
)


logger = get_logger(__name__)


class SecurityAnalysis(BaseModel):
    """分析一项操作的结果：风险级别加上可选细节。"""

    risk: SecurityRisk
    details: dict[str, Any] | None = Field(
        default=None,
        description="Analyzer-specific detail behind the risk (probabilities, "
        "confidence, rationale, ...). Surfaced in SecurityAnalysisEvent.",
    )


class SecurityAnalyzerBase(DiscriminatedUnionMixin, ABC):
    """安全分析器的抽象基类。

    安全分析器在执行操作之前评估操作的风险，并可以根据安全策略影响对话流。

    这是改编自 OpenHands SecurityAnalyzer，但旨在与智能体-SDK 的基于对话的架构配合使
    用。
    """

    @abstractmethod
    def security_risk(self, action: ActionEvent) -> SecurityRisk:
        """评估 ActionEvent 的安全风险。

        这是分析ActionEvent并返回其风险水平的核心方法。 实施过程中应检查行动的内容上
        下文和潜在影响，以确定适当的风险级别。

        Args:
            action: ActionEvent 安全风险分析

        Returns:
            ActionSecurityRisk 枚举表示风险级别
        """
        pass

    def analyze_event(self, event: Event) -> SecurityRisk | None:
        """分析事件的安全风险。

        这是一个方便的方法，它检查事件是否是一个动作，如果是，则调用 security_risk()
        。 非动作事件返回None。

        Args:
            event: 要分析的事件

        Returns:
            ActionSecurityRisk 如果事件是一个动作，None 否则
        """
        if isinstance(event, ActionEvent):
            return self.security_risk(event)
        return None

    def should_require_confirmation(
        self, risk: SecurityRisk, confirmation_mode: bool = False
    ) -> bool:
        """确定某个操作是否需要用户确认。

        这实现了基于风险级别和确认模式设置的默认确认逻辑。

        Args:
            risk: 操作的安全风险级别
            confirmation_mode: 是否启用确认模式

        Returns:
            True 如果需要确认，False 否则
        """
        if risk == SecurityRisk.HIGH:
            # HIGH 风险行动始终需要确认
            return True
        elif risk == SecurityRisk.UNKNOWN and not confirmation_mode:
            # UNKNOWN 如果未配置安全分析器，则需要确认风险
            return True
        elif confirmation_mode:
            # 确认模式下，所有操作都需要确认
            return True
        else:
            # LOW 和 MEDIUM 风险操作默认不需要确认
            return False

    def analyze_action(self, action: ActionEvent) -> SecurityAnalysis:
        """分析一项操作，返回其风险和可选细节。

        默认实现包装：meth:`security_risk` ，但没有任何细节。 能够解释其结论（概率、
        置信度、基本原理）的分析者应该推翻这一点。
        """
        return SecurityAnalysis(risk=self.security_risk(action))

    def analyze_actions(
        self, pending_actions: list[ActionEvent]
    ) -> list[tuple[ActionEvent, SecurityAnalysis]]:
        """分析待处理的操作，返回（操作，分析）对。

        分析器错误会将该操作默认为 HIGH 风险，并在分析详细信息中记录错误。 现有的覆盖
        :meth:`analyze_pending_actions` 提供了没有细节的判决。
        """
        if (
            type(self).analyze_pending_actions
            is not SecurityAnalyzerBase.analyze_pending_actions
        ):
            return [
                (action, SecurityAnalysis(risk=risk))
                for action, risk in self.analyze_pending_actions(pending_actions)
            ]
        return self._analyze_actions(pending_actions)

    def _analyze_actions(
        self, pending_actions: list[ActionEvent]
    ) -> list[tuple[ActionEvent, SecurityAnalysis]]:
        analyzed: list[tuple[ActionEvent, SecurityAnalysis]] = []
        for action_event in pending_actions:
            try:
                analysis = self.analyze_action(action_event)
                logger.debug(
                    f"Action {action_event} analyzed with risk level: {analysis.risk}"
                )
            except Exception as e:
                logger.error(f"Error analyzing action {action_event}: {e}")
                # 为了安全起见，默认为 HIGH 分析错误风险
                analysis = SecurityAnalysis(
                    risk=SecurityRisk.HIGH, details={"error": str(e)}
                )
            analyzed.append((action_event, analysis))
        return analyzed

    def analyze_pending_actions(
        self, pending_actions: list[ActionEvent]
    ) -> list[tuple[ActionEvent, SecurityRisk]]:
        """分析对话中所有待处理的操作。

        仅返回每个操作的风险级别。 覆盖可以通过 ``super()`` 调用此实现，而无需重新输
        入批量覆盖。

        Args:
            pending_actions: 需要分析的无与伦比的操作

        Returns:
            每个待处理操作包含 (action, risk_level) 的元组列表
        """
        return [
            (action, analysis.risk)
            for action, analysis in self._analyze_actions(pending_actions)
        ]
