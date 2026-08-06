"""
Skills command group for PraisonAI CLI.

Provides skill management commands inspired by moltbot's skills CLI.
Supports listing, checking eligibility, and managing skills.
"""

import typer

app = typer.Typer(help="Skill management and inspection")

bundle_app = typer.Typer(help="Skill bundle inspection (named sets of skills)")
app.add_typer(bundle_app, name="bundle")


@bundle_app.command("list")
def bundle_list(
    skill_dirs: str = typer.Option(
        None, "--dirs", "-d", help="Comma-separated skill directories"
    ),
):
    """List available skill bundles."""
    try:
        from praisonaiagents.skills import discover_bundles
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    dirs = skill_dirs.split(",") if skill_dirs else None
    bundles = discover_bundles(dirs, include_defaults=True)

    if not bundles:
        typer.echo("No skill bundles found.")
        return

    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title=f"Skill Bundles ({len(bundles)} found)")
    table.add_column("Name", style="cyan")
    table.add_column("Skills", style="green")
    table.add_column("Description")

    for b in bundles:
        desc = b.description or ""
        table.add_row(
            b.name,
            ", ".join(b.skills) if b.skills else "-",
            desc[:60] + "..." if len(desc) > 60 else desc,
        )

    console.print(table)


@bundle_app.command("show")
def bundle_show(
    name: str = typer.Argument(..., help="Bundle name"),
    skill_dirs: str = typer.Option(
        None, "--dirs", "-d", help="Comma-separated skill directories"
    ),
):
    """Show the members of a skill bundle."""
    try:
        from praisonaiagents.skills import discover_bundles
        from praisonaiagents.skills.bundles import strip_bundle_marker
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    dirs = skill_dirs.split(",") if skill_dirs else None
    bundles = discover_bundles(dirs, include_defaults=True)

    target = strip_bundle_marker(name)
    match = next((b for b in bundles if b.name == target), None)
    if match is None:
        typer.echo(f"Bundle not found: {name}", err=True)
        raise typer.Exit(1)

    from rich.console import Console

    console = Console()
    console.print(f"\n[bold cyan]{match.name}[/bold cyan]")
    if match.description:
        console.print(f"[dim]{match.description}[/dim]")
    if match.instruction:
        console.print(f"\n[bold]Instruction:[/bold]\n{match.instruction}")
    console.print("\n[bold]Skills:[/bold]")
    if match.skills:
        for s in match.skills:
            console.print(f"  - {s}")
    else:
        console.print("  (none)")


@app.command("list")
def skills_list(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List available skills."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['skills', 'list']
    if verbose:
        argv.append('--verbose')
    
    run_wrapper_command(argv, feature="skills")


@app.command("validate")
def skills_validate(
    path: str = typer.Argument(..., help="Skill directory path"),
):
    """Validate a skill."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['skills', 'validate', path]
    
    run_wrapper_command(argv, feature="skills")


@app.command("create")
def skills_create(
    name: str = typer.Argument(..., help="Skill name"),
):
    """Create a new skill."""
    from praisonai_code._wrapper_bridge import run_wrapper_command
    
    argv = ['skills', 'create', name]
    
    run_wrapper_command(argv, feature="skills")


@app.command("learn")
def skills_learn(
    request: str = typer.Argument(
        ...,
        help="Sources to learn from and the skill to make, e.g. "
        "\"deploy steps from ./repo and the runbook PDF\"",
    ),
    llm: str = typer.Option(None, "--llm", "-m", help="LLM model to use"),
):
    """Author a grounded, reusable skill from sources you describe.

    Points an agent at the sources you name (code, docs, PDFs, configs) and
    distils one grounded SKILL.md via the existing skill tools.

    This is the **skill authoring** path — distinct from ``praisonai memory
    learn`` (which captures a recall note) and the memory ``learn=`` param.

    Example:
        praisonai skills learn "deploy steps from ./repo and the runbook PDF"
    """
    try:
        from praisonaiagents import Agent
    except ImportError as e:
        typer.echo(f"Error: praisonaiagents is required for 'skills learn': {e}", err=True)
        raise typer.Exit(1)

    agent_kwargs = {}
    if llm:
        agent_kwargs["llm"] = llm

    agent = Agent(
        instructions="You author grounded, reusable Agent Skills from real sources.",
        **agent_kwargs,
    )
    try:
        result = agent.learn_skill(request)
    except Exception as e:  # noqa: BLE001 - surface a friendly message
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    if result:
        typer.echo(str(result))


@app.command("install")
def skills_install(
    source: str = typer.Argument(..., help="Skill source (local path or https:// git URL)"),
    dest: str = typer.Option(None, "--dest", "-d", help="Install destination (defaults to ~/.praisonai/skills)"),
):
    """Install a skill from a local path or git URL.

    Local path:  ``praisonai skills install ./my-skill``
    Git URL:     ``praisonai skills install https://github.com/org/repo``
    """
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    from praisonaiagents.paths import get_skills_dir
    from praisonaiagents.skills import validate as validate_skill

    dest_root = Path(dest).expanduser() if dest else get_skills_dir()
    dest_root.mkdir(parents=True, exist_ok=True)

    def _install_from_dir(src: Path) -> Path:
        target = dest_root / src.name
        if target.exists():
            typer.echo(f"Error: {target} already exists; remove it first.", err=True)
            raise typer.Exit(1)
        shutil.copytree(src, target)
        return target

    src_path = Path(source).expanduser()
    installed: Path
    if source.startswith(("http://", "https://", "git@")):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "clone"
            proc = subprocess.run(
                ["git", "clone", "--depth=1", source, str(tmp_path)],
                capture_output=True, text=True,
            )
            if proc.returncode != 0:
                typer.echo(f"git clone failed: {proc.stderr.strip()}", err=True)
                raise typer.Exit(1)
            # If the clone contains a top-level SKILL.md, install as-is.
            # Otherwise, install each direct subdirectory that looks like a skill.
            if (tmp_path / "SKILL.md").exists():
                installed = _install_from_dir(tmp_path)
            else:
                installed_any = False
                for child in tmp_path.iterdir():
                    if child.is_dir() and (child / "SKILL.md").exists():
                        _install_from_dir(child)
                        installed_any = True
                if not installed_any:
                    typer.echo("No SKILL.md found in clone.", err=True)
                    raise typer.Exit(1)
                typer.echo(f"Installed skills to {dest_root}")
                return
    elif src_path.exists() and src_path.is_dir():
        installed = _install_from_dir(src_path)
    else:
        typer.echo(f"Unknown source (not a dir, not a URL): {source}", err=True)
        raise typer.Exit(1)

    errors = validate_skill(installed)
    if errors:
        typer.echo(f"Installed at {installed} but validation found issues:", err=True)
        for e in errors:
            typer.echo(f"  - {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Installed: {installed}")


@app.command("add")
def skills_add(
    source: str = typer.Argument(..., help="Skill source (local path or https:// git URL)"),
    dest: str = typer.Option(None, "--dest", "-d", help="Install destination (defaults to ~/.praisonai/skills)"),
):
    """Add a skill from a URL or local path (alias of ``install``).

    Mirrors the familiar ``skills add <url>`` verb:

        praisonai skills add https://github.com/org/repo
        praisonai skills add ./my-skill
    """
    skills_install(source=source, dest=dest)


@app.command("sync")
def skills_sync(
    url: str = typer.Argument(
        None,
        help="Remote skill source git URL. If omitted, uses skills.urls from config.",
    ),
    ref: str = typer.Option(None, "--ref", "-r", help="Pin a branch/tag/commit"),
):
    """Force-refresh declarative remote skill sources into the local cache.

    Syncs remote skills into a versioned cache under ~/.praisonai/cache so that
    ``discover_skills`` (and every agent) picks up the latest without a manual
    ``skills install``. Offline-safe: keeps the last-good cache on failure.

    Examples:
        praisonai skills sync https://github.com/org/skills-repo
        praisonai skills sync           # uses skills.urls from config
    """
    try:
        from praisonaiagents.skills import (
            fetch_remote_skill_dirs,
            discover_skills,
            validate as validate_skill,
        )
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    sources = []
    if url:
        sources = [{"url": url, "ref": ref} if ref else url]
    else:
        sources = _load_configured_skill_sources()

    if not sources:
        typer.echo(
            "No remote skill sources. Pass a URL or set 'skills.urls' in config.",
            err=True,
        )
        raise typer.Exit(1)

    dirs = fetch_remote_skill_dirs(sources)
    if not dirs:
        typer.echo("Sync produced no skills (offline or empty source).", err=True)
        raise typer.Exit(1)

    # Re-use the canonical scanner so both layouts (skill-per-subdir and a
    # single root-level skill) are handled and de-duplicated identically to
    # normal discovery, instead of re-implementing the scan and double-counting.
    skills = discover_skills([str(d) for d in dirs], include_defaults=False)

    count = 0
    for skill in skills:
        errors = validate_skill(skill.path) if skill.path else ["missing path"]
        if errors:
            typer.echo(f"  ! {skill.name}: {'; '.join(errors)}", err=True)
        else:
            count += 1
            typer.echo(f"  ✓ {skill.name}")
    typer.echo(f"Synced {count} skill(s) into the local cache.")


def _load_configured_skill_sources():
    """Read skills.urls / skills.sources from PraisonAI config, if present.

    Looks in both the project-level ``praisonai.yaml``/``praisonai.yml`` (so a
    repo can declare shared skill sources) and the user-global
    ``~/.praisonai/config.yaml``. Project entries take precedence and are
    listed first; duplicates are removed while preserving order.
    """
    try:
        import yaml
    except ImportError:
        return []

    from pathlib import Path

    def _extract(path: Path):
        if not path.exists():
            return []
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except Exception:
            return []
        skills_cfg = data.get("skills") or {}
        if not isinstance(skills_cfg, dict):
            return []
        srcs = skills_cfg.get("urls") or skills_cfg.get("sources") or []
        if isinstance(srcs, str):
            srcs = [srcs]
        return list(srcs)

    candidates = []
    cwd = Path.cwd()
    for name in ("praisonai.yaml", "praisonai.yml"):
        candidates.append(cwd / name)
    try:
        from praisonaiagents.paths import get_config_path

        candidates.append(get_config_path())
    except ImportError:
        pass

    ordered = []
    seen = set()
    for path in candidates:
        for src in _extract(path):
            key = src if isinstance(src, str) else repr(src)
            if key not in seen:
                seen.add(key)
                ordered.append(src)
    return ordered


@app.command("reload")
def skills_reload(
    skill_dirs: str = typer.Option(
        None, "--dirs", "-d", help="Comma-separated skill directories"
    ),
):
    """Re-scan skill directories and report the skills now available.

    ``SkillManager.reload()`` is the live-session primitive: a running session
    calls it to pick up newly installed or edited skills on the *next* turn
    without a restart. This standalone CLI command is a convenience scan that
    lists the skills currently discoverable on disk (there is no live session
    to refresh from a separate process), so run it to confirm a
    ``praisonai skills install <url>`` or a SKILL.md edit landed on disk.

    Examples:
        praisonai skills reload
        praisonai skills reload --dirs ./skills
    """
    try:
        from praisonaiagents.skills import SkillManager
    except ImportError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    dirs = skill_dirs.split(",") if skill_dirs else None

    manager = SkillManager()
    manager.discover(dirs, include_defaults=dirs is None)

    from rich.console import Console

    console = Console()
    names = sorted(manager.skill_names)
    for name in names:
        console.print(f"[green]• {name}[/green]")

    console.print(f"Skills available: [green]{len(names)}[/green]")


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
