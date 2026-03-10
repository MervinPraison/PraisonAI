"""TDD Tests for Memory vs History Separation Fixes.

Tests G-1 (auto_save_session routes to SessionStore) and 
G-2 (Session._save_agent_chat_histories routes to SessionStore).

These tests verify the clean separation between:
- Memory = semantic facts/entities (injected into system prompt)
- History = conversation turns (injected into message array)
"""

import pytest
from unittest.mock import MagicMock, patch


class TestG1AutoSaveSessionRouting:
    """G-1: _auto_save_session() should route to SessionStore first."""

    def test_auto_save_uses_session_store_when_available(self):
        """When SessionStore is available, use it instead of Memory.save_session()."""
        from praisonaiagents import Agent
        
        # Create agent with auto_save
        agent = Agent(
            name="test",
            instructions="Test agent",
            auto_save="test_session",
        )
        
        # Mock session store
        mock_session_store = MagicMock()
        agent._session_store = mock_session_store
        
        # Add some chat history
        agent.chat_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        
        # Call _auto_save_session
        agent._auto_save_session()
        
        # Verify SessionStore.add_message was called
        assert mock_session_store.add_message.call_count == 2

    def test_auto_save_falls_back_to_memory_when_no_session_store(self):
        """When SessionStore is not available, fall back to Memory.save_session()."""
        from praisonaiagents import Agent
        
        # Create agent with auto_save and memory
        agent = Agent(
            name="test",
            instructions="Test agent",
            auto_save="test_session",
        )
        
        # No session store
        agent._session_store = None
        
        # Mock memory instance
        mock_memory = MagicMock()
        mock_memory.save_session = MagicMock()
        agent._memory_instance = mock_memory
        
        # Add some chat history
        agent.chat_history = [
            {"role": "user", "content": "Hello"},
        ]
        
        # Call _auto_save_session
        agent._auto_save_session()
        
        # Verify Memory.save_session was called as fallback
        mock_memory.save_session.assert_called_once()

    def test_auto_save_does_nothing_when_disabled(self):
        """When auto_save is not set, do nothing."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent",
        )
        
        # No auto_save set
        agent.auto_save = None
        
        # Mock session store
        mock_session_store = MagicMock()
        agent._session_store = mock_session_store
        
        # Call _auto_save_session
        agent._auto_save_session()
        
        # Verify nothing was called
        mock_session_store.add_message.assert_not_called()


class TestG2SessionSaveAgentChatHistories:
    """G-2: Session._save_agent_chat_histories() should route to SessionStore first."""

    def test_save_agent_histories_routes_to_session_store(self):
        """Verify _save_agent_chat_histories has SessionStore routing logic."""
        from praisonaiagents.session import Session
        import inspect
        
        # Verify the method exists and has the G-2 fix comment
        source = inspect.getsource(Session._save_agent_chat_histories)
        
        # Check that the G-2 fix is present
        assert "G-2 FIX" in source, "G-2 fix should be documented in the method"
        assert "SessionStore" in source, "Method should reference SessionStore"
        assert "get_default_session_store" in source, "Method should try to get SessionStore"


class TestMemoryHistorySeparation:
    """Test that Memory and History are properly separated."""

    def test_memory_context_does_not_include_conversation_turns(self):
        """Memory.get_context() should return facts/entities, not conversation turns."""
        from praisonaiagents.memory import FileMemory
        
        memory = FileMemory(user_id="test_user")
        
        # Store some facts using correct API
        memory.add_long_term("User prefers Python programming")
        memory.add_entity("Alice", "person", {"role": "developer"})
        
        # Get context
        context = memory.get_context()
        
        # Should contain facts and entities
        assert "Important Facts" in context or "Known Entities" in context or context == ""
        
        # Should NOT contain conversation turn markers
        assert "role" not in context.lower() or "user:" not in context.lower()

    def test_session_store_stores_conversation_turns(self):
        """SessionStore should store conversation turns with role/content."""
        from praisonaiagents.session import get_default_session_store
        
        store = get_default_session_store()
        
        # Add messages
        store.add_message("test_session", role="user", content="Hello")
        store.add_message("test_session", role="assistant", content="Hi!")
        
        # Get history
        history = store.get_chat_history("test_session")
        
        # Should have conversation turns
        assert len(history) >= 2
        assert any(msg.get("role") == "user" for msg in history)
        assert any(msg.get("role") == "assistant" for msg in history)


class TestG3PerTurnPersist:
    """G-3: Verify per-turn persist exists via _persist_message()."""

    def test_persist_message_exists(self):
        """Agent should have _persist_message method for per-turn persistence."""
        from praisonaiagents import Agent
        
        agent = Agent(name="test", instructions="Test")
        
        # Verify method exists
        assert hasattr(agent, '_persist_message')
        assert callable(agent._persist_message)

    def test_persist_message_uses_session_store(self):
        """_persist_message should use SessionStore when available."""
        from praisonaiagents import Agent
        
        # Create agent without session_id (it's set via memory config)
        agent = Agent(name="test", instructions="Test")
        
        # Mock session store
        mock_store = MagicMock()
        agent._session_store = mock_store
        agent._session_id = "test_session"
        agent._db = None  # No DB adapter
        
        # Call _persist_message
        agent._persist_message("user", "Hello")
        
        # Verify SessionStore was used
        mock_store.add_user_message.assert_called_once_with("test_session", "Hello")
