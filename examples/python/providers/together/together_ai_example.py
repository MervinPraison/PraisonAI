"""
Basic example of using Together AI with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Together AI
agent = Agent(
    instructions="You are a helpful assistant",
    llm="together_ai/meta-llama/Llama-3.1-8B-Instruct",
)

# Example conversation
response = agent.start("Hello! Can you help me with a research task?")

# Example with research and analysis
research_task = """
Research and provide insights on the latest developments in 
renewable energy technology, focusing on solar and wind power innovations.
"""

response = agent.start(research_task)

# Example with creative content
creative_task = """
Write a haiku about artificial intelligence and its impact on society.
Then explain the symbolism in your haiku.
"""

response = agent.start(creative_task) 