"""PraisonAI Example Plugin - Demonstrates how to create tool plugins.

This package shows how external developers can create pip-installable
tool plugins for PraisonAI Agents.

Usage after installation:
    from praisonaiagents import Agent
    
    # Tools are auto-discovered via entry_points!
    agent = Agent(tools=["example_greet", "example_math"])
    
    # Or import directly
    from praisonai_example_plugin import GreetTool, MathTool
    agent = Agent(tools=[GreetTool(), MathTool()])
"""

from typing import Dict, Any
from praisonaiagents import BaseTool, tool


# =============================================================================
# Class-Based Tools
# =============================================================================

class GreetTool(BaseTool):
    """A tool that generates personalized greetings.
    
    This demonstrates a simple class-based tool with multiple parameters.
    """
    name = "example_greet"
    description = "Generate a personalized greeting message"
    version = "1.0.0"
    
    def run(self, name: str, greeting: str = "Hello", punctuation: str = "!") -> str:
        """Generate a greeting.
        
        Args:
            name: The name of the person to greet
            greeting: The greeting word (default: "Hello")
            punctuation: End punctuation (default: "!")
            
        Returns:
            A formatted greeting string
        """
        return f"{greeting}, {name}{punctuation}"


class MathTool(BaseTool):
    """A tool for basic mathematical operations.
    
    Demonstrates returning structured data from a tool.
    """
    name = "example_math"
    description = "Perform basic math operations: add, subtract, multiply, divide"
    version = "1.0.0"
    
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
            Dict containing result and operation details
        """
        ops = {
            "add": ("+", lambda x, y: x + y),
            "subtract": ("-", lambda x, y: x - y),
            "multiply": ("*", lambda x, y: x * y),
            "divide": ("/", lambda x, y: x / y if y != 0 else float('inf')),
        }
        
        if operation not in ops:
            return {"error": f"Unknown operation: {operation}. Use: {list(ops.keys())}"}
        
        symbol, func = ops[operation]
        result = func(a, b)
        
        return {
            "result": result,
            "expression": f"{a} {symbol} {b} = {result}",
            "operation": operation
        }


# =============================================================================
# Decorator-Based Tools
# =============================================================================

@tool(name="example_reverse", description="Reverse a string of text")
def reverse_text(text: str) -> str:
    """Reverse the input text.
    
    Args:
        text: The text to reverse
        
    Returns:
        The reversed text
    """
    return text[::-1]


# =============================================================================
# Package Exports
# =============================================================================

__version__ = "1.0.0"
__all__ = [
    "GreetTool",
    "MathTool", 
    "reverse_text",
]
