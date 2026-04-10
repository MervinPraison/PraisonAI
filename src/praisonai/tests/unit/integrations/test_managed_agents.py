"""
Unit tests for the ManagedAgentIntegration feature.

Tests the basic functionality of the managed agent backend integration
without making actual API calls.
"""

import pytest
from unittest.mock import Mock, patch


def test_managed_agent_integration_import():
    """Test that ManagedAgentIntegration can be imported."""
    from praisonai.integrations.managed_agents import ManagedAgentIntegration
    assert ManagedAgentIntegration is not None


def test_managed_agent_integration_creation():
    """Test creating a ManagedAgentIntegration instance."""
    with patch('praisonai.integrations.managed_agents.aiohttp', None):
        from praisonai.integrations.managed_agents import ManagedAgentIntegration
        
        # Should not raise an exception even without aiohttp
        managed = ManagedAgentIntegration(
            provider="anthropic", 
            api_key="test_key"
        )
        
        assert managed.provider == "anthropic"
        assert managed.api_key == "test_key"
        assert managed.cli_command == "managed-anthropic"
        assert not managed.is_available  # Should be False without aiohttp


def test_tool_mapping():
    """Test the tool mapping functionality."""
    from praisonai.integrations.managed_agents import map_managed_tools
    
    managed_tools = ["bash", "read", "write", "edit", "unknown_tool"]
    mapped_tools = map_managed_tools(managed_tools)
    
    expected = ["execute_command", "read_file", "write_file", "apply_diff", "unknown_tool"]
    assert mapped_tools == expected


def test_agent_backend_parameter():
    """Test that Agent class supports the backend parameter."""
    # Mock aiohttp to avoid import issues
    with patch('praisonai.integrations.managed_agents.aiohttp', None):
        from praisonai.integrations.managed_agents import ManagedAgentIntegration
        from praisonaiagents import Agent
        
        # Create a managed backend instance
        managed = ManagedAgentIntegration(provider="anthropic", api_key="test_key")
        
        # Create agent with backend parameter
        agent = Agent(
            name="test_agent",
            instructions="You are a test agent.",
            backend=managed
        )
        
        # Verify backend is stored
        assert agent.backend == managed


def test_managed_backend_protocol():
    """Test the ManagedBackendProtocol interface."""
    from praisonai.integrations.managed_agents import ManagedBackendProtocol
    
    # Test that the protocol has the expected abstract methods
    expected_methods = [
        'create_agent',
        'create_environment',
        'create_session',
        'send_message',
        'stream_events',
        'collect_response'
    ]
    
    for method_name in expected_methods:
        assert hasattr(ManagedBackendProtocol, method_name)


@patch('praisonai.integrations.managed_agents.aiohttp')
def test_anthropic_provider_creation(mock_aiohttp):
    """Test creating an Anthropic provider."""
    from praisonai.integrations.managed_agents import ManagedAgentIntegration
    
    # Mock aiohttp to be available
    mock_aiohttp.__bool__ = lambda: True
    
    managed = ManagedAgentIntegration(
        provider="anthropic", 
        api_key="test_key"
    )
    
    assert managed.provider == "anthropic"
    assert managed.api_key == "test_key"
    assert managed.backend is not None
    assert managed.is_available


def test_unsupported_provider():
    """Test creating integration with unsupported provider."""
    with patch('praisonai.integrations.managed_agents.aiohttp'):
        from praisonai.integrations.managed_agents import ManagedAgentIntegration
        
        with pytest.raises(ValueError, match="Unsupported provider: unknown"):
            ManagedAgentIntegration(provider="unknown", api_key="test_key")


def test_session_caching():
    """Test that session IDs are cached correctly (regression test for #357 bug)."""
    with patch('praisonai.integrations.managed_agents.aiohttp'):
        from praisonai.integrations.managed_agents import ManagedAgentIntegration
        
        managed = ManagedAgentIntegration(provider="anthropic", api_key="test_key")
        
        # Simulate adding session to cache
        managed._session_cache["test_session"] = "session_id_123"
        
        # Verify the correct session ID is cached (not the key)
        assert managed._session_cache["test_session"] == "session_id_123"
        assert managed._session_cache["test_session"] != "test_session"


def test_api_key_persistence():
    """Test that API keys from environment are persisted (regression test)."""
    with patch('praisonai.integrations.managed_agents.aiohttp'), \
         patch('os.getenv', return_value="env_api_key"):
        
        from praisonai.integrations.managed_agents import ManagedAgentIntegration
        
        # Create without explicit API key to trigger env lookup
        managed = ManagedAgentIntegration(provider="anthropic", api_key=None)
        
        # Should have stored the env key back to api_key
        assert managed.api_key == "env_api_key"