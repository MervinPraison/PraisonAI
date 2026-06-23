"""Tests for runtime capability validation failure scenarios."""

import pytest

from praisonaiagents.runtime.capabilities import (
    CapabilityValidationError,
    RuntimeCapability,
    RuntimeCapabilityMatrix,
    validate_capabilities,
)


def test_validation_failure():
    """Test that validation correctly fails when capabilities are missing."""
    limited_runtime = RuntimeCapabilityMatrix(
        basic_chat=True,
        simple_tools=True,
    )

    required = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.STREAMING_DELTAS}

    with pytest.raises(CapabilityValidationError) as exc_info:
        validate_capabilities(limited_runtime, required, "plugin-harness")

    error = exc_info.value
    assert error.runtime_name == "plugin-harness"
    assert RuntimeCapability.NATIVE_HOOKS in error.missing_capabilities
    assert RuntimeCapability.STREAMING_DELTAS in error.missing_capabilities
    assert RuntimeCapability.BASIC_CHAT in error.available_capabilities
    assert RuntimeCapability.SIMPLE_TOOLS in error.available_capabilities


def test_partial_capability_validation_failure():
    """Test validation identifies specific missing capabilities."""
    partial_runtime = RuntimeCapabilityMatrix(
        native_hooks=True,
        basic_chat=True,
    )

    required_partial = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.STREAMING_DELTAS}

    with pytest.raises(CapabilityValidationError) as exc_info:
        validate_capabilities(partial_runtime, required_partial, "partial-runtime")

    error = exc_info.value
    assert RuntimeCapability.STREAMING_DELTAS in error.missing_capabilities
    assert RuntimeCapability.NATIVE_HOOKS not in error.missing_capabilities
