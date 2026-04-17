"""Tests for PraisonAI ↔ aiui datastore adapter.

Tests the bridge between praisonaiagents SessionStore and aiui BaseDataStore.
"""
import pytest
from unittest.mock import Mock, MagicMock
from typing import Dict, List, Optional, Any


class MockSessionStore:
    """Mock SessionStoreProtocol for testing."""
    
    def __init__(self):
        self._sessions: Dict[str, List[Dict[str, str]]] = {}
    
    def add_message(
        self, 
        session_id: str, 
        role: str, 
        content: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        
        message = {"role": role, "content": content}
        if metadata:
            message["metadata"] = metadata
            
        self._sessions[session_id].append(message)
        return True
    
    def get_chat_history(
        self, 
        session_id: str, 
        max_messages: Optional[int] = None
    ) -> List[Dict[str, str]]:
        messages = self._sessions.get(session_id, [])
        if max_messages:
            return messages[-max_messages:]
        return messages
    
    def clear_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            self._sessions[session_id] = []
            return True
        return False
    
    def delete_session(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
    
    def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions


@pytest.fixture
def mock_store():
    """Create a mock session store."""
    return MockSessionStore()


@pytest.fixture
def datastore(mock_store):
    """Create PraisonAISessionDataStore with mock store."""
    from praisonai.ui._aiui_datastore import PraisonAISessionDataStore
    return PraisonAISessionDataStore(store=mock_store)


class TestPraisonAISessionDataStore:
    """Test the PraisonAI → aiui datastore adapter."""
    
    @pytest.mark.asyncio
    async def test_create_session(self, datastore):
        """Test creating a new session."""
        session = await datastore.create_session()
        
        assert "id" in session
        assert "messages" in session
        assert session["messages"] == []
        assert session["metadata"]["created_via"] == "praisonai"
        assert session["metadata"]["message_count"] == 0
    
    @pytest.mark.asyncio
    async def test_create_session_with_custom_id(self, datastore):
        """Test creating a session with custom ID."""
        custom_id = "test-session-123"
        session = await datastore.create_session(session_id=custom_id)
        
        assert session["id"] == custom_id
        assert session["messages"] == []
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, datastore):
        """Test getting a session that doesn't exist."""
        result = await datastore.get_session("nonexistent")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_add_and_get_message(self, datastore, mock_store):
        """Test adding and retrieving messages."""
        session_id = "test-session"
        message = {
            "role": "user",
            "content": "Hello, world!",
            "metadata": {"timestamp": "2024-01-01T12:00:00Z"}
        }
        
        # Add message
        success = await datastore.add_message(session_id, message)
        assert success is True
        
        # Retrieve session
        session = await datastore.get_session(session_id)
        assert session is not None
        assert session["id"] == session_id
        assert len(session["messages"]) == 1
        assert session["messages"][0]["role"] == "user"
        assert session["messages"][0]["content"] == "Hello, world!"
        assert session["metadata"]["message_count"] == 1
    
    @pytest.mark.asyncio
    async def test_get_messages(self, datastore, mock_store):
        """Test getting messages directly."""
        session_id = "test-session"
        
        # Add some messages
        await datastore.add_message(session_id, {"role": "user", "content": "Hi"})
        await datastore.add_message(session_id, {"role": "assistant", "content": "Hello!"})
        
        # Get messages
        messages = await datastore.get_messages(session_id)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hi"
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hello!"
    
    @pytest.mark.asyncio
    async def test_clear_session(self, datastore, mock_store):
        """Test clearing session messages."""
        session_id = "test-session"
        
        # Add messages
        await datastore.add_message(session_id, {"role": "user", "content": "Hi"})
        await datastore.add_message(session_id, {"role": "assistant", "content": "Hello!"})
        
        # Verify messages exist
        messages = await datastore.get_messages(session_id)
        assert len(messages) == 2
        
        # Clear session
        success = await datastore.clear_session(session_id)
        assert success is True
        
        # Verify messages are cleared
        messages = await datastore.get_messages(session_id)
        assert len(messages) == 0
    
    @pytest.mark.asyncio
    async def test_delete_session(self, datastore, mock_store):
        """Test deleting a session completely."""
        session_id = "test-session"
        
        # Add messages
        await datastore.add_message(session_id, {"role": "user", "content": "Hi"})
        
        # Verify session exists
        session = await datastore.get_session(session_id)
        assert session is not None
        
        # Delete session
        success = await datastore.delete_session(session_id)
        assert success is True
        
        # Verify session is gone
        session = await datastore.get_session(session_id)
        assert session is None
    
    @pytest.mark.asyncio
    async def test_delete_nonexistent_session(self, datastore):
        """Test deleting a session that doesn't exist."""
        success = await datastore.delete_session("nonexistent")
        assert success is False
    
    @pytest.mark.asyncio
    async def test_list_sessions(self, datastore):
        """Test listing sessions (returns empty for now)."""
        sessions = await datastore.list_sessions()
        assert isinstance(sessions, list)
        # Currently returns empty list - see implementation note
        assert sessions == []
    
    @pytest.mark.asyncio
    async def test_message_without_metadata(self, datastore):
        """Test adding message without metadata."""
        session_id = "test-session"
        message = {
            "role": "user",
            "content": "Hello"
        }
        
        success = await datastore.add_message(session_id, message)
        assert success is True
        
        messages = await datastore.get_messages(session_id)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello"
    
    @pytest.mark.asyncio
    async def test_message_with_missing_fields(self, datastore):
        """Test adding message with missing required fields."""
        session_id = "test-session"
        
        # Message with missing content
        message = {"role": "user"}
        success = await datastore.add_message(session_id, message)
        assert success is True
        
        messages = await datastore.get_messages(session_id)
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == ""  # Should default to empty string
    
    def test_initialization_without_store(self):
        """Test that datastore uses hierarchical store by default."""
        # This test assumes praisonaiagents is available in the test environment
        try:
            from praisonai.ui._aiui_datastore import PraisonAISessionDataStore
            datastore = PraisonAISessionDataStore()
            assert datastore._store is not None
        except ImportError:
            # If praisonaiagents is not available, that's expected
            pytest.skip("praisonaiagents not available in test environment")
    
    def test_initialization_without_praisonaiagents(self, monkeypatch):
        """Test graceful handling when praisonaiagents is not available."""
        # Mock the imports to simulate missing praisonaiagents
        monkeypatch.setattr(
            "praisonai.ui._aiui_datastore.SessionStoreProtocol", 
            None
        )
        
        from praisonai.ui._aiui_datastore import PraisonAISessionDataStore
        
        with pytest.raises(ImportError, match="praisonaiagents is required"):
            PraisonAISessionDataStore()


# Integration test with real hierarchical store (if available)
@pytest.mark.integration
class TestWithRealStore:
    """Integration tests with real SessionStore implementations."""
    
    @pytest.mark.asyncio
    async def test_with_hierarchical_store(self, tmp_path):
        """Test with real hierarchical session store."""
        try:
            from praisonai.ui._aiui_datastore import PraisonAISessionDataStore
            from praisonaiagents.session import get_hierarchical_session_store
            import os
            
            # Use temporary directory for test sessions
            original_home = os.environ.get("HOME")
            os.environ["HOME"] = str(tmp_path)
            
            try:
                store = get_hierarchical_session_store()
                datastore = PraisonAISessionDataStore(store)
                
                # Test basic functionality
                session = await datastore.create_session("integration-test")
                await datastore.add_message("integration-test", {
                    "role": "user",
                    "content": "Integration test message"
                })
                
                retrieved = await datastore.get_session("integration-test")
                assert retrieved is not None
                assert len(retrieved["messages"]) == 1
                assert retrieved["messages"][0]["content"] == "Integration test message"
                
            finally:
                # Restore original HOME
                if original_home:
                    os.environ["HOME"] = original_home
                else:
                    os.environ.pop("HOME", None)
                    
        except ImportError:
            pytest.skip("praisonaiagents not available for integration test")