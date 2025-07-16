"""
Basic example of using Google Gemini with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Google Gemini
agent = Agent(
    instructions="You are a helpful assistant",
    llm="google/gemini-1.5-pro",
)

# Example conversation
response = agent.start("Hello! Can you help me with a research task?")

# Example with research and analysis
research_task = """
Research and provide insights on the latest developments in 
renewable energy technology, focusing on solar and wind power innovations.
"""

response = agent.start(research_task)

# Example with multimodal capabilities (text-based for now)
multimodal_task = """
Describe how you would analyze an image of a city skyline 
and provide insights about urban development patterns.
"""

response = agent.start(multimodal_task) 