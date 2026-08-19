"""Temperature conversion utilities."""

def celsius_to_fahrenheit(celsius):
    """Convert Celsius to Fahrenheit.
    
    Formula: F = C * 9/5 + 32
    
    Args:
        celsius: Temperature in Celsius
        
    Returns:
        Temperature in Fahrenheit
    """
    return celsius * 9/5 + 32


def fahrenheit_to_celsius(fahrenheit):
    """Convert Fahrenheit to Celsius.
    
    Formula: C = (F - 32) * 5/9
    
    Args:
        fahrenheit: Temperature in Fahrenheit
        
    Returns:
        Temperature in Celsius
    """
    return (fahrenheit - 32) * 5/9