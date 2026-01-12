"""
MCP command group for PraisonAI CLI.

Provides MCP (Model Context Protocol) server management.
"""

from typing import Optional

import typer

from ..output.console import get_output_controller
from ..configuration.loader import get_config_loader

app = typer.Typer(help="MCP server management")


@app.command("list")
def mcp_list(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List configured MCP servers."""
    output = get_output_controller()
    loader = get_config_loader()
    
    config = loader.load()
    servers = config.mcp.servers
    
    if output.is_json_mode or json_output:
        output.print_json({
            "servers": {
                name: {
                    "command": s.command,
                    "args": s.args,
                    "enabled": s.enabled,
                }
                for name, s in servers.items()
            }
        })
        return
    
    if not servers:
        output.print_info("No MCP servers configured")
        output.print("\nAdd a server with: praisonai mcp add <name> <command>")
        return
    
    headers = ["Name", "Command", "Enabled"]
    rows = []
    for name, server in servers.items():
        cmd = f"{server.command} {' '.join(server.args)}"
        if len(cmd) > 50:
            cmd = cmd[:47] + "..."
        rows.append([name, cmd, "✓" if server.enabled else "✗"])
    
    output.print_table(headers, rows, title="MCP Servers")


@app.command("add")
def mcp_add(
    name: str = typer.Argument(..., help="Server name"),
    command: str = typer.Argument(..., help="Command to run"),
    args: Optional[str] = typer.Option(None, "--args", "-a", help="Command arguments (space-separated)"),
    env: Optional[str] = typer.Option(None, "--env", "-e", help="Environment variables (KEY=VALUE,...)"),
):
    """Add an MCP server."""
    output = get_output_controller()
    loader = get_config_loader()
    
    # Parse args
    arg_list = args.split() if args else []
    
    # Parse env
    env_dict = {}
    if env:
        for pair in env.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                env_dict[key.strip()] = value.strip()
    
    # Build server config
    server_config = {
        "command": command,
        "args": arg_list,
        "env": env_dict,
        "enabled": True,
    }
    
    # Save to config
    loader.set(f"mcp.servers.{name}", server_config)
    
    if output.is_json_mode:
        output.print_json({"added": name, "config": server_config})
    else:
        output.print_success(f"Added MCP server: {name}")


@app.command("remove")
def mcp_remove(
    name: str = typer.Argument(..., help="Server name to remove"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove an MCP server."""
    output = get_output_controller()
    loader = get_config_loader()
    
    config = loader.load()
    if name not in config.mcp.servers:
        output.print_error(f"Server not found: {name}")
        raise typer.Exit(1)
    
    if not confirm:
        confirmed = typer.confirm(f"Remove MCP server '{name}'?")
        if not confirmed:
            output.print_info("Cancelled")
            raise typer.Exit(0)
    
    # Remove from config by setting to None (will be cleaned up)
    # For now, we need to reload and modify the raw config
    from ..configuration.paths import get_user_config_path
    from ..configuration.loader import _load_toml, _save_toml
    
    config_path = get_user_config_path()
    if config_path.exists():
        raw_config = _load_toml(config_path)
        if "mcp" in raw_config and "servers" in raw_config["mcp"]:
            if name in raw_config["mcp"]["servers"]:
                del raw_config["mcp"]["servers"][name]
                _save_toml(config_path, raw_config)
    
    if output.is_json_mode:
        output.print_json({"removed": name})
    else:
        output.print_success(f"Removed MCP server: {name}")


@app.command("test")
def mcp_test(
    name: str = typer.Argument(..., help="Server name to test"),
    timeout: float = typer.Option(10.0, "--timeout", "-t", help="Timeout in seconds"),
):
    """Test an MCP server connection."""
    output = get_output_controller()
    loader = get_config_loader()
    
    config = loader.load()
    if name not in config.mcp.servers:
        output.print_error(f"Server not found: {name}")
        raise typer.Exit(1)
    
    server = config.mcp.servers[name]
    
    output.print_info(f"Testing MCP server: {name}")
    output.print(f"  Command: {server.command} {' '.join(server.args)}")
    
    # Try to start the server and check if it responds
    import subprocess
    import time
    
    try:
        cmd = [server.command] + server.args
        env = dict(**server.env) if server.env else None
        
        # Start process
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        
        # Wait briefly and check if it's running
        time.sleep(0.5)
        
        if proc.poll() is None:
            # Process is running
            proc.terminate()
            proc.wait(timeout=2)
            
            if output.is_json_mode:
                output.print_json({"name": name, "status": "ok", "message": "Server started successfully"})
            else:
                output.print_success(f"Server '{name}' started successfully")
        else:
            # Process exited
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            if output.is_json_mode:
                output.print_json({"name": name, "status": "error", "message": stderr or "Server exited immediately"})
            else:
                output.print_error(f"Server exited immediately: {stderr}")
                raise typer.Exit(1)
    
    except FileNotFoundError:
        if output.is_json_mode:
            output.print_json({"name": name, "status": "error", "message": f"Command not found: {server.command}"})
        else:
            output.print_error(f"Command not found: {server.command}")
            raise typer.Exit(1)
    except Exception as e:
        if output.is_json_mode:
            output.print_json({"name": name, "status": "error", "message": str(e)})
        else:
            output.print_error(f"Test failed: {e}")
            raise typer.Exit(1)


@app.command("sync")
def mcp_sync(
    server: Optional[str] = typer.Argument(None, help="Server name (None for all)"),
):
    """Sync tool schemas from MCP servers to local index."""
    output = get_output_controller()
    
    try:
        from praisonai.mcp_server.tool_index import MCPToolIndex
        
        index = MCPToolIndex()
        loader = get_config_loader()
        config = loader.load()
        
        servers_to_sync = []
        if server:
            if server not in config.mcp.servers:
                output.print_error(f"Server not found: {server}")
                raise typer.Exit(1)
            servers_to_sync = [server]
        else:
            servers_to_sync = list(config.mcp.servers.keys())
        
        if not servers_to_sync:
            output.print_info("No MCP servers configured")
            return
        
        total_tools = 0
        for srv in servers_to_sync:
            output.print_info(f"Syncing {srv}...")
            # Note: This would need actual MCP connection to fetch tools
            # For now, we just create the index structure
            count = index.sync(srv, tools=[])
            total_tools += count
            output.print(f"  Synced {count} tools")
        
        if output.is_json_mode:
            output.print_json({"synced_servers": servers_to_sync, "total_tools": total_tools})
        else:
            output.print_success(f"Synced {len(servers_to_sync)} servers, {total_tools} tools total")
            
    except ImportError as e:
        output.print_error(f"Error: {e}")
        raise typer.Exit(1)


@app.command("tools")
def mcp_tools(
    server: Optional[str] = typer.Argument(None, help="Server name (None for all)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """List indexed MCP tools."""
    output = get_output_controller()
    
    try:
        from praisonai.mcp_server.tool_index import MCPToolIndex
        
        index = MCPToolIndex()
        
        if server:
            tools = index.list_tools(server)
            if not tools:
                output.print_info(f"No tools indexed for server: {server}")
                output.print("\nRun 'praisonai mcp sync' to index tools")
                return
        else:
            tools = index.get_all_tools()
            if not tools:
                output.print_info("No tools indexed")
                output.print("\nRun 'praisonai mcp sync' to index tools")
                return
        
        if output.is_json_mode or json_output:
            output.print_json({"tools": [t.to_dict() for t in tools]})
        else:
            headers = ["Server", "Tool", "Description"]
            rows = [[t.server, t.name, t.hint[:50] + "..." if len(t.hint) > 50 else t.hint] for t in tools]
            output.print_table(headers, rows, title=f"MCP Tools ({len(tools)} total)")
            
    except ImportError as e:
        output.print_error(f"Error: {e}")
        raise typer.Exit(1)


@app.command("describe")
def mcp_describe(
    server: str = typer.Argument(..., help="Server name"),
    tool: str = typer.Argument(..., help="Tool name"),
):
    """Show full schema for an MCP tool."""
    output = get_output_controller()
    
    try:
        from praisonai.mcp_server.tool_index import MCPToolIndex
        import json
        
        index = MCPToolIndex()
        schema = index.describe(server, tool)
        
        if not schema:
            output.print_error(f"Tool not found: {server}/{tool}")
            raise typer.Exit(1)
        
        if output.is_json_mode:
            output.print_json(schema)
        else:
            output.print(json.dumps(schema, indent=2))
            
    except ImportError as e:
        output.print_error(f"Error: {e}")
        raise typer.Exit(1)


@app.command("status")
def mcp_status(
    server: Optional[str] = typer.Argument(None, help="Server name (None for all)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show status of MCP servers."""
    output = get_output_controller()
    
    try:
        from praisonai.mcp_server.tool_index import MCPToolIndex
        from datetime import datetime
        
        index = MCPToolIndex()
        
        servers = [server] if server else index.list_servers()
        
        if not servers:
            output.print_info("No servers indexed")
            return
        
        statuses = []
        for srv in servers:
            status = index.get_status(srv)
            if status:
                statuses.append(status)
        
        if output.is_json_mode or json_output:
            output.print_json({"statuses": [s.to_dict() for s in statuses]})
        else:
            headers = ["Server", "Status", "Tools", "Last Sync"]
            rows = []
            for s in statuses:
                status_str = "✓ Available" if s.available else "✗ Unavailable"
                if s.auth_required:
                    status_str += " (auth required)"
                last_sync = datetime.fromtimestamp(s.last_sync).strftime("%Y-%m-%d %H:%M") if s.last_sync else "Never"
                rows.append([s.server, status_str, str(s.tool_count), last_sync])
            
            output.print_table(headers, rows, title="MCP Server Status")
            
    except ImportError as e:
        output.print_error(f"Error: {e}")
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def mcp_callback(ctx: typer.Context):
    """Show MCP help or list servers."""
    if ctx.invoked_subcommand is None:
        mcp_list(json_output=False)
