"""
Basic Guardrails Example - Agent-Centric API

Demonstrates guardrails with callable validator.
"""

from praisonaiagents import Agent

# Define a simple guardrail validator
def validate_response(output):
    """Validate that response doesn't contain forbidden words."""
    forbidden = ["error", "fail", "cannot"]
    text = str(output).lower()
    for word in forbidden:
        if word in text:
            return (False, f"Response contains forbidden word: {word}")
    return (True, output)

# Basic: Use callable guardrail
agent = Agent(
    instructions="You are a helpful assistant.",
    guardrails=validate_response,
)

response = agent.start("What is 2 + 2?")
print(response)
