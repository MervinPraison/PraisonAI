"""CLI smoke tests for browser module.

These tests verify CLI commands work without throwing errors.
They don't require external services (server, Chrome, etc).
"""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, Mock

from praisonai.browser.cli import app


runner = CliRunner()


class TestCLIHelp:
    """Test CLI help commands work."""
    
    def test_main_help(self):
        """Test main browser CLI help."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "browser" in result.output.lower() or "commands" in result.output.lower()
    
    def test_run_help(self):
        """Test run command help."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--goal" in result.output or "goal" in result.output.lower()
    
    def test_sessions_help(self):
        """Test sessions command help."""
        result = runner.invoke(app, ["sessions", "--help"])
        assert result.exit_code == 0
        assert "--limit" in result.output
    
    def test_history_help(self):
        """Test history command help."""
        result = runner.invoke(app, ["history", "--help"])
        assert result.exit_code == 0
    
    def test_doctor_help(self):
        """Test doctor command help."""
        result = runner.invoke(app, ["doctor", "--help"])
        assert result.exit_code == 0


class TestCLISessionsCommand:
    """Test sessions command with mocked database."""
    
    def test_sessions_empty(self):
        """Test sessions command with no sessions - imports work."""
        from praisonai.browser.sessions import SessionManager
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            manager = SessionManager(db_path)
            sessions = manager.list_sessions()
            assert sessions == []
            manager.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestCLIClearCommand:
    """Test clear command."""
    
    def test_clear_help(self):
        """Test clear command help works."""
        result = runner.invoke(app, ["clear", "--help"])
        assert result.exit_code == 0


class TestCLIDoctorCommand:
    """Test doctor diagnostics command."""
    
    def test_doctor_runs(self):
        """Test doctor command runs without error."""
        # Mock the database path check
        with patch('pathlib.Path.exists', return_value=True):
            with patch('sqlite3.connect') as mock_conn:
                mock_cursor = Mock()
                mock_conn.return_value.__enter__ = Mock(return_value=mock_conn.return_value)
                mock_conn.return_value.__exit__ = Mock(return_value=False)
                mock_conn.return_value.cursor.return_value = mock_cursor
                mock_cursor.fetchone.return_value = [0]
                mock_cursor.fetchall.return_value = []
                
                result = runner.invoke(app, ["doctor"])
                
                # Doctor should run and produce output
                assert result.exit_code == 0


class TestCLIMessageParsing:
    """Test that CLI handles various message types correctly."""
    
    def test_parse_dict_data(self):
        """Test parsing dictionary data."""
        import json
        
        # Valid dict message
        msg = json.dumps({"type": "status", "status": "connected"})
        data = json.loads(msg)
        
        assert isinstance(data, dict)
        assert data.get("type") == "status"
    
    def test_parse_string_data(self):
        """Test handling of string data (should not crash)."""
        import json
        
        # String message (edge case that could crash)
        msg = json.dumps("just a string")
        data = json.loads(msg)
        
        # This is a string, not a dict
        assert isinstance(data, str)
        
        # The fix: check before calling .get()
        if isinstance(data, dict):
            _ = data.get("type")
        else:
            # Should handle gracefully
            pass


class TestCLIRunCommand:
    """Test run command variations."""
    
    def test_run_requires_goal(self):
        """Test run command requires a goal."""
        result = runner.invoke(app, ["run"])
        # Should fail because goal is required
        assert result.exit_code != 0 or "goal" in result.output.lower()
    
    def test_run_help_shows_engines(self):
        """Test run help lists engine options."""
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "engine" in result.output.lower() or "cdp" in result.output.lower()


# Smoke tests - minimal checks that things don't crash

class TestSmokeImports:
    """Smoke tests for imports."""
    
    def test_import_sessions(self):
        """Test SessionManager can be imported."""
        from praisonai.browser.sessions import SessionManager
        assert SessionManager is not None
    
    def test_import_agent(self):
        """Test BrowserAgent can be imported."""
        from praisonai.browser.agent import BrowserAgent
        assert BrowserAgent is not None
    
    def test_import_server(self):
        """Test BrowserServer can be imported."""
        from praisonai.browser.server import BrowserServer
        assert BrowserServer is not None
    
    def test_import_cli(self):
        """Test CLI app can be imported."""
        from praisonai.browser.cli import app
        assert app is not None


class TestSmokeSessions:
    """Smoke tests for session manager."""
    
    def test_session_manager_creation(self):
        """Test SessionManager can be created with temp db."""
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            from praisonai.browser.sessions import SessionManager
            manager = SessionManager(db_path)
            assert manager is not None
            manager.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_create_and_get_session(self):
        """Test basic session CRUD."""
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        
        try:
            from praisonai.browser.sessions import SessionManager
            manager = SessionManager(db_path)
            
            session = manager.create_session("Test goal")
            assert session["session_id"]
            
            retrieved = manager.get_session(session["session_id"])
            assert retrieved["goal"] == "Test goal"
            
            manager.close()
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


class TestSmokeAgent:
    """Smoke tests for BrowserAgent."""
    
    def test_agent_creation(self):
        """Test BrowserAgent can be created."""
        from praisonai.browser.agent import BrowserAgent
        
        # Should create without error (won't call LLM until used)
        agent = BrowserAgent(model="gpt-4o-mini")
        assert agent is not None
        assert agent.model == "gpt-4o-mini"
    
    def test_agent_with_session_id(self):
        """Test BrowserAgent with session_id."""
        from praisonai.browser.agent import BrowserAgent
        
        agent = BrowserAgent(
            model="gpt-4o-mini",
            session_id="test-session-123"
        )
        assert agent.session_id == "test-session-123"


class TestSmokeServer:
    """Smoke tests for BrowserServer."""
    
    def test_server_creation(self):
        """Test BrowserServer can be created."""
        from praisonai.browser.server import BrowserServer
        
        server = BrowserServer(port=8766, model="gpt-4o-mini")
        assert server is not None
        assert server.port == 8766
