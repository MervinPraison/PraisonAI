"""Basic tests for runtime capability system."""

from praisonaiagents.config.feature_configs import RuntimeConfig, resolve_runtime
from praisonaiagents.runtime.capabilities import (
    RuntimeCapability,
    RuntimeCapabilityMatrix,
    get_native_runtime_capabilities,
    get_reduced_harness_capabilities,
    validate_capabilities,
)


def test_basic_capability_system():
    """Test basic functionality."""
    matrix = RuntimeCapabilityMatrix(
        native_hooks=True,
        tool_loop=True,
        basic_chat=True,
    )

    capabilities = matrix.to_capability_set()
    assert RuntimeCapability.NATIVE_HOOKS in capabilities
    assert RuntimeCapability.TOOL_LOOP in capabilities
    assert RuntimeCapability.BASIC_CHAT in capabilities

    native = get_native_runtime_capabilities()
    assert native.native_hooks
    assert native.tool_loop
    assert native.streaming_deltas

    reduced = get_reduced_harness_capabilities()
    assert not reduced.native_hooks
    assert reduced.basic_chat
    assert reduced.simple_tools

    required = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.BASIC_CHAT}
    assert validate_capabilities(native, required, "native") is True

    config = RuntimeConfig(
        required_capabilities=["native_hooks", "tool_loop"],
        preferred_runtime="native",
    )
    assert config.required_capabilities == ["native_hooks", "tool_loop"]
    assert config.preferred_runtime == "native"

    resolved = resolve_runtime({"required_capabilities": ["native_hooks"]})
    assert isinstance(resolved, RuntimeConfig)
    assert resolved.required_capabilities == ["native_hooks"]
