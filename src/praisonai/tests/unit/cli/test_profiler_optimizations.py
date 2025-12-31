"""
Unit tests for profiler optimizations module.

Tests Tier 0/1/2 optimization features:
- Provider caching
- Lazy imports
- Client pooling
- Prewarm manager
- Lite mode
- Performance snapshots
"""

import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch


class TestProviderCache:
    """Tests for ProviderCache (Tier 0)."""
    
    def test_singleton_pattern(self):
        """Test that ProviderCache is a singleton."""
        from praisonai.cli.features.profiler import ProviderCache
        
        cache1 = ProviderCache()
        cache2 = ProviderCache()
        assert cache1 is cache2
    
    def test_get_set(self):
        """Test basic get/set operations."""
        from praisonai.cli.features.profiler import get_provider_cache
        
        cache = get_provider_cache()
        cache.invalidate()  # Clear cache
        
        # Miss
        result = cache.get('test_key')
        assert result is None
        
        # Set
        cache.set('test_key', {'value': 'test'})
        
        # Hit - cache stores as {'value': ..., 'expires': ...}
        result = cache.get('test_key')
        assert result is not None
        assert result['value']['value'] == 'test'
    
    def test_invalidate(self):
        """Test cache invalidation."""
        from praisonai.cli.features.profiler import get_provider_cache
        
        cache = get_provider_cache()
        cache.set('key1', 'value1')
        cache.set('key2', 'value2')
        
        # Invalidate single key
        cache.invalidate('key1')
        assert cache.get('key1') is None
        assert cache.get('key2') is not None
        
        # Invalidate all
        cache.invalidate()
        assert cache.get('key2') is None
    
    def test_stats(self):
        """Test cache statistics."""
        from praisonai.cli.features.profiler import get_provider_cache
        
        cache = get_provider_cache()
        cache.invalidate()
        
        # Generate some hits and misses
        cache.get('miss1')  # miss
        cache.set('hit1', 'value')
        cache.get('hit1')  # hit
        cache.get('miss2')  # miss
        
        stats = cache.get_stats()
        assert 'hits' in stats
        assert 'misses' in stats
        assert 'size' in stats
    
    def test_thread_safety(self):
        """Test thread-safe operations."""
        from praisonai.cli.features.profiler import get_provider_cache
        
        cache = get_provider_cache()
        cache.invalidate()
        
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(100):
                    key = f"thread_{thread_id}_key_{i}"
                    cache.set(key, f"value_{i}")
                    cache.get(key)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestResolveModelProvider:
    """Tests for resolve_model_provider (Tier 0)."""
    
    def test_openai_models(self):
        """Test OpenAI model resolution."""
        from praisonai.cli.features.profiler import resolve_model_provider
        
        assert resolve_model_provider('gpt-4o') == ('openai', 'gpt-4o')
        assert resolve_model_provider('gpt-4o-mini') == ('openai', 'gpt-4o-mini')
        assert resolve_model_provider('o1-preview') == ('openai', 'o1-preview')
    
    def test_anthropic_models(self):
        """Test Anthropic model resolution."""
        from praisonai.cli.features.profiler import resolve_model_provider
        
        assert resolve_model_provider('claude-3-opus') == ('anthropic', 'claude-3-opus')
        assert resolve_model_provider('claude-3-sonnet') == ('anthropic', 'claude-3-sonnet')
    
    def test_google_models(self):
        """Test Google model resolution."""
        from praisonai.cli.features.profiler import resolve_model_provider
        
        assert resolve_model_provider('gemini-pro') == ('google', 'gemini-pro')
        assert resolve_model_provider('gemini-1.5-flash') == ('google', 'gemini-1.5-flash')
    
    def test_explicit_provider(self):
        """Test explicit provider/model format."""
        from praisonai.cli.features.profiler import resolve_model_provider
        
        assert resolve_model_provider('openai/gpt-4') == ('openai', 'gpt-4')
        assert resolve_model_provider('anthropic/claude-3') == ('anthropic', 'claude-3')
    
    def test_caching(self):
        """Test that results are cached."""
        from praisonai.cli.features.profiler import resolve_model_provider
        
        # Clear cache
        resolve_model_provider.cache_clear()
        
        # First call
        result1 = resolve_model_provider('gpt-4o')
        # Second call (should be cached)
        result2 = resolve_model_provider('gpt-4o')
        
        assert result1 == result2
        
        # Check cache info
        info = resolve_model_provider.cache_info()
        assert info.hits >= 1


class TestLazyImporter:
    """Tests for LazyImporter (Tier 0)."""
    
    def test_import_module(self):
        """Test lazy module import."""
        from praisonai.cli.features.profiler import LazyImporter
        
        LazyImporter.clear()
        
        # Import a standard library module
        json_module = LazyImporter.get('json')
        assert json_module is not None
        assert hasattr(json_module, 'dumps')
    
    def test_import_attribute(self):
        """Test lazy attribute import."""
        from praisonai.cli.features.profiler import LazyImporter
        
        LazyImporter.clear()
        
        # Import a specific attribute
        Path = LazyImporter.get('pathlib', 'Path')
        assert Path is not None
        assert callable(Path)
    
    def test_caching(self):
        """Test that imports are cached."""
        from praisonai.cli.features.profiler import LazyImporter
        
        LazyImporter.clear()
        
        # First import
        json1 = LazyImporter.get('json')
        # Second import (should be cached)
        json2 = LazyImporter.get('json')
        
        assert json1 is json2


class TestClientPool:
    """Tests for ClientPool (Tier 1)."""
    
    def test_get_or_create(self):
        """Test client creation and reuse."""
        from praisonai.cli.features.profiler import ClientPool
        
        pool = ClientPool(max_size=5)
        
        # Create client
        client1 = pool.get_or_create('key1', lambda: {'id': 1})
        assert client1 == {'id': 1}
        
        # Reuse client
        client2 = pool.get_or_create('key1', lambda: {'id': 2})
        assert client2 == {'id': 1}  # Same as first
    
    def test_eviction(self):
        """Test LRU eviction when pool is full."""
        from praisonai.cli.features.profiler import ClientPool
        
        pool = ClientPool(max_size=2)
        
        pool.get_or_create('key1', lambda: 'client1')
        pool.get_or_create('key2', lambda: 'client2')
        
        assert pool.size() == 2
        
        # This should evict key1 (oldest)
        pool.get_or_create('key3', lambda: 'client3')
        
        assert pool.size() == 2
    
    def test_remove(self):
        """Test explicit client removal."""
        from praisonai.cli.features.profiler import ClientPool
        
        pool = ClientPool()
        pool.get_or_create('key1', lambda: 'client1')
        
        assert pool.size() == 1
        
        pool.remove('key1')
        
        assert pool.size() == 0
    
    def test_clear(self):
        """Test clearing all clients."""
        from praisonai.cli.features.profiler import ClientPool
        
        pool = ClientPool()
        pool.get_or_create('key1', lambda: 'client1')
        pool.get_or_create('key2', lambda: 'client2')
        
        pool.clear()
        
        assert pool.size() == 0


class TestPrewarmManager:
    """Tests for PrewarmManager (Tier 1)."""
    
    def test_enable_disable(self):
        """Test enabling and disabling prewarm."""
        from praisonai.cli.features.profiler import PrewarmManager
        
        PrewarmManager.reset()
        
        assert not PrewarmManager.is_enabled()
        
        PrewarmManager.enable()
        assert PrewarmManager.is_enabled()
        
        PrewarmManager.disable()
        assert not PrewarmManager.is_enabled()
    
    def test_prewarm_disabled(self):
        """Test that prewarm does nothing when disabled."""
        from praisonai.cli.features.profiler import PrewarmManager
        
        PrewarmManager.reset()
        
        # Should not raise even without API key
        PrewarmManager.prewarm_provider('openai')
        
        assert not PrewarmManager.is_prewarmed('openai')
    
    def test_reset(self):
        """Test reset clears state."""
        from praisonai.cli.features.profiler import PrewarmManager
        
        PrewarmManager.enable()
        PrewarmManager.reset()
        
        assert not PrewarmManager.is_enabled()


class TestLiteModeConfig:
    """Tests for LiteModeConfig (Tier 2)."""
    
    def test_default_disabled(self):
        """Test that lite mode is disabled by default."""
        from praisonai.cli.features.profiler import LiteModeConfig
        
        config = LiteModeConfig()
        
        assert not config.enabled
        assert not config.skip_type_validation
        assert not config.skip_model_validation
        assert not config.minimal_imports
    
    def test_from_env(self):
        """Test loading config from environment."""
        from praisonai.cli.features.profiler import LiteModeConfig
        
        with patch.dict(os.environ, {
            'PRAISONAI_LITE_MODE': '1',
            'PRAISONAI_SKIP_TYPE_VALIDATION': 'true',
        }):
            config = LiteModeConfig.from_env()
            
            assert config.enabled
            assert config.skip_type_validation
            assert not config.skip_model_validation
    
    def test_is_lite_mode(self):
        """Test is_lite_mode helper."""
        from praisonai.cli.features.profiler import is_lite_mode
        
        # Reset global config
        import praisonai.cli.features.profiler.optimizations as opt
        opt._lite_mode_config = None
        
        with patch.dict(os.environ, {'PRAISONAI_LITE_MODE': ''}, clear=False):
            # Force reload
            opt._lite_mode_config = None
            assert not is_lite_mode()


class TestPerfSnapshot:
    """Tests for PerfSnapshot (Tier 2)."""
    
    def test_to_dict(self):
        """Test snapshot serialization."""
        from praisonai.cli.features.profiler import PerfSnapshot
        
        snapshot = PerfSnapshot(
            timestamp='2025-01-01T00:00:00Z',
            name='test',
            startup_cold_ms=100.0,
            startup_warm_ms=80.0,
            import_time_ms=500.0,
            query_time_ms=2000.0,
            first_token_ms=300.0,
        )
        
        data = snapshot.to_dict()
        
        assert data['name'] == 'test'
        assert data['startup_cold_ms'] == 100.0
        assert data['query_time_ms'] == 2000.0
    
    def test_from_dict(self):
        """Test snapshot deserialization."""
        from praisonai.cli.features.profiler import PerfSnapshot
        
        data = {
            'timestamp': '2025-01-01T00:00:00Z',
            'name': 'test',
            'startup_cold_ms': 100.0,
            'startup_warm_ms': 80.0,
            'import_time_ms': 500.0,
            'query_time_ms': 2000.0,
            'first_token_ms': 300.0,
        }
        
        snapshot = PerfSnapshot.from_dict(data)
        
        assert snapshot.name == 'test'
        assert snapshot.startup_cold_ms == 100.0


class TestPerfComparison:
    """Tests for PerfComparison (Tier 2)."""
    
    def test_diff_calculation(self):
        """Test difference calculations."""
        from praisonai.cli.features.profiler import PerfSnapshot, PerfComparison
        
        baseline = PerfSnapshot(
            timestamp='2025-01-01T00:00:00Z',
            name='baseline',
            startup_cold_ms=100.0,
            startup_warm_ms=80.0,
            import_time_ms=500.0,
            query_time_ms=2000.0,
            first_token_ms=300.0,
        )
        
        current = PerfSnapshot(
            timestamp='2025-01-02T00:00:00Z',
            name='current',
            startup_cold_ms=110.0,  # 10% slower
            startup_warm_ms=85.0,
            import_time_ms=550.0,  # 10% slower
            query_time_ms=2200.0,  # 10% slower
            first_token_ms=330.0,
        )
        
        comparison = PerfComparison(baseline=baseline, current=current)
        
        assert comparison.startup_cold_diff_ms == 10.0
        assert comparison.startup_cold_diff_pct == 10.0
        assert comparison.import_time_diff_ms == 50.0
        assert comparison.query_time_diff_ms == 200.0
    
    def test_regression_detection(self):
        """Test regression detection."""
        from praisonai.cli.features.profiler import PerfSnapshot, PerfComparison
        
        baseline = PerfSnapshot(
            timestamp='2025-01-01T00:00:00Z',
            name='baseline',
            startup_cold_ms=100.0,
            startup_warm_ms=80.0,
            import_time_ms=500.0,
            query_time_ms=2000.0,
            first_token_ms=300.0,
        )
        
        # No regression (within 10%)
        current_ok = PerfSnapshot(
            timestamp='2025-01-02T00:00:00Z',
            name='current',
            startup_cold_ms=105.0,
            startup_warm_ms=82.0,
            import_time_ms=520.0,
            query_time_ms=2100.0,
            first_token_ms=310.0,
        )
        
        comparison_ok = PerfComparison(baseline=baseline, current=current_ok)
        assert not comparison_ok.is_regression()
        
        # Regression (>10%)
        current_bad = PerfSnapshot(
            timestamp='2025-01-02T00:00:00Z',
            name='current',
            startup_cold_ms=150.0,  # 50% slower
            startup_warm_ms=82.0,
            import_time_ms=520.0,
            query_time_ms=2100.0,
            first_token_ms=310.0,
        )
        
        comparison_bad = PerfComparison(baseline=baseline, current=current_bad)
        assert comparison_bad.is_regression()


class TestPerfSnapshotManager:
    """Tests for PerfSnapshotManager (Tier 2)."""
    
    def test_save_and_load(self):
        """Test saving and loading snapshots."""
        from praisonai.cli.features.profiler import PerfSnapshot, PerfSnapshotManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PerfSnapshotManager(snapshot_dir=Path(tmpdir))
            
            snapshot = PerfSnapshot(
                timestamp='2025-01-01T00:00:00Z',
                name='test',
                startup_cold_ms=100.0,
                startup_warm_ms=80.0,
                import_time_ms=500.0,
                query_time_ms=2000.0,
                first_token_ms=300.0,
            )
            
            path = manager.save(snapshot)
            assert path.exists()
            
            loaded = manager.load('test')
            assert loaded is not None
            assert loaded.name == 'test'
            assert loaded.startup_cold_ms == 100.0
    
    def test_baseline(self):
        """Test baseline save and load."""
        from praisonai.cli.features.profiler import PerfSnapshot, PerfSnapshotManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PerfSnapshotManager(snapshot_dir=Path(tmpdir))
            
            snapshot = PerfSnapshot(
                timestamp='2025-01-01T00:00:00Z',
                name='original',
                startup_cold_ms=100.0,
                startup_warm_ms=80.0,
                import_time_ms=500.0,
                query_time_ms=2000.0,
                first_token_ms=300.0,
            )
            
            manager.save_baseline(snapshot)
            
            baseline = manager.load_baseline()
            assert baseline is not None
            assert baseline.name == 'baseline'
    
    def test_list_snapshots(self):
        """Test listing snapshots."""
        from praisonai.cli.features.profiler import PerfSnapshot, PerfSnapshotManager
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = PerfSnapshotManager(snapshot_dir=Path(tmpdir))
            
            for name in ['snap1', 'snap2', 'snap3']:
                snapshot = PerfSnapshot(
                    timestamp='2025-01-01T00:00:00Z',
                    name=name,
                    startup_cold_ms=100.0,
                    startup_warm_ms=80.0,
                    import_time_ms=500.0,
                    query_time_ms=2000.0,
                    first_token_ms=300.0,
                )
                manager.save(snapshot)
            
            names = manager.list_snapshots()
            assert 'snap1' in names
            assert 'snap2' in names
            assert 'snap3' in names


class TestFormatComparisonReport:
    """Tests for format_comparison_report."""
    
    def test_format_report(self):
        """Test report formatting."""
        from praisonai.cli.features.profiler import (
            PerfSnapshot, PerfComparison, format_comparison_report
        )
        
        baseline = PerfSnapshot(
            timestamp='2025-01-01T00:00:00Z',
            name='baseline',
            startup_cold_ms=100.0,
            startup_warm_ms=80.0,
            import_time_ms=500.0,
            query_time_ms=2000.0,
            first_token_ms=300.0,
        )
        
        current = PerfSnapshot(
            timestamp='2025-01-02T00:00:00Z',
            name='current',
            startup_cold_ms=105.0,
            startup_warm_ms=82.0,
            import_time_ms=520.0,
            query_time_ms=2100.0,
            first_token_ms=310.0,
        )
        
        comparison = PerfComparison(baseline=baseline, current=current)
        report = format_comparison_report(comparison)
        
        assert 'Performance Comparison Report' in report
        assert 'baseline' in report
        assert 'current' in report
        assert 'No significant regression' in report


class TestModuleImports:
    """Test that all exports are available."""
    
    def test_all_exports_available(self):
        """Test that all __all__ exports are importable."""
        from praisonai.cli.features.profiler import __all__
        import praisonai.cli.features.profiler as profiler
        
        for name in __all__:
            assert hasattr(profiler, name), f"Missing export: {name}"
