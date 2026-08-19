"""Statistics module with bugs and missing implementations."""
import statistics


def mean(numbers):
    """Calculate mean. INTENTIONAL BUG: No empty list check."""
    return sum(numbers) / len(numbers)  # This should handle empty lists


def median(numbers):
    """Calculate median. INTENTIONAL BUG: No empty list check."""
    return statistics.median(numbers)  # This should handle empty lists


def mode(numbers):
    """Calculate mode. NEEDS IMPLEMENTATION."""
    # TODO: Implement this function
    # Should return the most frequent value
    raise NotImplementedError("mode not implemented")