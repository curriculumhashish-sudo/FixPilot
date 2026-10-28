"""智能体操作边界的确定性本地安全分析器。

两个分析器，每个分析器负责一项工作：

- ``PatternSecurityAnalyzer`` -- 具有两个语料库扫描的正则表达式签名
- ``PolicyRailSecurityAnalyzer`` -- 组合条件规则（获取到执行等）

将它们与 ``EnsembleSecurityAnalyzer`` 一起连接到对话中，并且
``ConfirmRisky`` 在执行前对智能体操作进行分类。 没有网络调用，没有模型推理，没有超出
SDK 运行时的依赖项。
"""

from openhands.sdk.security.defense_in_depth.pattern import PatternSecurityAnalyzer
from openhands.sdk.security.defense_in_depth.policy_rails import (
    PolicyRailSecurityAnalyzer,
)


__all__ = [
    "PatternSecurityAnalyzer",
    "PolicyRailSecurityAnalyzer",
]
