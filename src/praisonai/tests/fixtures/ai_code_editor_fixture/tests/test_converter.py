"""Tests for temperature converter module."""
import pytest
from mathlib.converter import celsius_to_fahrenheit, fahrenheit_to_celsius


def test_celsius_to_fahrenheit():
    """Test Celsius to Fahrenheit conversion."""
    assert celsius_to_fahrenheit(0) == 32
    assert celsius_to_fahrenheit(100) == 212
    assert celsius_to_fahrenheit(-40) == -40


def test_fahrenheit_to_celsius():
    """Test Fahrenheit to Celsius conversion.""" 
    assert fahrenheit_to_celsius(32) == 0
    assert fahrenheit_to_celsius(212) == 100
    assert fahrenheit_to_celsius(-40) == -40