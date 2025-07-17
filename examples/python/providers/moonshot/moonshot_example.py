"""
Basic example of using Moonshot AI with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Moonshot AI
agent = Agent(
    instructions="You are a helpful assistant",
    llm="moonshot/moonshot-v1-8k",
)

# Example conversation
response = agent.start("Hello! Can you help me with a research task?")

# Example with research and analysis
research_task = """
Research and provide insights on the latest developments in 
artificial intelligence, focusing on recent breakthroughs and trends.
"""

response = agent.start(research_task)

# Example with creative content
creative_task = """
Write a haiku about artificial intelligence and its impact on society.
Then explain the symbolism in your haiku.
"""

response = agent.start(creative_task) 