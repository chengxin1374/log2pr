"""
计算工具模块 - 包含故意制造的 bug。

Calculation utilities - Contains intentional bugs.
"""

from typing import Optional


def calculate_subtotal(items: list) -> float:
    """计算订单小计。

    Args:
        items: 订单项列表。

    Returns:
        小计金额。
    """
    total = 0.0
    for item in items:
        total += item.unit_price * item.quantity
    return total


def apply_discount(amount: float, discount_rate: Optional[float]) -> float:
    """应用折扣 - 故意制造的 TypeError bug。

    Args:
        amount: 原始金额。
        discount_rate: 折扣率 (0-1)。

    Returns:
        折扣后金额。
    """
    # Bug: 没有检查 discount_rate 是否为 None
    # 当 discount_rate 为 None 时会抛出 TypeError
    return amount * (1 - discount_rate)


def calculate_tax(amount: float, tax_rate: float = 0.1) -> float:
    """计算税费。

    Args:
        amount: 金额。
        tax_rate: 税率，默认 10%。

    Returns:
        税费金额。
    """
    return amount * tax_rate


def calculate_total(
    subtotal: float,
    discount_rate: Optional[float],
    tax_rate: float = 0.1,
) -> float:
    """计算订单总价。

    Args:
        subtotal: 小计金额。
        discount_rate: 折扣率。
        tax_rate: 税率。

    Returns:
        订单总价。
    """
    discounted = apply_discount(subtotal, discount_rate)
    tax = calculate_tax(discounted, tax_rate)
    return discounted + tax
