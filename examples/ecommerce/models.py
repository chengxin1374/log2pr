"""
电商系统数据模型。

E-commerce system data models.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    """用户模型。"""

    id: int
    username: str
    email: Optional[str] = None
    balance: float = 0.0


@dataclass
class Product:
    """商品模型。"""

    id: int
    name: str
    price: float
    stock: int
    category_id: int


@dataclass
class OrderItem:
    """订单项模型。"""

    product_id: int
    quantity: int
    unit_price: float


@dataclass
class Order:
    """订单模型。"""

    id: int
    user_id: int
    items: list[OrderItem]
    status: str = "pending"
    discount_code: Optional[str] = None
