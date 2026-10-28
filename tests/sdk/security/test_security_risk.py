"""针对 SecurityRisk 枚举和 is_riskier 功能的综合测试。"""

from itertools import product

import pytest

from openhands.sdk.security.risk import SecurityRisk


def test_security_risk_enum_values():
    """测试 SecurityRisk 枚举是否具有预期值。"""
    assert SecurityRisk.UNKNOWN == "UNKNOWN"
    assert SecurityRisk.LOW == "LOW"
    assert SecurityRisk.MEDIUM == "MEDIUM"
    assert SecurityRisk.HIGH == "HIGH"


def test_security_risk_string_representation():
    """测试 SecurityRisk 值的字符串表示形式。"""
    assert str(SecurityRisk.UNKNOWN) == "UNKNOWN"
    assert str(SecurityRisk.LOW) == "LOW"
    assert str(SecurityRisk.MEDIUM) == "MEDIUM"
    assert str(SecurityRisk.HIGH) == "HIGH"


def test_riskiness_ordering():
    """使用 is_riskier 方法测试基本排序。"""
    # 测试自然风险排序：LOW < MEDIUM < HIGH
    assert SecurityRisk.MEDIUM.is_riskier(SecurityRisk.LOW)
    assert SecurityRisk.HIGH.is_riskier(SecurityRisk.MEDIUM)
    assert SecurityRisk.HIGH.is_riskier(SecurityRisk.LOW)

    # 测试反向排序（应为 False）
    assert not SecurityRisk.LOW.is_riskier(SecurityRisk.MEDIUM)
    assert not SecurityRisk.MEDIUM.is_riskier(SecurityRisk.HIGH)
    assert not SecurityRisk.LOW.is_riskier(SecurityRisk.HIGH)


@pytest.mark.parametrize(
    "risk_level",
    [
        SecurityRisk.LOW,
        SecurityRisk.MEDIUM,
        SecurityRisk.HIGH,
    ],
)
def test_riskiness_ordering_is_reflexive(risk_level):
    """测试 is_riskier 默认情况下是自反的。"""
    assert risk_level.is_riskier(risk_level)


@pytest.mark.parametrize(
    "risk_level",
    [
        SecurityRisk.LOW,
        SecurityRisk.MEDIUM,
        SecurityRisk.HIGH,
    ],
)
def test_riskiness_ordering_non_reflexive(risk_level):
    """测试 is_riskier 与自反=False 是非自反的。"""
    assert not risk_level.is_riskier(risk_level, reflexive=False)


def test_riskiness_ordering_undefined_for_unknown():
    """测试涉及 UNKNOWN 的比较是否会引发 ValueError。"""
    for first_risk, second_risk in product(list(SecurityRisk), repeat=2):
        if SecurityRisk.UNKNOWN in (first_risk, second_risk):
            with pytest.raises(ValueError):
                first_risk.is_riskier(second_risk)

        # 如果没有 UNKNOWN，则比较应该有效。 为了测试这一点，我们将调用该函数并确保它返
        # 回一个布尔值。
        #
        else:
            comparison = first_risk.is_riskier(second_risk)
            assert comparison in (True, False)


def test_security_risk_get_color():
    """测试 SecurityRisk.get_color() 返回预期的颜色代码。"""
    assert SecurityRisk.LOW.get_color() == "green"
    assert SecurityRisk.MEDIUM.get_color() == "yellow"
    assert SecurityRisk.HIGH.get_color() == "red"
    assert SecurityRisk.UNKNOWN.get_color() == "white"


def test_lt_ordering():
    """测试 __lt__ 是否遵循 LOW < MEDIUM < HIGH。"""
    assert SecurityRisk.LOW < SecurityRisk.MEDIUM
    assert SecurityRisk.MEDIUM < SecurityRisk.HIGH
    assert SecurityRisk.LOW < SecurityRisk.HIGH


def test_lt_not_less_than_self():
    """测试没有风险级别低于其自身。"""
    assert not SecurityRisk.LOW < SecurityRisk.LOW
    assert not SecurityRisk.MEDIUM < SecurityRisk.MEDIUM
    assert not SecurityRisk.HIGH < SecurityRisk.HIGH


def test_lt_reverse_ordering():
    """测试较高不小于较低。"""
    assert not SecurityRisk.HIGH < SecurityRisk.LOW
    assert not SecurityRisk.HIGH < SecurityRisk.MEDIUM
    assert not SecurityRisk.MEDIUM < SecurityRisk.LOW


def test_lt_unknown_raises():
    """测试比较 UNKNOWN 会产生 ValueError，与 is_riskier 一致。"""
    with pytest.raises(ValueError):
        SecurityRisk.UNKNOWN < SecurityRisk.LOW
    with pytest.raises(ValueError):
        SecurityRisk.LOW < SecurityRisk.UNKNOWN
    with pytest.raises(ValueError):
        SecurityRisk.UNKNOWN < SecurityRisk.UNKNOWN


def test_max_on_concrete_risks():
    """测试 max() 在具体风险列表上是否有效。

    SecurityRisk(str, 枚举) 通过 MRO 继承 str.__gt__，这给出了字母顺序 (HIGH < LOW <
    MEDIUM)。 所有比较方法（
    __lt__，__gt__，__le__，__ge__）都明确定义为可以覆盖此方法。@total_ordering在这里
    无能为力——它检测到字符串的比较方法已经定义
    ，跳过它们。
    """
    assert (
        max([SecurityRisk.LOW, SecurityRisk.MEDIUM, SecurityRisk.HIGH])
        == SecurityRisk.HIGH
    )
    assert max([SecurityRisk.LOW, SecurityRisk.LOW]) == SecurityRisk.LOW
    assert max([SecurityRisk.MEDIUM, SecurityRisk.HIGH]) == SecurityRisk.HIGH
