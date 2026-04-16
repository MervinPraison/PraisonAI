"""
Langfuse Integration Example (Updated for TraceSinkProtocol)

This example shows how to use Langfuse for LLM observability with PraisonAI's native trace infrastructure.

Setup:
    pip install "praisonai[langfuse]"
    export LANGFUSE_PUBLIC_KEY=pk-lf-xxx
    export LANGFUSE_SECRET_KEY=sk-lf-xxx

Usage:
    python langfuse_example.py
"""
from praisonaiagents import Agent
from praisonai.observability import LangfuseSink
from praisonaiagents.trace.protocol import (
    TraceEmitter, set_default_emitter
)

# Initialize Langfuse observability
sink = LangfuseSink()
emitter = TraceEmitter(sink=sink, enabled=True)
set_default_emitter(emitter)

# Create and run agent — all traces automatically captured
agent = Agent(
    name="Coder",
    instructions="You are a helpful coding assistant.",
    llm="openai/gpt-4o-mini",
)

try:
    result = agent.start("Write a Python function to calculate fibonacci numbers")
    print(result)
finally:
    # Ensure traces are flushed and resources cleaned up
    sink.flush()
    sink.close()

print("\nCheck Langfuse dashboard for traces!")
