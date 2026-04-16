"""
Unit tests for managed agent integration.

Tests the basic functionality of managed agent backends without making actual API calls.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock


def test_managed_agent_import():
    """Test that ManagedAgent can be imported."""
    from praisonai.integrations.managed_agents import ManagedAgent
    assert ManagedAgent is not None


def test_managed_config_defaults():
    """Test ManagedConfig default values."""
    from praisonai.integrations.managed_agents import ManagedConfig
    
    config = ManagedConfig()
    assert config.model == "claude-sonnet-4-6"
    assert config.system == "You are a skilled AI assistant"
    assert config.max_turns == 25
    assert isinstance(config.tools, list)


def test_managed_agent_creation():
    """Test creating a ManagedAgent instance."""
    from praisonai.integrations.managed_agents import ManagedAgent, ManagedConfig
    
    config = ManagedConfig(
        model="claude-haiku-4-5",
        system="Test assistant",
        name="TestAgent"
    )
    
    agent = ManagedAgent(config=config)
    assert agent._cfg == config.to_dict()


def test_tool_mapping():
    """Test the tool mapping functionality."""
    from praisonai.integrations.managed_agents import map_managed_tools
    
    managed_tools = ["bash", "read", "write", "edit", "unknown_tool"]
    mapped_tools = map_managed_tools(managed_tools)
    
    expected = ["execute_command", "read_file", "write_file", "apply_diff", "unknown_tool"]
    assert mapped_tools == expected


def test_local_managed_config_defaults():
    """Test LocalManagedConfig default values."""
    from praisonai.integrations.managed_local import LocalManagedConfig
    
    config = LocalManagedConfig()
    assert config.model == "gpt-4o-mini"
    assert config.system == "You are a skilled AI assistant"
    assert config.host_packages_ok is False
    assert config.sandbox_type == "subprocess"


def test_local_managed_agent_creation():
    """Test creating a LocalManagedAgent instance."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    
    config = LocalManagedConfig(
        model="gpt-4o-mini",
        name="LocalTestAgent",
        host_packages_ok=True
    )
    
    agent = LocalManagedAgent(config=config)
    assert agent._cfg["name"] == "LocalTestAgent"
    assert agent._cfg["host_packages_ok"] is True


@pytest.mark.asyncio
async def test_managed_backend_protocol_compliance():
    """Test that both backends implement ManagedBackendProtocol."""
    from praisonaiagents.agent.protocols import ManagedBackendProtocol
    from praisonai.integrations.managed_agents import ManagedAgent
    from praisonai.integrations.managed_local import LocalManagedAgent
    
    # Test structural typing compliance
    managed_agent = ManagedAgent()
    local_agent = LocalManagedAgent()
    
    assert isinstance(managed_agent, ManagedBackendProtocol)
    assert isinstance(local_agent, ManagedBackendProtocol)
    
    # Test required methods exist
    required_methods = ["execute", "stream", "reset_session", "reset_all"]
    for method in required_methods:
        assert hasattr(managed_agent, method)
        assert hasattr(local_agent, method)


@pytest.mark.asyncio 
async def test_managed_agent_factory_anthropic():
    """Test factory function for creating Anthropic managed agents."""
    from praisonai.integrations.managed_agents import ManagedAgent, create_managed_agent
    
    # Test explicit creation
    agent = create_managed_agent("anthropic", api_key="test_key")
    assert isinstance(agent, ManagedAgent)
    
    # Test env-based creation
    with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'env_key'}):
        agent = create_managed_agent("anthropic")
        assert isinstance(agent, ManagedAgent)


@pytest.mark.asyncio
async def test_managed_agent_factory_local():
    """Test factory function for creating local managed agents."""
    from praisonai.integrations.managed_local import LocalManagedAgent
    from praisonai.integrations.managed_agents import create_managed_agent
    
    agent = create_managed_agent("local")
    assert isinstance(agent, LocalManagedAgent)


def test_managed_sandbox_required_exception():
    """Test that ManagedSandboxRequired exception exists."""
    from praisonai.integrations.managed_agents import ManagedSandboxRequired
    
    # Test exception can be raised
    with pytest.raises(ManagedSandboxRequired):
        raise ManagedSandboxRequired("Test message")


@pytest.mark.asyncio
async def test_local_managed_packages_safety():
    """Test safety check for packages without compute."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonai.integrations.managed_agents import ManagedSandboxRequired
    
    config = LocalManagedConfig(
        packages={"pip": ["requests"]},
        host_packages_ok=False  # Safety enabled
    )
    
    agent = LocalManagedAgent(config=config)
    
    # Should raise exception when trying to install packages without compute
    with pytest.raises(ManagedSandboxRequired, match="packages= requires compute="):
        await agent._install_packages()


@pytest.mark.asyncio
async def test_local_managed_packages_host_allowed():
    """Test that host packages work when explicitly allowed."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    
    config = LocalManagedConfig(
        packages={"pip": ["requests"]},
        host_packages_ok=True  # Explicitly allow unsafe operation
    )
    
    agent = LocalManagedAgent(config=config)
    
    # Should not raise exception - mock subprocess to avoid actual installs
    with patch('subprocess.run') as mock_run:
        await agent._install_packages()
        # Should have attempted pip install
        assert mock_run.called


@pytest.mark.asyncio
async def test_local_managed_agent_backend_delegation():
    """Test that LocalManagedAgent properly implements the backend protocol."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonaiagents import Agent
    
    # Create managed backend
    config = LocalManagedConfig(model="gpt-4o-mini", name="TestAgent")
    managed = LocalManagedAgent(config=config)
    
    # Create Agent with backend
    agent = Agent(name="test", backend=managed)
    
    # Verify backend is stored
    assert hasattr(agent, '_backend')
    assert agent._backend == managed


def test_retrieve_session_schemas():
    """Test that retrieve_session returns consistent schema."""
    from praisonai.integrations.managed_agents import ManagedAgent
    from praisonai.integrations.managed_local import LocalManagedAgent
    
    # Both should return similar dict structure
    managed = ManagedAgent()
    local = LocalManagedAgent()
    
    # Mock session data
    managed.session_id = "test_session"
    local._session_id = "test_session" 
    
    managed_info = managed.retrieve_session()
    local_info = local.retrieve_session()
    
    # Both should have consistent keys
    required_keys = ["id", "status"]
    for key in required_keys:
        assert key in managed_info
        assert key in local_info