"""
PraisonAI Agents Core Profiling Module

Lightweight, protocol-based profiling for the core SDK.
Zero overhead when disabled. Opt-in only.

Features:
- Pre-LLM latency breakdown
- LLM client initialization timing
- Tool resolution timing
- Message serialization timing
- Streaming TTFT tracking
- Import timing
- Async-safe

Usage:
    from praisonaiagents.profiling import Profiler, profile_block
    
    # Enable profiling
    Profiler.enable()
    
    # Profile a block
    with profile_block("my_operation"):
        do_something()
    
    # Get report
    Profiler.report()
"""

import time
import os
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
from contextlib import contextmanager
import functools
import json


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class TimingRecord:
    """Record of a single timing measurement."""
    name: str
    duration_ms: float
    category: str = "block"
    parent: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamingRecord:
    """Record of streaming operation."""
    name: str
    ttft_ms: float  # Time to first token
    total_ms: float
    chunk_count: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class PreLLMBreakdown:
    """Breakdown of pre-LLM latency phases."""
    agent_init_ms: float = 0.0
    llm_client_init_ms: float = 0.0
    tool_resolution_ms: float = 0.0
    message_build_ms: float = 0.0
    context_management_ms: float = 0.0
    knowledge_retrieval_ms: float = 0.0
    guardrail_check_ms: float = 0.0
    total_pre_llm_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


# ============================================================================
# Streaming Tracker
# ============================================================================

class StreamingTracker:
    """Track streaming operations for TTFT metrics."""
    
    def __init__(self, name: str):
        self.name = name
        self._start_time: Optional[float] = None
        self._first_token_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._chunk_count: int = 0
    
    def start(self) -> None:
        self._start_time = time.perf_counter()
    
    def first_token(self) -> None:
        if self._first_token_time is None:
            self._first_token_time = time.perf_counter()
    
    def chunk(self) -> None:
        self._chunk_count += 1
    
    def end(self) -> None:
        self._end_time = time.perf_counter()
        if self._start_time is not None:
            ttft_ms = 0.0
            if self._first_token_time is not None:
                ttft_ms = (self._first_token_time - self._start_time) * 1000
            total_ms = (self._end_time - self._start_time) * 1000
            Profiler.record_streaming(
                name=self.name,
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                chunk_count=self._chunk_count
            )
    
    @property
    def ttft_ms(self) -> float:
        if self._start_time and self._first_token_time:
            return (self._first_token_time - self._start_time) * 1000
        return 0.0
    
    @property
    def elapsed_ms(self) -> float:
        if self._start_time:
            end = self._end_time or time.perf_counter()
            return (end - self._start_time) * 1000
        return 0.0


# ============================================================================
# Core Profiler
# ============================================================================

class Profiler:
    """
    Lightweight profiler for PraisonAI Agents core SDK.
    
    Thread-safe singleton with zero overhead when disabled.
    """
    
    _lock = threading.Lock()
    _enabled: bool = False
    _timings: List[TimingRecord] = []
    _streaming: List[StreamingRecord] = []
    _pre_llm_breakdown: Optional[PreLLMBreakdown] = None
    _current_phases: Dict[str, float] = {}  # Track in-progress phases
    _phase_stack: List[str] = []  # Track nested phases
    
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
            cls._streaming.clear()
            cls._pre_llm_breakdown = None
            cls._current_phases.clear()
            cls._phase_stack.clear()
    
    @classmethod
    def record_timing(cls, name: str, duration_ms: float, category: str = "block",
                      parent: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record a timing measurement."""
        if not cls.is_enabled():
            return
        with cls._lock:
            cls._timings.append(TimingRecord(
                name=name,
                duration_ms=duration_ms,
                category=category,
                parent=parent,
                metadata=metadata or {}
            ))
    
    @classmethod
    def record_streaming(cls, name: str, ttft_ms: float, total_ms: float,
                         chunk_count: int = 0) -> None:
        """Record streaming metrics."""
        if not cls.is_enabled():
            return
        with cls._lock:
            cls._streaming.append(StreamingRecord(
                name=name,
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                chunk_count=chunk_count
            ))
    
    @classmethod
    def start_phase(cls, phase_name: str) -> None:
        """Start timing a phase (for pre-LLM breakdown)."""
        if not cls.is_enabled():
            return
        with cls._lock:
            cls._current_phases[phase_name] = time.perf_counter()
            cls._phase_stack.append(phase_name)
    
    @classmethod
    def end_phase(cls, phase_name: str) -> float:
        """End timing a phase and return duration in ms."""
        if not cls.is_enabled():
            return 0.0
        with cls._lock:
            start = cls._current_phases.pop(phase_name, None)
            if phase_name in cls._phase_stack:
                cls._phase_stack.remove(phase_name)
            if start is None:
                return 0.0
            duration_ms = (time.perf_counter() - start) * 1000
            # Record as timing
            parent = cls._phase_stack[-1] if cls._phase_stack else ""
            cls._timings.append(TimingRecord(
                name=phase_name,
                duration_ms=duration_ms,
                category="phase",
                parent=parent
            ))
            return duration_ms
    
    @classmethod
    @contextmanager
    def phase(cls, name: str, category: str = "phase"):
        """Context manager for timing a phase."""
        if not cls.is_enabled():
            yield
            return
        
        start = time.perf_counter()
        parent = ""
        with cls._lock:
            parent = cls._phase_stack[-1] if cls._phase_stack else ""
            cls._phase_stack.append(name)
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            with cls._lock:
                if name in cls._phase_stack:
                    cls._phase_stack.remove(name)
                cls._timings.append(TimingRecord(
                    name=name,
                    duration_ms=duration_ms,
                    category=category,
                    parent=parent
                ))
    
    @classmethod
    @contextmanager
    def streaming(cls, name: str):
        """Context manager for streaming profiling."""
        tracker = StreamingTracker(name)
        tracker.start()
        try:
            yield tracker
        finally:
            tracker.end()
    
    @classmethod
    def set_pre_llm_breakdown(cls, breakdown: PreLLMBreakdown) -> None:
        """Set the pre-LLM breakdown data."""
        if not cls.is_enabled():
            return
        with cls._lock:
            cls._pre_llm_breakdown = breakdown
    
    @classmethod
    def get_timings(cls, category: Optional[str] = None) -> List[TimingRecord]:
        """Get timing records."""
        with cls._lock:
            if category:
                return [t for t in cls._timings if t.category == category]
            return cls._timings.copy()
    
    @classmethod
    def get_streaming_records(cls) -> List[StreamingRecord]:
        """Get streaming records."""
        with cls._lock:
            return cls._streaming.copy()
    
    @classmethod
    def get_pre_llm_breakdown(cls) -> Optional[PreLLMBreakdown]:
        """Get pre-LLM breakdown."""
        with cls._lock:
            return cls._pre_llm_breakdown
    
    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        """Get profiling summary."""
        with cls._lock:
            total_time = sum(t.duration_ms for t in cls._timings)
            
            # Group by category
            by_category: Dict[str, float] = {}
            for t in cls._timings:
                by_category[t.category] = by_category.get(t.category, 0) + t.duration_ms
            
            # Top slowest
            slowest = sorted(cls._timings, key=lambda x: x.duration_ms, reverse=True)[:15]
            
            # Pre-LLM breakdown
            pre_llm = cls._pre_llm_breakdown.to_dict() if cls._pre_llm_breakdown else {}
            
            # Streaming stats
            streaming_stats = []
            for s in cls._streaming:
                streaming_stats.append({
                    'name': s.name,
                    'ttft_ms': s.ttft_ms,
                    'total_ms': s.total_ms,
                    'chunk_count': s.chunk_count
                })
            
            return {
                'total_time_ms': total_time,
                'timing_count': len(cls._timings),
                'by_category': by_category,
                'slowest_operations': [(s.name, s.duration_ms, s.category) for s in slowest],
                'pre_llm_breakdown': pre_llm,
                'streaming': streaming_stats
            }
    
    @classmethod
    def report(cls, output: str = "console") -> str:
        """Generate and output profiling report."""
        summary = cls.get_summary()
        
        lines = [
            "=" * 70,
            "PraisonAI Agents Core Profiling Report",
            "=" * 70,
            "",
            f"Total Time: {summary['total_time_ms']:.2f}ms",
            f"Timing Records: {summary['timing_count']}",
            "",
        ]
        
        # Pre-LLM Breakdown (key for debugging the 7s delay)
        if summary['pre_llm_breakdown']:
            lines.append("## Pre-LLM Latency Breakdown")
            lines.append("-" * 50)
            for phase, ms in summary['pre_llm_breakdown'].items():
                if ms > 0:
                    lines.append(f"  {phase:<30}: {ms:>10.2f} ms")
            lines.append("")
        
        # By Category
        lines.append("## By Category")
        lines.append("-" * 50)
        for cat, time_ms in summary['by_category'].items():
            lines.append(f"  {cat}: {time_ms:.2f}ms")
        lines.append("")
        
        # Slowest Operations
        lines.append("## Slowest Operations")
        lines.append("-" * 50)
        for name, time_ms, cat in summary['slowest_operations']:
            lines.append(f"  {name:<40}: {time_ms:>10.2f}ms [{cat}]")
        lines.append("")
        
        # Streaming Stats
        if summary['streaming']:
            lines.append("## Streaming Metrics")
            lines.append("-" * 50)
            for s in summary['streaming']:
                lines.append(f"  {s['name']}: TTFT={s['ttft_ms']:.2f}ms, Total={s['total_ms']:.2f}ms, Chunks={s['chunk_count']}")
            lines.append("")
        
        lines.append("=" * 70)
        
        report_text = "\n".join(lines)
        
        if output == "console":
            print(report_text)
        
        return report_text
    
    @classmethod
    def export_json(cls) -> str:
        """Export profiling data as JSON."""
        summary = cls.get_summary()
        with cls._lock:
            data = {
                'summary': summary,
                'timings': [asdict(t) for t in cls._timings],
                'streaming': [asdict(s) for s in cls._streaming],
            }
            return json.dumps(data, indent=2, default=str)


# ============================================================================
# Decorators
# ============================================================================

def profile_func(func: Optional[Callable] = None, *, category: str = "function"):
    """Decorator to profile a function."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not Profiler.is_enabled():
                return fn(*args, **kwargs)
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                Profiler.record_timing(fn.__name__, duration_ms, category)
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


def profile_async(func: Optional[Callable] = None, *, category: str = "async"):
    """Decorator to profile an async function."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            if not Profiler.is_enabled():
                return await fn(*args, **kwargs)
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                Profiler.record_timing(fn.__name__, duration_ms, category)
        return wrapper
    
    if func is not None:
        return decorator(func)
    return decorator


@contextmanager
def profile_block(name: str, category: str = "block"):
    """Context manager for profiling a block of code."""
    if not Profiler.is_enabled():
        yield
        return
    
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        Profiler.record_timing(name, duration_ms, category)


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    'Profiler',
    'StreamingTracker',
    'TimingRecord',
    'StreamingRecord',
    'PreLLMBreakdown',
    'profile_func',
    'profile_async',
    'profile_block',
]
