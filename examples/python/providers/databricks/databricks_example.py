"""
Basic example of using Databricks with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Databricks
agent = Agent(
    instructions="You are a helpful assistant",
    llm="databricks/databricks-llama-3.1-8b-instruct",
)

# Example conversation
response = agent.start("Hello! Can you help me with a data analysis task?")

# Example with data analysis
analysis_task = """
Analyze the potential market opportunities for a new AI-powered 
productivity tool targeting remote workers. Include market size, 
competitive landscape, and go-to-market strategy recommendations.
"""

response = agent.start(analysis_task)

# Example with business intelligence
business_task = """
Provide insights on how AI can transform customer service operations
in the next 5 years, including specific use cases and implementation strategies.
"""

response = agent.start(business_task) 