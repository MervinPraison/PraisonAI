"""
PraisonAI Examples CLI Command.

Run and manage example files with reporting and diagnostics.

Usage:
    praisonai examples run                    # Run all examples
    praisonai examples run --path ./examples  # Custom path
    praisonai examples list                   # List discovered examples
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer

app = typer.Typer(help="Run and manage example files")


def _get_default_examples_path() -> Path:
    """Get default examples path (repo examples/ or cwd)."""
    candidates = [
        Path.home() / "praisonai-package" / "examples",
        Path("/Users/praison/praisonai-package/examples"),
        Path.cwd() / "examples",
        Path(__file__).parent.parent.parent.parent.parent / "examples",  # repo root
    ]
    
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    
    return Path.cwd()


def _get_default_report_dir() -> Path:
    """Get default report directory with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.home() / "Downloads" / "reports" / "examples" / timestamp


@app.command()
def run(
    path: Optional[Path] = typer.Option(
        None,
        "--path", "-p",
        help="Path to examples directory",
    ),
    include: Optional[List[str]] = typer.Option(
        None,
        "--include", "-i",
        help="Include patterns (glob), can be specified multiple times",
    ),
    exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude", "-e",
        help="Exclude patterns (glob), can be specified multiple times",
    ),
    group: Optional[List[str]] = typer.Option(
        None,
        "--group", "-g",
        help="Run only specific groups (top-level dirs), can be repeated",
    ),
    timeout: int = typer.Option(
        60,
        "--timeout", "-t",
        help="Per-example timeout in seconds",
    ),
    max_items: Optional[int] = typer.Option(
        None,
        "--max-items",
        help="Maximum examples to run",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast", "-x",
        help="Stop on first failure",
    ),
    no_stream: bool = typer.Option(
        False,
        "--no-stream",
        help="Don't stream output to terminal",
    ),
    report_dir: Optional[Path] = typer.Option(
        None,
        "--report-dir", "-r",
        help="Directory for reports (default: ./reports/examples/<timestamp>)",
    ),
    no_json: bool = typer.Option(
        False,
        "--no-json",
        help="Skip JSON report generation",
    ),
    no_md: bool = typer.Option(
        False,
        "--no-md",
        help="Skip Markdown report generation",
    ),
    no_csv: bool = typer.Option(
        False,
        "--no-csv",
        help="Skip CSV report generation",
    ),
    require_env: Optional[List[str]] = typer.Option(
        None,
        "--require-env",
        help="Required env vars (skip all if missing)",
    ),
    python: Optional[str] = typer.Option(
        None,
        "--python",
        help="Python executable to use (default: current interpreter)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet", "-q",
        help="Minimal output",
    ),
):
    """
    Run all examples in the specified directory.
    
    Examples:
        praisonai examples run
        praisonai examples run --path ./examples --timeout 120
        praisonai examples run --group python --group mcp --max-items 5
        praisonai examples run --include "context/*" --exclude "*_wow.py"
        praisonai examples run --fail-fast --no-stream
    """
    # Lazy import to avoid loading at CLI startup
    from praisonai.suite_runner import ExamplesSource, SuiteExecutor, RunResult
    
    # Resolve paths
    examples_path = path or _get_default_examples_path()
    output_dir = report_dir or _get_default_report_dir()
    
    if not examples_path.exists():
        typer.echo(f"❌ Examples path not found: {examples_path}")
        raise typer.Exit(2)
    
    # Create source
    source = ExamplesSource(
        root=examples_path,
        include_patterns=list(include) if include else None,
        exclude_patterns=list(exclude) if exclude else None,
        groups=list(group) if group else None,
    )
    
    # Discover items
    items = source.discover()
    
    # Create executor
    executor = SuiteExecutor(
        suite="examples",
        source_path=examples_path,
        timeout=timeout,
        fail_fast=fail_fast,
        stream_output=not no_stream,
        max_items=max_items,
        require_env=list(require_env) if require_env else None,
        report_dir=output_dir,
        generate_json=not no_json,
        generate_md=not no_md,
        generate_csv=not no_csv,
        python_executable=python,
        pythonpath_additions=source.get_pythonpath(),
        groups=list(group) if group else None,
    )
    
    # Status icons
    icons = {
        "passed": "✅",
        "failed": "❌",
        "skipped": "⏭️",
        "timeout": "⏱️",
        "xfail": "⚠️",
        "not_run": "📝",
    }
    
    def on_item_start(item, idx: int, total: int):
        if not quiet:
            typer.echo(f"\n[{idx}/{total}] Running: {item.display_name}")
    
    def on_item_end(result: RunResult, idx: int, total: int):
        icon = icons.get(result.status, "?")
        duration = f"{result.duration_seconds:.2f}s" if result.duration_seconds else ""
        
        if quiet:
            typer.echo(f"{icon} {result.display_name}")
        else:
            msg = f"  {icon} {result.status.upper()}"
            if duration:
                msg += f" ({duration})"
            if result.skip_reason:
                msg += f" - {result.skip_reason}"
            if result.error_message and not no_stream:
                msg += f"\n     Error: {result.error_message[:100]}"
            typer.echo(msg)
    
    def on_output(line: str, stream: str):
        if not quiet and not no_stream:
            prefix = "  │ " if stream == "stdout" else "  │ [err] "
            typer.echo(f"{prefix}{line.rstrip()}")
    
    # Print header
    if not quiet:
        typer.echo("=" * 60)
        typer.echo("PraisonAI Examples Runner")
        typer.echo("=" * 60)
        typer.echo(f"Path: {examples_path}")
        typer.echo(f"Timeout: {timeout}s")
        if group:
            typer.echo(f"Groups: {', '.join(group)}")
        typer.echo(f"Reports: {output_dir}")
        typer.echo(f"Items: {len(items)}")
    
    # Run examples
    report = executor.run(
        items=items,
        on_item_start=on_item_start,
        on_item_end=on_item_end,
        on_output=on_output if not no_stream else None,
    )
    
    # Update report with CLI args
    report.cli_args = [f"--path={examples_path}", f"--timeout={timeout}"]
    if fail_fast:
        report.cli_args.append("--fail-fast")
    if group:
        for g in group:
            report.cli_args.append(f"--group={g}")
    
    # Print summary
    totals = report.totals
    total_count = sum(totals.values())
    
    if not quiet:
        typer.echo("\n" + "=" * 60)
        typer.echo("SUMMARY")
        typer.echo("=" * 60)
        typer.echo(f"  ✅ Passed:  {totals['passed']}")
        typer.echo(f"  ❌ Failed:  {totals['failed']}")
        typer.echo(f"  ⏭️ Skipped: {totals['skipped']}")
        typer.echo(f"  ⏱️ Timeout: {totals['timeout']}")
        typer.echo(f"  ⚠️ XFail:   {totals['xfail']}")
        typer.echo("  ─────────────────")
        typer.echo(f"  Total:     {total_count}")
        typer.echo("=" * 60)
        
        if output_dir.exists():
            typer.echo(f"\n📁 Reports saved to: {output_dir}")
    
    # Exit code
    if totals['failed'] > 0 or totals['timeout'] > 0:
        raise typer.Exit(1)
    
    raise typer.Exit(0)


@app.command("list")
def list_examples(
    path: Optional[Path] = typer.Option(
        None,
        "--path", "-p",
        help="Path to examples directory",
    ),
    include: Optional[List[str]] = typer.Option(
        None,
        "--include", "-i",
        help="Include patterns (glob)",
    ),
    exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude", "-e",
        help="Exclude patterns (glob)",
    ),
    group: Optional[List[str]] = typer.Option(
        None,
        "--group", "-g",
        help="Filter by group (top-level dir)",
    ),
    show_metadata: bool = typer.Option(
        False,
        "--metadata", "-m",
        help="Show parsed metadata for each example",
    ),
    show_groups: bool = typer.Option(
        False,
        "--groups",
        help="Show available groups only",
    ),
):
    """
    List discovered examples without running them.
    
    Examples:
        praisonai examples list
        praisonai examples list --groups
        praisonai examples list --group python --metadata
    """
    from praisonai.suite_runner import ExamplesSource
    
    examples_path = path or _get_default_examples_path()
    
    if not examples_path.exists():
        typer.echo(f"❌ Examples path not found: {examples_path}")
        raise typer.Exit(2)
    
    source = ExamplesSource(
        root=examples_path,
        include_patterns=list(include) if include else None,
        exclude_patterns=list(exclude) if exclude else None,
        groups=list(group) if group else None,
    )
    
    # Show groups only
    if show_groups:
        groups = source.get_groups()
        typer.echo(f"Available groups in {examples_path}:\n")
        for g in groups:
            typer.echo(f"  - {g}")
        return
    
    items = source.discover()
    
    typer.echo(f"Found {len(items)} examples in {examples_path}\n")
    
    for idx, item in enumerate(items, 1):
        rel_path = item.source_path.relative_to(examples_path)
        
        if show_metadata:
            flags = []
            if item.skip:
                flags.append("skip")
            if item.timeout:
                flags.append(f"timeout={item.timeout}")
            if item.require_env:
                flags.append(f"env={','.join(item.require_env)}")
            if item.xfail:
                flags.append(f"xfail={item.xfail}")
            if item.is_interactive:
                flags.append("interactive")
            
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            typer.echo(f"  {idx:3}. [{item.group}] {rel_path}{flag_str}")
        else:
            typer.echo(f"  {idx:3}. [{item.group}] {rel_path}")


@app.command()
def info(
    example: Path = typer.Argument(
        ...,
        help="Path to example file",
    ),
):
    """
    Show detailed metadata for a specific example.
    
    Examples:
        praisonai examples info ./examples/context/01_basic.py
    """
    from praisonai.suite_runner import ExamplesSource
    
    if not example.exists():
        typer.echo(f"❌ Example not found: {example}")
        raise typer.Exit(2)
    
    # Create a source just to parse the file
    source = ExamplesSource(root=example.parent)
    item = source._create_item(example)
    
    typer.echo(f"Example: {example.name}")
    typer.echo(f"Path: {example}")
    typer.echo(f"Group: {item.group}")
    typer.echo("")
    typer.echo("Metadata:")
    typer.echo(f"  Runnable: {item.runnable}")
    typer.echo(f"  Decision: {item.runnable_decision}")
    typer.echo(f"  Skip: {item.skip}")
    if item.skip_reason:
        typer.echo(f"  Skip Reason: {item.skip_reason}")
    typer.echo(f"  Timeout: {item.timeout or 'default'}")
    typer.echo(f"  Required Env: {', '.join(item.require_env) if item.require_env else 'none'}")
    typer.echo(f"  XFail: {item.xfail or 'no'}")
    typer.echo(f"  Interactive: {item.is_interactive}")
    typer.echo(f"  Code Hash: {item.code_hash}")


@app.command("stats")
def examples_stats(
    path: Optional[Path] = typer.Option(
        None,
        "--path", "-p",
        help="Path to examples directory",
    ),
    group: Optional[List[str]] = typer.Option(
        None,
        "--group", "-g",
        help="Filter by group (top-level dir)",
    ),
):
    """
    Show statistics for examples.
    
    Displays counts by group, runnable status, and agent-centric usage.
    
    Examples:
        praisonai examples stats
        praisonai examples stats --group python --group mcp
    """
    from collections import Counter
    from praisonai.suite_runner import ExamplesSource
    
    examples_path = path or _get_default_examples_path()
    
    if not examples_path.exists():
        typer.echo(f"❌ Examples path not found: {examples_path}")
        raise typer.Exit(2)
    
    source = ExamplesSource(
        root=examples_path,
        groups=list(group) if group else None,
    )
    
    items = source.discover()
    
    # Calculate stats
    group_counts = Counter(item.group for item in items)
    runnable_by_group = Counter(item.group for item in items if item.runnable)
    
    # Agent-centric stats
    agent_count = sum(1 for item in items if item.uses_agent)
    agents_count = sum(1 for item in items if item.uses_agents)
    workflow_count = sum(1 for item in items if item.uses_workflow)
    
    agent_by_group = Counter(item.group for item in items if item.uses_agent)
    agents_by_group = Counter(item.group for item in items if item.uses_agents)
    workflow_by_group = Counter(item.group for item in items if item.uses_workflow)
    
    typer.echo("\n📊 Examples Statistics")
    typer.echo(f"Path: {examples_path}")
    typer.echo("=" * 80)
    
    typer.echo(f"\n{'Group':<20} {'Total':>8} {'Runnable':>10} {'Agent':>8} {'Agents':>8} {'Workflow':>10}")
    typer.echo("-" * 80)
    
    for g in sorted(group_counts.keys()):
        typer.echo(
            f"{g:<20} {group_counts[g]:>8} {runnable_by_group[g]:>10} "
            f"{agent_by_group[g]:>8} {agents_by_group[g]:>8} {workflow_by_group[g]:>10}"
        )
    
    typer.echo("-" * 80)
    typer.echo(
        f"{'TOTAL':<20} {len(items):>8} {sum(1 for i in items if i.runnable):>10} "
        f"{agent_count:>8} {agents_count:>8} {workflow_count:>10}"
    )
    typer.echo()


@app.command("run-all")
def examples_run_all(
    path: Optional[Path] = typer.Option(
        None,
        "--path", "-p",
        help="Path to examples directory",
    ),
    timeout: int = typer.Option(
        60,
        "--timeout", "-t",
        help="Per-example timeout in seconds",
    ),
    report_dir: Optional[Path] = typer.Option(
        None,
        "--report-dir", "-r",
        help="Directory for reports (default: ~/Downloads/reports/examples/<timestamp>)",
    ),
    parallel: bool = typer.Option(
        True,
        "--parallel/--sequential",
        help="Run groups in parallel (default: parallel)",
    ),
    max_workers: int = typer.Option(
        4,
        "--workers", "-w",
        help="Max parallel workers (default: 4)",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet", "-q",
        help="Minimal output",
    ),
    ci: bool = typer.Option(
        False,
        "--ci",
        help="CI-friendly output (no colors, proper exit codes)",
    ),
):
    """
    Run all examples group-by-group.
    
    Executes all groups and generates a comprehensive report.
    Uses parallel execution by default for faster results.
    
    Examples:
        praisonai examples run-all
        praisonai examples run-all --sequential
        praisonai examples run-all --workers 8 --timeout 120
    """
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from praisonai.suite_runner import ExamplesSource, SuiteExecutor, RunResult
    
    examples_path = path or _get_default_examples_path()
    output_dir = report_dir or _get_default_report_dir()
    
    if not examples_path.exists():
        typer.echo(f"❌ Examples path not found: {examples_path}")
        raise typer.Exit(2)
    
    # Get all groups
    source = ExamplesSource(root=examples_path)
    all_groups = sorted(source.get_groups())
    
    if ci:
        print(f"Found {len(all_groups)} groups to process")
        print(f"Mode: {'parallel' if parallel else 'sequential'}")
        print(f"Workers: {max_workers}")
        print(f"Timeout: {timeout}s")
        print("=" * 60)
    else:
        typer.echo(f"Found {len(all_groups)} groups to process")
        typer.echo(f"Mode: {'parallel' if parallel else 'sequential'}")
        typer.echo("=" * 60)
    
    # Track overall results
    overall_results = {
        'passed': 0, 'failed': 0, 'skipped': 0,
        'timeout': 0, 'not_run': 0, 'total': 0, 'xfail': 0,
    }
    group_summaries = []
    
    def run_group(group_name: str) -> dict:
        """Run a single group and return summary."""
        group_source = ExamplesSource(root=examples_path, groups=[group_name])
        items = group_source.discover()
        
        if not items:
            return {
                'group': group_name,
                'total': 0, 'passed': 0, 'failed': 0,
                'skipped': 0, 'timeout': 0, 'not_run': 0, 'xfail': 0,
            }
        
        group_report_dir = output_dir / group_name
        group_report_dir.mkdir(parents=True, exist_ok=True)
        
        executor = SuiteExecutor(
            suite='examples',
            source_path=examples_path,
            report_dir=group_report_dir,
            timeout=timeout,
            stream_output=False,
            generate_json=True,
            generate_md=True,
            generate_csv=True,
            groups=[group_name],
        )
        
        report = executor.run(items=items)
        totals = report.totals
        
        return {
            'group': group_name,
            **totals,
        }
    
    if parallel and len(all_groups) > 1:
        # Parallel execution using ThreadPoolExecutor (ProcessPoolExecutor cannot pickle nested functions)
        with ThreadPoolExecutor(max_workers=min(max_workers, len(all_groups))) as pool:
            futures = {pool.submit(run_group, g): g for g in all_groups}
            
            for future in as_completed(futures):
                group_name = futures[future]
                try:
                    summary = future.result()
                    group_summaries.append(summary)
                    
                    # Update overall
                    for key in overall_results:
                        if key in summary:
                            overall_results[key] += summary[key]
                    
                    if not quiet:
                        if ci:
                            print(
                                f"PASS {group_name}: "
                                f"PASS:{summary['passed']} FAIL:{summary['failed']} "
                                f"SKIP:{summary['skipped']} TIMEOUT:{summary['timeout']} XFAIL:{summary.get('xfail', 0)}"
                            )
                        else:
                            typer.echo(
                                f"✅ {group_name}: "
                                f"✅{summary['passed']} ❌{summary['failed']} "
                                f"⏭️{summary['skipped']} ⏱️{summary['timeout']} ⚠️{summary.get('xfail', 0)}"
                            )
                except Exception as e:
                    if ci:
                        print(f"FAIL {group_name}: Error - {e}")
                    else:
                        typer.echo(f"❌ {group_name}: Error - {e}")
    else:
        # Sequential execution with real-time output
        for group_name in all_groups:
            if not quiet:
                typer.echo(f"\n{'='*60}")
                typer.echo(f"GROUP: {group_name}")
                typer.echo(f"{'='*60}")
            
            group_source = ExamplesSource(root=examples_path, groups=[group_name])
            items = group_source.discover()
            
            if not items:
                if not quiet:
                    typer.echo("  No items found, skipping")
                group_summaries.append({
                    'group': group_name,
                    'total': 0, 'passed': 0, 'failed': 0,
                    'skipped': 0, 'timeout': 0, 'not_run': 0, 'xfail': 0,
                })
                continue
            
            group_report_dir = output_dir / group_name
            group_report_dir.mkdir(parents=True, exist_ok=True)
            
            executor = SuiteExecutor(
                suite='examples',
                source_path=examples_path,
                report_dir=group_report_dir,
                timeout=timeout,
                stream_output=False,
                generate_json=True,
                generate_md=True,
                generate_csv=True,
                groups=[group_name],
            )
            
            icons = {'passed': '✅', 'failed': '❌', 'skipped': '⏭️', 'timeout': '⏱️', 'xfail': '⚠️'}
            
            def on_start(item, idx, total):
                if not quiet:
                    typer.echo(f"  [{idx}/{total}] {item.display_name} ", nl=False)
            
            def on_end(result: RunResult, idx, total):
                if not quiet:
                    icon = icons.get(result.status, '❓')
                    typer.echo(f"{icon}")
            
            report = executor.run(items=items, on_item_start=on_start, on_item_end=on_end)
            totals = report.totals
            
            group_summaries.append({'group': group_name, **totals})
            
            for key in overall_results:
                if key in totals:
                    overall_results[key] += totals[key]
            
            if not quiet:
                typer.echo(
                    f"\n  Summary: ✅{totals['passed']} ❌{totals['failed']} "
                    f"⏭️{totals['skipped']} ⏱️{totals['timeout']} ⚠️{totals.get('xfail', 0)}"
                )
    
    # Final report
    if ci:
        print("")
        print("=" * 80)
        print("FINAL REPORT - ALL GROUPS")
        print("=" * 80)
        print(f"{'Group':<20} {'Total':>8} {'Passed':>8} {'Failed':>8} {'Skip':>8} {'Timeout':>8} {'XFail':>8}")
        print("-" * 80)
        for gs in sorted(group_summaries, key=lambda x: x['group']):
            print(
                f"{gs['group']:<20} {gs['total']:>8} {gs['passed']:>8} {gs['failed']:>8} "
                f"{gs['skipped']:>8} {gs['timeout']:>8} {gs.get('xfail', 0):>8}"
            )
        print("-" * 80)
        print(
            f"{'TOTAL':<20} {overall_results['total']:>8} {overall_results['passed']:>8} "
            f"{overall_results['failed']:>8} {overall_results['skipped']:>8} "
            f"{overall_results['timeout']:>8} {overall_results.get('xfail', 0):>8}"
        )
    else:
        typer.echo("\n" + "=" * 80)
        typer.echo("FINAL REPORT - ALL GROUPS")
        typer.echo("=" * 80)
        typer.echo(f"\n{'Group':<20} {'Total':>8} {'Passed':>8} {'Failed':>8} {'Skip':>8} {'Timeout':>8} {'XFail':>8}")
        typer.echo("-" * 80)
        for gs in sorted(group_summaries, key=lambda x: x['group']):
            typer.echo(
                f"{gs['group']:<20} {gs['total']:>8} {gs['passed']:>8} {gs['failed']:>8} "
                f"{gs['skipped']:>8} {gs['timeout']:>8} {gs.get('xfail', 0):>8}"
            )
        typer.echo("-" * 80)
        typer.echo(
            f"{'TOTAL':<20} {overall_results['total']:>8} {overall_results['passed']:>8} "
            f"{overall_results['failed']:>8} {overall_results['skipped']:>8} "
            f"{overall_results['timeout']:>8} {overall_results.get('xfail', 0):>8}"
        )
    
    # Save final summary
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / 'final_summary.json'
    with open(summary_path, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'overall': overall_results,
            'groups': group_summaries,
        }, f, indent=2)
    
    if ci:
        print(f"Final summary: {summary_path}")
        print(f"Group reports: {output_dir}")
    else:
        typer.echo(f"\n📁 Final summary saved to: {summary_path}")
        typer.echo(f"📁 Individual group reports in: {output_dir}")
    
    # Exit code
    if overall_results['failed'] > 0 or overall_results['timeout'] > 0:
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("report")
def examples_report(
    report_dir: Optional[Path] = typer.Argument(
        None,
        help="Report directory path (default: auto-detect latest)",
    ),
    base_dir: Optional[Path] = typer.Option(
        None,
        "--base-dir", "-b",
        help="Base reports directory (default: ~/Downloads/reports/examples)",
    ),
    limit: int = typer.Option(
        50,
        "--limit", "-n",
        help="Limit rows in tables (0 = no limit)",
    ),
    errors: bool = typer.Option(
        True,
        "--errors/--no-errors",
        help="Show error grouping section",
    ),
    wide: bool = typer.Option(
        False,
        "--wide/--no-wide",
        help="Wide output: full error messages and item lists",
    ),
    show_paths: bool = typer.Option(
        True,
        "--show-paths/--no-show-paths",
        help="Show affected item paths in error groups",
    ),
    match: Optional[List[str]] = typer.Option(
        None,
        "--match", "-m",
        help="Filter by status (repeatable: --match failed --match timeout)",
    ),
    group: Optional[List[str]] = typer.Option(
        None,
        "--group", "-g",
        help="Filter by group name (repeatable)",
    ),
    contains: Optional[str] = typer.Option(
        None,
        "--contains", "-c",
        help="Filter items whose error contains text (case-insensitive)",
    ),
    open_dir: bool = typer.Option(
        False,
        "--open",
        help="Show report artifacts listing",
    ),
    output_format: str = typer.Option(
        "table",
        "--format", "-f",
        help="Output format: table or json",
    ),
):
    """
    View execution report with failures and error grouping.
    
    Examples:
        praisonai examples report                    # View latest report
        praisonai examples report ./my-report        # View specific report
        praisonai examples report --wide --limit 0   # Full details
        praisonai examples report --match failed     # Only failures
        praisonai examples report --format json      # JSON output
    """
    # Lazy import to avoid loading at CLI startup
    from praisonai.suite_runner.report_viewer import view_report
    
    output, exit_code = view_report(
        report_dir=report_dir,
        suite="examples",
        base_dir=base_dir,
        limit=limit,
        show_errors=errors,
        wide=wide,
        show_paths=show_paths,
        match_statuses=match,
        match_groups=group,
        contains=contains,
        show_artifacts=open_dir,
        output_format=output_format,
    )
    
    typer.echo(output)
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()
