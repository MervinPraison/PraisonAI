"""
Docs command group for PraisonAI CLI.

Provides documentation commands including code execution validation.

Usage:
    praisonai docs run                    # Run all Python blocks from docs
    praisonai docs list                   # List discovered code blocks
    praisonai docs run --dry-run          # Extract only, no execution
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, List

import typer

app = typer.Typer(help="Documentation management and code validation")


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
        help="Show available groups only",
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
    from concurrent.futures import ProcessPoolExecutor, as_completed
    from praisonai.suite_runner import DocsSource, SuiteExecutor, RunResult
    
    docs = docs_path or _get_default_docs_path()
    output_dir = report_dir or _get_default_report_dir()
    
    if not docs.exists():
        typer.echo(f"❌ Docs path not found: {docs}")
        raise typer.Exit(2)
    
    # Get all groups
    source = DocsSource(root=docs)
    all_groups = sorted(source.get_groups())
    
    typer.echo(f"Found {len(all_groups)} groups to process")
    typer.echo(f"Mode: {'parallel' if parallel else 'sequential'}")
    typer.echo("=" * 60)
    
    # Track overall results
    overall_results = {
        'passed': 0, 'failed': 0, 'skipped': 0,
        'timeout': 0, 'not_run': 0, 'total': 0,
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
                'skipped': 0, 'timeout': 0, 'not_run': 0,
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
        # Parallel execution
        with ProcessPoolExecutor(max_workers=min(max_workers, len(all_groups))) as pool:
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
                        typer.echo(
                            f"✅ {group_name}: "
                            f"✅{summary['passed']} ❌{summary['failed']} "
                            f"⏭️{summary['skipped']} ⏱️{summary['timeout']} 📝{summary['not_run']}"
                        )
                except Exception as e:
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
    typer.echo("\n" + "=" * 80)
    typer.echo("FINAL REPORT - ALL GROUPS")
    typer.echo("=" * 80)
    
    typer.echo(f"\n{'Group':<20} {'Total':>8} {'Passed':>8} {'Failed':>8} {'Skip':>8} {'Timeout':>8} {'NotRun':>8}")
    typer.echo("-" * 80)
    
    for gs in sorted(group_summaries, key=lambda x: x['group']):
        typer.echo(
            f"{gs['group']:<20} {gs['total']:>8} {gs['passed']:>8} {gs['failed']:>8} "
            f"{gs['skipped']:>8} {gs['timeout']:>8} {gs['not_run']:>8}"
        )
    
    typer.echo("-" * 80)
    typer.echo(
        f"{'TOTAL':<20} {overall_results['total']:>8} {overall_results['passed']:>8} "
        f"{overall_results['failed']:>8} {overall_results['skipped']:>8} "
        f"{overall_results['timeout']:>8} {overall_results['not_run']:>8}"
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
    
    typer.echo(f"\n📁 Final summary saved to: {summary_path}")
    typer.echo(f"📁 Individual group reports in: {output_dir}")
    
    # Exit code
    if overall_results['failed'] > 0 or overall_results['timeout'] > 0:
        raise typer.Exit(1)
    raise typer.Exit(0)


@app.command("generate")
def docs_generate(
    source: str = typer.Argument(".", help="Source directory"),
    output: str = typer.Option("docs", "--output", "-o", help="Output directory"),
):
    """Generate documentation."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['docs', 'generate', source, '--output', output]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


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
