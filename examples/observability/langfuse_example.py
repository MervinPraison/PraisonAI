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
from praisonaiagents.trace.context_events import (
    ContextTraceEmitter, set_context_emitter
)

# Initialize Langfuse observability
sink = LangfuseSink()
emitter = ContextTraceEmitter(sink=sink, enabled=True)
set_context_emitter(emitter)

# Create and run agent — all traces automatically captured
agent = Agent(
    name="Coder",
    instructions="You are a helpful coding assistant.",
    llm="openai/gpt-4o-mini",
)

result = agent.start("Write a Python function to calculate fibonacci numbers")
print(result)

# Flush traces
sink.flush()
sink.close()

print("\nCheck Langfuse dashboard for traces!")
