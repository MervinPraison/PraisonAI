"""
Docs command group for PraisonAI CLI.

Provides documentation commands including code execution validation.

Usage:
    praisonai docs run                    # Run all Python blocks from docs
    praisonai docs list                   # List discovered code blocks
    praisonai docs run --dry-run          # Extract only, no execution
    praisonai docs cli run-all            # Validate all CLI commands from docs
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer

app = typer.Typer(help="Documentation management and code validation")

# CLI subcommand group for validating CLI commands in documentation
cli_app = typer.Typer(help="Validate CLI commands from documentation")
app.add_typer(cli_app, name="cli")


def _get_default_docs_path() -> Path:
    """Get default docs path."""
    candidates = [
        Path.home() / "PraisonAIDocs" / "docs",
        Path("/Users/praison/PraisonAIDocs/docs"),
        Path.cwd() / "docs",
        Path(__file__).parent.parent.parent.parent.parent / "docs",
    ]
    
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    
    return Path.cwd()


def _get_default_report_dir() -> Path:
    """Get default report directory with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.home() / "Downloads" / "reports" / "docs" / timestamp


@app.command("run")
def docs_run(
    docs_path: Optional[Path] = typer.Option(
        None,
        "--docs-path", "-p",
        help="Path to documentation directory",
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
    folder: Optional[List[str]] = typer.Option(
        None,
        "--folder", "-f",
        help="Run only specific folders (nested paths like examples/agent-recipes), can be repeated",
    ),
    exclude_groups: Optional[List[str]] = typer.Option(
        ["js"],
        "--exclude-groups", "-xg",
        help="Exclude specific groups (default: js). Use --exclude-groups '' to include all",
    ),
    languages: str = typer.Option(
        "python",
        "--languages", "-l",
        help="Languages to execute (comma-separated)",
    ),
    timeout: int = typer.Option(
        60,
        "--timeout", "-t",
        help="Per-snippet timeout in seconds",
    ),
    max_snippets: Optional[int] = typer.Option(
        None,
        "--max-snippets",
        help="Maximum snippets to process",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast", "-x",
        help="Stop on first failure",
    ),
    mode: str = typer.Option(
        "lenient",
        "--mode", "-m",
        help="Mode: 'lenient' or 'strict' (strict fails on not_run)",
    ),
    no_stream: bool = typer.Option(
        False,
        "--no-stream",
        help="Don't stream output to terminal",
    ),
    report_dir: Optional[Path] = typer.Option(
        None,
        "--report-dir", "-r",
        help="Directory for reports (default: ./reports/docs/<timestamp>)",
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
    Run Python code blocks from documentation files.
    
    Extracts code blocks from Mintlify docs, classifies them as runnable,
    executes them, and generates reports (JSON, Markdown, CSV).
    
    Examples:
        praisonai docs run
        praisonai docs run --docs-path /path/to/docs --timeout 120
        praisonai docs run --group models --group tools --max-snippets 10
        praisonai docs run --include "quickstart*" --fail-fast
    """
    # Lazy import to avoid loading at CLI startup
    from praisonai.suite_runner import DocsSource, SuiteExecutor, RunResult
    
    # Resolve paths
    docs = docs_path or _get_default_docs_path()
    output_dir = report_dir or _get_default_report_dir()
    
    if not docs.exists():
        typer.echo(f"❌ Docs path not found: {docs}")
        raise typer.Exit(2)
    
    # Parse languages
    lang_list = [lang.strip() for lang in languages.split(',') if lang.strip()]
    
    # Create source
    source = DocsSource(
        root=docs,
        languages=lang_list,
        include_patterns=list(include) if include else None,
        exclude_patterns=list(exclude) if exclude else None,
        groups=list(group) if group else None,
        folders=list(folder) if folder else None,
        exclude_groups=list(exclude_groups) if exclude_groups and exclude_groups != [''] else None,
    )
    
    # Discover items
    items = source.discover()
    
    # Create executor
    executor = SuiteExecutor(
        suite="docs",
        source_path=docs,
        timeout=timeout,
        fail_fast=fail_fast,
        stream_output=not no_stream,
        max_items=max_snippets,
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
        "not_run": "📝",
        "xfail": "⚠️",
    }
    
    def on_item_start(item, idx: int, total: int):
        if not quiet:
            typer.echo(f"\n[{idx}/{total}] {item.display_name}")
    
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
                msg += f" - {result.skip_reason[:50]}"
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
        typer.echo("PraisonAI Docs Code Execution")
        typer.echo("=" * 60)
        typer.echo(f"Docs Path: {docs}")
        typer.echo(f"Timeout: {timeout}s")
        typer.echo(f"Mode: {mode}")
        if group:
            typer.echo(f"Groups: {', '.join(group)}")
        if folder:
            typer.echo(f"Folders: {', '.join(folder)}")
        typer.echo(f"Reports: {output_dir}")
        typer.echo(f"Items: {len(items)}")
    
    # Run
    report = executor.run(
        items=items,
        on_item_start=on_item_start,
        on_item_end=on_item_end,
        on_output=on_output if not no_stream else None,
    )
    
    # Update report with CLI args
    report.cli_args = [f"--docs-path={docs}", f"--timeout={timeout}"]
    if group:
        for g in group:
            report.cli_args.append(f"--group={g}")
    if folder:
        for f in folder:
            report.cli_args.append(f"--folder={f}")
    
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
        typer.echo(f"  📝 Not Run: {totals['not_run']}")
        typer.echo("  ─────────────────")
        typer.echo(f"  Total:     {total_count}")
        typer.echo("=" * 60)
        
        if output_dir.exists():
            typer.echo(f"\n📁 Reports saved to: {output_dir}")
    
    # Exit code
    if totals['failed'] > 0 or totals['timeout'] > 0:
        raise typer.Exit(1)
    
    if mode == "strict" and totals['not_run'] > 0:
        raise typer.Exit(1)
    
    raise typer.Exit(0)


@app.command("list")
def docs_list(
    docs_path: Optional[Path] = typer.Option(
        None,
        "--docs-path", "-p",
        help="Path to documentation directory",
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
    languages: str = typer.Option(
        "python",
        "--languages", "-l",
        help="Languages to show (comma-separated)",
    ),
    show_code: bool = typer.Option(
        False,
        "--code", "-c",
        help="Show code preview",
    ),
    show_groups: bool = typer.Option(
        False,
        "--groups",
        help="Show available groups only (top-level dirs)",
    ),
    show_folders: bool = typer.Option(
        False,
        "--folders",
        help="Show available folders (including nested paths)",
    ),
):
    """
    List discovered code blocks from documentation.
    
    Examples:
        praisonai docs list
        praisonai docs list --groups
        praisonai docs list --group models --code
    """
    from praisonai.suite_runner import DocsSource
    
    docs = docs_path or _get_default_docs_path()
    
    if not docs.exists():
        typer.echo(f"❌ Docs path not found: {docs}")
        raise typer.Exit(2)
    
    # Parse languages
    lang_list = [lang.strip() for lang in languages.split(',') if lang.strip()]
    
    source = DocsSource(
        root=docs,
        languages=lang_list,
        include_patterns=list(include) if include else None,
        exclude_patterns=list(exclude) if exclude else None,
        groups=list(group) if group else None,
    )
    
    # Show groups only
    if show_groups:
        groups = source.get_groups()
        typer.echo(f"Available groups in {docs}:\n")
        for g in groups:
            typer.echo(f"  - {g}")
        return
    
    # Show folders (including nested paths)
    if show_folders:
        folders = source.get_folders(max_depth=3)
        typer.echo(f"Available folders in {docs}:\n")
        for f in folders:
            typer.echo(f"  - {f}")
        typer.echo(f"\nTotal: {len(folders)} folders")
        return
    
    items = source.discover()
    
    typer.echo(f"Found {len(items)} code blocks in {docs}\n")
    
    for idx, item in enumerate(items, 1):
        rel_path = item.source_path.relative_to(docs) if docs in item.source_path.parents else item.source_path
        
        status = "✅ Runnable" if item.runnable else "📝 Partial"
        
        typer.echo(f"{idx:3}. [{item.group}] {rel_path}:{item.line_start}-{item.line_end}")
        typer.echo(f"     {status} ({item.runnable_decision})")
        
        if show_code:
            preview = item.code[:100].replace('\n', ' ')
            if len(item.code) > 100:
                preview += "..."
            typer.echo(f"     Code: {preview}")
        
        typer.echo()


@app.command("stats")
def docs_stats(
    docs_path: Optional[Path] = typer.Option(
        None,
        "--docs-path", "-p",
        help="Path to documentation directory",
    ),
    group: Optional[List[str]] = typer.Option(
        None,
        "--group", "-g",
        help="Filter by group (top-level dir)",
    ),
    languages: str = typer.Option(
        "python",
        "--languages", "-l",
        help="Languages to show (comma-separated)",
    ),
):
    """
    Show statistics for documentation code blocks.
    
    Displays counts by group, runnable status, and agent-centric usage.
    
    Examples:
        praisonai docs stats
        praisonai docs stats --group models --group tools
    """
    from collections import Counter
    from praisonai.suite_runner import DocsSource
    
    docs = docs_path or _get_default_docs_path()
    
    if not docs.exists():
        typer.echo(f"❌ Docs path not found: {docs}")
        raise typer.Exit(2)
    
    lang_list = [lang.strip() for lang in languages.split(',') if lang.strip()]
    
    source = DocsSource(
        root=docs,
        languages=lang_list,
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
    
    typer.echo("\n📊 Documentation Code Block Statistics")
    typer.echo(f"Path: {docs}")
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
def docs_run_all(
    docs_path: Optional[Path] = typer.Option(
        None,
        "--docs-path", "-p",
        help="Path to documentation directory",
    ),
    timeout: int = typer.Option(
        60,
        "--timeout", "-t",
        help="Per-snippet timeout in seconds",
    ),
    report_dir: Optional[Path] = typer.Option(
        None,
        "--report-dir", "-r",
        help="Directory for reports (default: ~/Downloads/reports/docs/<timestamp>)",
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
    Run all documentation code blocks group-by-group.
    
    Executes all groups and generates a comprehensive report.
    Uses parallel execution by default for faster results.
    
    Examples:
        praisonai docs run-all
        praisonai docs run-all --sequential
        praisonai docs run-all --workers 8 --timeout 120
    """
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from praisonai.suite_runner import DocsSource, SuiteExecutor, RunResult
    
    docs = docs_path or _get_default_docs_path()
    output_dir = report_dir or _get_default_report_dir()
    
    if not docs.exists():
        typer.echo(f"❌ Docs path not found: {docs}")
        raise typer.Exit(2)
    
    # Get all groups
    source = DocsSource(root=docs)
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
        group_source = DocsSource(root=docs, groups=[group_name])
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
            suite='docs',
            source_path=docs,
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
                                f"PASS:{summary.get('passed', 0)} FAIL:{summary.get('failed', 0)} "
                                f"SKIP:{summary.get('skipped', 0)} TIMEOUT:{summary.get('timeout', 0)} XFAIL:{summary.get('xfail', 0)}"
                            )
                        else:
                            typer.echo(
                                f"✅ {group_name}: "
                                f"✅{summary.get('passed', 0)} ❌{summary.get('failed', 0)} "
                                f"⏭️{summary.get('skipped', 0)} ⏱️{summary.get('timeout', 0)} ⚠️{summary.get('xfail', 0)}"
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
            
            group_source = DocsSource(root=docs, groups=[group_name])
            items = group_source.discover()
            
            if not items:
                if not quiet:
                    typer.echo("  No items found, skipping")
                group_summaries.append({
                    'group': group_name,
                    'total': 0, 'passed': 0, 'failed': 0,
                    'skipped': 0, 'timeout': 0, 'not_run': 0,
                })
                continue
            
            group_report_dir = output_dir / group_name
            group_report_dir.mkdir(parents=True, exist_ok=True)
            
            executor = SuiteExecutor(
                suite='docs',
                source_path=docs,
                report_dir=group_report_dir,
                timeout=timeout,
                stream_output=False,
                generate_json=True,
                generate_md=True,
                generate_csv=True,
                groups=[group_name],
            )
            
            icons = {'passed': '✅', 'failed': '❌', 'skipped': '⏭️', 'timeout': '⏱️', 'not_run': '📝'}
            
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
                    f"⏭️{totals['skipped']} ⏱️{totals['timeout']} 📝{totals['not_run']}"
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
                f"{gs['group']:<20} {gs.get('total', 0):>8} {gs.get('passed', 0):>8} {gs.get('failed', 0):>8} "
                f"{gs.get('skipped', 0):>8} {gs.get('timeout', 0):>8} {gs.get('xfail', 0):>8}"
            )
        print("-" * 80)
        print(
            f"{'TOTAL':<20} {overall_results.get('total', 0):>8} {overall_results.get('passed', 0):>8} "
            f"{overall_results.get('failed', 0):>8} {overall_results.get('skipped', 0):>8} "
            f"{overall_results.get('timeout', 0):>8} {overall_results.get('xfail', 0):>8}"
        )
    else:
        typer.echo("\n" + "=" * 80)
        typer.echo("FINAL REPORT - ALL GROUPS")
        typer.echo("=" * 80)
        typer.echo(f"\n{'Group':<20} {'Total':>8} {'Passed':>8} {'Failed':>8} {'Skip':>8} {'Timeout':>8} {'XFail':>8}")
        typer.echo("-" * 80)
        for gs in sorted(group_summaries, key=lambda x: x['group']):
            typer.echo(
                f"{gs['group']:<20} {gs.get('total', 0):>8} {gs.get('passed', 0):>8} {gs.get('failed', 0):>8} "
                f"{gs.get('skipped', 0):>8} {gs.get('timeout', 0):>8} {gs.get('xfail', 0):>8}"
            )
        typer.echo("-" * 80)
        typer.echo(
            f"{'TOTAL':<20} {overall_results.get('total', 0):>8} {overall_results.get('passed', 0):>8} "
            f"{overall_results.get('failed', 0):>8} {overall_results.get('skipped', 0):>8} "
            f"{overall_results.get('timeout', 0):>8} {overall_results.get('xfail', 0):>8}"
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
    
    # Generate consolidated reports (report.md, report.csv, report.json at root level)
    from praisonai.suite_runner import RunReport, RunResult, SuiteReporter
    
    all_results = []
    for group_name in all_groups:
        group_report_path = output_dir / group_name / 'report.json'
        if group_report_path.exists():
            try:
                with open(group_report_path, 'r') as f:
                    group_data = json.load(f)
                
                # Parse results from group report
                for r in group_data.get('results', []):
                    result = RunResult(
                        item_id=r.get('item_id', ''),
                        suite=r.get('suite', 'docs'),
                        group=r.get('group', group_name),
                        source_path=Path(r.get('source_path', '')),
                        status=r.get('status', 'not_run'),
                        exit_code=r.get('exit_code'),
                        duration_seconds=r.get('duration_seconds'),
                        start_time=r.get('start_time'),
                        end_time=r.get('end_time'),
                        error_message=r.get('error_message'),
                        error_type=r.get('error_type'),
                        skip_reason=r.get('skip_reason'),
                        runnable_decision=r.get('runnable_decision'),
                        code_hash=r.get('code_hash'),
                        block_index=r.get('block_index'),
                        line_start=r.get('line_start'),
                        line_end=r.get('line_end'),
                        language=r.get('language'),
                    )
                    all_results.append(result)
            except (json.JSONDecodeError, KeyError) as e:
                if not quiet:
                    if ci:
                        print(f"Warning: Could not parse {group_report_path}: {e}")
                    else:
                        typer.echo(f"⚠️ Could not parse {group_report_path}: {e}")
    
    # Create consolidated report
    if all_results:
        consolidated_report = RunReport(
            results=all_results,
            suite='docs',
            source_path=docs,
            groups_run=all_groups,
        )
        
        # Generate consolidated reports at root level
        reporter = SuiteReporter(output_dir)
        reporter.generate_all(consolidated_report)
        
        if ci:
            print(f"Consolidated report.json: {output_dir / 'report.json'}")
            print(f"Consolidated report.md: {output_dir / 'report.md'}")
            print(f"Consolidated report.csv: {output_dir / 'report.csv'}")
        else:
            typer.echo(f"📄 Consolidated report.json: {output_dir / 'report.json'}")
            typer.echo(f"📄 Consolidated report.md: {output_dir / 'report.md'}")
            typer.echo(f"📄 Consolidated report.csv: {output_dir / 'report.csv'}")
    
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


@app.command("generate")
def docs_generate(
    package: Optional[Path] = typer.Option(
        None,
        "--package", "-p",
        help="Path to praisonaiagents package (default: auto-detect)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Output directory for MDX files (default: ~/PraisonAIDocs/docs/sdk/reference/praisonaiagents)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview without writing files",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing files",
    ),
    module: Optional[str] = typer.Option(
        None,
        "--module", "-m",
        help="Generate docs for specific module only",
    ),
    update_nav: bool = typer.Option(
        False,
        "--update-nav",
        help="Update docs.json navigation",
    ),
):
    """
    Generate SDK reference documentation from Python source code.
    
    Parses praisonaiagents package using griffe and generates Mintlify-compatible
    MDX documentation for all public symbols in _LAZY_IMPORTS.
    
    Examples:
        praisonai docs generate                    # Generate all reference docs
        praisonai docs generate --dry-run          # Preview without writing
        praisonai docs generate --module agent     # Generate only agent module
        praisonai docs generate --update-nav       # Also update docs.json
    """
    import subprocess
    import time
    
    start_time = time.time()
    
    # Default paths
    default_package = Path("/Users/praison/praisonai-package/src/praisonai-agents/praisonaiagents")
    default_output = Path("/Users/praison/PraisonAIDocs/docs/sdk/reference/praisonaiagents")
    generator_script = Path("/Users/praison/PraisonAI-tools/scripts/generate-sdk-docs.py")
    
    pkg_path = package or default_package
    out_path = output or default_output
    
    # Validate paths
    if not pkg_path.exists():
        typer.echo(f"❌ Package path not found: {pkg_path}")
        raise typer.Exit(2)
    
    if not generator_script.exists():
        typer.echo(f"❌ Generator script not found: {generator_script}")
        raise typer.Exit(2)
    
    typer.echo("=" * 60)
    typer.echo("PraisonAI SDK Documentation Generator")
    typer.echo("=" * 60)
    typer.echo(f"Package: {pkg_path}")
    typer.echo(f"Output: {out_path}")
    typer.echo(f"Dry run: {dry_run}")
    if module:
        typer.echo(f"Module filter: {module}")
    typer.echo()
    
    # Build command (use sys.executable to ensure same Python environment)
    import sys as _sys
    cmd = [
        _sys.executable,
        str(generator_script),
        "--package", str(pkg_path),
        "--output", str(out_path),
    ]
    
    if dry_run:
        cmd.append("--dry-run")
    if force:
        cmd.append("--force")
    if module:
        cmd.extend(["--module", module])
    if update_nav:
        cmd.append("--update-nav")
    
    # Run generator
    try:
        result = subprocess.run(
            cmd,
            capture_output=False,
            text=True,
            timeout=120,
        )
        
        elapsed = time.time() - start_time
        typer.echo(f"\nTotal time: {elapsed:.2f}s")
        
        if elapsed > 60:
            typer.echo("⚠️ Warning: Generation took longer than 60s target")
        
        raise typer.Exit(result.returncode)
        
    except subprocess.TimeoutExpired:
        typer.echo("❌ Generation timed out after 120s")
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo("❌ Python3 not found")
        raise typer.Exit(1)


@app.command("serve")
def docs_serve(
    port: int = typer.Option(8000, "--port", "-p", help="Port to serve on"),
):
    """Serve documentation locally."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['docs', 'serve', '--port', str(port)]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("report")
def docs_report(
    report_dir: Optional[Path] = typer.Argument(
        None,
        help="Report directory path (default: auto-detect latest)",
    ),
    base_dir: Optional[Path] = typer.Option(
        None,
        "--base-dir", "-b",
        help="Base reports directory (default: ~/Downloads/reports/docs)",
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
        praisonai docs report                    # View latest report
        praisonai docs report ./my-report        # View specific report
        praisonai docs report --wide --limit 0   # Full details
        praisonai docs report --match failed     # Only failures
        praisonai docs report --format json      # JSON output
    """
    # Lazy import to avoid loading at CLI startup
    from praisonai.suite_runner.report_viewer import view_report
    
    output, exit_code = view_report(
        report_dir=report_dir,
        suite="docs",
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


@app.command("api-md")
def docs_api_md(
    write: bool = typer.Option(
        True,
        "--write", "-w",
        help="Write api.md file (default)",
    ),
    check: bool = typer.Option(
        False,
        "--check", "-c",
        help="Check if api.md is up to date (exit 1 if not)",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout", "-s",
        help="Print to stdout instead of writing file",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Output file path (default: repo_root/api.md)",
    ),
):
    """
    Generate or check the api.md API reference file.
    
    This command generates a comprehensive API reference document
    covering all public exports from praisonaiagents, praisonai, CLI, and TypeScript.
    
    Examples:
        praisonai docs api-md              # Generate api.md
        praisonai docs api-md --check      # Check if api.md is up to date
        praisonai docs api-md --stdout     # Print to stdout
    """
    from praisonai._dev.api_md import generate_api_md
    
    exit_code = generate_api_md(
        output_path=output,
        check=check,
        stdout=stdout
    )
    raise typer.Exit(exit_code)


# =============================================================================
# CLI Subcommand Group - Validate CLI commands from documentation
# =============================================================================

def _get_default_cli_report_dir() -> Path:
    """Get default report directory for CLI validation."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.home() / "Downloads" / "reports" / "docs-cli" / timestamp


@cli_app.command("run-all")
def cli_run_all(
    docs_path: Optional[Path] = typer.Option(
        None,
        "--docs-path", "-p",
        help="Path to documentation directory (default: ~/PraisonAIDocs/docs/cli)",
    ),
    timeout: int = typer.Option(
        10,
        "--timeout", "-t",
        help="Per-command timeout in seconds",
    ),
    report_dir: Optional[Path] = typer.Option(
        None,
        "--report-dir", "-r",
        help="Directory for reports (default: ~/Downloads/reports/docs-cli/<timestamp>)",
    ),
    parallel: bool = typer.Option(
        True,
        "--parallel/--sequential",
        help="Run commands in parallel (default: parallel)",
    ),
    max_workers: int = typer.Option(
        4,
        "--workers", "-w",
        help="Max parallel workers (default: 4)",
    ),
    max_items: Optional[int] = typer.Option(
        None,
        "--max-items",
        help="Maximum commands to run",
    ),
    group: Optional[List[str]] = typer.Option(
        None,
        "--group", "-g",
        help="Run only specific groups (can be repeated)",
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
    Validate all CLI commands from documentation.
    
    Discovers praisonai CLI commands in bash code blocks and validates
    them by running with --help to ensure they exist and work.
    
    Examples:
        praisonai docs cli run-all
        praisonai docs cli run-all --max-items 10
        praisonai docs cli run-all --group cli --workers 8
        praisonai docs cli run-all --ci --timeout 5
    """
    import subprocess
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from praisonai.suite_runner import CLIDocsSource, RunResult, RunReport, SuiteReporter
    
    # Resolve paths
    if docs_path:
        docs = Path(docs_path).resolve()
    else:
        # Default to CLI docs directory
        candidates = [
            Path.home() / "PraisonAIDocs" / "docs" / "cli",
            Path("/Users/praison/PraisonAIDocs/docs/cli"),
            Path.cwd() / "docs" / "cli",
        ]
        docs = None
        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                docs = candidate
                break
        if not docs:
            docs = Path.cwd()
    
    output_dir = report_dir or _get_default_cli_report_dir()
    
    if not docs.exists():
        if ci:
            print(f"ERROR: Docs path not found: {docs}")
        else:
            typer.echo(f"❌ Docs path not found: {docs}")
        raise typer.Exit(2)
    
    # Discover CLI commands
    source = CLIDocsSource(
        root=docs,
        groups=group,
        help_only=True,
    )
    
    items = source.discover()
    
    if max_items:
        items = items[:max_items]
    
    if not items:
        if ci:
            print("No CLI commands found in documentation")
        else:
            typer.echo("⚠️ No CLI commands found in documentation")
        raise typer.Exit(0)
    
    # Get groups for reporting
    all_groups = sorted(set(item.group for item in items))
    
    # Header
    if ci:
        print("=" * 60)
        print("PraisonAI CLI Docs Validator")
        print("=" * 60)
        print(f"Docs path: {docs}")
        print(f"Commands: {len(items)}")
        print(f"Groups: {len(all_groups)}")
        print(f"Mode: {'parallel' if parallel else 'sequential'}")
        print(f"Workers: {max_workers}")
        print(f"Timeout: {timeout}s")
        print("=" * 60)
    else:
        typer.echo(f"📚 Docs path: {docs}")
        typer.echo(f"🔍 Found {len(items)} CLI commands in {len(all_groups)} groups")
        typer.echo(f"⚙️ Mode: {'parallel' if parallel else 'sequential'}, Workers: {max_workers}")
        typer.echo("=" * 60)
    
    # Run CLI commands
    results = []
    
    def run_cli_command(item) -> RunResult:
        """Run a single CLI command with --help."""
        import time
        start_time = time.time()
        
        # Get the test command (stored in title field, or add --help)
        test_cmd = item.title or (item.code + ' --help')
        
        if item.skip:
            return RunResult(
                item_id=item.item_id,
                suite='cli-docs',
                group=item.group,
                source_path=item.source_path,
                status='skipped',
                skip_reason=item.skip_reason,
                code_hash=item.code_hash,
            )
        
        try:
            result = subprocess.run(
                test_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            
            duration = time.time() - start_time
            
            if result.returncode == 0:
                return RunResult(
                    item_id=item.item_id,
                    suite='cli-docs',
                    group=item.group,
                    source_path=item.source_path,
                    status='passed',
                    exit_code=result.returncode,
                    duration_seconds=duration,
                    stdout=result.stdout[:1000] if result.stdout else None,
                    code_hash=item.code_hash,
                )
            else:
                return RunResult(
                    item_id=item.item_id,
                    suite='cli-docs',
                    group=item.group,
                    source_path=item.source_path,
                    status='failed',
                    exit_code=result.returncode,
                    duration_seconds=duration,
                    error_message=result.stderr[:500] if result.stderr else f"Exit code: {result.returncode}",
                    stdout=result.stdout[:500] if result.stdout else None,
                    code_hash=item.code_hash,
                )
        except subprocess.TimeoutExpired:
            return RunResult(
                item_id=item.item_id,
                suite='cli-docs',
                group=item.group,
                source_path=item.source_path,
                status='timeout',
                duration_seconds=timeout,
                error_message=f"Command timed out after {timeout}s",
                code_hash=item.code_hash,
            )
        except Exception as e:
            return RunResult(
                item_id=item.item_id,
                suite='cli-docs',
                group=item.group,
                source_path=item.source_path,
                status='failed',
                error_message=str(e),
                code_hash=item.code_hash,
            )
    
    # Execute commands
    if parallel and len(items) > 1:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
            futures = {pool.submit(run_cli_command, item): item for item in items}
            
            for i, future in enumerate(as_completed(futures), 1):
                item = futures[future]
                result = future.result()
                results.append(result)
                
                if not quiet:
                    icon = {'passed': '✅', 'failed': '❌', 'skipped': '⏭️', 'timeout': '⏱️'}.get(result.status, '❓')
                    if ci:
                        print(f"[{i}/{len(items)}] {result.status.upper()} {item.code[:60]}...")
                    else:
                        typer.echo(f"[{i}/{len(items)}] {icon} {item.code[:60]}...")
    else:
        for i, item in enumerate(items, 1):
            if not quiet:
                if ci:
                    print(f"[{i}/{len(items)}] Running: {item.code[:60]}...")
                else:
                    typer.echo(f"[{i}/{len(items)}] 🔄 {item.code[:60]}...")
            
            result = run_cli_command(item)
            results.append(result)
            
            if not quiet:
                icon = {'passed': '✅', 'failed': '❌', 'skipped': '⏭️', 'timeout': '⏱️'}.get(result.status, '❓')
                if ci:
                    print(f"  {result.status.upper()}")
                else:
                    typer.echo(f"  {icon} {result.status}")
    
    # Create report
    report = RunReport(
        results=results,
        suite='cli-docs',
        source_path=docs,
        groups_run=all_groups,
    )
    
    # Generate reports
    output_dir.mkdir(parents=True, exist_ok=True)
    reporter = SuiteReporter(output_dir)
    reporter.save_logs(results)
    json_path = reporter.generate_json(report)
    md_path = reporter.generate_markdown(report)
    csv_path = reporter.generate_csv(report)
    
    # Summary
    totals = report.totals
    
    if ci:
        print("")
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  PASSED:  {totals.get('passed', 0)}")
        print(f"  FAILED:  {totals.get('failed', 0)}")
        print(f"  SKIPPED: {totals.get('skipped', 0)}")
        print(f"  TIMEOUT: {totals.get('timeout', 0)}")
        print("  -----------------")
        print(f"  TOTAL:   {totals.get('total', 0)}")
        print("=" * 60)
        print(f"Reports: {output_dir}")
    else:
        typer.echo("")
        typer.echo("=" * 60)
        typer.echo("SUMMARY")
        typer.echo("=" * 60)
        typer.echo(f"  ✅ Passed:  {totals.get('passed', 0)}")
        typer.echo(f"  ❌ Failed:  {totals.get('failed', 0)}")
        typer.echo(f"  ⏭️ Skipped: {totals.get('skipped', 0)}")
        typer.echo(f"  ⏱️ Timeout: {totals.get('timeout', 0)}")
        typer.echo("  ─────────────────")
        typer.echo(f"  Total:     {totals.get('total', 0)}")
        typer.echo("=" * 60)
        typer.echo(f"\n📄 JSON report: {json_path}")
        typer.echo(f"📄 Markdown report: {md_path}")
        typer.echo(f"📄 CSV report: {csv_path}")
        typer.echo(f"📁 Reports saved to: {output_dir}")
    
    # Exit code
    if totals.get('failed', 0) > 0 or totals.get('timeout', 0) > 0:
        raise typer.Exit(1)
    raise typer.Exit(0)


@cli_app.command("list")
def cli_list(
    docs_path: Optional[Path] = typer.Option(
        None,
        "--docs-path", "-p",
        help="Path to documentation directory",
    ),
    group: Optional[List[str]] = typer.Option(
        None,
        "--group", "-g",
        help="Filter by group",
    ),
    runnable_only: bool = typer.Option(
        False,
        "--runnable",
        help="Show only runnable commands",
    ),
    show_groups: bool = typer.Option(
        False,
        "--groups",
        help="Show available groups only",
    ),
):
    """
    List discovered CLI commands from documentation.
    
    Examples:
        praisonai docs cli list
        praisonai docs cli list --groups
        praisonai docs cli list --runnable
    """
    from praisonai.suite_runner import CLIDocsSource
    
    # Resolve path
    if docs_path:
        docs = Path(docs_path).resolve()
    else:
        candidates = [
            Path.home() / "PraisonAIDocs" / "docs" / "cli",
            Path("/Users/praison/PraisonAIDocs/docs/cli"),
        ]
        docs = None
        for candidate in candidates:
            if candidate.exists():
                docs = candidate
                break
        if not docs:
            docs = Path.cwd()
    
    source = CLIDocsSource(root=docs, groups=group)
    
    if show_groups:
        groups = source.get_groups()
        typer.echo(f"Available groups ({len(groups)}):")
        for g in groups:
            typer.echo(f"  - {g}")
        return
    
    items = source.discover()
    
    if runnable_only:
        items = [i for i in items if i.runnable]
    
    typer.echo(f"Found {len(items)} CLI commands:")
    typer.echo("")
    
    for item in items:
        status = "✅" if item.runnable else "⏭️"
        typer.echo(f"{status} [{item.group}] {item.code[:70]}...")
        if not item.runnable:
            typer.echo(f"   Skip: {item.runnable_decision}")


@cli_app.command("stats")
def cli_stats(
    docs_path: Optional[Path] = typer.Option(
        None,
        "--docs-path", "-p",
        help="Path to documentation directory",
    ),
):
    """
    Show statistics for CLI commands in documentation.
    
    Examples:
        praisonai docs cli stats
    """
    from praisonai.suite_runner import CLIDocsSource
    
    # Resolve path
    if docs_path:
        docs = Path(docs_path).resolve()
    else:
        candidates = [
            Path.home() / "PraisonAIDocs" / "docs" / "cli",
            Path("/Users/praison/PraisonAIDocs/docs/cli"),
        ]
        docs = None
        for candidate in candidates:
            if candidate.exists():
                docs = candidate
                break
        if not docs:
            docs = Path.cwd()
    
    source = CLIDocsSource(root=docs)
    stats = source.get_stats()
    
    typer.echo("CLI Commands Statistics")
    typer.echo("=" * 40)
    typer.echo(f"Total commands:    {stats['total']}")
    typer.echo(f"Runnable:          {stats['runnable']}")
    typer.echo(f"Skipped:           {stats['skipped']}")
    typer.echo("")
    typer.echo("By Group:")
    typer.echo("-" * 40)
    
    for group_name, group_stats in sorted(stats['by_group'].items()):
        typer.echo(f"  {group_name:<20} {group_stats['runnable']:>4}/{group_stats['total']:<4} runnable")


@cli_app.command("report")
def cli_report(
    report_dir: Optional[Path] = typer.Argument(
        None,
        help="Report directory path (default: auto-detect latest)",
    ),
    base_dir: Optional[Path] = typer.Option(
        None,
        "--base-dir", "-b",
        help="Base directory for auto-detection",
    ),
    limit: int = typer.Option(
        20,
        "--limit", "-n",
        help="Max items to show (0 = unlimited)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format", "-f",
        help="Output format: table or json",
    ),
):
    """
    View CLI validation report.
    
    Examples:
        praisonai docs cli report
        praisonai docs cli report ./my-report
        praisonai docs cli report --format json
    """
    from praisonai.suite_runner.report_viewer import view_report
    
    output, exit_code = view_report(
        report_dir=report_dir,
        suite="docs-cli",
        base_dir=base_dir or (Path.home() / "Downloads" / "reports" / "docs-cli"),
        limit=limit,
        output_format=output_format,
    )
    
    typer.echo(output)
    raise typer.Exit(exit_code)
