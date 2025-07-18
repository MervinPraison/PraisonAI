"""
Basic example of using AWS SageMaker with PraisonAI
"""

from praisonaiagents import Agent

# Initialize Agent with AWS SageMaker
agent = Agent(
    instructions="You are a helpful assistant",
    llm="sagemaker/meta-llama/Llama-3.1-8B-Instruct",
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
that can handle 80% of common customer inquiries automatically.
"""

response = agent.start(summary_task) 