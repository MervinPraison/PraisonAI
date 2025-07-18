"""
Basic example of using AI21 with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with AI21
agent = Agent(
    instructions="You are a helpful assistant",
    llm="ai21/j2-ultra",
)

# Example conversation
response = agent.start("Hello! Can you help me with a writing task?")

# Example with creative writing
writing_task = """
Write a short story about a time traveler who discovers 
they can only travel to moments of great historical significance.
Make it engaging and about 200 words.
"""

response = agent.start(writing_task)

# Example with reasoning
reasoning_task = """
Explain the concept of quantum entanglement in simple terms,
and then discuss its potential applications in quantum computing.
"""

response = agent.start(reasoning_task) 