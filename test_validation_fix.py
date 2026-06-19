#!/usr/bin/env python3

"""Test that validation now correctly fails for incompatible runtimes."""

import sys
import os
# Add the package to path if running as a script
if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.agent.agent import Agent
from praisonaiagents.config.feature_configs import RuntimeConfig
from praisonaiagents.runtime.capabilities import RuntimeCapability, CapabilityValidationError

def test_validation_now_works():
    """Test that validation correctly fails for plugin runtime with native_hooks requirement."""
    print("Testing that validation now correctly catches incompatibilities...")
    
    # Test that plugin runtime correctly fails when native_hooks is required
    try:
        agent = Agent(
            instructions="Test agent",
            runtime=RuntimeConfig(
                preferred_runtime="plugin",  # Plugin runtime doesn't support native_hooks
                required_capabilities=[RuntimeCapability.NATIVE_HOOKS],
                validate_on_creation=True
            )
        )
        print("❌ Expected validation to fail but it passed!")
        return False
    except CapabilityValidationError as e:
        if "native_hooks" in str(e).lower():
            print(f"✓ Validation correctly failed: {e}")
        else:
            print(f"❌ Validation failed but for wrong reason: {e}")
            return False
    
    # Test that native runtime still passes with native_hooks
    try:
        agent = Agent(
            instructions="Test agent",
            runtime=RuntimeConfig(
                preferred_runtime="native",  # Native runtime supports everything
                required_capabilities=[RuntimeCapability.NATIVE_HOOKS],
                validate_on_creation=True
            )
        )
        print("✓ Native runtime correctly passes validation")
    except CapabilityValidationError as e:
        print(f"❌ Native runtime should have passed but failed: {e}")
        return False
    
    print("\n✅ All validation fix tests passed! The bug is fixed.")
    return True

if __name__ == "__main__":
    test_validation_now_works()