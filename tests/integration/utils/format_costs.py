#!/usr/bin/env python3

"""
以适当的精度格式化成本值的实用函数。
"""


def format_cost(value: float) -> str:
    """
    以智能精度格式化成本，即使金额很小也能显示有意义的值。

    Args:
        value: 要格式化的成本值（必须是数值）

    Returns:
        具有适当精度的格式化成本字符串
    """
    if value == 0.0:
        # 将零作为特殊情况处理
        return "$0.00"
    elif abs(value) >= 0.01:
        # 典型金额的正常四舍五入
        return f"${value:.2f}"
    elif abs(value) >= 0.001:
        # 小数四舍五入为 2 位有效数字
        return f"${value:.2g}"
    else:
        # 对于非常小的数字使用科学记数法
        return f"${value:.1e}"
