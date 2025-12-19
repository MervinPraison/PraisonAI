"""
PraisonAI Profiler Module

Standardized profiling for performance monitoring across praisonai and praisonai-agents.

Features:
- Import timing
- Function execution timing
- Flow tracking
- File/module usage tracking
- Memory usage (optional)

Usage:
    from praisonai.profiler import Profiler, profile, profile_imports
    
    # Profile a function
    @profile
    def my_function():
        pass
    
    # Profile a block
    with Profiler.block("my_operation"):
        do_something()
    
    # Profile imports
    with profile_imports():
        import heavy_module
    
    # Get report
    Profiler.report()
"""

import time
import functools
import threading
import sys
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from contextlib import contextmanager


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
# Profiler Class
# ============================================================================

class Profiler:
    """
    Centralized profiler for performance monitoring.
    
    Thread-safe singleton pattern for global access.
    """
    
    _instance: Optional['Profiler'] = None
    _lock = threading.Lock()
    
    # Class-level storage
    _timings: List[TimingRecord] = []
    _imports: List[ImportRecord] = []
    _flow: List[FlowRecord] = []
    _enabled: bool = False
    _flow_step: int = 0
    _files_accessed: Dict[str, int] = {}
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def enable(cls) -> None:
        """Enable profiling."""
        cls._enabled = True
    
    @classmethod
    def disable(cls) -> None:
        """Disable profiling."""
        cls._enabled = False
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if profiling is enabled."""
        return cls._enabled or os.environ.get('PRAISONAI_PROFILE', '').lower() in ('1', 'true', 'yes')
    
    @classmethod
    def clear(cls) -> None:
        """Clear all profiling data."""
        with cls._lock:
            cls._timings.clear()
            cls._imports.clear()
            cls._flow.clear()
            cls._flow_step = 0
            cls._files_accessed.clear()
    
    @classmethod
    def record_timing(cls, name: str, duration_ms: float, category: str = "function", 
                      file: str = "", line: int = 0) -> None:
        """Record a timing measurement."""
        if not cls.is_enabled():
            return
        
        with cls._lock:
            cls._timings.append(TimingRecord(
                name=name,
                duration_ms=duration_ms,
                category=category,
                file=file,
                line=line
            ))
            
            # Track file access
            if file:
                cls._files_accessed[file] = cls._files_accessed.get(file, 0) + 1
    
    @classmethod
    def record_import(cls, module: str, duration_ms: float, parent: str = "") -> None:
        """Record an import timing."""
        if not cls.is_enabled():
            return
        
        with cls._lock:
            cls._imports.append(ImportRecord(
                module=module,
                duration_ms=duration_ms,
                parent=parent
            ))
    
    @classmethod
    def record_flow(cls, name: str, duration_ms: float, file: str = "", line: int = 0) -> None:
        """Record a flow step."""
        if not cls.is_enabled():
            return
        
        with cls._lock:
            cls._flow_step += 1
            cls._flow.append(FlowRecord(
                step=cls._flow_step,
                name=name,
                file=file,
                line=line,
                duration_ms=duration_ms
            ))
    
    @classmethod
    @contextmanager
    def block(cls, name: str, category: str = "block"):
        """Context manager for profiling a block of code."""
        start = time.time()
        frame = sys._getframe(2) if hasattr(sys, '_getframe') else None
        file = frame.f_code.co_filename if frame else ""
        line = frame.f_lineno if frame else 0
        
        try:
            yield
        finally:
            duration_ms = (time.time() - start) * 1000
            cls.record_timing(name, duration_ms, category, file, line)
            cls.record_flow(name, duration_ms, file, line)
    
    @classmethod
    def get_timings(cls, category: Optional[str] = None) -> List[TimingRecord]:
        """Get timing records, optionally filtered by category."""
        with cls._lock:
            if category:
                return [t for t in cls._timings if t.category == category]
            return cls._timings.copy()
    
    @classmethod
    def get_imports(cls, min_duration_ms: float = 0) -> List[ImportRecord]:
        """Get import records, optionally filtered by minimum duration."""
        with cls._lock:
            if min_duration_ms > 0:
                return [i for i in cls._imports if i.duration_ms >= min_duration_ms]
            return cls._imports.copy()
    
    @classmethod
    def get_flow(cls) -> List[FlowRecord]:
        """Get flow records."""
        with cls._lock:
            return cls._flow.copy()
    
    @classmethod
    def get_files_accessed(cls) -> Dict[str, int]:
        """Get files accessed with counts."""
        with cls._lock:
            return cls._files_accessed.copy()
    
    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        """Get profiling summary."""
        with cls._lock:
            total_time = sum(t.duration_ms for t in cls._timings)
            import_time = sum(i.duration_ms for i in cls._imports)
            
            # Group by category
            by_category: Dict[str, float] = {}
            for t in cls._timings:
                by_category[t.category] = by_category.get(t.category, 0) + t.duration_ms
            
            # Top slowest
            slowest = sorted(cls._timings, key=lambda x: x.duration_ms, reverse=True)[:10]
            slowest_imports = sorted(cls._imports, key=lambda x: x.duration_ms, reverse=True)[:10]
            
            return {
                'total_time_ms': total_time,
                'import_time_ms': import_time,
                'timing_count': len(cls._timings),
                'import_count': len(cls._imports),
                'flow_steps': len(cls._flow),
                'files_accessed': len(cls._files_accessed),
                'by_category': by_category,
                'slowest_operations': [(s.name, s.duration_ms) for s in slowest],
                'slowest_imports': [(s.module, s.duration_ms) for s in slowest_imports],
            }
    
    @classmethod
    def report(cls, output: str = "console") -> str:
        """Generate and output profiling report."""
        summary = cls.get_summary()
        
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
# Exports
# ============================================================================

__all__ = [
    'Profiler',
    'profile',
    'profile_async',
    'profile_imports',
    'ImportProfiler',
    'time_import',
    'check_module_available',
    'TimingRecord',
    'ImportRecord',
    'FlowRecord',
]
