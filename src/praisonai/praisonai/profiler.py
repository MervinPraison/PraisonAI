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
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Callable, Any
from contextlib import contextmanager, asynccontextmanager


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

class Profiler:
    """
    Centralized profiler for performance monitoring.
    
    Thread-safe singleton pattern for global access.
    
    Features:
    - Function/block timing
    - API call profiling (wall-clock)
    - Streaming profiling (TTFT)
    - Memory profiling
    - Import timing
    - Statistics (p50, p95, p99)
    - cProfile integration
    - Export (JSON, HTML)
    """
    
    _instance: Optional['Profiler'] = None
    _lock = threading.Lock()
    
    # Class-level storage
    _timings: List[TimingRecord] = []
    _imports: List[ImportRecord] = []
    _flow: List[FlowRecord] = []
    _api_calls: List[APICallRecord] = []
    _streaming: List[StreamingRecord] = []
    _memory: List[MemoryRecord] = []
    _enabled: bool = False
    _flow_step: int = 0
    _files_accessed: Dict[str, int] = {}
    _line_profile_data: Dict[str, Any] = {}
    _cprofile_stats: List[Dict[str, Any]] = []
    
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
            cls._api_calls.clear()
            cls._streaming.clear()
            cls._memory.clear()
            cls._flow_step = 0
            cls._files_accessed.clear()
            cls._line_profile_data.clear()
            cls._cprofile_stats.clear()
    
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
    
    # ========================================================================
    # API Call Profiling
    # ========================================================================
    
    @classmethod
    def record_api_call(cls, endpoint: str, method: str, duration_ms: float,
                        status_code: int = 0, request_size: int = 0,
                        response_size: int = 0) -> None:
        """Record an API/HTTP call timing."""
        if not cls.is_enabled():
            return
        
        with cls._lock:
            cls._api_calls.append(APICallRecord(
                endpoint=endpoint,
                method=method,
                duration_ms=duration_ms,
                status_code=status_code,
                request_size=request_size,
                response_size=response_size
            ))
    
    @classmethod
    def get_api_calls(cls) -> List[APICallRecord]:
        """Get API call records."""
        with cls._lock:
            return cls._api_calls.copy()
    
    @classmethod
    @contextmanager
    def api_call(cls, endpoint: str, method: str = "GET"):
        """Context manager for profiling API calls."""
        start = time.perf_counter()
        call_info = {'status_code': 0, 'request_size': 0, 'response_size': 0}
        
        try:
            yield call_info
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            cls.record_api_call(
                endpoint=endpoint,
                method=method,
                duration_ms=duration_ms,
                status_code=call_info.get('status_code', 0),
                request_size=call_info.get('request_size', 0),
                response_size=call_info.get('response_size', 0)
            )
    
    # ========================================================================
    # Streaming Profiling
    # ========================================================================
    
    @classmethod
    def record_streaming(cls, name: str, ttft_ms: float, total_ms: float,
                         chunk_count: int = 0, total_tokens: int = 0) -> None:
        """Record streaming metrics."""
        if not cls.is_enabled():
            return
        
        with cls._lock:
            cls._streaming.append(StreamingRecord(
                name=name,
                ttft_ms=ttft_ms,
                total_ms=total_ms,
                chunk_count=chunk_count,
                total_tokens=total_tokens
            ))
    
    @classmethod
    def get_streaming_records(cls) -> List[StreamingRecord]:
        """Get streaming records."""
        with cls._lock:
            return cls._streaming.copy()
    
    @classmethod
    @contextmanager
    def streaming(cls, name: str):
        """Context manager for profiling streaming operations."""
        tracker = StreamingTracker(name)
        tracker.start()
        try:
            yield tracker
        finally:
            tracker.end()
    
    @classmethod
    @asynccontextmanager
    async def streaming_async(cls, name: str):
        """Async context manager for profiling streaming operations."""
        tracker = StreamingTracker(name)
        tracker.start()
        try:
            yield tracker
        finally:
            tracker.end()
    
    # ========================================================================
    # Memory Profiling
    # ========================================================================
    
    @classmethod
    def record_memory(cls, name: str, current_kb: float, peak_kb: float) -> None:
        """Record memory usage."""
        if not cls.is_enabled():
            return
        
        with cls._lock:
            cls._memory.append(MemoryRecord(
                name=name,
                current_kb=current_kb,
                peak_kb=peak_kb
            ))
    
    @classmethod
    def get_memory_records(cls) -> List[MemoryRecord]:
        """Get memory records."""
        with cls._lock:
            return cls._memory.copy()
    
    @classmethod
    @contextmanager
    def memory(cls, name: str):
        """Context manager for profiling memory usage."""
        tracemalloc.start()
        try:
            yield
        finally:
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            cls.record_memory(name, current / 1024, peak / 1024)
    
    @classmethod
    def memory_snapshot(cls) -> Dict[str, float]:
        """Take a memory snapshot."""
        tracemalloc.start()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            'current_kb': current / 1024,
            'peak_kb': peak / 1024
        }
    
    # ========================================================================
    # Statistics
    # ========================================================================
    
    @classmethod
    def get_statistics(cls, category: Optional[str] = None) -> Dict[str, float]:
        """
        Get statistical analysis of timing data.
        
        Returns p50, p95, p99, mean, std_dev, min, max.
        """
        with cls._lock:
            if category:
                durations = [t.duration_ms for t in cls._timings if t.category == category]
            else:
                durations = [t.duration_ms for t in cls._timings]
            
            if not durations:
                return {
                    'p50': 0.0, 'p95': 0.0, 'p99': 0.0,
                    'mean': 0.0, 'std_dev': 0.0, 'min': 0.0, 'max': 0.0,
                    'count': 0
                }
            
            sorted_durations = sorted(durations)
            n = len(sorted_durations)
            
            def percentile(p: float) -> float:
                idx = int(n * p / 100)
                return sorted_durations[min(idx, n - 1)]
            
            mean = statistics.mean(durations)
            std_dev = statistics.stdev(durations) if n > 1 else 0.0
            
            return {
                'p50': percentile(50),
                'p95': percentile(95),
                'p99': percentile(99),
                'mean': mean,
                'std_dev': std_dev,
                'min': min(durations),
                'max': max(durations),
                'count': n
            }
    
    # ========================================================================
    # cProfile Integration
    # ========================================================================
    
    @classmethod
    @contextmanager
    def cprofile(cls, name: str):
        """Context manager for cProfile profiling."""
        pr = cProfile.Profile()
        pr.enable()
        
        try:
            yield pr
        finally:
            pr.disable()
            
            # Store stats
            s = io.StringIO()
            ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
            ps.print_stats(30)
            
            with cls._lock:
                cls._cprofile_stats.append({
                    'name': name,
                    'stats': s.getvalue(),
                    'total_calls': ps.total_calls if hasattr(ps, 'total_calls') else 0,
                    'timestamp': time.time()
                })
    
    @classmethod
    def get_cprofile_stats(cls) -> List[Dict[str, Any]]:
        """Get cProfile statistics."""
        with cls._lock:
            return cls._cprofile_stats.copy()
    
    # ========================================================================
    # Line-Level Profiling
    # ========================================================================
    
    @classmethod
    def get_line_profile_data(cls) -> Dict[str, Any]:
        """Get line-level profiling data."""
        with cls._lock:
            return cls._line_profile_data.copy()
    
    @classmethod
    def set_line_profile_data(cls, func_name: str, data: Any) -> None:
        """Store line-level profiling data."""
        if not cls.is_enabled():
            return
        with cls._lock:
            cls._line_profile_data[func_name] = data
    
    # ========================================================================
    # Flamegraph
    # ========================================================================
    
    @classmethod
    def get_flamegraph_data(cls) -> List[Dict[str, Any]]:
        """
        Generate flamegraph-compatible data from flow records.
        
        Returns list of {name, value, children} for flamegraph visualization.
        """
        with cls._lock:
            # Convert flow records to flamegraph format
            data = []
            for record in cls._flow:
                data.append({
                    'name': record.name,
                    'value': record.duration_ms,
                    'file': record.file,
                    'line': record.line
                })
            return data
    
    @classmethod
    def export_flamegraph(cls, filepath: str) -> None:
        """
        Export flamegraph to SVG file.
        
        Note: Requires flamegraph data. For full flamegraph support,
        use py-spy: py-spy record -o profile.svg -- python script.py
        """
        data = cls.get_flamegraph_data()
        
        # Generate simple SVG flamegraph
        svg_content = cls._generate_simple_flamegraph_svg(data)
        
        with open(filepath, 'w') as f:
            f.write(svg_content)
    
    @classmethod
    def _generate_simple_flamegraph_svg(cls, data: List[Dict[str, Any]]) -> str:
        """Generate a simple SVG flamegraph."""
        if not data:
            return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="100"><text x="10" y="50">No profiling data</text></svg>'
        
        total_time = sum(d['value'] for d in data)
        if total_time == 0:
            total_time = 1
        
        width = 800
        height = max(100, len(data) * 25 + 50)
        
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
            '<style>rect:hover { opacity: 0.8; } text { font-family: monospace; font-size: 12px; }</style>',
            f'<text x="10" y="20">PraisonAI Profiling Flamegraph (Total: {total_time:.2f}ms)</text>'
        ]
        
        y = 40
        for item in sorted(data, key=lambda x: x['value'], reverse=True)[:20]:
            bar_width = max(10, (item['value'] / total_time) * (width - 20))
            color = f'hsl({int(item["value"] / total_time * 120)}, 70%, 50%)'
            
            svg_parts.append(
                f'<rect x="10" y="{y}" width="{bar_width}" height="20" fill="{color}" />'
            )
            svg_parts.append(
                f'<text x="15" y="{y + 15}">{item["name"]}: {item["value"]:.2f}ms</text>'
            )
            y += 25
        
        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)
    
    # ========================================================================
    # Export Functions
    # ========================================================================
    
    @classmethod
    def export_json(cls) -> str:
        """Export profiling data as JSON."""
        # Get summary and stats first (they acquire their own locks)
        summary = cls.get_summary()
        stats = cls.get_statistics()
        
        with cls._lock:
            data = {
                'summary': summary,
                'statistics': stats,
                'timings': [asdict(t) for t in cls._timings],
                'api_calls': [asdict(a) for a in cls._api_calls],
                'streaming': [asdict(s) for s in cls._streaming],
                'memory': [asdict(m) for m in cls._memory],
                'imports': [asdict(i) for i in cls._imports],
                'flow': [asdict(f) for f in cls._flow]
            }
            return json.dumps(data, indent=2, default=str)
    
    @classmethod
    def export_html(cls) -> str:
        """Export profiling data as HTML report."""
        summary = cls.get_summary()
        stats = cls.get_statistics()
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>PraisonAI Profiling Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        h2 {{ color: #666; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f5f5f5; }}
        .metric {{ display: inline-block; margin: 10px; padding: 15px; background: #f9f9f9; border-radius: 5px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: #0066cc; }}
        .metric-label {{ font-size: 12px; color: #666; }}
    </style>
</head>
<body>
    <h1>PraisonAI Profiling Report</h1>
    
    <h2>Summary</h2>
    <div class="metric">
        <div class="metric-value">{summary['total_time_ms']:.2f}ms</div>
        <div class="metric-label">Total Time</div>
    </div>
    <div class="metric">
        <div class="metric-value">{summary['timing_count']}</div>
        <div class="metric-label">Operations</div>
    </div>
    <div class="metric">
        <div class="metric-value">{len(cls._api_calls)}</div>
        <div class="metric-label">API Calls</div>
    </div>
    <div class="metric">
        <div class="metric-value">{len(cls._streaming)}</div>
        <div class="metric-label">Streams</div>
    </div>
    
    <h2>Statistics</h2>
    <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>P50 (Median)</td><td>{stats['p50']:.2f}ms</td></tr>
        <tr><td>P95</td><td>{stats['p95']:.2f}ms</td></tr>
        <tr><td>P99</td><td>{stats['p99']:.2f}ms</td></tr>
        <tr><td>Mean</td><td>{stats['mean']:.2f}ms</td></tr>
        <tr><td>Std Dev</td><td>{stats['std_dev']:.2f}ms</td></tr>
        <tr><td>Min</td><td>{stats['min']:.2f}ms</td></tr>
        <tr><td>Max</td><td>{stats['max']:.2f}ms</td></tr>
    </table>
    
    <h2>Slowest Operations</h2>
    <table>
        <tr><th>Operation</th><th>Duration (ms)</th></tr>
        {''.join(f"<tr><td>{name}</td><td>{dur:.2f}</td></tr>" for name, dur in summary['slowest_operations'])}
    </table>
    
    <h2>API Calls</h2>
    <table>
        <tr><th>Endpoint</th><th>Method</th><th>Duration (ms)</th><th>Status</th></tr>
        {''.join(f"<tr><td>{a.endpoint}</td><td>{a.method}</td><td>{a.duration_ms:.2f}</td><td>{a.status_code}</td></tr>" for a in cls._api_calls[:20])}
    </table>
    
    <h2>Streaming</h2>
    <table>
        <tr><th>Name</th><th>TTFT (ms)</th><th>Total (ms)</th><th>Chunks</th><th>Tokens</th></tr>
        {''.join(f"<tr><td>{s.name}</td><td>{s.ttft_ms:.2f}</td><td>{s.total_ms:.2f}</td><td>{s.chunk_count}</td><td>{s.total_tokens}</td></tr>" for s in cls._streaming[:20])}
    </table>
</body>
</html>'''
        return html
    
    @classmethod
    def export_to_file(cls, filepath: str, format: str = "json") -> None:
        """Export profiling data to file."""
        if format == "json":
            content = cls.export_json()
        elif format == "html":
            content = cls.export_html()
        else:
            raise ValueError(f"Unknown format: {format}")
        
        with open(filepath, 'w') as f:
            f.write(content)


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
