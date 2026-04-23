"""Unit tests for CLI Backend Protocol."""

import pytest
from unittest.mock import AsyncMock, Mock

from praisonaiagents.cli_backend.protocols import (
    CliBackendConfig,
    CliSessionBinding,
    CliBackendResult,
    CliBackendDelta,
    CliBackendProtocol
)


def test_cli_backend_config_defaults():
    """Test CliBackendConfig with default values."""
    config = CliBackendConfig(command="test-cli")
    
    assert config.command == "test-cli"
    assert config.args == []
    assert config.output == "text"
    assert config.input == "arg"
    assert config.session_mode == "none"
    assert config.timeout_ms == 300_000


def test_cli_backend_config_custom():
    """Test CliBackendConfig with custom values."""
    config = CliBackendConfig(
        command="claude",
        args=["-p", "--verbose"],
        output="jsonl",
        session_mode="always",
        clear_env=["API_KEY"],
        timeout_ms=60_000
    )
    
    assert config.command == "claude"
    assert config.args == ["-p", "--verbose"]
    assert config.output == "jsonl"
    assert config.session_mode == "always"
    assert config.clear_env == ["API_KEY"]
    assert config.timeout_ms == 60_000


def test_cli_session_binding():
    """Test CliSessionBinding data structure."""
    binding = CliSessionBinding(
        session_id="test-session",
        auth_profile_id="profile1",
        system_prompt_hash="hash123"
    )
    
    assert binding.session_id == "test-session"
    assert binding.auth_profile_id == "profile1"
    assert binding.system_prompt_hash == "hash123"
    assert binding.mcp_config_hash is None


def test_cli_backend_result():
    """Test CliBackendResult data structure."""
    result = CliBackendResult(
        content="Hello response",
        metadata={"duration": 1.5},
        session_id="session-123"
    )
    
    assert result.content == "Hello response"
    assert result.metadata == {"duration": 1.5}
    assert result.session_id == "session-123"
    assert result.error is None


def test_cli_backend_delta():
    """Test CliBackendDelta data structure."""
    delta = CliBackendDelta(
        type="text",
        content="Hello",
        metadata={"chunk": 1}
    )
    
    assert delta.type == "text"
    assert delta.content == "Hello"
    assert delta.metadata == {"chunk": 1}


def test_cli_backend_protocol_interface():
    """Test that CliBackendProtocol is properly defined."""
    # Create a mock implementation
    mock_backend = Mock()
    mock_backend.config = CliBackendConfig(command="test")
    mock_backend.execute = AsyncMock(return_value=CliBackendResult(content="test"))
    mock_backend.stream = AsyncMock()
    
    # Verify it satisfies the protocol
    assert isinstance(mock_backend, CliBackendProtocol)
    assert hasattr(mock_backend, 'config')
    assert hasattr(mock_backend, 'execute')
    assert hasattr(mock_backend, 'stream')


@pytest.mark.asyncio
async def test_protocol_execution_interface():
    """Test protocol execution interface."""
    mock_backend = Mock()
    mock_backend.config = CliBackendConfig(command="test")
    
    # Mock execute method
    expected_result = CliBackendResult(content="test response")
    mock_backend.execute = AsyncMock(return_value=expected_result)
    
    # Test execution
    result = await mock_backend.execute("test prompt")
    
    assert result == expected_result
    mock_backend.execute.assert_called_once_with("test prompt")


@pytest.mark.asyncio 
async def test_protocol_streaming_interface():
    """Test protocol streaming interface."""
    mock_backend = Mock()
    mock_backend.config = CliBackendConfig(command="test")
    
    # Mock stream method
    async def mock_stream_generator(*args, **kwargs):
        yield CliBackendDelta(type="text", content="Hello")
        yield CliBackendDelta(type="text", content=" World")
    
    mock_backend.stream = mock_stream_generator
    
    # Test streaming
    chunks = []
    async for delta in mock_backend.stream("test prompt"):
        chunks.append(delta)
    
    assert len(chunks) == 2
    assert chunks[0].content == "Hello"
    assert chunks[1].content == " World"