"""
Basic Middleware Example - PraisonAI Agents

Demonstrates before/after hooks and wrap decorators for model and tool calls.
"""

from praisonaiagents import Agent, tool
from praisonaiagents.hooks import (
    before_model, after_model, wrap_model_call,
    before_tool, after_tool, wrap_tool_call,
    InvocationContext, ModelRequest, ModelResponse
)

# Simple tool for demonstration
@tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Sunny, 22°C in {city}"

# Before model hook - adds context
@before_model
def add_context(request: ModelRequest) -> ModelRequest:
    print(f"[before_model] Adding context to request")
    return request

# After model hook - logs response
@after_model  
def log_response(response: ModelResponse) -> ModelResponse:
    print(f"[after_model] Response received")
    return response

# Wrap tool call - retry on error
@wrap_tool_call
def retry_on_error(tool_call, call_next):
    print(f"[wrap_tool_call] Executing tool")
    try:
        return call_next(tool_call)
    except Exception as e:
        print(f"[wrap_tool_call] Retrying after error: {e}")
        return call_next(tool_call)

# Create agent with hooks
agent = Agent(
    name="WeatherBot",
    instructions="You help with weather queries.",
    tools=[get_weather],
    hooks=[add_context, log_response, retry_on_error]
)

if __name__ == "__main__":
    # Test the tool directly
    result = get_weather("London")
    print(f"Weather: {result}")
    
    print("\n✓ Middleware example complete")
