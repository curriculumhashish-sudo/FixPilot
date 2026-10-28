from typing import Any

from pydantic import Field
from rich.text import Text

from openhands.sdk.event.base import Event
from openhands.sdk.event.types import EventID, SourceType
from openhands.sdk.security.risk import SecurityRisk


class SecurityAnalysisEvent(Event):
    """已配置的安全分析器分配给待处理操作的风险级别。

    智能体执行时，每当配置了安全分析器并在对话中时，无论确认策略是否要求确认，都会发
    出一次。 这使得分析器的结论在事件日志和 UI 中可见，即使策略（例如
    ``NeverConfirm``）从未查阅它。

    该事件不会发送到 LLM。
    """

    source: SourceType = "environment"

    analyzer: str = Field(
        description="Kind of the security analyzer that produced these risks."
    )
    policy: str = Field(
        description="Kind of the confirmation policy in force when the actions "
        "were analyzed."
    )
    risks: dict[EventID, SecurityRisk] = Field(
        description="Risk level per analyzed action, keyed by ActionEvent id."
    )
    details: dict[EventID, dict[str, Any]] = Field(
        default_factory=dict,
        description="Optional analyzer-specific detail per action, keyed by "
        "ActionEvent id (for example probabilities, confidence, or a rationale).",
    )

    @property
    def visualize(self) -> Text:
        text = Text()
        text.append("Security Analysis\n", style="bold")
        text.append(f"analyzer={self.analyzer} policy={self.policy}\n")
        for action_id, risk in self.risks.items():
            text.append(f"  {action_id}: {risk.value}\n")
        return text
