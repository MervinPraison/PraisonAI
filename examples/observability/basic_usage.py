"""
Basic Observability Usage Example

This example demonstrates how to use the observability module
with PraisonAI agents.

Usage:
    # Set your provider's API key first
    export LANGFUSE_PUBLIC_KEY=pk-lf-xxx
    export LANGFUSE_SECRET_KEY=sk-lf-xxx
    
    python basic_usage.py
"""

from praisonai_tools.observability import obs
from praisonaiagents import Agent

# Initialize observability (auto-detects provider from env vars)
obs.init()

# Or specify a provider explicitly
# obs.init(provider="langfuse", project_name="my-project")

# Create an agent
agent = Agent(
    instructions="You are a helpful assistant.",
    model="gpt-4o-mini",
)

# Use trace context manager for complete workflow tracing
with obs.trace("chat-session", session_id="user-123"):
    # Use span context manager for individual operations
    with obs.span("user-query", kind=obs.SpanKind.AGENT):
        response = agent.chat("What is the capital of France?")
        print(response)

# Log LLM calls manually if needed
obs.log_llm_call(
    model="gpt-4o-mini",
    input_messages="What is 2+2?",
    output="4",
    input_tokens=10,
    output_tokens=1,
)

# Check diagnostics
print("\nDiagnostics:")
print(obs.doctor())
