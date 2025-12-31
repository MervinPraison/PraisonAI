"""
Performance Optimization Example for PraisonAI

This example demonstrates how to use the Tier 0/1/2 optimization features
programmatically.

Run with:
    python optimization_example.py
"""

import os

# Ensure API key is set
if not os.environ.get("OPENAI_API_KEY"):
    print("Please set OPENAI_API_KEY environment variable")
    exit(1)


def demo_provider_cache():
    """Demonstrate provider caching (Tier 0)."""
    print("\n" + "=" * 60)
    print("Tier 0: Provider Cache Demo")
    print("=" * 60)
    
    from praisonai.cli.features.profiler import (
        get_provider_cache,
        resolve_model_provider,
    )
    
    cache = get_provider_cache()
    cache.invalidate()  # Start fresh
    
    # Resolve some models
    models = ['gpt-4o', 'claude-3-opus', 'gemini-pro', 'gpt-4o-mini']
    
    print("\nResolving models:")
    for model in models:
        provider, name = resolve_model_provider(model)
        print(f"  {model} -> {provider}/{name}")
    
    # Check cache stats
    stats = cache.get_stats()
    print("\nCache Stats:")
    print(f"  Hits: {stats['hits']}")
    print(f"  Misses: {stats['misses']}")
    print(f"  Size: {stats['size']}")


def demo_lazy_importer():
    """Demonstrate lazy imports (Tier 0)."""
    print("\n" + "=" * 60)
    print("Tier 0: Lazy Importer Demo")
    print("=" * 60)
    
    from praisonai.cli.features.profiler import LazyImporter
    import time
    
    LazyImporter.clear()
    
    # Time lazy import
    start = time.perf_counter()
    json_module = LazyImporter.get('json')
    first_import = (time.perf_counter() - start) * 1000
    
    # Second import (cached)
    start = time.perf_counter()
    json_module2 = LazyImporter.get('json')
    cached_import = (time.perf_counter() - start) * 1000
    
    print(f"\nFirst import: {first_import:.3f}ms")
    print(f"Cached import: {cached_import:.3f}ms")
    print(f"Same object: {json_module is json_module2}")


def demo_client_pool():
    """Demonstrate client pooling (Tier 1)."""
    print("\n" + "=" * 60)
    print("Tier 1: Client Pool Demo")
    print("=" * 60)
    
    from praisonai.cli.features.profiler import ClientPool
    
    pool = ClientPool(max_size=3)
    
    # Create some mock clients
    def create_client(name):
        return {'name': name, 'created': True}
    
    # Get or create clients
    client1 = pool.get_or_create('openai', lambda: create_client('openai'))
    _ = pool.get_or_create('anthropic', lambda: create_client('anthropic'))
    
    # Reuse existing client
    client1_again = pool.get_or_create('openai', lambda: create_client('openai_new'))
    
    print(f"\nPool size: {pool.size()}")
    print(f"Client reused: {client1 is client1_again}")
    print(f"Client1 name: {client1['name']}")


def demo_prewarm():
    """Demonstrate pre-warming (Tier 1)."""
    print("\n" + "=" * 60)
    print("Tier 1: Pre-warming Demo")
    print("=" * 60)
    
    from praisonai.cli.features.profiler import PrewarmManager
    import time
    
    PrewarmManager.reset()
    
    print(f"\nPre-warming enabled: {PrewarmManager.is_enabled()}")
    
    # Enable and prewarm
    PrewarmManager.enable()
    print(f"After enable: {PrewarmManager.is_enabled()}")
    
    # Prewarm OpenAI (runs in background)
    PrewarmManager.prewarm_provider('openai')
    print("Pre-warming OpenAI in background...")
    
    # Wait a bit for background thread
    time.sleep(0.5)
    
    print(f"OpenAI prewarmed: {PrewarmManager.is_prewarmed('openai')}")
    
    PrewarmManager.reset()


def demo_lite_mode():
    """Demonstrate lite mode (Tier 2)."""
    print("\n" + "=" * 60)
    print("Tier 2: Lite Mode Demo")
    print("=" * 60)
    
    from praisonai.cli.features.profiler import (
        LiteModeConfig,
        is_lite_mode,
    )
    
    # Default config
    config = LiteModeConfig()
    print(f"\nDefault lite mode: {config.enabled}")
    
    # Config from env
    print("\nTo enable lite mode, set environment variables:")
    print("  export PRAISONAI_LITE_MODE=1")
    print("  export PRAISONAI_SKIP_TYPE_VALIDATION=1")
    
    print(f"\nCurrent is_lite_mode(): {is_lite_mode()}")


def demo_perf_snapshot():
    """Demonstrate performance snapshots (Tier 2)."""
    print("\n" + "=" * 60)
    print("Tier 2: Performance Snapshot Demo")
    print("=" * 60)
    
    from praisonai.cli.features.profiler import (
        PerfSnapshot,
        PerfComparison,
        PerfSnapshotManager,
    )
    import tempfile
    from pathlib import Path
    
    # Create manager with temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = PerfSnapshotManager(snapshot_dir=Path(tmpdir))
        
        # Create baseline
        baseline = PerfSnapshot(
            timestamp='2025-01-01T00:00:00Z',
            name='baseline',
            startup_cold_ms=100.0,
            startup_warm_ms=80.0,
            import_time_ms=500.0,
            query_time_ms=2000.0,
            first_token_ms=300.0,
        )
        manager.save_baseline(baseline)
        print("\nBaseline saved")
        
        # Create current snapshot (simulated improvement)
        current = PerfSnapshot(
            timestamp='2025-01-02T00:00:00Z',
            name='current',
            startup_cold_ms=95.0,  # 5% faster
            startup_warm_ms=78.0,
            import_time_ms=480.0,  # 4% faster
            query_time_ms=1900.0,  # 5% faster
            first_token_ms=280.0,
        )
        
        # Compare
        comparison = PerfComparison(baseline=baseline, current=current)
        
        print(f"\nStartup improvement: {-comparison.startup_cold_diff_pct:.1f}%")
        print(f"Import improvement: {-comparison.import_time_diff_pct:.1f}%")
        print(f"Query improvement: {-comparison.query_time_diff_pct:.1f}%")
        print(f"Is regression: {comparison.is_regression()}")


def main():
    """Run all demos."""
    print("=" * 60)
    print("PraisonAI Performance Optimization Demo")
    print("=" * 60)
    
    demo_provider_cache()
    demo_lazy_importer()
    demo_client_pool()
    demo_prewarm()
    demo_lite_mode()
    demo_perf_snapshot()
    
    print("\n" + "=" * 60)
    print("All demos complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
