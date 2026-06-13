"""
Tests for runtime resolution and auto-selection logic.
"""

import pytest
from unittest.mock import Mock, patch
from praisonaiagents.runtime import resolve_runtime, register_runtime
from praisonaiagents.runtime.protocols import AgentRuntimeProtocol
from praisonaiagents.runtime.registry import _get_runtime_registry


class MockRuntime:
    """Mock runtime for testing."""
    
    def __init__(self, runtime_id: str, supports_providers: list, priority: int = 50, available: bool = True):
        self._runtime_id = runtime_id
        self._supports_providers = supports_providers
        self._priority = priority
        self._available = available
    
    def supports(self, provider: str, model: str) -> bool:
        return provider in self._supports_providers
    
    def selection_priority(self) -> int:
        return self._priority
    
    @property
    def runtime_id(self) -> str:
        return self._runtime_id
    
    @property
    def is_available(self) -> bool:
        return self._available
    
    async def execute_agent(self, config, **kwargs):
        return f"executed on {self._runtime_id}"
    
    async def cleanup(self):
        pass


class TestRuntimeResolve:
    """Test runtime resolution and auto-selection."""
    
    def setup_method(self):
        """Reset registry before each test."""
        # Clear global registry
        import praisonaiagents.runtime.registry as reg
        reg._runtime_registry = None
    
    def test_explicit_runtime_selection(self):
        """Test explicit runtime selection by ID."""
        # Register a mock runtime
        mock_runtime = MockRuntime("test-runtime", ["openai"], 30)
        register_runtime("test-runtime", lambda: mock_runtime)
        
        # Resolve explicitly
        runtime = resolve_runtime("openai", "gpt-4", mode="test-runtime")
        assert runtime.runtime_id == "test-runtime"
    
    def test_auto_selection_single_supporting_runtime(self):
        """Test auto selection with single supporting runtime."""
        mock_runtime = MockRuntime("openai-runtime", ["openai"], 30)
        register_runtime("openai-runtime", lambda: mock_runtime)
        
        runtime = resolve_runtime("openai", "gpt-4", mode="auto")
        assert runtime.runtime_id == "openai-runtime"
    
    def test_auto_selection_priority_ordering(self):
        """Test auto selection respects priority ordering."""
        # Register two runtimes with different priorities
        high_priority = MockRuntime("high-priority", ["openai"], 10)  # Lower number = higher priority
        low_priority = MockRuntime("low-priority", ["openai"], 90)
        
        register_runtime("high-priority", lambda: high_priority)
        register_runtime("low-priority", lambda: low_priority)
        
        runtime = resolve_runtime("openai", "gpt-4", mode="auto")
        assert runtime.runtime_id == "high-priority"
    
    def test_auto_selection_no_supporting_runtime_fallback(self):
        """Test auto selection falls back to praisonai when no runtime supports provider."""
        non_supporting = MockRuntime("non-supporting", ["anthropic"], 30)
        register_runtime("non-supporting", lambda: non_supporting)
        
        # Should fall back to praisonai built-in runtime
        runtime = resolve_runtime("openai", "gpt-4", mode="auto")
        assert runtime.runtime_id == "praisonai"
    
    def test_auto_selection_skips_unavailable_runtimes(self):
        """Test auto selection skips unavailable runtimes."""
        unavailable = MockRuntime("unavailable", ["openai"], 10, available=False)
        available = MockRuntime("available", ["openai"], 20, available=True)
        
        register_runtime("unavailable", lambda: unavailable) 
        register_runtime("available", lambda: available)
        
        runtime = resolve_runtime("openai", "gpt-4", mode="auto")
        assert runtime.runtime_id == "available"
    
    def test_explicit_runtime_not_found(self):
        """Test error when explicit runtime is not registered."""
        with pytest.raises(ValueError, match="Unknown runtime: nonexistent"):
            resolve_runtime("openai", "gpt-4", mode="nonexistent")
    
    def test_praisonai_builtin_runtime_supports_all(self):
        """Test that built-in praisonai runtime supports all providers."""
        runtime = resolve_runtime("openai", "gpt-4", mode="praisonai")
        assert runtime.runtime_id == "praisonai"
        assert runtime.supports("openai", "gpt-4")
        assert runtime.supports("anthropic", "claude-3")
        assert runtime.supports("google", "gemini-pro")
    
    def test_runtime_protocol_conformance(self):
        """Test that resolved runtimes conform to protocol."""
        runtime = resolve_runtime("openai", "gpt-4", mode="praisonai")
        
        # Check protocol methods exist
        assert hasattr(runtime, 'supports')
        assert hasattr(runtime, 'selection_priority')
        assert hasattr(runtime, 'execute_agent')
        assert hasattr(runtime, 'cleanup')
        assert hasattr(runtime, 'runtime_id')
        assert hasattr(runtime, 'is_available')
        
        # Check method signatures work
        assert isinstance(runtime.supports("openai", "gpt-4"), bool)
        assert isinstance(runtime.selection_priority(), int)
        assert isinstance(runtime.runtime_id, str)
        assert isinstance(runtime.is_available, bool)