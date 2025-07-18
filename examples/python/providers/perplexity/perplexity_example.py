"""
Basic example of using Perplexity with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Perplexity
agent = Agent(
    instructions="You are a helpful assistant",
    llm="perplexity/llama-3.1-8b-instruct",
)

# Example conversation
response = agent.start("Hello! Can you help me with a research task?")

# Example with research and analysis
research_task = """
Research and provide insights on the latest developments in 
artificial intelligence, focusing on recent breakthroughs and trends.
"""

response = agent.start(research_task)

# Example with document analysis
analysis_task = """
Analyze the potential market opportunities for a new AI-powered 
productivity tool targeting remote workers.
"""

response = agent.start(analysis_task) 