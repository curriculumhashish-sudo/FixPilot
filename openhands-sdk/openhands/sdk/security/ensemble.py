"""将多个安全分析器组合成一个风险评估。

如果您有 ``PatternSecurityAnalyzer`` 捕获已知签名和 ``PolicyRailSecurityAnalyzer`` 捕
获组合威胁，那么您需要一个
answer: 所有这些风险中最坏的情况是什么？ 就是这样
这个模块的作用是——纯粹的融合，没有自身的检测。
"""

from __future__ import annotations

from pydantic import Field

from openhands.sdk.event import ActionEvent
from openhands.sdk.logger import get_logger
from openhands.sdk.security.analyzer import SecurityAnalyzerBase
from openhands.sdk.security.risk import SecurityRisk


logger = get_logger(__name__)


class EnsembleSecurityAnalyzer(SecurityAnalyzerBase):
    """将多个分析仪连接在一起并承担最坏情况的风险。

    使用它作为您在对话中设置的顶级分析器。 它调用每个子分析器，收集他们的风险评估，并
    返回最高的具体风险。 它本身不执行任何检测、提取或标准化。

    UNKNOWN 的工作原理（默认为 ``propagate_unknown=False``）：如果 *all* 子级返回
    UNKNOWN，则集成返回 UNKNOWN
    （其中
    ``ConfirmRisky`` 默认确认）。 如果任何子级返回具体级别，UNKNOWN 结果将被过滤掉，
    最高的具体级别获胜。

    对于 ``propagate_unknown=True``：如果 *any* 子级返回 UNKNOWN，则无论其他结果如何
    ，整体都会返回 UNKNOWN。 在更严格
    的环境中使用此功能，其中不完整的评估应触发确认。

    如果子分析器引发异常，它将贡献 HIGH（失败关闭，记录）。 这可以防止损坏的分析仪悄
    悄降低安全性。

    示例：:

        from openhands.sdk.security import (
            EnsembleSecurityAnalyzer,
            PatternSecurityAnalyzer,
            PolicyRailSecurityAnalyzer,
            ConfirmRisky,
            SecurityRisk,
        )

        analyzer = EnsembleSecurityAnalyzer(
            analyzers=[
                PolicyRailSecurityAnalyzer(),
                PatternSecurityAnalyzer(),
            ]
        )
        policy = ConfirmRisky(threshold=SecurityRisk.MEDIUM)
    """

    analyzers: list[SecurityAnalyzerBase] = Field(
        ...,
        description="Analyzers whose assessments are combined via max-severity",
        min_length=1,
    )
    propagate_unknown: bool = Field(
        default=False,
        description=(
            "When True, any child returning UNKNOWN causes the ensemble "
            "to return UNKNOWN. When False (default), UNKNOWN is filtered "
            "out if any child returns a concrete level."
        ),
    )

    def security_risk(self, action: ActionEvent) -> SecurityRisk:
        """通过子分析器之间的最大严重性融合来评估风险。"""
        results: list[SecurityRisk] = []
        for analyzer in self.analyzers:
            try:
                results.append(analyzer.security_risk(action))
            except Exception:
                logger.exception("Analyzer %s raised -- fail-closed to HIGH", analyzer)
                results.append(SecurityRisk.HIGH)

        has_unknown = SecurityRisk.UNKNOWN in results

        # 严格模式：任何 UNKNOWN 立即传播。
        if self.propagate_unknown and has_unknown:
            return SecurityRisk.UNKNOWN

        # 默认模式：过滤器UNKNOWN，取具体结果的最大值。
        concrete = [r for r in results if r != SecurityRisk.UNKNOWN]

        if not concrete:
            return SecurityRisk.UNKNOWN

        # max() 使用 SecurityRisk.__lt__； UNKNOWN已经被过滤掉了。
        return max(concrete)
