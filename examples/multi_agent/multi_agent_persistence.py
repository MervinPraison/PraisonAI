"""
Multi-Agent Persistence Example

Demonstrates how multiple agents can share or isolate conversation
history using the persistence layer.
"""

from praisonai.persistence.factory import create_conversation_store, create_state_store
from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage
import uuid


def main():
    # Create stores
    conv_store = create_conversation_store("sqlite", path=":memory:")
    state_store = create_state_store("memory")
    
    print("=== Multi-Agent Persistence Demo ===\n")
    
    # Scenario 1: Shared session (agents collaborate)
    print("--- Scenario 1: Shared Session ---")
    shared_session_id = f"shared-{uuid.uuid4().hex[:8]}"
    
    session = ConversationSession(
        session_id=shared_session_id,
        user_id="user-123",
        name="Shared Conversation"
    )
    conv_store.create_session(session)
    
    # Agent 1 (Researcher) adds context
    conv_store.add_message(shared_session_id, ConversationMessage(
        role="assistant",
        content="[Researcher] I found relevant information about the topic.",
        metadata={"agent_id": "researcher", "agent_role": "research"}
    ))
    
    # Agent 2 (Writer) uses the context
    conv_store.add_message(shared_session_id, ConversationMessage(
        role="assistant", 
        content="[Writer] Based on the research, here's a summary...",
        metadata={"agent_id": "writer", "agent_role": "writing"}
    ))
    
    # Agent 3 (Editor) reviews
    conv_store.add_message(shared_session_id, ConversationMessage(
        role="assistant",
        content="[Editor] I've reviewed and polished the content.",
        metadata={"agent_id": "editor", "agent_role": "editing"}
    ))
    
    messages = conv_store.get_messages(shared_session_id)
    print(f"Shared session has {len(messages)} messages from different agents")
    for msg in messages:
        agent = msg.metadata.get("agent_id", "unknown") if msg.metadata else "unknown"
        print(f"  - {agent}: {msg.content[:50]}...")
    
    # Scenario 2: Isolated sessions (agents work independently)
    print("\n--- Scenario 2: Isolated Sessions ---")
    
    agent_sessions = {}
    for agent_name in ["planner", "executor", "validator"]:
        session_id = f"{agent_name}-{uuid.uuid4().hex[:8]}"
        agent_sessions[agent_name] = session_id
        
        conv_store.create_session(ConversationSession(
            session_id=session_id,
            agent_id=agent_name,
            name=f"{agent_name.title()} Session"
        ))
        
        # Each agent has its own conversation
        conv_store.add_message(session_id, ConversationMessage(
            role="user",
            content=f"Task for {agent_name}"
        ))
        conv_store.add_message(session_id, ConversationMessage(
            role="assistant",
            content=f"[{agent_name.title()}] Processing task..."
        ))
    
    print("Created isolated sessions for each agent:")
    for agent, sid in agent_sessions.items():
        msgs = conv_store.get_messages(sid)
        print(f"  - {agent}: {len(msgs)} messages")
    
    # Scenario 3: Shared state across agents
    print("\n--- Scenario 3: Shared State ---")
    
    # Agents share state for coordination
    state_store.set("workflow:status", {"phase": "research", "progress": 0})
    state_store.set("workflow:context", {"topic": "AI Agents", "deadline": "2024-12-31"})
    
    # Agent 1 updates progress
    state = state_store.get("workflow:status")
    state["progress"] = 33
    state["phase"] = "writing"
    state_store.set("workflow:status", state)
    print(f"Agent 1 updated state: {state}")
    
    # Agent 2 reads and updates
    state = state_store.get("workflow:status")
    state["progress"] = 66
    state["phase"] = "editing"
    state_store.set("workflow:status", state)
    print(f"Agent 2 updated state: {state}")
    
    # Agent 3 completes
    state = state_store.get("workflow:status")
    state["progress"] = 100
    state["phase"] = "complete"
    state_store.set("workflow:status", state)
    print(f"Agent 3 completed: {state}")
    
    # Cleanup
    conv_store.close()
    state_store.close()
    print("\n✅ Multi-agent persistence demo complete!")


if __name__ == "__main__":
    main()
