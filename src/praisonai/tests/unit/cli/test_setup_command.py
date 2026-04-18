"""
Unit tests for the setup command.

Tests the setup command functionality including non-interactive mode,
file writing, idempotency, and provider matrix.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer.testing
from typer.testing import CliRunner

from praisonai.cli.commands.setup import app

runner = CliRunner()


@pytest.fixture
def temp_praison_home():
    """Provide a temporary directory for ~/.praisonai/"""
    with tempfile.TemporaryDirectory() as temp_dir:
        with patch.dict(os.environ, {"PRAISONAI_HOME": temp_dir}):
            yield Path(temp_dir)


@pytest.fixture
def mock_input():
    """Mock user inputs for interactive prompts."""
    with patch("builtins.input") as mock:
        yield mock


@pytest.fixture
def mock_getpass():
    """Mock password input for API keys."""
    with patch("getpass.getpass") as mock:
        yield mock


class TestSetupCommand:
    """Test cases for the setup command."""

    def test_setup_command_exists(self):
        """Test that the setup command is registered."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Interactive onboarding" in result.stdout or "configuration wizard" in result.stdout

    def test_setup_non_interactive_openai(self, temp_praison_home):
        """Test setup in non-interactive mode with OpenAI provider."""
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "openai",
            "--api-key", "sk-test123",
            "--model", "gpt-4o-mini"
        ])
        
        assert result.exit_code == 0
        assert "Setup complete" in result.stdout
        
        # Check that .env file was created
        env_file = temp_praison_home / ".env"
        assert env_file.exists()
        
        # Check file permissions (should be 600)
        assert oct(env_file.stat().st_mode)[-3:] == "600"
        
        # Check file contents
        env_content = env_file.read_text()
        assert "OPENAI_API_KEY=sk-test123" in env_content

    def test_setup_non_interactive_anthropic(self, temp_praison_home):
        """Test setup in non-interactive mode with Anthropic provider."""
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "anthropic",
            "--api-key", "sk-ant-test123",
            "--model", "claude-3-5-sonnet-latest"
        ])
        
        assert result.exit_code == 0
        assert "Setup complete" in result.stdout
        
        env_file = temp_praison_home / ".env"
        assert env_file.exists()
        
        env_content = env_file.read_text()
        assert "ANTHROPIC_API_KEY=sk-ant-test123" in env_content

    def test_setup_non_interactive_google(self, temp_praison_home):
        """Test setup in non-interactive mode with Google provider."""
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "google",
            "--api-key", "AIzatest123",
            "--model", "gemini-2.0-flash"
        ])
        
        assert result.exit_code == 0
        env_file = temp_praison_home / ".env"
        env_content = env_file.read_text()
        assert "GEMINI_API_KEY=AIzatest123" in env_content

    def test_setup_non_interactive_ollama(self, temp_praison_home):
        """Test setup in non-interactive mode with Ollama (no API key needed)."""
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "ollama",
            "--model", "llama3.2"
        ])
        
        assert result.exit_code == 0

    def test_setup_creates_directory_structure(self, temp_praison_home):
        """Test that setup creates the required directory structure."""
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "openai",
            "--api-key", "sk-test123"
        ])
        
        assert result.exit_code == 0
        
        # Check that directories are created
        assert (temp_praison_home / "logs").is_dir()
        assert (temp_praison_home / "sessions").is_dir()

    def test_setup_idempotent(self, temp_praison_home):
        """Test that running setup multiple times is idempotent."""
        # First run
        result1 = runner.invoke(app, [
            "--non-interactive",
            "--provider", "openai",
            "--api-key", "sk-test123"
        ])
        assert result1.exit_code == 0
        
        # Second run should not fail
        result2 = runner.invoke(app, [
            "--non-interactive",
            "--provider", "openai",  
            "--api-key", "sk-test456"  # Different key to test overwrite
        ])
        assert result2.exit_code == 0
        
        # Check that the new key is used
        env_file = temp_praison_home / ".env"
        env_content = env_file.read_text()
        assert "OPENAI_API_KEY=sk-test456" in env_content

    def test_setup_preserves_existing_env_vars(self, temp_praison_home):
        """Test that setup preserves existing environment variables."""
        # Create existing .env file
        env_file = temp_praison_home / ".env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text("EXISTING_VAR=existing_value\n")
        
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "openai",
            "--api-key", "sk-test123"
        ])
        
        assert result.exit_code == 0
        
        # Check that existing var is preserved
        env_content = env_file.read_text()
        assert "EXISTING_VAR=existing_value" in env_content
        assert "OPENAI_API_KEY=sk-test123" in env_content

    @patch("rich.prompt.Prompt.ask")
    @patch("rich.prompt.Confirm.ask")
    @patch("getpass.getpass")
    def test_setup_interactive_mode(self, mock_getpass, mock_confirm, mock_prompt, temp_praison_home):
        """Test setup in interactive mode."""
        # Mock user interactions
        mock_prompt.side_effect = ["1", "gpt-4o-mini"]  # OpenAI, then model
        mock_getpass.return_value = "sk-interactive123"
        mock_confirm.side_effect = [True, False]  # Enable telemetry, no starter YAML
        
        result = runner.invoke(app)
        
        assert result.exit_code == 0
        assert "Setup complete" in result.stdout
        
        env_file = temp_praison_home / ".env"
        assert env_file.exists()
        env_content = env_file.read_text()
        assert "OPENAI_API_KEY=sk-interactive123" in env_content

    def test_setup_missing_required_args(self):
        """Test that setup fails when required args are missing in non-interactive mode."""
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "openai"
            # Missing --api-key
        ])
        
        assert result.exit_code != 0
        assert "API key is required" in result.stdout or "required" in result.stdout

    def test_setup_invalid_provider(self):
        """Test that setup fails with invalid provider."""
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "invalid-provider",
            "--api-key", "test"
        ])
        
        assert result.exit_code != 0

    def test_setup_env_file_permissions(self, temp_praison_home):
        """Test that .env file is created with secure permissions."""
        result = runner.invoke(app, [
            "--non-interactive",
            "--provider", "openai",
            "--api-key", "sk-test123"
        ])
        
        assert result.exit_code == 0
        
        env_file = temp_praison_home / ".env"
        # Check that file is readable only by owner (600 permissions)
        stat_mode = env_file.stat().st_mode
        # Last 3 octal digits should be 600
        assert oct(stat_mode)[-3:] == "600"

    def test_setup_with_existing_env_var(self, temp_praison_home):
        """Test setup when API key already exists in environment."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-existing"}):
            # In this case, setup should still work and create .env file
            result = runner.invoke(app, [
                "--non-interactive", 
                "--provider", "openai",
                "--api-key", "sk-test123"
            ])
            
            assert result.exit_code == 0
            
            env_file = temp_praison_home / ".env"
            env_content = env_file.read_text()
            assert "OPENAI_API_KEY=sk-test123" in env_content