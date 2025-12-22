"""
PraisonAI CLI Profiling Commands

Provides CLI commands for profiling agent execution.

Usage:
    praisonai profile run "task" --output report.html
    praisonai profile report --format json
    praisonai profile benchmark --iterations 10
"""

import time
import json
from typing import Optional, Dict, Any


class ProfilingHandler:
    """
    Handler for CLI profiling commands.
    
    Features:
    - Run tasks with profiling enabled
    - Generate reports (console, JSON, HTML)
    - Benchmark agent performance
    - Export flamegraphs
    """
    
    def __init__(self):
        self._profiler = None
    
    @property
    def profiler(self):
        """Lazy load profiler."""
        if self._profiler is None:
            from praisonai.profiler import Profiler
            self._profiler = Profiler
        return self._profiler
    
    def enable(self) -> None:
        """Enable profiling."""
        self.profiler.enable()
    
    def disable(self) -> None:
        """Disable profiling."""
        self.profiler.disable()
    
    def clear(self) -> None:
        """Clear profiling data."""
        self.profiler.clear()
    
    def run_with_profiling(self, task: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Run a task with profiling enabled.
        
        Args:
            task: Task description or prompt
            config: Optional configuration dict
            
        Returns:
            Dict with result and profiling data
        """
        self.profiler.enable()
        self.profiler.clear()
        
        result = None
        error = None
        
        try:
            # Import and run PraisonAI
            from praisonai import PraisonAI
            
            with self.profiler.block("total_execution"):
                with self.profiler.block("initialization"):
                    praison = PraisonAI(auto=task, **(config or {}))
                
                with self.profiler.block("agent_run"):
                    result = praison.run()
        except Exception as e:
            error = str(e)
        finally:
            self.profiler.disable()
        
        return {
            'result': result,
            'error': error,
            'summary': self.profiler.get_summary(),
            'statistics': self.profiler.get_statistics()
        }
    
    def report(self, format: str = "console", output: Optional[str] = None) -> str:
        """
        Generate profiling report.
        
        Args:
            format: Output format (console, json, html)
            output: Optional file path to save report
            
        Returns:
            Report content as string
        """
        if format == "console":
            content = self.profiler.report(output="console")
        elif format == "json":
            content = self.profiler.export_json()
        elif format == "html":
            content = self.profiler.export_html()
        else:
            raise ValueError(f"Unknown format: {format}")
        
        if output:
            with open(output, 'w') as f:
                f.write(content)
            print(f"Report saved to: {output}")
        
        return content
    
    def benchmark(self, task: str, iterations: int = 5, 
                  warmup: int = 1, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Benchmark agent performance.
        
        Args:
            task: Task to benchmark
            iterations: Number of iterations
            warmup: Number of warmup runs
            config: Optional configuration
            
        Returns:
            Benchmark results with statistics
        """
        from praisonai.profiler import Profiler
        
        times = []
        errors = []
        
        # Warmup runs
        for i in range(warmup):
            print(f"Warmup {i + 1}/{warmup}...")
            try:
                self.run_with_profiling(task, config)
            except Exception as e:
                print(f"Warmup error: {e}")
        
        # Benchmark runs
        for i in range(iterations):
            print(f"Iteration {i + 1}/{iterations}...")
            Profiler.clear()
            
            start = time.perf_counter()
            try:
                self.run_with_profiling(task, config)
                duration_ms = (time.perf_counter() - start) * 1000
                times.append(duration_ms)
            except Exception as e:
                errors.append(str(e))
                duration_ms = (time.perf_counter() - start) * 1000
                times.append(duration_ms)
        
        # Calculate statistics
        if times:
            sorted_times = sorted(times)
            n = len(sorted_times)
            
            results = {
                'iterations': iterations,
                'successful': iterations - len(errors),
                'failed': len(errors),
                'times_ms': times,
                'mean_ms': sum(times) / n,
                'min_ms': min(times),
                'max_ms': max(times),
                'p50_ms': sorted_times[n // 2],
                'p95_ms': sorted_times[int(n * 0.95)] if n > 1 else sorted_times[-1],
                'p99_ms': sorted_times[int(n * 0.99)] if n > 1 else sorted_times[-1],
                'errors': errors
            }
        else:
            results = {
                'iterations': iterations,
                'successful': 0,
                'failed': len(errors),
                'errors': errors
            }
        
        return results
    
    def export_flamegraph(self, filepath: str) -> None:
        """Export flamegraph to SVG file."""
        self.profiler.export_flamegraph(filepath)
        print(f"Flamegraph saved to: {filepath}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get profiling summary."""
        return self.profiler.get_summary()
    
    def get_statistics(self, category: Optional[str] = None) -> Dict[str, float]:
        """Get profiling statistics."""
        return self.profiler.get_statistics(category)
    
    def print_summary(self) -> None:
        """Print profiling summary to console."""
        summary = self.get_summary()
        stats = self.get_statistics()
        
        print("\n" + "=" * 60)
        print("PROFILING SUMMARY")
        print("=" * 60)
        
        print(f"\nTotal Time: {summary['total_time_ms']:.2f}ms")
        print(f"Operations: {summary['timing_count']}")
        print(f"Imports: {summary['import_count']}")
        print(f"Flow Steps: {summary['flow_steps']}")
        
        print("\nStatistics:")
        print(f"  P50 (Median): {stats['p50']:.2f}ms")
        print(f"  P95: {stats['p95']:.2f}ms")
        print(f"  P99: {stats['p99']:.2f}ms")
        print(f"  Mean: {stats['mean']:.2f}ms")
        print(f"  Std Dev: {stats['std_dev']:.2f}ms")
        
        print("\nSlowest Operations:")
        for name, duration in summary['slowest_operations'][:5]:
            print(f"  {name}: {duration:.2f}ms")
        
        print("=" * 60)


def handle_profile_command(args) -> int:
    """
    Handle profile CLI command.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Exit code (0 for success)
    """
    handler = ProfilingHandler()
    
    subcommand = getattr(args, 'profile_command', None)
    
    if subcommand == 'run':
        task = getattr(args, 'task', '')
        output = getattr(args, 'output', None)
        format_type = getattr(args, 'format', 'console')
        
        print(f"Running with profiling: {task[:50]}...")
        result = handler.run_with_profiling(task)
        
        if result['error']:
            print(f"Error: {result['error']}")
        
        handler.report(format=format_type, output=output)
        return 0 if not result['error'] else 1
    
    elif subcommand == 'report':
        output = getattr(args, 'output', None)
        format_type = getattr(args, 'format', 'console')
        
        handler.report(format=format_type, output=output)
        return 0
    
    elif subcommand == 'benchmark':
        task = getattr(args, 'task', '')
        iterations = getattr(args, 'iterations', 5)
        warmup = getattr(args, 'warmup', 1)
        output = getattr(args, 'output', None)
        
        print(f"Benchmarking: {task[:50]}...")
        results = handler.benchmark(task, iterations=iterations, warmup=warmup)
        
        print("\n" + "=" * 60)
        print("BENCHMARK RESULTS")
        print("=" * 60)
        print(f"Iterations: {results['iterations']}")
        print(f"Successful: {results['successful']}")
        print(f"Failed: {results['failed']}")
        
        if 'mean_ms' in results:
            print("\nTiming:")
            print(f"  Mean: {results['mean_ms']:.2f}ms")
            print(f"  Min: {results['min_ms']:.2f}ms")
            print(f"  Max: {results['max_ms']:.2f}ms")
            print(f"  P50: {results['p50_ms']:.2f}ms")
            print(f"  P95: {results['p95_ms']:.2f}ms")
        
        if output:
            with open(output, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {output}")
        
        return 0
    
    elif subcommand == 'flamegraph':
        output = getattr(args, 'output', 'profile.svg')
        handler.export_flamegraph(output)
        return 0
    
    elif subcommand == 'summary':
        handler.print_summary()
        return 0
    
    else:
        print("Usage: praisonai profile <run|report|benchmark|flamegraph|summary>")
        return 1


def add_profile_parser(subparsers) -> None:
    """Add profile subcommand to argument parser."""
    profile_parser = subparsers.add_parser(
        'profile',
        help='Profile agent execution'
    )
    
    profile_subparsers = profile_parser.add_subparsers(dest='profile_command')
    
    # Run with profiling
    run_parser = profile_subparsers.add_parser('run', help='Run task with profiling')
    run_parser.add_argument('task', help='Task to run')
    run_parser.add_argument('--output', '-o', help='Output file path')
    run_parser.add_argument('--format', '-f', choices=['console', 'json', 'html'], 
                           default='console', help='Output format')
    
    # Generate report
    report_parser = profile_subparsers.add_parser('report', help='Generate profiling report')
    report_parser.add_argument('--output', '-o', help='Output file path')
    report_parser.add_argument('--format', '-f', choices=['console', 'json', 'html'],
                              default='console', help='Output format')
    
    # Benchmark
    bench_parser = profile_subparsers.add_parser('benchmark', help='Benchmark agent performance')
    bench_parser.add_argument('task', help='Task to benchmark')
    bench_parser.add_argument('--iterations', '-n', type=int, default=5, help='Number of iterations')
    bench_parser.add_argument('--warmup', '-w', type=int, default=1, help='Warmup runs')
    bench_parser.add_argument('--output', '-o', help='Output file for results')
    
    # Flamegraph
    flame_parser = profile_subparsers.add_parser('flamegraph', help='Export flamegraph')
    flame_parser.add_argument('--output', '-o', default='profile.svg', help='Output SVG file')
    
    # Summary
    profile_subparsers.add_parser('summary', help='Print profiling summary')  # noqa: F841


# Exports
__all__ = [
    'ProfilingHandler',
    'handle_profile_command',
    'add_profile_parser',
]
