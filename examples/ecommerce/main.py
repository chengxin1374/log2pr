"""
电商系统主入口 - 运行测试用例，触发跨文件错误。

E-commerce system main entry - Run test cases, trigger cross-file errors.

这个文件模拟了一个真实的电商订单处理场景，错误会跨越多个文件传播：
1. main.py -> order_service.py -> validators.py (KeyError)
2. main.py -> order_service.py -> calculations.py (TypeError)

测试用例说明：
- Test 1: KeyError - 折扣码不存在
- Test 2: TypeError - 折扣率为 None 导致乘法错误
"""

from models import Order, OrderItem, User
from services.order_service import OrderService


def test_keyerror_invalid_discount_code():
    """测试 KeyError - 使用无效折扣码。

    错误传播路径：
    main.py -> order_service.py:process_order()
            -> validators.py:validate_discount_code()

    错误原因：
    validators.py:25 直接访问 valid_codes[code]，但 code 不存在于字典中。
    """
    print("\n" + "=" * 60)
    print("Test 1: KeyError - Invalid Discount Code")
    print("=" * 60)

    user = User(id=1, username="testuser", email="test@example.com", balance=1000.0)
    order_service = OrderService()

    # 创建订单
    items = [OrderItem(product_id=1, quantity=1, unit_price=999.99)]
    order = order_service.create_order(user, items, discount_code="INVALID_CODE")

    try:
        # 处理订单 - 会触发 KeyError
        result = order_service.process_order(order, user)
        print(f"✅ Order processed: {result}")
    except KeyError as e:
        print(f"❌ KeyError occurred: {e}")
        print(f"   Error location: validators.py:validate_discount_code()")
        print(f"   Root cause: discount code 'INVALID_CODE' not in VALID_DISCOUNT_CODES")


def test_typeerror_none_discount():
    """测试 TypeError - 折扣率为 None。

    错误传播路径：
    main.py -> order_service.py:process_order()
            -> calculations.py:calculate_total()
            -> calculations.py:apply_discount()

    错误原因：
    calculations.py:27 执行 amount * (1 - discount_rate)，
    但 discount_rate 为 None，导致 TypeError。
    """
    print("\n" + "=" * 60)
    print("Test 2: TypeError - None Discount Rate")
    print("=" * 60)

    user = User(id=2, username="testuser2", email="test2@example.com", balance=500.0)
    order_service = OrderService()

    # 创建订单，不使用折扣码
    items = [OrderItem(product_id=2, quantity=2, unit_price=29.99)]
    order = order_service.create_order(user, items, discount_code=None)

    try:
        # 处理订单 - 会触发 TypeError
        result = order_service.process_order(order, user)
        print(f"✅ Order processed: {result}")
    except TypeError as e:
        print(f"❌ TypeError occurred: {e}")
        print(f"   Error location: calculations.py:apply_discount()")
        print(f"   Root cause: discount_rate is None, cannot perform (1 - None)")


def test_successful_order():
    """测试成功的订单流程。"""
    print("\n" + "=" * 60)
    print("Test 3: Successful Order with Valid Discount")
    print("=" * 60)

    user = User(id=3, username="testuser3", email="test3@example.com", balance=2000.0)
    order_service = OrderService()

    # 创建订单，使用有效折扣码
    items = [OrderItem(product_id=1, quantity=1, unit_price=999.99)]
    order = order_service.create_order(user, items, discount_code="SAVE10")

    try:
        result = order_service.process_order(order, user)
        print(f"✅ Order processed successfully!")
        print(f"   Order ID: {result['order_id']}")
        print(f"   Total: ${result['total']:.2f}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("🛒 E-commerce System - Cross-file Bug Test Suite")
    print("=" * 60)

    # 运行测试
    test_keyerror_invalid_discount_code()
    test_typeerror_none_discount()
    test_successful_order()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("These cross-file bugs can be auto-fixed by log2pr.")
    print("=" * 60)
