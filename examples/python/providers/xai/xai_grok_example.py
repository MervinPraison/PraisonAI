"""
Basic example of using xAI Grok with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with xAI Grok
agent = Agent(
    instructions="You are a helpful assistant",
    llm="xai/grok-beta",
)

# Example conversation
response = agent.start("Hello! Can you help me with a complex reasoning task?")

# Example with complex reasoning
reasoning_task = """
Analyze this scenario step by step:
A company has 100 employees, 60% work remotely, 30% work hybrid, and 10% work in-office.
They want to implement a new AI tool that requires high-speed internet.
What are the challenges and solutions for this implementation?
"""

response = agent.start(reasoning_task)

# Example with creative problem solving
creative_task = """
Design a solution for reducing food waste in urban areas using AI technology.
Consider economic, environmental, and social factors.
Provide a step-by-step implementation plan.
"""

response = agent.start(creative_task)

# Example with humor and personality (Grok's specialty)
humor_task = """
Explain quantum physics using analogies that would make a 10-year-old laugh,
while still being scientifically accurate.
"""

response = agent.start(humor_task) 