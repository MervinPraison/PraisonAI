"""
Streaming Example with TTFT Metrics

This example demonstrates true pass-through streaming with timing metrics.
When verbose output is enabled, tokens are displayed as they arrive from the provider.

Key timing metrics:
- TTFT (Time To First Token): Time from request to first token received
- Stream Duration: Time from first to last token
- Total Time: End-to-end request time
"""
from praisonaiagents import Agent
from praisonaiagents.config import OutputConfig

# Create agent with verbose output (shows streaming progress)
agent = Agent(
    instructions="You are a helpful assistant",
    llm="gpt-4o-mini",
    output=OutputConfig(output="verbose")  # Show generation progress
)

# Run the agent - verbose mode shows streaming progress via Rich Live display
result = agent.start("Write a short paragraph about the history of computing")
print(f"\n--- Response ---\n{result}")