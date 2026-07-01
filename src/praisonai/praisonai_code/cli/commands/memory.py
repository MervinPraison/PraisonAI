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


# Learn subcommand group
learn_app = typer.Typer(help="Continuous learning management")
app.add_typer(learn_app, name="learn")


@learn_app.command("status")
def learn_status(
    user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
    scope: str = typer.Option("private", "--scope", "-s", help="Scope (private/shared)"),
):
    """Show learning status and statistics."""
    from praisonaiagents.memory.learn import LearnManager
    from praisonaiagents.config.feature_configs import LearnConfig
    
    config = LearnConfig()
    manager = LearnManager(config=config, user_id=user_id)
    stats = manager.get_stats()
    
    typer.echo(f"\n📚 Learning Status for user: {user_id}")
    typer.echo(f"   Scope: {scope}")
    typer.echo("-" * 40)
    
    if not stats:
        typer.echo("No learning stores enabled.")
        return
    
    total = 0
    for store_name, count in stats.items():
        typer.echo(f"   {store_name}: {count} entries")
        total += count
    
    typer.echo("-" * 40)
    typer.echo(f"   Total: {total} entries")


@learn_app.command("show")
def learn_show(
    store: str = typer.Argument("all", help="Store to show (persona/insights/threads/patterns/decisions/feedback/improvements/all)"),
    user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
    limit: int = typer.Option(10, "--limit", "-l", help="Number of entries to show"),
):
    """Show learned entries."""
    from praisonaiagents.memory.learn import LearnManager
    from praisonaiagents.config.feature_configs import LearnConfig
    
    config = LearnConfig(
        persona=True,
        insights=True,
        thread=True,
        patterns=True,
        decisions=True,
        feedback=True,
        improvements=True,
    )
    manager = LearnManager(config=config, user_id=user_id)
    
    if store == "all":
        context = manager.get_learning_context(limit_per_store=limit)
        for store_name, entries in context.items():
            if entries:
                typer.echo(f"\n📁 {store_name.upper()}")
                typer.echo("-" * 40)
                for entry in entries:
                    typer.echo(f"  [{entry['id'][:20]}...] {entry['content'][:60]}...")
    else:
        context = manager.get_learning_context(limit_per_store=limit)
        if store in context:
            entries = context[store]
            typer.echo(f"\n📁 {store.upper()}")
            typer.echo("-" * 40)
            for entry in entries:
                typer.echo(f"  [{entry['id'][:20]}...] {entry['content']}")
        else:
            typer.echo(f"Store '{store}' not found or empty.")


@learn_app.command("add")
def learn_add(
    content: str = typer.Argument(..., help="Content to learn"),
    store: str = typer.Option("insights", "--store", "-s", help="Store type (persona/insights/patterns)"),
    user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
):
    """Add a learning entry."""
    from praisonaiagents.memory.learn import LearnManager
    from praisonaiagents.config.feature_configs import LearnConfig
    
    config = LearnConfig(
        persona=(store == "persona"),
        insights=(store == "insights"),
        patterns=(store == "patterns"),
        thread=(store == "threads"),
        decisions=(store == "decisions"),
        feedback=(store == "feedback"),
        improvements=(store == "improvements"),
    )
    manager = LearnManager(config=config, user_id=user_id)
    
    entry = None
    if store == "persona":
        entry = manager.capture_persona(content)
    elif store == "insights":
        entry = manager.capture_insight(content)
    elif store == "patterns":
        entry = manager.capture_pattern(content)
    elif store == "decisions":
        entry = manager.capture_decision(content)
    elif store == "feedback":
        entry = manager.capture_feedback(content)
    elif store == "improvements":
        entry = manager.capture_improvement(content)
    else:
        typer.echo(f"Unknown store: {store}")
        raise typer.Exit(1)
    
    if entry:
        typer.echo(f"✅ Added to {store}: {entry.id}")
    else:
        typer.echo(f"❌ Failed to add to {store}")


@learn_app.command("search")
def learn_search(
    query: str = typer.Argument(..., help="Search query"),
    user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results per store"),
):
    """Search across all learning stores."""
    from praisonaiagents.memory.learn import LearnManager
    from praisonaiagents.config.feature_configs import LearnConfig
    
    config = LearnConfig(
        persona=True,
        insights=True,
        thread=True,
        patterns=True,
        decisions=True,
        feedback=True,
        improvements=True,
    )
    manager = LearnManager(config=config, user_id=user_id)
    
    results = manager.search(query, limit=limit)
    
    if not results:
        typer.echo(f"No results found for: {query}")
        return
    
    typer.echo(f"\n🔍 Search results for: {query}")
    for store_name, entries in results.items():
        typer.echo(f"\n📁 {store_name.upper()}")
        typer.echo("-" * 40)
        for entry in entries:
            typer.echo(f"  {entry['content'][:80]}...")


@learn_app.command("clear")
def learn_clear(
    store: str = typer.Argument("all", help="Store to clear (or 'all')"),
    user_id: str = typer.Option("default", "--user-id", "-u", help="User ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Clear learning entries."""
    from praisonaiagents.memory.learn import LearnManager
    from praisonaiagents.config.feature_configs import LearnConfig
    
    if not force:
        confirm = typer.confirm(f"Clear {store} learning data for user {user_id}?")
        if not confirm:
            typer.echo("Cancelled.")
            return
    
    config = LearnConfig(
        persona=True,
        insights=True,
        thread=True,
        patterns=True,
        decisions=True,
        feedback=True,
        improvements=True,
    )
    manager = LearnManager(config=config, user_id=user_id)
    
    cleared = manager.clear_all()
    
    typer.echo("\n🗑️  Cleared learning data:")
    for store_name, count in cleared.items():
        typer.echo(f"   {store_name}: {count} entries")
