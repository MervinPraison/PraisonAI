"""
Langfuse Integration Example

This example shows how to use Langfuse for LLM observability.

Setup:
    1. Sign up at https://langfuse.com/
    2. Get your API keys from the project settings
    3. Set environment variables:
       export LANGFUSE_PUBLIC_KEY=pk-lf-xxx
       export LANGFUSE_SECRET_KEY=sk-lf-xxx
    4. Install dependencies:
       pip install opentelemetry-sdk opentelemetry-exporter-otlp

Usage:
    python langfuse_example.py
"""

import os
from praisonai_tools.observability import obs
from praisonaiagents import Agent

# Initialize Langfuse
success = obs.init(
    provider="langfuse",
    project_name="praisonai-demo",
)

if not success:
    print("Failed to initialize Langfuse. Check your API keys.")
    print("Required: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY")
    exit(1)

print("Langfuse initialized successfully!")
print(f"View traces at: https://cloud.langfuse.com/")

# Create agent
agent = Agent(
    instructions="You are a helpful coding assistant.",
    model="gpt-4o-mini",
)

# Run with tracing
with obs.trace("coding-session", user_id="developer-1"):
    response = agent.chat("Write a Python function to calculate fibonacci numbers")
    print(response)

print("\nCheck Langfuse dashboard for traces!")
