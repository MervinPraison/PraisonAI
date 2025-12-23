"""
Profile Handler for CLI.

Provides performance profiling and benchmarking capabilities.
Usage: praisonai profile <subcommand> [options]
"""

import argparse
import time
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProfileResult:
    """Result from a profiling run."""
    prompt: str
    response: str
    execution_time_ms: float
    model: str
    tokens: Optional[Dict[str, int]] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "response": self.response[:200] + "..." if len(self.response) > 200 else self.response,
            "execution_time_ms": self.execution_time_ms,
            "model": self.model,
            "tokens": self.tokens,
            "timestamp": self.timestamp
        }


def run_benchmark(prompt: str, model: str = None, iterations: int = 1, verbose: bool = False) -> List[ProfileResult]:
    """
    Run a benchmark on a prompt.
    
    Args:
        prompt: The prompt to benchmark
        model: Optional model to use
        iterations: Number of iterations to run
        verbose: Enable verbose output
        
    Returns:
        List of ProfileResult objects
    """
    try:
        from praisonaiagents import Agent
    except ImportError:
        print("[red]ERROR: praisonaiagents not installed. Install with: pip install praisonaiagents[/red]")
        return []
    
    results = []
    
    agent_config = {
        "name": "BenchmarkAgent",
        "role": "Benchmark Assistant",
        "goal": "Complete tasks efficiently",
        "verbose": verbose
    }
    
    if model:
        agent_config["llm"] = model
    
    agent = Agent(**agent_config)
    
    for i in range(iterations):
        if verbose:
            print(f"[dim]Running iteration {i + 1}/{iterations}...[/dim]")
        
        start_time = time.time()
        response = agent.start(prompt)
        end_time = time.time()
        
        execution_time_ms = (end_time - start_time) * 1000
        
        result = ProfileResult(
            prompt=prompt,
            response=str(response),
            execution_time_ms=execution_time_ms,
            model=model or "default"
        )
        results.append(result)
    
    return results


def display_benchmark_results(results: List[ProfileResult], output_format: str = "table"):
    """Display benchmark results."""
    if not results:
        print("[yellow]No results to display[/yellow]")
        return
    
    try:
        from rich.console import Console
        from rich.table import Table
        console = Console()
    except ImportError:
        # Fallback to simple output
        for r in results:
            print(f"Time: {r.execution_time_ms:.1f}ms | Model: {r.model}")
        return
    
    if output_format == "json":
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return
    
    # Calculate statistics
    times = [r.execution_time_ms for r in results]
    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)
    
    table = Table(title="📊 Benchmark Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Iterations", str(len(results)))
    table.add_row("Average Time", f"{avg_time:.1f}ms")
    table.add_row("Min Time", f"{min_time:.1f}ms")
    table.add_row("Max Time", f"{max_time:.1f}ms")
    table.add_row("Model", results[0].model)
    
    console.print(table)
    
    # Show response preview
    if results:
        console.print("\n[bold]Response Preview:[/bold]")
        preview = results[0].response[:300] + "..." if len(results[0].response) > 300 else results[0].response
        console.print(f"[dim]{preview}[/dim]")


def handle_profile_command(args: List[str]) -> int:
    """
    Handle the profile command.
    
    Args:
        args: Command line arguments
        
    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(prog="praisonai profile", description="Performance profiling and benchmarking")
    subparsers = parser.add_subparsers(dest='subcommand', help='Profile subcommands')
    
    # Benchmark subcommand
    bench_parser = subparsers.add_parser('benchmark', aliases=['bench', 'run'], help='Run a benchmark')
    bench_parser.add_argument('prompt', nargs='?', help='Prompt to benchmark')
    bench_parser.add_argument('--model', '-m', type=str, help='Model to use')
    bench_parser.add_argument('--iterations', '-n', type=int, default=1, help='Number of iterations')
    bench_parser.add_argument('--output', '-o', type=str, help='Output file path')
    bench_parser.add_argument('--format', '-f', type=str, choices=['table', 'json', 'html'], default='table', help='Output format')
    bench_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    # Compare subcommand
    compare_parser = subparsers.add_parser('compare', help='Compare models')
    compare_parser.add_argument('prompt', nargs='?', help='Prompt to compare')
    compare_parser.add_argument('--models', type=str, help='Comma-separated list of models to compare')
    
    # Report subcommand
    report_parser = subparsers.add_parser('report', help='Generate a profiling report')
    report_parser.add_argument('--input', '-i', type=str, help='Input JSON file with results')
    report_parser.add_argument('--output', '-o', type=str, help='Output file path')
    report_parser.add_argument('--format', '-f', type=str, choices=['html', 'json', 'markdown'], default='html', help='Report format')
    
    try:
        parsed_args = parser.parse_args(args)
    except SystemExit:
        return 1
    
    if not parsed_args.subcommand:
        parser.print_help()
        print("\n[bold]Examples:[/bold]")
        print("  praisonai profile benchmark \"What is 2+2?\"")
        print("  praisonai profile benchmark \"Write a poem\" --model gpt-4o --iterations 3")
        print("  praisonai profile compare \"Explain AI\" --models gpt-4o,gpt-4o-mini")
        return 0
    
    if parsed_args.subcommand in ['benchmark', 'bench', 'run']:
        if not parsed_args.prompt:
            print("[red]ERROR: Please provide a prompt to benchmark[/red]")
            print("Usage: praisonai profile benchmark \"Your prompt here\"")
            return 1
        
        print(f"[bold cyan]🔬 Running benchmark...[/bold cyan]")
        results = run_benchmark(
            parsed_args.prompt,
            model=parsed_args.model,
            iterations=parsed_args.iterations,
            verbose=parsed_args.verbose
        )
        
        display_benchmark_results(results, parsed_args.format)
        
        if parsed_args.output:
            with open(parsed_args.output, 'w') as f:
                json.dump([r.to_dict() for r in results], f, indent=2)
            print(f"[green]Results saved to {parsed_args.output}[/green]")
        
        return 0
    
    elif parsed_args.subcommand == 'compare':
        if not parsed_args.prompt:
            print("[red]ERROR: Please provide a prompt to compare[/red]")
            return 1
        
        models = parsed_args.models.split(',') if parsed_args.models else ['gpt-4o-mini', 'gpt-4o']
        print(f"[bold cyan]🔬 Comparing models: {', '.join(models)}[/bold cyan]")
        
        all_results = []
        for model in models:
            print(f"[dim]Testing {model}...[/dim]")
            results = run_benchmark(parsed_args.prompt, model=model, iterations=1)
            all_results.extend(results)
        
        display_benchmark_results(all_results)
        return 0
    
    elif parsed_args.subcommand == 'report':
        print("[yellow]Report generation not yet implemented[/yellow]")
        return 0
    
    return 0
