"""
TemplateConfig Example

Demonstrates using TemplateConfig for custom prompt templates.
"""
import os
from praisonaiagents import Agent, TemplateConfig

# Ensure API key is set from environment
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY must be set"

# Custom system template
agent = Agent(
    instructions="You are a helpful assistant.",
    templates=TemplateConfig(
        system="You are a professional technical writer. Always be concise and clear.",
        use_system_prompt=True,
    ),
)

# Custom prompt and response templates
agent_custom = Agent(
    instructions="You are a helpful assistant.",
    templates=TemplateConfig(
        system="You are an expert in Python programming.",
        prompt=None,  # Use default
        response=None,  # Use default
        use_system_prompt=True,
    ),
)

if __name__ == "__main__":
    print("Testing TemplateConfig...")
    
    result = agent.chat("Explain what an API is in one sentence.")
    print(f"Result: {result}")
    
    print("\nTemplateConfig tests passed!")
