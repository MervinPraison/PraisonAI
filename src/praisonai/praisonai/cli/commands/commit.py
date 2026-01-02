"""
Commit command group for PraisonAI CLI.

Provides git commit commands with AI assistance.
"""

import typer

app = typer.Typer(help="AI-assisted git commits")


@app.callback(invoke_without_command=True)
def commit_main(
    ctx: typer.Context,
    message: str = typer.Option(None, "--message", "-m", help="Commit message (auto-generated if not provided)"),
    all_files: bool = typer.Option(False, "--all", "-a", help="Stage all changes"),
    push: bool = typer.Option(False, "--push", "-p", help="Push after commit"),
):
    """
    Create AI-assisted git commits.
    
    Examples:
        praisonai commit
        praisonai commit -m "Fix bug"
        praisonai commit --all --push
    """
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['commit']
    if message:
        argv.extend(['--message', message])
    if all_files:
        argv.append('--all')
    if push:
        argv.append('--push')
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
