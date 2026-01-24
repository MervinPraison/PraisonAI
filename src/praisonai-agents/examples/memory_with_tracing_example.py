"""
Example: Memory with Tracing

This example demonstrates how to use memory with context tracing enabled.
When tracing is enabled, memory operations (store/search) emit trace events
that can be used for debugging and analysis with the LLM Judge.

Usage:
    python memory_with_tracing_example.py

To judge the trace:
    praisonai recipe judge <trace_id> --memory
"""

from praisonaiagents.memory import Memory
from praisonaiagents.trace.context_events import (
    ContextTraceEmitter, 
    ContextListSink,
    set_context_emitter,
    reset_context_emitter,
)


def main():
    # Set up trace emitter to capture events
    sink = ContextListSink()
    emitter = ContextTraceEmitter(sink=sink, session_id="memory-demo", enabled=True)
    token = set_context_emitter(emitter)
    
    try:
        # Create memory instance
        memory = Memory(config={
            "provider": "rag",
            "use_embedding": False,
            "agent_name": "demo_agent",  # Used in trace events
        })
        
        # Store some memories
        print("Storing memories...")
        memory.store_short_term("The user's name is Alice")
        memory.store_short_term("Alice likes Python programming")
        memory.store_long_term("Important: Alice prefers dark mode in all applications")
        
        # Search memories
        print("\nSearching memories...")
        results = memory.search_short_term("Alice", limit=5)
        print(f"Found {len(results)} short-term memories")
        
        results = memory.search_long_term("preferences", limit=5)
        print(f"Found {len(results)} long-term memories")
        
        # Print captured trace events
        events = sink.get_events()
        print(f"\n--- Captured {len(events)} trace events ---")
        for event in events:
            print(f"  {event.event_type.value}: {event.data}")
        
        # Filter memory-specific events
        memory_events = [e for e in events if 'memory' in e.event_type.value]
        print(f"\n--- Memory-specific events: {len(memory_events)} ---")
        for event in memory_events:
            print(f"  {event.event_type.value}:")
            print(f"    agent: {event.agent_name}")
            print(f"    data: {event.data}")
        
    finally:
        reset_context_emitter(token)
        print("\nTrace emitter reset.")


if __name__ == "__main__":
    main()
