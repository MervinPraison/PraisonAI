"""
Multi-Agent Tracing Example

This example shows how to trace multi-agent workflows with
parent/child span relationships.

Usage:
    # Set your provider's API key
    export LANGFUSE_PUBLIC_KEY=pk-lf-xxx
    export LANGFUSE_SECRET_KEY=sk-lf-xxx
    
    python multi_agent_tracing.py
"""

from praisonai_tools.observability import obs
from praisonai_tools.observability.base import SpanKind
from praisonaiagents import Agent, AgentTeam

# Initialize observability
obs.init()


def set_span_attr(span, key, value):
    """Set span attribute safely across observability implementations."""
    if hasattr(span, "set_attribute"):
        span.set_attribute(key, value)
        return
    attrs = getattr(span, "attributes", None)
    if attrs is not None:
        attrs[key] = value

# Create agents
researcher = Agent(
    name="Researcher",
    instructions="You research topics and provide detailed information.",
    model="gpt-4o-mini",
)

writer = Agent(
    name="Writer", 
    instructions="You write clear, engaging content based on research.",
    model="gpt-4o-mini",
)

# Trace the multi-agent workflow
with obs.trace("content-creation", metadata={"workflow": "research-write"}):
    
    # Research phase
    with obs.span("research-phase", kind=SpanKind.AGENT) as research_span:
        set_span_attr(research_span, "agent", "Researcher")
        research_result = researcher.chat("Research the benefits of AI in healthcare")
    
    # Writing phase  
    with obs.span("writing-phase", kind=SpanKind.AGENT) as write_span:
        set_span_attr(write_span, "agent", "Writer")
        set_span_attr(write_span, "input_length", len(str(research_result)))
        final_content = writer.chat(f"Write a blog post based on: {research_result}")

print("Final Content:")
print(final_content)

# Check trace info
print("\nDiagnostics:", obs.doctor())
