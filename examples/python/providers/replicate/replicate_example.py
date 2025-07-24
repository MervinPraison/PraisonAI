"""
Basic example of using Replicate with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Replicate
agent = Agent(
    instructions="You are a helpful assistant",
    llm="replicate/meta/llama-3.1-8b-instruct",
)

# Example conversation
response = agent.start("Hello! Can you help me with a creative task?")

# Example with creative writing
creative_task = """
Write a short story about a robot learning to paint.
Make it engaging and about 100 words.
"""

response = agent.start(creative_task)

# Example with problem solving
problem_task = """
Solve this problem step by step:
If a train travels at 60 mph for 2.5 hours, how far does it travel?
"""

response = agent.start(problem_task) 