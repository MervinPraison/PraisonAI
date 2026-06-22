#!/usr/bin/env python3

"""Test capability validation failure scenarios."""

import sys
import os
# Add the package to path if running as a script
if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.runtime.capabilities import (
    RuntimeCapabilityMatrix,
    RuntimeCapability,
    CapabilityValidationError,
    validate_capabilities,
)

def test_validation_failure():
    """Test that validation correctly fails when capabilities are missing."""
    print("Testing capability validation failure scenarios...")
    
    # Create a limited runtime (like plugin harness)
    limited_runtime = RuntimeCapabilityMatrix(
        basic_chat=True,
        simple_tools=True,
        # Missing: native_hooks, streaming_deltas, etc.
    )
    
    # Require capabilities the limited runtime doesn't have
    required = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.STREAMING_DELTAS}
    
    try:
        validate_capabilities(limited_runtime, required, "plugin-harness")
        raise AssertionError("Expected CapabilityValidationError but validation passed")
    except CapabilityValidationError as e:
        assert e.runtime_name == "plugin-harness"
        assert RuntimeCapability.NATIVE_HOOKS in e.missing_capabilities
        assert RuntimeCapability.STREAMING_DELTAS in e.missing_capabilities
        assert RuntimeCapability.BASIC_CHAT in e.available_capabilities
        assert RuntimeCapability.SIMPLE_TOOLS in e.available_capabilities
        print("✓ Capability validation correctly fails for missing capabilities")
    
    # Test that partial capability matching also fails
    partial_runtime = RuntimeCapabilityMatrix(
        native_hooks=True,  # Has this one
        basic_chat=True,
        # Missing: streaming_deltas
    )
    
    required_partial = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.STREAMING_DELTAS}
    
    try:
        validate_capabilities(partial_runtime, required_partial, "partial-runtime")
        raise AssertionError("Expected CapabilityValidationError but validation passed")
    except CapabilityValidationError as e:
        assert RuntimeCapability.STREAMING_DELTAS in e.missing_capabilities
        assert RuntimeCapability.NATIVE_HOOKS not in e.missing_capabilities  # This one is available
        print("✓ Capability validation correctly identifies specific missing capabilities")
    
    print("\nAll validation failure tests passed! 🎉")

if __name__ == "__main__":
    test_validation_failure()