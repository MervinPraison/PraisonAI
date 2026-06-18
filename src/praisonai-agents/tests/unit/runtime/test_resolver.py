"""Tests for runtime resolver with resolution order logic."""

import pytest
import warnings
from unittest.mock import Mock, patch

from praisonaiagents.runtime.resolver import (
    RuntimeResolver,
    RuntimeResolutionContext,
    RuntimeResolutionResult
)
from praisonaiagents.runtime.config import AgentRuntimeConfig


class TestRuntimeResolutionContext:
    """Test suite for RuntimeResolutionContext."""
    
    def test_basic_initialization(self):
        """Test basic initialization of resolution context."""
        context = RuntimeResolutionContext()
        
        assert context.model_name is None
        assert context.provider_name is None
        assert context.model_config is None
        assert context.provider_config is None
        assert context.agent_config is None
        assert context.metadata == {}
    
    def test_initialization_with_parameters(self):
        """Test initialization with parameters."""
        context = RuntimeResolutionContext(
            model_name="gpt-4o",
            provider_name="openai",
            model_config={"temperature": 0.7},
            agent_config={"agent_id": "test-agent"}
        )
        
        assert context.model_name == "gpt-4o"
        assert context.provider_name == "openai"
        assert context.model_config == {"temperature": 0.7}
        assert context.agent_config == {"agent_id": "test-agent"}


class TestRuntimeResolutionResult:
    """Test suite for RuntimeResolutionResult."""
    
    def test_basic_initialization(self):
        """Test basic initialization of resolution result."""
        runtime_mock = Mock()
        result = RuntimeResolutionResult(
            runtime=runtime_mock,
            runtime_id="claude-code",
            resolution_source="model"
        )
        
        assert result.runtime is runtime_mock
        assert result.runtime_id == "claude-code"
        assert result.resolution_source == "model"
        assert result.config_used is None
        assert result.metadata == {}


class TestRuntimeResolver:
    """Test suite for RuntimeResolver functionality."""
    
    def test_initialization(self):
        """Test basic resolver initialization."""
        resolver = RuntimeResolver()
        assert resolver.default_runtime_id == "praisonai"
        
        resolver2 = RuntimeResolver(default_runtime_id="claude-code")
        assert resolver2.default_runtime_id == "claude-code"
    
    def test_resolve_runtime_config_model_scoped(self):
        """Test model-scoped runtime resolution."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext(model_name="claude-3-sonnet")
        
        # Model-scoped runtime configuration
        model_configs = {
            "claude-3-sonnet": AgentRuntimeConfig.from_runtime_id("claude-code")
        }
        
        result = resolver.resolve_runtime_config(
            context=context,
            model_runtime_configs=model_configs
        )
        
        assert result.runtime == "claude-code"
        assert result.metadata["resolution_source"] == "model"
    
    def test_resolve_runtime_config_provider_scoped(self):
        """Test provider-scoped runtime resolution."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext(
            model_name="gpt-4o",
            provider_name="openai"
        )
        
        # Provider-scoped runtime configuration
        provider_configs = {
            "openai": AgentRuntimeConfig.from_runtime_id("openai-cli")
        }
        
        result = resolver.resolve_runtime_config(
            context=context,
            provider_runtime_configs=provider_configs
        )
        
        assert result.runtime == "openai-cli"
        assert result.metadata["resolution_source"] == "provider"
    
    def test_resolve_runtime_config_default(self):
        """Test default runtime resolution."""
        resolver = RuntimeResolver(default_runtime_id="my-default")
        context = RuntimeResolutionContext(model_name="unknown-model")
        
        result = resolver.resolve_runtime_config(context=context)
        
        assert result.runtime == "my-default"
        assert result.metadata["resolution_source"] == "default"
    
    def test_resolve_runtime_config_legacy_cli_backend(self):
        """Test legacy cli_backend resolution with deprecation warning."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext(model_name="gpt-4o")
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            result = resolver.resolve_runtime_config(
                context=context,
                legacy_cli_backend="claude-code"
            )
            
            # Check deprecation warning was emitted
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "deprecated" in str(w[0].message).lower()
            
            # Check result
            assert result.metadata["resolution_source"] == "legacy"
    
    def test_resolve_runtime_config_resolution_order(self):
        """Test that resolution follows the correct priority order."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext(
            model_name="claude-3-sonnet",
            provider_name="anthropic"
        )
        
        # Set up configs at all levels
        model_configs = {
            "claude-3-sonnet": AgentRuntimeConfig.from_runtime_id("model-runtime")
        }
        provider_configs = {
            "anthropic": AgentRuntimeConfig.from_runtime_id("provider-runtime")
        }
        
        # Model should win over provider
        result = resolver.resolve_runtime_config(
            context=context,
            model_runtime_configs=model_configs,
            provider_runtime_configs=provider_configs,
            legacy_cli_backend="legacy-runtime"
        )
        
        assert result.runtime == "model-runtime"
        assert result.metadata["resolution_source"] == "model"
    
    def test_resolve_runtime_config_fallback_chain(self):
        """Test fallback chain when higher priority configs are missing."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext(
            model_name="unknown-model",
            provider_name="anthropic"
        )
        
        # Only provider config available
        provider_configs = {
            "anthropic": AgentRuntimeConfig.from_runtime_id("provider-runtime")
        }
        
        result = resolver.resolve_runtime_config(
            context=context,
            provider_runtime_configs=provider_configs
        )
        
        assert result.runtime == "provider-runtime"
        assert result.metadata["resolution_source"] == "provider"
    
    def test_resolve_runtime_config_non_explicit_configs_skipped(self):
        """Test that non-explicit configs are skipped."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext(model_name="claude-3-sonnet")
        
        # Model config without explicit runtime
        model_configs = {
            "claude-3-sonnet": AgentRuntimeConfig()  # No runtime specified
        }
        
        result = resolver.resolve_runtime_config(
            context=context,
            model_runtime_configs=model_configs
        )
        
        # Should fall back to default since model config is not explicit
        assert result.runtime == "praisonai"
        assert result.metadata["resolution_source"] == "default"
    
    @patch('praisonaiagents.runtime.resolver.resolve_runtime')
    def test_resolve_runtime_instance_success(self, mock_resolve_runtime):
        """Test successful runtime instance resolution."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext(model_name="claude-3-sonnet")
        
        # Mock runtime instance
        runtime_mock = Mock()
        mock_resolve_runtime.return_value = runtime_mock
        
        # Model-scoped config
        model_configs = {
            "claude-3-sonnet": AgentRuntimeConfig.from_runtime_id("claude-code")
        }
        
        result = resolver.resolve_runtime_instance(
            context=context,
            model_runtime_configs=model_configs
        )
        
        assert result.runtime is runtime_mock
        assert result.runtime_id == "claude-code"
        assert result.resolution_source == "model"
        
        # Check that resolve_runtime was called correctly
        mock_resolve_runtime.assert_called_once_with(
            runtime_id="claude-code",
            config_overrides={}
        )
    
    @patch('praisonaiagents.runtime.resolver.resolve_runtime')
    def test_resolve_runtime_instance_legacy_instance(self, mock_resolve_runtime):
        """Test legacy instance resolution."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext()
        
        # Legacy instance that's already resolved
        legacy_instance = Mock()
        
        result = resolver.resolve_runtime_instance(
            context=context,
            legacy_cli_backend=legacy_instance
        )
        
        assert result.runtime is legacy_instance
        assert result.runtime_id == "legacy"
        assert result.resolution_source == "legacy"
        assert result.metadata["legacy_instance"] is True
        
        # Should not call registry resolve for legacy instances
        mock_resolve_runtime.assert_not_called()
    
    @patch('praisonaiagents.runtime.resolver.resolve_runtime')
    @patch('praisonaiagents.runtime.resolver.list_available_runtimes')
    def test_resolve_runtime_instance_unknown_runtime(self, mock_list_runtimes, mock_resolve_runtime):
        """Test error handling for unknown runtime ID."""
        resolver = RuntimeResolver()
        context = RuntimeResolutionContext(model_name="claude-3-sonnet")
        
        # Mock registry to raise ValueError for unknown runtime
        mock_resolve_runtime.side_effect = ValueError("Unknown runtime: unknown-runtime")
        mock_list_runtimes.return_value = [
            Mock(runtime_id="claude-code"),
            Mock(runtime_id="praisonai")
        ]
        
        # Model config with unknown runtime
        model_configs = {
            "claude-3-sonnet": AgentRuntimeConfig.from_runtime_id("unknown-runtime")
        }
        
        with pytest.raises(ValueError, match="Unknown runtime ID: unknown-runtime"):
            resolver.resolve_runtime_instance(
                context=context,
                model_runtime_configs=model_configs
            )
    
    def test_validate_runtime_config_valid(self):
        """Test validation of valid runtime config."""
        resolver = RuntimeResolver()
        config = AgentRuntimeConfig.from_runtime_id("claude-code")
        
        # Should not raise any exception
        resolver.validate_runtime_config(config)
    
    def test_validate_runtime_config_invalid_runtime_type(self):
        """Test validation with invalid runtime type."""
        resolver = RuntimeResolver()
        config = AgentRuntimeConfig(runtime=123)  # Invalid type
        
        with pytest.raises(TypeError, match="Runtime ID must be a string"):
            resolver.validate_runtime_config(config)
    
    def test_validate_runtime_config_empty_runtime(self):
        """Test validation with empty runtime."""
        resolver = RuntimeResolver()
        config = AgentRuntimeConfig(runtime="   ")  # Empty/whitespace
        
        with pytest.raises(ValueError, match="Runtime ID cannot be empty"):
            resolver.validate_runtime_config(config)
    
    def test_validate_runtime_config_missing_runtime_attribute(self):
        """Test validation with object missing runtime attribute."""
        resolver = RuntimeResolver()
        invalid_config = Mock()
        del invalid_config.runtime  # Remove runtime attribute
        
        with pytest.raises(TypeError, match="Runtime configuration must have 'runtime' attribute"):
            resolver.validate_runtime_config(invalid_config)
    
    def test_validate_runtime_config_invalid_config_overrides(self):
        """Test validation with invalid config_overrides."""
        resolver = RuntimeResolver()
        config = AgentRuntimeConfig(
            runtime="claude-code",
            config_overrides="invalid"  # Should be dict
        )
        
        with pytest.raises(TypeError, match="config_overrides must be a dictionary"):
            resolver.validate_runtime_config(config)
    
    def test_validate_runtime_config_invalid_metadata(self):
        """Test validation with invalid metadata."""
        resolver = RuntimeResolver()
        config = AgentRuntimeConfig(
            runtime="claude-code",
            metadata="invalid"  # Should be dict
        )
        
        with pytest.raises(TypeError, match="metadata must be a dictionary"):
            resolver.validate_runtime_config(config)