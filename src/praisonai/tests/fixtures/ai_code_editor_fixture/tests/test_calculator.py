"""Tests for calculator module."""
import pytest
from mathlib.calculator import Calculator


def test_add():
    """Test addition."""
    calc = Calculator()
    assert calc.add(2, 3) == 5
    assert calc.add(-1, 1) == 0


def test_subtract():
    """Test subtraction."""
    calc = Calculator()
    assert calc.subtract(5, 3) == 2
    assert calc.subtract(1, 1) == 0


def test_multiply():
    """Test multiplication."""
    calc = Calculator()
    assert calc.multiply(4, 3) == 12
    assert calc.multiply(-2, 3) == -6


def test_divide():
    """Test division."""
    calc = Calculator()
    assert calc.divide(6, 2) == 3
    assert calc.divide(7, 2) == 3.5


def test_divide_by_zero():
    """Test division by zero raises error."""
    calc = Calculator()
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        calc.divide(5, 0)