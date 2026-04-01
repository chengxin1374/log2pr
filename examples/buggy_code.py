"""
故意写错的代码示例 - 用于测试 log2pr 自动修复功能
Buggy code example - For testing log2pr auto-fix functionality

这个文件包含几个常见的 Python 错误，用于测试 log2pr 的自动修复能力。
This file contains common Python bugs for testing log2pr's auto-fix capability.
"""


def get_user_name(user_dict: dict) -> str:
    """获取用户名称 - 故意制造的 KeyError。

    Args:
        user_dict: 用户信息字典。

    Returns:
        用户名称字符串。
    """
    # Bug: 直接访问可能不存在的 key，没有处理 KeyError
    return user_dict["name"]


def calculate_discount(price: float, discount_rate: float) -> float:
    """计算折扣价格 - 故意制造的 TypeError。

    Args:
        price: 原价。
        discount_rate: 折扣率 (0-1)。

    Returns:
        折扣后的价格。
    """
    # Bug: 没有检查 None 值，可能导致 TypeError
    discounted = price * discount_rate
    return discounted


def process_items(items: list) -> list:
    """处理列表项 - 故意制造的 IndexError。

    Args:
        items: 项目列表。

    Returns:
        处理后的列表。
    """
    result = []
    # Bug: 假设列表至少有 3 个元素，可能导致 IndexError
    result.append(items[0])
    result.append(items[1])
    result.append(items[2])
    return result


def divide_numbers(a: int, b: int) -> float:
    """除法运算 - 故意制造的 ZeroDivisionError。

    Args:
        a: 被除数。
        b: 除数。

    Returns:
        除法结果。
    """
    # Bug: 没有检查除数是否为 0
    return a / b


class UserService:
    """用户服务类 - 故意制造的 AttributeError。"""

    def __init__(self):
        """初始化服务。"""
        self.users = {}

    def get_user_email(self, user_id: int) -> str:
        """获取用户邮箱。

        Args:
            user_id: 用户 ID。

        Returns:
            用户邮箱字符串。
        """
        # Bug: 没有检查用户是否存在，可能导致 AttributeError
        user = self.users.get(user_id)
        return user.email  # type: ignore


# 测试代码 - 运行时会触发错误
if __name__ == "__main__":
    print("=" * 50)
    print("测试 log2pr 自动修复功能")
    print("=" * 50)

    # 测试 KeyError
    print("\n1. 测试 KeyError:")
    try:
        user = {"id": 1, "username": "test"}  # 注意: 没有 "name" key
        name = get_user_name(user)
        print(f"   用户名: {name}")
    except KeyError as e:
        print(f"   ❌ KeyError: {e}")

    # 测试 TypeError
    print("\n2. 测试 TypeError:")
    try:
        price = 100
        discount = None  # 故意传入 None
        result = calculate_discount(price, discount)  # type: ignore
        print(f"   折扣价: {result}")
    except TypeError as e:
        print(f"   ❌ TypeError: {e}")

    # 测试 IndexError
    print("\n3. 测试 IndexError:")
    try:
        items = ["item1"]  # 只有一个元素
        result = process_items(items)
        print(f"   处理结果: {result}")
    except IndexError as e:
        print(f"   ❌ IndexError: {e}")

    # 测试 ZeroDivisionError
    print("\n4. 测试 ZeroDivisionError:")
    try:
        result = divide_numbers(10, 0)
        print(f"   除法结果: {result}")
    except ZeroDivisionError as e:
        print(f"   ❌ ZeroDivisionError: {e}")

    print("\n" + "=" * 50)
    print("所有测试完成！这些错误可以被 log2pr 自动修复。")
    print("=" * 50)
