"""
Dynamic Context Discovery Example.

This example demonstrates how to use the Dynamic Context Discovery feature
to efficiently manage large tool outputs, conversation history, and terminal logs.

Features demonstrated:
1. Tool output queuing - Large outputs automatically saved as artifacts
2. Artifact tools - tail, grep, chunk operations on stored artifacts
3. History persistence - Conversation history saved for loss recovery
4. Terminal logging - Shell command outputs captured

Usage:
    python dynamic_context_example.py
"""

import tempfile


def example_artifact_store():
    """Demonstrate artifact storage and retrieval."""
    print("\n=== Artifact Store Example ===\n")
    
    from praisonai.context import FileSystemArtifactStore
    from praisonaiagents.context.artifacts import ArtifactMetadata
    
    # Create a temporary store
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileSystemArtifactStore(base_dir=tmpdir)
        
        # Store a large JSON response (simulating API output)
        large_data = {
            "records": [{"id": i, "name": f"Item {i}"} for i in range(1000)],
            "metadata": {"total": 1000, "page": 1},
        }
        
        metadata = ArtifactMetadata(
            agent_id="data_agent",
            run_id="run_001",
            tool_name="api_fetch",
        )
        
        ref = store.store(large_data, metadata)
        print(f"Stored artifact: {ref.path}")
        print(f"Size: {ref._format_size(ref.size_bytes)}")
        print(f"Summary: {ref.summary}")
        print(f"Inline reference: {ref.to_inline()}")
        
        # Demonstrate tail operation
        print("\n--- Tail (last 5 lines) ---")
        tail = store.tail(ref, lines=5)
        print(tail)
        
        # Demonstrate grep operation
        print("\n--- Grep for 'Item 50' ---")
        matches = store.grep(ref, pattern="Item 50")
        for match in matches[:3]:
            print(f"Line {match.line_number}: {match.line_content[:60]}...")
        
        # List all artifacts
        print("\n--- List artifacts ---")
        artifacts = store.list_artifacts(run_id="run_001")
        for art in artifacts:
            print(f"  - {art.artifact_id}: {art.tool_name} ({art._format_size(art.size_bytes)})")


def example_output_queue():
    """Demonstrate automatic tool output queuing (previously called spooling)."""
    print("\n=== Output Queue Example ===\n")
    
    from praisonai.context import OutputQueue
    from praisonaiagents.context.artifacts import ArtifactMetadata, ArtifactRef, QueueConfig
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create output queue with 1KB threshold (for demo)
        config = QueueConfig(inline_max_bytes=1024)
        queue = OutputQueue(base_dir=tmpdir, config=config)
        
        # Small output - stays inline (not queued to artifact)
        small_output = "Hello, world!"
        metadata = ArtifactMetadata(agent_id="agent1", run_id="run1")
        result = queue.process(small_output, metadata)
        print(f"Small output ({len(small_output)} bytes): {'Queued' if isinstance(result, ArtifactRef) else 'Inline'}")
        
        # Large output - automatically queued to artifact
        large_output = "x" * 2000
        result = queue.process(large_output, metadata)
        print(f"Large output ({len(large_output)} bytes): {'Queued' if isinstance(result, ArtifactRef) else 'Inline'}")
        
        if isinstance(result, ArtifactRef):
            print(f"  Artifact path: {result.path}")


def example_history_store():
    """Demonstrate conversation history persistence."""
    print("\n=== History Store Example ===\n")
    
    from praisonai.context import HistoryStore
    
    with tempfile.TemporaryDirectory() as tmpdir:
        store = HistoryStore(base_dir=tmpdir)
        
        # Simulate a conversation
        messages = [
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
            {"role": "user", "content": "What about Germany?"},
            {"role": "assistant", "content": "The capital of Germany is Berlin."},
            {"role": "user", "content": "And what about the error in my code?"},
            {"role": "assistant", "content": "I see an error on line 42. The variable is undefined."},
        ]
        
        for msg in messages:
            store.append(msg, agent_id="assistant", run_id="session_001")
        
        # Get history reference
        ref = store.get_ref(agent_id="assistant", run_id="session_001")
        print(f"History stored: {ref.summary}")
        
        # Search history
        print("\n--- Search for 'capital' ---")
        matches = store.search("capital", agent_id="assistant", run_id="session_001")
        for msg in matches:
            print(f"  [{msg['role']}]: {msg['content'][:50]}...")
        
        # Get last messages
        print("\n--- Last 2 messages ---")
        recent = store.get_last_messages(agent_id="assistant", run_id="session_001", count=2)
        for msg in recent:
            print(f"  [{msg['role']}]: {msg['content'][:50]}...")


def example_terminal_logger():
    """Demonstrate terminal session logging."""
    print("\n=== Terminal Logger Example ===\n")
    
    from praisonai.context import TerminalLogger
    
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = TerminalLogger(base_dir=tmpdir)
        
        # Log some commands
        commands = [
            ("ls -la", "total 100\ndrwxr-xr-x 5 user user 160 Jan 1 00:00 .\n-rw-r--r-- 1 user user 1234 Jan 1 00:00 file.txt", 0),
            ("cat file.txt", "Hello, world!\nThis is a test file.", 0),
            ("grep error log.txt", "Error: Something went wrong\nError: Another issue", 0),
            ("invalid_command", "command not found: invalid_command", 127),
        ]
        
        for cmd, output, exit_code in commands:
            ref = logger.log_command(
                command=cmd,
                output=output,
                exit_code=exit_code,
                agent_id="shell_agent",
                run_id="session_001",
            )
        
        # Get session reference
        ref = logger.get_session_ref(agent_id="shell_agent", run_id="session_001")
        print(f"Terminal session: {ref.summary}")
        
        # Tail the session
        print("\n--- Tail (last 10 lines) ---")
        tail = logger.tail_session(agent_id="shell_agent", run_id="session_001", lines=10)
        print(tail)
        
        # Search for errors
        print("\n--- Grep for 'Error' ---")
        matches = logger.grep_session("Error", agent_id="shell_agent", run_id="session_001")
        for match in matches:
            print(f"  Line {match.line_number}: {match.line_content}")
        
        # Get command list
        print("\n--- Commands executed ---")
        cmds = logger.get_commands(agent_id="shell_agent", run_id="session_001")
        for cmd in cmds:
            status = "✓" if cmd["exit_code"] == 0 else "✗"
            print(f"  {status} $ {cmd['command']}")


def example_setup_dynamic_context():
    """Demonstrate the convenience setup function."""
    print("\n=== Setup Dynamic Context Example ===\n")
    
    from praisonai.context import setup_dynamic_context
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up dynamic context with all features
        ctx = setup_dynamic_context(
            base_dir=tmpdir,
            inline_max_kb=16,  # 16KB threshold
            redact_secrets=True,
            history_enabled=True,
            terminal_logging=True,
        )
        
        print(f"Run ID: {ctx.run_id}")
        print(f"Base directory: {ctx.config.base_dir}")
        
        # Get tools for agent
        tools = ctx.get_tools()
        print(f"\nAvailable tools ({len(tools)}):")
        for tool in tools:
            print(f"  - {tool.__name__}: {tool.__doc__.split(chr(10))[0] if tool.__doc__ else 'No description'}")
        
        # Get middleware
        middleware = ctx.get_middleware()
        print(f"\nMiddleware: {middleware.__name__}")


def example_agent_integration():
    """Show how to integrate with Agent (conceptual)."""
    print("\n=== Agent Integration Example (Conceptual) ===\n")
    
    print("""
# To integrate Dynamic Context Discovery with an Agent:

from praisonaiagents import Agent
from praisonai.context import setup_dynamic_context

# Set up dynamic context
ctx = setup_dynamic_context(
    inline_max_kb=32,
    history_enabled=True,
)

# Create agent with dynamic context tools and middleware
agent = Agent(
    name="DataAnalyst",
    instructions="You are a data analyst. Use artifact tools to explore large outputs.",
    tools=ctx.get_tools(),  # Adds artifact_tail, artifact_grep, etc.
    hooks=[ctx.get_middleware()],  # Auto-queues large tool outputs
)

# Now when the agent uses tools that produce large outputs,
# they will be automatically queued to artifacts.
# The agent can then use artifact_tail, artifact_grep, etc.
# to explore the data without loading it all into context.
""")


if __name__ == "__main__":
    print("=" * 60)
    print("Dynamic Context Discovery Examples")
    print("=" * 60)
    
    example_artifact_store()
    example_output_queue()
    example_history_store()
    example_terminal_logger()
    example_setup_dynamic_context()
    example_agent_integration()
    
    print("\n" + "=" * 60)
    print("All examples completed successfully!")
    print("=" * 60)
