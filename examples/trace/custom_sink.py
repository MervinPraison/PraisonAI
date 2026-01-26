"""
Custom Trace Sink Example

Demonstrates how to create custom trace sinks for PraisonAI agents.
The trace system uses a protocol-driven design - implement 3 methods
and your sink works with any agent.

Protocol: ContextTraceSinkProtocol (AGENTS.md naming: XProtocol for interfaces)
- emit(event) - Receive a trace event
- flush() - Flush any buffered events  
- close() - Release resources

Examples:
1. HTTP Sink - Send events to a remote server
2. SQLite Sink - Store events in a database
3. Console Sink - Pretty-print events to terminal
"""

from praisonaiagents import (
    Agent,
    ContextTraceEmitter,
    ContextTraceSinkProtocol,  # Protocol for type hints (optional)
    trace_context,
)


# =============================================================================
# Example 1: HTTP Sink - Send events to a remote server
# =============================================================================

class HTTPSink:
    """Send trace events to a remote HTTP endpoint."""
    
    def __init__(self, url: str, batch_size: int = 10):
        self.url = url
        self.batch_size = batch_size
        self.buffer = []
    
    def emit(self, event):
        """Buffer events and send in batches."""
        self.buffer.append(event.to_dict())
        if len(self.buffer) >= self.batch_size:
            self.flush()
    
    def flush(self):
        """Send buffered events to server."""
        if self.buffer:
            # In production, use: requests.post(self.url, json=self.buffer)
            print(f"[HTTP] Would send {len(self.buffer)} events to {self.url}")
            self.buffer.clear()
    
    def close(self):
        """Flush remaining events."""
        self.flush()


# =============================================================================
# Example 2: SQLite Sink - Store events in a database
# =============================================================================

class SQLiteSink:
    """Store trace events in SQLite database."""
    
    def __init__(self, db_path: str = "traces.db"):
        import sqlite3
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                session_id TEXT,
                event_type TEXT,
                agent_name TEXT,
                timestamp REAL,
                data TEXT
            )
        """)
        self.conn.commit()
    
    def emit(self, event):
        """Insert event into database."""
        import json
        self.conn.execute(
            "INSERT INTO events (session_id, event_type, agent_name, timestamp, data) VALUES (?, ?, ?, ?, ?)",
            (event.session_id, event.event_type.value, event.agent_name, event.timestamp, json.dumps(event.data))
        )
    
    def flush(self):
        """Commit pending transactions."""
        self.conn.commit()
    
    def close(self):
        """Commit and close connection."""
        self.flush()
        self.conn.close()


# =============================================================================
# Example 3: Console Sink - Pretty-print events
# =============================================================================

class ConsoleSink:
    """Print trace events to console with colors."""
    
    COLORS = {
        "session_start": "\033[92m",  # Green
        "session_end": "\033[92m",
        "agent_start": "\033[94m",    # Blue
        "agent_end": "\033[94m",
        "tool_call_start": "\033[93m", # Yellow
        "tool_call_end": "\033[93m",
        "llm_request": "\033[95m",    # Magenta
        "llm_response": "\033[95m",
    }
    RESET = "\033[0m"
    
    def emit(self, event):
        """Print event with color coding."""
        color = self.COLORS.get(event.event_type.value, "")
        print(f"{color}[{event.event_type.value}]{self.RESET} {event.agent_name or 'session'}")
    
    def flush(self):
        pass
    
    def close(self):
        pass


# =============================================================================
# Usage Examples
# =============================================================================

def example_http_sink():
    """Example: Send events to HTTP endpoint."""
    print("\n=== HTTP Sink Example ===")
    
    sink = HTTPSink(url="https://my-telemetry.example.com/events")
    emitter = ContextTraceEmitter(sink=sink, session_id="http-demo", enabled=True)
    
    with trace_context(emitter):
        # Events automatically go to HTTPSink
        emitter.session_start({"demo": True})
        emitter.agent_start("demo_agent", {"role": "demo"})
        emitter.agent_end("demo_agent")
        emitter.session_end()
    
    print("HTTP sink example complete")


def example_console_sink():
    """Example: Pretty-print events to console."""
    print("\n=== Console Sink Example ===")
    
    sink = ConsoleSink()
    emitter = ContextTraceEmitter(sink=sink, session_id="console-demo", enabled=True)
    
    with trace_context(emitter):
        emitter.session_start({})
        emitter.agent_start("researcher", {"role": "Research Assistant"})
        emitter.tool_call_start("researcher", "web_search", {"query": "AI trends"})
        emitter.tool_call_end("researcher", "web_search", "Found 10 results", 150.0)
        emitter.llm_request("researcher", "gpt-4o-mini", [{"role": "user", "content": "test"}])
        emitter.llm_response("researcher", 100, 500, "stop", "Response text")
        emitter.agent_end("researcher")
        emitter.session_end()
    
    print("Console sink example complete")


def example_with_real_agent():
    """Example: Use custom sink with a real agent.
    
    Note: Requires OPENAI_API_KEY environment variable.
    """
    import os
    print("\n=== Real Agent with Custom Sink ===")
    
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Skipping real agent test (no OPENAI_API_KEY)")
        return
    
    # Create custom sink
    sink = ConsoleSink()
    emitter = ContextTraceEmitter(sink=sink, session_id="real-agent-demo", enabled=True)
    
    # Use trace_context to capture all agent events
    with trace_context(emitter):
        agent = Agent(
            name="demo_agent",
            instructions="You are a helpful assistant. Be brief.",
            llm="gpt-4o-mini",
        )
        
        # This chat will emit events to ConsoleSink
        result = agent.chat("Say hello in 5 words or less")
        print(f"\nAgent response: {result}")
    
    print("Real agent example complete")


if __name__ == "__main__":
    # Run examples
    example_http_sink()
    example_console_sink()
    example_with_real_agent()
    
    print("\n✅ All examples complete!")
    print("\nKey points:")
    print("1. Implement emit(), flush(), close() - that's it!")
    print("2. Use trace_context() for automatic cleanup")
    print("3. Zero overhead when tracing is disabled")
