"""
Basic example of using Cohere with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with Cohere
agent = Agent(
    instructions="You are a helpful assistant",
    llm="cohere/command-r-plus",
)

# Example conversation
response = agent.start("Hello! Can you help me with a business analysis task?")

# Example with business analysis
business_task = """
Analyze the potential market opportunities for a new AI-powered 
productivity tool targeting remote workers. Include market size, 
competitive landscape, and go-to-market strategy recommendations.
"""

response = agent.start(business_task)

# Example with document summarization
summary_task = """
Summarize the key points from this business proposal:

Our company proposes to develop an AI-powered customer service chatbot
that can handle 80% of common customer inquiries automatically. The system
will integrate with existing CRM platforms and provide 24/7 support.
Expected ROI is 300% within the first year, with implementation taking
6 months and requiring a team of 5 developers.
"""

response = agent.start(summary_task) 