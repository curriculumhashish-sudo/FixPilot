from __future__ import annotations

from enum import Enum

from rich.text import Text


# 具体风险级别的共享排序。 UNKNOWN 被设计排除——涉及 UNKNOWN 的比较引发 ValueError。
#
_RISK_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


class SecurityRisk(str, Enum):
    """操作的安全风险级别。

    基于 OpenHands 安全风险级别，但适用于智能体-SDK。 整数值可以轻松比较和排序。
    """

    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def description(self) -> str:
        """获取人类可读的风险级别描述。"""
        descriptions = {
            SecurityRisk.LOW: (
                "Low risk - Safe operation with minimal security impact"
            ),
            SecurityRisk.MEDIUM: (
                "Medium risk - Moderate security impact, review recommended"
            ),
            SecurityRisk.HIGH: (
                "High risk - Significant security impact, confirmation required"
            ),
            SecurityRisk.UNKNOWN: ("Unknown risk - Risk level could not be determined"),
        }
        return descriptions.get(self, "Unknown risk level")

    def __str__(self) -> str:
        return self.name

    def get_color(self) -> str:
        """获取以富文本形式显示此风险级别的颜色。"""
        color_map = {
            SecurityRisk.LOW: "green",
            SecurityRisk.MEDIUM: "yellow",
            SecurityRisk.HIGH: "red",
            SecurityRisk.UNKNOWN: "white",
        }
        return color_map.get(self, "white")

    @property
    def visualize(self) -> Text:
        """返回此风险级别的富文本表示形式。"""
        content = Text()
        content.append(
            "Predicted Security Risk: ",
            style="bold",
        )
        content.append(
            f"{self.value}\n\n",
            style=f"bold {self.get_color()}",
        )
        return content

    def is_riskier(self, other: SecurityRisk, reflexive: bool = True) -> bool:
        """检查此风险级别是否比另一个风险级别更高。

        风险等级遵循自然排序： LOW 风险小于 MEDIUM，风险比 HIGH. UNKNOWN 不与其他级别
        相比较。

        为了使其像标准的有序域一样，我们本能地认为风险级别比其本身风险更大。 即：

            for risk_level in list(SecurityRisk):
                断言 risk_level.is_riskier(risk_level)

            # 更具体地说：
            断言 SecurityRisk.HIGH.is_riskier(SecurityRisk.HIGH) 断言
            SecurityRisk.MEDIUM.is_riskier(SecurityRisk.MEDIUM) 断言
            SecurityRisk.LOW.is_riskier(SecurityRisk.LOW)

        可以通过将 `reflexive` 参数设置为 False 来禁用此功能。

        Args:
            other (SecurityRisk): 要比较的其他风险级别。
            reflexive (bool): 这种关系是否是反射性的。

        Raises:
            ValueError: 如果任一风险级别为 UNKNOWN。
        """
        if self.value == SecurityRisk.UNKNOWN or other.value == SecurityRisk.UNKNOWN:
            raise ValueError("Cannot compare unknown risk levels.")

        return _RISK_ORDER[self.value] > _RISK_ORDER[other.value] or (
            reflexive and self == other
        )

    def _check_comparable(self, other: object) -> int | None:
        """验证其他的可比性并返回订购键。

        如果 other 不是 SecurityRisk，则返回 None（具有 NotImplemented 语义）。 如果
        任一侧为 UNKNOWN，则加注
        ValueError。
        """
        if not isinstance(other, SecurityRisk):
            return None
        if self == SecurityRisk.UNKNOWN or other == SecurityRisk.UNKNOWN:
            raise ValueError("Cannot compare unknown risk levels.")
        return _RISK_ORDER[other.value]

    def __lt__(self, other: object) -> bool:
        """比较订购的风险级别：LOW < MEDIUM < HIGH。

        UNKNOWN 不可比较——引发 ValueError，与 is_riskier() 一致。 这使得 max() 能够在
        没有辅助指令的情况下在具体风险列表上
        实现。
        """
        other_ord = self._check_comparable(other)
        if other_ord is None:
            return NotImplemented
        return _RISK_ORDER[self.value] < other_ord

    def __gt__(self, other: object) -> bool:
        """需要显式 __gt__，因为 str.__gt__ 优先通过
        MRO，按字母顺序排列 (HIGH < LOW < MEDIUM)。

        Note: @functools.total_ordering 在这里无能为力——它检测到
        str 的比较方法已定义并跳过它们。
        """
        other_ord = self._check_comparable(other)
        if other_ord is None:
            return NotImplemented
        return _RISK_ORDER[self.value] > other_ord

    def __le__(self, other: object) -> bool:
        other_ord = self._check_comparable(other)
        if other_ord is None:
            return NotImplemented
        return _RISK_ORDER[self.value] <= other_ord

    def __ge__(self, other: object) -> bool:
        other_ord = self._check_comparable(other)
        if other_ord is None:
            return NotImplemented
        return _RISK_ORDER[self.value] >= other_ord
