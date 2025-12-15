"""Example plugin tools demonstrating the BaseTool and @tool patterns.

This module shows how to create tools using the new plugin system.
External developers can use these patterns to create pip-installable plugins.

Usage:
    from praisonaiagents import BaseTool, tool, Agent

    # Method 1: Class-based tool
    class MyTool(BaseTool):
        name = "my_tool"
        description = "Does something useful"
        
        def run(self, param: str) -> str:
            return f"Result: {param}"

    # Method 2: Decorator-based tool
    @tool
    def my_function(param: str) -> str:
        '''Does something useful.'''
        return f"Result: {param}"

    # Use with Agent
    agent = Agent(tools=[MyTool(), my_function])
"""

from typing import Dict, Any, List
from .base import BaseTool
from .decorator import tool


# =============================================================================
# Example 1: Simple Class-Based Tool
# =============================================================================

class EchoTool(BaseTool):
    """A simple tool that echoes input back.
    
    This demonstrates the minimal BaseTool implementation.
    """
    name = "echo"
    description = "Echo the input message back"
    
    def run(self, message: str) -> str:
        """Echo the message.
        
        Args:
            message: The message to echo
            
        Returns:
            The same message
        """
        return message


# =============================================================================
# Example 2: Tool with Multiple Parameters
# =============================================================================

class MathTool(BaseTool):
    """A tool for basic math operations.
    
    Demonstrates:
    - Multiple parameters with types
    - Default parameter values
    - Returning structured data
    """
    name = "basic_math"
    description = "Perform basic math operations (add, subtract, multiply, divide)"
    
    def run(
        self,
        a: float,
        b: float,
        operation: str = "add"
    ) -> Dict[str, Any]:
        """Perform a math operation.
        
        Args:
            a: First number
            b: Second number
            operation: One of 'add', 'subtract', 'multiply', 'divide'
            
        Returns:
            Dict with result and operation details
        """
        operations = {
            "add": lambda x, y: x + y,
            "subtract": lambda x, y: x - y,
            "multiply": lambda x, y: x * y,
            "divide": lambda x, y: x / y if y != 0 else float('inf')
        }
        
        if operation not in operations:
            return {"error": f"Unknown operation: {operation}"}
        
        result = operations[operation](a, b)
        return {
            "result": result,
            "operation": operation,
            "expression": f"{a} {operation} {b} = {result}"
        }


# =============================================================================
# Example 3: Tool with State (Instance Variables)
# =============================================================================

class CounterTool(BaseTool):
    """A tool that maintains state between calls.
    
    Demonstrates:
    - Instance variables for state
    - Custom __init__ with super() call
    """
    name = "counter"
    description = "A counter that increments each time it's called"
    
    def __init__(self, start: int = 0):
        self._count = start
        super().__init__()  # Important: call parent init
    
    def run(self, increment: int = 1) -> Dict[str, int]:
        """Increment the counter.
        
        Args:
            increment: Amount to increment by (default: 1)
            
        Returns:
            Dict with previous and current count
        """
        previous = self._count
        self._count += increment
        return {
            "previous": previous,
            "current": self._count,
            "increment": increment
        }


# =============================================================================
# Example 4: Decorator-Based Tools
# =============================================================================

@tool
def greet(name: str, greeting: str = "Hello") -> str:
    """Generate a greeting message.
    
    Args:
        name: Name of the person to greet
        greeting: The greeting word (default: "Hello")
        
    Returns:
        A greeting string
    """
    return f"{greeting}, {name}!"


@tool(name="reverse_text", description="Reverse a string of text")
def reverse_string(text: str) -> str:
    """Reverse the input text."""
    return text[::-1]


@tool
def list_numbers(start: int, end: int, step: int = 1) -> List[int]:
    """Generate a list of numbers.
    
    Args:
        start: Starting number (inclusive)
        end: Ending number (exclusive)
        step: Step between numbers (default: 1)
        
    Returns:
        List of integers
    """
    return list(range(start, end, step))


# =============================================================================
# Example 5: Tool with Error Handling
# =============================================================================

class SafeDivideTool(BaseTool):
    """A division tool with proper error handling.
    
    Demonstrates:
    - Error handling in run()
    - Returning error information
    """
    name = "safe_divide"
    description = "Safely divide two numbers with error handling"
    
    def run(self, numerator: float, denominator: float) -> Dict[str, Any]:
        """Divide numerator by denominator.
        
        Args:
            numerator: The number to divide
            denominator: The number to divide by
            
        Returns:
            Dict with result or error message
        """
        if denominator == 0:
            return {
                "success": False,
                "error": "Division by zero is not allowed"
            }
        
        result = numerator / denominator
        return {
            "success": True,
            "result": result
        }


# =============================================================================
# Convenience exports
# =============================================================================

# These can be imported directly:
# from praisonaiagents.tools.example_plugin import echo_tool, math_tool, greet

echo_tool = EchoTool()
math_tool = MathTool()
counter_tool = CounterTool()
safe_divide_tool = SafeDivideTool()

__all__ = [
    # Classes
    'EchoTool',
    'MathTool',
    'CounterTool',
    'SafeDivideTool',
    # Instances
    'echo_tool',
    'math_tool',
    'counter_tool',
    'safe_divide_tool',
    # Decorated functions
    'greet',
    'reverse_string',
    'list_numbers',
]
