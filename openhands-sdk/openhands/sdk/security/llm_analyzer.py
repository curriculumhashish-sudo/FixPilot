from openhands.sdk.event import ActionEvent
from openhands.sdk.logger import get_logger
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.risk import SecurityRisk


logger = get_logger(__name__)


class LLMSecurityAnalyzer(SecurityAnalyzerBase):
    """LLM基于安全分析器。

    该分析器会尊重security_risk属性，该属性可以在生成动作时由LLM设置，类似于OpenHands
    的LLMRiskAnalyzer。

    它提供了一种轻量级安全分析方法，利用 LLM 对操作上下文和潜在风险的理解。
    """

    def security_risk(self, action: ActionEvent) -> SecurityRisk:
        """根据 LLM 提供的评估来评估安全风险。

        此方法检查操作是否具有由 LLM 设置的 security_risk 属性并返回它。 LLM 可能并不
        总是提供此属性，但如果未明确设置，则默认为
        UNKNOWN。
        """
        logger.debug(f"Analyzing security risk: {action} -- {action.security_risk}")

        return action.security_risk
