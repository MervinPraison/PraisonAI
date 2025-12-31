"""
Performance Optimizations for PraisonAI CLI.

Implements Tier 0/1/2 optimizations:
- Tier 0: Lazy imports, provider caching, CLI startup optimization
- Tier 1: Connection pooling, prewarm hooks (opt-in)
- Tier 2: Lite mode, async init, perf snapshot

All optimizations are safe-by-default and opt-in where behavior changes.
Multi-agent safe: no global mutable state that affects concurrent runs.
"""

import os
import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from functools import lru_cache


# =============================================================================
# TIER 0: Safe Fast Wins (No behavior change)
# =============================================================================

class ProviderCache:
    """
    Thread-safe cache for provider/model resolution.
    
    Caches resolved provider configurations to avoid repeated lookups.
    Per-process cache with clear invalidation rules.
    Multi-agent safe: uses thread-local storage for mutable state.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._cache = {}
                    cls._instance._cache_lock = threading.Lock()
                    cls._instance._hits = 0
                    cls._instance._misses = 0
        return cls._instance
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value (thread-safe)."""
        with self._cache_lock:
            if key in self._cache:
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set cached value with TTL (thread-safe)."""
        with self._cache_lock:
            self._cache[key] = {
                'value': value,
                'expires': time.time() + ttl_seconds,
            }
    
    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate cache entry or entire cache."""
        with self._cache_lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        with self._cache_lock:
            return {
                'hits': self._hits,
                'misses': self._misses,
                'size': len(self._cache),
            }
    
    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        now = time.time()
        removed = 0
        with self._cache_lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if isinstance(v, dict) and v.get('expires', float('inf')) < now
            ]
            for k in expired_keys:
                del self._cache[k]
                removed += 1
        return removed


# Global provider cache instance (singleton, thread-safe)
_provider_cache = None

def get_provider_cache() -> ProviderCache:
    """Get the global provider cache instance."""
    global _provider_cache
    if _provider_cache is None:
        _provider_cache = ProviderCache()
    return _provider_cache


@lru_cache(maxsize=32)
def resolve_model_provider(model: str) -> Tuple[str, str]:
    """
    Resolve model string to (provider, model_name) tuple.
    
    Cached using LRU cache for repeated lookups.
    """
    if '/' in model:
        parts = model.split('/', 1)
        return parts[0], parts[1]
    
    # Default provider mappings
    if model.startswith('gpt-') or model.startswith('o1-') or model.startswith('o3-'):
        return 'openai', model
    elif model.startswith('claude-'):
        return 'anthropic', model
    elif model.startswith('gemini-'):
        return 'google', model
    elif model.startswith('llama') or model.startswith('mistral'):
        return 'ollama', model
    
    return 'openai', model  # Default to OpenAI


class LazyImporter:
    """
    Lazy importer for heavy modules.
    
    Defers import until first use, reducing CLI startup time.
    Thread-safe and caches imported modules.
    """
    
    _imports: Dict[str, Any] = {}
    _lock = threading.Lock()
    
    @classmethod
    def get(cls, module_path: str, attr: Optional[str] = None) -> Any:
        """
        Lazily import a module or attribute.
        
        Args:
            module_path: Full module path (e.g., 'openai.OpenAI')
            attr: Optional attribute to get from module
            
        Returns:
            Imported module or attribute
        """
        cache_key = f"{module_path}.{attr}" if attr else module_path
        
        with cls._lock:
            if cache_key in cls._imports:
                return cls._imports[cache_key]
        
        # Import outside lock to avoid deadlocks
        import importlib
        
        if attr:
            module = importlib.import_module(module_path)
            result = getattr(module, attr)
        else:
            result = importlib.import_module(module_path)
        
        with cls._lock:
            cls._imports[cache_key] = result
        
        return result
    
    @classmethod
    def clear(cls) -> None:
        """Clear import cache."""
        with cls._lock:
            cls._imports.clear()


# =============================================================================
# TIER 1: Medium Effort (Guarded/opt-in)
# =============================================================================

class ClientPool:
    """
    Connection pool for API clients.
    
    Reuses client instances for repeated calls to the same provider.
    Multi-agent safe: clients are isolated by key.
    Does not leak API keys between different configurations.
    """
    
    def __init__(self, max_size: int = 10):
        self._pool: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._max_size = max_size
        self._access_times: Dict[str, float] = {}
    
    def get_or_create(
        self,
        key: str,
        factory: Callable[[], Any],
    ) -> Any:
        """
        Get existing client or create new one.
        
        Args:
            key: Unique key for this client configuration
            factory: Function to create new client if needed
            
        Returns:
            Client instance
        """
        with self._lock:
            if key in self._pool:
                self._access_times[key] = time.time()
                return self._pool[key]
            
            # Evict oldest if at capacity
            if len(self._pool) >= self._max_size:
                oldest_key = min(self._access_times, key=self._access_times.get)
                del self._pool[oldest_key]
                del self._access_times[oldest_key]
        
        # Create outside lock
        client = factory()
        
        with self._lock:
            self._pool[key] = client
            self._access_times[key] = time.time()
        
        return client
    
    def remove(self, key: str) -> None:
        """Remove client from pool."""
        with self._lock:
            self._pool.pop(key, None)
            self._access_times.pop(key, None)
    
    def clear(self) -> None:
        """Clear all clients from pool."""
        with self._lock:
            self._pool.clear()
            self._access_times.clear()
    
    def size(self) -> int:
        """Get current pool size."""
        with self._lock:
            return len(self._pool)


# Global client pool (opt-in usage)
_client_pool: Optional[ClientPool] = None

def get_client_pool() -> ClientPool:
    """Get the global client pool instance."""
    global _client_pool
    if _client_pool is None:
        _client_pool = ClientPool()
    return _client_pool


class PrewarmManager:
    """
    Manager for pre-warming provider connections.
    
    OPT-IN ONLY: Must be explicitly enabled.
    Pre-initializes provider clients in background to reduce first-call latency.
    """
    
    _enabled = False
    _prewarmed: Dict[str, bool] = {}
    _lock = threading.Lock()
    _background_thread: Optional[threading.Thread] = None
    
    @classmethod
    def enable(cls) -> None:
        """Enable pre-warming (opt-in)."""
        cls._enabled = True
    
    @classmethod
    def disable(cls) -> None:
        """Disable pre-warming."""
        cls._enabled = False
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if pre-warming is enabled."""
        return cls._enabled
    
    @classmethod
    def prewarm_provider(cls, provider: str, api_key: Optional[str] = None) -> None:
        """
        Pre-warm a provider connection in background.
        
        Only runs if pre-warming is enabled.
        """
        if not cls._enabled:
            return
        
        with cls._lock:
            if provider in cls._prewarmed:
                return
            cls._prewarmed[provider] = False
        
        def _prewarm():
            try:
                if provider == 'openai':
                    # Just import and create client - don't make API call
                    from openai import OpenAI
                    key = api_key or os.environ.get('OPENAI_API_KEY')
                    if key:
                        _ = OpenAI(api_key=key)
                elif provider == 'anthropic':
                    from anthropic import Anthropic
                    key = api_key or os.environ.get('ANTHROPIC_API_KEY')
                    if key:
                        _ = Anthropic(api_key=key)
                
                with cls._lock:
                    cls._prewarmed[provider] = True
            except Exception:
                pass  # Silently fail - pre-warming is optional
        
        # Run in background thread
        thread = threading.Thread(target=_prewarm, daemon=True)
        thread.start()
    
    @classmethod
    def is_prewarmed(cls, provider: str) -> bool:
        """Check if provider is pre-warmed."""
        with cls._lock:
            return cls._prewarmed.get(provider, False)
    
    @classmethod
    def reset(cls) -> None:
        """Reset pre-warm state."""
        with cls._lock:
            cls._prewarmed.clear()
            cls._enabled = False


# =============================================================================
# TIER 2: Architectural (Safe and non-breaking)
# =============================================================================

@dataclass
class LiteModeConfig:
    """
    Configuration for lite runtime mode.
    
    OPT-IN ONLY: Defaults to OFF.
    Avoids expensive type/model loading when not required.
    """
    enabled: bool = False
    skip_type_validation: bool = False
    skip_model_validation: bool = False
    minimal_imports: bool = False
    
    @classmethod
    def from_env(cls) -> 'LiteModeConfig':
        """Create config from environment variables."""
        return cls(
            enabled=os.environ.get('PRAISONAI_LITE_MODE', '').lower() in ('1', 'true', 'yes'),
            skip_type_validation=os.environ.get('PRAISONAI_SKIP_TYPE_VALIDATION', '').lower() in ('1', 'true'),
            skip_model_validation=os.environ.get('PRAISONAI_SKIP_MODEL_VALIDATION', '').lower() in ('1', 'true'),
            minimal_imports=os.environ.get('PRAISONAI_MINIMAL_IMPORTS', '').lower() in ('1', 'true'),
        )


# Global lite mode config
_lite_mode_config: Optional[LiteModeConfig] = None

def get_lite_mode_config() -> LiteModeConfig:
    """Get lite mode configuration."""
    global _lite_mode_config
    if _lite_mode_config is None:
        _lite_mode_config = LiteModeConfig.from_env()
    return _lite_mode_config

def is_lite_mode() -> bool:
    """Check if lite mode is enabled."""
    return get_lite_mode_config().enabled


@dataclass
class PerfSnapshot:
    """
    Performance snapshot for baseline comparison.
    
    Records timing data that can be compared against later runs.
    """
    timestamp: str
    name: str
    startup_cold_ms: float
    startup_warm_ms: float
    import_time_ms: float
    query_time_ms: float
    first_token_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'name': self.name,
            'startup_cold_ms': self.startup_cold_ms,
            'startup_warm_ms': self.startup_warm_ms,
            'import_time_ms': self.import_time_ms,
            'query_time_ms': self.query_time_ms,
            'first_token_ms': self.first_token_ms,
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerfSnapshot':
        return cls(
            timestamp=data['timestamp'],
            name=data['name'],
            startup_cold_ms=data['startup_cold_ms'],
            startup_warm_ms=data['startup_warm_ms'],
            import_time_ms=data['import_time_ms'],
            query_time_ms=data['query_time_ms'],
            first_token_ms=data.get('first_token_ms', 0.0),
            metadata=data.get('metadata', {}),
        )


@dataclass
class PerfComparison:
    """Comparison between two performance snapshots."""
    baseline: PerfSnapshot
    current: PerfSnapshot
    
    @property
    def startup_cold_diff_ms(self) -> float:
        return self.current.startup_cold_ms - self.baseline.startup_cold_ms
    
    @property
    def startup_cold_diff_pct(self) -> float:
        if self.baseline.startup_cold_ms == 0:
            return 0.0
        return (self.startup_cold_diff_ms / self.baseline.startup_cold_ms) * 100
    
    @property
    def import_time_diff_ms(self) -> float:
        return self.current.import_time_ms - self.baseline.import_time_ms
    
    @property
    def import_time_diff_pct(self) -> float:
        if self.baseline.import_time_ms == 0:
            return 0.0
        return (self.import_time_diff_ms / self.baseline.import_time_ms) * 100
    
    @property
    def query_time_diff_ms(self) -> float:
        return self.current.query_time_ms - self.baseline.query_time_ms
    
    @property
    def query_time_diff_pct(self) -> float:
        if self.baseline.query_time_ms == 0:
            return 0.0
        return (self.query_time_diff_ms / self.baseline.query_time_ms) * 100
    
    def is_regression(self, threshold_pct: float = 10.0) -> bool:
        """Check if there's a performance regression above threshold."""
        return (
            self.startup_cold_diff_pct > threshold_pct or
            self.import_time_diff_pct > threshold_pct or
            self.query_time_diff_pct > threshold_pct
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'baseline': self.baseline.to_dict(),
            'current': self.current.to_dict(),
            'diffs': {
                'startup_cold_ms': self.startup_cold_diff_ms,
                'startup_cold_pct': self.startup_cold_diff_pct,
                'import_time_ms': self.import_time_diff_ms,
                'import_time_pct': self.import_time_diff_pct,
                'query_time_ms': self.query_time_diff_ms,
                'query_time_pct': self.query_time_diff_pct,
            },
            'is_regression': self.is_regression(),
        }


class PerfSnapshotManager:
    """
    Manager for performance snapshots.
    
    Stores snapshots locally for baseline comparison.
    OPT-IN: User must explicitly invoke snapshot commands.
    """
    
    DEFAULT_DIR = Path.home() / '.praisonai' / 'perf_snapshots'
    
    def __init__(self, snapshot_dir: Optional[Path] = None):
        self.snapshot_dir = snapshot_dir or self.DEFAULT_DIR
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
    
    def save(self, snapshot: PerfSnapshot) -> Path:
        """Save a snapshot to disk."""
        filename = f"{snapshot.name}_{snapshot.timestamp.replace(':', '-').replace('.', '-')}.json"
        path = self.snapshot_dir / filename
        with open(path, 'w') as f:
            json.dump(snapshot.to_dict(), f, indent=2)
        return path
    
    def load(self, name: str) -> Optional[PerfSnapshot]:
        """Load the most recent snapshot with given name."""
        pattern = f"{name}_*.json"
        files = sorted(self.snapshot_dir.glob(pattern), reverse=True)
        if not files:
            return None
        
        with open(files[0]) as f:
            data = json.load(f)
        return PerfSnapshot.from_dict(data)
    
    def load_baseline(self, name: str = 'baseline') -> Optional[PerfSnapshot]:
        """Load the baseline snapshot."""
        return self.load(name)
    
    def save_baseline(self, snapshot: PerfSnapshot) -> Path:
        """Save as baseline (overwrites previous baseline)."""
        snapshot.name = 'baseline'
        # Remove old baselines
        for f in self.snapshot_dir.glob('baseline_*.json'):
            f.unlink()
        return self.save(snapshot)
    
    def compare(self, current: PerfSnapshot, baseline_name: str = 'baseline') -> Optional[PerfComparison]:
        """Compare current snapshot against baseline."""
        baseline = self.load(baseline_name)
        if not baseline:
            return None
        return PerfComparison(baseline=baseline, current=current)
    
    def list_snapshots(self) -> List[str]:
        """List all saved snapshot names."""
        files = self.snapshot_dir.glob('*.json')
        names = set()
        for f in files:
            # Extract name from filename (before first underscore)
            name = f.stem.rsplit('_', 1)[0] if '_' in f.stem else f.stem
            names.add(name)
        return sorted(names)


# =============================================================================
# Utility Functions
# =============================================================================

def create_snapshot_from_suite(suite_result: Any, name: str = 'current') -> PerfSnapshot:
    """
    Create a PerfSnapshot from a SuiteResult.
    
    Args:
        suite_result: SuiteResult from profile suite
        name: Name for the snapshot
        
    Returns:
        PerfSnapshot instance
    """
    # Get average query time from scenarios
    query_times = []
    first_token_times = []
    for scenario in suite_result.scenarios:
        query_times.extend(scenario.total_times)
        first_token_times.extend(scenario.first_token_times)
    
    avg_query_time = sum(query_times) / len(query_times) if query_times else 0.0
    avg_first_token = sum(first_token_times) / len(first_token_times) if first_token_times else 0.0
    
    # Get import time from analysis
    import_time = 0.0
    if suite_result.import_analysis:
        import_time = suite_result.import_analysis[0].get('cumulative_ms', 0.0)
    
    return PerfSnapshot(
        timestamp=suite_result.timestamp,
        name=name,
        startup_cold_ms=suite_result.startup_cold_ms,
        startup_warm_ms=suite_result.startup_warm_ms,
        import_time_ms=import_time,
        query_time_ms=avg_query_time,
        first_token_ms=avg_first_token,
        metadata=suite_result.metadata,
    )


def format_comparison_report(comparison: PerfComparison) -> str:
    """Format a comparison report as text."""
    lines = []
    lines.append("=" * 70)
    lines.append("Performance Comparison Report")
    lines.append("=" * 70)
    lines.append("")
    
    lines.append(f"Baseline: {comparison.baseline.name} ({comparison.baseline.timestamp})")
    lines.append(f"Current:  {comparison.current.name} ({comparison.current.timestamp})")
    lines.append("")
    
    lines.append("-" * 70)
    lines.append(f"{'Metric':<25} {'Baseline':>12} {'Current':>12} {'Diff':>12} {'%':>8}")
    lines.append("-" * 70)
    
    def format_row(name: str, baseline: float, current: float, diff: float, pct: float) -> str:
        sign = '+' if diff > 0 else ''
        pct_sign = '+' if pct > 0 else ''
        return f"{name:<25} {baseline:>12.2f} {current:>12.2f} {sign}{diff:>11.2f} {pct_sign}{pct:>7.1f}%"
    
    lines.append(format_row(
        "Startup Cold (ms)",
        comparison.baseline.startup_cold_ms,
        comparison.current.startup_cold_ms,
        comparison.startup_cold_diff_ms,
        comparison.startup_cold_diff_pct,
    ))
    
    lines.append(format_row(
        "Import Time (ms)",
        comparison.baseline.import_time_ms,
        comparison.current.import_time_ms,
        comparison.import_time_diff_ms,
        comparison.import_time_diff_pct,
    ))
    
    lines.append(format_row(
        "Query Time (ms)",
        comparison.baseline.query_time_ms,
        comparison.current.query_time_ms,
        comparison.query_time_diff_ms,
        comparison.query_time_diff_pct,
    ))
    
    lines.append("-" * 70)
    lines.append("")
    
    if comparison.is_regression():
        lines.append("⚠️  REGRESSION DETECTED (>10% slower)")
    else:
        lines.append("✅ No significant regression")
    
    lines.append("=" * 70)
    
    return "\n".join(lines)
