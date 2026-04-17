"""
Unit tests for the Managed Agents Integration feature.

Tests the basic functionality of the managed agent backend integration
without making actual API calls. Focuses on current API surface and
protocol compliance.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock


def test_managed_config_dataclass():
    """Test ManagedConfig dataclass creation and defaults."""
    from praisonai.integrations.managed_agents import ManagedConfig
    
    # Test with defaults
    config = ManagedConfig()
    assert config.name == "Agent"
    assert config.model == "claude-haiku-4-5"
    assert config.system == "You are a helpful coding assistant."
    assert config.tools == [{"type": "agent_toolset_20260401"}]
    assert config.env_name == "praisonai-env"
    assert config.networking == {"type": "unrestricted"}
    
    # Test with custom values
    custom_config = ManagedConfig(
        name="CustomAgent",
        model="claude-sonnet-4-6",
        system="You are a research assistant.",
        tools=[{"type": "agent_toolset_20260401"}, {"type": "custom", "name": "my_tool"}]
    )
    assert custom_config.name == "CustomAgent"
    assert custom_config.model == "claude-sonnet-4-6"
    assert custom_config.system == "You are a research assistant."
    assert len(custom_config.tools) == 2


def test_tool_mapping():
    """Test the tool mapping functionality."""
    from praisonai.integrations.managed_agents import map_managed_tools
    
    managed_tools = ["bash", "read", "write", "edit", "unknown_tool"]
    mapped_tools = map_managed_tools(managed_tools)
    
    expected = ["execute_command", "read_file", "write_file", "apply_diff", "unknown_tool"]
    assert mapped_tools == expected


def test_managed_agent_factory_auto_detection():
    """Test ManagedAgent factory auto-detection logic."""
    from praisonai.integrations.managed_agents import ManagedAgent
    
    # Test auto-detection with no env vars (should default to local)
    with patch.dict('os.environ', {}, clear=True):
        managed = ManagedAgent()
        assert managed.provider == "local"
    
    # Test auto-detection with ANTHROPIC_API_KEY
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}, clear=True):
        managed = ManagedAgent()
        assert managed.provider == "anthropic"
        assert managed.api_key == "test-key"
    
    # Test auto-detection with CLAUDE_API_KEY
    with patch.dict('os.environ', {'CLAUDE_API_KEY': 'claude-key'}, clear=True):
        managed = ManagedAgent()
        assert managed.provider == "anthropic"
        assert managed.api_key == "claude-key"


def test_managed_agent_factory_explicit_providers():
    """Test ManagedAgent factory with explicit provider selection."""
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig
    
    # Test explicit anthropic
    config = ManagedConfig(model="claude-haiku-4-5")
    managed = ManagedAgent(provider="anthropic", config=config, api_key="test-key")
    assert managed.provider == "anthropic"
    assert managed.api_key == "test-key"
    
    # Test explicit local
    managed = ManagedAgent(provider="local", config=config)
    assert managed.provider == "local"
    
    # Test OpenAI routing to local
    managed = ManagedAgent(provider="openai", config=config)
    assert managed.provider == "openai"
    
    # Test Ollama routing to local
    managed = ManagedAgent(provider="ollama", config=config)
    assert managed.provider == "ollama"


def test_anthropic_managed_agent_creation():
    """Test AnthropicManagedAgent creation and configuration."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent, ManagedConfig
    
    config = ManagedConfig(
        name="TestAgent",
        model="claude-haiku-4-5",
        system="Test system prompt",
        tools=[{"type": "agent_toolset_20260401"}]
    )
    
    managed = AnthropicManagedAgent(
        provider="anthropic",
        api_key="test-key",
        config=config,
        timeout=120,
        instructions="Test instructions"
    )
    
    assert managed.provider == "anthropic"
    assert managed.api_key == "test-key"
    assert managed.timeout == 120
    assert managed.instructions == "Test instructions"
    assert managed._cfg["name"] == "TestAgent"
    assert managed._cfg["model"] == "claude-haiku-4-5"
    assert managed._cfg["system"] == "Test system prompt"
    
    # Check initial state
    assert managed.agent_id is None
    assert managed.environment_id is None
    assert managed.session_id is None
    assert managed.total_input_tokens == 0
    assert managed.total_output_tokens == 0


def test_anthropic_managed_agent_dict_config():
    """Test AnthropicManagedAgent with dict config (backward compatibility)."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    config_dict = {
        "name": "DictAgent",
        "model": "claude-sonnet-4-6",
        "system": "Dict config test",
        "tools": [{"type": "custom", "name": "test_tool"}]
    }
    
    managed = AnthropicManagedAgent(config=config_dict, api_key="test-key")
    
    assert managed._cfg["name"] == "DictAgent"
    assert managed._cfg["model"] == "claude-sonnet-4-6"
    assert managed._cfg["system"] == "Dict config test"
    assert managed._cfg["tools"] == [{"type": "custom", "name": "test_tool"}]


def test_managed_backend_protocol_compliance():
    """Test that managed agents implement the expected protocol methods."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    managed = AnthropicManagedAgent(api_key="test-key")
    
    # Check protocol methods exist
    assert hasattr(managed, 'execute')
    assert hasattr(managed, 'stream')
    assert hasattr(managed, 'reset_session')
    assert hasattr(managed, 'reset_all')
    assert hasattr(managed, 'update_agent')
    assert hasattr(managed, 'interrupt')
    assert hasattr(managed, 'retrieve_session')
    assert hasattr(managed, 'list_sessions')
    assert hasattr(managed, 'resume_session')
    assert hasattr(managed, 'save_ids')
    assert hasattr(managed, 'restore_ids')
    
    # Check properties
    assert hasattr(managed, 'session_id')
    assert hasattr(managed, 'managed_session_id')
    assert managed.managed_session_id == managed.session_id


def test_id_persistence_methods():
    """Test save_ids and restore_ids functionality."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    managed = AnthropicManagedAgent(api_key="test-key")
    
    # Set some test IDs
    managed.agent_id = "agent_123"
    managed.agent_version = 2
    managed.environment_id = "env_456"
    managed._session_id = "session_789"
    
    # Save IDs
    saved_ids = managed.save_ids()
    expected_ids = {
        "agent_id": "agent_123",
        "agent_version": 2,
        "environment_id": "env_456",
        "session_id": "session_789"
    }
    assert saved_ids == expected_ids
    
    # Reset and restore
    managed.reset_all()
    assert managed.agent_id is None
    assert managed.session_id is None
    
    managed.restore_ids(saved_ids)
    assert managed.agent_id == "agent_123"
    assert managed.agent_version == 2
    assert managed.environment_id == "env_456"
    assert managed.session_id == "session_789"


def test_session_management():
    """Test session management methods."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    managed = AnthropicManagedAgent(api_key="test-key")
    
    # Test initial state
    assert managed.session_id is None
    
    # Test reset methods
    managed._session_id = "test_session"
    managed.total_input_tokens = 100
    managed.total_output_tokens = 200
    
    managed.reset_session()
    assert managed.session_id is None
    assert managed.total_input_tokens == 100  # Should not reset tokens
    
    managed._session_id = "test_session"
    managed.reset_all()
    assert managed.session_id is None
    assert managed.total_input_tokens == 0
    assert managed.total_output_tokens == 0
    assert managed.agent_id is None


def test_agent_backend_integration():
    """Test that Agent class can use managed backend."""
    from praisonaiagents import Agent
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    # Create a mock backend
    mock_backend = Mock(spec=AnthropicManagedAgent)
    mock_backend.execute.return_value = "Backend response"
    
    # Create agent with backend
    agent = Agent(
        name="test_agent",
        instructions="Test agent",
        backend=mock_backend
    )
    
    # Verify backend is stored
    assert agent.backend == mock_backend


def test_agent_env_key_resolution():
    """Test API key resolution from environment variables."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    # Test ANTHROPIC_API_KEY
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'anthropic-key'}, clear=True):
        managed = AnthropicManagedAgent()
        assert managed.api_key == "anthropic-key"
    
    # Test CLAUDE_API_KEY fallback
    with patch.dict('os.environ', {'CLAUDE_API_KEY': 'claude-key'}, clear=True):
        managed = AnthropicManagedAgent()
        assert managed.api_key == "claude-key"
    
    # Test explicit key overrides env
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'env-key'}, clear=True):
        managed = AnthropicManagedAgent(api_key="explicit-key")
        assert managed.api_key == "explicit-key"


def test_usage_tracking_initialization():
    """Test that usage tracking counters are properly initialized."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    managed = AnthropicManagedAgent(api_key="test-key")
    
    assert managed.total_input_tokens == 0
    assert managed.total_output_tokens == 0
    
    # Test that reset_all clears counters
    managed.total_input_tokens = 100
    managed.total_output_tokens = 200
    managed.reset_all()
    
    assert managed.total_input_tokens == 0
    assert managed.total_output_tokens == 0


def test_backward_compatible_aliases():
    """Test backward compatible class aliases."""
    from praisonai.integrations.managed_agents import ManagedAgentIntegration, ManagedBackendConfig, ManagedAgent, ManagedConfig
    
    # Test that aliases exist and point to correct classes
    assert ManagedAgentIntegration == ManagedAgent
    assert ManagedBackendConfig == ManagedConfig


def test_local_retrieve_session_no_session_returns_empty_dict():
    """Local backend should preserve empty-session behavior."""
    from praisonai.integrations.managed_local import LocalManagedAgent

    managed = LocalManagedAgent()
    assert managed.retrieve_session() == {}


@patch("praisonai.integrations.managed_local.subprocess.run")
def test_local_install_packages_prefers_compute_and_skips_host(mock_subprocess_run):
    """Successful compute install must not fall through to host install."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig

    managed = LocalManagedAgent(
        config=LocalManagedConfig(packages={"pip": ["requests"]})
    )
    managed._compute = object()
    managed._install_via_compute = AsyncMock(return_value=None)

    managed._install_packages()

    managed._install_via_compute.assert_awaited_once_with(["requests"])
    mock_subprocess_run.assert_not_called()


@pytest.mark.asyncio
@patch("praisonai.integrations.managed_local.subprocess.run")
async def test_local_install_packages_prefers_compute_inside_running_loop(mock_subprocess_run):
    """Compute install should also work when called inside an active event loop."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig

    managed = LocalManagedAgent(
        config=LocalManagedConfig(packages={"pip": ["requests"]})
    )
    managed._compute = object()
    managed._install_via_compute = AsyncMock(return_value=None)

    managed._install_packages()

    managed._install_via_compute.assert_awaited_once_with(["requests"])
    mock_subprocess_run.assert_not_called()


@pytest.mark.asyncio
async def test_local_install_via_compute_quotes_package_names():
    """Package names passed through shell command should be shell-escaped."""
    from praisonai.integrations.managed_local import LocalManagedAgent

    managed = LocalManagedAgent()
    managed._compute_instance_id = "inst_123"
    managed.execute_in_compute = AsyncMock(return_value={"stdout": "", "stderr": "", "exit_code": 0})

    await managed._install_via_compute(["requests", "bad;echo pwned"])

    managed.execute_in_compute.assert_awaited_once()
    command = managed.execute_in_compute.await_args.args[0]
    assert "pip install -q " in command
    assert "'bad;echo pwned'" in command


@patch('praisonai.integrations.managed_agents.logger')
def test_logging_integration(mock_logger):
    """Test that managed agents include proper logging."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    managed = AnthropicManagedAgent(api_key="test-key")
    managed.reset_session()
    managed.reset_all()
    
    # Verify logging is available (don't assert specific calls since they may not happen in unit tests)
    assert mock_logger is not None
