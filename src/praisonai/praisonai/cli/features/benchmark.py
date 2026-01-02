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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
from pathlib import Path

from .base import FlagHandler


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
        return {
            "timestamp": self.timestamp,
            "prompt": self.prompt,
            "iterations": self.iterations,
            "sdk_baseline_ms": self.sdk_baseline_ms,
            "results": {
                name: {
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
                        }
                        for run in r.runs
                    ]
                }
                for name, r in self.results.items()
            }
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

agent = Agent(instructions="You are helpful", llm="{self.DEFAULT_MODEL}", verbose=False)
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
from praisonaiagents import Agent, Task, PraisonAIAgents
t_import = time.perf_counter()

agent = Agent(name="Helper", instructions="You are helpful", llm="{self.DEFAULT_MODEL}", verbose=False)
task = Task(name="respond", description="{prompt}", expected_output="response", agent=agent)
agents = PraisonAIAgents(agents=[agent], tasks=[task], verbose=0)
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
from praisonaiagents import Agent, Task, PraisonAIAgents
t_import = time.perf_counter()

agent1 = Agent(name="Analyzer", instructions="Analyze the request", llm="{self.DEFAULT_MODEL}", verbose=False)
agent2 = Agent(name="Responder", instructions="Provide a response", llm="{self.DEFAULT_MODEL}", verbose=False)
task1 = Task(name="analyze", description="Analyze: {prompt}", expected_output="analysis", agent=agent1)
task2 = Task(name="respond", description="Respond based on analysis", expected_output="response", agent=agent2)
agents = PraisonAIAgents(agents=[agent1, agent2], tasks=[task1, task2], verbose=0)
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

agent = Agent(instructions="You are helpful", llm="openai/{self.DEFAULT_MODEL}", verbose=False)
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
    
    def run_full_benchmark(self, prompt: str = None, iterations: int = None, 
                           paths: List[str] = None, verbose: bool = True) -> BenchmarkReport:
        """
        Run full benchmark suite.
        
        Args:
            prompt: Query to benchmark (default: "Hi")
            iterations: Number of iterations per path (default: 3)
            paths: List of paths to benchmark (default: all)
            verbose: Print progress
            
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
            print("=" * 70)
        
        # Benchmark each path
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
                print(f"\n📊 Benchmarking: {path_name}")
            
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
    
    def print_report(self, report: BenchmarkReport):
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
