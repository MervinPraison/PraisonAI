"""
Skills command group for PraisonAI CLI.

Provides skill management commands.
"""

import typer

app = typer.Typer(help="Skill management")


@app.command("list")
def skills_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List available skills."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['skills', 'list']
    if verbose:
        argv.append('--verbose')
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("validate")
def skills_validate(
    path: str = typer.Argument(..., help="Skill directory path"),
):
    """Validate a skill."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['skills', 'validate', path]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("create")
def skills_create(
    name: str = typer.Argument(..., help="Skill name"),
):
    """Create a new skill."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['skills', 'create', name]
    
    original_argv = sys.argv
    sys.argv = ['praisonai'] + argv
    
    try:
        praison = PraisonAI()
        praison.main()
    except SystemExit:
        pass
    finally:
        sys.argv = original_argv


@app.command("install")
def skills_install(
    source: str = typer.Argument(..., help="Skill source (path or URL)"),
):
    """Install a skill."""
    from praisonai.cli.main import PraisonAI
    import sys
    
    argv = ['skills', 'install', source]
    
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
def skills_search(
    query: str = typer.Argument(..., help="Search query"),
    skill_dirs: str = typer.Option(None, "--dirs", "-d", help="Comma-separated skill directories"),
):
    """Search skills by name, description, or content."""
    try:
        from praisonaiagents.skills import discover_skills
        import re
        
        dirs = skill_dirs.split(",") if skill_dirs else None
        skills = discover_skills(dirs, include_defaults=True)
        
        pattern = re.compile(query, re.IGNORECASE)
        matches = []
        
        for skill in skills:
            # Search in name and description
            if pattern.search(skill.name) or pattern.search(skill.description):
                matches.append(skill)
                continue
            
            # Search in SKILL.md content if path available
            if skill.path:
                skill_md = skill.path / "SKILL.md"
                if skill_md.exists():
                    content = skill_md.read_text()
                    if pattern.search(content):
                        matches.append(skill)
        
        if not matches:
            typer.echo(f"No skills found matching: {query}")
            return
        
        from rich.console import Console
        from rich.table import Table
        
        console = Console()
        table = Table(title=f"Skills matching '{query}' ({len(matches)} found)")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("Path", style="dim")
        
        for skill in matches:
            table.add_row(
                skill.name,
                skill.description[:60] + "..." if len(skill.description) > 60 else skill.description,
                str(skill.path) if skill.path else "-",
            )
        
        console.print(table)
        
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("info")
def skills_info(
    name: str = typer.Argument(..., help="Skill name or path"),
):
    """Show detailed information about a skill."""
    try:
        from praisonaiagents.skills import discover_skills, SkillLoader
        from pathlib import Path
        
        # Try as path first
        path = Path(name).expanduser()
        if path.exists() and path.is_dir():
            loader = SkillLoader()
            skill = loader.load_metadata(str(path))
            if skill:
                loader.activate(skill)
        else:
            # Search by name
            skills = discover_skills(include_defaults=True)
            skill = None
            for s in skills:
                if s.name == name:
                    loader = SkillLoader()
                    skill = loader.load_metadata(str(s.path))
                    if skill:
                        loader.activate(skill)
                    break
        
        if not skill:
            typer.echo(f"Skill not found: {name}", err=True)
            raise typer.Exit(1)
        
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        
        console = Console()
        
        # Show metadata
        console.print(f"\n[bold cyan]{skill.properties.name}[/bold cyan]")
        console.print(f"[dim]{skill.properties.description}[/dim]\n")
        
        if skill.properties.license:
            console.print(f"License: {skill.properties.license}")
        if skill.properties.compatibility:
            console.print(f"Compatibility: {skill.properties.compatibility}")
        if skill.properties.allowed_tools:
            console.print(f"Allowed Tools: {skill.properties.allowed_tools}")
        if skill.properties.metadata:
            console.print(f"Metadata: {skill.properties.metadata}")
        
        # Show instructions if loaded
        if skill.instructions:
            console.print("\n[bold]Instructions:[/bold]")
            console.print(Panel(Markdown(skill.instructions[:2000])))
        
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
