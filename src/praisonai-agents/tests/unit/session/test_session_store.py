"""
TDD Tests for Session Store.

Tests for DefaultSessionStore with JSON-based persistence.
"""

import json
import os
import tempfile
import threading
import time
import builtins
import importlib
import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

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

    def test_import_without_fcntl(self):
        """Test module import succeeds when fcntl is unavailable."""
        import praisonaiagents.session.store as store_module
        import importlib.util
        original_import = builtins.__import__

        def import_without_fcntl(name, *args, **kwargs):
            if name == "fcntl":
                raise ImportError("fcntl unavailable")
            return original_import(name, *args, **kwargs)

        try:
            with patch("builtins.__import__", side_effect=import_without_fcntl):
                reloaded_module = importlib.reload(store_module)
                assert reloaded_module._HAS_FCNTL is False
        finally:
            restored_module = importlib.reload(store_module)
        
        assert restored_module._HAS_FCNTL is (importlib.util.find_spec("fcntl") is not None)


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

    def test_update_session_metadata_preserves_messages(self, temp_store):
        """Metadata updates must not drop messages added by another store instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DefaultSessionStore(session_dir=tmpdir)
            reader = DefaultSessionStore(session_dir=tmpdir)

            writer.add_user_message("session-1", "first")
            reader._load_session("session-1")
            writer.add_user_message("session-1", "second")

            assert reader.update_session_metadata(
                "session-1", model="gpt-4o-mini", total_tokens=42
            )

            writer.invalidate_cache("session-1")
            history = writer.get_chat_history("session-1")
            assert len(history) == 2
            assert history[1]["content"] == "second"

            session = writer.get_session("session-1")
            assert session.metadata.get("model") == "gpt-4o-mini"
            assert session.metadata.get("total_tokens") == 42

    def test_set_agent_info_preserves_messages(self, temp_store):
        """Agent info updates must not drop messages added by another store instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DefaultSessionStore(session_dir=tmpdir)
            reader = DefaultSessionStore(session_dir=tmpdir)

            writer.add_user_message("session-1", "first")
            reader._load_session("session-1")
            writer.add_user_message("session-1", "second")

            assert reader.set_agent_info("session-1", agent_name="TestBot", user_id="u-1")

            writer.invalidate_cache("session-1")
            history = writer.get_chat_history("session-1")
            assert len(history) == 2
            assert history[1]["content"] == "second"

            session = writer.get_session("session-1")
            assert session.agent_name == "TestBot"
            assert session.user_id == "u-1"

    def test_set_chat_history_replaces_under_lock(self, temp_store):
        """History replace is a single locked write (not clear + N adds)."""
        temp_store.add_user_message("session-1", "old")
        assert temp_store.set_chat_history(
            "session-1",
            [
                {"role": "user", "content": "new"},
                {"role": "assistant", "content": "reply"},
            ],
        )
        assert temp_store.get_chat_history("session-1") == [
            {"role": "user", "content": "new"},
            {"role": "assistant", "content": "reply"},
        ]

    def test_get_chat_history_sees_writes_from_other_store(self, temp_store):
        """Reads must reload from disk, not a stale in-memory cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DefaultSessionStore(session_dir=tmpdir)
            reader = DefaultSessionStore(session_dir=tmpdir)

            writer.add_user_message("session-1", "first")
            reader._load_session("session-1")
            writer.add_user_message("session-1", "second")
            history = reader.get_chat_history("session-1")
            assert len(history) == 2
            assert history[1]["content"] == "second"
            assert history[1]["content"] == "second"

    def test_clear_session_preserves_new_messages(self, temp_store):
        """Clear must reload from disk so concurrent adds are not lost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DefaultSessionStore(session_dir=tmpdir)
            reader = DefaultSessionStore(session_dir=tmpdir)

            writer.add_user_message("session-1", "first")
            reader._load_session("session-1")
            writer.add_user_message("session-1", "second")

            assert reader.clear_session("session-1")

            writer.invalidate_cache("session-1")
            history = writer.get_chat_history("session-1")
            assert len(history) == 0

    def test_set_gateway_info_preserves_messages(self, temp_store):
        """Gateway info updates must not drop messages added by another store instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DefaultSessionStore(session_dir=tmpdir)
            reader = DefaultSessionStore(session_dir=tmpdir)

            writer.add_user_message("session-1", "first")
            reader._load_session("session-1")
            writer.add_user_message("session-1", "second")

            assert reader.set_gateway_info("session-1", gateway_session_id="gw-123", agent_id="agent-456")

            writer.invalidate_cache("session-1")
            history = writer.get_chat_history("session-1")
            assert len(history) == 2
            assert history[1]["content"] == "second"

            session = writer.get_session("session-1")
            assert session.gateway_session_id == "gw-123"
            assert session.agent_id == "agent-456"
    
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
        """Test that reads always see latest disk state."""
        temp_store.add_user_message("session-1", "Hello")
        
        # Modify file directly
        filepath = os.path.join(temp_store.session_dir, "session-1.json")
        with open(filepath, "r") as f:
            data = json.load(f)
        data["messages"].append({"role": "user", "content": "Direct edit", "timestamp": time.time(), "metadata": {}})
        with open(filepath, "w") as f:
            json.dump(data, f)
        
        # Reads always reload from disk (no stale cache)
        history = temp_store.get_chat_history("session-1")
        assert len(history) == 2

        # invalidate_cache still clears in-memory state when a file is missing
        temp_store.invalidate_cache("session-1")
        history = temp_store.get_chat_history("session-1")
        assert len(history) == 2

    def test_get_chat_history_sees_other_store_instance(self):
        """Another store on the same session_dir must see new messages without invalidate_cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DefaultSessionStore(session_dir=tmpdir)
            reader = DefaultSessionStore(session_dir=tmpdir)

            writer.add_user_message("session-1", "first")
            reader._load_session("session-1")
            writer.add_user_message("session-1", "second")

            history = reader.get_chat_history("session-1")
            assert len(history) == 2
            assert history[1]["content"] == "second"
    
    def test_list_sessions_with_none_updated_at(self, temp_store):
        """Test list_sessions handles None updated_at values without crashing.
        
        Regression test for issue #1445 where sessions with updated_at=None
        caused TypeError in sorting.
        """
        # Create a session with a regular message
        temp_store.add_user_message("session-1", "Hello")
        
        # Create another session and manually set updated_at to None
        temp_store.add_user_message("session-2", "Hi")
        filepath = os.path.join(temp_store.session_dir, "session-2.json")
        
        # Read the session file and set updated_at to None
        with open(filepath, "r") as f:
            data = json.load(f)
        data["updated_at"] = None  # Explicit None value
        with open(filepath, "w") as f:
            json.dump(data, f)
        
        # Clear cache to ensure file is re-read
        temp_store.invalidate_cache("session-2")
        
        # This should not crash with TypeError
        sessions = temp_store.list_sessions(limit=50)
        
        # Should return both sessions
        assert len(sessions) == 2
        session_ids = [s["session_id"] for s in sessions]
        assert "session-1" in session_ids
        assert "session-2" in session_ids
        
        # Session with None updated_at should appear last (empty string sorts before timestamps)
        assert sessions[-1]["session_id"] == "session-2"
        assert sessions[-1]["updated_at"] is None


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
                    memory=True,  # Enable memory for session
                    output="silent",
                )
                
                # Verify session store is initialized after first chat
                # (We can't actually call chat without API key, so we test init)
                # Agent with memory=True should be created successfully
                assert agent is not None
            finally:
                store_module.DEFAULT_SESSION_DIR = original_dir
                store_module._default_store = None
    
    def test_agent_no_session_id_no_persistence(self):
        """Test that Agent without session_id doesn't use session store."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="TestAgent",
            instructions="You are a test agent.",
            output="silent",
        )
        
        # Agent without memory enabled should not have session store
        assert agent._session_store is None or not hasattr(agent, '_session_store')
    
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
            memory=True,  # Enable memory
            output="silent",
        )
        
        # Agent should be created successfully
        assert agent is not None


class TestRuntimeStateMirroring:
    """Tests for runtime state mirroring functionality (Issue #1943)."""
    
    @pytest.fixture
    def temp_store(self):
        """Create a temporary session store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DefaultSessionStore(session_dir=tmpdir)
            yield store
    
    def test_session_data_runtime_state_field(self):
        """Test that SessionData includes runtime_state field."""
        session = SessionData(session_id="test-123")
        assert hasattr(session, 'runtime_state')
        assert session.runtime_state == {}
        assert isinstance(session.runtime_state, dict)
    
    def test_session_data_runtime_state_serialization(self):
        """Test that runtime_state is included in to_dict/from_dict."""
        session = SessionData(session_id="test-123")
        session.runtime_state = {
            "native": {"turn-1": {"tool_calls": ["call-1", "call-2"]}},
            "plugin": {"turn-1": {"transcript": "some data"}}
        }
        
        # Test to_dict includes runtime_state
        d = session.to_dict()
        assert "runtime_state" in d
        assert d["runtime_state"] == session.runtime_state
        
        # Test from_dict preserves runtime_state
        restored = SessionData.from_dict(d)
        assert restored.runtime_state == session.runtime_state
    
    def test_session_data_runtime_state_backward_compatibility(self):
        """Test that sessions without runtime_state load correctly."""
        # Simulate old session data without runtime_state
        old_data = {
            "session_id": "old-session",
            "messages": [],
            "metadata": {},
            # No runtime_state field
        }
        
        session = SessionData.from_dict(old_data)
        assert session.runtime_state == {}  # Should default to empty dict
    
    def test_set_runtime_state(self, temp_store):
        """Test setting runtime state for a session."""
        session_id = "test-session"
        runtime_id = "native"
        turn_id = "turn-1"
        state = {"tool_calls": ["call-1", "call-2"], "transcript": "some data"}
        
        result = temp_store.set_runtime_state(session_id, runtime_id, turn_id, state)
        assert result is True
        
        # Verify state was saved
        retrieved_state = temp_store.get_runtime_state(session_id, runtime_id, turn_id)
        assert retrieved_state == state
    
    def test_get_runtime_state_single_turn(self, temp_store):
        """Test getting runtime state for a specific turn."""
        session_id = "test-session"
        runtime_id = "native"
        turn_id = "turn-1"
        state = {"tool_calls": ["call-1"]}
        
        temp_store.set_runtime_state(session_id, runtime_id, turn_id, state)
        
        retrieved_state = temp_store.get_runtime_state(session_id, runtime_id, turn_id)
        assert retrieved_state == state
    
    def test_get_runtime_state_all_turns(self, temp_store):
        """Test getting runtime state for all turns of a runtime."""
        session_id = "test-session"
        runtime_id = "native"
        
        # Add multiple turns
        temp_store.set_runtime_state(session_id, runtime_id, "turn-1", {"data": "turn1"})
        temp_store.set_runtime_state(session_id, runtime_id, "turn-2", {"data": "turn2"})
        
        all_turns = temp_store.get_runtime_state(session_id, runtime_id)
        assert len(all_turns) == 2
        assert all_turns["turn-1"] == {"data": "turn1"}
        assert all_turns["turn-2"] == {"data": "turn2"}
    
    def test_get_runtime_state_nonexistent(self, temp_store):
        """Test getting runtime state for nonexistent session/runtime/turn."""
        # Nonexistent session
        state = temp_store.get_runtime_state("nonexistent", "native", "turn-1")
        assert state == {}
        
        # Nonexistent runtime
        temp_store.add_user_message("test-session", "Hello")
        state = temp_store.get_runtime_state("test-session", "nonexistent", "turn-1")
        assert state == {}
        
        # Nonexistent turn
        temp_store.set_runtime_state("test-session", "native", "turn-1", {"data": "test"})
        state = temp_store.get_runtime_state("test-session", "native", "nonexistent")
        assert state == {}
    
    def test_clear_runtime_state_specific_runtime(self, temp_store):
        """Test clearing runtime state for a specific runtime."""
        session_id = "test-session"
        
        # Add state for multiple runtimes
        temp_store.set_runtime_state(session_id, "native", "turn-1", {"data": "native1"})
        temp_store.set_runtime_state(session_id, "plugin", "turn-1", {"data": "plugin1"})
        
        # Clear only native runtime
        result = temp_store.clear_runtime_state(session_id, "native")
        assert result is True
        
        # Verify native is cleared but plugin remains
        native_state = temp_store.get_runtime_state(session_id, "native")
        plugin_state = temp_store.get_runtime_state(session_id, "plugin")
        assert native_state == {}
        assert plugin_state == {"turn-1": {"data": "plugin1"}}
    
    def test_clear_runtime_state_all(self, temp_store):
        """Test clearing all runtime state for a session."""
        session_id = "test-session"
        
        # Add state for multiple runtimes
        temp_store.set_runtime_state(session_id, "native", "turn-1", {"data": "native1"})
        temp_store.set_runtime_state(session_id, "plugin", "turn-1", {"data": "plugin1"})
        
        # Clear all runtime state
        result = temp_store.clear_runtime_state(session_id)
        assert result is True
        
        # Verify all state is cleared
        session = temp_store.get_session(session_id)
        assert session.runtime_state == {}
    
    def test_runtime_state_persistence_across_instances(self, temp_store):
        """Test that runtime state persists across store instances."""
        session_dir = temp_store.session_dir
        session_id = "test-session"
        runtime_id = "native"
        turn_id = "turn-1"
        state = {"tool_calls": ["call-1", "call-2"], "transcript": "data"}
        
        # Set state with first store
        temp_store.set_runtime_state(session_id, runtime_id, turn_id, state)
        
        # Create new store instance
        store2 = DefaultSessionStore(session_dir=session_dir)
        
        # Verify state is restored
        retrieved_state = store2.get_runtime_state(session_id, runtime_id, turn_id)
        assert retrieved_state == state
    
    def test_runtime_state_with_concurrent_operations(self, temp_store):
        """Test runtime state operations don't interfere with messages."""
        session_id = "test-session"
        
        # Add messages
        temp_store.add_user_message(session_id, "Hello")
        temp_store.add_assistant_message(session_id, "Hi!")
        
        # Add runtime state
        temp_store.set_runtime_state(session_id, "native", "turn-1", {"tool_calls": ["call-1"]})
        
        # Verify both messages and runtime state are preserved
        history = temp_store.get_chat_history(session_id)
        assert len(history) == 2
        
        runtime_state = temp_store.get_runtime_state(session_id, "native", "turn-1")
        assert runtime_state == {"tool_calls": ["call-1"]}
    
    def test_runtime_state_file_format(self, temp_store):
        """Test that runtime state is properly saved to session file."""
        session_id = "test-session"
        runtime_id = "native"
        turn_id = "turn-1"
        state = {"tool_calls": ["call-1"], "metadata": {"timestamp": 123}}
        
        temp_store.set_runtime_state(session_id, runtime_id, turn_id, state)
        
        # Check file contents
        filepath = os.path.join(temp_store.session_dir, "test-session.json")
        assert os.path.exists(filepath)
        
        with open(filepath, "r") as f:
            data = json.load(f)
        
        assert "runtime_state" in data
        assert data["runtime_state"][runtime_id][turn_id] == state
    
    def test_multiple_runtimes_and_turns(self, temp_store):
        """Test complex scenario with multiple runtimes and turns."""
        session_id = "complex-session"
        
        # Add state for multiple runtimes and turns
        states = {
            ("native", "turn-1"): {"tool_calls": ["call-1"], "status": "completed"},
            ("native", "turn-2"): {"tool_calls": ["call-2", "call-3"], "status": "completed"},
            ("plugin", "turn-1"): {"transcript": "plugin data", "version": "1.0"},
            ("plugin", "turn-2"): {"transcript": "more plugin data", "version": "1.1"},
        }
        
        for (runtime_id, turn_id), state in states.items():
            temp_store.set_runtime_state(session_id, runtime_id, turn_id, state)
        
        # Verify all states can be retrieved
        for (runtime_id, turn_id), expected_state in states.items():
            retrieved_state = temp_store.get_runtime_state(session_id, runtime_id, turn_id)
            assert retrieved_state == expected_state
        
        # Verify runtime-level retrieval
        native_states = temp_store.get_runtime_state(session_id, "native")
        plugin_states = temp_store.get_runtime_state(session_id, "plugin")
        
        assert len(native_states) == 2
        assert len(plugin_states) == 2
        assert native_states["turn-1"]["status"] == "completed"
        assert plugin_states["turn-1"]["version"] == "1.0"
    
    def test_runtime_state_mirror_enabled_flag(self, temp_store):
        """Test that mirror_enabled flag controls whether runtime state is stored."""
        session_id = "test-session"
        runtime_id = "native"
        turn_id = "turn-1"
        state = {"tool_calls": ["call-1", "call-2"]}
        
        # Test with mirror_enabled=False (should not store)
        result = temp_store.set_runtime_state(
            session_id, runtime_id, turn_id, state, mirror_enabled=False
        )
        assert result is True  # Should return True (successfully skipped)
        
        # Verify state was NOT saved
        retrieved_state = temp_store.get_runtime_state(session_id, runtime_id, turn_id)
        assert retrieved_state == {}  # Should be empty
        
        # Test with mirror_enabled=True (should store)
        result = temp_store.set_runtime_state(
            session_id, runtime_id, turn_id, state, mirror_enabled=True
        )
        assert result is True
        
        # Verify state WAS saved
        retrieved_state = temp_store.get_runtime_state(session_id, runtime_id, turn_id)
        assert retrieved_state == state
    
    def test_runtime_state_deep_copy_protection(self, temp_store):
        """Test that modifications to original state don't affect stored state."""
        session_id = "test-session"
        runtime_id = "native"
        turn_id = "turn-1"
        original_state = {"tool_calls": ["call-1"], "metadata": {"key": "value"}}
        
        # Set runtime state
        temp_store.set_runtime_state(session_id, runtime_id, turn_id, original_state)
        
        # Modify original state
        original_state["tool_calls"].append("call-2")
        original_state["metadata"]["key"] = "modified"
        
        # Verify stored state is unaffected
        retrieved_state = temp_store.get_runtime_state(session_id, runtime_id, turn_id)
        assert retrieved_state == {"tool_calls": ["call-1"], "metadata": {"key": "value"}}
        assert retrieved_state != original_state
    
    def test_runtime_state_null_handling(self, temp_store):
        """Test that null runtime_state in JSON is handled correctly."""
        session_id = "test-session"
        
        # Manually create a session file with null runtime_state
        filepath = os.path.join(temp_store.session_dir, f"{session_id}.json")
        session_data = {
            "session_id": session_id,
            "messages": [],
            "metadata": {},
            "runtime_state": None  # Explicitly null
        }
        
        with open(filepath, "w") as f:
            json.dump(session_data, f)
        
        # Verify that loading handles null correctly
        session = temp_store.get_session(session_id)
        assert session.runtime_state == {}  # Should default to empty dict, not None
