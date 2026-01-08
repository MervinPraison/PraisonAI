"""
Basic Guardrails Configuration Example

Demonstrates using guardrails for output validation.
"""
import os
from praisonaiagents import Agent

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

def validate_length(output):
    """Validate that output is not too short."""
    if len(str(output.raw)) < 10:
        return False, "Response too short"
    return True, output

# Enable guardrails with a validator function
agent = Agent(
    instructions="You are a helpful assistant.",
    guardrails=validate_length,
)

if __name__ == "__main__":
    print("Testing guardrails...")
    
    result = agent.chat("Explain what Python is.")
    print(f"Result: {result}")
    
    print("\nGuardrails tests passed!")
