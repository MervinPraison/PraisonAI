#!/usr/bin/env python3
"""
Session Management Example

Demonstrates how to use the Session class for stateful agent interactions
with persistent memory and state management.
"""

from praisonaiagents import Session

def main():
    print("🔄 Session Management Example")
    print("=" * 50)
    
    # Create a session with persistent storage
    session = Session(
        session_id="demo_chat_001",
        user_id="demo_user"
    )
    
    print(f"📝 Created session: {session}")
    
    # Create an agent within the session context
    agent = session.Agent(
        name="Personal Assistant",
        role="Helpful AI Assistant", 
        instructions="Remember user preferences and provide personalized assistance",
        memory=True
    )
    
    print(f"🤖 Created agent: {agent.name}")
    
    # Initial conversation with preference setting
    print("\n--- Initial Conversation ---")
    response1 = agent.chat("Hi! I prefer brief, technical explanations. Please remember this.")
    print(f"Assistant: {response1}")
    
    # Save some session state
    session.save_state({
        "conversation_style": "brief_technical", 
        "topics_discussed": ["preferences"],
        "session_start": "2024-01-15 10:00:00"
    })
    
    print("\n💾 Saved session state")
    
    # Continue conversation - agent should remember preference
    print("\n--- Continued Conversation ---")
    response2 = agent.chat("Can you explain how neural networks work?")
    print(f"Assistant: {response2}")
    
    # Update session state
    session.set_state("topics_discussed", ["preferences", "neural_networks"])
    session.increment_state("message_count", 2, default=0)
    
    # Add some knowledge to the session
    print("\n📚 Adding knowledge to session...")
    session.add_memory(
        "User prefers brief technical explanations for complex topics",
        memory_type="long"
    )
    
    # Simulate session restart - restore state
    print("\n🔄 Simulating session restart...")
    restored_state = session.restore_state()
    print(f"Restored state: {restored_state}")
    
    # Get specific state values
    style = session.get_state("conversation_style", "default")
    topics = session.get_state("topics_discussed", [])
    msg_count = session.get_state("message_count", 0)
    
    print(f"Conversation style: {style}")
    print(f"Topics discussed: {topics}")
    print(f"Message count: {msg_count}")
    
    # Search session memory
    print("\n🔍 Searching session memory...")
    memory_results = session.search_memory("preferences", memory_type="long")
    if memory_results:
        print(f"Found memory: {memory_results[0]['text'][:100]}...")
    
    # Build context for new conversation
    print("\n🧠 Building context for new conversation...")
    context = session.get_context("machine learning concepts")
    if context:
        print(f"Context preview: {context[:200]}...")
    
    # Final conversation using built context
    print("\n--- Final Conversation with Context ---")
    response3 = agent.chat("What about deep learning? Keep it technical but concise.")
    print(f"Assistant: {response3}")
    
    print("\n✅ Session example completed!")
    print("The agent maintained conversation context and user preferences across the session.")

if __name__ == "__main__":
    main()