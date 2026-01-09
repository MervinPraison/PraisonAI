"""Sample application."""

def greet(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"

def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

class Calculator:
    """Simple calculator."""
    
    def __init__(self):
        self.value = 0
    
    def add(self, x):
        self.value += x
        return self.value

if __name__ == "__main__":
    print(greet("World"))
