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
        Path("/Users/praison/PraisonAIDocs"),
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
    return Path.cwd() / "reports" / "docs" / timestamp


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
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast", "-x",
        help="Stop on first failure",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Extract only, don't execute",
    ),
    mode: str = typer.Option(
        "lenient",
        "--mode", "-m",
        help="Mode: 'lenient' or 'strict' (strict fails on not_run)",
    ),
    max_snippets: Optional[int] = typer.Option(
        None,
        "--max-snippets",
        help="Maximum snippets to process",
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
    Run Python code blocks from documentation files.
    
    Extracts code blocks from Mintlify docs, classifies them as runnable,
    executes them, and generates reports.
    
    Examples:
        praisonai docs run
        praisonai docs run --docs-path /path/to/docs --timeout 120
        praisonai docs run --dry-run --max-snippets 10
        praisonai docs run --include "quickstart*" --fail-fast
    """
    # Lazy import to avoid loading at CLI startup
    from praisonai.docs_runner.executor import DocsExecutor
    from praisonai.docs_runner.reporter import SnippetResult
    
    # Resolve paths
    docs = docs_path or _get_default_docs_path()
    output_dir = report_dir or _get_default_report_dir()
    
    if not docs.exists():
        typer.echo(f"❌ Docs path not found: {docs}")
        raise typer.Exit(2)
    
    # Parse languages
    lang_list = [lang.strip() for lang in languages.split(',') if lang.strip()]
    
    # Create executor
    executor = DocsExecutor(
        docs_path=docs,
        include_patterns=list(include) if include else None,
        exclude_patterns=list(exclude) if exclude else None,
        languages=lang_list,
        timeout=timeout,
        fail_fast=fail_fast,
        stream_output=not no_stream,
        dry_run=dry_run,
        mode=mode,
        max_snippets=max_snippets,
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
        "not_run": "📝",
    }
    
    def on_snippet_start(block, idx: int, total: int):
        if not quiet:
            doc_name = block.doc_path.name
            typer.echo(f"\n[{idx}/{total}] {doc_name} block {block.block_index}")
    
    def on_snippet_end(result: SnippetResult, idx: int, total: int):
        icon = icons.get(result.status, "?")
        duration = f"{result.duration_seconds:.2f}s" if result.duration_seconds else ""
        
        if quiet:
            typer.echo(f"{icon} {result.doc_path.name}:{result.block_index}")
        else:
            msg = f"  {icon} {result.status.upper()}"
            if duration:
                msg += f" ({duration})"
            if result.skip_reason:
                msg += f" - {result.skip_reason[:50]}"
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
        typer.echo("PraisonAI Docs Code Execution")
        typer.echo("=" * 60)
        typer.echo(f"Docs Path: {docs}")
        typer.echo(f"Timeout: {timeout}s")
        typer.echo(f"Mode: {mode}")
        if dry_run:
            typer.echo("Mode: DRY RUN (no execution)")
        typer.echo(f"Reports: {output_dir}")
    
    # Run
    report = executor.run(
        on_snippet_start=on_snippet_start,
        on_snippet_end=on_snippet_end,
        on_output=on_output if not no_stream else None,
    )
    
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
):
    """
    List discovered code blocks from documentation.
    
    Examples:
        praisonai docs list
        praisonai docs list --docs-path /path/to/docs --code
    """
    from praisonai.docs_runner.extractor import FenceExtractor
    from praisonai.docs_runner.classifier import RunnableClassifier
    
    docs = docs_path or _get_default_docs_path()
    
    if not docs.exists():
        typer.echo(f"❌ Docs path not found: {docs}")
        raise typer.Exit(2)
    
    # Parse languages
    lang_list = [lang.strip() for lang in languages.split(',') if lang.strip()]
    
    extractor = FenceExtractor(languages=lang_list)
    classifier = RunnableClassifier(target_languages=tuple(lang_list))
    
    blocks = extractor.extract_from_directory(
        docs,
        include_patterns=list(include) if include else None,
        exclude_patterns=list(exclude) if exclude else None,
    )
    
    # Filter to target languages
    blocks = [b for b in blocks if b.language in lang_list]
    
    typer.echo(f"Found {len(blocks)} code blocks in {docs}\n")
    
    for idx, block in enumerate(blocks, 1):
        rel_path = block.doc_path.relative_to(docs) if docs in block.doc_path.parents else block.doc_path
        classification = classifier.classify(block)
        
        status = "✅ Runnable" if classification.is_runnable else "📝 Partial"
        
        typer.echo(f"{idx:3}. {rel_path}:{block.line_start}-{block.line_end}")
        typer.echo(f"     {status} ({classification.reason})")
        
        if show_code:
            preview = block.code[:100].replace('\n', ' ')
            if len(block.code) > 100:
                preview += "..."
            typer.echo(f"     Code: {preview}")
        
        typer.echo()


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
