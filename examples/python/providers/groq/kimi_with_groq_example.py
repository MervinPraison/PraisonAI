"""
Basic example of using Kimi model with Groq provider in PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Kimi model using Groq provider
agent = Agent(
    instructions="You are a helpful assistant",
    llm="groq/kimi",
)

# Example conversation
response = agent.start("Hello! Can you help me with a coding task?")

# Example with more complex task
coding_task = """
Write a Python function that calculates the factorial of a number.
Include error handling and documentation.
"""

response = agent.start(coding_task) 