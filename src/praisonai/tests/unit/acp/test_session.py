"""Unit tests for ACP session management."""

import tempfile
import time
from pathlib import Path

from praisonai.acp.session import ACPSession, SessionStore


class TestACPSession:
    """Tests for ACPSession class."""
    
    def test_create_session(self):
        """Test session creation."""
        session = ACPSession.create(
            workspace=Path("/tmp/test"),
            agent_id="test_agent",
        )
        
        assert session.session_id.startswith("sess_")
        assert session.workspace == Path("/tmp/test")
        assert session.agent_id == "test_agent"
        assert session.run_id is not None
        assert session.trace_id is not None
        assert session.mode == "manual"
    
    def test_update_activity(self):
        """Test activity timestamp update."""
        session = ACPSession.create(workspace=Path("/tmp"))
        original_time = session.last_activity
        
        time.sleep(0.01)
        session.update_activity()
        
        assert session.last_activity > original_time
    
    def test_add_message(self):
        """Test adding messages to session."""
        session = ACPSession.create(workspace=Path("/tmp"))
        
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!")
        
        assert len(session.messages) == 2
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "Hello"
        assert session.messages[1]["role"] == "assistant"
        assert session.messages[1]["content"] == "Hi there!"
    
    def test_add_tool_call(self):
        """Test adding tool calls to session."""
        session = ACPSession.create(workspace=Path("/tmp"))
        
        session.add_tool_call(
            tool_call_id="call_001",
            title="Read file",
            status="completed",
            path="/tmp/test.txt",
        )
        
        assert len(session.tool_calls) == 1
        assert session.tool_calls[0]["tool_call_id"] == "call_001"
        assert session.tool_calls[0]["title"] == "Read file"
        assert session.tool_calls[0]["status"] == "completed"
        assert session.tool_calls[0]["path"] == "/tmp/test.txt"
    
    def test_to_dict(self):
        """Test session serialization."""
        session = ACPSession.create(
            workspace=Path("/tmp/test"),
            agent_id="test_agent",
        )
        session.add_message("user", "Test message")
        
        data = session.to_dict()
        
        assert data["session_id"] == session.session_id
        assert data["workspace"] == "/tmp/test"
        assert data["agent_id"] == "test_agent"
        assert len(data["messages"]) == 1
    
    def test_from_dict(self):
        """Test session deserialization."""
        data = {
            "session_id": "sess_test123",
            "workspace": "/tmp/test",
            "created_at": 1234567890.0,
            "last_activity": 1234567891.0,
            "agent_id": "test_agent",
            "run_id": "run_abc",
            "trace_id": "trace_xyz",
            "mode": "auto",
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "tool_calls": [],
            "mcp_servers": [],
        }
        
        session = ACPSession.from_dict(data)
        
        assert session.session_id == "sess_test123"
        assert session.workspace == Path("/tmp/test")
        assert session.agent_id == "test_agent"
        assert session.mode == "auto"
        assert session.model == "gpt-4"
        assert len(session.messages) == 1


class TestSessionStore:
    """Tests for SessionStore class."""
    
    def test_save_and_load(self):
        """Test saving and loading sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(storage_dir=Path(tmpdir))
            
            session = ACPSession.create(workspace=Path("/tmp/test"))
            session.add_message("user", "Test")
            
            store.save(session)
            
            loaded = store.load(session.session_id)
            
            assert loaded is not None
            assert loaded.session_id == session.session_id
            assert len(loaded.messages) == 1
    
    def test_load_nonexistent(self):
        """Test loading non-existent session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(storage_dir=Path(tmpdir))
            
            loaded = store.load("nonexistent_session")
            
            assert loaded is None
    
    def test_load_last(self):
        """Test loading the last session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(storage_dir=Path(tmpdir))
            
            # Create and save multiple sessions
            session1 = ACPSession.create(workspace=Path("/tmp/test1"))
            store.save(session1)
            
            session2 = ACPSession.create(workspace=Path("/tmp/test2"))
            store.save(session2)
            
            # Last saved should be session2
            last = store.load_last()
            
            assert last is not None
            assert last.session_id == session2.session_id
    
    def test_delete(self):
        """Test deleting a session."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(storage_dir=Path(tmpdir))
            
            session = ACPSession.create(workspace=Path("/tmp/test"))
            store.save(session)
            
            # Verify it exists
            assert store.load(session.session_id) is not None
            
            # Delete it
            result = store.delete(session.session_id)
            assert result is True
            
            # Verify it's gone
            assert store.load(session.session_id) is None
    
    def test_list_sessions(self):
        """Test listing sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(storage_dir=Path(tmpdir))
            
            # Create multiple sessions
            for i in range(3):
                session = ACPSession.create(workspace=Path(f"/tmp/test{i}"))
                store.save(session)
                time.sleep(0.01)  # Ensure different timestamps
            
            sessions = store.list_sessions()
            
            assert len(sessions) == 3
            # Should be sorted by last_activity, most recent first
            assert sessions[0].last_activity >= sessions[1].last_activity
            assert sessions[1].last_activity >= sessions[2].last_activity
    
    def test_list_sessions_limit(self):
        """Test listing sessions with limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(storage_dir=Path(tmpdir))
            
            # Create multiple sessions
            for i in range(5):
                session = ACPSession.create(workspace=Path(f"/tmp/test{i}"))
                store.save(session)
            
            sessions = store.list_sessions(limit=2)
            
            assert len(sessions) == 2
