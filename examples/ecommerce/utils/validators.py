"""
验证工具模块。

Validation utilities.
"""

import re
from typing import Optional


def validate_email(email: str) -> bool:
    """验证邮箱格式。

    Args:
        email: 邮箱地址。

    Returns:
        是否有效。
    """
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email))


def validate_discount_code(code: Optional[str], valid_codes: dict) -> Optional[float]:
    """验证折扣码并返回折扣率 - 故意制造的 KeyError bug。

    Args:
        code: 折扣码。
        valid_codes: 有效折扣码字典。

    Returns:
        折扣率，无效则返回 None。
    """
    if code is None:
        return None

    # Bug: 没有检查 code 是否存在于 valid_codes 中
    # 当 code 不存在时会抛出 KeyError
    return valid_codes[code]


def validate_stock(product: "Product", quantity: int) -> bool:
    """验证库存是否充足。

    Args:
        product: 商品对象。
        quantity: 请求数量。

    Returns:
        库存是否充足。
    """
    return product.stock >= quantity
