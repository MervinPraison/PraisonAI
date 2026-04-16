"""
PraisonAI Langextract Commands.

CLI commands for rendering PraisonAI traces with langextract:
- `praisonai langextract view` - render existing JSONL to HTML
- `praisonai langextract render` - run workflow with langextract observability
"""

import typer
import webbrowser
from pathlib import Path
from typing import Optional

app = typer.Typer(name="langextract", help="Render PraisonAI traces with langextract.")


@app.command(name="view")
def view(
    jsonl_path: Path = typer.Argument(..., help="Path to annotated-documents JSONL"),
    output_html: Path = typer.Option("trace.html", "--output", "-o", help="Output HTML file path"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open HTML in browser"),
):
    """Render an existing annotated-documents JSONL to an interactive HTML."""
    try:
        import langextract as lx  # type: ignore
    except ImportError:
        typer.echo("Error: langextract is not installed. Install with: pip install 'praisonai[langextract]'", err=True)
        raise typer.Exit(1)

    if not jsonl_path.exists():
        typer.echo(f"Error: JSONL file not found: {jsonl_path}", err=True)
        raise typer.Exit(1)

    try:
        html = lx.visualize(str(jsonl_path))
        html_text = html.data if hasattr(html, "data") else html
        output_html.write_text(html_text, encoding="utf-8")
        typer.echo(f"✅ Wrote {output_html}")
        
        if not no_open:
            webbrowser.open(f"file://{output_html.resolve()}")
    except Exception as e:
        typer.echo(f"Error: Failed to render HTML: {e}", err=True)
        raise typer.Exit(1)


@app.command(name="render")
def render(
    yaml_path: Path = typer.Argument(..., help="PraisonAI YAML workflow"),
    output_html: Path = typer.Option("workflow.html", "--output", "-o", help="Output HTML file path"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open HTML in browser"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="API URL (if using remote API)"),
):
    """Run a workflow end-to-end with LangextractSink attached, then open the HTML."""
    try:
        from praisonai.observability import LangextractSink, LangextractSinkConfig
        from praisonaiagents.trace.protocol import TraceEmitter, set_default_emitter
        from praisonai import PraisonAI
    except ImportError as e:
        typer.echo(f"Error: Missing dependencies: {e}", err=True)
        raise typer.Exit(1)

    if not yaml_path.exists():
        typer.echo(f"Error: YAML file not found: {yaml_path}", err=True)
        raise typer.Exit(1)

    # Set up langextract observability
    config = LangextractSinkConfig(
        output_path=str(output_html),
        auto_open=not no_open,
    )
    sink = LangextractSink(config=config)
    
    # Set up trace emitter for the duration of the run
    emitter = TraceEmitter(sink=sink, enabled=True)
    set_default_emitter(emitter)
    
    try:
        # Run the workflow
        praison = PraisonAI(agent_file=str(yaml_path))
        if api_url:
            praison.api_url = api_url
        
        result = praison.main()
        typer.echo(result)
        
    except Exception as e:
        typer.echo(f"Error: Workflow failed: {e}", err=True)
        raise typer.Exit(1) from e
    finally:
        # Ensure sink is closed even if workflow fails
        sink.close()
    
    typer.echo(f"✅ Trace rendered: {output_html}")