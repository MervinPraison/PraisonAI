"""Tests for PraisonAI → aiui datastore adapter."""

import pytest
from unittest.mock import Mock, patch
from praisonai.ui._aiui_datastore import PraisonAISessionDataStore


class TestPraisonAISessionDataStore:
    """Test the datastore adapter that bridges PraisonAI sessions to aiui."""

    def test_init_with_default_store(self):
        """Test initialization with default hierarchical store."""
        with patch('praisonai.ui._aiui_datastore.get_hierarchical_session_store') as mock_get_store:
            mock_store = Mock()
            mock_get_store.return_value = mock_store
            
            adapter = PraisonAISessionDataStore()
            
            assert adapter._store == mock_store
            mock_get_store.assert_called_once()

    def test_init_with_custom_store(self):
        """Test initialization with custom session store."""
        mock_store = Mock()
        adapter = PraisonAISessionDataStore(store=mock_store)
        
        assert adapter._store == mock_store

    @pytest.mark.asyncio
    async def test_get_session_exists(self):
        """Test getting an existing session."""
        mock_store = Mock()
        mock_store.session_exists.return_value = True
        mock_store.get_chat_history.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"}
        ]
        
        adapter = PraisonAISessionDataStore(store=mock_store)
        result = await adapter.get_session("test-session")
        
        assert result == {
            "id": "test-session",
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"}
            ]
        }
        mock_store.session_exists.assert_called_once_with("test-session")
        mock_store.get_chat_history.assert_called_once_with("test-session")

    @pytest.mark.asyncio
    async def test_get_session_not_exists(self):
        """Test getting a non-existent session."""
        mock_store = Mock()
        mock_store.session_exists.return_value = False
        
        adapter = PraisonAISessionDataStore(store=mock_store)
        result = await adapter.get_session("nonexistent")
        
        assert result is None
        mock_store.session_exists.assert_called_once_with("nonexistent")
        mock_store.get_chat_history.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_session_corrupted(self):
        """Test getting a corrupted session."""
        mock_store = Mock()
        mock_store.session_exists.return_value = True
        mock_store.get_chat_history.side_effect = Exception("Corrupted session")
        
        adapter = PraisonAISessionDataStore(store=mock_store)
        result = await adapter.get_session("corrupted-session")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_create_session_with_id(self):
        """Test creating a session with specified ID."""
        mock_store = Mock()
        adapter = PraisonAISessionDataStore(store=mock_store)
        
        result = await adapter.create_session("my-session")
        
        assert result == {"id": "my-session", "messages": []}

    @pytest.mark.asyncio
    async def test_create_session_auto_id(self):
        """Test creating a session with auto-generated ID."""
        mock_store = Mock()
        adapter = PraisonAISessionDataStore(store=mock_store)
        
        result = await adapter.create_session()
        
        assert "id" in result
        assert result["messages"] == []
        # Check that ID is a valid UUID format
        assert len(result["id"]) == 36  # UUID length
        assert result["id"].count("-") == 4  # UUID has 4 dashes

    @pytest.mark.asyncio
    async def test_delete_session_success(self):
        """Test successful session deletion."""
        mock_store = Mock()
        mock_store.delete_session.return_value = True
        
        adapter = PraisonAISessionDataStore(store=mock_store)
        result = await adapter.delete_session("test-session")
        
        assert result is True
        mock_store.delete_session.assert_called_once_with("test-session")

    @pytest.mark.asyncio
    async def test_delete_session_failure(self):
        """Test failed session deletion."""
        mock_store = Mock()
        mock_store.delete_session.side_effect = Exception("Delete failed")
        
        adapter = PraisonAISessionDataStore(store=mock_store)
        result = await adapter.delete_session("test-session")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_add_message(self):
        """Test adding a message to a session."""
        mock_store = Mock()
        adapter = PraisonAISessionDataStore(store=mock_store)
        
        message = {
            "role": "user",
            "content": "Hello world",
            "metadata": {"timestamp": "2024-01-01"}
        }
        
        await adapter.add_message("test-session", message)
        
        mock_store.add_message.assert_called_once_with(
            session_id="test-session",
            role="user",
            content="Hello world",
            metadata={"timestamp": "2024-01-01"}
        )

    @pytest.mark.asyncio
    async def test_add_message_minimal(self):
        """Test adding a message with minimal fields."""
        mock_store = Mock()
        adapter = PraisonAISessionDataStore(store=mock_store)
        
        message = {"content": "Hello"}
        
        await adapter.add_message("test-session", message)
        
        mock_store.add_message.assert_called_once_with(
            session_id="test-session",
            role="user",  # default
            content="Hello",
            metadata=None
        )

    @pytest.mark.asyncio
    async def test_get_messages_success(self):
        """Test getting messages for a session."""
        mock_store = Mock()
        mock_store.session_exists.return_value = True
        mock_store.get_chat_history.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"}
        ]
        
        adapter = PraisonAISessionDataStore(store=mock_store)
        result = await adapter.get_messages("test-session")
        
        assert result == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"}
        ]

    @pytest.mark.asyncio
    async def test_get_messages_nonexistent(self):
        """Test getting messages for non-existent session."""
        mock_store = Mock()
        mock_store.session_exists.return_value = False
        
        adapter = PraisonAISessionDataStore(store=mock_store)
        result = await adapter.get_messages("nonexistent")
        
        assert result == []

    @pytest.mark.asyncio
    async def test_get_messages_error(self):
        """Test getting messages when store throws error."""
        mock_store = Mock()
        mock_store.session_exists.return_value = True
        mock_store.get_chat_history.side_effect = Exception("Store error")
        
        adapter = PraisonAISessionDataStore(store=mock_store)
        result = await adapter.get_messages("test-session")
        
        assert result == []

    @pytest.mark.asyncio
    async def test_list_sessions_delegates_to_store(self):
        """Test listing sessions delegates to store when available."""
        mock_store = Mock()
        mock_store.list_sessions.return_value = [
            {"session_id": "a", "created_at": 1, "message_count": 3},
            {"session_id": "b", "created_at": 2, "message_count": 5},
        ]
        adapter = PraisonAISessionDataStore(store=mock_store)
        
        result = await adapter.list_sessions()
        
        assert len(result) == 2
        assert result[0]["session_id"] == "a"
        assert result[1]["session_id"] == "b"
        mock_store.list_sessions.assert_called_once_with(limit=50)

    @pytest.mark.asyncio
    async def test_list_sessions_store_without_list(self):
        """Test listing sessions when store doesn't support listing."""
        # Custom SessionStoreProtocol impls don't require list_sessions
        mock_store = Mock(spec=["add_message", "get_chat_history",
                               "clear_session", "delete_session", "session_exists"])
        adapter = PraisonAISessionDataStore(store=mock_store)
        
        result = await adapter.list_sessions()
        
        assert result == []


# Removed test_import_fallback - was a no-op test that passed regardless of behavior
# After Blocker 1 fix, imports now fail loudly instead of falling back silently