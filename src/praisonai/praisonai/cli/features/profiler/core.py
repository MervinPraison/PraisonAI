"""
Core profiler implementation for PraisonAI CLI.

Provides cProfile-based profiling with detailed per-file/per-function timing,
call graphs, and import time analysis.
"""

import cProfile
import io
import json
import os
import pstats
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# Patterns for secrets to redact
SECRET_PATTERNS = [
    r'sk-[a-zA-Z0-9]{20,}',  # OpenAI keys
    r'sk-ant-[a-zA-Z0-9-]{20,}',  # Anthropic keys
    r'AIza[a-zA-Z0-9_-]{35}',  # Google API keys
    r'tvly-[a-zA-Z0-9-]{20,}',  # Tavily keys
    r'[a-zA-Z0-9_-]{32,}',  # Generic long tokens (be careful)
]


def redact_secrets(text: str) -> str:
    """Redact potential secrets from text."""
    result = text
    for pattern in SECRET_PATTERNS[:4]:  # Skip generic pattern for safety
        result = re.sub(pattern, '[REDACTED]', result)
    return result


@dataclass
class ProfilerConfig:
    """Configuration for profiler."""
    deep: bool = False  # Enable deep call tracing
    limit: int = 30  # Top N functions to show
    sort_by: str = "cumulative"  # cumulative or tottime
    show_files: bool = False  # Group by file
    show_callers: bool = False  # Show callers
    show_callees: bool = False  # Show callees
    importtime: bool = False  # Show import timing
    first_token: bool = False  # Track time to first token
    save_path: Optional[str] = None  # Path to save artifacts
    output_format: str = "text"  # text or json
    stream: bool = False  # Streaming mode


@dataclass
class TimingBreakdown:
    """Timing breakdown for profiling."""
    cli_parse_ms: float = 0.0
    imports_ms: float = 0.0
    agent_construction_ms: float = 0.0
    model_init_ms: float = 0.0
    first_token_ms: float = 0.0
    total_run_ms: float = 0.0


@dataclass
class FunctionStats:
    """Statistics for a single function."""
    name: str
    filename: str
    lineno: int
    calls: int
    tottime: float  # Time in function excluding subcalls
    cumtime: float  # Time in function including subcalls
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "filename": self.filename,
            "lineno": self.lineno,
            "calls": self.calls,
            "tottime_ms": self.tottime * 1000,
            "cumtime_ms": self.cumtime * 1000,
        }


@dataclass
class FileStats:
    """Statistics aggregated by file."""
    filename: str
    total_time: float
    functions: List[FunctionStats] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "total_time_ms": self.total_time * 1000,
            "function_count": len(self.functions),
        }


@dataclass
class ProfilerResult:
    """Result from a profiling run."""
    prompt: str
    response: str
    timing: TimingBreakdown
    function_stats: List[FunctionStats]
    file_stats: List[FileStats]
    callers: Dict[str, List[str]] = field(default_factory=dict)
    callees: Dict[str, List[str]] = field(default_factory=dict)
    import_times: List[Tuple[str, float]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "prompt": self.prompt[:200] + "..." if len(self.prompt) > 200 else self.prompt,
            "response_preview": self.response[:200] + "..." if len(self.response) > 200 else self.response,
            "timing": {
                "cli_parse_ms": self.timing.cli_parse_ms,
                "imports_ms": self.timing.imports_ms,
                "agent_construction_ms": self.timing.agent_construction_ms,
                "model_init_ms": self.timing.model_init_ms,
                "first_token_ms": self.timing.first_token_ms,
                "total_run_ms": self.timing.total_run_ms,
            },
            "top_functions": [f.to_dict() for f in self.function_stats[:20]],
            "top_files": [f.to_dict() for f in self.file_stats[:10]],
        }


class QueryProfiler:
    """
    Profiler for query execution.
    
    Uses cProfile for function-level profiling and optional sys.setprofile
    for deep call tracing.
    """
    
    def __init__(self, config: Optional[ProfilerConfig] = None):
        self.config = config or ProfilerConfig()
        self.profiler = cProfile.Profile()
        self._first_token_time: Optional[float] = None
        self._start_time: float = 0.0
        self._deep_trace_data: Dict[str, Dict] = {}
    
    def _on_first_token(self):
        """Called when first token is received (for streaming)."""
        if self._first_token_time is None:
            self._first_token_time = time.perf_counter()
    
    def _deep_trace_callback(self, frame, event, arg):
        """Callback for sys.setprofile deep tracing."""
        if event not in ('call', 'return'):
            return
        
        filename = frame.f_code.co_filename
        funcname = frame.f_code.co_name
        lineno = frame.f_lineno
        
        key = f"{filename}:{funcname}:{lineno}"
        
        if key not in self._deep_trace_data:
            self._deep_trace_data[key] = {
                'filename': filename,
                'funcname': funcname,
                'lineno': lineno,
                'calls': 0,
                'total_time': 0.0,
                'start_times': [],
            }
        
        if event == 'call':
            self._deep_trace_data[key]['calls'] += 1
            self._deep_trace_data[key]['start_times'].append(time.perf_counter())
        elif event == 'return' and self._deep_trace_data[key]['start_times']:
            start = self._deep_trace_data[key]['start_times'].pop()
            self._deep_trace_data[key]['total_time'] += time.perf_counter() - start
    
    def profile_query(
        self,
        prompt: str,
        model: Optional[str] = None,
        stream: bool = False,
    ) -> ProfilerResult:
        """
        Profile a query execution.
        
        Args:
            prompt: The prompt to execute
            model: Optional model to use
            stream: Whether to use streaming mode
            
        Returns:
            ProfilerResult with detailed timing and statistics
        """
        timing = TimingBreakdown()
        response = ""
        
        # Metadata
        metadata = self._collect_metadata(model)
        
        # Time CLI parsing (simulated - actual parsing happens before this)
        cli_start = time.perf_counter()
        timing.cli_parse_ms = (time.perf_counter() - cli_start) * 1000
        
        # Time imports
        import_start = time.perf_counter()
        try:
            from praisonaiagents import Agent
        except ImportError:
            raise ImportError("praisonaiagents not installed")
        timing.imports_ms = (time.perf_counter() - import_start) * 1000
        
        # Time agent construction
        construct_start = time.perf_counter()
        agent_config = {
            "name": "ProfilerAgent",
            "role": "Assistant",
            "goal": "Complete the task",
            "verbose": False,
        }
        if model:
            agent_config["llm"] = model
        
        agent = Agent(**agent_config)
        timing.agent_construction_ms = (time.perf_counter() - construct_start) * 1000
        
        # Time model initialization (first call)
        model_init_start = time.perf_counter()
        timing.model_init_ms = (time.perf_counter() - model_init_start) * 1000
        
        # Profile the actual execution
        self._start_time = time.perf_counter()
        self._first_token_time = None
        
        if self.config.deep:
            sys.setprofile(self._deep_trace_callback)
        
        self.profiler.enable()
        
        try:
            if stream and hasattr(agent, '_start_stream'):
                # Streaming mode with first token tracking
                chunks = []
                for chunk in agent._start_stream(prompt):
                    if not chunks:
                        self._on_first_token()
                    chunks.append(chunk)
                response = ''.join(chunks)
            else:
                # Non-streaming mode
                response = agent.start(prompt)
                if response is None:
                    response = ""
        finally:
            self.profiler.disable()
            if self.config.deep:
                sys.setprofile(None)
        
        end_time = time.perf_counter()
        timing.total_run_ms = (end_time - self._start_time) * 1000
        
        if self._first_token_time:
            timing.first_token_ms = (self._first_token_time - self._start_time) * 1000
        
        # Extract statistics
        function_stats = self._extract_function_stats()
        file_stats = self._extract_file_stats(function_stats)
        callers, callees = self._extract_call_graph()
        
        # Get import times if requested
        import_times = []
        if self.config.importtime:
            import_times = self._get_import_times()
        
        return ProfilerResult(
            prompt=prompt,
            response=str(response),
            timing=timing,
            function_stats=function_stats,
            file_stats=file_stats,
            callers=callers if self.config.show_callers else {},
            callees=callees if self.config.show_callees else {},
            import_times=import_times,
            metadata=metadata,
        )
    
    def _collect_metadata(self, model: Optional[str]) -> Dict[str, Any]:
        """Collect system metadata."""
        import platform
        try:
            from praisonai.version import __version__ as praisonai_version
        except ImportError:
            praisonai_version = "unknown"
        
        return {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "praisonai_version": praisonai_version,
            "model": model or "default",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    
    def _extract_function_stats(self) -> List[FunctionStats]:
        """Extract function statistics from profiler."""
        stats_stream = io.StringIO()
        stats = pstats.Stats(self.profiler, stream=stats_stream)
        
        # Sort by configured key
        sort_key = pstats.SortKey.CUMULATIVE if self.config.sort_by == "cumulative" else pstats.SortKey.TIME
        stats.sort_stats(sort_key)
        
        function_stats = []
        for (filename, lineno, funcname), (cc, nc, tt, ct, callers) in stats.stats.items():
            function_stats.append(FunctionStats(
                name=funcname,
                filename=filename,
                lineno=lineno,
                calls=nc,
                tottime=tt,
                cumtime=ct,
            ))
        
        # Sort and limit
        if self.config.sort_by == "cumulative":
            function_stats.sort(key=lambda x: x.cumtime, reverse=True)
        else:
            function_stats.sort(key=lambda x: x.tottime, reverse=True)
        
        return function_stats[:self.config.limit]
    
    def _extract_file_stats(self, function_stats: List[FunctionStats]) -> List[FileStats]:
        """Aggregate statistics by file."""
        file_map: Dict[str, FileStats] = {}
        
        for func in function_stats:
            if func.filename not in file_map:
                file_map[func.filename] = FileStats(
                    filename=func.filename,
                    total_time=0.0,
                    functions=[],
                )
            file_map[func.filename].total_time += func.cumtime
            file_map[func.filename].functions.append(func)
        
        file_stats = list(file_map.values())
        file_stats.sort(key=lambda x: x.total_time, reverse=True)
        
        return file_stats[:self.config.limit]
    
    def _extract_call_graph(self) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        """Extract caller/callee relationships."""
        callers: Dict[str, List[str]] = {}
        callees: Dict[str, List[str]] = {}
        
        stats = pstats.Stats(self.profiler)
        
        for (filename, lineno, funcname), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
            func_key = f"{funcname} ({os.path.basename(filename)}:{lineno})"
            
            if caller_dict:
                callers[func_key] = []
                for (caller_file, caller_line, caller_name), _ in caller_dict.items():
                    caller_key = f"{caller_name} ({os.path.basename(caller_file)}:{caller_line})"
                    callers[func_key].append(caller_key)
                    
                    if caller_key not in callees:
                        callees[caller_key] = []
                    callees[caller_key].append(func_key)
        
        return callers, callees
    
    def _get_import_times(self) -> List[Tuple[str, float]]:
        """Get import timing by running subprocess with -X importtime."""
        try:
            result = subprocess.run(
                [sys.executable, "-X", "importtime", "-c", "import praisonaiagents"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            import_times = []
            for line in result.stderr.split('\n'):
                if 'import time:' in line:
                    # Parse: "import time:       123 |        456 | module_name"
                    match = re.search(r'import time:\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(.+)', line)
                    if match:
                        self_time = int(match.group(1))
                        cumulative = int(match.group(2))
                        module = match.group(3).strip()
                        import_times.append((module, cumulative / 1000000))  # Convert to seconds
            
            # Sort by time descending
            import_times.sort(key=lambda x: x[1], reverse=True)
            return import_times[:20]  # Top 20
            
        except Exception:
            return []
    
    def save_artifacts(self, result: ProfilerResult, base_path: str):
        """Save profiling artifacts to files."""
        base = Path(base_path)
        base.parent.mkdir(parents=True, exist_ok=True)
        
        # Save .prof binary
        prof_path = str(base) + ".prof"
        self.profiler.dump_stats(prof_path)
        
        # Save .txt report
        txt_path = str(base) + ".txt"
        with open(txt_path, 'w') as f:
            f.write(format_profile_report(result, self.config))
        
        # Save .json if requested
        if self.config.output_format == "json":
            json_path = str(base) + ".json"
            with open(json_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
        
        return prof_path, txt_path


def run_profiled_query(
    prompt: str,
    config: Optional[ProfilerConfig] = None,
    model: Optional[str] = None,
) -> ProfilerResult:
    """
    Run a profiled query.
    
    Args:
        prompt: The prompt to execute
        config: Profiler configuration
        model: Optional model to use
        
    Returns:
        ProfilerResult with detailed timing and statistics
    """
    profiler = QueryProfiler(config)
    return profiler.profile_query(prompt, model=model, stream=config.stream if config else False)


def format_profile_report(result: ProfilerResult, config: Optional[ProfilerConfig] = None) -> str:
    """
    Format a profile result as a text report.
    
    Args:
        result: ProfilerResult to format
        config: Optional profiler config
        
    Returns:
        Formatted text report
    """
    config = config or ProfilerConfig()
    lines = []
    
    # Header
    lines.append("=" * 70)
    lines.append("PraisonAI Profile Report")
    lines.append("=" * 70)
    lines.append("")
    
    # Metadata
    lines.append("## System Information")
    lines.append(f"  Timestamp:        {result.timestamp}")
    lines.append(f"  Python Version:   {result.metadata.get('python_version', 'N/A')}")
    lines.append(f"  Platform:         {result.metadata.get('platform', 'N/A')}")
    lines.append(f"  PraisonAI:        {result.metadata.get('praisonai_version', 'N/A')}")
    lines.append(f"  Model:            {result.metadata.get('model', 'N/A')}")
    lines.append("")
    
    # Timing breakdown
    lines.append("## Timing Breakdown")
    lines.append(f"  CLI Parse:        {result.timing.cli_parse_ms:>10.2f} ms")
    lines.append(f"  Imports:          {result.timing.imports_ms:>10.2f} ms")
    lines.append(f"  Agent Construct:  {result.timing.agent_construction_ms:>10.2f} ms")
    lines.append(f"  Model Init:       {result.timing.model_init_ms:>10.2f} ms")
    if result.timing.first_token_ms > 0:
        lines.append(f"  First Token:      {result.timing.first_token_ms:>10.2f} ms")
    lines.append(f"  Total Run:        {result.timing.total_run_ms:>10.2f} ms")
    lines.append("")
    
    # Per-file timing (if requested)
    if config.show_files and result.file_stats:
        lines.append("## Per-File Timing (Top Files)")
        lines.append("-" * 70)
        lines.append(f"{'File':<50} {'Time (ms)':>15}")
        lines.append("-" * 70)
        for fs in result.file_stats[:15]:
            filename = os.path.basename(fs.filename)
            if len(filename) > 48:
                filename = "..." + filename[-45:]
            lines.append(f"{filename:<50} {fs.total_time * 1000:>15.2f}")
        lines.append("")
    
    # Per-function timing
    lines.append("## Per-Function Timing (Top Functions)")
    lines.append("-" * 70)
    sort_label = "Cumulative" if config.sort_by == "cumulative" else "Total"
    lines.append(f"{'Function':<35} {'Calls':>8} {sort_label + ' (ms)':>12} {'Self (ms)':>12}")
    lines.append("-" * 70)
    for fs in result.function_stats[:config.limit]:
        funcname = fs.name
        if len(funcname) > 33:
            funcname = funcname[:30] + "..."
        lines.append(f"{funcname:<35} {fs.calls:>8} {fs.cumtime * 1000:>12.2f} {fs.tottime * 1000:>12.2f}")
    lines.append("")
    
    # Callers (if requested)
    if config.show_callers and result.callers:
        lines.append("## Callers (Who called each function)")
        lines.append("-" * 70)
        for func, caller_list in list(result.callers.items())[:10]:
            lines.append(f"  {func}:")
            for caller in caller_list[:5]:
                lines.append(f"    <- {caller}")
        lines.append("")
    
    # Callees (if requested)
    if config.show_callees and result.callees:
        lines.append("## Callees (What each function called)")
        lines.append("-" * 70)
        for func, callee_list in list(result.callees.items())[:10]:
            lines.append(f"  {func}:")
            for callee in callee_list[:5]:
                lines.append(f"    -> {callee}")
        lines.append("")
    
    # Import times (if requested)
    if config.importtime and result.import_times:
        lines.append("## Import Times (Top Modules)")
        lines.append("-" * 70)
        lines.append(f"{'Module':<50} {'Time (ms)':>15}")
        lines.append("-" * 70)
        for module, time_sec in result.import_times[:15]:
            module_name = module
            if len(module_name) > 48:
                module_name = "..." + module_name[-45:]
            lines.append(f"{module_name:<50} {time_sec * 1000:>15.2f}")
        lines.append("")
    
    # Response preview
    lines.append("## Response Preview")
    lines.append("-" * 70)
    preview = result.response[:500] + "..." if len(result.response) > 500 else result.response
    lines.append(preview)
    lines.append("")
    
    lines.append("=" * 70)
    
    return "\n".join(lines)
