"""
Unit tests for Langfuse CLI commands (traces, sessions, show).

Tests verify:
1. Langfuse API client fetches traces correctly
2. CLI traces command displays traces in table format
3. CLI sessions command displays sessions
4. CLI show command displays trace details
5. Commands handle API errors gracefully
6. Commands respect configuration from ~/.praisonai/langfuse.env
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

# Import the langfuse CLI app
from praisonai.cli.commands.langfuse import app

runner = CliRunner()


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def mock_langfuse_env(tmp_path):
    """Create a mock langfuse.env file for testing."""
    env_file = tmp_path / "langfuse.env"
    env_content = """# Langfuse Configuration
LANGFUSE_PUBLIC_KEY=pk-test-12345
LANGFUSE_SECRET_KEY=sk-test-67890
LANGFUSE_HOST=http://localhost:3000
"""
    env_file.write_text(env_content)
    return env_file


@pytest.fixture
def sample_traces():
    """Return sample trace data from Langfuse API."""
    return {
        "data": [
            {
                "id": "trace-001",
                "name": "TestAgent",
                "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
                "sessionId": "session-abc",
                "userId": "user-123",
                "metadata": {"test": True},
                "observations": [],
                "scores": []
            },
            {
                "id": "trace-002",
                "name": "TestAgent",
                "timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(),
                "sessionId": "session-abc",
                "userId": "user-123",
                "metadata": {},
                "observations": []
            },
            {
                "id": "trace-003",
                "name": "AnotherAgent",
                "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(),
                "sessionId": "session-def",
                "userId": "user-456",
                "metadata": {},
                "observations": []
            }
        ],
        "meta": {"page": 1, "limit": 20, "totalCount": 3}
    }


@pytest.fixture
def sample_sessions():
    """Return sample session data from Langfuse API."""
    return {
        "data": [
            {
                "id": "session-abc",
                "createdAt": (datetime.now() - timedelta(hours=2)).isoformat(),
                "traceCount": 2,
                "traces": [{"id": "trace-001"}, {"id": "trace-002"}]
            },
            {
                "id": "session-def",
                "createdAt": (datetime.now() - timedelta(days=1)).isoformat(),
                "traceCount": 1,
                "traces": [{"id": "trace-003"}]
            }
        ],
        "meta": {"page": 1, "limit": 20, "totalCount": 2}
    }


@pytest.fixture
def sample_trace_detail():
    """Return detailed trace data."""
    return {
        "id": "trace-001",
        "name": "TestAgent",
        "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
        "sessionId": "session-abc",
        "userId": "user-123",
        "metadata": {"test": True, "cli": True},
        "input": {"prompt": "Say hello"},
        "output": {"response": "Hello! How can I help you today?"},
        "observations": [
            {
                "id": "obs-1",
                "type": "span",
                "name": "llm-call",
                "startTime": (datetime.now() - timedelta(minutes=5, seconds=2)).isoformat(),
                "endTime": (datetime.now() - timedelta(minutes=5)).isoformat(),
                "level": "DEFAULT",
                "statusMessage": None
            }
        ],
        "scores": []
    }


# -----------------------------------------------------------------------------
# Langfuse API Client Tests
# -----------------------------------------------------------------------------

class TestLangfuseAPIClient:
    """Tests for the Langfuse API client module."""
    
    @patch("praisonai.cli.langfuse_client.requests.get")
    def test_fetch_traces_success(self, mock_get, sample_traces):
        """Test successful trace fetching."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: sample_traces,
            raise_for_status=lambda: None
        )
        
        # Import the client module (to be created)
        from praisonai.cli.langfuse_client import LangfuseClient
        
        client = LangfuseClient(
            public_key="pk-test",
            secret_key="sk-test",
            host="http://localhost:3000"
        )
        
        traces = client.get_traces(limit=10)
        
        assert len(traces) == 3
        assert traces[0]["id"] == "trace-001"
        mock_get.assert_called_once()
    
    @patch("praisonai.cli.langfuse_client.requests.get")
    def test_fetch_traces_with_session_filter(self, mock_get, sample_traces):
        """Test fetching traces filtered by session ID."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: sample_traces,
            raise_for_status=lambda: None
        )
        
        from praisonai.cli.langfuse_client import LangfuseClient
        
        client = LangfuseClient(
            public_key="pk-test",
            secret_key="sk-test",
            host="http://localhost:3000"
        )
        
        traces = client.get_traces(session_id="session-abc")
        
        # Verify session filter was passed
        call_args = mock_get.call_args
        assert "sessionId" in str(call_args)
    
    @patch("praisonai.cli.langfuse_client.requests.get")
    def test_fetch_sessions_success(self, mock_get, sample_sessions):
        """Test successful session fetching."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: sample_sessions,
            raise_for_status=lambda: None
        )
        
        from praisonai.cli.langfuse_client import LangfuseClient
        
        client = LangfuseClient(
            public_key="pk-test",
            secret_key="sk-test",
            host="http://localhost:3000"
        )
        
        sessions = client.get_sessions()
        
        assert len(sessions) == 2
        assert sessions[0]["id"] == "session-abc"
    
    @patch("praisonai.cli.langfuse_client.requests.get")
    def test_fetch_trace_detail_success(self, mock_get, sample_trace_detail):
        """Test fetching detailed trace information."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: sample_trace_detail,
            raise_for_status=lambda: None
        )
        
        from praisonai.cli.langfuse_client import LangfuseClient
        
        client = LangfuseClient(
            public_key="pk-test",
            secret_key="sk-test",
            host="http://localhost:3000"
        )
        
        trace = client.get_trace("trace-001")
        
        assert trace["id"] == "trace-001"
        assert "observations" in trace
    
    @patch("praisonai.cli.langfuse_client.requests.get")
    def test_api_error_handling(self, mock_get):
        """Test graceful handling of API errors."""
        mock_get.return_value = MagicMock(
            status_code=401,
            text="Unauthorized",
            raise_for_status=lambda: (__ for __ in ()).throw(
                Exception("401 Client Error: Unauthorized")
            )
        )
        
        from praisonai.cli.langfuse_client import LangfuseClient, LangfuseAPIError
        
        client = LangfuseClient(
            public_key="pk-invalid",
            secret_key="sk-invalid",
            host="http://localhost:3000"
        )
        
        with pytest.raises(LangfuseAPIError):
            client.get_traces()
    
    def test_load_config_from_file(self, tmp_path, mock_langfuse_env):
        """Test loading configuration from praisonai langfuse.env file."""
        from praisonai.cli.langfuse_client import LangfuseClient
        
        # Copy the mock config file to the tmp_path location
        import shutil
        config_dir = tmp_path / ".praisonai"
        config_dir.mkdir(parents=True, exist_ok=True)
        dest_file = config_dir / "langfuse.env"
        shutil.copy(mock_langfuse_env, dest_file)
        
        # Mock the default config path
        with patch("pathlib.Path.home", return_value=tmp_path):
            client = LangfuseClient.from_config_file()
        
        assert client.public_key == "pk-test-12345"
        assert client.secret_key == "sk-test-67890"
        assert client.host == "http://localhost:3000"


# -----------------------------------------------------------------------------
# CLI Command Tests
# -----------------------------------------------------------------------------

class TestTracesCommand:
    """Tests for 'praisonai langfuse traces' command."""
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_traces_command_basic(self, mock_client_class, sample_traces, mock_langfuse_env):
        """Test basic traces command execution."""
        mock_client = MagicMock()
        mock_client.get_traces.return_value = sample_traces["data"]
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["traces"])
        
        assert result.exit_code == 0
        assert "trace-001" in result.output
        assert "TestAgent" in result.output
        mock_client.get_traces.assert_called_once_with(limit=20, session_id=None, name=None)
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_traces_command_with_limit(self, mock_client_class, sample_traces, mock_langfuse_env):
        """Test traces command with custom limit."""
        mock_client = MagicMock()
        mock_client.get_traces.return_value = sample_traces["data"][:2]
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["traces", "--limit", "5"])
        
        assert result.exit_code == 0
        mock_client.get_traces.assert_called_once_with(limit=5, session_id=None, name=None)
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_traces_command_with_session_filter(self, mock_client_class, sample_traces, mock_langfuse_env):
        """Test traces command filtered by session ID."""
        mock_client = MagicMock()
        mock_client.get_traces.return_value = [
            t for t in sample_traces["data"] if t["sessionId"] == "session-abc"
        ]
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["traces", "--session", "session-abc"])
        
        assert result.exit_code == 0
        mock_client.get_traces.assert_called_once_with(limit=20, session_id="session-abc", name=None)
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_traces_command_no_config(self, mock_client_class):
        """Test traces command when no config exists."""
        mock_client_class.from_config_file.side_effect = FileNotFoundError("Config not found")
        
        result = runner.invoke(app, ["traces"])
        
        assert result.exit_code != 0
        assert "config" in result.output.lower() or "Error" in result.output


class TestSessionsCommand:
    """Tests for 'praisonai langfuse sessions' command."""
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_sessions_command_basic(self, mock_client_class, sample_sessions, mock_langfuse_env):
        """Test basic sessions command execution."""
        mock_client = MagicMock()
        mock_client.get_sessions.return_value = sample_sessions["data"]
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["sessions"])
        
        assert result.exit_code == 0
        assert "session-abc" in result.output
        assert "2 traces" in result.output or "2" in result.output
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_sessions_command_empty(self, mock_client_class, mock_langfuse_env):
        """Test sessions command when no sessions exist."""
        mock_client = MagicMock()
        mock_client.get_sessions.return_value = []
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["sessions"])
        
        assert result.exit_code == 0
        assert "No sessions" in result.output or "empty" in result.output.lower()


class TestShowCommand:
    """Tests for 'praisonai langfuse show' command."""
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_show_command_basic(self, mock_client_class, sample_trace_detail, mock_langfuse_env):
        """Test basic show command execution."""
        mock_client = MagicMock()
        mock_client.get_trace.return_value = sample_trace_detail
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["show", "trace-001"])
        
        assert result.exit_code == 0
        assert "trace-001" in result.output
        assert "TestAgent" in result.output
        assert "observations" in result.output.lower() or "llm-call" in result.output
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_show_command_not_found(self, mock_client_class, mock_langfuse_env):
        """Test show command when trace doesn't exist."""
        mock_client = MagicMock()
        mock_client.get_trace.side_effect = Exception("Trace not found")
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["show", "nonexistent"])
        
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "Error" in result.output
    
    def test_show_command_missing_argument(self):
        """Test show command without required trace_id argument."""
        result = runner.invoke(app, ["show"])
        
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "TRACE_ID" in result.output


# -----------------------------------------------------------------------------
# Integration with praisonaiagents.obs
# -----------------------------------------------------------------------------

class TestObservabilityConfigLoading:
    """Tests for auto-loading praisonai config in Agent observability."""
    
    def test_auto_load_from_praisonai_config(self, tmp_path, mock_langfuse_env):
        """Test that obs.auto() loads from praisonai config file."""
        from praisonaiagents.obs import _LazyObsModule
        
        # Create module instance
        obs_module = _LazyObsModule()
        
        # Mock the config file location and praisonai-tools import
        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict("os.environ", {}, clear=True):  # Clear env vars
                # Set only the env vars from our config
                with patch.dict("os.environ", {
                    "LANGFUSE_PUBLIC_KEY": "pk-test-12345",
                    "LANGFUSE_SECRET_KEY": "sk-test-67890",
                    "LANGFUSE_HOST": "http://localhost:3000"
                }):
                    # Mock the provider import to avoid needing praisonai-tools
                    with patch.object(obs_module, "_create_provider_factory", return_value=lambda **kwargs: "mock_provider"):
                        provider = obs_module.auto()
        
        # Should detect langfuse from env vars
        assert provider is not None
    
    @patch("importlib.import_module")
    def test_provider_factory_with_config(self, mock_import, mock_langfuse_env):
        """Test that provider factory uses correct credentials."""
        # Mock the praisonai-tools module
        mock_module = MagicMock()
        mock_provider_class = MagicMock(return_value="mock_provider")
        mock_module.LangfuseProvider = mock_provider_class
        mock_import.return_value = mock_module
        
        from praisonaiagents.obs import _LazyObsModule
        
        obs_module = _LazyObsModule()
        
        # Set env vars as if loaded from config
        with patch.dict("os.environ", {
            "LANGFUSE_PUBLIC_KEY": "pk-test-12345",
            "LANGFUSE_SECRET_KEY": "sk-test-67890"
        }):
            factory = obs_module._create_provider_factory("langfuse")
            provider = factory()
        
        mock_provider_class.assert_called_once()


# -----------------------------------------------------------------------------
# Error Handling Tests
# -----------------------------------------------------------------------------

class TestErrorHandling:
    """Tests for error handling in CLI commands."""
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_traces_api_error(self, mock_client_class, mock_langfuse_env):
        """Test graceful handling of API errors in traces command."""
        mock_client = MagicMock()
        mock_client.get_traces.side_effect = Exception("Connection refused")
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["traces"])
        
        assert result.exit_code != 0
        assert "connection" in result.output.lower() or "error" in result.output.lower()
    
    @patch("praisonai.cli.langfuse_client.LangfuseClient")
    def test_unauthorized_error(self, mock_client_class, mock_langfuse_env):
        """Test handling of 401 unauthorized errors."""
        mock_client = MagicMock()
        mock_client.get_traces.side_effect = Exception("401 Client Error: Unauthorized")
        mock_client_class.from_config_file.return_value = mock_client
        
        with patch("pathlib.Path.home", return_value=mock_langfuse_env.parent):
            result = runner.invoke(app, ["traces"])
        
        assert result.exit_code != 0
        assert "credentials" in result.output.lower() or "unauthorized" in result.output.lower()
