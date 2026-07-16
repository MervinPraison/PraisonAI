"""CLI smoke tests for browser module.

These tests verify CLI commands work without throwing errors.
They don't require external services (server, Chrome, etc).
"""

import pytest
from typer.testing import CliRunner
from unittest.mock import patch, Mock

from praisonai_browser.cli.commands.browser import app


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
        from praisonai_browser.sessions import SessionManager
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
    
    @patch('praisonai_browser.cli.commands.browser.doctor_flow')
    def test_doctor_runs(self, mock_doctor_flow):
        """Test doctor command runs without error."""
        mock_doctor_flow.return_value = None

        result = runner.invoke(app, ["doctor"])

        assert result.exit_code == 0
        mock_doctor_flow.assert_called_once()


class TestCLIDoctorExtension:
    """Test doctor extension bridge-vs-CDP split (issue #3098)."""

    def test_doctor_extension_help(self):
        """doctor extension help renders without error."""
        result = runner.invoke(app, ["doctor", "extension", "--help"])
        assert result.exit_code == 0

    @patch("requests.get")
    def test_doctor_extension_passes_when_bridge_connected(self, mock_get):
        """Passes on bridge connection even when CDP Chrome is empty."""
        def side_effect(url, *args, **kwargs):
            resp = Mock()
            if "/health" in url:
                resp.json.return_value = {"status": "ok", "connections": 1, "sessions": 0}
            else:
                resp.json.return_value = []  # No CDP targets (daily Work Chrome)
            return resp

        mock_get.side_effect = side_effect
        result = runner.invoke(app, ["doctor", "extension"])
        assert result.exit_code == 0
        assert "connected to bridge" in result.output

    @patch("requests.get")
    def test_doctor_extension_fails_when_no_bridge_connection(self, mock_get):
        """Fails when the extension is not connected to the bridge."""
        def side_effect(url, *args, **kwargs):
            resp = Mock()
            if "/health" in url:
                resp.json.return_value = {"status": "ok", "connections": 0, "sessions": 0}
            else:
                resp.json.return_value = []
            return resp

        mock_get.side_effect = side_effect
        result = runner.invoke(app, ["doctor", "extension"])
        assert result.exit_code == 1

    @patch("requests.get")
    def test_doctor_extension_uses_extension_specific_count(self, mock_get):
        """Prefers extension_connections over raw connections when present."""
        def side_effect(url, *args, **kwargs):
            resp = Mock()
            if "/health" in url:
                resp.json.return_value = {
                    "status": "ok",
                    "connections": 2,
                    "extension_connections": 1,
                    "sessions": 0,
                }
            else:
                resp.json.return_value = []
            return resp

        mock_get.side_effect = side_effect
        result = runner.invoke(app, ["doctor", "extension"])
        assert result.exit_code == 0
        assert "connected to bridge" in result.output

    @patch("requests.get")
    def test_doctor_extension_fails_when_only_cli_connected(self, mock_get):
        """A stray non-extension client must not pass the check (issue #3098 P1)."""
        def side_effect(url, *args, **kwargs):
            resp = Mock()
            if "/health" in url:
                resp.json.return_value = {
                    "status": "ok",
                    "connections": 1,
                    "extension_connections": 0,
                    "sessions": 0,
                }
            else:
                resp.json.return_value = []
            return resp

        mock_get.side_effect = side_effect
        result = runner.invoke(app, ["doctor", "extension"])
        assert result.exit_code == 1


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


class TestBridgeUnreachableError:
    """Test friendly bridge-not-running error handling."""

    def test_detects_connection_refused(self):
        """ConnectionRefusedError is recognised as bridge unreachable."""
        from praisonai_browser.cli.commands.browser import _is_bridge_unreachable
        assert _is_bridge_unreachable(ConnectionRefusedError()) is True

    def test_detects_winerror_1225(self):
        """Windows WinError 1225 is recognised as bridge unreachable."""
        from praisonai_browser.cli.commands.browser import _is_bridge_unreachable
        exc = OSError("refused")
        exc.winerror = 1225
        assert _is_bridge_unreachable(exc) is True

    def test_detects_posix_errno(self):
        """POSIX ECONNREFUSED (111/61) is recognised as bridge unreachable."""
        from praisonai_browser.cli.commands.browser import _is_bridge_unreachable
        for errno in (111, 61):
            exc = OSError()
            exc.errno = errno
            assert _is_bridge_unreachable(exc) is True

    def test_detects_wrapped_cause(self):
        """Detection follows the exception __cause__ chain."""
        from praisonai_browser.cli.commands.browser import _is_bridge_unreachable
        outer = RuntimeError("wrapper")
        outer.__cause__ = ConnectionRefusedError()
        assert _is_bridge_unreachable(outer) is True

    def test_ignores_unrelated_errors(self):
        """Unrelated errors are not misclassified as bridge unreachable."""
        from praisonai_browser.cli.commands.browser import _is_bridge_unreachable
        assert _is_bridge_unreachable(ValueError("boom")) is False

    def test_message_contains_actionable_hints(self):
        """The message names the bridge URL and the start command."""
        from praisonai_browser.cli.commands.browser import _bridge_unreachable_message
        msg = _bridge_unreachable_message(8765)
        assert "ws://localhost:8765/ws" in msg
        assert "praisonai browser start" in msg
        assert "/health" in msg


# Smoke tests - minimal checks that things don't crash

class TestSmokeImports:
    """Smoke tests for imports."""
    
    def test_import_sessions(self):
        """Test SessionManager can be imported."""
        from praisonai_browser.sessions import SessionManager
        assert SessionManager is not None
    
    def test_import_agent(self):
        """Test BrowserAgent can be imported."""
        from praisonai_browser.agent import BrowserAgent
        assert BrowserAgent is not None
    
    def test_import_server(self):
        """Test BrowserServer can be imported."""
        from praisonai_browser.server import BrowserServer
        assert BrowserServer is not None
    
    def test_import_cli(self):
        """Test CLI app can be imported."""
        from praisonai_browser.cli.commands.browser import app
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
            from praisonai_browser.sessions import SessionManager
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
            from praisonai_browser.sessions import SessionManager
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
        from praisonai_browser.agent import BrowserAgent
        
        # Should create without error (won't call LLM until used)
        agent = BrowserAgent(model="gpt-4o-mini")
        assert agent is not None
        assert agent.model == "gpt-4o-mini"
    
    def test_agent_with_session_id(self):
        """Test BrowserAgent with session_id."""
        from praisonai_browser.agent import BrowserAgent
        
        agent = BrowserAgent(
            model="gpt-4o-mini",
            session_id="test-session-123"
        )
        assert agent.session_id == "test-session-123"


class TestSmokeServer:
    """Smoke tests for BrowserServer."""
    
    def test_server_creation(self):
        """Test BrowserServer can be created."""
        from praisonai_browser.server import BrowserServer
        
        server = BrowserServer(port=8766, model="gpt-4o-mini")
        assert server is not None
        assert server.port == 8766
