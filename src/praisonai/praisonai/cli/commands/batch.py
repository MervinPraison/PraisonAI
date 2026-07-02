"""
PraisonAI Batch CLI Command.

Run all Python files with PraisonAI imports in the current directory.
Designed for quick debugging - running multiple local scripts at once.

Usage:
    praisonai batch                    # Run all PraisonAI scripts in current dir
    praisonai batch --sub              # Include subdirectories
    praisonai batch --sub --depth 2    # Limit recursion depth
    praisonai batch --parallel         # Run in parallel with async reporting
    praisonai batch list               # List discovered files
    praisonai batch stats              # Show statistics
    praisonai batch report             # View latest report
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    help="Run all PraisonAI scripts in current folder for quick debugging",
    no_args_is_help=False,
)


def _get_default_report_dir() -> Path:
    """Get default report directory with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.home() / "Downloads" / "reports" / "batch" / timestamp


def _get_latest_report_dir() -> Optional[Path]:
    """Get the latest report directory."""
    base_dir = Path.home() / "Downloads" / "reports" / "batch"
    if not base_dir.exists():
        return None
    
    # Find most recent timestamp directory
    dirs = [d for d in base_dir.iterdir() if d.is_dir()]
    if not dirs:
        return None
    
    return max(dirs, key=lambda d: d.name)


@app.callback(invoke_without_command=True)
def batch_run(
    ctx: typer.Context,
    path: Optional[Path] = typer.Option(
        None,
        "--path", "-p",
        help="Path to search (default: current directory)",
    ),
    recursive: bool = typer.Option(
        False,
        "--sub", "--recursive", "-r",
        help="Include subdirectories",
    ),
    depth: Optional[int] = typer.Option(
        None,
        "--depth", "-d",
        help="Maximum recursion depth (only with --sub)",
    ),
    include_tests: bool = typer.Option(
        False,
        "--include-tests",
        help="Include test files (test_*.py, *_test.py)",
    ),
    timeout: int = typer.Option(
        60,
        "--timeout", "-t",
        help="Per-script timeout in seconds",
    ),
    max_items: Optional[int] = typer.Option(
        None,
        "--max-items",
        help="Maximum scripts to run",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast", "-x",
        help="Stop on first failure",
    ),
    parallel: bool = typer.Option(
        True,
        "--parallel/--sequential",
        help="Run in parallel (default: parallel)",
    ),
    max_workers: int = typer.Option(
        4,
        "--workers", "-w",
        help="Max parallel workers (only with --parallel)",
    ),
    no_stream: bool = typer.Option(
        False,
        "--no-stream",
        help="Don't stream output to terminal",
    ),
    report_dir: Optional[Path] = typer.Option(
        None,
        "--report-dir",
        help="Directory for reports (default: ~/Downloads/reports/batch/<timestamp>)",
    ),
    no_report: bool = typer.Option(
        False,
        "--no-report",
        help="Skip report generation",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet", "-q",
        help="Minimal output",
    ),
    server: bool = typer.Option(
        False,
        "--server",
        help="Run only server scripts (uvicorn, Flask, streamlit, etc.) with 10s timeout",
    ),
    filter_type: Optional[str] = typer.Option(
        None,
        "--filter", "-f",
        help="Filter by type: 'agent', 'agents', or 'workflow'",
    ),
    ci: bool = typer.Option(
        False,
        "--ci",
        help="CI-friendly output (no colors, proper exit codes)",
    ),
):
    """
    Run all PraisonAI scripts in the current folder.
    
    Quick debugging tool for running multiple Python files that use
    praisonaiagents or praisonai. Unlike 'praisonai run' (which runs
    agent configs) or 'praisonai examples' (which runs repo examples),
    this command finds and executes local scripts for rapid testing.
    
    Only files containing 'from praisonaiagents' or 'from praisonai'
    are executed. Test files (test_*.py) are excluded by default.
    
    Examples:
        praisonai batch                    # Run all in current dir
        praisonai batch --sub              # Include subdirectories
        praisonai batch --sub --depth 2    # Limit depth
        praisonai batch --parallel         # Run in parallel
        praisonai batch --timeout 120      # Custom timeout
    """
    # If a subcommand was invoked, skip the default run
    if ctx.invoked_subcommand is not None:
        return
    
    # Lazy import to avoid loading at CLI startup
    from praisonai.suite_runner import BatchSource, SuiteExecutor, RunResult
    
    # Resolve paths
    search_path = Path(path).resolve() if path else Path.cwd().resolve()
    output_dir = report_dir or _get_default_report_dir()
    
    if not search_path.exists():
        if ci:
            print(f"ERROR: Path not found: {search_path}")
        else:
            typer.echo(f"❌ Path not found: {search_path}")
        raise typer.Exit(2)
    
    # Validate filter_type
    if filter_type and filter_type not in ("agent", "agents", "workflow"):
        if ci:
            print(f"ERROR: Invalid filter type: {filter_type}. Use 'agent', 'agents', or 'workflow'")
        else:
            typer.echo(f"❌ Invalid filter type: {filter_type}. Use 'agent', 'agents', or 'workflow'")
        raise typer.Exit(2)
    
    # Server mode uses 10s timeout by default
    effective_timeout = 10 if server else timeout
    
    # Create source
    source = BatchSource(
        root=search_path,
        recursive=recursive,
        depth=depth,
        exclude_tests=not include_tests,
        exclude_servers=not server,  # Exclude servers by default, include when --server
        server_only=server,  # Only servers when --server flag
        filter_type=filter_type,
    )
    
    # Discover items
    items = source.discover()
    
    if not items:
        if ci:
            print(f"INFO: No PraisonAI scripts found in {search_path}")
        else:
            typer.echo(f"ℹ️ No PraisonAI scripts found in {search_path}")
            if not recursive:
                typer.echo("   Tip: Use --sub to include subdirectories")
        raise typer.Exit(0)
    
    # Parallel execution
    if parallel:
        _run_parallel(
            items=items,
            source=source,
            search_path=search_path,
            output_dir=output_dir,
            timeout=effective_timeout,
            max_workers=max_workers,
            quiet=quiet,
            ci=ci,
        )
        return
    
    # Sequential execution (default)
    executor = SuiteExecutor(
        suite="batch",
        source_path=search_path,
        timeout=effective_timeout,
        fail_fast=fail_fast,
        stream_output=not no_stream,
        max_items=max_items,
        report_dir=output_dir if not no_report else None,
        generate_json=not no_report,
        generate_md=not no_report,
        generate_csv=not no_report,
        pythonpath_additions=source.get_pythonpath(),
    )
    
    # Status icons (CI mode uses text)
    if ci:
        icons = {
            "passed": "PASS",
            "failed": "FAIL",
            "skipped": "SKIP",
            "timeout": "TIMEOUT",
            "not_run": "NOT_RUN",
            "xfail": "XFAIL",
        }
    else:
        icons = {
            "passed": "✅",
            "failed": "❌",
            "skipped": "⏭️",
            "timeout": "⏱️",
            "not_run": "📝",
            "xfail": "⚠️",
        }
    
    def on_item_start(item, idx: int, total: int):
        if not quiet:
            if ci:
                print(f"[{idx}/{total}] Running: {item.display_name}")
            else:
                typer.echo(f"\n[{idx}/{total}] Running: {item.display_name}")
    
    def on_item_end(result: RunResult, idx: int, total: int):
        icon = icons.get(result.status, "?")
        duration = f"{result.duration_seconds:.2f}s" if result.duration_seconds else ""
        
        if quiet:
            if ci:
                print(f"{icon} {result.display_name}")
            else:
                typer.echo(f"{icon} {result.display_name}")
        else:
            msg = f"  {icon} {result.status.upper()}"
            if duration:
                msg += f" ({duration})"
            if result.skip_reason:
                msg += f" - {result.skip_reason}"
            if result.error_message and not no_stream:
                msg += f"\n     Error: {result.error_message[:100]}"
            if ci:
                print(msg)
            else:
                typer.echo(msg)
    
    def on_output(line: str, stream: str):
        if not quiet and not no_stream:
            prefix = "  | " if ci else "  │ "
            if stream != "stdout":
                prefix += "[err] "
            if ci:
                print(f"{prefix}{line.rstrip()}")
            else:
                typer.echo(f"{prefix}{line.rstrip()}")
    
    # Print header
    if not quiet:
        if ci:
            print("=" * 60)
            print("PraisonAI Batch Runner")
            print("=" * 60)
            print(f"Path: {search_path}")
            print(f"Recursive: {recursive}")
            if depth:
                print(f"Depth: {depth}")
            print(f"Timeout: {effective_timeout}s")
            print(f"Scripts: {len(items)}")
            if server:
                print("Mode: Server scripts only")
            if filter_type:
                print(f"Filter: {filter_type}")
            if not no_report:
                print(f"Reports: {output_dir}")
        else:
            typer.echo("=" * 60)
            typer.echo("PraisonAI Batch Runner")
            typer.echo("=" * 60)
            typer.echo(f"Path: {search_path}")
            typer.echo(f"Recursive: {recursive}")
            if depth:
                typer.echo(f"Depth: {depth}")
            typer.echo(f"Timeout: {effective_timeout}s")
            typer.echo(f"Scripts: {len(items)}")
            if server:
                typer.echo("Mode: Server scripts only")
            if filter_type:
                typer.echo(f"Filter: {filter_type}")
            if not no_report:
                typer.echo(f"Reports: {output_dir}")
    
    # Run
    report = executor.run(
        items=items,
        on_item_start=on_item_start,
        on_item_end=on_item_end,
        on_output=on_output if not no_stream else None,
    )
    
    # Print summary
    totals = report.totals
    total_count = sum(totals.values())
    
    if not quiet:
        if ci:
            print("")
            print("=" * 60)
            print("SUMMARY")
            print("=" * 60)
            print(f"  PASSED:  {totals['passed']}")
            print(f"  FAILED:  {totals['failed']}")
            print(f"  SKIPPED: {totals['skipped']}")
            print(f"  TIMEOUT: {totals['timeout']}")
            print("  -----------------")
            print(f"  TOTAL:   {total_count}")
            print("=" * 60)
            if not no_report and output_dir.exists():
                print(f"Reports: {output_dir}")
        else:
            typer.echo("\n" + "=" * 60)
            typer.echo("SUMMARY")
            typer.echo("=" * 60)
            typer.echo(f"  ✅ Passed:  {totals['passed']}")
            typer.echo(f"  ❌ Failed:  {totals['failed']}")
            typer.echo(f"  ⏭️ Skipped: {totals['skipped']}")
            typer.echo(f"  ⏱️ Timeout: {totals['timeout']}")
            typer.echo("  ─────────────────")
            typer.echo(f"  Total:     {total_count}")
            typer.echo("=" * 60)
            
            if not no_report and output_dir.exists():
                typer.echo(f"\n📁 Reports saved to: {output_dir}")
    
    # Exit code
    if totals['failed'] > 0 or totals['timeout'] > 0:
        raise typer.Exit(1)
    
    raise typer.Exit(0)


def _run_parallel(
    items,
    source,
    search_path: Path,
    output_dir: Path,
    timeout: int,
    max_workers: int,
    quiet: bool,
    ci: bool = False,
):
    """Run items in parallel with async reporting."""
    import subprocess
    import sys
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from praisonai.suite_runner import RunResult, RunReport, SuiteReporter
    from datetime import timezone
    
    if ci:
        print("=" * 60)
        print("PraisonAI Batch Runner (Parallel Mode)")
        print("=" * 60)
        print(f"Path: {search_path}")
        print(f"Workers: {max_workers}")
        print(f"Timeout: {timeout}s")
        print(f"Scripts: {len(items)}")
        print(f"Reports: {output_dir}")
        print("")
        print("Running... Progress:")
        print("-" * 60)
    else:
        typer.echo("=" * 60)
        typer.echo("PraisonAI Batch Runner (Parallel Mode)")
        typer.echo("=" * 60)
        typer.echo(f"Path: {search_path}")
        typer.echo(f"Workers: {max_workers}")
        typer.echo(f"Timeout: {timeout}s")
        typer.echo(f"Scripts: {len(items)}")
        typer.echo(f"Reports: {output_dir}")
        typer.echo("")
        typer.echo("Running in background... Progress:")
        typer.echo("-" * 60)
    
    results = []
    completed = 0
    total = len(items)
    
    # Build environment
    import os
    env = os.environ.copy()
    pythonpath = source.get_pythonpath()
    if pythonpath:
        existing = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = os.pathsep.join(pythonpath + ([existing] if existing else []))
    
    def run_item(item):
        """Run a single item and return result."""
        nonlocal completed
        
        if not item.runnable:
            completed += 1
            return RunResult(
                item_id=item.item_id,
                suite="batch",
                group=item.group,
                source_path=item.source_path,
                status="skipped" if item.skip else "not_run",
                skip_reason=item.skip_reason,
                code_hash=item.code_hash,
            )
        
        start_time = datetime.now(timezone.utc)
        
        try:
            result = subprocess.run(
                [sys.executable, '-u', str(item.script_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                cwd=item.script_path.parent,
            )
            
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            status = "passed" if result.returncode == 0 else "failed"
            if item.xfail and result.returncode != 0:
                status = "xfail"
            
            error_message = None
            if result.returncode != 0 and result.stderr:
                lines = result.stderr.strip().split('\n')
                error_message = lines[-1][:200] if lines else None
            
            completed += 1
            
            # Progress indicator
            if ci:
                icon = "PASS" if status == "passed" else "FAIL" if status == "failed" else "XFAIL"
            else:
                icon = "✅" if status == "passed" else "❌" if status == "failed" else "⚠️"
            if not quiet:
                if ci:
                    print(f"  [{completed}/{total}] {icon} {item.display_name} ({duration:.2f}s)")
                else:
                    typer.echo(f"  [{completed}/{total}] {icon} {item.display_name} ({duration:.2f}s)")
            
            return RunResult(
                item_id=item.item_id,
                suite="batch",
                group=item.group,
                source_path=item.source_path,
                status=status,
                exit_code=result.returncode,
                duration_seconds=duration,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                error_message=error_message,
                stdout=result.stdout,
                stderr=result.stderr,
                code_hash=item.code_hash,
            )
            
        except subprocess.TimeoutExpired:
            completed += 1
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds()
            
            if not quiet:
                if ci:
                    print(f"  [{completed}/{total}] TIMEOUT {item.display_name} (timeout)")
                else:
                    typer.echo(f"  [{completed}/{total}] ⏱️ {item.display_name} (timeout)")
            
            return RunResult(
                item_id=item.item_id,
                suite="batch",
                group=item.group,
                source_path=item.source_path,
                status="timeout",
                duration_seconds=duration,
                error_message=f"Exceeded {timeout}s timeout",
                code_hash=item.code_hash,
            )
        except Exception as e:
            completed += 1
            if not quiet:
                if ci:
                    print(f"  [{completed}/{total}] FAIL {item.display_name} (error: {e})")
                else:
                    typer.echo(f"  [{completed}/{total}] ❌ {item.display_name} (error: {e})")
            
            return RunResult(
                item_id=item.item_id,
                suite="batch",
                group=item.group,
                source_path=item.source_path,
                status="failed",
                error_message=str(e),
                code_hash=item.code_hash,
            )
    
    # Run in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_item, item): item for item in items}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
    
    # Create report
    report = RunReport(
        results=results,
        suite="batch",
        source_path=search_path,
        groups_run=[],
    )
    
    # Generate reports
    output_dir.mkdir(parents=True, exist_ok=True)
    reporter = SuiteReporter(output_dir)
    reporter.save_logs(results)
    reporter.generate_json(report)
    reporter.generate_markdown(report)
    reporter.generate_csv(report)
    
    # Print summary
    totals = report.totals
    total_count = sum(totals.values())
    
    if ci:
        print("-" * 60)
        print("")
        print("SUMMARY")
        print("=" * 60)
        print(f"  PASSED:  {totals['passed']}")
        print(f"  FAILED:  {totals['failed']}")
        print(f"  SKIPPED: {totals['skipped']}")
        print(f"  TIMEOUT: {totals['timeout']}")
        print("  -----------------")
        print(f"  TOTAL:   {total_count}")
        print("=" * 60)
        print(f"Reports: {output_dir}")
    else:
        typer.echo("-" * 60)
        typer.echo("\nSUMMARY")
        typer.echo("=" * 60)
        typer.echo(f"  ✅ Passed:  {totals['passed']}")
        typer.echo(f"  ❌ Failed:  {totals['failed']}")
        typer.echo(f"  ⏭️ Skipped: {totals['skipped']}")
        typer.echo(f"  ⏱️ Timeout: {totals['timeout']}")
        typer.echo("  ─────────────────")
        typer.echo(f"  Total:     {total_count}")
        typer.echo("=" * 60)
        typer.echo(f"\n📁 Reports saved to: {output_dir}")
    
    # Exit code
    if totals['failed'] > 0 or totals['timeout'] > 0:
        raise typer.Exit(1)
    
    raise typer.Exit(0)


@app.command("list")
def batch_list(
    path: Optional[Path] = typer.Option(
        None,
        "--path", "-p",
        help="Path to search",
    ),
    recursive: bool = typer.Option(
        False,
        "--sub", "--recursive", "-r",
        help="Include subdirectories",
    ),
    depth: Optional[int] = typer.Option(
        None,
        "--depth", "-d",
        help="Maximum recursion depth",
    ),
    include_tests: bool = typer.Option(
        False,
        "--include-tests",
        help="Include test files",
    ),
    show_groups: bool = typer.Option(
        False,
        "--groups",
        help="Show available groups only",
    ),
):
    """
    List discovered PraisonAI scripts without running them.
    
    Examples:
        praisonai batch list
        praisonai batch list --sub
        praisonai batch list --groups
    """
    from praisonai.suite_runner import BatchSource
    
    search_path = Path(path).resolve() if path else Path.cwd().resolve()
    
    if not search_path.exists():
        typer.echo(f"❌ Path not found: {search_path}")
        raise typer.Exit(2)
    
    source = BatchSource(
        root=search_path,
        recursive=recursive,
        depth=depth,
        exclude_tests=not include_tests,
    )
    
    # Show groups only
    if show_groups:
        groups = source.get_groups()
        if not groups:
            typer.echo(f"No PraisonAI scripts found in {search_path}")
            return
        typer.echo(f"Available groups in {search_path}:\n")
        for g in groups:
            typer.echo(f"  - {g}")
        return
    
    items = source.discover()
    
    if not items:
        typer.echo(f"No PraisonAI scripts found in {search_path}")
        if not recursive:
            typer.echo("Tip: Use --sub to include subdirectories")
        return
    
    typer.echo(f"Found {len(items)} PraisonAI scripts in {search_path}\n")
    
    for idx, item in enumerate(items, 1):
        rel_path = item.source_path.relative_to(search_path)
        flags = []
        if item.skip:
            flags.append("skip")
        if item.uses_agent:
            flags.append("Agent")
        if item.uses_agents:
            flags.append("Agents")
        if item.uses_workflow:
            flags.append("Workflow")
        
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        typer.echo(f"  {idx:3}. [{item.group}] {rel_path}{flag_str}")


@app.command("stats")
def batch_stats(
    path: Optional[Path] = typer.Option(
        None,
        "--path", "-p",
        help="Path to search",
    ),
    recursive: bool = typer.Option(
        False,
        "--sub", "--recursive", "-r",
        help="Include subdirectories",
    ),
    depth: Optional[int] = typer.Option(
        None,
        "--depth", "-d",
        help="Maximum recursion depth",
    ),
    include_tests: bool = typer.Option(
        False,
        "--include-tests",
        help="Include test files",
    ),
):
    """
    Show statistics for PraisonAI scripts.
    
    Displays counts by group, runnable status, and agent-centric usage.
    
    Examples:
        praisonai batch stats
        praisonai batch stats --sub
    """
    from collections import Counter
    from praisonai.suite_runner import BatchSource
    
    search_path = Path(path).resolve() if path else Path.cwd().resolve()
    
    if not search_path.exists():
        typer.echo(f"❌ Path not found: {search_path}")
        raise typer.Exit(2)
    
    source = BatchSource(
        root=search_path,
        recursive=recursive,
        depth=depth,
        exclude_tests=not include_tests,
    )
    
    items = source.discover()
    
    if not items:
        typer.echo(f"No PraisonAI scripts found in {search_path}")
        return
    
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
    
    typer.echo("\n📊 Batch Execution Statistics")
    typer.echo(f"Path: {search_path}")
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


@app.command("report")
def batch_report(
    report_dir: Optional[Path] = typer.Option(
        None,
        "--dir", "-d",
        help="Specific report directory (default: latest)",
    ),
    format: str = typer.Option(
        "summary",
        "--format", "-f",
        help="Output format: summary, failures, full",
    ),
):
    """
    View the latest batch execution report.
    
    Examples:
        praisonai batch report
        praisonai batch report --format failures
        praisonai batch report --dir ~/Downloads/reports/batch/20240115_120000
    """
    import json
    
    # Find report directory
    if report_dir:
        target_dir = Path(report_dir)
    else:
        target_dir = _get_latest_report_dir()
    
    if not target_dir or not target_dir.exists():
        typer.echo("❌ No batch reports found.")
        typer.echo("   Run 'praisonai batch' first to generate a report.")
        raise typer.Exit(1)
    
    # Load JSON report
    json_path = target_dir / "report.json"
    if not json_path.exists():
        typer.echo(f"❌ Report not found: {json_path}")
        raise typer.Exit(1)
    
    report_data = json.loads(json_path.read_text())
    
    typer.echo(f"\n📊 Batch Report: {target_dir.name}")
    typer.echo("=" * 60)
    
    # Summary
    totals = report_data.get("totals", {})
    typer.echo(f"  ✅ Passed:  {totals.get('passed', 0)}")
    typer.echo(f"  ❌ Failed:  {totals.get('failed', 0)}")
    typer.echo(f"  ⏭️ Skipped: {totals.get('skipped', 0)}")
    typer.echo(f"  ⏱️ Timeout: {totals.get('timeout', 0)}")
    typer.echo("=" * 60)
    
    if format in ("failures", "full"):
        results = report_data.get("results", [])
        failures = [r for r in results if r.get("status") == "failed"]
        
        if failures:
            typer.echo("\n❌ FAILURES:")
            typer.echo("-" * 60)
            for r in failures:
                typer.echo(f"\n  {r.get('source_path', 'unknown')}")
                if r.get("error_message"):
                    typer.echo(f"    Error: {r['error_message'][:200]}")
    
    if format == "full":
        results = report_data.get("results", [])
        typer.echo("\n📋 ALL RESULTS:")
        typer.echo("-" * 60)
        for r in results:
            status = r.get("status", "unknown")
            icon = {"passed": "✅", "failed": "❌", "skipped": "⏭️", "timeout": "⏱️"}.get(status, "?")
            duration = r.get("duration_seconds", 0)
            typer.echo(f"  {icon} {r.get('source_path', 'unknown')} ({duration:.2f}s)")
    
    typer.echo(f"\n📁 Full report: {target_dir}")
