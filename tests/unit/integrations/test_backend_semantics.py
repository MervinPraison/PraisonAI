"""
Test semantic correctness of the new HostedAgent/LocalAgent split.

Ensures that the provider= overload fix maintains all backward compatibility
while clearly distinguishing hosted runtime from local execution semantics.
"""
import pytest
import warnings
from unittest.mock import patch, MagicMock

def test_hosted_agent_imports():
    """Test that new HostedAgent classes can be imported."""
    from praisonai.integrations import HostedAgent, HostedAgentConfig
    assert HostedAgent is not None
    assert HostedAgentConfig is not None
    
    # Also test top-level imports
    from praisonai import HostedAgent as TopLevelHostedAgent
    from praisonai import HostedAgentConfig as TopLevelHostedAgentConfig
    assert TopLevelHostedAgent is not None
    assert TopLevelHostedAgentConfig is not None


def test_local_agent_imports():
    """Test that new LocalAgent classes can be imported."""
    from praisonai.integrations import LocalAgent, LocalAgentConfig
    assert LocalAgent is not None
    assert LocalAgentConfig is not None
    
    # Also test top-level imports  
    from praisonai import LocalAgent as TopLevelLocalAgent
    from praisonai import LocalAgentConfig as TopLevelLocalAgentConfig
    assert TopLevelLocalAgent is not None
    assert TopLevelLocalAgentConfig is not None


def test_hosted_agent_only_accepts_anthropic():
    """Test that HostedAgent only accepts 'anthropic' as provider."""
    from praisonai.integrations import HostedAgent, HostedAgentConfig
    
    # Should work
    hosted = HostedAgent(provider="anthropic")
    assert hosted.provider == "anthropic"
    
    # Should raise ValueError for non-existent managed runtimes
    with pytest.raises(ValueError) as exc_info:
        HostedAgent(provider="modal")
    assert "not yet available" in str(exc_info.value)
    assert "LocalAgent" in str(exc_info.value)
    
    with pytest.raises(ValueError) as exc_info:
        HostedAgent(provider="e2b")
    assert "not yet available" in str(exc_info.value)
    
    with pytest.raises(ValueError) as exc_info:
        HostedAgent(provider="openai")
    assert "not yet available" in str(exc_info.value)


def test_local_agent_rejects_provider_overload():
    """Test that LocalAgent rejects the provider= overload pattern."""
    from praisonai.integrations import LocalAgent, LocalAgentConfig
    
    # Should work without provider=
    local = LocalAgent(config=LocalAgentConfig(model="gpt-4o-mini"))
    
    # Should warn when provider= is used (deprecated pattern)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        LocalAgent(provider="openai", config=LocalAgentConfig(model="gpt-4o-mini"))
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "provider=" in str(w[0].message)
        assert "config.model=" in str(w[0].message)


def test_managed_agent_deprecation_warnings():
    """Test that ManagedAgent emits proper deprecation warnings."""
    from praisonai.integrations.managed_agents import ManagedAgent
    
    # LLM routing providers should emit deprecation warning
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        with patch('praisonai.integrations.managed_local.LocalManagedAgent'):
            ManagedAgent(provider="openai")
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
            assert "LocalAgent" in str(w[0].message)


def test_managed_agent_compute_provider_errors():
    """Test that ManagedAgent raises proper errors for compute provider names."""
    from praisonai.integrations.managed_agents import ManagedAgent
    
    # Compute providers should raise ValueError 
    with pytest.raises(ValueError) as exc_info:
        ManagedAgent(provider="modal")
    assert "compute" in str(exc_info.value).lower()
    assert "LocalAgent" in str(exc_info.value)
    
    with pytest.raises(ValueError) as exc_info:
        ManagedAgent(provider="e2b")
    assert "compute" in str(exc_info.value).lower()
    assert "LocalAgent" in str(exc_info.value)
    
    with pytest.raises(ValueError) as exc_info:
        ManagedAgent(provider="docker")
    assert "compute" in str(exc_info.value).lower()
    assert "LocalAgent" in str(exc_info.value)


def test_managed_agent_anthropic_passthrough():
    """Test that ManagedAgent(provider='anthropic') still works."""
    from praisonai.integrations.managed_agents import ManagedAgent, AnthropicManagedAgent
    
    with patch('praisonai.integrations.managed_agents.AnthropicManagedAgent') as mock_anthropic:
        mock_instance = MagicMock()
        mock_anthropic.return_value = mock_instance
        
        result = ManagedAgent(provider="anthropic")
        
        mock_anthropic.assert_called_once_with(provider="anthropic")
        assert result == mock_instance


def test_backward_compatibility_all_old_names():
    """Test that all old import paths still work."""
    # All these should import without errors
    from praisonai.integrations.managed_agents import (
        ManagedAgent, ManagedConfig, AnthropicManagedAgent,
        ManagedAgentIntegration, ManagedBackendConfig
    )
    from praisonai.integrations.managed_local import (
        LocalManagedAgent, LocalManagedConfig
    )
    from praisonai.integrations.sandboxed_agent import (
        SandboxedAgent, SandboxedAgentConfig
    )
    
    # Top-level imports
    from praisonai import (
        ManagedAgent as TopManagedAgent,
        ManagedConfig as TopManagedConfig,
        AnthropicManagedAgent as TopAnthropicManagedAgent,
        LocalManagedAgent as TopLocalManagedAgent,
        LocalManagedConfig as TopLocalManagedConfig,
        SandboxedAgent as TopSandboxedAgent,
        SandboxedAgentConfig as TopSandboxedAgentConfig,
    )
    
    # All should be defined
    assert ManagedAgent is not None
    assert ManagedConfig is not None
    assert AnthropicManagedAgent is not None
    assert ManagedAgentIntegration is not None
    assert ManagedBackendConfig is not None
    assert LocalManagedAgent is not None
    assert LocalManagedConfig is not None
    assert SandboxedAgent is not None
    assert SandboxedAgentConfig is not None


def test_config_aliases():
    """Test that config class aliases work correctly."""
    from praisonai.integrations import (
        HostedAgent, HostedAgentConfig, LocalAgent, LocalAgentConfig
    )
    from praisonai.integrations.managed_agents import ManagedConfig
    from praisonai.integrations.managed_local import LocalManagedConfig
    
    # HostedAgentConfig should alias ManagedConfig
    assert HostedAgentConfig == ManagedConfig
    
    # LocalAgentConfig should alias LocalManagedConfig  
    assert LocalAgentConfig == LocalManagedConfig


def test_unknown_provider_error():
    """Test that unknown providers raise helpful error messages."""
    from praisonai.integrations.managed_agents import ManagedAgent
    
    with pytest.raises(ValueError) as exc_info:
        ManagedAgent(provider="unknown-provider")
    assert "Unknown provider" in str(exc_info.value)
    assert "anthropic" in str(exc_info.value)
    assert "LocalAgent" in str(exc_info.value)