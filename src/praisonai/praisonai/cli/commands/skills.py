"""
Skills command group for PraisonAI CLI.

Provides skill management commands inspired by moltbot's skills CLI.
Supports listing, checking eligibility, and managing skills.
"""

import typer

app = typer.Typer(help="Skill management and inspection")


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


@app.command("check")
def skills_check(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed check results"),
):
    """Check skill requirements and eligibility.
    
    Verifies that all required binaries, environment variables, and
    configurations are present for skills to be eligible.
    
    Examples:
        praisonai skills check
        praisonai skills check --verbose
    """
    try:
        from praisonaiagents.skills import discover_skills
        import os
        import shutil
        
        skills = discover_skills(include_defaults=True)
        
        from rich.console import Console
        from rich.table import Table
        
        console = Console()
        table = Table(title="Skill Requirements Check")
        table.add_column("Skill", style="cyan")
        table.add_column("Status")
        table.add_column("Missing", style="yellow")
        
        total = 0
        eligible = 0
        
        for skill in skills:
            total += 1
            missing = []
            
            # Check metadata requirements if available
            metadata = getattr(skill, 'metadata', {}) or {}
            requires = metadata.get('requires', {}) if isinstance(metadata, dict) else {}
            
            # Check required binaries
            bins = requires.get('bins', []) if isinstance(requires, dict) else []
            for bin_name in bins:
                if not shutil.which(bin_name):
                    missing.append(f"bin:{bin_name}")
            
            # Check required env vars
            env_vars = requires.get('env', []) if isinstance(requires, dict) else []
            for env_var in env_vars:
                if not os.environ.get(env_var):
                    missing.append(f"env:{env_var}")
            
            if missing:
                status = "[red]✗ Missing requirements[/red]"
            else:
                status = "[green]✓ Eligible[/green]"
                eligible += 1
            
            if verbose or missing:
                table.add_row(
                    skill.name,
                    status,
                    ", ".join(missing) if missing else "-",
                )
        
        console.print(table)
        console.print(f"\n[bold]Summary:[/bold] {eligible}/{total} skills eligible")
        
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("eligible")
def skills_eligible(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List only eligible skills (requirements met).
    
    Shows skills that have all their requirements satisfied and are
    ready to use.
    
    Examples:
        praisonai skills eligible
        praisonai skills eligible --json
    """
    try:
        from praisonaiagents.skills import discover_skills
        import os
        import shutil
        
        skills = discover_skills(include_defaults=True)
        eligible_skills = []
        
        for skill in skills:
            # Check metadata requirements if available
            metadata = getattr(skill, 'metadata', {}) or {}
            requires = metadata.get('requires', {}) if isinstance(metadata, dict) else {}
            
            is_eligible = True
            
            # Check required binaries
            bins = requires.get('bins', []) if isinstance(requires, dict) else []
            for bin_name in bins:
                if not shutil.which(bin_name):
                    is_eligible = False
                    break
            
            # Check required env vars
            if is_eligible:
                env_vars = requires.get('env', []) if isinstance(requires, dict) else []
                for env_var in env_vars:
                    if not os.environ.get(env_var):
                        is_eligible = False
                        break
            
            if is_eligible:
                eligible_skills.append(skill)
        
        if json_output:
            import json
            output = [
                {
                    "name": s.name,
                    "description": s.description,
                    "path": str(s.path) if s.path else None,
                }
                for s in eligible_skills
            ]
            print(json.dumps(output, indent=2))
        else:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title=f"Eligible Skills ({len(eligible_skills)} ready)")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            
            for skill in eligible_skills:
                table.add_row(
                    skill.name,
                    skill.description[:60] + "..." if len(skill.description) > 60 else skill.description,
                )
            
            console.print(table)
        
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
