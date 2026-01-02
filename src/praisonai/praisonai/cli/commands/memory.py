"""
Memory command group for PraisonAI CLI.

Provides memory management commands.
"""

import typer

app = typer.Typer(help="Memory management")


@app.command("show")
def memory_show(
    user_id: str = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of memories to show"),
):
    """Show stored memories."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['memory', 'show']
    if user_id:
        argv.extend(['--user-id', user_id])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("add")
def memory_add(
    content: str = typer.Argument(..., help="Memory content to add"),
    user_id: str = typer.Option(None, "--user-id", help="User ID for memory isolation"),
):
    """Add a memory."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['memory', 'add', content]
    if user_id:
        argv.extend(['--user-id', user_id])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Search query"),
    user_id: str = typer.Option(None, "--user-id", help="User ID for memory isolation"),
):
    """Search memories."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['memory', 'search', query]
    if user_id:
        argv.extend(['--user-id', user_id])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("clear")
def memory_clear(
    user_id: str = typer.Option(None, "--user-id", help="User ID for memory isolation"),
    force: bool = typer.Option(False, "--force", "-f", help="Force clear without confirmation"),
):
    """Clear all memories."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['memory', 'clear']
    if user_id:
        argv.extend(['--user-id', user_id])
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv
