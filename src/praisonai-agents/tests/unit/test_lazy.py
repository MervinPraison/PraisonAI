"""
Tests for centralized lazy loading utility.

TDD: These tests are written FIRST before implementation.
"""

import pytest
import threading


class TestLazyImport:
    """Test the lazy_import function."""
    
    def test_lazy_import_returns_attribute(self):
        """Test that lazy_import returns the correct attribute."""
        from praisonaiagents._lazy import lazy_import
        
        # Import a known module attribute
        result = lazy_import('praisonaiagents.hooks.types', 'HookEvent')
        
        # Verify it's the correct type
        assert result is not None
        assert hasattr(result, 'BEFORE_TOOL')
    
    def test_lazy_import_caches_result(self):
        """Test that lazy_import caches the result."""
        from praisonaiagents._lazy import lazy_import
        
        cache = {}
        
        # First call
        result1 = lazy_import('praisonaiagents.hooks.types', 'HookEvent', cache=cache)
        
        # Second call should use cache
        result2 = lazy_import('praisonaiagents.hooks.types', 'HookEvent', cache=cache)
        
        assert result1 is result2
        assert 'praisonaiagents.hooks.types.HookEvent' in cache
    
    def test_lazy_import_thread_safe(self):
        """Test that lazy_import is thread-safe."""
        from praisonaiagents._lazy import lazy_import
        
        results = []
        errors = []
        cache = {}
        
        def import_in_thread():
            try:
                result = lazy_import('praisonaiagents.hooks.types', 'HookEvent', cache=cache)
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = [threading.Thread(target=import_in_thread) for _ in range(10)]
        
        # Start all threads
        for t in threads:
            t.start()
        
        # Wait for all threads
        for t in threads:
            t.join()
        
        # All should succeed
        assert len(errors) == 0
        assert len(results) == 10
        
        # All should be the same object
        first = results[0]
        for r in results[1:]:
            assert r is first
    
    def test_lazy_import_raises_on_invalid_module(self):
        """Test that lazy_import raises on invalid module."""
        from praisonaiagents._lazy import lazy_import
        
        with pytest.raises(ModuleNotFoundError):
            lazy_import('nonexistent.module', 'Attr')
    
    def test_lazy_import_raises_on_invalid_attribute(self):
        """Test that lazy_import raises on invalid attribute."""
        from praisonaiagents._lazy import lazy_import
        
        with pytest.raises(AttributeError):
            lazy_import('praisonaiagents.hooks.types', 'NonexistentAttr')


class TestLazyModule:
    """Test the LazyModule class for module-level lazy loading."""
    
    def test_lazy_module_defers_import(self):
        """Test that LazyModule defers the actual import."""
        from praisonaiagents._lazy import LazyModule
        
        # Create a lazy module
        lazy = LazyModule('praisonaiagents.hooks.types')
        
        # Module should not be loaded yet
        assert lazy._module is None
        
        # Access an attribute
        hook_event = lazy.HookEvent
        
        # Now module should be loaded
        assert lazy._module is not None
        assert hook_event is not None
    
    def test_lazy_module_caches_module(self):
        """Test that LazyModule caches the loaded module."""
        from praisonaiagents._lazy import LazyModule
        
        lazy = LazyModule('praisonaiagents.hooks.types')
        
        # Access twice
        _ = lazy.HookEvent
        module1 = lazy._module
        
        _ = lazy.HookDecision
        module2 = lazy._module
        
        # Should be same module
        assert module1 is module2


class TestCreateLazyGetattr:
    """Test the create_lazy_getattr helper."""
    
    def test_create_lazy_getattr_returns_function(self):
        """Test that create_lazy_getattr returns a callable."""
        from praisonaiagents._lazy import create_lazy_getattr
        
        mapping = {
            'HookEvent': ('praisonaiagents.hooks.types', 'HookEvent'),
        }
        
        getattr_fn = create_lazy_getattr(mapping)
        
        assert callable(getattr_fn)
    
    def test_create_lazy_getattr_imports_correctly(self):
        """Test that created __getattr__ imports correctly."""
        from praisonaiagents._lazy import create_lazy_getattr
        
        mapping = {
            'HookEvent': ('praisonaiagents.hooks.types', 'HookEvent'),
        }
        
        getattr_fn = create_lazy_getattr(mapping)
        
        result = getattr_fn('HookEvent')
        
        assert result is not None
        assert hasattr(result, 'BEFORE_TOOL')
    
    def test_create_lazy_getattr_raises_on_unknown(self):
        """Test that created __getattr__ raises AttributeError for unknown names."""
        from praisonaiagents._lazy import create_lazy_getattr
        
        mapping = {
            'HookEvent': ('praisonaiagents.hooks.types', 'HookEvent'),
        }
        
        getattr_fn = create_lazy_getattr(mapping, module_name='test_module')
        
        with pytest.raises(AttributeError) as exc_info:
            getattr_fn('NonexistentAttr')
        
        assert 'test_module' in str(exc_info.value)


class TestLazyImportPerformance:
    """Test that lazy loading has minimal performance impact."""
    
    def test_lazy_import_is_fast(self):
        """Test that lazy_import from cache is fast."""
        import time
        from praisonaiagents._lazy import lazy_import
        
        cache = {}
        
        # Prime the cache
        lazy_import('praisonaiagents.hooks.types', 'HookEvent', cache=cache)
        
        # Measure cached access
        start = time.perf_counter()
        for _ in range(1000):
            lazy_import('praisonaiagents.hooks.types', 'HookEvent', cache=cache)
        elapsed = time.perf_counter() - start
        
        # Should be very fast (< 10ms for 1000 calls)
        assert elapsed < 0.01, f"Cached lazy_import too slow: {elapsed*1000:.2f}ms for 1000 calls"
