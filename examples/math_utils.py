"""
简单数学工具 - 故意制造 ZeroDivisionError。

Simple math utilities - Intentional ZeroDivisionError bug.
"""


def calculate_ratio(total: float, count: int) -> float:
    """计算比率 - 故意不处理 count 为 0 的情况。

    Args:
        total: 总数。
        count: 计数。

    Returns:
        比率值。
    """
    # Bug: 没有检查 count 是否为 0
    return total / count


if __name__ == "__main__":
    print(calculate_ratio(100, 0))
