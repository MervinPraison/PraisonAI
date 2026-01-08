"""
Profile command group for PraisonAI CLI.

Provides detailed cProfile-based profiling for query execution.
"""

import sys
from typing import Optional

import typer

app = typer.Typer(help="Performance profiling and diagnostics")


@app.command("query")
def profile_query(
    prompt: str = typer.Argument(..., help="Prompt to profile"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    stream: bool = typer.Option(False, "--stream/--no-stream", help="Use streaming mode"),
    deep: bool = typer.Option(False, "--deep", help="Enable deep call tracing (higher overhead)"),
    limit: int = typer.Option(30, "--limit", "-n", help="Top N functions to show"),
    sort: str = typer.Option("cumulative", "--sort", "-s", help="Sort by: cumulative or tottime"),
    show_callers: bool = typer.Option(False, "--show-callers", help="Show caller functions"),
    show_callees: bool = typer.Option(False, "--show-callees", help="Show callee functions"),
    save: Optional[str] = typer.Option(None, "--save", help="Save artifacts to path (creates .prof, .txt, .json)"),
    output_format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """
    Profile a query execution with detailed timing breakdown.
    
    Uses the unified profiling architecture for consistent results across
    CLI direct invocation (--profile) and this command.
    
    Shows per-function timing, call graphs, and latency metrics.
    
    Examples:
        praisonai profile query "What is 2+2?"
        praisonai profile query "Hello" --limit 20
        praisonai profile query "Test" --deep --show-callers --show-callees
        praisonai profile query "Test" --save ./profile_results
    """
    # Use unified profiler for consistent results
    try:
        from ..execution import ExecutionRequest, Profiler, ProfilerConfig as UnifiedProfilerConfig
    except ImportError as e:
        typer.echo(f"Error: Unified profiler not available: {e}", err=True)
        raise typer.Exit(1)
    
    # Warn about deep tracing overhead
    if deep:
        typer.echo("⚠️  Deep call tracing enabled - this adds significant overhead", err=True)
    
    # Create unified execution request
    request = ExecutionRequest(
        prompt=prompt,
        agent_name="ProfiledAgent",
        model=model,
        stream=stream,
    )
    
    # Create unified profiler config
    config = UnifiedProfilerConfig(
        layer=2 if deep else 1,
        limit=limit,
        sort_by=sort,
        show_callers=show_callers,
        show_callees=show_callees,
        output_format=output_format,
        save_path=save,
    )
    
    # Run profiler
    typer.echo("🔬 Starting profiled execution...", err=True)
    
    try:
        profiler = Profiler(config)
        result, report = profiler.profile_sync(request, invocation_method="profile_command")
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        typer.echo("Install praisonaiagents: pip install praisonaiagents", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error during profiling: {e}", err=True)
        raise typer.Exit(1)
    
    # Output results
    if output_format == "json":
        typer.echo(report.to_json())
    else:
        typer.echo(report.to_text())
    
    # Save artifacts if requested
    if save:
        try:
            import os
            os.makedirs(save, exist_ok=True)
            
            # Save JSON report
            json_path = os.path.join(save, "profile_report.json")
            with open(json_path, 'w') as f:
                f.write(report.to_json())
            
            # Save text report
            txt_path = os.path.join(save, "profile_report.txt")
            with open(txt_path, 'w') as f:
                f.write(report.to_text())
            
            typer.echo("\n✅ Artifacts saved:", err=True)
            typer.echo(f"   {json_path}", err=True)
            typer.echo(f"   {txt_path}", err=True)
        except Exception as e:
            typer.echo(f"Warning: Failed to save artifacts: {e}", err=True)


@app.command("imports")
def profile_imports():
    """
    Profile module import times.
    
    Shows which modules take longest to import, useful for optimizing startup time.
    """
    import subprocess
    import re
    
    typer.echo("🔬 Profiling import times...", err=True)
    
    try:
        result = subprocess.run(
            [sys.executable, "-X", "importtime", "-c", "import praisonaiagents"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        # Parse import times
        import_times = []
        for line in result.stderr.split('\n'):
            if 'import time:' in line:
                match = re.search(r'import time:\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(.+)', line)
                if match:
                    self_time = int(match.group(1))
                    cumulative = int(match.group(2))
                    module = match.group(3).strip()
                    import_times.append((module, self_time, cumulative))
        
        # Sort by cumulative time
        import_times.sort(key=lambda x: x[2], reverse=True)
        
        # Display
        typer.echo("\n" + "=" * 70)
        typer.echo("Import Time Analysis")
        typer.echo("=" * 70)
        typer.echo(f"{'Module':<45} {'Self (μs)':>10} {'Cumul (μs)':>12}")
        typer.echo("-" * 70)
        
        for module, self_time, cumulative in import_times[:30]:
            module_name = module
            if len(module_name) > 43:
                module_name = "..." + module_name[-40:]
            typer.echo(f"{module_name:<45} {self_time:>10} {cumulative:>12}")
        
        typer.echo("-" * 70)
        
        if import_times:
            total_time = max(t[2] for t in import_times)
            typer.echo(f"Total import time: {total_time / 1000:.2f} ms")
        
    except subprocess.TimeoutExpired:
        typer.echo("Error: Import profiling timed out", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("startup")
def profile_startup():
    """
    Profile CLI startup time.
    
    Measures time from CLI invocation to ready state.
    """
    import time
    import subprocess
    
    typer.echo("🔬 Profiling startup time...", err=True)
    
    # Measure cold start (new process)
    start = time.perf_counter()
    subprocess.run(
        [sys.executable, "-c", "import praisonai; import praisonai.cli"],
        capture_output=True,
        text=True,
    )
    cold_start = (time.perf_counter() - start) * 1000
    
    # Measure warm start (imports cached)
    start = time.perf_counter()
    subprocess.run(
        [sys.executable, "-c", "import praisonai; import praisonai.cli"],
        capture_output=True,
        text=True,
    )
    warm_start = (time.perf_counter() - start) * 1000
    
    typer.echo("\n" + "=" * 50)
    typer.echo("Startup Time Analysis")
    typer.echo("=" * 50)
    typer.echo(f"Cold Start:  {cold_start:>10.2f} ms")
    typer.echo(f"Warm Start:  {warm_start:>10.2f} ms")
    typer.echo("=" * 50)
    
    if cold_start > 1000:
        typer.echo("\n⚠️  Cold start > 1s - consider lazy imports", err=True)


@app.command("suite")
def profile_suite(
    output_dir: Optional[str] = typer.Option("/tmp/praisonai_profile_suite", "--output", "-o", help="Output directory for results"),
    iterations: int = typer.Option(3, "--iterations", "-n", help="Iterations per scenario"),
    quick: bool = typer.Option(False, "--quick", help="Quick mode (fewer iterations)"),
):
    """
    Run a comprehensive profiling suite.
    
    Runs multiple scenarios (streaming/non-streaming, simple/complex prompts)
    and produces aggregated statistics and reports.
    
    Examples:
        praisonai profile suite
        praisonai profile suite --output ./my_profile_results
        praisonai profile suite --quick
    """
    try:
        from ..features.profiler import run_profile_suite, ScenarioConfig
    except ImportError as e:
        typer.echo(f"Error: Profiler module not available: {e}", err=True)
        raise typer.Exit(1)
    
    # Define scenarios
    iters = 1 if quick else iterations
    scenarios = [
        ScenarioConfig(name="simple_non_stream", prompt="hi", stream=False, iterations=iters, warmup=0 if quick else 1),
        ScenarioConfig(name="simple_stream", prompt="hi", stream=True, iterations=iters, warmup=0 if quick else 1),
    ]
    
    if not quick:
        scenarios.extend([
            ScenarioConfig(name="medium_non_stream", prompt="Explain Python in 2 sentences", stream=False, iterations=max(1, iters-1)),
            ScenarioConfig(name="medium_stream", prompt="Explain Python in 2 sentences", stream=True, iterations=max(1, iters-1)),
        ])
    
    typer.echo("🔬 Running Profile Suite...", err=True)
    typer.echo(f"   Output: {output_dir}", err=True)
    typer.echo(f"   Scenarios: {len(scenarios)}", err=True)
    typer.echo(f"   Iterations: {iterations}", err=True)
    
    try:
        result = run_profile_suite(
            output_dir=output_dir,
            scenarios=scenarios,
            verbose=True,
        )
        
        # Print summary
        typer.echo("\n" + "=" * 60)
        typer.echo("Profile Suite Summary")
        typer.echo("=" * 60)
        typer.echo(f"Startup Cold: {result.startup_cold_ms:.2f}ms")
        typer.echo(f"Startup Warm: {result.startup_warm_ms:.2f}ms")
        
        if result.import_analysis:
            typer.echo(f"\nTop Import: {result.import_analysis[0]['module']}")
            typer.echo(f"  Time: {result.import_analysis[0]['cumulative_ms']:.2f}ms")
        
        typer.echo("\nScenario Results:")
        for scenario in result.scenarios:
            stats = scenario.get_stats(scenario.total_times)
            typer.echo(f"  {scenario.name}: {stats['mean']:.2f}ms (±{stats['stdev']:.2f}ms)")
        
        typer.echo(f"\n✅ Full results saved to: {output_dir}")
        
    except Exception as e:
        typer.echo(f"Error running suite: {e}", err=True)
        raise typer.Exit(1)


@app.command("snapshot")
def profile_snapshot(
    name: str = typer.Argument("current", help="Name for the snapshot"),
    baseline: bool = typer.Option(False, "--baseline", "-b", help="Save as baseline for comparison"),
    compare: bool = typer.Option(False, "--compare", "-c", help="Compare against baseline"),
    output_format: str = typer.Option("text", "--format", "-f", help="Output format: text or json"),
):
    """
    Create or compare performance snapshots.
    
    Snapshots record timing data for baseline comparison.
    Use --baseline to save a reference point, then --compare to check for regressions.
    
    Examples:
        praisonai profile snapshot --baseline
        praisonai profile snapshot current --compare
        praisonai profile snapshot v2.0 --format json
    """
    try:
        from ..features.profiler import (
            run_profile_suite,
            ScenarioConfig,
            PerfSnapshotManager,
            create_snapshot_from_suite,
            format_comparison_report,
        )
    except ImportError as e:
        typer.echo(f"Error: Profiler module not available: {e}", err=True)
        raise typer.Exit(1)
    
    manager = PerfSnapshotManager()
    
    if compare:
        # Load baseline and compare
        baseline_snap = manager.load_baseline()
        if not baseline_snap:
            typer.echo("❌ No baseline found. Create one with: praisonai profile snapshot --baseline", err=True)
            raise typer.Exit(1)
        
        typer.echo("🔬 Running current profile for comparison...", err=True)
        
        # Run quick suite
        scenarios = [
            ScenarioConfig(name="simple", prompt="hi", stream=False, iterations=2, warmup=1),
        ]
        result = run_profile_suite(
            output_dir="/tmp/praisonai_snapshot_compare",
            scenarios=scenarios,
            output="minimal",
        )
        
        current_snap = create_snapshot_from_suite(result, name)
        comparison = manager.compare(current_snap)
        
        if output_format == "json":
            import json
            typer.echo(json.dumps(comparison.to_dict(), indent=2))
        else:
            typer.echo(format_comparison_report(comparison))
        
        if comparison.is_regression():
            raise typer.Exit(1)  # Exit with error on regression
    else:
        # Create new snapshot
        typer.echo(f"🔬 Creating performance snapshot '{name}'...", err=True)
        
        scenarios = [
            ScenarioConfig(name="simple", prompt="hi", stream=False, iterations=3, warmup=1),
            ScenarioConfig(name="stream", prompt="hi", stream=True, iterations=2, warmup=1),
        ]
        result = run_profile_suite(
            output_dir="/tmp/praisonai_snapshot",
            scenarios=scenarios,
            verbose=True,
        )
        
        snapshot = create_snapshot_from_suite(result, name)
        
        if baseline:
            path = manager.save_baseline(snapshot)
            typer.echo(f"\n✅ Baseline saved to: {path}")
        else:
            path = manager.save(snapshot)
            typer.echo(f"\n✅ Snapshot saved to: {path}")
        
        if output_format == "json":
            import json
            typer.echo(json.dumps(snapshot.to_dict(), indent=2))
        else:
            typer.echo("\nSnapshot Summary:")
            typer.echo(f"  Startup Cold: {snapshot.startup_cold_ms:.2f}ms")
            typer.echo(f"  Import Time:  {snapshot.import_time_ms:.2f}ms")
            typer.echo(f"  Query Time:   {snapshot.query_time_ms:.2f}ms")


@app.command("optimize")
def profile_optimize(
    prewarm: bool = typer.Option(False, "--prewarm", help="Enable provider pre-warming"),
    lite: bool = typer.Option(False, "--lite", help="Enable lite mode (skip type validation)"),
    show_config: bool = typer.Option(False, "--show", help="Show current optimization config"),
):
    """
    Configure performance optimizations.
    
    All optimizations are opt-in and safe by default.
    
    Examples:
        praisonai profile optimize --show
        praisonai profile optimize --prewarm
        praisonai profile optimize --lite
    """
    try:
        from ..features.profiler import (
            PrewarmManager,
            get_lite_mode_config,
            get_provider_cache,
        )
    except ImportError as e:
        typer.echo(f"Error: Profiler module not available: {e}", err=True)
        raise typer.Exit(1)
    
    if show_config:
        typer.echo("=" * 50)
        typer.echo("Performance Optimization Status")
        typer.echo("=" * 50)
        
        lite_config = get_lite_mode_config()
        typer.echo(f"\nLite Mode: {'Enabled' if lite_config.enabled else 'Disabled'}")
        if lite_config.enabled:
            typer.echo(f"  Skip Type Validation: {lite_config.skip_type_validation}")
            typer.echo(f"  Skip Model Validation: {lite_config.skip_model_validation}")
            typer.echo(f"  Minimal Imports: {lite_config.minimal_imports}")
        
        typer.echo(f"\nPre-warming: {'Enabled' if PrewarmManager.is_enabled() else 'Disabled'}")
        
        cache = get_provider_cache()
        stats = cache.get_stats()
        typer.echo("\nProvider Cache:")
        typer.echo(f"  Hits: {stats['hits']}")
        typer.echo(f"  Misses: {stats['misses']}")
        typer.echo(f"  Size: {stats['size']}")
        
        typer.echo("\n" + "=" * 50)
        typer.echo("\nTo enable optimizations, set environment variables:")
        typer.echo("  PRAISONAI_LITE_MODE=1")
        typer.echo("  PRAISONAI_SKIP_TYPE_VALIDATION=1")
        typer.echo("  PRAISONAI_MINIMAL_IMPORTS=1")
        return
    
    if prewarm:
        typer.echo("🔥 Enabling provider pre-warming...")
        PrewarmManager.enable()
        
        import os
        if os.environ.get('OPENAI_API_KEY'):
            typer.echo("   Pre-warming OpenAI...")
            PrewarmManager.prewarm_provider('openai')
        if os.environ.get('ANTHROPIC_API_KEY'):
            typer.echo("   Pre-warming Anthropic...")
            PrewarmManager.prewarm_provider('anthropic')
        
        typer.echo("✅ Pre-warming initiated (runs in background)")
    
    if lite:
        typer.echo("⚡ Lite mode configuration:")
        typer.echo("   Set these environment variables to enable:")
        typer.echo("   export PRAISONAI_LITE_MODE=1")
        typer.echo("   export PRAISONAI_SKIP_TYPE_VALIDATION=1")
        typer.echo("   export PRAISONAI_MINIMAL_IMPORTS=1")
    
    if not prewarm and not lite and not show_config:
        typer.echo("Use --show to see current config, or --prewarm/--lite to enable optimizations")


@app.callback(invoke_without_command=True)
def profile_callback(ctx: typer.Context):
    """Show profile help if no subcommand."""
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
