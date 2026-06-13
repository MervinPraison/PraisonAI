"""
Tests for runtime registry functionality.
"""

import pytest
from unittest.mock import Mock
from praisonaiagents.runtime.registry import (
    register_runtime, 
    list_runtimes, 
    resolve_runtime_factory,
    get_all_runtime_factories,
    _get_runtime_registry
)


class MockRuntimeForRegistry:
    """Mock runtime for registry testing."""
    
    def __init__(self, name: str):
        self.name = name
        
    @property
    def runtime_id(self) -> str:
        return self.name


class TestRuntimeRegistry:
    """Test runtime registry operations."""
    
    def setup_method(self):
        """Reset registry before each test."""
        import praisonaiagents.runtime.registry as reg
        reg._runtime_registry = None
    
    def test_register_and_list_runtimes(self):
        """Test registering and listing runtimes."""
        # Register a runtime
        mock_runtime = MockRuntimeForRegistry("test-runtime")
        register_runtime("test-runtime", lambda: mock_runtime)
        
        # Check it appears in the list
        runtimes = list_runtimes()
        assert "test-runtime" in runtimes
        assert "praisonai" in runtimes  # Built-in should be there
    
    def test_resolve_runtime_factory(self):
        """Test resolving runtime factory by ID."""
        mock_runtime = MockRuntimeForRegistry("test-runtime") 
        register_runtime("test-runtime", lambda: mock_runtime)
        
        factory = resolve_runtime_factory("test-runtime")
        runtime = factory()
        assert runtime.runtime_id == "test-runtime"
    
    def test_resolve_unknown_runtime_raises_error(self):
        """Test that resolving unknown runtime raises ValueError."""
        with pytest.raises(ValueError, match="Unknown runtime: nonexistent"):
            resolve_runtime_factory("nonexistent")
    
    def test_get_all_runtime_factories(self):
        """Test getting all registered factories."""
        mock_runtime = MockRuntimeForRegistry("test-runtime")
        register_runtime("test-runtime", lambda: mock_runtime)
        
        factories = get_all_runtime_factories()
        assert "test-runtime" in factories
        assert "praisonai" in factories
        
        # Verify factories work
        test_runtime = factories["test-runtime"]()
        assert test_runtime.runtime_id == "test-runtime"
    
    def test_builtin_praisonai_runtime_registered(self):
        """Test that built-in praisonai runtime is automatically registered."""
        runtimes = list_runtimes()
        assert "praisonai" in runtimes
        
        factory = resolve_runtime_factory("praisonai")
        runtime = factory()
        assert runtime.runtime_id == "praisonai"
    
    def test_registry_thread_safety(self):
        """Test basic thread safety of registry operations."""
        import threading
        import time
        
        results = []
        
        def register_multiple():
            for i in range(5):
                name = f"runtime-{i}"
                runtime = MockRuntimeForRegistry(name)
                register_runtime(name, lambda r=runtime: r)
                results.append(name)
                time.sleep(0.001)  # Small delay to encourage race conditions
        
        # Run registration in parallel
        threads = [threading.Thread(target=register_multiple) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Check all runtimes were registered
        runtimes = list_runtimes()
        for result in results:
            assert result in runtimes