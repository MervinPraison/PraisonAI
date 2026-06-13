"""
Runtime Capability System for PraisonAI Agents.

Provides capability detection and validation for different runtime environments
to prevent incompatibilities discovered mid-turn. Enables fail-fast validation
at config/preflight time.

Features:
- RuntimeCapability flags for feature detection
- RuntimeCapabilityMatrix for runtime capability sets
- AgentRuntimeProtocol for runtime implementations
- Capability validation at runtime selection time
- Support for native, plugin harness, and managed runtimes

Usage:
    from praisonaiagents.runtime import (
        RuntimeCapability, 
        RuntimeCapabilityMatrix,
        AgentRuntimeProtocol,
        validate_capabilities
    )
    
    # Define runtime capabilities
    capabilities = RuntimeCapabilityMatrix(
        native_hooks=True,
        tool_loop=True,
        streaming_deltas=True,
        context_compaction=True,
        mcp_tools=True,
        code_execution=True
    )
    
    # Validate against requirements
    required = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.STREAMING_DELTAS}
    if not validate_capabilities(capabilities, required):
        raise RuntimeError("Runtime lacks required capabilities")
"""

from .._lazy import create_lazy_getattr_with_groups

__all__ = [
    # Capability types
    "RuntimeCapability",
    "RuntimeCapabilityMatrix",
    # Protocols
    "AgentRuntimeProtocol",
    # Validation
    "validate_capabilities",
    "CapabilityValidationError",
    # Built-in runtimes
    "get_native_runtime_capabilities",
]

# Grouped lazy imports for DRY and efficient loading
_LAZY_GROUPS = {
    'capabilities': {
        'RuntimeCapability': ('praisonaiagents.runtime.capabilities', 'RuntimeCapability'),
        'RuntimeCapabilityMatrix': ('praisonaiagents.runtime.capabilities', 'RuntimeCapabilityMatrix'),
    },
    'protocols': {
        'AgentRuntimeProtocol': ('praisonaiagents.runtime.protocols', 'AgentRuntimeProtocol'),
    },
    'validation': {
        'validate_capabilities': ('praisonaiagents.runtime.capabilities', 'validate_capabilities'),
        'CapabilityValidationError': ('praisonaiagents.runtime.capabilities', 'CapabilityValidationError'),
    },
    'builtin': {
        'get_native_runtime_capabilities': ('praisonaiagents.runtime.capabilities', 'get_native_runtime_capabilities'),
    },
}

# Create the __getattr__ function using centralized utility
__getattr__ = create_lazy_getattr_with_groups(_LAZY_GROUPS, __name__)