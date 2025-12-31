"""
PraisonAI CLI Profiler Module.

Provides detailed cProfile-based profiling for CLI commands and agent execution.
Supports per-file/per-function timing, call graphs, and import time analysis.

Includes Tier 0/1/2 optimizations:
- Tier 0: Lazy imports, provider caching, CLI startup optimization
- Tier 1: Connection pooling, prewarm hooks (opt-in)
- Tier 2: Lite mode, async init, perf snapshot
"""

from .core import (
    ProfilerConfig,
    ProfilerResult,
    QueryProfiler,
    run_profiled_query,
    format_profile_report,
)

from .suite import (
    ScenarioConfig,
    ScenarioResult,
    SuiteResult,
    ProfileSuiteRunner,
    run_profile_suite,
)

from .optimizations import (
    # Tier 0
    ProviderCache,
    get_provider_cache,
    resolve_model_provider,
    LazyImporter,
    # Tier 1
    ClientPool,
    get_client_pool,
    PrewarmManager,
    # Tier 2
    LiteModeConfig,
    get_lite_mode_config,
    is_lite_mode,
    PerfSnapshot,
    PerfComparison,
    PerfSnapshotManager,
    create_snapshot_from_suite,
    format_comparison_report,
)

__all__ = [
    # Core profiler
    'ProfilerConfig',
    'ProfilerResult', 
    'QueryProfiler',
    'run_profiled_query',
    'format_profile_report',
    # Suite runner
    'ScenarioConfig',
    'ScenarioResult',
    'SuiteResult',
    'ProfileSuiteRunner',
    'run_profile_suite',
    # Tier 0 optimizations
    'ProviderCache',
    'get_provider_cache',
    'resolve_model_provider',
    'LazyImporter',
    # Tier 1 optimizations
    'ClientPool',
    'get_client_pool',
    'PrewarmManager',
    # Tier 2 optimizations
    'LiteModeConfig',
    'get_lite_mode_config',
    'is_lite_mode',
    'PerfSnapshot',
    'PerfComparison',
    'PerfSnapshotManager',
    'create_snapshot_from_suite',
    'format_comparison_report',
]
