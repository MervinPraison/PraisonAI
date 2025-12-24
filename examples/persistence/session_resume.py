"""
Session Resume Example

Demonstrates how to resume a conversation from a previous session.

Run:
    python session_resume.py

Expected output:
    - First run: Creates new session
    - Second run: Resumes with history
"""

from praisonaiagents import Agent, db

# Create database
my_db = db.PraisonDB(
    database_url="postgresql://postgres:praison123@localhost:5432/praisonai",
    state_url="redis://localhost:6379"
)

SESSION_ID = "resume-demo-session"

# Create agent with explicit session_id
agent = Agent(
    name="MemoryBot",
    instructions="You remember our conversation. Be helpful and concise.",
    db=my_db,
    session_id=SESSION_ID
)

# Check if this is a new or resumed session
data = my_db.export_session(SESSION_ID)
existing_messages = len(data.get('messages', []))

if existing_messages == 0:
    print("=== NEW SESSION ===")
    print("This is a new conversation.\n")
    
    response = agent.chat("My name is Alice and I love Python programming.")
    print(f"Response: {response}\n")
    
    response = agent.chat("What's my favorite programming language?")
    print(f"Response: {response}\n")
else:
    print(f"=== RESUMED SESSION ({existing_messages} previous messages) ===")
    print("Continuing previous conversation.\n")
    
    # Show previous messages
    print("Previous messages:")
    for msg in data.get('messages', [])[:4]:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')[:60]
        print(f"  [{role}] {content}...")
    print()
    
    # Continue conversation
    response = agent.chat("What's my name and what do I like?")
    print(f"Response: {response}\n")

# Show final state
final_data = my_db.export_session(SESSION_ID)
print(f"Total messages now: {len(final_data.get('messages', []))}")

my_db.close()
print("✅ Done")
