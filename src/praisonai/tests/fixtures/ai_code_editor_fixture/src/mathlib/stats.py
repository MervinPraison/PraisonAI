"""Statistical utilities."""
import statistics
from collections import Counter


def mean(numbers):
    """Calculate mean of a list of numbers.
    
    Args:
        numbers: List of numbers
        
    Returns:
        Arithmetic mean
        
    Raises:
        ValueError: If the list is empty
    """
    if not numbers:
        raise ValueError("Cannot calculate mean of empty list")
    return sum(numbers) / len(numbers)


def median(numbers):
    """Calculate median of a list of numbers.
    
    Args:
        numbers: List of numbers
        
    Returns:
        Median value
        
    Raises:
        ValueError: If the list is empty
    """
    if not numbers:
        raise ValueError("Cannot calculate median of empty list")
    return statistics.median(numbers)


def mode(numbers):
    """Calculate mode (most frequent value) of a list.
    
    Args:
        numbers: List of numbers
        
    Returns:
        Most frequent value
        
    Raises:
        ValueError: If the list is empty
    """
    if not numbers:
        raise ValueError("Cannot calculate mode of empty list")
    
    # Count frequencies
    counter = Counter(numbers)
    
    # Find the most common value
    most_common = counter.most_common(1)
    return most_common[0][0]