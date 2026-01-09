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
    return Path.cwd() / "reports" / "examples" / timestamp


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


if __name__ == "__main__":
    app()
