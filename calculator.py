
import statistics

def calculate_stats(numbers):
    """
    Calculates the sum, mean, and median of a list of numbers.
    """
    if not numbers:
        return {"sum": 0, "mean": 0, "median": 0}

    # Calculate sum
    total = sum(numbers)

    # Calculate mean
    mean = statistics.mean(numbers)

    # Calculate median
    median = statistics.median(numbers)

    return {"sum": total, "mean": mean, "median": median}

if __name__ == '__main__':
    # Example usage
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    result = calculate_stats(data)
    print(f"Statistics for {data}:")
    print(result)

    data2 = [10, 20, 30]
    result2 = calculate_stats(data2)
    print(f"Statistics for {data2}:")
    print(result2)
