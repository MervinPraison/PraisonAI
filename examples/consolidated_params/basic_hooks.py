"""
Basic Hooks Example - Agent-Centric API

Demonstrates lifecycle hooks with consolidated params.
Valid keys: on_step, on_tool_call, middleware
"""

from praisonaiagents import Agent

# Define hook callbacks
def on_step_callback(step_info):
    print(f"Step: {step_info}")

def on_tool_call_callback(tool_info):
    print(f"Tool called: {tool_info}")

# Basic: Enable hooks with dict
agent = Agent(
    instructions="You are a helpful assistant.",
    hooks={
        "on_step": on_step_callback,
        "on_tool_call": on_tool_call_callback,
    },
)

if __name__ == "__main__":
    response = agent.start("What is 2 + 2?")
    print(response)
