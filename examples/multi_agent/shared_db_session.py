"""Multi-Agent Shared Session - DB Persistence Test"""
import sys
sys.path.insert(0, 'src/praisonai')
from praisonai.persistence import create_conversation_store
from praisonai.persistence.conversation.base import ConversationSession, ConversationMessage

# Create shared session for multiple agents
store = create_conversation_store("sqlite", path="/tmp/multi_agent.db")
session_id = "shared-session-123"

# Create session
session = ConversationSession(session_id=session_id, agent_id="multi")
try:
    store.create_session(session)
except Exception:
    pass

# Agent 1 writes
msg1 = ConversationMessage(session_id=session_id, role="user", content="Agent1: Hello")
store.add_message(session_id, msg1)
msg2 = ConversationMessage(session_id=session_id, role="assistant", content="Agent1: Hi there!")
store.add_message(session_id, msg2)

# Agent 2 writes to same session
msg3 = ConversationMessage(session_id=session_id, role="user", content="Agent2: What did Agent1 say?")
store.add_message(session_id, msg3)
msg4 = ConversationMessage(session_id=session_id, role="assistant", content="Agent2: Agent1 said Hello")
store.add_message(session_id, msg4)

# Verify both agents' messages are in session
messages = store.get_messages(session_id)
print(f"Total messages in shared session: {len(messages)}")
assert len(messages) >= 4, "Should have messages from both agents"

# Verify content
contents = [m.content for m in messages]
assert any("Agent1" in c for c in contents), "Should have Agent1 messages"
assert any("Agent2" in c for c in contents), "Should have Agent2 messages"

print("PASSED: Multi-agent shared session persistence")
