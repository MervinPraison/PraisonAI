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
    # Try to find examples directory
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
    timeout: int = typer.Option(
        60,
        "--timeout", "-t",
        help="Per-example timeout in seconds",
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
    require_env: Optional[List[str]] = typer.Option(
        None,
        "--require-env",
        help="Required env vars (skip all if missing)",
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
        praisonai examples run --include "context/*" --exclude "*_wow.py"
        praisonai examples run --fail-fast --no-stream
    """
    # Lazy import to avoid loading at CLI startup
    from praisonai.cli.features.examples import ExamplesExecutor, ExampleResult
    
    # Resolve paths
    examples_path = path or _get_default_examples_path()
    output_dir = report_dir or _get_default_report_dir()
    
    if not examples_path.exists():
        typer.echo(f"❌ Examples path not found: {examples_path}")
        raise typer.Exit(2)
    
    # Create executor
    executor = ExamplesExecutor(
        path=examples_path,
        timeout=timeout,
        fail_fast=fail_fast,
        stream_output=not no_stream,
        include_patterns=list(include) if include else None,
        exclude_patterns=list(exclude) if exclude else None,
        require_env=list(require_env) if require_env else None,
        report_dir=output_dir,
        generate_json=not no_json,
        generate_md=not no_md,
    )
    
    # Status icons
    icons = {
        "passed": "✅",
        "failed": "❌",
        "skipped": "⏭️",
        "timeout": "⏱️",
        "xfail": "⚠️",
    }
    
    def on_example_start(path: Path, idx: int, total: int):
        if not quiet:
            typer.echo(f"\n[{idx}/{total}] Running: {path.name}")
    
    def on_example_end(result: ExampleResult, idx: int, total: int):
        icon = icons.get(result.status, "?")
        duration = f"{result.duration_seconds:.2f}s" if result.duration_seconds else ""
        
        if quiet:
            typer.echo(f"{icon} {result.path.name}")
        else:
            msg = f"  {icon} {result.status.upper()}"
            if duration:
                msg += f" ({duration})"
            if result.skip_reason:
                msg += f" - {result.skip_reason}"
            if result.error_summary and not no_stream:
                msg += f"\n     Error: {result.error_summary[:100]}"
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
        typer.echo(f"Reports: {output_dir}")
    
    # Run examples
    report = executor.run(
        on_example_start=on_example_start,
        on_example_end=on_example_end,
        on_output=on_output if not no_stream else None,
    )
    
    # Update report with CLI args
    report.cli_args = [
        f"--path={examples_path}",
        f"--timeout={timeout}",
    ]
    if fail_fast:
        report.cli_args.append("--fail-fast")
    if include:
        for p in include:
            report.cli_args.append(f"--include={p}")
    if exclude:
        for p in exclude:
            report.cli_args.append(f"--exclude={p}")
    
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
    show_metadata: bool = typer.Option(
        False,
        "--metadata", "-m",
        help="Show parsed metadata for each example",
    ),
):
    """
    List discovered examples without running them.
    
    Examples:
        praisonai examples list
        praisonai examples list --path ./examples --metadata
    """
    from praisonai.cli.features.examples import ExampleDiscovery, ExampleMetadata
    
    examples_path = path or _get_default_examples_path()
    
    if not examples_path.exists():
        typer.echo(f"❌ Examples path not found: {examples_path}")
        raise typer.Exit(2)
    
    discovery = ExampleDiscovery(
        examples_path,
        include_patterns=list(include) if include else None,
        exclude_patterns=list(exclude) if exclude else None,
    )
    
    examples = discovery.discover()
    
    typer.echo(f"Found {len(examples)} examples in {examples_path}\n")
    
    for idx, ex in enumerate(examples, 1):
        rel_path = ex.relative_to(examples_path)
        
        if show_metadata:
            meta = ExampleMetadata.from_file(ex)
            flags = []
            if meta.skip:
                flags.append("skip")
            if meta.timeout:
                flags.append(f"timeout={meta.timeout}")
            if meta.require_env:
                flags.append(f"env={','.join(meta.require_env)}")
            if meta.xfail:
                flags.append(f"xfail={meta.xfail}")
            if meta.is_interactive:
                flags.append("interactive")
            
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            typer.echo(f"  {idx:3}. {rel_path}{flag_str}")
        else:
            typer.echo(f"  {idx:3}. {rel_path}")


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
    from praisonai.cli.features.examples import ExampleMetadata
    
    if not example.exists():
        typer.echo(f"❌ Example not found: {example}")
        raise typer.Exit(2)
    
    meta = ExampleMetadata.from_file(example)
    
    typer.echo(f"Example: {example.name}")
    typer.echo(f"Path: {example}")
    typer.echo("")
    typer.echo("Metadata:")
    typer.echo(f"  Skip: {meta.skip}" if meta.skip else "  Skip: False")
    if meta.skip_reason:
        typer.echo(f"  Skip Reason: {meta.skip_reason}")
    typer.echo(f"  Timeout: {meta.timeout or 'default'}")
    typer.echo(f"  Required Env: {', '.join(meta.require_env) if meta.require_env else 'none'}")
    typer.echo(f"  XFail: {meta.xfail or 'no'}")
    typer.echo(f"  Interactive: {meta.is_interactive}")


if __name__ == "__main__":
    app()
