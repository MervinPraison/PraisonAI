"""
Unit tests for UnifiedSession and UnifiedSessionStore.
"""

import json
import os
import tempfile
import pytest
from pathlib import Path
from datetime import datetime

from praisonai.cli.session.unified import (
    UnifiedSession,
    UnifiedSessionStore,
    get_session_store,
)


class TestUnifiedSession:
    """Tests for UnifiedSession class."""
    
    def test_create_session(self):
        """Test creating a new session."""
        session = UnifiedSession(session_id="test-123")
        
        assert session.session_id == "test-123"
        assert session.messages == []
        assert session.total_input_tokens == 0
        assert session.total_output_tokens == 0
        assert session.request_count == 0
    
    def test_add_user_message(self):
        """Test adding a user message."""
        session = UnifiedSession(session_id="test-123")
        session.add_user_message("Hello, world!")
        
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "Hello, world!"
        assert "timestamp" in session.messages[0]
    
    def test_add_assistant_message(self):
        """Test adding an assistant message."""
        session = UnifiedSession(session_id="test-123")
        session.add_assistant_message("Hello! How can I help?")
        
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "assistant"
        assert session.messages[0]["content"] == "Hello! How can I help?"
    
    def test_get_chat_history(self):
        """Test getting chat history in LLM format."""
        session = UnifiedSession(session_id="test-123")
        session.add_user_message("Hello")
        session.add_assistant_message("Hi there!")
        session.add_user_message("How are you?")
        
        history = session.get_chat_history()
        
        assert len(history) == 3
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi there!"}
        assert history[2] == {"role": "user", "content": "How are you?"}
    
    def test_get_chat_history_with_limit(self):
        """Test getting limited chat history."""
        session = UnifiedSession(session_id="test-123")
        for i in range(10):
            session.add_user_message(f"Message {i}")
        
        history = session.get_chat_history(max_messages=3)
        
        assert len(history) == 3
        assert history[0]["content"] == "Message 7"
        assert history[2]["content"] == "Message 9"
    
    def test_update_stats(self):
        """Test updating token statistics."""
        session = UnifiedSession(session_id="test-123")
        session.update_stats(100, 50, 0.01)
        session.update_stats(200, 100, 0.02)
        
        assert session.total_input_tokens == 300
        assert session.total_output_tokens == 150
        assert session.total_cost == 0.03
        assert session.request_count == 2
    
    def test_clear_messages(self):
        """Test clearing messages."""
        session = UnifiedSession(session_id="test-123")
        session.add_user_message("Hello")
        session.add_assistant_message("Hi")
        session.clear_messages()
        
        assert len(session.messages) == 0
    
    def test_message_count(self):
        """Test message count property."""
        session = UnifiedSession(session_id="test-123")
        assert session.message_count == 0
        
        session.add_user_message("Hello")
        session.add_assistant_message("Hi")
        
        assert session.message_count == 2
    
    def test_user_message_count(self):
        """Test user message count property."""
        session = UnifiedSession(session_id="test-123")
        session.add_user_message("Hello")
        session.add_assistant_message("Hi")
        session.add_user_message("How are you?")
        
        assert session.user_message_count == 2
    
    def test_to_dict(self):
        """Test converting session to dictionary."""
        session = UnifiedSession(session_id="test-123")
        session.add_user_message("Hello")
        
        data = session.to_dict()
        
        assert data["session_id"] == "test-123"
        assert len(data["messages"]) == 1
        assert "created_at" in data
        assert "updated_at" in data
    
    def test_from_dict(self):
        """Test creating session from dictionary."""
        data = {
            "session_id": "test-456",
            "workspace": "/tmp/test",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
            "messages": [{"role": "user", "content": "Hello", "timestamp": "2024-01-01T00:00:00"}],
            "metadata": {},
            "total_input_tokens": 100,
            "total_output_tokens": 50,
            "total_cost": 0.01,
            "request_count": 1,
            "current_model": "gpt-4o-mini",
        }
        
        session = UnifiedSession.from_dict(data)
        
        assert session.session_id == "test-456"
        assert session.total_input_tokens == 100
        assert len(session.messages) == 1


class TestUnifiedSessionStore:
    """Tests for UnifiedSessionStore class."""
    
    @pytest.fixture
    def temp_session_dir(self):
        """Create a temporary session directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_create_store(self, temp_session_dir):
        """Test creating a session store."""
        store = UnifiedSessionStore(session_dir=temp_session_dir)
        
        assert store.session_dir == temp_session_dir
        assert temp_session_dir.exists()
    
    def test_save_and_load_session(self, temp_session_dir):
        """Test saving and loading a session."""
        store = UnifiedSessionStore(session_dir=temp_session_dir)
        
        session = UnifiedSession(session_id="test-123")
        session.add_user_message("Hello")
        session.add_assistant_message("Hi there!")
        
        store.save(session)
        
        # Clear cache to force reload from disk
        store._cache.clear()
        
        loaded = store.load("test-123")
        
        assert loaded is not None
        assert loaded.session_id == "test-123"
        assert len(loaded.messages) == 2
        assert loaded.messages[0]["content"] == "Hello"
    
    def test_get_or_create_new(self, temp_session_dir):
        """Test get_or_create with new session."""
        store = UnifiedSessionStore(session_dir=temp_session_dir)
        
        session = store.get_or_create("new-session")
        
        assert session.session_id == "new-session"
        assert (temp_session_dir / "new-session.json").exists()
    
    def test_get_or_create_existing(self, temp_session_dir):
        """Test get_or_create with existing session."""
        store = UnifiedSessionStore(session_dir=temp_session_dir)
        
        # Create and save a session
        original = UnifiedSession(session_id="existing")
        original.add_user_message("Original message")
        store.save(original)
        
        # Clear cache
        store._cache.clear()
        
        # Get or create should return existing
        session = store.get_or_create("existing")
        
        assert session.session_id == "existing"
        assert len(session.messages) == 1
        assert session.messages[0]["content"] == "Original message"
    
    def test_delete_session(self, temp_session_dir):
        """Test deleting a session."""
        store = UnifiedSessionStore(session_dir=temp_session_dir)
        
        session = store.get_or_create("to-delete")
        assert (temp_session_dir / "to-delete.json").exists()
        
        result = store.delete("to-delete")
        
        assert result is True
        assert not (temp_session_dir / "to-delete.json").exists()
    
    def test_list_sessions(self, temp_session_dir):
        """Test listing sessions."""
        store = UnifiedSessionStore(session_dir=temp_session_dir)
        
        # Create multiple sessions
        for i in range(3):
            session = store.get_or_create(f"session-{i}")
            session.add_user_message(f"Message {i}")
            store.save(session)
        
        sessions = store.list_sessions()
        
        assert len(sessions) == 3
        assert all("session_id" in s for s in sessions)
        assert all("message_count" in s for s in sessions)
    
    def test_last_session(self, temp_session_dir):
        """Test last session tracking."""
        store = UnifiedSessionStore(session_dir=temp_session_dir)
        
        # Create sessions
        store.get_or_create("first")
        store.get_or_create("second")
        
        last_id = store.get_last_session_id()
        assert last_id == "second"
        
        last_session = store.get_last_session()
        assert last_session is not None
        assert last_session.session_id == "second"
    
    def test_load_nonexistent(self, temp_session_dir):
        """Test loading a nonexistent session."""
        store = UnifiedSessionStore(session_dir=temp_session_dir)
        
        session = store.load("nonexistent")
        
        assert session is None


class TestGlobalSessionStore:
    """Tests for global session store."""
    
    def test_get_session_store(self):
        """Test getting global session store."""
        store1 = get_session_store()
        store2 = get_session_store()
        
        # Should return same instance
        assert store1 is store2
