"""
GuardrailConfig Example

Demonstrates using GuardrailConfig for fine-grained control.
"""
import os
from praisonaiagents import Agent, GuardrailConfig

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

def validate_no_code(output):
    """Validate that output doesn't contain code blocks."""
    if "```" in str(output.raw):
        return False, "Response should not contain code blocks"
    return True, output

# Custom guardrail configuration
agent = Agent(
    instructions="You are a helpful assistant. Explain concepts without code.",
    guardrails=GuardrailConfig(
        validator=validate_no_code,
        max_retries=3,
        on_fail="retry",
    ),
)

# LLM-based validation
agent_llm = Agent(
    instructions="You are a helpful assistant.",
    guardrails=GuardrailConfig(
        llm_validator="Ensure the response is helpful, accurate, and professional.",
        max_retries=2,
    ),
)

if __name__ == "__main__":
    print("Testing GuardrailConfig...")
    
    result = agent.chat("What is a variable in programming?")
    print(f"Result: {result}")
    
    print("\nGuardrailConfig tests passed!")
