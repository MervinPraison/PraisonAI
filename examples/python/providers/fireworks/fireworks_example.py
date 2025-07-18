"""
Basic example of using Fireworks AI with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Fireworks AI
agent = Agent(
    instructions="You are a helpful assistant",
    llm="fireworks/accounts/fireworks/models/llama-v3-8b-instruct",
)

# Example conversation
response = agent.start("Hello! Can you help me with a coding task?")

# Example with code generation
coding_task = """
Write a Python function that implements a binary search algorithm.
Include proper documentation and error handling.
"""

response = agent.start(coding_task)

# Example with creative writing
creative_task = """
Write a short story about a time traveler who discovers 
they can only travel to moments of great historical significance.
"""

response = agent.start(creative_task) 