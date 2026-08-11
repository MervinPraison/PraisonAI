"""Calculator module with intentional bugs for testing."""


class Calculator:
    """A simple calculator class."""
    
    def add(self, a, b):
        """Add two numbers."""
        return a + b
    
    def subtract(self, a, b):
        """Subtract two numbers."""
        return a - b
    
    def multiply(self, a, b):
        """Multiply two numbers."""
        return a * b
        
    def divide(self, a, b):
        """Divide two numbers."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b