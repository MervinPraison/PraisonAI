"""
TDD Tests for Session Store.

Tests for DefaultSessionStore with JSON-based persistence.
"""

import json
import os
import tempfile
import threading
import time
import pytest
from concurrent.futures import ThreadPoolExecutor

from praisonaiagents.session.store import (
    DefaultSessionStore,
    SessionMessage,
    SessionData,
    FileLock,
    DEFAULT_MAX_MESSAGES,
)


class TestSessionMessage:
    """Tests for SessionMessage dataclass."""
    
    def test_create_message(self):
        """Test creating a session message."""
        msg = SessionMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.timestamp > 0
        assert msg.metadata == {}
    
    def test_message_to_dict(self):
        """Test converting message to dict."""
        msg = SessionMessage(role="assistant", content="Hi there!")
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there!"
        assert "timestamp" in d
        assert "metadata" in d
    
    def test_message_from_dict(self):
        """Test creating message from dict."""
        d = {"role": "user", "content": "Test", "timestamp": 123.0, "metadata": {"key": "value"}}
        msg = SessionMessage.from_dict(d)
        assert msg.role == "user"
        assert msg.content == "Test"
        assert msg.timestamp == 123.0
        assert msg.metadata == {"key": "value"}


class TestSessionData:
    """Tests for SessionData dataclass."""
    
    def test_create_session(self):
        """Test creating session data."""
        session = SessionData(session_id="test-123")
        assert session.session_id == "test-123"
        assert session.messages == []
        assert session.created_at is not None
        assert session.updated_at is not None
    
    def test_session_to_dict(self):
        """Test converting session to dict."""
        session = SessionData(session_id="test-123", agent_name="Assistant")
        session.messages.append(SessionMessage(role="user", content="Hello"))
        d = session.to_dict()
        assert d["session_id"] == "test-123"
        assert d["agent_name"] == "Assistant"
        assert len(d["messages"]) == 1
    
    def test_session_from_dict(self):
        """Test creating session from dict."""
        d = {
            "session_id": "test-456",
            "messages": [{"role": "user", "content": "Hi"}],
            "agent_name": "Bot",
        }
        session = SessionData.from_dict(d)
        assert session.session_id == "test-456"
        assert session.agent_name == "Bot"
        assert len(session.messages) == 1
    
    def test_get_chat_history(self):
        """Test getting chat history in LLM format."""
        session = SessionData(session_id="test")
        session.messages.append(SessionMessage(role="user", content="Hello"))
        session.messages.append(SessionMessage(role="assistant", content="Hi!"))
        
        history = session.get_chat_history()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "Hello"}
        assert history[1] == {"role": "assistant", "content": "Hi!"}
    
    def test_get_chat_history_with_limit(self):
        """Test getting limited chat history."""
        session = SessionData(session_id="test")
        for i in range(10):
            session.messages.append(SessionMessage(role="user", content=f"Message {i}"))
        
        history = session.get_chat_history(max_messages=3)
        assert len(history) == 3
        assert history[0]["content"] == "Message 7"
        assert history[2]["content"] == "Message 9"


class TestFileLock:
    """Tests for FileLock."""
    
    def test_acquire_release(self):
        """Test basic lock acquire and release."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            lock = FileLock(filepath, timeout=1.0)
            
            assert lock.acquire()
            lock.release()
    
    def test_context_manager(self):
        """Test lock as context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            
            with FileLock(filepath, timeout=1.0):
                # Lock is held
                pass
            # Lock is released
    
    def test_concurrent_locks(self):
        """Test that concurrent locks are serialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            results = []
            lock_obj = threading.Lock()  # For thread-safe list append
            
            def worker(worker_id):
                with FileLock(filepath, timeout=10.0):
                    with lock_obj:
                        results.append(f"start-{worker_id}")
                    time.sleep(0.05)  # Reduced sleep for faster test
                    with lock_obj:
                        results.append(f"end-{worker_id}")
            
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15.0)  # Add timeout to prevent hanging
            
            # Check that starts and ends are paired (no interleaving)
            for i in range(3):
                start_idx = results.index(f"start-{i}")
                end_idx = results.index(f"end-{i}")
                # No other start should be between this start and end
                for j in range(3):
                    if i != j:
                        other_start = results.index(f"start-{j}")
                        if start_idx < other_start < end_idx:
                            pytest.fail(f"Lock interleaving detected: {results}")


class TestDefaultSessionStore:
    """Tests for DefaultSessionStore."""
    
    @pytest.fixture
    def temp_store(self):
        """Create a temporary session store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            yield store
    
    def test_add_message(self, temp_store):
        """Test adding a message."""
        result = temp_store.add_message("session-1", "user", "Hello")
        assert result is True
        
        history = temp_store.get_chat_history("session-1")
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
    
    def test_add_user_message(self, temp_store):
        """Test adding a user message."""
        temp_store.add_user_message("session-1", "Hello")
        history = temp_store.get_chat_history("session-1")
        assert history[0]["role"] == "user"
    
    def test_add_assistant_message(self, temp_store):
        """Test adding an assistant message."""
        temp_store.add_assistant_message("session-1", "Hi there!")
        history = temp_store.get_chat_history("session-1")
        assert history[0]["role"] == "assistant"
    
    def test_persistence_across_instances(self, temp_store):
        """Test that sessions persist across store instances."""
        session_dir = temp_store.session_dir
        
        # Add messages with first store
        temp_store.add_user_message("session-1", "Hello")
        temp_store.add_assistant_message("session-1", "Hi!")
        
        # Create new store instance
        store2 = DefaultSessionStore(session_dir=session_dir)
        
        # Verify messages are restored
        history = store2.get_chat_history("session-1")
        assert len(history) == 2
        assert history[0]["content"] == "Hello"
        assert history[1]["content"] == "Hi!"
    
    def test_session_file_created(self, temp_store):
        """Test that session file is created on disk."""
        temp_store.add_user_message("test-session", "Hello")
        
        filepath = os.path.join(temp_store.session_dir, "test-session.json")
        assert os.path.exists(filepath)
        
        with open(filepath, "r") as f:
            data = json.load(f)
        assert data["session_id"] == "test-session"
        assert len(data["messages"]) == 1
    
    def test_max_messages_limit(self):
        """Test that messages are trimmed to max limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir, max_messages=5)
            
            for i in range(10):
                store.add_user_message("session-1", f"Message {i}")
            
            history = store.get_chat_history("session-1")
            assert len(history) == 5
            assert history[0]["content"] == "Message 5"
            assert history[4]["content"] == "Message 9"
    
    def test_clear_session(self, temp_store):
        """Test clearing a session."""
        temp_store.add_user_message("session-1", "Hello")
        temp_store.add_assistant_message("session-1", "Hi!")
        
        temp_store.clear_session("session-1")
        
        history = temp_store.get_chat_history("session-1")
        assert len(history) == 0
    
    def test_delete_session(self, temp_store):
        """Test deleting a session."""
        temp_store.add_user_message("session-1", "Hello")
        filepath = os.path.join(temp_store.session_dir, "session-1.json")
        assert os.path.exists(filepath)
        
        temp_store.delete_session("session-1")
        assert not os.path.exists(filepath)
    
    def test_list_sessions(self, temp_store):
        """Test listing sessions."""
        temp_store.add_user_message("session-1", "Hello")
        temp_store.add_user_message("session-2", "Hi")
        temp_store.add_user_message("session-3", "Hey")
        
        sessions = temp_store.list_sessions()
        assert len(sessions) == 3
        session_ids = [s["session_id"] for s in sessions]
        assert "session-1" in session_ids
        assert "session-2" in session_ids
        assert "session-3" in session_ids
    
    def test_session_exists(self, temp_store):
        """Test checking if session exists."""
        assert not temp_store.session_exists("session-1")
        
        temp_store.add_user_message("session-1", "Hello")
        assert temp_store.session_exists("session-1")
    
    def test_set_agent_info(self, temp_store):
        """Test setting agent info."""
        temp_store.add_user_message("session-1", "Hello")
        temp_store.set_agent_info("session-1", agent_name="TestBot", user_id="user-123")
        
        session = temp_store.get_session("session-1")
        assert session.agent_name == "TestBot"
        assert session.user_id == "user-123"
    
    def test_concurrent_writes(self, temp_store):
        """Test concurrent writes to same session."""
        def writer(msg_id):
            temp_store.add_user_message("session-1", f"Message {msg_id}")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(writer, i) for i in range(10)]
            for f in futures:
                f.result()
        
        history = temp_store.get_chat_history("session-1")
        assert len(history) == 10
    
    def test_sanitize_session_id(self, temp_store):
        """Test that session IDs are sanitized for filesystem."""
        temp_store.add_user_message("session/with/slashes", "Hello")
        temp_store.add_user_message("session:with:colons", "Hi")
        
        # Should not raise errors
        history1 = temp_store.get_chat_history("session/with/slashes")
        history2 = temp_store.get_chat_history("session:with:colons")
        assert len(history1) == 1
        assert len(history2) == 1
    
    def test_empty_session_returns_empty_history(self, temp_store):
        """Test that non-existent session returns empty history."""
        history = temp_store.get_chat_history("nonexistent")
        assert history == []
    
    def test_invalidate_cache(self, temp_store):
        """Test cache invalidation."""
        temp_store.add_user_message("session-1", "Hello")
        
        # Modify file directly
        filepath = os.path.join(temp_store.session_dir, "session-1.json")
        with open(filepath, "r") as f:
            data = json.load(f)
        data["messages"].append({"role": "user", "content": "Direct edit", "timestamp": time.time(), "metadata": {}})
        with open(filepath, "w") as f:
            json.dump(data, f)
        
        # Without invalidation, cache returns old data
        history = temp_store.get_chat_history("session-1")
        assert len(history) == 1  # Cached
        
        # After invalidation, new data is loaded
        temp_store.invalidate_cache("session-1")
        history = temp_store.get_chat_history("session-1")
        assert len(history) == 2


class TestAgentSessionIntegration:
    """Tests for Agent integration with session store."""
    
    def test_agent_session_persistence(self):
        """Test that Agent persists session with session_id."""
        from praisonaiagents import Agent
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch the default session directory
            import praisonaiagents.session.store as store_module
            original_dir = store_module.DEFAULT_SESSION_DIR
            store_module.DEFAULT_SESSION_DIR = tmpdir
            
            # Reset global store
            store_module._default_store = None
            
            try:
                # Create agent with session_id
                agent = Agent(
                    name="TestAgent",
                    instructions="You are a test agent.",
                    session_id="test-session-123",
                    verbose=False,
                )
                
                # Verify session store is initialized after first chat
                # (We can't actually call chat without API key, so we test init)
                agent._init_session_store()
                
                assert agent._session_store is not None
                assert agent._session_store_initialized is True
            finally:
                store_module.DEFAULT_SESSION_DIR = original_dir
                store_module._default_store = None
    
    def test_agent_no_session_id_no_persistence(self):
        """Test that Agent without session_id doesn't use session store."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="You are a test agent.",
            verbose=False,
        )
        
        agent._init_session_store()
        
        assert agent._session_store is None
        assert agent._session_store_initialized is True
    
    def test_agent_with_db_no_session_store(self):
        """Test that Agent with DB adapter doesn't use session store."""
        from praisonaiagents import Agent
        
        # Mock DB adapter
        class MockDbAdapter:
            def on_agent_start(self, **kwargs):
                return []
        
        agent = Agent(
            name="TestAgent",
            instructions="You are a test agent.",
            session_id="test-session",
            db=MockDbAdapter(),
            verbose=False,
        )
        
        agent._init_session_store()
        
        # Session store should not be used when DB is provided
        assert agent._session_store is None
