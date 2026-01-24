"""
Context Instrumentation for PraisonAI Agents.

Low-overhead instrumentation for context operations:
- Timing decorators for context operations
- Debug-level logging (zero overhead when disabled)
- Token utilization tracking
- Performance metrics collection

Zero Performance Impact:
- All instrumentation is guarded by logging level checks
- No overhead when logging is not at DEBUG level
- Metrics collection is opt-in only
"""

import time
import logging
import functools
import os
from typing import Dict, Any, Callable, TypeVar, List
from dataclasses import dataclass
from contextlib import contextmanager
from threading import Lock

logger = logging.getLogger(__name__)

# Type variable for decorated functions
F = TypeVar('F', bound=Callable[..., Any])


@dataclass
class ContextMetrics:
    """Collected metrics for context operations."""
    # Timing
    process_calls: int = 0
    process_total_ms: float = 0.0
    process_max_ms: float = 0.0
    
    optimize_calls: int = 0
    optimize_total_ms: float = 0.0
    optimize_max_ms: float = 0.0
    
    estimate_calls: int = 0
    estimate_total_ms: float = 0.0
    
    # Token tracking
    tokens_processed: int = 0
    tokens_saved: int = 0
    tokens_saved_by_summarization: int = 0  # Tokens saved by LLM summarization
    tokens_saved_by_truncation: int = 0  # Tokens saved by truncation
    compactions_triggered: int = 0
    tool_outputs_summarized: int = 0  # Count of tool outputs summarized
    tool_outputs_truncated: int = 0  # Count of tool outputs truncated
    
    # Cache stats
    cache_hits: int = 0
    cache_misses: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timing": {
                "process": {
                    "calls": self.process_calls,
                    "total_ms": round(self.process_total_ms, 2),
                    "avg_ms": round(self.process_total_ms / max(1, self.process_calls), 2),
                    "max_ms": round(self.process_max_ms, 2),
                },
                "optimize": {
                    "calls": self.optimize_calls,
                    "total_ms": round(self.optimize_total_ms, 2),
                    "avg_ms": round(self.optimize_total_ms / max(1, self.optimize_calls), 2),
                    "max_ms": round(self.optimize_max_ms, 2),
                },
                "estimate": {
                    "calls": self.estimate_calls,
                    "total_ms": round(self.estimate_total_ms, 2),
                    "avg_ms": round(self.estimate_total_ms / max(1, self.estimate_calls), 2),
                },
            },
            "tokens": {
                "processed": self.tokens_processed,
                "saved": self.tokens_saved,
                "saved_by_summarization": self.tokens_saved_by_summarization,
                "saved_by_truncation": self.tokens_saved_by_truncation,
                "compactions": self.compactions_triggered,
            },
            "tool_outputs": {
                "summarized": self.tool_outputs_summarized,
                "truncated": self.tool_outputs_truncated,
            },
            "cache": {
                "hits": self.cache_hits,
                "misses": self.cache_misses,
                "hit_rate": round(self.cache_hits / max(1, self.cache_hits + self.cache_misses), 3),
            },
        }


# Global metrics instance
_metrics = ContextMetrics()
_metrics_lock = Lock()


def get_metrics() -> ContextMetrics:
    """Get global metrics instance."""
    return _metrics


def reset_metrics() -> None:
    """Reset global metrics (for testing)."""
    global _metrics
    with _metrics_lock:
        _metrics = ContextMetrics()


def is_debug_enabled() -> bool:
    """Check if debug logging is enabled (cached check)."""
    return logger.isEnabledFor(logging.DEBUG) or os.environ.get('LOGLEVEL', '').upper() == 'DEBUG'


def context_operation(operation_name: str) -> Callable[[F], F]:
    """
    Decorator for timing context operations.
    
    Zero overhead when debug logging is disabled.
    
    Usage:
        @context_operation("process")
        def process(self, messages):
            ...
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Fast path: no instrumentation if debug disabled
            if not is_debug_enabled():
                return func(*args, **kwargs)
            
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                
                # Update metrics
                with _metrics_lock:
                    if operation_name == "process":
                        _metrics.process_calls += 1
                        _metrics.process_total_ms += elapsed_ms
                        _metrics.process_max_ms = max(_metrics.process_max_ms, elapsed_ms)
                    elif operation_name == "optimize":
                        _metrics.optimize_calls += 1
                        _metrics.optimize_total_ms += elapsed_ms
                        _metrics.optimize_max_ms = max(_metrics.optimize_max_ms, elapsed_ms)
                    elif operation_name == "estimate":
                        _metrics.estimate_calls += 1
                        _metrics.estimate_total_ms += elapsed_ms
                
                logger.debug(
                    f"[context.{operation_name}] completed in {elapsed_ms:.2f}ms"
                )
        
        return wrapper  # type: ignore
    return decorator


@contextmanager
def timed_section(name: str):
    """
    Context manager for timing arbitrary sections.
    
    Usage:
        with timed_section("token_estimation"):
            tokens = estimate_tokens(messages)
    """
    if not is_debug_enabled():
        yield
        return
    
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.debug(f"[context.{name}] completed in {elapsed_ms:.2f}ms")


def log_context_size(
    messages: List[Dict[str, Any]],
    tokens: int,
    utilization: float,
    agent_name: str = "",
) -> None:
    """
    Log context size at debug level.
    
    Zero overhead when debug logging is disabled.
    """
    if not is_debug_enabled():
        return
    
    prefix = f"[{agent_name}] " if agent_name else ""
    logger.debug(
        f"{prefix}Context: {len(messages)} messages, "
        f"{tokens} tokens, {utilization*100:.1f}% utilization"
    )


def log_optimization_event(
    event_type: str,
    tokens_before: int,
    tokens_after: int,
    strategy: str = "",
    agent_name: str = "",
) -> None:
    """
    Log optimization event at debug level.
    
    Zero overhead when debug logging is disabled.
    """
    if not is_debug_enabled():
        return
    
    saved = tokens_before - tokens_after
    prefix = f"[{agent_name}] " if agent_name else ""
    logger.debug(
        f"{prefix}Optimization [{event_type}]: "
        f"{tokens_before} -> {tokens_after} tokens "
        f"(saved {saved}, strategy={strategy})"
    )
    
    # Update metrics
    with _metrics_lock:
        _metrics.tokens_saved += saved
        if event_type in ("auto_compact", "overflow_detected"):
            _metrics.compactions_triggered += 1


def log_cache_access(hit: bool) -> None:
    """Track cache hit/miss for token estimation."""
    if not is_debug_enabled():
        return
    
    with _metrics_lock:
        if hit:
            _metrics.cache_hits += 1
        else:
            _metrics.cache_misses += 1


def track_tokens_processed(count: int) -> None:
    """Track total tokens processed."""
    with _metrics_lock:
        _metrics.tokens_processed += count


# Benchmark utilities
@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""
    name: str
    iterations: int
    total_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    std_dev_ms: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "total_ms": round(self.total_ms, 3),
            "avg_ms": round(self.avg_ms, 3),
            "min_ms": round(self.min_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "std_dev_ms": round(self.std_dev_ms, 3),
        }


def run_benchmark(
    name: str,
    func: Callable[[], Any],
    iterations: int = 100,
    warmup: int = 10,
) -> BenchmarkResult:
    """
    Run a benchmark for a function.
    
    Args:
        name: Benchmark name
        func: Function to benchmark
        iterations: Number of iterations
        warmup: Number of warmup iterations (not counted)
        
    Returns:
        BenchmarkResult with timing statistics
    """
    import statistics
    
    # Warmup
    for _ in range(warmup):
        func()
    
    # Benchmark
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return BenchmarkResult(
        name=name,
        iterations=iterations,
        total_ms=sum(times),
        avg_ms=statistics.mean(times),
        min_ms=min(times),
        max_ms=max(times),
        std_dev_ms=statistics.stdev(times) if len(times) > 1 else 0.0,
    )


def format_benchmark_results(results: List[BenchmarkResult]) -> str:
    """Format benchmark results as a table."""
    lines = [
        "=" * 70,
        f"{'Benchmark':<30} {'Avg (ms)':<12} {'Min':<10} {'Max':<10} {'StdDev':<10}",
        "-" * 70,
    ]
    
    for r in results:
        lines.append(
            f"{r.name:<30} {r.avg_ms:<12.3f} {r.min_ms:<10.3f} "
            f"{r.max_ms:<10.3f} {r.std_dev_ms:<10.3f}"
        )
    
    lines.append("=" * 70)
    return "\n".join(lines)
