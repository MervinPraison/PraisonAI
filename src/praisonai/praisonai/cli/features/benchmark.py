"""
Comprehensive Benchmarking CLI for PraisonAI.

Provides deep profiling and comparison across all execution paths:
- OpenAI SDK (baseline)
- PraisonAI Agent (Python SDK)
- PraisonAI CLI (fast path)
- PraisonAI CLI with profiling
- PraisonAI Workflow (single agent)
- PraisonAI Workflow (multi-agent)
- PraisonAI via LiteLLM
- LiteLLM standalone

Usage: praisonai benchmark profile "What is 2+2?"
"""

import os
import sys
import json
import time
import subprocess
import statistics
import cProfile
import pstats
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from .base import FlagHandler


# Deep profiling constants
MAX_FUNCTION_STATS = 1000
MAX_CALL_GRAPH_EDGES = 5000


@dataclass
class PhaseTimings:
    """Timing breakdown for execution phases."""
    import_ms: float = 0.0
    init_ms: float = 0.0
    network_ms: float = 0.0
    exec_ms: float = 0.0
    render_ms: float = 0.0
    total_ms: float = 0.0
    ttft_ms: float = 0.0  # Time to first token
    subprocess_ms: float = 0.0  # CLI subprocess overhead


@dataclass
class FunctionStat:
    """Statistics for a single function from cProfile."""
    name: str
    file: str
    line: int
    calls: int
    total_time_ms: float  # Self time
    cumulative_time_ms: float  # Cumulative time
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "calls": self.calls,
            "total_time_ms": self.total_time_ms,
            "cumulative_time_ms": self.cumulative_time_ms,
        }


@dataclass
class CallGraphData:
    """Call graph data (callers and callees)."""
    callers: Dict[str, List[str]] = field(default_factory=dict)
    callees: Dict[str, List[str]] = field(default_factory=dict)
    
    @property
    def edge_count(self) -> int:
        return sum(len(v) for v in self.callers.values())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "callers": self.callers,
            "callees": self.callees,
            "edge_count": self.edge_count,
        }


@dataclass
class ModuleBreakdown:
    """Module/file breakdown for deep profile visibility."""
    praisonai_modules: List[Tuple[str, float]] = field(default_factory=list)  # (file, cumulative_ms)
    agent_modules: List[Tuple[str, float]] = field(default_factory=list)
    network_modules: List[Tuple[str, float]] = field(default_factory=list)
    third_party_modules: List[Tuple[str, float]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "praisonai": [{"file": f, "cumulative_ms": t} for f, t in self.praisonai_modules[:20]],
            "agent": [{"file": f, "cumulative_ms": t} for f, t in self.agent_modules[:20]],
            "network": [{"file": f, "cumulative_ms": t} for f, t in self.network_modules[:20]],
            "third_party": [{"file": f, "cumulative_ms": t} for f, t in self.third_party_modules[:20]],
        }


@dataclass
class DeepProfileData:
    """Deep profiling data from cProfile."""
    functions: List[FunctionStat] = field(default_factory=list)
    call_graph: Optional[CallGraphData] = None
    module_breakdown: Optional[ModuleBreakdown] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "functions": [f.to_dict() for f in self.functions],
        }
        if self.call_graph:
            result["call_graph"] = self.call_graph.to_dict()
        if self.module_breakdown:
            result["module_breakdown"] = self.module_breakdown.to_dict()
        return result


@dataclass
class BenchmarkRun:
    """Single benchmark run result."""
    path_name: str
    iteration: int
    is_cold: bool
    timings: PhaseTimings
    memory_mb: float = 0.0
    success: bool = True
    error: str = ""
    response_preview: str = ""
    deep_profile: Optional[DeepProfileData] = None  # Deep profiling data


@dataclass
class BenchmarkResult:
    """Aggregated benchmark result for a path."""
    path_name: str
    runs: List[BenchmarkRun] = field(default_factory=list)
    
    # Aggregated stats
    mean_total_ms: float = 0.0
    min_total_ms: float = 0.0
    max_total_ms: float = 0.0
    std_total_ms: float = 0.0
    
    mean_import_ms: float = 0.0
    mean_init_ms: float = 0.0
    mean_network_ms: float = 0.0
    
    cold_total_ms: float = 0.0
    warm_total_ms: float = 0.0
    
    delta_vs_sdk_ms: float = 0.0
    
    # Aggregated deep profile data (when --deep is used)
    aggregated_functions: Optional[List[FunctionStat]] = None
    aggregated_call_graph: Optional[CallGraphData] = None
    aggregated_module_breakdown: Optional[ModuleBreakdown] = None
    
    def compute_stats(self, sdk_baseline_ms: float = 0.0):
        """Compute aggregated statistics from runs."""
        if not self.runs:
            return
        
        totals = [r.timings.total_ms for r in self.runs if r.success]
        if not totals:
            return
        
        self.mean_total_ms = statistics.mean(totals)
        self.min_total_ms = min(totals)
        self.max_total_ms = max(totals)
        self.std_total_ms = statistics.stdev(totals) if len(totals) > 1 else 0.0
        
        self.mean_import_ms = statistics.mean([r.timings.import_ms for r in self.runs if r.success])
        self.mean_init_ms = statistics.mean([r.timings.init_ms for r in self.runs if r.success])
        self.mean_network_ms = statistics.mean([r.timings.network_ms for r in self.runs if r.success])
        
        cold_runs = [r.timings.total_ms for r in self.runs if r.is_cold and r.success]
        warm_runs = [r.timings.total_ms for r in self.runs if not r.is_cold and r.success]
        
        self.cold_total_ms = statistics.mean(cold_runs) if cold_runs else 0.0
        self.warm_total_ms = statistics.mean(warm_runs) if warm_runs else 0.0
        
        self.delta_vs_sdk_ms = self.mean_total_ms - sdk_baseline_ms
        
        # Aggregate deep profile data if present
        self._aggregate_deep_profiles()
    
    def _aggregate_deep_profiles(self):
        """Aggregate deep profile data across all runs."""
        runs_with_deep = [r for r in self.runs if r.success and r.deep_profile]
        if not runs_with_deep:
            return
        
        # Aggregate function stats by averaging times and summing calls
        func_aggregates: Dict[str, Dict[str, Any]] = {}
        
        for run in runs_with_deep:
            for func in run.deep_profile.functions:
                key = f"{func.name}:{func.file}:{func.line}"
                if key not in func_aggregates:
                    func_aggregates[key] = {
                        "name": func.name,
                        "file": func.file,
                        "line": func.line,
                        "calls_list": [],
                        "total_time_list": [],
                        "cumulative_time_list": [],
                    }
                func_aggregates[key]["calls_list"].append(func.calls)
                func_aggregates[key]["total_time_list"].append(func.total_time_ms)
                func_aggregates[key]["cumulative_time_list"].append(func.cumulative_time_ms)
        
        # Build aggregated function list
        aggregated = []
        for key, data in func_aggregates.items():
            aggregated.append(FunctionStat(
                name=data["name"],
                file=data["file"],
                line=data["line"],
                calls=int(statistics.mean(data["calls_list"])),
                total_time_ms=statistics.mean(data["total_time_list"]),
                cumulative_time_ms=statistics.mean(data["cumulative_time_list"]),
            ))
        
        # Sort by cumulative time and limit
        aggregated.sort(key=lambda x: x.cumulative_time_ms, reverse=True)
        self.aggregated_functions = aggregated[:100]
        
        # Use call graph from first run (structure is consistent)
        if runs_with_deep[0].deep_profile.call_graph:
            self.aggregated_call_graph = runs_with_deep[0].deep_profile.call_graph
        
        # Use module breakdown from first run
        if runs_with_deep[0].deep_profile.module_breakdown:
            self.aggregated_module_breakdown = runs_with_deep[0].deep_profile.module_breakdown


@dataclass
class BenchmarkReport:
    """Complete benchmark report."""
    timestamp: str
    prompt: str
    iterations: int
    results: Dict[str, BenchmarkResult] = field(default_factory=dict)
    sdk_baseline_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        results_dict = {}
        for name, r in self.results.items():
            result_data = {
                "path_name": r.path_name,
                "mean_total_ms": r.mean_total_ms,
                "min_total_ms": r.min_total_ms,
                "max_total_ms": r.max_total_ms,
                "std_total_ms": r.std_total_ms,
                "mean_import_ms": r.mean_import_ms,
                "mean_init_ms": r.mean_init_ms,
                "mean_network_ms": r.mean_network_ms,
                "cold_total_ms": r.cold_total_ms,
                "warm_total_ms": r.warm_total_ms,
                "delta_vs_sdk_ms": r.delta_vs_sdk_ms,
                "runs": [
                    {
                        "iteration": run.iteration,
                        "is_cold": run.is_cold,
                        "total_ms": run.timings.total_ms,
                        "import_ms": run.timings.import_ms,
                        "init_ms": run.timings.init_ms,
                        "network_ms": run.timings.network_ms,
                        "memory_mb": run.memory_mb,
                        "success": run.success,
                        **({"deep_profile": run.deep_profile.to_dict()} if run.deep_profile else {})
                    }
                    for run in r.runs
                ]
            }
            
            # Add aggregated deep profile data if present
            if r.aggregated_functions:
                result_data["functions"] = [f.to_dict() for f in r.aggregated_functions]
            if r.aggregated_call_graph:
                result_data["call_graph"] = r.aggregated_call_graph.to_dict()
            if r.aggregated_module_breakdown:
                result_data["module_breakdown"] = r.aggregated_module_breakdown.to_dict()
            
            results_dict[name] = result_data
        
        return {
            "timestamp": self.timestamp,
            "prompt": self.prompt,
            "iterations": self.iterations,
            "sdk_baseline_ms": self.sdk_baseline_ms,
            "results": results_dict
        }


class BenchmarkHandler(FlagHandler):
    """
    Comprehensive benchmarking handler for PraisonAI.
    
    Commands:
        praisonai benchmark profile [query]  - Run full benchmark suite
        praisonai benchmark sdk [query]      - Benchmark OpenAI SDK only
        praisonai benchmark agent [query]    - Benchmark Agent only
        praisonai benchmark cli [query]      - Benchmark CLI only
        praisonai benchmark compare [query]  - Quick comparison table
    """
    
    DEFAULT_PROMPT = "Hi"
    DEFAULT_ITERATIONS = 3
    DEFAULT_MODEL = "gpt-4o-mini"
    
    # Benchmark paths
    PATHS = [
        "openai_sdk",
        "praisonai_agent",
        "praisonai_cli",
        "praisonai_cli_profile",
        "praisonai_workflow_single",
        "praisonai_workflow_multi",
        "praisonai_litellm",
        "litellm_standalone",
    ]
    
    @property
    def feature_name(self) -> str:
        return "benchmark"
    
    @property
    def flag_name(self) -> str:
        return "benchmark"
    
    @property
    def flag_help(self) -> str:
        return "Run comprehensive performance benchmarks"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if benchmarking is available."""
        return True, ""
    
    def execute(self, *args, **kwargs) -> Any:
        """Execute the benchmark command."""
        return self.handle(*args, **kwargs)
    
    def _get_project_root(self) -> str:
        """Get the project root directory."""
        # Navigate up from this file to find the project root
        current = Path(__file__).resolve()
        # Go up to praisonai-package
        for _ in range(6):
            current = current.parent
            if (current / "pyproject.toml").exists():
                return str(current)
        return os.getcwd()
    
    def _run_subprocess_benchmark(self, code: str, cwd: str = None) -> Tuple[Dict[str, float], str, str]:
        """
        Run a benchmark in a subprocess and return timing data.
        
        Returns:
            Tuple of (timings_dict, stdout, stderr)
        """
        if cwd is None:
            cwd = self._get_project_root()
        
        t0 = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=cwd,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=120
        )
        subprocess_time = (time.perf_counter() - t0) * 1000
        
        timings = {"subprocess_ms": subprocess_time}
        
        # Parse JSON output from the benchmark code
        if result.returncode == 0 and result.stdout.strip():
            try:
                # Look for JSON in the output
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    if line.startswith("{") and line.endswith("}"):
                        data = json.loads(line)
                        timings.update(data)
                        break
            except json.JSONDecodeError:
                pass
        
        return timings, result.stdout, result.stderr
    
    def _extract_function_stats(self, profiler: cProfile.Profile, limit: int = 30, 
                                 sort_by: str = "cumulative") -> List[FunctionStat]:
        """Extract function statistics from cProfile."""
        stats = pstats.Stats(profiler)
        stats.sort_stats(sort_by)
        
        function_stats = []
        for (filename, line, name), (cc, nc, tt, ct, callers) in stats.stats.items():
            if len(function_stats) >= MAX_FUNCTION_STATS:
                break
            
            function_stats.append(FunctionStat(
                name=name,
                file=filename,
                line=line,
                calls=nc,
                total_time_ms=tt * 1000,
                cumulative_time_ms=ct * 1000,
            ))
        
        function_stats.sort(key=lambda x: x.cumulative_time_ms, reverse=True)
        return function_stats[:limit]
    
    def _extract_call_graph(self, profiler: cProfile.Profile) -> CallGraphData:
        """Extract call graph from cProfile."""
        stats = pstats.Stats(profiler)
        
        callers: Dict[str, List[str]] = {}
        callees: Dict[str, List[str]] = {}
        edge_count = 0
        
        for (filename, line, name), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
            if edge_count >= MAX_CALL_GRAPH_EDGES:
                break
            
            callee_key = f"{name}:{filename}:{line}"
            
            for (caller_file, caller_line, caller_name), _ in caller_dict.items():
                if edge_count >= MAX_CALL_GRAPH_EDGES:
                    break
                
                caller_key = f"{caller_name}:{caller_file}:{caller_line}"
                
                if callee_key not in callers:
                    callers[callee_key] = []
                if caller_key not in callers[callee_key]:
                    callers[callee_key].append(caller_key)
                
                if caller_key not in callees:
                    callees[caller_key] = []
                if callee_key not in callees[caller_key]:
                    callees[caller_key].append(callee_key)
                
                edge_count += 1
        
        return CallGraphData(callers=callers, callees=callees)
    
    def _extract_module_breakdown(self, functions: List[FunctionStat]) -> ModuleBreakdown:
        """Extract module breakdown from function stats."""
        praisonai_modules: Dict[str, float] = {}
        agent_modules: Dict[str, float] = {}
        network_modules: Dict[str, float] = {}
        third_party_modules: Dict[str, float] = {}
        
        for func in functions:
            file_path = func.file.lower()
            cumul = func.cumulative_time_ms
            
            if "praisonai" in file_path and "agents" not in file_path:
                praisonai_modules[func.file] = praisonai_modules.get(func.file, 0) + cumul
            elif "praisonaiagents" in file_path or ("praisonai" in file_path and "agents" in file_path):
                agent_modules[func.file] = agent_modules.get(func.file, 0) + cumul
            elif any(x in file_path for x in ["httpx", "httpcore", "urllib", "requests", "aiohttp", "openai"]):
                network_modules[func.file] = network_modules.get(func.file, 0) + cumul
            elif "site-packages" in file_path or not file_path.startswith("/"):
                third_party_modules[func.file] = third_party_modules.get(func.file, 0) + cumul
        
        def to_sorted_list(d: Dict[str, float]) -> List[Tuple[str, float]]:
            return sorted(d.items(), key=lambda x: x[1], reverse=True)[:20]
        
        return ModuleBreakdown(
            praisonai_modules=to_sorted_list(praisonai_modules),
            agent_modules=to_sorted_list(agent_modules),
            network_modules=to_sorted_list(network_modules),
            third_party_modules=to_sorted_list(third_party_modules),
        )
    
    def _run_with_deep_profile(self, func, limit: int = 30) -> Tuple[Any, DeepProfileData]:
        """Run a function with deep cProfile profiling."""
        profiler = cProfile.Profile()
        profiler.enable()
        
        try:
            result = func()
        finally:
            profiler.disable()
        
        # Extract deep profile data
        functions = self._extract_function_stats(profiler, limit=limit)
        call_graph = self._extract_call_graph(profiler)
        module_breakdown = self._extract_module_breakdown(functions)
        
        deep_profile = DeepProfileData(
            functions=functions,
            call_graph=call_graph,
            module_breakdown=module_breakdown,
        )
        
        return result, deep_profile
    
    def benchmark_praisonai_agent_deep(self, prompt: str, iteration: int, is_cold: bool, limit: int = 30) -> BenchmarkRun:
        """Benchmark PraisonAI Agent with deep cProfile profiling (in-process)."""
        t0 = time.perf_counter()
        
        # Import timing
        try:
            from praisonaiagents import Agent
        except ImportError:
            return BenchmarkRun(
                path_name="praisonai_agent",
                iteration=iteration,
                is_cold=is_cold,
                timings=PhaseTimings(),
                success=False,
                error="praisonaiagents not installed"
            )
        t_import = time.perf_counter()
        import_ms = (t_import - t0) * 1000
        
        # Run with deep profiling
        profiler = cProfile.Profile()
        profiler.enable()
        
        try:
            agent = Agent(instructions="You are helpful", llm=self.DEFAULT_MODEL, output="minimal")
            t_init = time.perf_counter()
            init_ms = (t_init - t_import) * 1000
            
            result = agent.start(prompt)
            t_network = time.perf_counter()
            network_ms = (t_network - t_init) * 1000
        except Exception as e:
            profiler.disable()
            return BenchmarkRun(
                path_name="praisonai_agent",
                iteration=iteration,
                is_cold=is_cold,
                timings=PhaseTimings(),
                success=False,
                error=str(e)
            )
        finally:
            profiler.disable()
        
        total_ms = (t_network - t0) * 1000
        
        # Extract deep profile data
        functions = self._extract_function_stats(profiler, limit=limit)
        call_graph = self._extract_call_graph(profiler)
        module_breakdown = self._extract_module_breakdown(functions)
        
        deep_profile = DeepProfileData(
            functions=functions,
            call_graph=call_graph,
            module_breakdown=module_breakdown,
        )
        
        return BenchmarkRun(
            path_name="praisonai_agent",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                import_ms=import_ms,
                init_ms=init_ms,
                network_ms=network_ms,
                total_ms=total_ms,
            ),
            success=True,
            response_preview=str(result)[:50] if result else "",
            deep_profile=deep_profile,
        )
    
    def benchmark_openai_sdk_deep(self, prompt: str, iteration: int, is_cold: bool, limit: int = 30) -> BenchmarkRun:
        """Benchmark OpenAI SDK with deep cProfile profiling (in-process)."""
        t0 = time.perf_counter()
        
        # Import timing
        try:
            import openai
        except ImportError:
            return BenchmarkRun(
                path_name="openai_sdk",
                iteration=iteration,
                is_cold=is_cold,
                timings=PhaseTimings(),
                success=False,
                error="openai not installed"
            )
        t_import = time.perf_counter()
        import_ms = (t_import - t0) * 1000
        
        # Run with deep profiling
        profiler = cProfile.Profile()
        profiler.enable()
        
        try:
            client = openai.OpenAI()
            t_init = time.perf_counter()
            init_ms = (t_init - t_import) * 1000
            
            response = client.chat.completions.create(
                model=self.DEFAULT_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10
            )
            result = response.choices[0].message.content
            t_network = time.perf_counter()
            network_ms = (t_network - t_init) * 1000
        except Exception as e:
            profiler.disable()
            return BenchmarkRun(
                path_name="openai_sdk",
                iteration=iteration,
                is_cold=is_cold,
                timings=PhaseTimings(),
                success=False,
                error=str(e)
            )
        finally:
            profiler.disable()
        
        total_ms = (t_network - t0) * 1000
        
        # Extract deep profile data
        functions = self._extract_function_stats(profiler, limit=limit)
        call_graph = self._extract_call_graph(profiler)
        module_breakdown = self._extract_module_breakdown(functions)
        
        deep_profile = DeepProfileData(
            functions=functions,
            call_graph=call_graph,
            module_breakdown=module_breakdown,
        )
        
        return BenchmarkRun(
            path_name="openai_sdk",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                import_ms=import_ms,
                init_ms=init_ms,
                network_ms=network_ms,
                total_ms=total_ms,
            ),
            success=True,
            response_preview=str(result)[:50] if result else "",
            deep_profile=deep_profile,
        )
    
    def benchmark_openai_sdk(self, prompt: str, iteration: int, is_cold: bool) -> BenchmarkRun:
        """Benchmark raw OpenAI SDK."""
        code = f'''
import time
import json
import os

t0 = time.perf_counter()
import openai
t_import = time.perf_counter()

client = openai.OpenAI()
t_init = time.perf_counter()

response = client.chat.completions.create(
    model="{self.DEFAULT_MODEL}",
    messages=[{{"role": "user", "content": "{prompt}"}}],
    max_tokens=10
)
t_network = time.perf_counter()

result = response.choices[0].message.content
t_end = time.perf_counter()

print(json.dumps({{
    "import_ms": (t_import - t0) * 1000,
    "init_ms": (t_init - t_import) * 1000,
    "network_ms": (t_network - t_init) * 1000,
    "exec_ms": (t_end - t_network) * 1000,
    "total_ms": (t_end - t0) * 1000,
    "response": result[:50]
}}))
'''
        timings, stdout, stderr = self._run_subprocess_benchmark(code)
        
        return BenchmarkRun(
            path_name="openai_sdk",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                import_ms=timings.get("import_ms", 0),
                init_ms=timings.get("init_ms", 0),
                network_ms=timings.get("network_ms", 0),
                exec_ms=timings.get("exec_ms", 0),
                total_ms=timings.get("total_ms", 0),
                subprocess_ms=timings.get("subprocess_ms", 0),
            ),
            success="total_ms" in timings,
            error=stderr if "total_ms" not in timings else "",
            response_preview=timings.get("response", "")[:50]
        )
    
    def benchmark_praisonai_agent(self, prompt: str, iteration: int, is_cold: bool) -> BenchmarkRun:
        """Benchmark PraisonAI Agent (Python SDK)."""
        code = f'''
import time
import json
import sys
sys.path.insert(0, "{self._get_project_root()}/src/praisonai")

t0 = time.perf_counter()
from praisonaiagents import Agent
t_import = time.perf_counter()

agent = Agent(instructions="You are helpful", llm="{self.DEFAULT_MODEL}", output="minimal")
t_init = time.perf_counter()

result = agent.start("{prompt}")
t_network = time.perf_counter()

print(json.dumps({{
    "import_ms": (t_import - t0) * 1000,
    "init_ms": (t_init - t_import) * 1000,
    "network_ms": (t_network - t_init) * 1000,
    "total_ms": (t_network - t0) * 1000,
    "response": str(result)[:50] if result else ""
}}))
'''
        timings, stdout, stderr = self._run_subprocess_benchmark(code)
        
        return BenchmarkRun(
            path_name="praisonai_agent",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                import_ms=timings.get("import_ms", 0),
                init_ms=timings.get("init_ms", 0),
                network_ms=timings.get("network_ms", 0),
                total_ms=timings.get("total_ms", 0),
                subprocess_ms=timings.get("subprocess_ms", 0),
            ),
            success="total_ms" in timings,
            error=stderr if "total_ms" not in timings else "",
            response_preview=timings.get("response", "")[:50]
        )
    
    def benchmark_praisonai_cli(self, prompt: str, iteration: int, is_cold: bool, with_profile: bool = False) -> BenchmarkRun:
        """Benchmark PraisonAI CLI."""
        t0 = time.perf_counter()
        
        cmd = ["praisonai", prompt, "--llm", self.DEFAULT_MODEL]
        if with_profile:
            cmd.append("--profile")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self._get_project_root(),
            timeout=120
        )
        
        total_ms = (time.perf_counter() - t0) * 1000
        
        return BenchmarkRun(
            path_name="praisonai_cli_profile" if with_profile else "praisonai_cli",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                total_ms=total_ms,
                subprocess_ms=total_ms,
            ),
            success=result.returncode == 0,
            error=result.stderr[:200] if result.returncode != 0 else "",
            response_preview=result.stdout[:50] if result.stdout else ""
        )
    
    def benchmark_praisonai_workflow_single(self, prompt: str, iteration: int, is_cold: bool) -> BenchmarkRun:
        """Benchmark PraisonAI Workflow with single agent."""
        code = f'''
import time
import json
import sys
sys.path.insert(0, "{self._get_project_root()}/src/praisonai")

t0 = time.perf_counter()
from praisonaiagents import Agent, Task, Agents
t_import = time.perf_counter()

agent = Agent(name="Helper", instructions="You are helpful", llm="{self.DEFAULT_MODEL}", output="minimal")
task = Task(name="respond", description="{prompt}", expected_output="response", agent=agent)
agents = AgentManager(agents=[agent], tasks=[task], verbose=0)
t_init = time.perf_counter()

result = agents.start()
t_network = time.perf_counter()

print(json.dumps({{
    "import_ms": (t_import - t0) * 1000,
    "init_ms": (t_init - t_import) * 1000,
    "network_ms": (t_network - t_init) * 1000,
    "total_ms": (t_network - t0) * 1000,
    "response": str(result)[:50] if result else ""
}}))
'''
        timings, stdout, stderr = self._run_subprocess_benchmark(code)
        
        return BenchmarkRun(
            path_name="praisonai_workflow_single",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                import_ms=timings.get("import_ms", 0),
                init_ms=timings.get("init_ms", 0),
                network_ms=timings.get("network_ms", 0),
                total_ms=timings.get("total_ms", 0),
                subprocess_ms=timings.get("subprocess_ms", 0),
            ),
            success="total_ms" in timings,
            error=stderr[:200] if "total_ms" not in timings else "",
            response_preview=timings.get("response", "")[:50]
        )
    
    def benchmark_praisonai_workflow_multi(self, prompt: str, iteration: int, is_cold: bool) -> BenchmarkRun:
        """Benchmark PraisonAI Workflow with multiple agents."""
        code = f'''
import time
import json
import sys
sys.path.insert(0, "{self._get_project_root()}/src/praisonai")

t0 = time.perf_counter()
from praisonaiagents import Agent, Task, Agents
t_import = time.perf_counter()

agent1 = Agent(name="Analyzer", instructions="Analyze the request", llm="{self.DEFAULT_MODEL}", output="minimal")
agent2 = Agent(name="Responder", instructions="Provide a response", llm="{self.DEFAULT_MODEL}", output="minimal")
task1 = Task(name="analyze", description="Analyze: {prompt}", expected_output="analysis", agent=agent1)
task2 = Task(name="respond", description="Respond based on analysis", expected_output="response", agent=agent2)
agents = AgentManager(agents=[agent1, agent2], tasks=[task1, task2], verbose=0)
t_init = time.perf_counter()

result = agents.start()
t_network = time.perf_counter()

print(json.dumps({{
    "import_ms": (t_import - t0) * 1000,
    "init_ms": (t_init - t_import) * 1000,
    "network_ms": (t_network - t_init) * 1000,
    "total_ms": (t_network - t0) * 1000,
    "response": str(result)[:50] if result else ""
}}))
'''
        timings, stdout, stderr = self._run_subprocess_benchmark(code)
        
        return BenchmarkRun(
            path_name="praisonai_workflow_multi",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                import_ms=timings.get("import_ms", 0),
                init_ms=timings.get("init_ms", 0),
                network_ms=timings.get("network_ms", 0),
                total_ms=timings.get("total_ms", 0),
                subprocess_ms=timings.get("subprocess_ms", 0),
            ),
            success="total_ms" in timings,
            error=stderr[:200] if "total_ms" not in timings else "",
            response_preview=timings.get("response", "")[:50]
        )
    
    def benchmark_praisonai_litellm(self, prompt: str, iteration: int, is_cold: bool) -> BenchmarkRun:
        """Benchmark PraisonAI Agent using LiteLLM path (openai/ prefix)."""
        code = f'''
import time
import json
import sys
sys.path.insert(0, "{self._get_project_root()}/src/praisonai")

t0 = time.perf_counter()
from praisonaiagents import Agent
t_import = time.perf_counter()

agent = Agent(instructions="You are helpful", llm="openai/{self.DEFAULT_MODEL}", output="minimal")
t_init = time.perf_counter()

result = agent.start("{prompt}")
t_network = time.perf_counter()

print(json.dumps({{
    "import_ms": (t_import - t0) * 1000,
    "init_ms": (t_init - t_import) * 1000,
    "network_ms": (t_network - t_init) * 1000,
    "total_ms": (t_network - t0) * 1000,
    "response": str(result)[:50] if result else ""
}}))
'''
        timings, stdout, stderr = self._run_subprocess_benchmark(code)
        
        return BenchmarkRun(
            path_name="praisonai_litellm",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                import_ms=timings.get("import_ms", 0),
                init_ms=timings.get("init_ms", 0),
                network_ms=timings.get("network_ms", 0),
                total_ms=timings.get("total_ms", 0),
                subprocess_ms=timings.get("subprocess_ms", 0),
            ),
            success="total_ms" in timings,
            error=stderr[:200] if "total_ms" not in timings else "",
            response_preview=timings.get("response", "")[:50]
        )
    
    def benchmark_litellm_standalone(self, prompt: str, iteration: int, is_cold: bool) -> BenchmarkRun:
        """Benchmark LiteLLM standalone (raw)."""
        code = f'''
import time
import json
import os

t0 = time.perf_counter()
import litellm
t_import = time.perf_counter()

# Configure
litellm.drop_params = True
t_init = time.perf_counter()

response = litellm.completion(
    model="{self.DEFAULT_MODEL}",
    messages=[{{"role": "user", "content": "{prompt}"}}],
    max_tokens=10
)
t_network = time.perf_counter()

result = response.choices[0].message.content
t_end = time.perf_counter()

print(json.dumps({{
    "import_ms": (t_import - t0) * 1000,
    "init_ms": (t_init - t_import) * 1000,
    "network_ms": (t_network - t_init) * 1000,
    "exec_ms": (t_end - t_network) * 1000,
    "total_ms": (t_end - t0) * 1000,
    "response": result[:50] if result else ""
}}))
'''
        timings, stdout, stderr = self._run_subprocess_benchmark(code)
        
        return BenchmarkRun(
            path_name="litellm_standalone",
            iteration=iteration,
            is_cold=is_cold,
            timings=PhaseTimings(
                import_ms=timings.get("import_ms", 0),
                init_ms=timings.get("init_ms", 0),
                network_ms=timings.get("network_ms", 0),
                exec_ms=timings.get("exec_ms", 0),
                total_ms=timings.get("total_ms", 0),
                subprocess_ms=timings.get("subprocess_ms", 0),
            ),
            success="total_ms" in timings,
            error=stderr[:200] if "total_ms" not in timings else "",
            response_preview=timings.get("response", "")[:50]
        )
    
    def create_timeline_diagram(self, result: BenchmarkResult) -> str:
        """Create ASCII timeline diagram for a benchmark result."""
        if not result.runs:
            return "No data"
        
        # Use mean values
        import_ms = result.mean_import_ms
        init_ms = result.mean_init_ms
        network_ms = result.mean_network_ms
        total_ms = result.mean_total_ms
        
        # Calculate other time
        other_ms = max(0, total_ms - import_ms - init_ms - network_ms)
        
        # Scale to 60 chars width
        if total_ms <= 0:
            return "No timing data"
        
        scale = 50.0 / total_ms
        
        def bar_width(ms):
            return max(1, int(ms * scale))
        
        import_w = bar_width(import_ms)
        init_w = bar_width(init_ms)
        network_w = bar_width(network_ms)
        other_w = bar_width(other_ms)
        
        # Build diagram
        lines = []
        
        # Top line
        total_w = import_w + init_w + network_w + other_w
        lines.append(f"ENTER {'─' * total_w}► RESPONSE")
        
        # Phase boxes
        phases = []
        if import_ms > 0:
            phases.append(("import", import_ms, import_w))
        if init_ms > 0:
            phases.append(("init", init_ms, init_w))
        if network_ms > 0:
            phases.append(("network", network_ms, network_w))
        if other_ms > 10:
            phases.append(("other", other_ms, other_w))
        
        if phases:
            # Phase names line
            name_line = "      "
            for name, ms, w in phases:
                name_line += "│" + name.center(w - 1)
            name_line += "│"
            lines.append(name_line)
            
            # Phase times line
            time_line = "      "
            for name, ms, w in phases:
                time_str = f"{ms:.0f}ms"
                time_line += "│" + time_str.center(w - 1)
            time_line += "│"
            lines.append(time_line)
            
            # Bottom line
            bottom_line = "      "
            for i, (name, ms, w) in enumerate(phases):
                if i == 0:
                    bottom_line += "└" + "─" * (w - 1)
                else:
                    bottom_line += "┴" + "─" * (w - 1)
            bottom_line += "┘"
            lines.append(bottom_line)
        
        # Total line
        lines.append(f"{' ' * 40}TOTAL: {total_ms:.0f}ms")
        
        return "\n".join(lines)
    
    def create_comparison_table(self, report: BenchmarkReport) -> str:
        """Create master ASCII comparison table."""
        lines = []
        
        # Header
        lines.append("+" + "-" * 30 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 12 + "+")
        lines.append(f"| {'Path':<28} | {'Import':>8} | {'Init':>8} | {'Network':>8} | {'Total':>8} | {'Δ SDK':>10} |")
        lines.append("+" + "-" * 30 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 12 + "+")
        
        # Sort by total time
        sorted_results = sorted(report.results.values(), key=lambda r: r.mean_total_ms)
        
        for result in sorted_results:
            delta_str = f"{result.delta_vs_sdk_ms:+.0f}ms" if result.delta_vs_sdk_ms != 0 else "baseline"
            lines.append(
                f"| {result.path_name:<28} | "
                f"{result.mean_import_ms:>6.0f}ms | "
                f"{result.mean_init_ms:>6.0f}ms | "
                f"{result.mean_network_ms:>6.0f}ms | "
                f"{result.mean_total_ms:>6.0f}ms | "
                f"{delta_str:>10} |"
            )
        
        lines.append("+" + "-" * 30 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 12 + "+")
        
        return "\n".join(lines)
    
    def create_variance_table(self, report: BenchmarkReport) -> str:
        """Create variance analysis table."""
        lines = []
        
        lines.append("\n## Variance Analysis")
        lines.append("+" + "-" * 30 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 12 + "+")
        lines.append(f"| {'Path':<28} | {'Mean':>8} | {'Min':>8} | {'Max':>8} | {'StdDev':>8} | {'Cold/Warm':>10} |")
        lines.append("+" + "-" * 30 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 12 + "+")
        
        for name, result in sorted(report.results.items(), key=lambda x: x[1].mean_total_ms):
            cold_warm = f"{result.cold_total_ms:.0f}/{result.warm_total_ms:.0f}" if result.cold_total_ms > 0 else "N/A"
            lines.append(
                f"| {name:<28} | "
                f"{result.mean_total_ms:>6.0f}ms | "
                f"{result.min_total_ms:>6.0f}ms | "
                f"{result.max_total_ms:>6.0f}ms | "
                f"{result.std_total_ms:>6.0f}ms | "
                f"{cold_warm:>10} |"
            )
        
        lines.append("+" + "-" * 30 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 10 + "+" + "-" * 12 + "+")
        
        return "\n".join(lines)
    
    def classify_overhead(self, report: BenchmarkReport) -> str:
        """Classify overhead by category."""
        lines = []
        
        sdk_result = report.results.get("openai_sdk")
        if not sdk_result:
            return "No SDK baseline for comparison"
        
        lines.append("\n## Overhead Classification")
        lines.append("-" * 60)
        
        for name, result in report.results.items():
            if name == "openai_sdk":
                continue
            
            total_overhead = result.delta_vs_sdk_ms
            
            # Classify overhead
            network_variance = abs(result.mean_network_ms - sdk_result.mean_network_ms)
            import_overhead = result.mean_import_ms - sdk_result.mean_import_ms
            init_overhead = result.mean_init_ms - sdk_result.mean_init_ms
            
            lines.append(f"\n{name}:")
            lines.append(f"  Total overhead: {total_overhead:+.0f}ms")
            lines.append(f"  - Network variance (unavoidable): ~{network_variance:.0f}ms")
            lines.append(f"  - Import overhead: {import_overhead:+.0f}ms")
            lines.append(f"  - Init overhead: {init_overhead:+.0f}ms")
            
            # Categorize
            if "cli" in name.lower():
                lines.append(f"  - CLI subprocess overhead: ~100-300ms (estimated)")
            if "litellm" in name.lower():
                lines.append(f"  - LiteLLM wrapper overhead: included in init")
            if "workflow" in name.lower():
                lines.append(f"  - Workflow orchestration: included in init")
        
        return "\n".join(lines)
    
    def create_deep_profile_output(self, result: BenchmarkResult, limit: int = 30) -> str:
        """Create deep profile text output for a benchmark result."""
        lines = []
        
        if not result.aggregated_functions:
            return ""
        
        lines.append("\n## Deep Profile: Top Functions by Cumulative Time")
        lines.append("-" * 80)
        lines.append(f"{'Function':<45} {'Calls':>8} {'Self (ms)':>12} {'Cumul (ms)':>12}")
        lines.append("-" * 80)
        
        for func in result.aggregated_functions[:limit]:
            name = func.name[:43] if len(func.name) > 43 else func.name
            lines.append(f"{name:<45} {func.calls:>8} {func.total_time_ms:>12.2f} {func.cumulative_time_ms:>12.2f}")
        
        lines.append("-" * 80)
        
        # Top functions by self time
        by_self = sorted(result.aggregated_functions, key=lambda x: x.total_time_ms, reverse=True)[:10]
        lines.append("\n## Top Functions by Self Time")
        lines.append("-" * 80)
        lines.append(f"{'Function':<45} {'Calls':>8} {'Self (ms)':>12} {'Cumul (ms)':>12}")
        lines.append("-" * 80)
        
        for func in by_self:
            name = func.name[:43] if len(func.name) > 43 else func.name
            lines.append(f"{name:<45} {func.calls:>8} {func.total_time_ms:>12.2f} {func.cumulative_time_ms:>12.2f}")
        
        lines.append("-" * 80)
        
        # Module breakdown
        if result.aggregated_module_breakdown:
            mb = result.aggregated_module_breakdown
            lines.append("\n## Module Breakdown (by cumulative time)")
            lines.append("-" * 60)
            
            if mb.praisonai_modules:
                lines.append("\nPraisonAI CLI Modules:")
                for file, cumul in mb.praisonai_modules[:5]:
                    short_file = "..." + file[-50:] if len(file) > 50 else file
                    lines.append(f"  {short_file:<55} {cumul:>10.2f}ms")
            
            if mb.agent_modules:
                lines.append("\nPraisonAI Agent Modules:")
                for file, cumul in mb.agent_modules[:5]:
                    short_file = "..." + file[-50:] if len(file) > 50 else file
                    lines.append(f"  {short_file:<55} {cumul:>10.2f}ms")
            
            if mb.network_modules:
                lines.append("\nNetwork Modules:")
                for file, cumul in mb.network_modules[:5]:
                    short_file = "..." + file[-50:] if len(file) > 50 else file
                    lines.append(f"  {short_file:<55} {cumul:>10.2f}ms")
            
            if mb.third_party_modules:
                lines.append("\nThird-Party Modules:")
                for file, cumul in mb.third_party_modules[:5]:
                    short_file = "..." + file[-50:] if len(file) > 50 else file
                    lines.append(f"  {short_file:<55} {cumul:>10.2f}ms")
        
        # Call graph summary
        if result.aggregated_call_graph:
            cg = result.aggregated_call_graph
            lines.append(f"\n## Call Graph: {cg.edge_count} edges")
        
        return "\n".join(lines)
    
    def run_full_benchmark(self, prompt: str = None, iterations: int = None, 
                           paths: List[str] = None, verbose: bool = True,
                           deep: bool = False, limit: int = 30) -> BenchmarkReport:
        """
        Run full benchmark suite.
        
        Args:
            prompt: Query to benchmark (default: "Hi")
            iterations: Number of iterations per path (default: 3)
            paths: List of paths to benchmark (default: all)
            verbose: Print progress
            deep: Enable deep cProfile profiling
            limit: Number of top functions to show in deep profile
            
        Returns:
            BenchmarkReport with all results
        """
        prompt = prompt or self.DEFAULT_PROMPT
        iterations = iterations or self.DEFAULT_ITERATIONS
        paths = paths or self.PATHS
        
        from datetime import datetime
        
        report = BenchmarkReport(
            timestamp=datetime.utcnow().isoformat() + "Z",
            prompt=prompt,
            iterations=iterations,
        )
        
        if verbose:
            print("=" * 70)
            print("PraisonAI Comprehensive Benchmark Suite")
            print("=" * 70)
            print(f"Prompt: \"{prompt}\"")
            print(f"Iterations: {iterations}")
            print(f"Paths: {len(paths)}")
            if deep:
                print(f"Deep Profiling: ENABLED (limit={limit})")
            print("=" * 70)
        
        # Benchmark each path - use deep profiling methods when deep=True
        if deep:
            # Deep profiling uses in-process methods for supported paths
            benchmark_methods = {
                "openai_sdk": lambda p, i, c: self.benchmark_openai_sdk_deep(p, i, c, limit=limit),
                "praisonai_agent": lambda p, i, c: self.benchmark_praisonai_agent_deep(p, i, c, limit=limit),
                "praisonai_cli": lambda p, i, c: self.benchmark_praisonai_cli(p, i, c, with_profile=False),
                "praisonai_cli_profile": lambda p, i, c: self.benchmark_praisonai_cli(p, i, c, with_profile=True),
                "praisonai_workflow_single": self.benchmark_praisonai_workflow_single,
                "praisonai_workflow_multi": self.benchmark_praisonai_workflow_multi,
                "praisonai_litellm": self.benchmark_praisonai_litellm,
                "litellm_standalone": self.benchmark_litellm_standalone,
            }
        else:
            benchmark_methods = {
                "openai_sdk": self.benchmark_openai_sdk,
                "praisonai_agent": self.benchmark_praisonai_agent,
                "praisonai_cli": lambda p, i, c: self.benchmark_praisonai_cli(p, i, c, with_profile=False),
                "praisonai_cli_profile": lambda p, i, c: self.benchmark_praisonai_cli(p, i, c, with_profile=True),
                "praisonai_workflow_single": self.benchmark_praisonai_workflow_single,
                "praisonai_workflow_multi": self.benchmark_praisonai_workflow_multi,
                "praisonai_litellm": self.benchmark_praisonai_litellm,
                "litellm_standalone": self.benchmark_litellm_standalone,
            }
        
        for path_name in paths:
            if path_name not in benchmark_methods:
                if verbose:
                    print(f"\n⚠ Unknown path: {path_name}")
                continue
            
            if verbose:
                deep_indicator = " [DEEP]" if deep and path_name in ["openai_sdk", "praisonai_agent"] else ""
                print(f"\n📊 Benchmarking: {path_name}{deep_indicator}")
            
            result = BenchmarkResult(path_name=path_name)
            method = benchmark_methods[path_name]
            
            for i in range(iterations):
                is_cold = (i == 0)
                if verbose:
                    print(f"   Run {i + 1}/{iterations} ({'cold' if is_cold else 'warm'})...", end=" ", flush=True)
                
                try:
                    run = method(prompt, i + 1, is_cold)
                    result.runs.append(run)
                    
                    if verbose:
                        if run.success:
                            print(f"{run.timings.total_ms:.0f}ms")
                        else:
                            print(f"FAILED: {run.error[:50]}")
                except Exception as e:
                    if verbose:
                        print(f"ERROR: {e}")
                    result.runs.append(BenchmarkRun(
                        path_name=path_name,
                        iteration=i + 1,
                        is_cold=is_cold,
                        timings=PhaseTimings(),
                        success=False,
                        error=str(e)
                    ))
            
            report.results[path_name] = result
        
        # Compute stats
        sdk_baseline = 0.0
        if "openai_sdk" in report.results:
            report.results["openai_sdk"].compute_stats(0.0)
            sdk_baseline = report.results["openai_sdk"].mean_total_ms
            report.sdk_baseline_ms = sdk_baseline
        
        for name, result in report.results.items():
            result.compute_stats(sdk_baseline)
        
        return report
    
    def print_report(self, report: BenchmarkReport, deep: bool = False, limit: int = 30):
        """Print full benchmark report."""
        print("\n" + "=" * 70)
        print("BENCHMARK RESULTS")
        print("=" * 70)
        
        # Timeline diagrams for each path
        print("\n## Timeline Diagrams")
        print("-" * 70)
        
        for name, result in sorted(report.results.items(), key=lambda x: x[1].mean_total_ms):
            print(f"\n### {name}")
            print(self.create_timeline_diagram(result))
        
        # Comparison table
        print("\n" + "=" * 70)
        print("## Master Comparison Table")
        print(self.create_comparison_table(report))
        
        # Variance analysis
        print(self.create_variance_table(report))
        
        # Overhead classification
        print(self.classify_overhead(report))
        
        # Deep profile output (if enabled and data available)
        if deep:
            for name, result in sorted(report.results.items(), key=lambda x: x[1].mean_total_ms):
                if result.aggregated_functions:
                    print(f"\n{'=' * 70}")
                    print(f"DEEP PROFILE: {name}")
                    print("=" * 70)
                    print(self.create_deep_profile_output(result, limit=limit))
        
        print("\n" + "=" * 70)
    
    def handle(self, subcommand: str = "profile", prompt: str = None, 
               iterations: int = None, output_format: str = "text", 
               output_file: str = None, **kwargs) -> Any:
        """
        Handle benchmark subcommands.
        
        Args:
            subcommand: One of profile, sdk, agent, cli, compare
            prompt: Query to benchmark
            iterations: Number of iterations
            output_format: text or json
            output_file: Path to save results
            
        Returns:
            BenchmarkReport
        """
        prompt = prompt or self.DEFAULT_PROMPT
        iterations = iterations or self.DEFAULT_ITERATIONS
        
        if subcommand == "profile":
            # Full benchmark
            report = self.run_full_benchmark(prompt, iterations)
            
            if output_format == "json":
                output = json.dumps(report.to_dict(), indent=2)
                if output_file:
                    with open(output_file, "w") as f:
                        f.write(output)
                    print(f"Results saved to {output_file}")
                else:
                    print(output)
            else:
                self.print_report(report)
                if output_file:
                    with open(output_file, "w") as f:
                        f.write(json.dumps(report.to_dict(), indent=2))
                    print(f"\nJSON results saved to {output_file}")
            
            return report
        
        elif subcommand == "sdk":
            # SDK only
            report = self.run_full_benchmark(prompt, iterations, paths=["openai_sdk"])
            self.print_report(report)
            return report
        
        elif subcommand == "agent":
            # Agent only
            report = self.run_full_benchmark(prompt, iterations, paths=["openai_sdk", "praisonai_agent"])
            self.print_report(report)
            return report
        
        elif subcommand == "cli":
            # CLI only
            report = self.run_full_benchmark(prompt, iterations, paths=["openai_sdk", "praisonai_cli", "praisonai_cli_profile"])
            self.print_report(report)
            return report
        
        elif subcommand == "compare":
            # Quick comparison (fewer iterations)
            report = self.run_full_benchmark(prompt, iterations=2, 
                                            paths=["openai_sdk", "praisonai_agent", "praisonai_cli", "litellm_standalone"])
            print("\n" + self.create_comparison_table(report))
            return report
        
        else:
            print(f"Unknown subcommand: {subcommand}")
            print("Available: profile, sdk, agent, cli, compare")
            return None


def run_benchmark_command(args) -> int:
    """
    Run benchmark command from CLI args.
    
    Args:
        args: Parsed CLI arguments
        
    Returns:
        Exit code (0 for success)
    """
    handler = BenchmarkHandler()
    
    subcommand = getattr(args, 'benchmark_command', 'profile')
    prompt = getattr(args, 'benchmark_prompt', None)
    iterations = getattr(args, 'benchmark_iterations', None)
    output_format = getattr(args, 'benchmark_format', 'text')
    output_file = getattr(args, 'benchmark_output', None)
    
    result = handler.handle(
        subcommand=subcommand,
        prompt=prompt,
        iterations=iterations,
        output_format=output_format,
        output_file=output_file
    )
    
    return 0 if result else 1
