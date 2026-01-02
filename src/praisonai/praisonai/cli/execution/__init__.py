"""
PraisonAI Unified Execution Module.

Provides a single, unified execution primitive for all CLI modes:
- CLI direct prompt
- Profile command
- TUI workers

Design Principles:
1. Profiling observes, never alters execution
2. Zero overhead when profiling disabled
3. Sync and async are first-class citizens
4. Fail-safe, not fail-fast
5. Bounded resource usage
6. Schema stability with versioning
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .request import ExecutionRequest
    from .result import ExecutionResult
    from .core import execute_sync, execute_async
    from .profiler import Profiler, ProfilerConfig, ProfileReport

# Lazy loading to maintain zero-overhead when not used
_lazy_cache = {}


def __getattr__(name: str):
    """Lazy load execution components."""
    global _lazy_cache
    
    if name in _lazy_cache:
        return _lazy_cache[name]
    
    if name == "ExecutionRequest":
        from .request import ExecutionRequest
        _lazy_cache[name] = ExecutionRequest
        return ExecutionRequest
    elif name == "ExecutionResult":
        from .result import ExecutionResult
        _lazy_cache[name] = ExecutionResult
        return ExecutionResult
    elif name == "execute_sync":
        from .core import execute_sync
        _lazy_cache[name] = execute_sync
        return execute_sync
    elif name == "execute_async":
        from .core import execute_async
        _lazy_cache[name] = execute_async
        return execute_async
    elif name == "Profiler":
        from .profiler import Profiler
        _lazy_cache[name] = Profiler
        return Profiler
    elif name == "ProfilerConfig":
        from .profiler import ProfilerConfig
        _lazy_cache[name] = ProfilerConfig
        return ProfilerConfig
    elif name == "ProfileReport":
        from .profiler import ProfileReport
        _lazy_cache[name] = ProfileReport
        return ProfileReport
    elif name == "TimingBreakdown":
        from .profiler import TimingBreakdown
        _lazy_cache[name] = TimingBreakdown
        return TimingBreakdown
    elif name == "InvocationInfo":
        from .profiler import InvocationInfo
        _lazy_cache[name] = InvocationInfo
        return InvocationInfo
    elif name == "DecisionTrace":
        from .profiler import DecisionTrace
        _lazy_cache[name] = DecisionTrace
        return DecisionTrace
    elif name == "ModuleBreakdown":
        from .profiler import ModuleBreakdown
        _lazy_cache[name] = ModuleBreakdown
        return ModuleBreakdown
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Core execution
    "ExecutionRequest",
    "ExecutionResult",
    "execute_sync",
    "execute_async",
    # Profiling
    "Profiler",
    "ProfilerConfig",
    "ProfileReport",
    "TimingBreakdown",
    "InvocationInfo",
    "DecisionTrace",
    "ModuleBreakdown",
]
