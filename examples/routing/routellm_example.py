"""
RouteLLM Integration Example

Route requests between strong and weak models to optimize cost.

Prerequisites:
1. pip install routellm
2. export OPENAI_API_KEY=your-api-key
3. Start RouteLLM server:
   python -m routellm.openai_server \
     --routers mf \
     --strong-model gpt-4o \
     --weak-model gpt-4o-mini \
     --port 6060
"""

from praisonaiagents import Agent

# Basic usage with RouteLLM routing
agent = Agent(
    instructions="You are a helpful assistant.",
    llm="router-mf-0.5",
    base_url="http://localhost:6060/v1"
)

response = agent.chat("What is 2+2?")
print(response)
