"""
Performance Handler for CLI.

Provides performance benchmarking and regression testing.
Usage: praisonai perf [benchmark|check|import-time|memory]
"""

import os
import sys
import subprocess
from typing import Any, Dict, Tuple
from .base import FlagHandler


class PerformanceHandler(FlagHandler):
    """
    Handler for performance benchmarking commands.
    
    Commands:
        praisonai perf benchmark     - Run full performance benchmark
        praisonai perf import-time   - Measure import time only
        praisonai perf memory        - Measure memory usage only
        praisonai perf check         - Run regression check against targets
        praisonai perf lazy-check    - Verify lazy imports are working
    """
    
    # Performance targets
    IMPORT_TIME_TARGET_MS = 200
    IMPORT_TIME_HARD_FAIL_MS = 300
    MEMORY_TARGET_MB = 30
    MEMORY_HARD_FAIL_MB = 45
    
    @property
    def feature_name(self) -> str:
        return "performance"
    
    @property
    def flag_name(self) -> str:
        return "perf"
    
    @property
    def flag_help(self) -> str:
        return "Run performance benchmarks and regression checks"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if performance testing is available."""
        return True, ""
    
    def measure_import_time(self, runs: int = 5) -> Dict[str, Any]:
        """
        Measure import time for praisonaiagents.
        
        Args:
            runs: Number of runs to average
            
        Returns:
            Dict with timing statistics
        """
        times = []
        
        for _ in range(runs):
            code = """
import time
start = time.perf_counter()
import praisonaiagents
end = time.perf_counter()
print(f"{(end - start) * 1000:.1f}")
"""
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            )
            if result.returncode == 0:
                try:
                    times.append(float(result.stdout.strip()))
                except ValueError:
                    pass
        
        if not times:
            return {"error": "Failed to measure import time"}
        
        times.sort()
        median = times[len(times) // 2]
        
        return {
            "times": times,
            "min": min(times),
            "max": max(times),
            "median": median,
            "mean": sum(times) / len(times),
            "pass": median < self.IMPORT_TIME_TARGET_MS,
            "hard_fail": median > self.IMPORT_TIME_HARD_FAIL_MS
        }
    
    def measure_memory(self) -> Dict[str, Any]:
        """
        Measure memory usage after importing praisonaiagents.
        
        Returns:
            Dict with memory statistics
        """
        code = """
import tracemalloc
tracemalloc.start()
import praisonaiagents
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
print(f"{current / 1024 / 1024:.1f},{peak / 1024 / 1024:.1f}")
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        )
        
        if result.returncode != 0:
            return {"error": f"Failed to measure memory: {result.stderr}"}
        
        try:
            current, peak = result.stdout.strip().split(",")
            current_mb = float(current)
            peak_mb = float(peak)
            
            return {
                "current_mb": current_mb,
                "peak_mb": peak_mb,
                "pass": current_mb < self.MEMORY_TARGET_MB,
                "hard_fail": current_mb > self.MEMORY_HARD_FAIL_MB
            }
        except (ValueError, IndexError) as e:
            return {"error": f"Failed to parse memory output: {e}"}
    
    def check_lazy_imports(self) -> Dict[str, bool]:
        """
        Check that heavy dependencies are not loaded at import time.
        
        Returns:
            Dict mapping module name to whether it's lazy (True = good)
        """
        heavy_modules = ["litellm", "chromadb", "mem0", "requests"]
        results = {}
        
        for module in heavy_modules:
            code = f"""
import sys
# Clear any cached imports
for key in list(sys.modules.keys()):
    if key.startswith('{module}'):
        del sys.modules[key]

import praisonaiagents
print('{module}' not in sys.modules)
"""
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            )
            
            if result.returncode == 0:
                results[module] = result.stdout.strip() == "True"
            else:
                results[module] = False
        
        return results
    
    def run_benchmark(self, verbose: bool = True) -> Dict[str, Any]:
        """
        Run full performance benchmark.
        
        Args:
            verbose: Print results to console
            
        Returns:
            Dict with all benchmark results
        """
        results = {}
        
        if verbose:
            print("=" * 60)
            print("PraisonAI Agents Performance Benchmark")
            print("=" * 60)
        
        # Import time
        if verbose:
            print("\n[1/3] Measuring import time...")
        results["import_time"] = self.measure_import_time()
        
        if verbose and "error" not in results["import_time"]:
            median = results["import_time"]["median"]
            status = "PASS" if results["import_time"]["pass"] else "FAIL"
            print(f"      Median: {median:.1f}ms [{status}]")
        
        # Memory
        if verbose:
            print("\n[2/3] Measuring memory usage...")
        results["memory"] = self.measure_memory()
        
        if verbose and "error" not in results["memory"]:
            current = results["memory"]["current_mb"]
            status = "PASS" if results["memory"]["pass"] else "WARN" if not results["memory"]["hard_fail"] else "FAIL"
            print(f"      Current: {current:.1f}MB [{status}]")
        
        # Lazy imports
        if verbose:
            print("\n[3/3] Checking lazy imports...")
        results["lazy_imports"] = self.check_lazy_imports()
        
        if verbose:
            all_lazy = all(results["lazy_imports"].values())
            status = "PASS" if all_lazy else "FAIL"
            print(f"      All lazy: {all_lazy} [{status}]")
            for module, is_lazy in results["lazy_imports"].items():
                symbol = "✓" if is_lazy else "✗"
                print(f"        {symbol} {module}")
        
        # Overall
        overall_pass = (
            results["import_time"].get("pass", False) and
            not results["memory"].get("hard_fail", True) and
            all(results["lazy_imports"].values())
        )
        results["overall_pass"] = overall_pass
        
        if verbose:
            print("\n" + "=" * 60)
            status = "PASS" if overall_pass else "FAIL"
            print(f"Overall: [{status}]")
            print("=" * 60)
        
        return results
    
    def run_check(self) -> bool:
        """
        Run regression check against targets.
        
        Returns:
            True if all checks pass
        """
        results = self.run_benchmark(verbose=True)
        return results.get("overall_pass", False)
    
    def handle(self, subcommand: str = "benchmark", **kwargs) -> Any:
        """
        Handle performance subcommands.
        
        Args:
            subcommand: One of benchmark, import-time, memory, check, lazy-check
            **kwargs: Additional options
            
        Returns:
            Results dict or bool
        """
        if subcommand == "benchmark":
            return self.run_benchmark(verbose=True)
        elif subcommand == "import-time":
            result = self.measure_import_time()
            if "error" not in result:
                print(f"Import time: {result['median']:.1f}ms (median)")
                print(f"Target: <{self.IMPORT_TIME_TARGET_MS}ms")
                print(f"Status: {'PASS' if result['pass'] else 'FAIL'}")
            return result
        elif subcommand == "memory":
            result = self.measure_memory()
            if "error" not in result:
                print(f"Memory: {result['current_mb']:.1f}MB")
                print(f"Target: <{self.MEMORY_TARGET_MB}MB")
                print(f"Status: {'PASS' if result['pass'] else 'WARN' if not result['hard_fail'] else 'FAIL'}")
            return result
        elif subcommand == "check":
            return self.run_check()
        elif subcommand == "lazy-check":
            results = self.check_lazy_imports()
            print("Lazy Import Check:")
            for module, is_lazy in results.items():
                status = "LAZY (good)" if is_lazy else "EAGER (bad)"
                print(f"  {module}: {status}")
            return all(results.values())
        else:
            print(f"Unknown subcommand: {subcommand}")
            print("Available: benchmark, import-time, memory, check, lazy-check")
            return False


# Convenience function for CLI integration
def run_performance_command(args) -> int:
    """
    Run performance command from CLI args.
    
    Args:
        args: Parsed CLI arguments
        
    Returns:
        Exit code (0 for success)
    """
    handler = PerformanceHandler()
    subcommand = getattr(args, 'perf_command', 'benchmark')
    result = handler.handle(subcommand)
    
    if isinstance(result, bool):
        return 0 if result else 1
    elif isinstance(result, dict):
        return 0 if result.get("overall_pass", result.get("pass", False)) else 1
    return 0
