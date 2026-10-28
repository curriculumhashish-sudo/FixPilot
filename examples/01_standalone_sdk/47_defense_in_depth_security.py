"""纵深防御安全：用ConfirmRisky组成本地分析器。

此示例演示如何将深度防御分析器系列连接到对话中。 分析器在动作边界对智能体动作进行分类
； 确认策略决定是否提示词用户。

分析器选择不会自动更改确认策略——您必须显式配置两者。
"""

from openhands.sdk.security import (
    ConfirmRisky,
    EnsembleSecurityAnalyzer,
    PatternSecurityAnalyzer,
    PolicyRailSecurityAnalyzer,
    SecurityRisk,
)


# 创建分析器集成
security_analyzer = EnsembleSecurityAnalyzer(
    analyzers=[
        PolicyRailSecurityAnalyzer(),
        PatternSecurityAnalyzer(),
    ]
)

# 确认策略：提示词用户进行HIGH-风险操作
confirmation_policy = ConfirmRisky(threshold=SecurityRisk.HIGH)

# 连入对话：
#
#   conversation = Conversation(agent=agent, workspace=".")
#   conversation.set_security_analyzer(security_analyzer)
#   conversation.set_confirmation_policy(confirmation_policy)
#
# 现在每个智能体操作都会通过分析器。 HIGH -> 确认提示词。 MEDIUM/LOW -> 允许。 UNKNOWN -
# > 默认确认 (confirm_unknown=True)。
#
# 对于更严格的环境，降低阈值：
#   confirmation_policy = ConfirmRisky(threshold=SecurityRisk.MEDIUM)

print("Defense-in-depth security analyzer configured.")
print(f"Analyzer: {security_analyzer}")
print(f"Confirmation policy: {confirmation_policy}")
print("EXAMPLE_COST: 0")
