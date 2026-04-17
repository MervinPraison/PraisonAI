"""
Unit tests for managed CLI destructive operations.

Tests the newly added delete commands and update functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typer.testing import CliRunner
import typer

from praisonai.cli.commands.managed import (
    sessions_app,
    agents_app, 
    envs_app,
    _get_client,
)


@pytest.fixture
def cli_runner():
    """Create a CLI runner for testing."""
    return CliRunner()


@pytest.fixture 
def mock_anthropic_client():
    """Mock Anthropic client."""
    with patch('praisonai.cli.commands.managed._get_client') as mock_get_client:
        mock_client = Mock()
        mock_get_client.return_value = mock_client
        yield mock_client


class TestSessionsDelete:
    """Test sessions delete command."""

    def test_sessions_delete_success_with_yes_flag(self, cli_runner, mock_anthropic_client):
        """Test successful session deletion with --yes flag."""
        mock_anthropic_client.beta.sessions.delete.return_value = None
        
        result = cli_runner.invoke(sessions_app, [
            "delete", "sesn_01test123", "--yes"
        ])
        
        assert result.exit_code == 0
        assert "Session sesn_01test123 deleted successfully" in result.stdout
        mock_anthropic_client.beta.sessions.delete.assert_called_once_with("sesn_01test123")

    def test_sessions_delete_user_confirms(self, cli_runner, mock_anthropic_client):
        """Test session deletion when user confirms."""
        mock_anthropic_client.beta.sessions.delete.return_value = None
        
        result = cli_runner.invoke(sessions_app, [
            "delete", "sesn_01test123"
        ], input="y\n")
        
        assert result.exit_code == 0
        assert "Session sesn_01test123 deleted successfully" in result.stdout
        mock_anthropic_client.beta.sessions.delete.assert_called_once_with("sesn_01test123")

    def test_sessions_delete_user_cancels(self, cli_runner, mock_anthropic_client):
        """Test session deletion when user cancels."""
        result = cli_runner.invoke(sessions_app, [
            "delete", "sesn_01test123"
        ], input="n\n")
        
        assert result.exit_code == 0
        assert "Deletion cancelled" in result.stdout
        mock_anthropic_client.beta.sessions.delete.assert_not_called()

    def test_sessions_delete_api_error(self, cli_runner, mock_anthropic_client):
        """Test session deletion with API error."""
        mock_anthropic_client.beta.sessions.delete.side_effect = Exception("API Error")
        
        result = cli_runner.invoke(sessions_app, [
            "delete", "sesn_01test123", "--yes"
        ])
        
        assert result.exit_code == 1
        assert "Error deleting session: API Error" in result.stdout


class TestAgentsDelete:
    """Test agents delete command."""

    def test_agents_delete_success_with_yes_flag(self, cli_runner, mock_anthropic_client):
        """Test successful agent deletion with --yes flag."""
        mock_anthropic_client.beta.agents.delete.return_value = None
        
        result = cli_runner.invoke(agents_app, [
            "delete", "agent_01test123", "--yes"
        ])
        
        assert result.exit_code == 0
        assert "Agent agent_01test123 deleted successfully" in result.stdout
        mock_anthropic_client.beta.agents.delete.assert_called_once_with("agent_01test123")

    def test_agents_delete_user_confirms(self, cli_runner, mock_anthropic_client):
        """Test agent deletion when user confirms."""
        mock_anthropic_client.beta.agents.delete.return_value = None
        
        result = cli_runner.invoke(agents_app, [
            "delete", "agent_01test123"
        ], input="y\n")
        
        assert result.exit_code == 0
        assert "Agent agent_01test123 deleted successfully" in result.stdout
        mock_anthropic_client.beta.agents.delete.assert_called_once_with("agent_01test123")

    def test_agents_delete_user_cancels(self, cli_runner, mock_anthropic_client):
        """Test agent deletion when user cancels."""
        result = cli_runner.invoke(agents_app, [
            "delete", "agent_01test123"
        ], input="n\n")
        
        assert result.exit_code == 0
        assert "Deletion cancelled" in result.stdout
        mock_anthropic_client.beta.agents.delete.assert_not_called()

    def test_agents_delete_api_error(self, cli_runner, mock_anthropic_client):
        """Test agent deletion with API error."""
        mock_anthropic_client.beta.agents.delete.side_effect = Exception("API Error")
        
        result = cli_runner.invoke(agents_app, [
            "delete", "agent_01test123", "--yes"
        ])
        
        assert result.exit_code == 1
        assert "Error deleting agent: API Error" in result.stdout


class TestEnvsUpdate:
    """Test envs update command."""

    def test_envs_update_packages_success(self, cli_runner, mock_anthropic_client):
        """Test successful environment update with packages."""
        mock_env = Mock()
        mock_env.id = "env_01test123"
        mock_anthropic_client.beta.environments.update.return_value = mock_env
        
        result = cli_runner.invoke(envs_app, [
            "update", "env_01test123", "--packages", "numpy,pandas"
        ])
        
        assert result.exit_code == 0
        assert "Updated environment: env_01test123" in result.stdout
        mock_anthropic_client.beta.environments.update.assert_called_once_with(
            "env_01test123",
            packages={"pip": ["numpy", "pandas"]}
        )

    def test_envs_update_networking_success(self, cli_runner, mock_anthropic_client):
        """Test successful environment update with networking."""
        mock_env = Mock()
        mock_env.id = "env_01test123"
        mock_anthropic_client.beta.environments.update.return_value = mock_env
        
        result = cli_runner.invoke(envs_app, [
            "update", "env_01test123", "--networking", "limited"
        ])
        
        assert result.exit_code == 0
        assert "Updated environment: env_01test123" in result.stdout
        mock_anthropic_client.beta.environments.update.assert_called_once_with(
            "env_01test123",
            networking={"type": "limited"}
        )

    def test_envs_update_both_options(self, cli_runner, mock_anthropic_client):
        """Test environment update with both packages and networking."""
        mock_env = Mock()
        mock_env.id = "env_01test123"
        mock_anthropic_client.beta.environments.update.return_value = mock_env
        
        result = cli_runner.invoke(envs_app, [
            "update", "env_01test123",
            "--packages", "requests,beautifulsoup4",
            "--networking", "full"
        ])
        
        assert result.exit_code == 0
        assert "Updated environment: env_01test123" in result.stdout
        mock_anthropic_client.beta.environments.update.assert_called_once_with(
            "env_01test123",
            packages={"pip": ["requests", "beautifulsoup4"]},
            networking={"type": "full"}
        )

    def test_envs_update_invalid_networking(self, cli_runner, mock_anthropic_client):
        """Test environment update with invalid networking option."""
        result = cli_runner.invoke(envs_app, [
            "update", "env_01test123", "--networking", "invalid"
        ])
        
        assert result.exit_code == 1
        assert "--networking must be 'full' or 'limited'" in result.stdout
        mock_anthropic_client.beta.environments.update.assert_not_called()

    def test_envs_update_no_options(self, cli_runner, mock_anthropic_client):
        """Test environment update with no options."""
        result = cli_runner.invoke(envs_app, [
            "update", "env_01test123"
        ])
        
        assert result.exit_code == 0
        assert "Nothing to update. Pass --packages or --networking" in result.stdout
        mock_anthropic_client.beta.environments.update.assert_not_called()

    def test_envs_update_api_error(self, cli_runner, mock_anthropic_client):
        """Test environment update with API error."""
        mock_anthropic_client.beta.environments.update.side_effect = Exception("API Error")
        
        result = cli_runner.invoke(envs_app, [
            "update", "env_01test123", "--packages", "numpy"
        ])
        
        assert result.exit_code == 1
        assert "Error updating environment: API Error" in result.stdout


class TestEnvsDelete:
    """Test envs delete command."""

    def test_envs_delete_success_with_yes_flag(self, cli_runner, mock_anthropic_client):
        """Test successful environment deletion with --yes flag."""
        mock_anthropic_client.beta.environments.delete.return_value = None
        
        result = cli_runner.invoke(envs_app, [
            "delete", "env_01test123", "--yes"
        ])
        
        assert result.exit_code == 0
        assert "Environment env_01test123 deleted successfully" in result.stdout
        mock_anthropic_client.beta.environments.delete.assert_called_once_with("env_01test123")

    def test_envs_delete_user_confirms(self, cli_runner, mock_anthropic_client):
        """Test environment deletion when user confirms."""
        mock_anthropic_client.beta.environments.delete.return_value = None
        
        result = cli_runner.invoke(envs_app, [
            "delete", "env_01test123"
        ], input="y\n")
        
        assert result.exit_code == 0
        assert "Environment env_01test123 deleted successfully" in result.stdout
        mock_anthropic_client.beta.environments.delete.assert_called_once_with("env_01test123")

    def test_envs_delete_user_cancels(self, cli_runner, mock_anthropic_client):
        """Test environment deletion when user cancels."""
        result = cli_runner.invoke(envs_app, [
            "delete", "env_01test123"
        ], input="n\n")
        
        assert result.exit_code == 0
        assert "Deletion cancelled" in result.stdout
        mock_anthropic_client.beta.environments.delete.assert_not_called()

    def test_envs_delete_api_error(self, cli_runner, mock_anthropic_client):
        """Test environment deletion with API error."""
        mock_anthropic_client.beta.environments.delete.side_effect = Exception("API Error")
        
        result = cli_runner.invoke(envs_app, [
            "delete", "env_01test123", "--yes"
        ])
        
        assert result.exit_code == 1
        assert "Error deleting environment: API Error" in result.stdout


class TestGetClient:
    """Test the _get_client helper function."""

    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'})
    def test_get_client_with_anthropic_api_key(self):
        """Test client creation with ANTHROPIC_API_KEY."""
        import sys
        mock_anthropic = MagicMock()
        mock_client = Mock()
        mock_anthropic.Anthropic.return_value = mock_client
        with patch.dict(sys.modules, {'anthropic': mock_anthropic}):
            from praisonai.cli.commands.managed import _get_client
            client = _get_client()
        mock_anthropic.Anthropic.assert_called_once_with(api_key='test-key')
        assert client == mock_client

    @patch.dict('os.environ', {'CLAUDE_API_KEY': 'test-key-2'}, clear=True)
    def test_get_client_with_claude_api_key(self):
        """Test client creation with CLAUDE_API_KEY."""
        import sys
        mock_anthropic = MagicMock()
        mock_client = Mock()
        mock_anthropic.Anthropic.return_value = mock_client
        with patch.dict(sys.modules, {'anthropic': mock_anthropic}):
            from praisonai.cli.commands.managed import _get_client
            client = _get_client()
        mock_anthropic.Anthropic.assert_called_once_with(api_key='test-key-2')
        assert client == mock_client

    @patch.dict('os.environ', {}, clear=True)
    def test_get_client_no_api_key(self):
        """Test client creation with no API key."""
        import sys
        mock_anthropic = MagicMock()
        with patch.dict(sys.modules, {'anthropic': mock_anthropic}):
            from praisonai.cli.commands.managed import _get_client
            with pytest.raises(typer.Exit) as exc_info:
                _get_client()
        assert exc_info.value.exit_code == 1

    def test_get_client_no_anthropic_package(self):
        """Test client creation when anthropic package is not installed."""
        import sys
        import builtins
        real_import = builtins.__import__
        def fake_import(name, *args, **kwargs):
            if name == 'anthropic':
                raise ImportError("No module named 'anthropic'")
            return real_import(name, *args, **kwargs)
        saved = sys.modules.pop('anthropic', None)
        try:
            with patch('builtins.__import__', side_effect=fake_import):
                from praisonai.cli.commands.managed import _get_client
                with pytest.raises(typer.Exit) as exc_info:
                    _get_client()
            assert exc_info.value.exit_code == 1
        finally:
            if saved is not None:
                sys.modules['anthropic'] = saved