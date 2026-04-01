"""
支付服务模块 - 包含故意制造的 bug。

Payment service module - Contains intentional bugs.
"""

import logging
from typing import Optional

from models import Order, User

logger = logging.getLogger(__name__)


class PaymentService:
    """支付服务类。"""

    def __init__(self):
        """初始化支付服务。"""
        self.transactions: dict[int, dict] = {}

    def process_payment(
        self,
        user: User,
        order: Order,
        amount: float,
    ) -> dict:
        """处理支付 - 故意制造的 AttributeError bug。

        Args:
            user: 用户对象。
            order: 订单对象。
            amount: 支付金额。

        Returns:
            交易结果字典。
        """
        # Bug: 假设 user 一定有 email 属性，但 email 可能为 None
        # 当 email 为 None 时，后续使用会出问题
        # 实际上这个 bug 比较隐蔽，需要结合其他情况触发
        logger.info(f"Processing payment for user {user.id}")

        # 模拟支付处理
        transaction_id = len(self.transactions) + 1

        # Bug: 没有检查 user.balance 是否足够
        # 直接扣除余额，可能变成负数
        user.balance -= amount

        transaction = {
            "id": transaction_id,
            "user_id": user.id,
            "order_id": order.id,
            "amount": amount,
            "status": "completed",
        }

        self.transactions[transaction_id] = transaction
        logger.info(f"Payment completed: transaction {transaction_id}")

        return transaction

    def refund(self, transaction_id: int) -> Optional[dict]:
        """退款。

        Args:
            transaction_id: 交易 ID。

        Returns:
            退款结果，不存在则返回 None。
        """
        if transaction_id not in self.transactions:
            return None

        transaction = self.transactions[transaction_id]
        transaction["status"] = "refunded"

        logger.info(f"Refunded transaction {transaction_id}")
        return transaction

    def get_user_balance(self, user: User) -> float:
        """获取用户余额 - 故意制造的 AttributeError bug。

        Args:
            user: 用户对象。

        Returns:
            用户余额。
        """
        # Bug: 假设 user 一定有 balance 属性
        # 如果传入的是普通 dict 而不是 User 对象，会抛出 AttributeError
        return user.balance
