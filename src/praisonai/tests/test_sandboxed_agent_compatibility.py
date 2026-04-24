"""
Tests for backward compatibility between LocalManagedAgent and SandboxedAgent.
Ensures silent aliases work correctly.
"""

import pytest


def test_backward_compatibility_imports():
    """Test that old imports still work identically."""
    
    # Test old imports still work
    try:
        from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
        from praisonai import LocalManagedAgent as TopLevelLocal, LocalManagedConfig as TopLevelLocalConfig
        print("✅ Old imports work")
    except ImportError as e:
        pytest.fail(f"Old imports failed: {e}")
    
    # Test new imports work
    try:
        from praisonai.integrations.sandboxed_agent import SandboxedAgent, SandboxedAgentConfig
        from praisonai import SandboxedAgent as TopLevelSandboxed, SandboxedAgentConfig as TopLevelSandboxedConfig
        print("✅ New imports work")
    except ImportError as e:
        pytest.fail(f"New imports failed: {e}")


def test_aliases_point_to_same_classes():
    """Test that LocalManagedAgent and SandboxedAgent are the same class."""
    from praisonai.integrations.managed_local import LocalManagedAgent, LocalManagedConfig
    from praisonai.integrations.sandboxed_agent import SandboxedAgent, SandboxedAgentConfig
    
    # These should be aliases to the same classes
    assert SandboxedAgent is LocalManagedAgent, "SandboxedAgent should alias LocalManagedAgent"
    assert SandboxedAgentConfig is LocalManagedConfig, "SandboxedAgentConfig should alias LocalManagedConfig"
    print("✅ Aliases point to same classes")


def test_top_level_imports():
    """Test that top-level imports work for both names."""
    from praisonai import LocalManagedAgent, LocalManagedConfig, SandboxedAgent, SandboxedAgentConfig
    
    # Should be the same classes
    assert SandboxedAgent is LocalManagedAgent
    assert SandboxedAgentConfig is LocalManagedConfig
    print("✅ Top-level imports work")


def test_instantiation_compatibility():
    """Test that both names can be instantiated identically."""
    from praisonai import LocalManagedAgent, SandboxedAgent, LocalManagedConfig, SandboxedAgentConfig
    
    # Create configs
    old_config = LocalManagedConfig(model="gpt-4o", system="Old style")
    new_config = SandboxedAgentConfig(model="gpt-4o", system="New style")
    
    # Both should have same structure
    assert type(old_config) is type(new_config)
    assert old_config.model == new_config.model
    print("✅ Config instantiation compatible")
    
    # Create agents (without actually running to avoid needing real LLM)
    old_agent = LocalManagedAgent(provider="local", config=old_config)
    new_agent = SandboxedAgent(provider="local", config=new_config)
    
    # Should be same type
    assert type(old_agent) is type(new_agent)
    print("✅ Agent instantiation compatible")


def test_method_interface_identical():
    """Test that both classes have identical method interfaces."""
    from praisonai import LocalManagedAgent, SandboxedAgent
    
    old_methods = set(dir(LocalManagedAgent))
    new_methods = set(dir(SandboxedAgent))
    
    assert old_methods == new_methods, "Method interfaces should be identical"
    print("✅ Method interfaces identical")


if __name__ == "__main__":
    print("Testing backward compatibility...")
    
    test_backward_compatibility_imports()
    test_aliases_point_to_same_classes()
    test_top_level_imports() 
    test_instantiation_compatibility()
    test_method_interface_identical()
    
    print("All backward compatibility tests passed! 🎉")