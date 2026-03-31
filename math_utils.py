def calculate_ratio(total, count):
    """Calculate the ratio of total to count.
    
    Args:
        total: The numerator value
        count: The denominator value
    
    Returns:
        The ratio total/count, or 0.0 if count is zero to avoid division by zero.
    """
    if count == 0:
        return 0.0
    return total / count

if __name__ == "__main__":
    print(calculate_ratio(100, 0))
