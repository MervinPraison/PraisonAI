"""
Tools command group for PraisonAI CLI.

Provides tool management commands including:
- List available tools from all sources
- Validate YAML tool references
- Show tool information
"""

from typing import Dict, Optional, Tuple

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

app = typer.Typer(help="Tool management and discovery")
console = Console()


# Upper bound (seconds) on connecting-to + enumerating a single MCP server
# during discovery, so an unreachable/hung server cannot stall the listing for
# its full configured timeout. Discovery is read-only, so a short cap is safe.
_MCP_DISCOVERY_TIMEOUT_S = 8


def _discover_mcp_tools() -> Tuple[Dict[str, str], Dict[str, str]]:
    """Discover tools exposed by configured MCP servers, lazily and fail-soft.

    Reads the same MCP server config the run path / ``praisonai mcp`` group
    uses, connects to each enabled server through the already-guarded
    ``MCPHandler.create_mcp_from_server`` (executable allow-list + inline-exec
    blocking), and enumerates its tools. Tools are listed under the *same*
    callable name an agent would dispatch at runtime (the run path registers
    MCP tools by their bare ``__name__``), with the server surfaced separately
    as the source — so a name copied from this listing actually resolves.

    A server that is unreachable, slow, or misconfigured never blocks the rest
    of the listing: each server is discovered under a short timeout and, on
    failure, reported as unavailable with a reason.

    Returns:
        Tuple of (tools, unavailable) where ``tools`` maps the runtime tool
        name -> one-line description and ``unavailable`` maps ``<server>`` ->
        reason string. Both are empty when no MCP servers are configured, so
        the cost is zero for the common case.
    """
    tools: Dict[str, str] = {}
    unavailable: Dict[str, str] = {}

    try:
        from praisonai_code.cli.commands.run import _collect_mcp_servers_from_config
        from praisonai_code.cli.configuration.resolver import resolve_config
    except Exception:
        return tools, unavailable

    try:
        config = resolve_config()
    except Exception:
        return tools, unavailable

    try:
        servers = _collect_mcp_servers_from_config(config)
    except Exception:
        return tools, unavailable

    if not servers:
        return tools, unavailable

    try:
        from praisonai_code.cli.features.mcp import MCPHandler
    except Exception:
        return tools, unavailable

    # Suppress the handler's own status prints so discovery stays quiet; a
    # failed connection surfaces as an unavailable row instead.
    handler = MCPHandler()
    handler.print_status = lambda *a, **k: None  # type: ignore[assignment]

    for server in servers:
        name = str(server.get("name") or server.get("command") or server.get("url") or "mcp")
        try:
            server_tools = _discover_single_server(handler, server)
        except Exception as e:
            unavailable[name] = str(e) or "connection failed"
            continue

        if server_tools is None:
            unavailable[name] = "unavailable (not reachable or misconfigured)"
            continue

        if not server_tools:
            unavailable[name] = "connected but exposed no tools"
            continue

        for tool_name, doc in server_tools.items():
            # If two servers expose the same tool name, disambiguate the later
            # one so both are visible without hiding either. The first keeps the
            # bare runtime name; ties are surfaced with the server context.
            display = tool_name if tool_name not in tools else f"{tool_name} ({name})"
            tools[display] = doc

    return tools, unavailable


def _discover_single_server(handler, server) -> Optional[Dict[str, str]]:
    """Connect to one MCP server and enumerate its tools under a hard timeout.

    Runs the (potentially blocking) connect + enumerate in a worker thread so a
    slow or unreachable server cannot stall the whole listing for its full
    configured timeout — it is abandoned after :data:`_MCP_DISCOVERY_TIMEOUT_S`.

    Returns a mapping of runtime tool name -> one-line description, ``None`` if
    the server was unreachable/misconfigured, or ``{}`` if it connected but
    exposed no tools. Raises on timeout so the caller records a reason.
    """
    import concurrent.futures

    def _work() -> Optional[Dict[str, str]]:
        mcp = handler.create_mcp_from_server(server)
        if mcp is None:
            return None
        found: Dict[str, str] = {}
        for tool in mcp:
            tool_name = getattr(tool, "__name__", None)
            if not tool_name:
                continue
            doc = (getattr(tool, "__doc__", None) or "").strip()
            found[tool_name] = doc.split("\n")[0] if doc else "MCP tool"
        return found

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_work)
        try:
            return future.result(timeout=_MCP_DISCOVERY_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"timed out after {_MCP_DISCOVERY_TIMEOUT_S}s"
            )


@app.command("list")
def tools_list(
    source: Optional[str] = typer.Option(
        None, "--source", "-s", 
        help="Filter by source: builtin, local, external, registered, mcp"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """List all available tools that can be used in YAML files.
    
    Shows tools from:
    - Built-in tools (praisonaiagents.tools)
    - Local tools.py (if present)
    - External tools (praisonai-tools package)
    - Registered/entry-point tools (core registry plugins)
    - MCP tools (from configured MCP servers, discovered live)
    """
    from praisonai_code.tool_resolver import ToolResolver
    
    resolver = ToolResolver()
    available = resolver.list_available()
    sources = resolver.list_available_sources()

    # MCP tools live behind a network connection, so only discover them when
    # they are relevant to the requested view (default view or --source mcp).
    # This keeps the common four-bucket listing free of connection cost.
    mcp_tools: dict = {}
    mcp_unavailable: dict = {}
    if source in (None, "mcp"):
        mcp_tools, mcp_unavailable = _discover_mcp_tools()
        for name in mcp_tools:
            sources[name] = "mcp"

    if not available and not mcp_tools and not mcp_unavailable:
        console.print("[yellow]No tools available.[/yellow]")
        return
    
    # Categorize tools by their authoritative resolution source (not by
    # substring matching on the description, which may come from a docstring).
    builtin_tools = {}
    local_tools = {}
    external_tools = {}
    registered_tools = {}
    bucket = {
        "local": local_tools,
        "external": external_tools,
        "registered": registered_tools,
        "builtin": builtin_tools,
    }
    for name, desc in available.items():
        bucket.get(sources.get(name, "builtin"), builtin_tools)[name] = desc
    
    # Filter by source if specified
    if source == "builtin":
        available = builtin_tools
    elif source == "local":
        available = local_tools
    elif source == "external":
        available = external_tools
    elif source == "registered":
        available = registered_tools
    elif source == "mcp":
        available = dict(mcp_tools)
    elif source is None:
        available = {**available, **mcp_tools}
    
    # Create table
    table = Table(title="Available Tools", show_header=True, header_style="bold cyan")
    table.add_column("Tool Name", style="green")
    table.add_column("Source", style="blue")
    if verbose:
        table.add_column("Description", style="dim")
    
    # Add rows
    for name in sorted(available.keys()):
        desc = available[name]
        src = sources.get(name, "builtin")
        
        if verbose:
            table.add_row(name, src, desc[:60] + "..." if len(desc) > 60 else desc)
        else:
            table.add_row(name, src)
    
    console.print(table)
    console.print(f"\n[dim]Total: {len(available)} tools[/dim]")
    
    if not source:
        console.print(
            f"[dim]  Built-in: {len(builtin_tools)} | Local: {len(local_tools)} | "
            f"External: {len(external_tools)} | Registered: {len(registered_tools)} | "
            f"MCP: {len(mcp_tools)}[/dim]"
        )

    # Surface unreachable MCP servers so a present-but-broken server is
    # debuggable rather than silently absent (mirrors describe_unresolved UX).
    if mcp_unavailable and source in (None, "mcp"):
        console.print("\n[yellow]Unavailable MCP servers:[/yellow]")
        for server_name in sorted(mcp_unavailable.keys()):
            console.print(
                f"  [red]• {escape(server_name)}[/red]: "
                f"[dim]{escape(mcp_unavailable[server_name])}[/dim]"
            )


@app.command("search")
def tools_search(
    query: str = typer.Argument(..., help="Substring to search tool names for"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """Search available tools by name substring (case-insensitive).

    Enumerates the same catalogue as 'tools list' (built-in, local, external,
    registered/entry-point) and filters to names containing the query.
    """
    from praisonai_code.tool_resolver import ToolResolver

    resolver = ToolResolver()
    available = resolver.list_available()
    sources = resolver.list_available_sources()

    needle = query.strip().lower()
    matches = {
        name: desc for name, desc in available.items() if needle in name.lower()
    }

    safe_query = escape(query)
    if not matches:
        console.print(f"[yellow]No tools matching '{safe_query}'.[/yellow]")
        console.print("[dim]Run 'praisonai tools list' to see all available tools.[/dim]")
        return

    table = Table(title=f"Tools matching '{safe_query}'", show_header=True, header_style="bold cyan")
    table.add_column("Tool Name", style="green")
    table.add_column("Source", style="blue")
    if verbose:
        table.add_column("Description", style="dim")

    for name in sorted(matches.keys()):
        desc = matches[name]
        src = sources.get(name, "builtin")
        if verbose:
            table.add_row(name, src, desc[:60] + "..." if len(desc) > 60 else desc)
        else:
            table.add_row(name, src)

    console.print(table)
    console.print(f"\n[dim]Total: {len(matches)} match(es)[/dim]")


@app.command("validate")
def tools_validate(
    yaml_file: str = typer.Argument("agents.yaml", help="YAML file to validate"),
):
    """Validate that all tools in a YAML file can be resolved.
    
    Checks that every tool name in the YAML can be found in:
    - Local tools.py
    - Built-in tools (praisonaiagents.tools)
    - External tools (praisonai-tools)
    """
    import yaml
    from pathlib import Path
    from praisonai_code.tool_resolver import ToolResolver
    
    yaml_path = Path(yaml_file)
    if not yaml_path.exists():
        console.print(f"[red]Error: File not found: {yaml_file}[/red]")
        raise typer.Exit(1)
    
    try:
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]Error parsing YAML: {e}[/red]")
        raise typer.Exit(1)
    
    resolver = ToolResolver()
    missing = resolver.validate_yaml_tools(config)
    
    if not missing:
        console.print(f"[green]✓ All tools in {yaml_file} are valid![/green]")
        
        # Show which tools were found
        roles = config.get('roles', config.get('agents', {}))
        all_tools = set()
        for role_config in roles.values():
            if isinstance(role_config, dict):
                all_tools.update(role_config.get('tools', []))
        
        if all_tools:
            console.print(f"[dim]Tools found: {', '.join(sorted(all_tools))}[/dim]")
    else:
        console.print(f"[red]✗ Missing tools in {yaml_file}:[/red]")
        for tool in missing:
            console.print(f"  [red]• {tool}[/red]")
        
        console.print("\n[yellow]Hint: Run 'praisonai tools list' to see available tools.[/yellow]")
        raise typer.Exit(1)


@app.command("info")
def tools_info(
    name: str = typer.Argument(..., help="Tool name"),
):
    """Show detailed information about a tool."""
    from praisonai_code.tool_resolver import ToolResolver
    
    resolver = ToolResolver()
    tool = resolver.resolve(name)
    
    if tool is None:
        console.print(f"[red]Tool '{name}' not found.[/red]")
        console.print("[yellow]Hint: Run 'praisonai tools list' to see available tools.[/yellow]")
        raise typer.Exit(1)
    
    console.print(f"\n[bold green]{name}[/bold green]")
    console.print("-" * 40)
    
    # Get docstring
    doc = getattr(tool, '__doc__', None)
    if doc:
        console.print(f"[dim]{doc}[/dim]")
    
    # Get signature if possible
    import inspect
    try:
        sig = inspect.signature(tool)
        console.print(f"\n[cyan]Signature:[/cyan] {name}{sig}")
    except (ValueError, TypeError):
        pass
    
    # Show source (authoritative, matches runtime resolution precedence)
    sources = resolver.list_available_sources()
    if name in sources:
        labels = {
            "local": "Local tools.py",
            "external": "praisonai-tools package",
            "registered": "Registered/entry-point tool (registry)",
            "builtin": "praisonaiagents.tools (built-in)",
        }
        console.print(f"\n[blue]Source:[/blue] {labels.get(sources[name], labels['builtin'])}")


def _resolve_installer(global_env: bool = False):
    """Resolve the installer command, honouring how PraisonAI was installed.

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


@app.command("add")
def tools_add(
    package: str = typer.Argument(..., help="Tool package to install (pip requirement spec)"),
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
    """Install a tool package and verify its tools become available.

    Installs the package into the active environment, refreshes tool
    discovery, and reports exactly which tools became available — or a clear
    error if nothing new was discovered.

    Examples:
        praisonai tools add praisonai-my-tools
        praisonai tools add praisonai-my-tools --upgrade
        praisonai tools add praisonai-my-tools --dry-run
    """
    from praisonai_code.tool_resolver import ToolResolver

    resolver = ToolResolver()
    before = set(resolver.list_available().keys())

    if not dry_run:
        import importlib
        import subprocess

        cmd = _resolve_installer(global_env)
        if upgrade:
            cmd = cmd + ["--upgrade"]
        cmd = cmd + [package]
        console.print(f"Installing {package} ...")
        result = subprocess.run(cmd)
        if result.returncode != 0:
            console.print(f"[red]Error: installation failed for '{package}'.[/red]")
            raise typer.Exit(1)
        # A package installed into the running interpreter is only importable
        # after the finder caches are refreshed; otherwise discovery below can
        # miss the just-installed distribution.
        importlib.invalidate_caches()

    # Use a fresh resolver so instance-level availability caches (e.g. whether
    # ``praisonai_tools`` is importable) are re-evaluated against the now-updated
    # environment; ``invalidate()`` only clears the per-name resolution cache.
    resolver = ToolResolver()
    available = resolver.list_available()
    after = set(available.keys())
    new_names = sorted(after - before)

    if not new_names:
        console.print(
            f"[yellow]No new tools were registered by '{escape(package)}'.[/yellow]\n"
            "[dim]The package installed but exposed no discoverable tools, "
            "or an entry point failed to load. Run 'praisonai tools list' to inspect.[/dim]"
        )
        raise typer.Exit(1)

    sources = resolver.list_available_sources()
    verb = "Discovered" if dry_run else "Registered"
    table = Table(
        title=f"{verb} {len(new_names)} tool(s) from {escape(package)}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Tool Name", style="green")
    table.add_column("Source", style="blue")

    for name in new_names:
        table.add_row(name, sources.get(name, "builtin"))

    console.print(table)


@app.command("test")
def tools_test(
    name: str = typer.Argument(..., help="Tool name to test"),
):
    """Test a tool with a simple invocation."""
    from praisonai_code.tool_resolver import ToolResolver
    
    resolver = ToolResolver()
    tool = resolver.resolve(name)
    
    if tool is None:
        console.print(f"[red]Tool '{name}' not found.[/red]")
        raise typer.Exit(1)
    
    console.print(f"[green]✓ Tool '{name}' resolved successfully![/green]")
    console.print(f"[dim]Type: {type(tool).__name__}[/dim]")
    console.print(f"[dim]Callable: {callable(tool)}[/dim]")
