"""
Session Persistence Example

Demonstrates automatic session persistence with zero configuration.
When you provide a session_id to an Agent, conversation history is
automatically saved to disk and restored on subsequent runs.

Usage:
    python session_persistence_example.py

Requirements:
    - praisonaiagents package installed
    - OPENAI_API_KEY environment variable set
"""

from praisonaiagents import Agent


def example_basic_persistence():
    """Basic session persistence example."""
    print("=" * 60)
    print("EXAMPLE 1: Basic Session Persistence")
    print("=" * 60)
    
    session_id = "demo-session-basic"
    
    # Create agent with session_id
    agent = Agent(
        name="Assistant",
        instructions="You are a helpful assistant. Be very brief.",
        session_id=session_id,
        verbose=False,
    )
    
    # First message
    print("\n[User]: My favorite color is blue and my lucky number is 7.")
    response1 = agent.chat("My favorite color is blue and my lucky number is 7.")
    print(f"[Assistant]: {response1}")
    
    # Second message - agent remembers
    print("\n[User]: What is my favorite color?")
    response2 = agent.chat("What is my favorite color?")
    print(f"[Assistant]: {response2}")
    
    print(f"\n✅ Session saved to: ~/.praison/sessions/{session_id}.json")
    print(f"   Chat history length: {len(agent.chat_history)} messages")


def example_session_restoration():
    """Demonstrates session restoration across Agent instances."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Session Restoration")
    print("=" * 60)
    
    session_id = "demo-session-restore"
    
    # First agent instance
    print("\n--- First Agent Instance ---")
    agent1 = Agent(
        name="MemoryBot",
        instructions="You are a helpful assistant. Be very brief.",
        session_id=session_id,
        verbose=False,
    )
    
    print("[User]: Remember that my pet's name is Max.")
    response1 = agent1.chat("Remember that my pet's name is Max.")
    print(f"[Assistant]: {response1}")
    
    # Simulate new process by creating new agent instance
    print("\n--- New Agent Instance (simulating restart) ---")
    agent2 = Agent(
        name="MemoryBot",
        instructions="You are a helpful assistant. Be very brief.",
        session_id=session_id,
        verbose=False,
    )
    
    print("[User]: What is my pet's name?")
    response2 = agent2.chat("What is my pet's name?")
    print(f"[Assistant]: {response2}")
    
    if "max" in response2.lower():
        print("\n✅ Session restored successfully! Agent remembered 'Max'.")
    else:
        print("\n⚠️ Agent may not have remembered correctly.")


def example_in_memory_only():
    """Demonstrates in-memory memory without persistence."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: In-Memory Only (No session_id)")
    print("=" * 60)
    
    # Agent without session_id - in-memory only
    agent = Agent(
        name="TempBot",
        instructions="You are a helpful assistant. Be very brief.",
        verbose=False,
    )
    
    print("\n[User]: My name is Alice.")
    response1 = agent.chat("My name is Alice.")
    print(f"[Assistant]: {response1}")
    
    print("\n[User]: What is my name?")
    response2 = agent.chat("What is my name?")
    print(f"[Assistant]: {response2}")
    
    print(f"\n✅ In-memory chat history: {len(agent.chat_history)} messages")
    print("   (This will be lost when the Agent instance is garbage collected)")


def example_direct_store_access():
    """Demonstrates direct access to the session store."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Direct Session Store Access")
    print("=" * 60)
    
    from praisonaiagents.session import get_default_session_store
    
    store = get_default_session_store()
    session_id = "demo-direct-access"
    
    # Add messages directly
    store.add_user_message(session_id, "Hello from direct access!")
    store.add_assistant_message(session_id, "Hi! I received your message.")
    
    # Get history
    history = store.get_chat_history(session_id)
    print(f"\n✅ Added {len(history)} messages directly to session store")
    
    for msg in history:
        print(f"   [{msg['role']}]: {msg['content']}")
    
    # List all sessions
    sessions = store.list_sessions()
    print(f"\n📋 Total sessions in store: {len(sessions)}")
    
    # Clean up demo session
    store.delete_session(session_id)
    print(f"   Deleted demo session: {session_id}")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("SESSION PERSISTENCE EXAMPLES")
    print("=" * 60)
    
    # Run examples
    example_basic_persistence()
    example_session_restoration()
    example_in_memory_only()
    example_direct_store_access()
    
    print("\n" + "=" * 60)
    print("ALL EXAMPLES COMPLETE")
    print("=" * 60)
    print("\nSession files are stored in: ~/.praison/sessions/")
    print("You can inspect them with: cat ~/.praison/sessions/<session_id>.json")


if __name__ == "__main__":
    main()
