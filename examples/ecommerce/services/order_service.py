"""
订单服务模块 - 协调各模块，触发跨文件 bug。

Order service module - Coordinates modules, triggers cross-file bugs.
"""

import logging
from typing import Optional

from models import Order, OrderItem, Product, User
from utils.calculations import calculate_subtotal, calculate_total
from utils.validators import validate_discount_code, validate_stock
from services.payment_service import PaymentService

logger = logging.getLogger(__name__)


# 模拟数据库
PRODUCTS_DB: dict[int, Product] = {
    1: Product(id=1, name="Laptop", price=999.99, stock=10, category_id=1),
    2: Product(id=2, name="Mouse", price=29.99, stock=50, category_id=2),
    3: Product(id=3, name="Keyboard", price=79.99, stock=30, category_id=2),
}

# 有效折扣码
VALID_DISCOUNT_CODES: dict[str, float] = {
    "SAVE10": 0.1,
    "SAVE20": 0.2,
    "VIP30": 0.3,
}


class OrderService:
    """订单服务类。"""

    def __init__(self):
        """初始化订单服务。"""
        self.payment_service = PaymentService()
        self.orders: dict[int, Order] = {}

    def create_order(
        self,
        user: User,
        items: list[OrderItem],
        discount_code: Optional[str] = None,
    ) -> Order:
        """创建订单。

        Args:
            user: 用户对象。
            items: 订单项列表。
            discount_code: 折扣码。

        Returns:
            创建的订单。
        """
        # 验证库存
        for item in items:
            product = PRODUCTS_DB.get(item.product_id)
            if not product:
                raise ValueError(f"Product {item.product_id} not found")
            if not validate_stock(product, item.quantity):
                raise ValueError(f"Insufficient stock for product {product.name}")

        # 创建订单
        order_id = len(self.orders) + 1
        order = Order(
            id=order_id,
            user_id=user.id,
            items=items,
            discount_code=discount_code,
        )

        self.orders[order_id] = order
        logger.info(f"Created order {order_id} for user {user.id}")

        return order

    def process_order(self, order: Order, user: User) -> dict:
        """处理订单 - 这里会触发跨文件的 bug。

        Args:
            order: 订单对象。
            user: 用户对象。

        Returns:
            处理结果。
        """
        # 计算小计
        subtotal = calculate_subtotal(order.items)
        logger.info(f"Order {order.id} subtotal: {subtotal}")

        # 验证折扣码 - Bug 在 validators.py 中
        # 如果 discount_code 不在 VALID_DISCOUNT_CODES 中，会抛出 KeyError
        discount_rate = validate_discount_code(order.discount_code, VALID_DISCOUNT_CODES)
        logger.info(f"Discount rate: {discount_rate}")

        # 计算总价 - Bug 在 calculations.py 中
        # 如果 discount_rate 是 None，apply_discount 会抛出 TypeError
        total = calculate_total(subtotal, discount_rate)
        logger.info(f"Order {order.id} total: {total}")

        # 处理支付
        transaction = self.payment_service.process_payment(user, order, total)

        # 更新订单状态
        order.status = "completed"

        return {
            "order_id": order.id,
            "total": total,
            "transaction": transaction,
        }

    def get_order(self, order_id: int) -> Optional[Order]:
        """获取订单。

        Args:
            order_id: 订单 ID。

        Returns:
            订单对象，不存在则返回 None。
        """
        return self.orders.get(order_id)
