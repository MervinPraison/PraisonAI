"""
Basic example of using Grok model in PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Grok model
agent = Agent(
    instructions="You are a helpful assistant",
    llm="xai/grok-beta",
)

# Example conversation
response = agent.start("Hello! Can you explain quantum computing in simple terms?")

# Example with mathematical reasoning
math_task = """
Solve this problem step by step:
If a train travels at 60 mph for 2.5 hours, how far does it travel?
"""

response = agent.start(math_task)

# Example with creative writing
creative_task = """
Write a short story about a robot learning to paint.
Make it engaging and about 100 words.
"""

response = agent.start(creative_task) 