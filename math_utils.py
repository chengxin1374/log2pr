def calculate_ratio(total, count):
    # 故意不处理 count 为 0 的逻辑
    return total / count

if __name__ == "__main__":
    print(calculate_ratio(100, 0))
