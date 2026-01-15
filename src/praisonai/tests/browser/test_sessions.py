"""Tests for browser session management."""

import pytest
import os
import tempfile
import time

from praisonai.browser.sessions import SessionManager


@pytest.fixture
def session_manager():
    """Create a session manager with temp database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    manager = SessionManager(db_path)
    yield manager
    
    manager.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestSessionManager:
    """Tests for SessionManager class."""
    
    def test_create_session(self, session_manager):
        """Test creating a new session."""
        session = session_manager.create_session("Find restaurants in NYC")
        
        assert "session_id" in session
        assert len(session["session_id"]) == 36  # UUID length
        assert session["goal"] == "Find restaurants in NYC"
        assert session["status"] == "running"
        assert session["started_at"] > 0
    
    def test_get_session(self, session_manager):
        """Test retrieving a session by ID."""
        created = session_manager.create_session("Test goal")
        session_id = created["session_id"]
        
        retrieved = session_manager.get_session(session_id)
        
        assert retrieved is not None
        assert retrieved["session_id"] == session_id
        assert retrieved["goal"] == "Test goal"
        assert retrieved["steps"] == []
    
    def test_get_nonexistent_session(self, session_manager):
        """Test retrieving a session that doesn't exist."""
        result = session_manager.get_session("nonexistent-id")
        assert result is None
    
    def test_update_session_status(self, session_manager):
        """Test updating session status."""
        session = session_manager.create_session("Test")
        session_id = session["session_id"]
        
        session_manager.update_session(session_id, status="completed")
        
        updated = session_manager.get_session(session_id)
        assert updated["status"] == "completed"
        assert updated["ended_at"] is not None
    
    def test_update_session_url(self, session_manager):
        """Test updating current URL."""
        session = session_manager.create_session("Test")
        session_id = session["session_id"]
        
        session_manager.update_session(session_id, current_url="https://example.com")
        
        updated = session_manager.get_session(session_id)
        assert updated["current_url"] == "https://example.com"
    
    def test_update_session_error(self, session_manager):
        """Test updating session with error."""
        session = session_manager.create_session("Test")
        session_id = session["session_id"]
        
        session_manager.update_session(
            session_id,
            status="failed",
            error="Connection timeout"
        )
        
        updated = session_manager.get_session(session_id)
        assert updated["status"] == "failed"
        assert updated["error"] == "Connection timeout"
    
    def test_add_step(self, session_manager):
        """Test adding steps to a session."""
        session = session_manager.create_session("Test")
        session_id = session["session_id"]
        
        observation = {"url": "https://example.com", "title": "Example"}
        action = {"action": "click", "selector": "#btn"}
        
        session_manager.add_step(
            session_id,
            step_number=1,
            observation=observation,
            action=action,
            thought="Clicking the button"
        )
        
        retrieved = session_manager.get_session(session_id)
        assert len(retrieved["steps"]) == 1
        
        step = retrieved["steps"][0]
        assert step["step_number"] == 1
        assert step["observation"] == observation
        assert step["action"] == action
        assert step["thought"] == "Clicking the button"
    
    def test_add_multiple_steps(self, session_manager):
        """Test adding multiple steps."""
        session = session_manager.create_session("Test")
        session_id = session["session_id"]
        
        for i in range(1, 4):
            session_manager.add_step(
                session_id,
                step_number=i,
                action={"action": "click", "step": i}
            )
        
        retrieved = session_manager.get_session(session_id)
        assert len(retrieved["steps"]) == 3
        assert retrieved["steps"][0]["step_number"] == 1
        assert retrieved["steps"][2]["step_number"] == 3
    
    def test_list_sessions(self, session_manager):
        """Test listing all sessions."""
        session_manager.create_session("Goal 1")
        session_manager.create_session("Goal 2")
        session_manager.create_session("Goal 3")
        
        sessions = session_manager.list_sessions()
        
        assert len(sessions) == 3
    
    def test_list_sessions_by_status(self, session_manager):
        """Test filtering sessions by status."""
        s1 = session_manager.create_session("Goal 1")
        s2 = session_manager.create_session("Goal 2")
        session_manager.create_session("Goal 3")
        
        session_manager.update_session(s1["session_id"], status="completed")
        session_manager.update_session(s2["session_id"], status="completed")
        
        running = session_manager.list_sessions(status="running")
        completed = session_manager.list_sessions(status="completed")
        
        assert len(running) == 1
        assert len(completed) == 2
    
    def test_list_sessions_limit(self, session_manager):
        """Test limiting session list."""
        for i in range(10):
            session_manager.create_session(f"Goal {i}")
        
        sessions = session_manager.list_sessions(limit=5)
        
        assert len(sessions) == 5
    
    def test_delete_session(self, session_manager):
        """Test deleting a session."""
        session = session_manager.create_session("Test")
        session_id = session["session_id"]
        
        # Add a step
        session_manager.add_step(session_id, 1, action={"action": "click"})
        
        # Delete
        result = session_manager.delete_session(session_id)
        
        assert result is True
        assert session_manager.get_session(session_id) is None
    
    def test_delete_nonexistent_session(self, session_manager):
        """Test deleting a session that doesn't exist."""
        result = session_manager.delete_session("nonexistent-id")
        assert result is False
    
    def test_session_metadata(self, session_manager):
        """Test session with custom metadata."""
        session = session_manager.create_session(
            "Test",
            metadata={"model": "gpt-4o", "max_steps": 20}
        )
        
        assert "session_id" in session


class TestSessionManagerThreadSafety:
    """Tests for thread safety of SessionManager."""
    
    def test_multiple_connections(self):
        """Test that multiple instances can access same DB."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            manager1 = SessionManager(db_path)
            manager2 = SessionManager(db_path)
            
            session = manager1.create_session("Test")
            session_id = session["session_id"]
            
            # Should be visible in manager2
            retrieved = manager2.get_session(session_id)
            assert retrieved is not None
            
            manager1.close()
            manager2.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
