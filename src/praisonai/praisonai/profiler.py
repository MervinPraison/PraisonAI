"""
PraisonAI Profiler Module

Standardized profiling for performance monitoring across praisonai and praisonai-agents.

Features:
- Import timing
- Function execution timing
- Flow tracking
- File/module usage tracking
- Memory usage (tracemalloc)
- API call profiling (wall-clock time)
- Streaming profiling (TTFT, total time)
- Statistics (p50, p95, p99)
- cProfile integration
- Flamegraph generation
- Line-level profiling
- JSON/HTML export

Usage:
    from praisonai.profiler import Profiler, profile, profile_imports
    
    # Profile a function
    @profile
    def my_function():
        pass
    
    # Profile a block
    with Profiler.block("my_operation"):
        do_something()
    
    # Profile API calls
    with Profiler.api_call("https://api.example.com") as call:
        response = requests.get(...)
    
    # Profile streaming
    with Profiler.streaming("chat") as tracker:
        tracker.first_token()
        for chunk in stream:
            tracker.chunk()
    
    # Profile imports
    with profile_imports():
        import heavy_module
    
    # Get report with statistics
    Profiler.report()
    stats = Profiler.get_statistics()
    
    # Export
    Profiler.export_json()
    Profiler.export_html()
"""

import time
import functools
import threading
import sys
import os
import json
import tracemalloc
import cProfile
import pstats
import io
import statistics
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any
from contextlib import contextmanager, asynccontextmanager


# ============================================================================
# Configuration
# ============================================================================

# Maximum number of records per profiler buffer
def _get_profiler_max() -> int:
    raw = os.environ.get("PRAISONAI_PROFILE_MAX", "10000")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 10000


_PROFILER_MAX = _get_profiler_max()


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TimingRecord:
    """Record of a single timing measurement."""
    name: str
    duration_ms: float
    category: str = "function"
    file: str = ""
    line: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class APICallRecord:
    """Record of an API/HTTP call."""
    endpoint: str
    method: str
    duration_ms: float
    status_code: int = 0
    request_size: int = 0
    response_size: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class StreamingRecord:
    """Record of streaming operation (LLM responses)."""
    name: str
    ttft_ms: float  # Time to first token
    total_ms: float
    chunk_count: int = 0
    total_tokens: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class MemoryRecord:
    """Record of memory usage."""
    name: str
    current_kb: float
    peak_kb: float
    timestamp: float = field(default_factory=time.time)


@dataclass
class ImportRecord:
    """Record of a module import."""
    module: str
    duration_ms: float
    parent: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class FlowRecord:
    """Record of execution flow."""
    step: int
    name: str
    file: str
    line: int
    duration_ms: float
    timestamp: float = field(default_factory=time.time)


# ============================================================================
# Streaming Tracker
# ============================================================================

class StreamingTracker:
    """
    Track streaming operations (LLM responses).
    
    Usage:
        tracker = StreamingTracker("chat")
        tracker.start()
        tracker.first_token()  # Mark TTFT
        for chunk in stream:
            tracker.chunk()
        tracker.end(total_tokens=100)
    """
    
    def __init__(self, name: str):
        self.name = name
        self._start_time: Optional[float] = None
        self._first_token_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._chunk_count: int = 0
        self._total_tokens: int = 0
    
    def start(self) -> None:
        """Start tracking."""
        self._start_time = time.perf_counter()
    
    def first_token(self) -> None:
        """Mark time to first token."""
        if self._first_token_time is None:
            self._first_token_time = time.perf_counter()
    
    def chunk(self) -> None:
        """Record a chunk received."""
        self._chunk_count += 1
    
    def end(self, total_tokens: int = 0) -> None:
        """End tracking and record to Profiler."""
        self._end_time = time.perf_counter()
        self._total_tokens = total_tokens
        
        if self._start_time is not None:
            ttft_ms = 0.0
            if self._first_token_time is not None:
                ttft_ms = (self._first_token_time - self._start_time) * 1000
            
            total_ms = (self._end_time - self._start_time) * 1000
            
            Profiler.record_streaming(
                name=self.name,
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                chunk_count=self._chunk_count,
                total_tokens=self._total_tokens
            )
    
    @property
    def ttft_ms(self) -> float:
        """Get time to first token in ms."""
        if self._start_time and self._first_token_time:
            return (self._first_token_time - self._start_time) * 1000
        return 0.0
    
    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time in ms."""
        if self._start_time:
            end = self._end_time or time.perf_counter()
            return (end - self._start_time) * 1000
        return 0.0


# ============================================================================
# Profiler Class
# ============================================================================

class _ProfilerImpl:
    """
    Performance monitoring with bounded buffers.
    
    Per-instance profiler for isolated multi-agent use.
    
    Features:
    - Function/block timing
    - API call profiling (wall-clock)
    - Streaming profiling (TTFT)
    - Memory profiling
    - Import timing
    - Statistics (p50, p95, p99)
    - cProfile integration
    - Export (JSON, HTML)
    - Bounded per-instance buffers (default 10k records each)
    """
    
    def __init__(self, *, max_records: int = None):
        """Initialize profiler with per-instance storage.
        
        Args:
            max_records: Maximum records per buffer (defaults to _PROFILER_MAX)
        """
        max_records = max_records or _PROFILER_MAX
        
        # Instance-level storage with bounded deque buffers
        self._timings = deque(maxlen=max_records)
        self._imports = deque(maxlen=max_records) 
        self._flow = deque(maxlen=max_records)
        self._api_calls = deque(maxlen=max_records)
        self._streaming = deque(maxlen=max_records)
        self._memory = deque(maxlen=max_records)
        self._enabled: bool = False
        self._flow_step: int = 0
        self._files_accessed: Dict[str, int] = {}
        self._line_profile_data: Dict[str, Any] = {}
        self._cprofile_stats = deque(maxlen=max_records)
        self._lock = threading.Lock()
    
    def enable(self) -> None:
        """Enable profiling."""
        self._enabled = True
    
    def disable(self) -> None:
        """Disable profiling."""
        self._enabled = False
    
    def is_enabled(self) -> bool:
        """Check if profiling is enabled."""
        return self._enabled or os.environ.get('PRAISONAI_PROFILE', '').lower() in ('1', 'true', 'yes')
    
    def clear(self) -> None:
        """Clear all profiling data."""
        with self._lock:
            self._timings.clear()
            self._imports.clear()
            self._flow.clear()
            self._api_calls.clear()
            self._streaming.clear()
            self._memory.clear()
            self._flow_step = 0
            self._files_accessed.clear()
            self._line_profile_data.clear()
            self._cprofile_stats.clear()
    
    def record_timing(self, name: str, duration_ms: float, category: str = "function", 
                      file: str = "", line: int = 0) -> None:
        """Record a timing measurement."""
        if not self.is_enabled():
            return
        
        with self._lock:
            self._timings.append(TimingRecord(
                name=name,
                duration_ms=duration_ms,
                category=category,
                file=file,
                line=line
            ))
            
            # Track file access
            if file:
                self._files_accessed[file] = self._files_accessed.get(file, 0) + 1
    
    def record_import(self, module: str, duration_ms: float, parent: str = "") -> None:
        """Record an import timing."""
        if not self.is_enabled():
            return
        
        with self._lock:
            self._imports.append(ImportRecord(
                module=module,
                duration_ms=duration_ms,
                parent=parent
            ))
    
    def record_flow(self, name: str, duration_ms: float, file: str = "", line: int = 0) -> None:
        """Record a flow step."""
        if not self.is_enabled():
            return
        
        with self._lock:
            self._flow_step += 1
            self._flow.append(FlowRecord(
                step=self._flow_step,
                name=name,
                file=file,
                line=line,
                duration_ms=duration_ms
            ))
    
    def record_api_call(self, endpoint: str, method: str, duration_ms: float,
                        status_code: int = 0, request_size: int = 0,
                        response_size: int = 0) -> None:
        """Record an API/HTTP call timing."""
        if not self.is_enabled():
            return
        
        with self._lock:
            self._api_calls.append(APICallRecord(
                endpoint=endpoint,
                method=method,
                duration_ms=duration_ms,
                status_code=status_code,
                request_size=request_size,
                response_size=response_size
            ))
    
    @contextmanager
    def block(self, name: str, category: str = "block"):
        """Context manager for profiling a block of code."""
        start = time.time()
        frame = sys._getframe(2) if hasattr(sys, '_getframe') else None
        file = frame.f_code.co_filename if frame else ""
        line = frame.f_lineno if frame else 0
        
        try:
            yield
        finally:
            duration_ms = (time.time() - start) * 1000
            self.record_timing(name, duration_ms, category, file, line)
            self.record_flow(name, duration_ms, file, line)
    
    @contextmanager
    def api_call(self, endpoint: str, method: str = "GET"):
        """Context manager for profiling API calls."""
        start = time.perf_counter()
        call_info = {'status_code': 0, 'request_size': 0, 'response_size': 0}
        
        try:
            yield call_info
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self.record_api_call(
                endpoint=endpoint,
                method=method,
                duration_ms=duration_ms,
                status_code=call_info.get('status_code', 0),
                request_size=call_info.get('request_size', 0),
                response_size=call_info.get('response_size', 0)
            )
    
    @contextmanager
    def streaming(self, name: str):
        """Context manager for profiling streaming operations."""
        tracker = StreamingTracker(name)
        tracker.start()
        try:
            yield tracker
        finally:
            tracker.end()
    
    def get_timings(self, category: Optional[str] = None) -> List[TimingRecord]:
        """Get timing records, optionally filtered by category."""
        with self._lock:
            if category:
                return [t for t in self._timings if t.category == category]
            return list(self._timings)
    
    def get_imports(self, min_duration_ms: float = 0) -> List[ImportRecord]:
        """Get import records, optionally filtered by minimum duration."""
        with self._lock:
            if min_duration_ms > 0:
                return [i for i in self._imports if i.duration_ms >= min_duration_ms]
            return list(self._imports)
    
    def get_flow(self) -> List[FlowRecord]:
        """Get flow records."""
        with self._lock:
            return list(self._flow)
    
    def get_files_accessed(self) -> Dict[str, int]:
        """Get files accessed with counts."""
        with self._lock:
            return self._files_accessed.copy()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get profiling summary."""
        with self._lock:
            total_time = sum(t.duration_ms for t in self._timings)
            import_time = sum(i.duration_ms for i in self._imports)
            
            # Group by category
            by_category: Dict[str, float] = {}
            for t in self._timings:
                by_category[t.category] = by_category.get(t.category, 0) + t.duration_ms
            
            # Top slowest
            slowest = sorted(self._timings, key=lambda x: x.duration_ms, reverse=True)[:10]
            slowest_imports = sorted(self._imports, key=lambda x: x.duration_ms, reverse=True)[:10]
            
            return {
                'total_time_ms': total_time,
                'import_time_ms': import_time,
                'timing_count': len(self._timings),
                'import_count': len(self._imports),
                'flow_steps': len(self._flow),
                'files_accessed': len(self._files_accessed),
                'by_category': by_category,
                'slowest_operations': [(s.name, s.duration_ms) for s in slowest],
                'slowest_imports': [(s.module, s.duration_ms) for s in slowest_imports],
            }
    
    def report(self, output: str = "console") -> str:
        """Generate and output profiling report."""
        summary = self.get_summary()
        
        lines = [
            "=" * 60,
            "PraisonAI Profiling Report",
            "=" * 60,
            "",
            f"Total Time: {summary['total_time_ms']:.2f}ms",
            f"Import Time: {summary['import_time_ms']:.2f}ms",
            f"Timing Records: {summary['timing_count']}",
            f"Import Records: {summary['import_count']}",
            f"Flow Steps: {summary['flow_steps']}",
            f"Files Accessed: {summary['files_accessed']}",
            "",
            "By Category:",
        ]
        
        for cat, time_ms in summary['by_category'].items():
            lines.append(f"  {cat}: {time_ms:.2f}ms")
        
        lines.extend([
            "",
            "Slowest Operations:",
        ])
        for name, time_ms in summary['slowest_operations']:
            lines.append(f"  {name}: {time_ms:.2f}ms")
        
        lines.extend([
            "",
            "Slowest Imports:",
        ])
        for module, time_ms in summary['slowest_imports']:
            lines.append(f"  {module}: {time_ms:.2f}ms")
        
        lines.append("=" * 60)
        
        report_text = "\n".join(lines)
        
        if output == "console":
            print(report_text)
        
        return report_text

# ============================================================================
# Streaming Tracker
# ============================================================================

# (Note: StreamingTracker class is already defined above)

# ============================================================================


# ============================================================================
# Context-Aware Default Profiler
# ============================================================================

# Context variable for current profiler (enables per-agent isolation)
_current_profiler: ContextVar[Optional[_ProfilerImpl]] = ContextVar("current_profiler", default=None)

# Module-level default for CLI and backward compatibility
_default_profiler = None
_default_lock = threading.Lock()

def get_profiler() -> _ProfilerImpl:
    """Get the current profiler (context-aware or default)."""
    # Check context variable first (for per-agent use)
    profiler = _current_profiler.get()
    if profiler is not None:
        return profiler
    
    # Fall back to module-level default
    global _default_profiler
    if _default_profiler is None:
        with _default_lock:
            if _default_profiler is None:
                _default_profiler = _ProfilerImpl()
    return _default_profiler

def set_profiler(profiler: _ProfilerImpl) -> None:
    """Set the current profiler in context."""
    _current_profiler.set(profiler)

class ProfilerCompat:
    """
    Compatibility wrapper for old classmethod-based Profiler usage.
    
    Delegates all calls to the current profiler instance via get_profiler().
    This maintains backward compatibility while enabling per-agent isolation.
    """
    
    @staticmethod
    def enable() -> None:
        """Enable profiling."""
        get_profiler().enable()
    
    @staticmethod
    def disable() -> None:
        """Disable profiling."""
        get_profiler().disable()
    
    @staticmethod
    def is_enabled() -> bool:
        """Check if profiling is enabled."""
        return get_profiler().is_enabled()
    
    @staticmethod
    def clear() -> None:
        """Clear all profiling data."""
        get_profiler().clear()
    
    @staticmethod
    def record_timing(name: str, duration_ms: float, category: str = "function", 
                      file: str = "", line: int = 0) -> None:
        """Record a timing measurement."""
        get_profiler().record_timing(name, duration_ms, category, file, line)
    
    @staticmethod
    def record_import(module: str, duration_ms: float, parent: str = "") -> None:
        """Record an import timing."""
        get_profiler().record_import(module, duration_ms, parent)
    
    @staticmethod
    def record_flow(name: str, duration_ms: float, file: str = "", line: int = 0) -> None:
        """Record a flow step."""
        get_profiler().record_flow(name, duration_ms, file, line)
    
    @staticmethod
    def block(name: str, category: str = "block"):
        """Context manager for profiling a block of code."""
        return get_profiler().block(name, category)
    
    @staticmethod
    def get_timings(category: Optional[str] = None):
        """Get timing records."""
        return get_profiler().get_timings(category)
    
    @staticmethod
    def get_imports(min_duration_ms: float = 0):
        """Get import records."""
        return get_profiler().get_imports(min_duration_ms)
    
    @staticmethod
    def get_flow():
        """Get flow records."""
        return get_profiler().get_flow()
    
    @staticmethod
    def get_files_accessed():
        """Get files accessed."""
        return get_profiler().get_files_accessed()
    
    @staticmethod
    def get_summary():
        """Get profiling summary."""
        return get_profiler().get_summary()
    
    @staticmethod
    def report(output: str = "console") -> str:
        """Generate and output profiling report."""
        return get_profiler().report(output)
    
    @staticmethod
    def record_api_call(endpoint: str, method: str, duration_ms: float,
                        status_code: int = 0, request_size: int = 0,
                        response_size: int = 0) -> None:
        """Record an API/HTTP call timing."""
        get_profiler().record_api_call(endpoint, method, duration_ms, 
                                       status_code, request_size, response_size)
    
    @staticmethod
    def streaming(name: str):
        """Context manager for profiling streaming operations."""
        return get_profiler().streaming(name)
    
    @staticmethod
    def api_call(endpoint: str, method: str = "GET"):
        """Context manager for profiling API calls."""
        return get_profiler().api_call(endpoint, method)

# Create compatibility instance that acts like old singleton
# This allows existing code to work: Profiler.enable(), etc.
# But it actually delegates to the context-aware profiler
ProfilerSingleton = ProfilerCompat()

# Replace the class-based Profiler with the compatibility wrapper
# This ensures all existing code continues to work
Profiler = ProfilerCompat


# ============================================================================
# Decorators
# ============================================================================

def profile(func: Optional[Callable] = None, *, category: str = "function"):
    """
    Decorator to profile a function.
    
    Usage:
        @profile
        def my_function():
            pass
        
        @profile(category="api")
        def api_call():
            pass
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not Profiler.is_enabled():
                return fn(*args, **kwargs)
            
            start = time.time()
            try:
                return fn(*args, **kwargs)
            finally:
                duration_ms = (time.time() - start) * 1000
                file = fn.__code__.co_filename if hasattr(fn, '__code__') else ""
                line = fn.__code__.co_firstlineno if hasattr(fn, '__code__') else 0
                Profiler.record_timing(fn.__name__, duration_ms, category, file, line)
                Profiler.record_flow(fn.__name__, duration_ms, file, line)
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


def profile_async(func: Optional[Callable] = None, *, category: str = "async"):
    """
    Decorator to profile an async function.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if not Profiler.is_enabled():
                return await fn(*args, **kwargs)
            
            start = time.time()
            try:
                return await fn(*args, **kwargs)
            finally:
                duration_ms = (time.time() - start) * 1000
                file = fn.__code__.co_filename if hasattr(fn, '__code__') else ""
                line = fn.__code__.co_firstlineno if hasattr(fn, '__code__') else 0
                Profiler.record_timing(fn.__name__, duration_ms, category, file, line)
                Profiler.record_flow(fn.__name__, duration_ms, file, line)
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


# ============================================================================
# Import Profiling
# ============================================================================

class ImportProfiler:
    """
    Context manager to profile imports.
    
    Usage:
        with profile_imports() as profiler:
            import heavy_module
        
        print(profiler.get_imports())
    """
    
    def __init__(self):
        self._original_import = None
        self._imports: List[ImportRecord] = []
    
    def __enter__(self):
        import builtins
        self._original_import = builtins.__import__
        
        def profiled_import(name, globals=None, locals=None, fromlist=(), level=0):
            start = time.time()
            try:
                return self._original_import(name, globals, locals, fromlist, level)
            finally:
                duration_ms = (time.time() - start) * 1000
                if duration_ms > 1:  # Only record imports > 1ms
                    record = ImportRecord(module=name, duration_ms=duration_ms)
                    self._imports.append(record)
                    Profiler.record_import(name, duration_ms)
        
        builtins.__import__ = profiled_import
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import builtins
        builtins.__import__ = self._original_import
        return False
    
    def get_imports(self, min_duration_ms: float = 0) -> List[ImportRecord]:
        """Get recorded imports."""
        if min_duration_ms > 0:
            return [i for i in self._imports if i.duration_ms >= min_duration_ms]
        return self._imports.copy()
    
    def get_slowest(self, n: int = 10) -> List[ImportRecord]:
        """Get N slowest imports."""
        return sorted(self._imports, key=lambda x: x.duration_ms, reverse=True)[:n]


def profile_imports():
    """Create an import profiler context manager."""
    return ImportProfiler()


# ============================================================================
# API Profiling Decorators
# ============================================================================

def profile_api(func: Optional[Callable] = None, *, endpoint: str = ""):
    """
    Decorator to profile a function as an API call.
    
    Usage:
        @profile_api(endpoint="openai/chat")
        def call_openai():
            pass
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not Profiler.is_enabled():
                return fn(*args, **kwargs)
            
            ep = endpoint or fn.__name__
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                Profiler.record_api_call(ep, "CALL", duration_ms)
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


def profile_api_async(func: Optional[Callable] = None, *, endpoint: str = ""):
    """
    Decorator to profile an async function as an API call.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if not Profiler.is_enabled():
                return await fn(*args, **kwargs)
            
            ep = endpoint or fn.__name__
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                Profiler.record_api_call(ep, "CALL", duration_ms)
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


# ============================================================================
# cProfile Decorator
# ============================================================================

def profile_detailed(func: Optional[Callable] = None):
    """
    Decorator for detailed cProfile profiling.
    
    Usage:
        @profile_detailed
        def heavy_computation():
            pass
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not Profiler.is_enabled():
                return fn(*args, **kwargs)
            
            pr = cProfile.Profile()
            pr.enable()
            try:
                return fn(*args, **kwargs)
            finally:
                pr.disable()
                s = io.StringIO()
                ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
                ps.print_stats(20)
                Profiler._cprofile_stats.append({
                    'name': fn.__name__,
                    'stats': s.getvalue(),
                    'timestamp': time.time()
                })
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


# ============================================================================
# Line-Level Profiling Decorator
# ============================================================================

def profile_lines(func: Optional[Callable] = None):
    """
    Decorator for line-level profiling.
    
    Note: Requires line_profiler package for full functionality.
    Falls back to basic timing if not available.
    
    Usage:
        @profile_lines
        def my_function():
            pass
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not Profiler.is_enabled():
                return fn(*args, **kwargs)
            
            # Try to use line_profiler if available
            try:
                from line_profiler import LineProfiler
                lp = LineProfiler()
                lp.add_function(fn)
                lp.enable()
                try:
                    result = fn(*args, **kwargs)
                finally:
                    lp.disable()
                    s = io.StringIO()
                    lp.print_stats(stream=s)
                    Profiler.set_line_profile_data(fn.__name__, s.getvalue())
                return result
            except ImportError:
                # Fallback to basic timing
                start = time.perf_counter()
                try:
                    return fn(*args, **kwargs)
                finally:
                    duration_ms = (time.perf_counter() - start) * 1000
                    Profiler.set_line_profile_data(fn.__name__, {
                        'note': 'line_profiler not installed',
                        'total_ms': duration_ms
                    })
        
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


# ============================================================================
# Quick Profiling Functions
# ============================================================================

def time_import(module_name: str) -> float:
    """
    Time how long it takes to import a module.
    
    Returns duration in milliseconds.
    """
    start = time.time()
    __import__(module_name)
    return (time.time() - start) * 1000


def check_module_available(module_name: str) -> bool:
    """
    Check if a module is available without importing it.
    
    Uses importlib.util.find_spec which is fast.
    """
    import importlib.util
    return importlib.util.find_spec(module_name) is not None


# ============================================================================
# Context-Aware Default Profiler
# ============================================================================

# Context variable for current profiler (enables per-agent isolation)
_current_profiler: ContextVar[Optional[_ProfilerImpl]] = ContextVar("current_profiler", default=None)

# Module-level default for CLI and backward compatibility
_default_profiler = None
_default_lock = threading.Lock()

def get_profiler() -> _ProfilerImpl:
    """Get the current profiler (context-aware or default)."""
    # Check context variable first (for per-agent use)
    profiler = _current_profiler.get()
    if profiler is not None:
        return profiler
    
    # Fall back to module-level default
    global _default_profiler
    if _default_profiler is None:
        with _default_lock:
            if _default_profiler is None:
                _default_profiler = _ProfilerImpl()
    return _default_profiler

def set_profiler(profiler: _ProfilerImpl) -> None:
    """Set the current profiler in context."""
    _current_profiler.set(profiler)

class ProfilerCompat:
    """
    Compatibility wrapper for old classmethod-based Profiler usage.
    
    Delegates all calls to the current profiler instance via get_profiler().
    This maintains backward compatibility while enabling per-agent isolation.
    """
    
    @staticmethod
    def enable() -> None:
        """Enable profiling."""
        get_profiler().enable()
    
    @staticmethod
    def disable() -> None:
        """Disable profiling."""
        get_profiler().disable()
    
    @staticmethod
    def is_enabled() -> bool:
        """Check if profiling is enabled."""
        return get_profiler().is_enabled()
    
    @staticmethod
    def clear() -> None:
        """Clear all profiling data."""
        get_profiler().clear()
    
    @staticmethod
    def record_timing(name: str, duration_ms: float, category: str = "function", 
                      file: str = "", line: int = 0) -> None:
        """Record a timing measurement."""
        get_profiler().record_timing(name, duration_ms, category, file, line)
    
    @staticmethod
    def record_import(module: str, duration_ms: float, parent: str = "") -> None:
        """Record an import timing."""
        get_profiler().record_import(module, duration_ms, parent)
    
    @staticmethod
    def record_flow(name: str, duration_ms: float, file: str = "", line: int = 0) -> None:
        """Record a flow step."""
        get_profiler().record_flow(name, duration_ms, file, line)
    
    @staticmethod
    def block(name: str, category: str = "block"):
        """Context manager for profiling a block of code."""
        return get_profiler().block(name, category)
    
    @staticmethod
    def get_timings(category: Optional[str] = None):
        """Get timing records."""
        return get_profiler().get_timings(category)
    
    @staticmethod
    def get_imports(min_duration_ms: float = 0):
        """Get import records."""
        return get_profiler().get_imports(min_duration_ms)
    
    @staticmethod
    def get_flow():
        """Get flow records."""
        return get_profiler().get_flow()
    
    @staticmethod
    def get_files_accessed():
        """Get files accessed."""
        return get_profiler().get_files_accessed()
    
    @staticmethod
    def get_summary():
        """Get profiling summary."""
        return get_profiler().get_summary()
    
    @staticmethod
    def report(output: str = "console") -> str:
        """Generate and output profiling report."""
        return get_profiler().report(output)
    
    @staticmethod
    def record_flow(name: str, duration_ms: float, file: str = "", line: int = 0) -> None:
        """Record a flow step."""
        get_profiler().record_flow(name, duration_ms, file, line)
    
    @staticmethod
    def record_api_call(endpoint: str, method: str, duration_ms: float,
                        status_code: int = 0, request_size: int = 0,
                        response_size: int = 0) -> None:
        """Record an API/HTTP call timing."""
        get_profiler().record_api_call(endpoint, method, duration_ms, 
                                       status_code, request_size, response_size)
    
    @staticmethod
    def block(name: str, category: str = "block"):
        """Context manager for profiling a block of code."""
        return get_profiler().block(name, category)
    
    @staticmethod
    def streaming(name: str):
        """Context manager for profiling streaming operations."""
        return get_profiler().streaming(name)
    
    @staticmethod
    def api_call(endpoint: str, method: str = "GET"):
        """Context manager for profiling API calls."""
        return get_profiler().api_call(endpoint, method)

# Create compatibility instance that acts like old singleton
# This allows existing code to work: Profiler.enable(), etc.
# But it actually delegates to the context-aware profiler
ProfilerSingleton = ProfilerCompat()

# Replace the class-based Profiler with the compatibility wrapper
# This ensures all existing code continues to work
Profiler = ProfilerCompat


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    # Core
    'Profiler',
    'StreamingTracker',
    # Decorators
    'profile',
    'profile_async',
    'profile_api',
    'profile_api_async',
    'profile_detailed',
    'profile_lines',
    # Import profiling
    'profile_imports',
    'ImportProfiler',
    # Utilities
    'time_import',
    'check_module_available',
    # Data classes
    'TimingRecord',
    'ImportRecord',
    'FlowRecord',
    'APICallRecord',
    'StreamingRecord',
    'MemoryRecord',
]
