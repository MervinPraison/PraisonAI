"""
Docs command group for PraisonAI CLI.

Provides documentation commands.
"""

import typer

app = typer.Typer(help="Documentation management")


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
