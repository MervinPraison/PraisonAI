"""
Plugins command group for PraisonAI CLI.

Provides plugin management commands inspired by moltbot's plugins CLI.
Supports listing, enabling, disabling, and inspecting plugins.
"""

import typer

app = typer.Typer(
    help="Plugin management and inspection",
    no_args_is_help=True,
)


def _resolve_installer(global_env: bool = False):
    """Resolve the installer command, honouring how PraisonAI was installed.

    Prefers ``uv pip`` when the ``uv`` binary is available, otherwise falls
    back to ``<python> -m pip`` for the active interpreter.

    The ``uv`` branch pins ``--python <sys.executable>`` so the package lands
    in the interpreter running the CLI rather than an unrelated environment
    ``uv`` might auto-discover (``VIRTUAL_ENV`` / ``CONDA_PREFIX`` / nearby
    ``.venv``). When ``global_env`` is set the target is the ambient system
    interpreter instead (``uv``'s ``--system`` / plain ``pip``).
    """
    import shutil
    import sys

    if shutil.which("uv"):
        if global_env:
            return ["uv", "pip", "install", "--system"]
        return ["uv", "pip", "install", "--python", sys.executable]
    if global_env:
        return ["pip", "install"]
    return [sys.executable, "-m", "pip", "install"]


def _registered_entry_point_names():
    """Return the set of currently registered entry-point plugin names."""
    try:
        from praisonaiagents.plugins.manager import get_plugin_manager
    except ImportError:
        return set()
    manager = get_plugin_manager()
    return {info.name for info in manager.list_plugins()}


@app.command("list")
def plugins_list(
    enabled_only: bool = typer.Option(False, "--enabled", help="Show only enabled plugins"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List available plugins.
    
    Examples:
        praisonai plugins list
        praisonai plugins list --enabled
        praisonai plugins list --json
    """
    try:
        # Try to get plugins from the plugin system
        plugins = _get_available_plugins()
        
        if enabled_only:
            plugins = [p for p in plugins if p.get("enabled", False)]
        
        if json_output:
            import json
            print(json.dumps(plugins, indent=2))
        else:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            table = Table(title=f"Plugins ({len(plugins)} available)")
            table.add_column("Name", style="cyan")
            table.add_column("Source")
            table.add_column("Status")
            table.add_column("Description")
            
            for plugin in plugins:
                status = "[green]enabled[/green]" if plugin.get("enabled") else "[dim]disabled[/dim]"
                desc = plugin.get("description", "") or "-"
                if len(desc) > 40:
                    desc = desc[:40] + "..."
                table.add_row(
                    plugin.get("name", "-"),
                    plugin.get("source", "-"),
                    status,
                    desc,
                )
            
            console.print(table)
            
    except Exception as e:
        typer.echo(f"Error listing plugins: {e}", err=True)
        raise typer.Exit(1)


@app.command("info")
def plugins_info(
    plugin_id: str = typer.Argument(..., help="Plugin ID"),
):
    """Show detailed information about a plugin.
    
    Examples:
        praisonai plugins info my-plugin
    """
    try:
        plugins = _get_available_plugins()
        plugin = next((p for p in plugins if p.get("id") == plugin_id), None)
        
        if not plugin:
            typer.echo(f"Plugin not found: {plugin_id}", err=True)
            raise typer.Exit(1)
        
        from rich.console import Console
        from rich.panel import Panel
        
        console = Console()
        
        console.print(f"\n[bold cyan]{plugin.get('name', plugin_id)}[/bold cyan]")
        console.print(f"ID: {plugin.get('id', '-')}")
        console.print(f"Source: {plugin.get('source', '-')}")
        console.print(f"Status: {'[green]enabled[/green]' if plugin.get('enabled') else '[dim]disabled[/dim]'}")
        console.print(f"Description: {plugin.get('description', '-')}")
        
        if plugin.get("version"):
            console.print(f"Version: {plugin.get('version')}")
        if plugin.get("author"):
            console.print(f"Author: {plugin.get('author')}")
        if plugin.get("hooks"):
            console.print(f"Hooks: {', '.join(plugin.get('hooks', []))}")
        if plugin.get("config_schema"):
            console.print("\n[bold]Config Schema:[/bold]")
            import json
            console.print(Panel(json.dumps(plugin.get("config_schema"), indent=2)))
            
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("enable")
def plugins_enable(
    plugin_id: str = typer.Argument(..., help="Plugin ID to enable"),
):
    """Enable a plugin.
    
    Examples:
        praisonai plugins enable my-plugin
    """
    try:
        from praisonaiagents.config.loader import set_plugin_enabled

        path = set_plugin_enabled(plugin_id, True)
        typer.echo(f"Plugin enabled: {plugin_id} ({path})")

        # If a runtime is live in this process, wire it in immediately.
        try:
            from praisonaiagents.plugins.manager import get_plugin_manager

            manager = get_plugin_manager()
            if manager.enable(plugin_id):
                manager.wire_into_hook_registry()
        except Exception as wire_err:
            typer.echo(
                f"Note: could not wire '{plugin_id}' into the live runtime: "
                f"{wire_err}",
                err=True,
            )

    except Exception as e:
        typer.echo(f"Error enabling plugin: {e}", err=True)
        raise typer.Exit(1) from e


@app.command("disable")
def plugins_disable(
    plugin_id: str = typer.Argument(..., help="Plugin ID to disable"),
):
    """Disable a plugin.
    
    Examples:
        praisonai plugins disable my-plugin
    """
    try:
        from praisonaiagents.config.loader import set_plugin_enabled

        path = set_plugin_enabled(plugin_id, False)
        typer.echo(f"Plugin disabled: {plugin_id} ({path})")

        # If a runtime is live in this process, unwire its hooks immediately.
        try:
            from praisonaiagents.plugins.manager import get_plugin_manager

            get_plugin_manager().disable(plugin_id)
        except Exception as wire_err:
            typer.echo(
                f"Note: could not unwire '{plugin_id}' hooks from the live "
                f"runtime: {wire_err}",
                err=True,
            )

        # A single-file plugin also contributes tools to the global registry;
        # manager.disable() only unwires hooks, so unload the module to remove
        # its tools instead of leaving them callable for the rest of the run.
        try:
            from praisonaiagents.plugins.manager import get_plugin_manager
            from praisonaiagents.plugins.discovery import unload_plugin

            meta = get_plugin_manager().get_single_file_plugin(plugin_id)
            module_name = meta.get("module") if meta else None
            if module_name:
                unload_plugin(module_name)
        except Exception as unload_err:
            typer.echo(
                f"Note: could not unload single-file plugin '{plugin_id}' "
                f"tools: {unload_err}",
                err=True,
            )

    except Exception as e:
        typer.echo(f"Error disabling plugin: {e}", err=True)
        raise typer.Exit(1) from e


@app.command("doctor")
def plugins_doctor():
    """Check plugin health and configuration.
    
    Verifies that all enabled plugins are properly configured and
    their dependencies are met.
    
    Examples:
        praisonai plugins doctor
    """
    try:
        from rich.console import Console
        from rich.table import Table
        
        console = Console()
        plugins = _get_available_plugins()
        enabled_plugins = [p for p in plugins if p.get("enabled")]
        
        console.print("[bold]Plugin Health Check[/bold]\n")

        # Show whether external plugins are suppressed for the current process,
        # and how to reproduce a clean, plugin-free baseline for debugging/CI.
        import os as _os_doctor
        if _os_doctor.environ.get("PRAISONAI_NO_PLUGINS", "").strip().lower() in (
            "true", "1", "yes",
        ):
            console.print(
                "[yellow]External plugins are suppressed for this run "
                "(--pure / PRAISONAI_NO_PLUGINS).[/yellow]\n"
            )
        else:
            console.print(
                "[dim]Tip: run any command with --pure / --no-plugins "
                "(or PRAISONAI_NO_PLUGINS=1) for a clean, plugin-free "
                "baseline.[/dim]\n"
            )
        
        if not enabled_plugins:
            console.print("[yellow]No plugins enabled[/yellow]")
            return
        
        table = Table()
        table.add_column("Plugin", style="cyan")
        table.add_column("Status")
        table.add_column("Issues")
        
        issues_found = 0
        
        # Gate status for project-local single-file plugins.
        try:
            from praisonaiagents.plugins.discovery import _project_plugins_allowed
            gate_open = _project_plugins_allowed()
        except Exception:
            gate_open = False

        for plugin in enabled_plugins:
            issues = []
            source = plugin.get("source", "")

            # Single-file project plugins require the trust gate to load.
            if source == "single_file" and not gate_open:
                issues.append("blocked: set PRAISONAI_ALLOW_PROJECT_PLUGINS=true")

            # A registered plugin with no hooks is wired but contributes no
            # lifecycle behaviour (it may still expose tools).
            if source == "registered" and not plugin.get("hooks"):
                issues.append("no hooks wired")

            # An entry-point plugin present but not yet loaded imports its
            # hooks only when enabled, so hooks are empty until then.
            if source.startswith("entry_point") and not plugin.get("hooks"):
                issues.append("not loaded (hooks import on enable)")

            if issues:
                status = "[red]✗ Issues[/red]"
                issues_found += len(issues)
            else:
                status = "[green]✓ OK[/green]"
            
            table.add_row(
                plugin.get("name", plugin.get("id")),
                status,
                ", ".join(issues) if issues else "-",
            )
        
        console.print(table)
        
        if issues_found:
            console.print(f"\n[red]Found {issues_found} issue(s)[/red]")
        else:
            console.print(f"\n[green]All {len(enabled_plugins)} plugins healthy[/green]")
            
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("reload")
def plugins_reload():
    """Reload plugins without restarting.

    Forces rediscovery of single-file and entry-point plugins, then rewires
    enabled plugins into the runtime hook registry — so newly added plugins
    take effect in the current process instead of on the next run.

    Examples:
        praisonai plugins reload
    """
    try:
        from praisonaiagents.plugins.manager import get_plugin_manager
        from praisonaiagents.plugins.discovery import unload_plugin
    except ImportError as exc:
        typer.echo("Error: praisonaiagents package not found.", err=True)
        raise typer.Exit(1) from exc

    try:
        manager = get_plugin_manager()

        # Unload previously-loaded single-file plugins first so an edited file
        # is re-executed and re-registered cleanly. Without this, the old
        # tool stays in the registry and rediscovery skips re-registration,
        # leaving agents on the stale implementation.
        for meta in manager.list_single_file_plugins():
            module_name = meta.get("module")
            if module_name:
                unload_plugin(module_name)

        single_file = manager.auto_discover_plugins()
        entry_points = manager.discover_entry_points()
        wired = manager.wire_into_hook_registry()
        typer.echo(
            f"Reloaded plugins: {single_file} single-file, "
            f"{entry_points} entry-point, {wired} hook(s) wired"
        )
        if single_file == 0:
            typer.echo(
                "No single-file plugins were loaded. Set "
                "PRAISONAI_ALLOW_PLUGIN_DISCOVERY=true (and "
                "PRAISONAI_ALLOW_PROJECT_PLUGINS=true for project-local "
                "plugins) to load them."
            )
    except Exception as e:
        typer.echo(f"Error reloading plugins: {e}", err=True)
        raise typer.Exit(1) from e


@app.command("add")
def plugins_add(
    package: str = typer.Argument(..., help="Plugin package to install (pip requirement spec)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Only run discovery/verification, do not install"
    ),
    upgrade: bool = typer.Option(
        False, "--upgrade", "-U", help="Upgrade the package if already installed"
    ),
    global_env: bool = typer.Option(
        False,
        "--global",
        help="Install into the ambient/system environment instead of the CLI interpreter",
    ),
):
    """Install a plugin package and verify it registers.

    Installs the package into the active environment, triggers entry-point
    discovery for the ``praisonai.plugins`` group, and reports exactly which
    plugins were registered (name, type, hooks) — or a clear error if nothing
    was discovered.

    Examples:
        praisonai plugins add praisonai-my-plugin
        praisonai plugins add praisonai-my-plugin --upgrade
        praisonai plugins add praisonai-my-plugin --dry-run
    """
    try:
        from praisonaiagents.plugins.manager import get_plugin_manager
    except ImportError:
        typer.echo(
            "Error: praisonaiagents package not found. Install with: pip install praisonaiagents",
            err=True,
        )
        raise typer.Exit(1)

    before = _registered_entry_point_names()

    if not dry_run:
        import importlib
        import subprocess

        cmd = _resolve_installer(global_env)
        if upgrade:
            cmd = cmd + ["--upgrade"]
        cmd = cmd + [package]
        typer.echo(f"Installing {package} ...")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            typer.echo(f"Error: installation failed for '{package}'.", err=True)
            raise typer.Exit(1)
        # A package installed into the running interpreter is only importable
        # after the finder caches are refreshed; otherwise entry-point
        # discovery below can miss the just-installed distribution.
        importlib.invalidate_caches()

    manager = get_plugin_manager()
    manager.discover_entry_points()
    after = _registered_entry_point_names()

    new_names = sorted(after - before)

    if not new_names:
        typer.echo(
            f"[yellow]No new plugins were registered by '{package}'.[/yellow]\n"
            "The package installed but exposed no 'praisonai.plugins' entry points, "
            "or an entry point failed to load. Run 'praisonai plugins list' to inspect.",
            err=True,
        )
        raise typer.Exit(1)

    from rich.console import Console
    from rich.table import Table

    console = Console()
    verb = "Discovered" if dry_run else "Registered"
    table = Table(title=f"{verb} {len(new_names)} plugin(s) from {package}")
    table.add_column("Plugin", style="cyan")
    table.add_column("Type")
    table.add_column("Hooks", style="green")

    for name in new_names:
        plugin = manager.get_plugin(name)
        info = plugin.info if plugin is not None else None
        ptype = type(plugin).__name__ if plugin is not None else "-"
        hooks = ", ".join(h.value for h in info.hooks) if info and info.hooks else "-"
        table.add_row(name, ptype, hooks)

    console.print(table)


# ============ Single-File Plugin Commands ============

@app.command("create")
def plugins_create(
    name: str = typer.Argument(..., help="Plugin name (will be converted to snake_case)"),
    description: str = typer.Option("A PraisonAI plugin", "--description", "-d", help="Plugin description"),
    author: str = typer.Option("", "--author", "-a", help="Plugin author"),
    output_dir: str = typer.Option(None, "--output", "-o", help="Output directory (default: ~/.praison/plugins/)"),
):
    """Create a new single-file plugin from template.
    
    Creates a new plugin with WordPress-style docstring header in the
    user's plugin directory (~/.praison/plugins/).
    
    Examples:
        praisonai plugins create weather
        praisonai plugins create weather --description "Weather API tools"
        praisonai plugins create weather -o ./my_plugins/
    """
    try:
        from pathlib import Path
        from praisonaiagents.plugins.discovery import get_plugin_template, ensure_plugin_dir
        
        # Sanitize plugin name
        safe_name = name.lower().replace("-", "_").replace(" ", "_")
        
        # Determine output directory
        if output_dir:
            plugin_dir = Path(output_dir).expanduser().resolve()
            plugin_dir.mkdir(parents=True, exist_ok=True)
        else:
            plugin_dir = ensure_plugin_dir()
        
        plugin_path = plugin_dir / f"{safe_name}.py"
        
        # Check if file already exists
        if plugin_path.exists():
            overwrite = typer.confirm(f"Plugin {plugin_path} already exists. Overwrite?")
            if not overwrite:
                typer.echo("Cancelled.")
                raise typer.Exit(0)
        
        # Generate template
        template = get_plugin_template(name, description, author)
        
        # Write file
        plugin_path.write_text(template)
        
        typer.echo(f"[green]✓[/green] Created plugin: {plugin_path}")
        typer.echo(f"\nNext steps:")
        typer.echo(f"  1. Edit {plugin_path} to add your tools")
        typer.echo(f"  2. Run 'praisonai plugins discover' to verify")
        typer.echo(f"  3. Use tools with Agent(tools=['example_tool'])")
        
    except ImportError as e:
        typer.echo(f"Error: praisonaiagents package not found. Install with: pip install praisonaiagents", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error creating plugin: {e}", err=True)
        raise typer.Exit(1)


@app.command("install")  
def plugins_install(
    source: str = typer.Argument(..., help="Path to plugin file to install"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing plugin"),
):
    """Install a single-file plugin.
    
    Copies a plugin file to the user's plugin directory (~/.praison/plugins/).
    
    Examples:
        praisonai plugins install ./my_weather_plugin.py
        praisonai plugins install ./my_weather_plugin.py --force
    """
    try:
        from pathlib import Path
        import shutil
        from praisonaiagents.plugins.discovery import ensure_plugin_dir
        from praisonaiagents.plugins.parser import parse_plugin_header_from_file
        
        source_path = Path(source).expanduser().resolve()
        
        # Validate source file
        if not source_path.exists():
            typer.echo(f"Error: File not found: {source}", err=True)
            raise typer.Exit(1)
        
        if not source_path.suffix == ".py":
            typer.echo(f"Error: Plugin must be a Python file (.py)", err=True)
            raise typer.Exit(1)
        
        # Validate plugin header
        try:
            metadata = parse_plugin_header_from_file(str(source_path))
            plugin_name = metadata.get("name", source_path.stem)
        except Exception as e:
            typer.echo(f"Error: Invalid plugin header: {e}", err=True)
            raise typer.Exit(1)
        
        # Install to user plugin directory
        plugin_dir = ensure_plugin_dir()
        dest_path = plugin_dir / source_path.name
        
        if dest_path.exists() and not force:
            overwrite = typer.confirm(f"Plugin {dest_path.name} already exists. Overwrite?")
            if not overwrite:
                typer.echo("Cancelled.")
                raise typer.Exit(0)
        
        shutil.copy2(source_path, dest_path)
        
        typer.echo(f"[green]✓[/green] Installed '{plugin_name}' to {dest_path}")
        typer.echo("\nRun 'praisonai plugins reload' to load it now, or it "
                   "loads on next run.")
        
    except ImportError:
        typer.echo(f"Error: praisonaiagents package not found.", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error installing plugin: {e}", err=True)
        raise typer.Exit(1)


@app.command("discover")
def plugins_discover(
    plugin_dirs: str = typer.Option(None, "--dirs", "-d", help="Additional plugin directories (comma-separated)"),
    load: bool = typer.Option(False, "--load", "-l", help="Actually load the plugins"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Discover single-file plugins from plugin directories.
    
    Scans ~/.praison/plugins/ and ./.praison/plugins/ for valid plugins.
    
    Examples:
        praisonai plugins discover
        praisonai plugins discover --load
        praisonai plugins discover --json
    """
    try:
        from praisonaiagents.plugins.discovery import discover_plugins, discover_and_load_plugins
        
        extra_dirs = plugin_dirs.split(",") if plugin_dirs else None
        
        if load:
            plugins = discover_and_load_plugins(extra_dirs)
        else:
            plugins = discover_plugins(extra_dirs)
        
        if json_output:
            import json
            print(json.dumps(plugins, indent=2, default=str))
        else:
            from rich.console import Console
            from rich.table import Table
            
            console = Console()
            
            if not plugins:
                console.print("[yellow]No single-file plugins found.[/yellow]")
                console.print("\nCreate one with: praisonai plugins init <name>")
                return
            
            table = Table(title=f"Single-File Plugins ({len(plugins)} found)")
            table.add_column("Name", style="cyan")
            table.add_column("Version")
            table.add_column("Tools", style="green")
            table.add_column("Path")
            
            for plugin in plugins:
                tools = plugin.get("tools", [])
                tools_str = ", ".join(tools[:3])
                if len(tools) > 3:
                    tools_str += f" (+{len(tools)-3})"
                
                table.add_row(
                    plugin.get("name", "-"),
                    plugin.get("version", "-"),
                    tools_str or "-",
                    str(plugin.get("path", "-"))[:40],
                )
            
            console.print(table)
            
            if load:
                console.print("\n[green]Plugins loaded.[/green] Tools are now available.")
            
    except ImportError:
        typer.echo(f"Error: praisonaiagents package not found.", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error discovering plugins: {e}", err=True)
        raise typer.Exit(1)


@app.command("remove")
def plugins_remove(
    name: str = typer.Argument(..., help="Plugin name or filename to remove"),
    force: bool = typer.Option(False, "--force", "-f", help="Remove without confirmation"),
):
    """Remove a single-file plugin.
    
    Removes a plugin from the user's plugin directory.
    
    Examples:
        praisonai plugins remove weather
        praisonai plugins remove weather_plugin.py --force
    """
    try:
        from pathlib import Path
        from praisonaiagents.plugins.discovery import get_default_plugin_dirs
        
        # Normalize name
        if not name.endswith(".py"):
            name = f"{name}.py"
        
        # Search in plugin directories
        plugin_path = None
        for plugin_dir in get_default_plugin_dirs():
            candidate = plugin_dir / name
            if candidate.exists():
                plugin_path = candidate
                break
        
        # Also check user directory explicitly
        if not plugin_path:
            user_dir = Path.home() / ".praison" / "plugins"
            candidate = user_dir / name
            if candidate.exists():
                plugin_path = candidate
        
        if not plugin_path:
            typer.echo(f"Plugin not found: {name}", err=True)
            raise typer.Exit(1)
        
        if not force:
            confirm = typer.confirm(f"Remove plugin {plugin_path}?")
            if not confirm:
                typer.echo("Cancelled.")
                raise typer.Exit(0)
        
        plugin_path.unlink()
        typer.echo(f"[green]✓[/green] Removed: {plugin_path}")
        
    except ImportError:
        # Fallback without praisonaiagents
        from pathlib import Path
        user_dir = Path.home() / ".praison" / "plugins"
        if not name.endswith(".py"):
            name = f"{name}.py"
        plugin_path = user_dir / name
        if plugin_path.exists():
            if force or typer.confirm(f"Remove plugin {plugin_path}?"):
                plugin_path.unlink()
                typer.echo(f"[green]✓[/green] Removed: {plugin_path}")
        else:
            typer.echo(f"Plugin not found: {name}", err=True)
            raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error removing plugin: {e}", err=True)
        raise typer.Exit(1)


def _get_available_plugins():
    """Return the real, unified plugin registry from core.

    Delegates entirely to ``praisonaiagents.plugins.get_plugin_registry()``,
    which reports entry-point, registered, and single-file plugins with their
    provenance and enabled state. There is no hardcoded/fake list — the CLI
    shows exactly what the runtime can load. Each entry's ``name`` is reused as
    its ``id`` so existing ``info``/``enable``/``disable`` argument handling
    keeps working.
    """
    from praisonaiagents.plugins import get_plugin_registry

    entries = get_plugin_registry() or []
    for entry in entries:
        entry.setdefault("id", entry.get("name"))
    return entries


@app.callback(invoke_without_command=True)
def plugins_callback(ctx: typer.Context):
    """Show plugins help if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Plugins - Plugin Management[/bold cyan]

Manage plugins with: praisonai plugins <command>

[bold]Commands:[/bold]
  [green]list[/green]        List available plugins
  [green]add[/green]         Install a plugin package and verify it registers
  [green]info[/green]        Show plugin details
  [green]enable[/green]      Enable a plugin
  [green]disable[/green]     Disable a plugin
  [green]reload[/green]      Reload plugins without restarting
  [green]doctor[/green]      Check plugin health

[bold]Examples:[/bold]
  praisonai plugins list
  praisonai plugins add praisonai-my-plugin
  praisonai plugins info my-plugin
  praisonai plugins enable my-plugin
  praisonai plugins reload
  praisonai plugins doctor
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)
