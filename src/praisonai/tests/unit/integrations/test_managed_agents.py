"""
Unit tests for the ManagedAgentIntegration feature.

Tests the basic functionality of the managed agent backend integration
without making actual API calls.
"""

import os
from unittest.mock import Mock, patch

import pytest


def test_anthropic_managed_agent_import():
    """Test that AnthropicManagedAgent can be imported."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    assert AnthropicManagedAgent is not None


def test_local_managed_agent_import():
    """Test that LocalManagedAgent can be imported."""
    from praisonai.integrations.managed_local import LocalManagedAgent
    assert LocalManagedAgent is not None


def test_anthropic_managed_agent_creation():
    """Test creating an AnthropicManagedAgent instance."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent
    
    managed = AnthropicManagedAgent(api_key="test_key")
    assert managed.api_key == "test_key"
    assert managed.provider == "anthropic"


def test_local_managed_agent_creation():
    """Test creating a LocalManagedAgent instance."""  
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    
    config = LocalManagedConfig(model="gpt-4o", system="Test assistant")
    managed = LocalManagedAgent(config=config)
    assert managed.provider == "local"
    assert managed._cfg["model"] == "gpt-4o"
    assert managed._cfg["system"] == "Test assistant"


def test_tool_mapping():
    """Test the tool mapping functionality."""
    from praisonai.integrations.managed_agents import map_managed_tools
    
    managed_tools = ["bash", "read", "write", "edit", "unknown_tool"]
    mapped_tools = map_managed_tools(managed_tools)
    
    expected = ["execute_command", "read_file", "write_file", "apply_diff", "unknown_tool"]
    assert mapped_tools == expected


def test_agent_backend_parameter():
    """Test that Agent class supports the backend parameter."""
    from praisonai.integrations.managed_agents import AnthropicManagedAgent  
    from praisonaiagents import Agent
    
    # Create a managed backend instance
    managed = AnthropicManagedAgent(api_key="test_key")
    
    # Create agent with backend parameter
    agent = Agent(
        name="test_agent",
        instructions="You are a test agent.",
        backend=managed
    )
    
    # Verify backend is stored
    assert agent.backend == managed


def test_agent_backend_delegation():
    """Test that Agent properly delegates execution to backend."""
    import asyncio
    from typing import Dict, Any, AsyncIterator
    
    class MockManagedBackend:
        """Mock backend to test delegation."""
        
        def __init__(self):
            self.executed_prompts = []
            self.execution_kwargs = []
        
        async def execute(self, prompt: str, **kwargs) -> str:
            self.executed_prompts.append(prompt)
            self.execution_kwargs.append(kwargs)
            return f"Backend response: {prompt}"
        
        async def stream(self, prompt: str, **kwargs) -> AsyncIterator[Dict[str, Any]]:
            self.executed_prompts.append(prompt)
            self.execution_kwargs.append(kwargs)
            yield {
                'type': 'agent.message',
                'content': [{'type': 'text', 'text': f"Backend streamed: {prompt}"}]
            }
    
    # Create mock backend
    mock_backend = MockManagedBackend()
    
    # Create agent with backend
    agent = Agent(
        name="test-agent",
        instructions="Test agent",
        backend=mock_backend
    )
    
    # Test run() delegation
    result = agent.run("Test run prompt")
    assert result == "Backend response: Test run prompt"
    assert len(mock_backend.executed_prompts) == 1
    assert mock_backend.executed_prompts[0] == "Test run prompt"
    
    # Test start() delegation
    result = agent.start("Test start prompt")
    assert result == "Backend response: Test start prompt"
    assert len(mock_backend.executed_prompts) == 2
    assert mock_backend.executed_prompts[1] == "Test start prompt"
    
    # Test chat() delegation
    result = agent.chat("Test chat prompt")
    assert result == "Backend response: Test chat prompt"
    assert len(mock_backend.executed_prompts) == 3
    assert mock_backend.executed_prompts[2] == "Test chat prompt"
    
    # Test that Agent without backend doesn't delegate
    local_agent = Agent(name="local", instructions="Local agent")
    assert not hasattr(local_agent, 'backend') or local_agent.backend is None


def test_managed_backend_protocol():
    """Test the ManagedBackendProtocol interface."""
    from praisonaiagents.managed import ManagedBackendProtocol
    
    # Test that the protocol has the expected methods
    expected_methods = [
        'execute',
        'stream', 
        'reset_session',
        'reset_all',
        'update_agent',
        'interrupt',
        'retrieve_session',
        'list_sessions'
    ]
    
    for method_name in expected_methods:
        assert hasattr(ManagedBackendProtocol, method_name)


def test_compute_provider_integration():
    """Test LocalManagedAgent with compute provider."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonai.integrations.compute.local import LocalCompute
    
    config = LocalManagedConfig(
        model="gpt-4o",
        system="You are a test assistant.", 
        sandbox_type="subprocess"
    )
    
    compute = LocalCompute()
    managed = LocalManagedAgent(config=config, compute=compute)
    
    assert managed.compute_provider is not None
    assert managed._cfg["sandbox_type"] == "subprocess"


def test_managed_agent_protocol_compliance():
    """Test that managed agents implement the protocol correctly."""
    from praisonai.integrations.managed_local import LocalManagedAgent
    from praisonaiagents.managed import ManagedBackendProtocol
    
    # Check that LocalManagedAgent implements required protocol methods
    local_agent = LocalManagedAgent()
    
    # Test protocol compliance at runtime
    assert hasattr(local_agent, 'execute')
    assert hasattr(local_agent, 'stream') 
    assert hasattr(local_agent, 'reset_session')
    assert hasattr(local_agent, 'reset_all')
    
    # Test method signatures exist and are callable
    assert callable(local_agent.execute)
    assert callable(local_agent.stream)


@pytest.mark.asyncio
async def test_local_managed_agent_real_execution():
    """Real agentic test - LocalManagedAgent must call LLM and produce response."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonaiagents import Agent

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set; skipping real managed execution test")
    
    # Create local managed backend
    config = LocalManagedConfig(
        model="gpt-4o-mini",  # Use smaller model for testing
        system="You are a helpful assistant. Respond in exactly one sentence."
    )
    managed = LocalManagedAgent(config=config, api_key=api_key)
    
    # Create agent with managed backend
    agent = Agent(
        name="test_agent",
        instructions="You are a test agent.",
        backend=managed
    )
    
    # This must actually call the LLM and produce a real response
    result = agent.start("Say hello in one sentence")
    print(f"Agent response: {result}")

    # Verify we got a meaningful response
    assert isinstance(result, str)
    assert len(result.strip()) > 0
    assert "hello" in result.lower() or "hi" in result.lower()
