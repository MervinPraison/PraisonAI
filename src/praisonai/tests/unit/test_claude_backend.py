"""Unit tests for Claude Code CLI Backend."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

# Add path for importing 
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from praisonai.cli_backends.claude import ClaudeCodeBackend, DEFAULT_CONFIG
from praisonaiagents.cli_backend.protocols import CliBackendConfig, CliSessionBinding


def test_default_config():
    """Test default configuration for Claude backend."""
    backend = ClaudeCodeBackend()
    
    assert backend.config.command == "claude"
    assert "-p" in backend.config.args
    assert "--output-format" in backend.config.args
    assert "stream-json" in backend.config.args
    assert backend.config.output == "jsonl"
    assert backend.config.model_arg == "--model"
    assert "opus" in backend.config.model_aliases
    assert "ANTHROPIC_API_KEY" in backend.config.clear_env


def test_custom_config():
    """Test Claude backend with custom configuration."""
    custom_config = CliBackendConfig(
        command="custom-claude",
        args=["--custom"],
        output="text",
        timeout_ms=120_000
    )
    
    backend = ClaudeCodeBackend(config=custom_config)
    
    assert backend.config.command == "custom-claude"
    assert backend.config.args == ["--custom"]
    assert backend.config.output == "text"
    assert backend.config.timeout_ms == 120_000


def test_build_command_basic():
    """Test basic command building."""
    backend = ClaudeCodeBackend()
    
    cmd = backend._build_command("Hello world")
    
    assert cmd[0] == "claude"
    assert "-p" in cmd
    # With input="stdin" (default), prompt should NOT be in command args
    assert "Hello world" not in cmd


def test_build_command_with_session():
    """Test command building with session."""
    backend = ClaudeCodeBackend()
    session = CliSessionBinding(session_id="test-session-123")
    
    cmd = backend._build_command("Hello", session=session)
    
    assert "--session-id" in cmd
    session_idx = cmd.index("--session-id")
    assert cmd[session_idx + 1] == "test-session-123"


def test_build_command_with_model():
    """Test command building with model."""
    backend = ClaudeCodeBackend()
    
    cmd = backend._build_command("Hello", model="opus")
    
    assert "--model" in cmd
    model_idx = cmd.index("--model")
    # Should use alias
    assert cmd[model_idx + 1] == "claude-opus-4-5"


def test_build_command_with_images():
    """Test command building with images."""
    backend = ClaudeCodeBackend()
    
    cmd = backend._build_command("Analyze this", images=["image1.png", "image2.jpg"])
    
    # Should have two --image arguments
    image_count = cmd.count("--image")
    assert image_count == 2
    assert "image1.png" in cmd
    assert "image2.jpg" in cmd


def test_build_command_with_system_prompt():
    """Test command building with system prompt."""
    backend = ClaudeCodeBackend()
    
    cmd = backend._build_command(
        "Hello", 
        system_prompt="You are a helpful assistant"
    )
    
    assert "--append-system-prompt" in cmd
    prompt_idx = cmd.index("--append-system-prompt")
    assert cmd[prompt_idx + 1] == "You are a helpful assistant"


def test_env_sanitization():
    """Test environment variable sanitization.""" 
    backend = ClaudeCodeBackend()
    
    # Mock environment with sensitive variables
    with patch.dict(os.environ, {
        "ANTHROPIC_API_KEY": "secret-key",
        "CLAUDE_CONFIG_DIR": "/some/path",
        "SAFE_VAR": "keep-this",
        "AWS_ACCESS_KEY_ID": "aws-key"
    }):
        env = backend._get_env()
    
    # Should clear sensitive vars
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CONFIG_DIR" not in env 
    assert "AWS_ACCESS_KEY_ID" not in env
    
    # Should keep non-sensitive vars
    assert env.get("SAFE_VAR") == "keep-this"


@pytest.mark.asyncio
async def test_execute_success():
    """Test successful execution."""
    backend = ClaudeCodeBackend()
    
    # Mock subprocess execution
    mock_output = '{"content": "Hello response"}'
    with patch.object(backend, '_execute_subprocess', return_value=mock_output):
        result = await backend.execute("Hello")
    
    assert result.content == "Hello response"
    assert result.error is None


@pytest.mark.asyncio
async def test_execute_with_session():
    """Test execution with session binding."""
    backend = ClaudeCodeBackend()
    session = CliSessionBinding(session_id="test-session")
    
    mock_output = "Response content"
    with patch.object(backend, '_execute_subprocess', return_value=mock_output):
        result = await backend.execute("Hello", session=session)
    
    assert result.content == "Response content"
    assert result.session_id == "test-session"


@pytest.mark.asyncio
async def test_execute_json_parsing():
    """Test JSON response parsing."""
    backend = ClaudeCodeBackend()
    
    # Mock subprocess to return JSON
    mock_output = '{"result": "Parsed response", "metadata": {"tokens": 10}}'
    with patch.object(backend, '_execute_subprocess', return_value=mock_output):
        with patch.object(backend, 'config') as mock_config:
            mock_config.output = "json"
            result = await backend.execute("Hello")
    
    assert result.content == "Parsed response"


@pytest.mark.asyncio
async def test_execute_error_handling():
    """Test error handling in execution."""
    import subprocess
    backend = ClaudeCodeBackend()
    
    # Mock subprocess to raise CalledProcessError
    error = subprocess.CalledProcessError(1, ["claude"], stderr="CLI error")
    with patch.object(backend, '_execute_subprocess', side_effect=error):
        result = await backend.execute("Hello")
    
    assert result.content == ""
    assert "Claude CLI failed" in result.error


def test_model_aliases():
    """Test model alias resolution."""
    backend = ClaudeCodeBackend()
    
    # Test opus alias
    cmd = backend._build_command("test", model="opus")
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "claude-opus-4-5"
    
    # Test direct model name (no alias)
    cmd = backend._build_command("test", model="gpt-4")
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "gpt-4"