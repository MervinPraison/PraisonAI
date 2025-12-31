"""
Profile Suite Runner for PraisonAI CLI.

Runs a matrix of profiling scenarios and produces aggregated reports.
Supports cold/warm start, streaming/non-streaming, and multiple iterations.
"""

import json
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .core import ProfilerConfig, ProfilerResult, QueryProfiler


@dataclass
class ScenarioConfig:
    """Configuration for a single profiling scenario."""
    name: str
    prompt: str
    model: Optional[str] = None
    stream: bool = False
    iterations: int = 3
    warmup: int = 1
    show_files: bool = True
    limit: int = 20


@dataclass
class ScenarioResult:
    """Result from running a scenario."""
    name: str
    config: ScenarioConfig
    results: List[ProfilerResult] = field(default_factory=list)
    
    @property
    def import_times(self) -> List[float]:
        return [r.timing.imports_ms for r in self.results]
    
    @property
    def total_times(self) -> List[float]:
        return [r.timing.total_run_ms for r in self.results]
    
    @property
    def first_token_times(self) -> List[float]:
        return [r.timing.first_token_ms for r in self.results if r.timing.first_token_ms > 0]
    
    def get_stats(self, values: List[float]) -> Dict[str, float]:
        if not values:
            return {"mean": 0, "min": 0, "max": 0, "stdev": 0, "median": 0}
        return {
            "mean": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
            "median": statistics.median(values),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "config": {
                "prompt": self.config.prompt[:50] + "..." if len(self.config.prompt) > 50 else self.config.prompt,
                "model": self.config.model or "default",
                "stream": self.config.stream,
                "iterations": self.config.iterations,
            },
            "import_time_stats": self.get_stats(self.import_times),
            "total_time_stats": self.get_stats(self.total_times),
            "first_token_stats": self.get_stats(self.first_token_times) if self.first_token_times else None,
            "raw_import_times_ms": self.import_times,
            "raw_total_times_ms": self.total_times,
        }


@dataclass
class SuiteResult:
    """Result from running a full profiling suite."""
    scenarios: List[ScenarioResult] = field(default_factory=list)
    startup_cold_ms: float = 0.0
    startup_warm_ms: float = 0.0
    import_analysis: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "startup": {
                "cold_ms": self.startup_cold_ms,
                "warm_ms": self.startup_warm_ms,
            },
            "import_analysis": self.import_analysis[:20],
            "scenarios": [s.to_dict() for s in self.scenarios],
        }


class ProfileSuiteRunner:
    """
    Runs a suite of profiling scenarios.
    
    Collects comprehensive timing data across multiple runs and scenarios.
    """
    
    DEFAULT_SCENARIOS = [
        ScenarioConfig(name="simple_non_stream", prompt="hi", stream=False, iterations=3),
        ScenarioConfig(name="simple_stream", prompt="hi", stream=True, iterations=3),
        ScenarioConfig(name="medium_non_stream", prompt="Explain what Python is in 2 sentences", stream=False, iterations=2),
        ScenarioConfig(name="medium_stream", prompt="Explain what Python is in 2 sentences", stream=True, iterations=2),
    ]
    
    def __init__(
        self,
        scenarios: Optional[List[ScenarioConfig]] = None,
        output_dir: Optional[str] = None,
        verbose: bool = False,
    ):
        self.scenarios = scenarios or self.DEFAULT_SCENARIOS
        self.output_dir = Path(output_dir) if output_dir else Path("/tmp/praisonai_profile_suite")
        self.verbose = verbose
    
    def run(self) -> SuiteResult:
        """Run the full profiling suite."""
        result = SuiteResult()
        result.metadata = self._collect_metadata()
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if self.verbose:
            print("🔬 Starting Profile Suite...")
            print(f"   Output: {self.output_dir}")
        
        # 1. Measure startup times
        if self.verbose:
            print("\n📊 Measuring startup times...")
        result.startup_cold_ms, result.startup_warm_ms = self._measure_startup()
        if self.verbose:
            print(f"   Cold: {result.startup_cold_ms:.2f}ms, Warm: {result.startup_warm_ms:.2f}ms")
        
        # 2. Analyze imports
        if self.verbose:
            print("\n📊 Analyzing imports...")
        result.import_analysis = self._analyze_imports()
        if self.verbose and result.import_analysis:
            print(f"   Top import: {result.import_analysis[0]['module']} ({result.import_analysis[0]['cumulative_ms']:.2f}ms)")
        
        # 3. Run scenarios
        for scenario in self.scenarios:
            if self.verbose:
                print(f"\n📊 Running scenario: {scenario.name}")
            scenario_result = self._run_scenario(scenario)
            result.scenarios.append(scenario_result)
            
            if self.verbose:
                stats = scenario_result.get_stats(scenario_result.total_times)
                print(f"   Total time: {stats['mean']:.2f}ms (±{stats['stdev']:.2f}ms)")
        
        # 4. Save results
        self._save_results(result)
        
        if self.verbose:
            print(f"\n✅ Suite complete. Results saved to {self.output_dir}")
        
        return result
    
    def _collect_metadata(self) -> Dict[str, Any]:
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
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    
    def _measure_startup(self) -> tuple:
        """Measure cold and warm startup times."""
        # Cold start
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", "import praisonai; import praisonai.cli"],
            capture_output=True,
            text=True,
        )
        cold_ms = (time.perf_counter() - start) * 1000
        
        # Warm start
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-c", "import praisonai; import praisonai.cli"],
            capture_output=True,
            text=True,
        )
        warm_ms = (time.perf_counter() - start) * 1000
        
        return cold_ms, warm_ms
    
    def _analyze_imports(self) -> List[Dict[str, Any]]:
        """Analyze import times."""
        import re
        
        try:
            result = subprocess.run(
                [sys.executable, "-X", "importtime", "-c", "import praisonaiagents"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            import_times = []
            for line in result.stderr.split('\n'):
                if 'import time:' in line:
                    match = re.search(r'import time:\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(.+)', line)
                    if match:
                        self_time = int(match.group(1))
                        cumulative = int(match.group(2))
                        module = match.group(3).strip()
                        import_times.append({
                            "module": module,
                            "self_us": self_time,
                            "cumulative_us": cumulative,
                            "self_ms": self_time / 1000,
                            "cumulative_ms": cumulative / 1000,
                        })
            
            import_times.sort(key=lambda x: x["cumulative_us"], reverse=True)
            return import_times[:30]
            
        except Exception:
            return []
    
    def _run_scenario(self, scenario: ScenarioConfig) -> ScenarioResult:
        """Run a single scenario with multiple iterations."""
        result = ScenarioResult(name=scenario.name, config=scenario)
        
        config = ProfilerConfig(
            stream=scenario.stream,
            show_files=scenario.show_files,
            limit=scenario.limit,
            first_token=scenario.stream,
        )
        
        # Warmup runs (discarded)
        for _ in range(scenario.warmup):
            try:
                profiler = QueryProfiler(config)
                profiler.profile_query(scenario.prompt, model=scenario.model, stream=scenario.stream)
            except Exception:
                pass
        
        # Actual runs
        for i in range(scenario.iterations):
            try:
                profiler = QueryProfiler(config)
                profile_result = profiler.profile_query(
                    scenario.prompt,
                    model=scenario.model,
                    stream=scenario.stream,
                )
                result.results.append(profile_result)
                
                if self.verbose:
                    print(f"   Iteration {i+1}: {profile_result.timing.total_run_ms:.2f}ms")
                    
            except Exception as e:
                if self.verbose:
                    print(f"   Iteration {i+1}: ERROR - {e}")
        
        return result
    
    def _save_results(self, result: SuiteResult):
        """Save results to files."""
        # Save JSON summary
        json_path = self.output_dir / "suite_results.json"
        with open(json_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2, default=str)
        
        # Save human-readable report
        report_path = self.output_dir / "suite_report.txt"
        with open(report_path, 'w') as f:
            f.write(self._format_report(result))
    
    def _format_report(self, result: SuiteResult) -> str:
        """Format a human-readable report."""
        lines = []
        lines.append("=" * 70)
        lines.append("PraisonAI Profile Suite Report")
        lines.append("=" * 70)
        lines.append("")
        
        # Metadata
        lines.append("## System Information")
        lines.append(f"  Timestamp:        {result.timestamp}")
        lines.append(f"  Python Version:   {result.metadata.get('python_version', 'N/A')}")
        lines.append(f"  Platform:         {result.metadata.get('platform', 'N/A')}")
        lines.append(f"  PraisonAI:        {result.metadata.get('praisonai_version', 'N/A')}")
        lines.append("")
        
        # Startup times
        lines.append("## Startup Times")
        lines.append(f"  Cold Start:       {result.startup_cold_ms:>10.2f} ms")
        lines.append(f"  Warm Start:       {result.startup_warm_ms:>10.2f} ms")
        lines.append("")
        
        # Import analysis
        if result.import_analysis:
            lines.append("## Top Import Times")
            lines.append("-" * 70)
            lines.append(f"{'Module':<45} {'Self (ms)':>10} {'Cumul (ms)':>12}")
            lines.append("-" * 70)
            for imp in result.import_analysis[:15]:
                module = imp["module"]
                if len(module) > 43:
                    module = "..." + module[-40:]
                lines.append(f"{module:<45} {imp['self_ms']:>10.2f} {imp['cumulative_ms']:>12.2f}")
            lines.append("")
        
        # Scenario results
        lines.append("## Scenario Results")
        lines.append("-" * 70)
        lines.append(f"{'Scenario':<25} {'Stream':>8} {'Iters':>6} {'Mean (ms)':>12} {'StdDev':>10}")
        lines.append("-" * 70)
        
        for scenario in result.scenarios:
            stats = scenario.get_stats(scenario.total_times)
            stream_str = "Yes" if scenario.config.stream else "No"
            lines.append(
                f"{scenario.name:<25} {stream_str:>8} {len(scenario.results):>6} "
                f"{stats['mean']:>12.2f} {stats['stdev']:>10.2f}"
            )
        lines.append("")
        
        # Summary statistics
        all_import_times = []
        all_total_times = []
        for scenario in result.scenarios:
            all_import_times.extend(scenario.import_times)
            all_total_times.extend(scenario.total_times)
        
        if all_import_times:
            lines.append("## Overall Statistics")
            lines.append(f"  Import Time (mean):   {statistics.mean(all_import_times):>10.2f} ms")
            lines.append(f"  Total Time (mean):    {statistics.mean(all_total_times):>10.2f} ms")
            if len(all_total_times) > 1:
                lines.append(f"  Total Time (stdev):   {statistics.stdev(all_total_times):>10.2f} ms")
            lines.append("")
        
        lines.append("=" * 70)
        
        return "\n".join(lines)


def run_profile_suite(
    output_dir: Optional[str] = None,
    scenarios: Optional[List[ScenarioConfig]] = None,
    verbose: bool = True,
) -> SuiteResult:
    """
    Run a profile suite and return results.
    
    Args:
        output_dir: Directory to save results
        scenarios: Custom scenarios to run
        verbose: Print progress
        
    Returns:
        SuiteResult with all profiling data
    """
    runner = ProfileSuiteRunner(
        scenarios=scenarios,
        output_dir=output_dir,
        verbose=verbose,
    )
    return runner.run()
