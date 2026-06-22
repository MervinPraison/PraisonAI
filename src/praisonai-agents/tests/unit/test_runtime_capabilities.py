"""
Unit tests for the runtime capability system.

Tests the capability matrix, validation logic, and integration
with agent configuration system.
"""

import pytest
from unittest.mock import Mock

from praisonaiagents.runtime.capabilities import (
    RuntimeCapability,
    RuntimeCapabilityMatrix,
    CapabilityValidationError,
    validate_capabilities,
    get_native_runtime_capabilities,
    get_reduced_harness_capabilities,
)
from praisonaiagents.config.feature_configs import RuntimeConfig, resolve_runtime


class TestRuntimeCapability:
    """Test RuntimeCapability enum."""
    
    def test_capability_enum_values(self):
        """Test that all expected capabilities are defined."""
        expected_capabilities = {
            'NATIVE_HOOKS',
            'TOOL_LOOP', 
            'STREAMING_DELTAS',
            'CONTEXT_COMPACTION',
            'MCP_TOOLS',
            'CODE_EXECUTION',
            'MULTI_MODAL',
            'ASYNC_EXECUTION',
            'SESSION_PERSISTENCE',
            'MEMORY_MANAGEMENT',
            'BASIC_CHAT',
            'SIMPLE_TOOLS',
        }
        
        actual_capabilities = {cap.name for cap in RuntimeCapability}
        assert expected_capabilities.issubset(actual_capabilities)


class TestRuntimeCapabilityMatrix:
    """Test RuntimeCapabilityMatrix dataclass."""
    
    def test_default_matrix(self):
        """Test default capability matrix (all False)."""
        matrix = RuntimeCapabilityMatrix()
        
        # All should default to False
        assert not matrix.native_hooks
        assert not matrix.tool_loop
        assert not matrix.streaming_deltas
        assert not matrix.context_compaction
        assert not matrix.mcp_tools
        assert not matrix.code_execution
        assert not matrix.multi_modal
        assert not matrix.async_execution
        assert not matrix.session_persistence
        assert not matrix.memory_management
        assert not matrix.basic_chat
        assert not matrix.simple_tools
    
    def test_to_capability_set(self):
        """Test conversion to capability set."""
        matrix = RuntimeCapabilityMatrix(
            native_hooks=True,
            streaming_deltas=True,
            basic_chat=True,
        )
        
        capabilities = matrix.to_capability_set()
        expected = {
            RuntimeCapability.NATIVE_HOOKS,
            RuntimeCapability.STREAMING_DELTAS,
            RuntimeCapability.BASIC_CHAT,
        }
        
        assert capabilities == expected
    
    def test_supports_capability(self):
        """Test supports() method."""
        matrix = RuntimeCapabilityMatrix(tool_loop=True, mcp_tools=True)
        
        assert matrix.supports(RuntimeCapability.TOOL_LOOP)
        assert matrix.supports(RuntimeCapability.MCP_TOOLS)
        assert not matrix.supports(RuntimeCapability.NATIVE_HOOKS)
    
    def test_supports_all(self):
        """Test supports_all() method."""
        matrix = RuntimeCapabilityMatrix(
            native_hooks=True,
            tool_loop=True,
            streaming_deltas=True,
        )
        
        # Should support subset
        required = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.TOOL_LOOP}
        assert matrix.supports_all(required)
        
        # Should not support superset
        required_with_extra = {
            RuntimeCapability.NATIVE_HOOKS,
            RuntimeCapability.TOOL_LOOP,
            RuntimeCapability.CODE_EXECUTION,  # Not supported
        }
        assert not matrix.supports_all(required_with_extra)
    
    def test_missing_capabilities(self):
        """Test missing_capabilities() method."""
        matrix = RuntimeCapabilityMatrix(basic_chat=True, simple_tools=True)
        
        required = {
            RuntimeCapability.BASIC_CHAT,
            RuntimeCapability.NATIVE_HOOKS,
            RuntimeCapability.STREAMING_DELTAS,
        }
        
        missing = matrix.missing_capabilities(required)
        expected_missing = {
            RuntimeCapability.NATIVE_HOOKS,
            RuntimeCapability.STREAMING_DELTAS,
        }
        
        assert missing == expected_missing


class TestBuiltinCapabilities:
    """Test built-in capability matrices."""
    
    def test_native_runtime_capabilities(self):
        """Test that native runtime supports all capabilities."""
        matrix = get_native_runtime_capabilities()
        
        # Native runtime should support everything
        assert matrix.native_hooks
        assert matrix.tool_loop
        assert matrix.streaming_deltas
        assert matrix.context_compaction
        assert matrix.mcp_tools
        assert matrix.code_execution
        assert matrix.multi_modal
        assert matrix.async_execution
        assert matrix.session_persistence
        assert matrix.memory_management
        assert matrix.basic_chat
        assert matrix.simple_tools
        
        # Check metadata
        assert matrix.metadata["runtime_type"] == "native"
    
    def test_reduced_harness_capabilities(self):
        """Test that plugin harness has reduced capabilities."""
        matrix = get_reduced_harness_capabilities()
        
        # Should not support native features
        assert not matrix.native_hooks
        assert not matrix.streaming_deltas
        assert not matrix.context_compaction
        assert not matrix.mcp_tools
        assert not matrix.code_execution
        assert not matrix.multi_modal
        assert not matrix.async_execution
        assert not matrix.session_persistence
        assert not matrix.memory_management
        
        # Should support basic features
        assert matrix.tool_loop  # Can execute tools but without native hooks
        assert matrix.basic_chat
        assert matrix.simple_tools
        
        # Check metadata
        assert matrix.metadata["runtime_type"] == "plugin_harness"


class TestCapabilityValidation:
    """Test capability validation logic."""
    
    def test_validate_capabilities_success(self):
        """Test successful capability validation."""
        runtime_matrix = RuntimeCapabilityMatrix(
            native_hooks=True,
            tool_loop=True,
            basic_chat=True,
        )
        
        required = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.BASIC_CHAT}
        
        # Should not raise exception
        result = validate_capabilities(runtime_matrix, required, "test-runtime")
        assert result is True
    
    def test_validate_capabilities_failure(self):
        """Test capability validation failure."""
        runtime_matrix = RuntimeCapabilityMatrix(basic_chat=True, simple_tools=True)
        
        required = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.STREAMING_DELTAS}
        
        # Should raise CapabilityValidationError
        with pytest.raises(CapabilityValidationError) as exc_info:
            validate_capabilities(runtime_matrix, required, "test-runtime")
        
        error = exc_info.value
        assert error.runtime_name == "test-runtime"
        assert RuntimeCapability.NATIVE_HOOKS in error.missing_capabilities
        assert RuntimeCapability.STREAMING_DELTAS in error.missing_capabilities
    
    def test_validate_with_matrix_input(self):
        """Test validation with RuntimeCapabilityMatrix as required input."""
        runtime_matrix = get_native_runtime_capabilities()
        required_matrix = RuntimeCapabilityMatrix(native_hooks=True, tool_loop=True)
        
        # Should not raise exception
        result = validate_capabilities(runtime_matrix, required_matrix, "native")
        assert result is True


class TestRuntimeConfig:
    """Test RuntimeConfig dataclass."""
    
    def test_default_config(self):
        """Test default runtime configuration."""
        config = RuntimeConfig()
        
        assert config.required_capabilities is None
        assert config.preferred_runtime is None
        assert config.fallback_allowed is True
        assert config.validate_on_creation is True
        assert config.metadata == {}
    
    def test_config_with_capabilities(self):
        """Test runtime config with capabilities."""
        config = RuntimeConfig(
            required_capabilities=["native_hooks", "streaming_deltas"],
            preferred_runtime="native",
            fallback_allowed=False,
        )
        
        assert config.required_capabilities == ["native_hooks", "streaming_deltas"]
        assert config.preferred_runtime == "native"
        assert config.fallback_allowed is False
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = RuntimeConfig(
            required_capabilities={"native_hooks", "tool_loop"},
            preferred_runtime="native",
            metadata={"version": "1.0"},
        )
        
        result = config.to_dict()
        expected = {
            "required_capabilities": ["native_hooks", "tool_loop"],  # Set converted to list
            "preferred_runtime": "native",
            "fallback_allowed": True,
            "validate_on_creation": True,
            "metadata": {"version": "1.0"},
        }
        
        # Convert list to set for comparison since order doesn't matter
        assert set(result["required_capabilities"]) == set(expected["required_capabilities"])
        assert result["preferred_runtime"] == expected["preferred_runtime"]
        assert result["fallback_allowed"] == expected["fallback_allowed"]
        assert result["validate_on_creation"] == expected["validate_on_creation"]
        assert result["metadata"] == expected["metadata"]


class TestResolveRuntime:
    """Test runtime parameter resolution."""
    
    def test_resolve_none(self):
        """Test resolving None returns None."""
        result = resolve_runtime(None)
        assert result is None
    
    def test_resolve_false(self):
        """Test resolving False returns None."""
        result = resolve_runtime(False)
        assert result is None
    
    def test_resolve_true(self):
        """Test resolving True returns default config."""
        result = resolve_runtime(True)
        assert isinstance(result, RuntimeConfig)
        assert result.required_capabilities is None
    
    def test_resolve_string(self):
        """Test resolving string sets preferred_runtime."""
        result = resolve_runtime("native")
        assert isinstance(result, RuntimeConfig)
        assert result.preferred_runtime == "native"
    
    def test_resolve_dict(self):
        """Test resolving dict creates config with values."""
        config_dict = {
            "required_capabilities": ["native_hooks"],
            "preferred_runtime": "native",
            "fallback_allowed": False,
        }
        
        result = resolve_runtime(config_dict)
        assert isinstance(result, RuntimeConfig)
        assert result.required_capabilities == ["native_hooks"]
        assert result.preferred_runtime == "native"
        assert result.fallback_allowed is False
    
    def test_resolve_config_instance(self):
        """Test resolving RuntimeConfig instance returns it unchanged."""
        config = RuntimeConfig(preferred_runtime="test")
        result = resolve_runtime(config)
        assert result is config


class TestCapabilityValidationError:
    """Test CapabilityValidationError exception."""
    
    def test_error_creation(self):
        """Test creating capability validation error."""
        missing = {RuntimeCapability.NATIVE_HOOKS, RuntimeCapability.STREAMING_DELTAS}
        available = {RuntimeCapability.BASIC_CHAT, RuntimeCapability.SIMPLE_TOOLS}
        
        error = CapabilityValidationError(
            runtime_name="test-runtime",
            missing_capabilities=missing,
            available_capabilities=available,
        )
        
        assert error.runtime_name == "test-runtime"
        assert error.missing_capabilities == missing
        assert error.available_capabilities == available
        
        # Check error message contains expected info
        error_msg = str(error)
        assert "test-runtime" in error_msg
        assert "NATIVE_HOOKS" in error_msg
        assert "STREAMING_DELTAS" in error_msg