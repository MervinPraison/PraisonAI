"""Tests for statistics module."""
import pytest
from mathlib.stats import mean, median, mode


def test_mean():
    """Test mean calculation."""
    assert mean([1, 2, 3]) == 2
    assert mean([1, 1, 1]) == 1
    assert mean([2, 4]) == 3


def test_mean_empty_list():
    """Test mean with empty list raises error."""
    with pytest.raises(ValueError, match="Cannot calculate mean of empty list"):
        mean([])


def test_median():
    """Test median calculation."""
    assert median([1, 2, 3]) == 2
    assert median([1, 2, 3, 4]) == 2.5
    assert median([5]) == 5


def test_median_empty_list():
    """Test median with empty list raises error."""
    with pytest.raises(ValueError, match="Cannot calculate median of empty list"):
        median([])


def test_mode():
    """Test mode calculation."""
    assert mode([1, 1, 2, 3]) == 1
    assert mode([1, 2, 2, 3]) == 2
    assert mode([1]) == 1