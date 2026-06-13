#!/usr/bin/env python3

"""Basic test of runtime capability system."""

import sys
sys.path.insert(0, '/home/runner/work/PraisonAI/PraisonAI/src/praisonai-agents')

from praisonaiagents.runtime.capabilities import (
    RuntimeCapability,
    RuntimeCapabilityMatrix,
    validate_capabilities,
    get_native_runtime_capabilities,
    get_reduced_harness_capabilities,
)

from praisonaiagents.config.feature_configs import RuntimeConfig, resolve_runtime

def test_basic_capability_system():
    """Test basic functionality."""
    print("Testing runtime capability system...")
    
    # Test 1: Create capability matrix
    matrix = RuntimeCapabilityMatrix(
        native_hooks=True,
        tool_loop=True,
        basic_chat=True,
    )
    
    capabilities = matrix.to_capability_set()
    assert RuntimeCapability.NATIVE_HOOKS in capabilities
    assert RuntimeCapability.TOOL_LOOP in capabilities
    assert RuntimeCapability.BASIC_CHAT in capabilities
    print("✓ Capability matrix creation works")
    
    # Test 2: Test native runtime capabilities
    native = get_native_runtime_capabilities()
    assert native.native_hooks
    assert native.tool_loop
    assert native.streaming_deltas
    print("✓ Native runtime capabilities work")
    
    # Test 3: Test reduced harness capabilities
    reduced = get_reduced_harness_capabilities()
    assert not reduced.native_hooks
    assert reduced.basic_chat
    assert reduced.simple_tools
    print("✓ Reduced harness capabilities work")
    
    # Test 4: Test capability validation success
    required = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.BASIC_CHAT}
    result = validate_capabilities(native, required, "native")
    assert result is True
    print("✓ Capability validation success works")
    
    # Test 5: Test RuntimeConfig creation
    config = RuntimeConfig(
        required_capabilities=["native_hooks", "tool_loop"],
        preferred_runtime="native"
    )
    assert config.required_capabilities == ["native_hooks", "tool_loop"]
    assert config.preferred_runtime == "native"
    print("✓ RuntimeConfig creation works")
    
    # Test 6: Test resolve_runtime
    resolved = resolve_runtime({"required_capabilities": ["native_hooks"]})
    assert isinstance(resolved, RuntimeConfig)
    assert resolved.required_capabilities == ["native_hooks"]
    print("✓ Runtime parameter resolution works")
    
    print("\nAll tests passed! 🎉")

if __name__ == "__main__":
    test_basic_capability_system()