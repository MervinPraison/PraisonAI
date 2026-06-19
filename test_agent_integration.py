#!/usr/bin/env python3

"""Test Agent integration with runtime capability system."""

import sys
import os
# Add the package to path if running as a script
if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.agent.agent import Agent
from praisonaiagents.config.feature_configs import RuntimeConfig
from praisonaiagents.runtime.capabilities import RuntimeCapability, CapabilityValidationError

def test_agent_runtime_integration():
    """Test Agent constructor with runtime parameter."""
    print("Testing Agent integration with runtime capabilities...")
    
    # Test 1: Agent with no runtime config (should work)
    agent = Agent(instructions="Test agent")
    assert agent._runtime_config is None
    print("✓ Agent without runtime config works")
    
    # Test 2: Agent with runtime=True (default config)
    agent = Agent(instructions="Test agent", runtime=True)
    assert agent._runtime_config is not None
    assert agent._runtime_config.required_capabilities is None
    print("✓ Agent with runtime=True works")
    
    # Test 3: Agent with runtime="native" (preferred runtime)
    agent = Agent(instructions="Test agent", runtime="native")
    assert agent._runtime_config is not None
    assert agent._runtime_config.preferred_runtime == "native"
    print("✓ Agent with runtime='native' works")
    
    # Test 4: Agent with runtime config dict
    agent = Agent(
        instructions="Test agent",
        runtime={
            "required_capabilities": ["tool_loop", "basic_chat"],
            "preferred_runtime": "native"
        }
    )
    assert agent._runtime_config is not None
    assert "tool_loop" in agent._runtime_config.required_capabilities
    assert "basic_chat" in agent._runtime_config.required_capabilities
    print("✓ Agent with runtime config dict works")
    
    # Test 5: Agent with RuntimeConfig instance
    config = RuntimeConfig(
        required_capabilities=["native_hooks", "streaming_deltas"],
        preferred_runtime="native"
    )
    agent = Agent(instructions="Test agent", runtime=config)
    assert agent._runtime_config is config
    print("✓ Agent with RuntimeConfig instance works")
    
    # Test 6: Agent with validation disabled
    config_no_validation = RuntimeConfig(
        required_capabilities=["native_hooks"],
        validate_on_creation=False
    )
    agent = Agent(instructions="Test agent", runtime=config_no_validation)
    assert agent._runtime_config.validate_on_creation is False
    print("✓ Agent with validation disabled works")
    
    print("\nAll Agent integration tests passed! 🎉")

if __name__ == "__main__":
    test_agent_runtime_integration()