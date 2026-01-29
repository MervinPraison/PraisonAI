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
    from ..configuration.schema import MCPLocalConfig, MCPRemoteConfig
    
    output = get_output_controller()
    loader = get_config_loader()
    
    config = loader.load()
    servers = config.mcp.servers
    
    if output.is_json_mode or json_output:
        server_data = {}
        for name, s in servers.items():
            if isinstance(s, MCPRemoteConfig):
                server_data[name] = {
                    "type": "remote",
                    "url": s.url,
                    "enabled": s.enabled,
                }
            else:
                server_data[name] = {
                    "type": "local",
                    "command": s.command,
                    "args": s.args,
                    "enabled": s.enabled,
                }
        output.print_json({"servers": server_data})
        return
    
    if not servers:
        output.print_info("No MCP servers configured")
        output.print("\nAdd a server with: praisonai mcp add <name> <command>")
        return
    
    headers = ["Name", "Type", "Target", "Enabled"]
    rows = []
    for name, server in servers.items():
        if isinstance(server, MCPRemoteConfig):
            target = server.url
            server_type = "remote"
        else:
            target = f"{server.command} {' '.join(server.args)}"
            server_type = "local"
        if len(target) > 45:
            target = target[:42] + "..."
        rows.append([name, server_type, target, "✓" if server.enabled else "✗"])
    
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
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Timeout in seconds"),
):
    """Sync tool schemas from MCP servers to local index."""
    output = get_output_controller()
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
    synced_servers = []
    failed_servers = []
    
    for srv in servers_to_sync:
        output.print_info(f"Syncing {srv}...")
        srv_config = config.mcp.servers[srv]
        
        try:
            # Actually connect to MCP server and fetch tools
            from praisonaiagents.mcp import MCP
            
            # Build command string
            cmd_parts = [srv_config.command] + srv_config.args
            cmd_string = " ".join(cmd_parts)
            
            # Create MCP instance with env vars
            mcp = MCP(cmd_string, timeout=int(timeout), env=srv_config.env or {})
            
            # Get tools
            tools = mcp.get_tools()
            openai_tools = mcp.to_openai_tool() or []
            
            tool_count = len(tools)
            total_tools += tool_count
            synced_servers.append(srv)
            
            output.print(f"  Found {tool_count} tools:")
            for tool_def in openai_tools:
                if isinstance(tool_def, dict) and "function" in tool_def:
                    name = tool_def["function"].get("name", "unknown")
                    desc = tool_def["function"].get("description", "")[:40]
                    output.print(f"    - {name}: {desc}...")
            
            # Clean up
            mcp.shutdown()
            
        except ImportError:
            output.print_error("  MCP package not installed. Install with: pip install praisonaiagents[mcp]")
            failed_servers.append(srv)
        except Exception as e:
            output.print_error(f"  Failed to sync: {e}")
            failed_servers.append(srv)
    
    # Summary
    if output.is_json_mode:
        output.print_json({
            "synced_servers": synced_servers,
            "failed_servers": failed_servers,
            "total_tools": total_tools
        })
    else:
        if synced_servers:
            output.print_success(f"Synced {len(synced_servers)} server(s), {total_tools} tools total")
        if failed_servers:
            output.print_error(f"Failed to sync {len(failed_servers)} server(s): {', '.join(failed_servers)}")


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


@app.command("run")
def mcp_run(
    name: str = typer.Argument(..., help="Server name to run"),
    port: int = typer.Option(8080, "--port", "-p", help="Port for SSE transport"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    transport: str = typer.Option("stdio", "--transport", "-T", help="Transport type: stdio or sse"),
):
    """Run an MCP server from configuration.
    
    DEPRECATED: Use `praisonai serve mcp --name <server>` instead.
    
    This command starts an MCP server using the configuration stored
    for the given server name. It can run in stdio mode (default) or
    as an SSE server.
    
    Examples:
        praisonai mcp run my-server
        praisonai mcp run my-server --transport sse --port 8080
    """
    import sys
    
    # Print deprecation warning
    print("\n\033[93m⚠ DEPRECATION WARNING:\033[0m", file=sys.stderr)
    print("\033[93m'praisonai mcp run' is deprecated and will be removed in a future version.\033[0m", file=sys.stderr)
    print("\033[93mPlease use 'praisonai serve mcp --name <server>' instead.\033[0m\n", file=sys.stderr)
    
    output = get_output_controller()
    loader = get_config_loader()
    
    config = loader.load()
    if name not in config.mcp.servers:
        output.print_error(f"Server not found: {name}")
        raise typer.Exit(1)
    
    server = config.mcp.servers[name]
    
    if transport not in ("stdio", "sse"):
        output.print_error(f"Invalid transport: {transport}. Use 'stdio' or 'sse'")
        raise typer.Exit(1)
    
    output.print_info(f"Starting MCP server: {name}")
    output.print(f"  Command: {server.command} {' '.join(server.args)}")
    output.print(f"  Transport: {transport}")
    
    if transport == "sse":
        output.print(f"  Endpoint: http://{host}:{port}/sse")
    
    import subprocess
    import os
    import sys
    
    try:
        cmd = [server.command] + server.args
        
        # Build environment
        env = os.environ.copy()
        if server.env:
            env.update(server.env)
        
        if transport == "stdio":
            # Run in stdio mode - pass through stdin/stdout
            output.print_info("Running in stdio mode. Press Ctrl+C to stop.")
            proc = subprocess.Popen(
                cmd,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
                env=env,
            )
            proc.wait()
        else:
            # SSE mode - would need to wrap the server
            # For now, just run the server and let it handle SSE
            output.print_info(f"Running in SSE mode on http://{host}:{port}")
            output.print_info("Press Ctrl+C to stop.")
            
            # Try to use praisonaiagents MCP server wrapper
            try:
                from praisonaiagents.mcp import MCP
                
                # Build command string
                cmd_string = " ".join(cmd)
                mcp = MCP(cmd_string, timeout=60, env=server.env or {})
                
                # Get tools and expose via SSE
                tools = mcp.get_tools()
                output.print(f"  Exposing {len(tools)} tools via SSE")
                
                # Use ToolsMCPServer to expose tools
                from praisonaiagents.mcp import ToolsMCPServer
                
                mcp_server = ToolsMCPServer(name=name, tools=tools)
                mcp_server.run_sse(host=host, port=port)
                
            except ImportError:
                output.print_error("MCP package not installed. Install with: pip install praisonaiagents[mcp]")
                raise typer.Exit(1)
            except KeyboardInterrupt:
                output.print_info("\nServer stopped.")
    
    except FileNotFoundError:
        output.print_error(f"Command not found: {server.command}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        output.print_info("\nServer stopped.")
    except Exception as e:
        output.print_error(f"Failed to start server: {e}")
        raise typer.Exit(1)


@app.command("auth")
def mcp_auth(
    name: str = typer.Argument(..., help="Server name to authenticate"),
    timeout: float = typer.Option(300.0, "--timeout", "-t", help="Timeout for OAuth flow in seconds"),
):
    """Authenticate with an OAuth-enabled MCP server.
    
    This command initiates the OAuth 2.1 authorization flow for a remote
    MCP server. It will open your browser for authentication and wait
    for the callback.
    
    Examples:
        praisonai mcp auth github
        praisonai mcp auth tavily --timeout 60
    """
    output = get_output_controller()
    loader = get_config_loader()
    
    config = loader.load()
    if name not in config.mcp.servers:
        output.print_error(f"Server not found: {name}")
        raise typer.Exit(1)
    
    server = config.mcp.servers[name]
    
    # Check if this is a remote server
    from ..configuration.schema import MCPRemoteConfig
    if not isinstance(server, MCPRemoteConfig):
        output.print_error(f"Server '{name}' is a local server. OAuth is only for remote servers.")
        raise typer.Exit(1)
    
    if not server.url:
        output.print_error(f"Server '{name}' has no URL configured.")
        raise typer.Exit(1)
    
    output.print_info(f"Authenticating with MCP server: {name}")
    output.print(f"  URL: {server.url}")
    
    try:
        from praisonaiagents.mcp import (
            MCPAuthStorage,
            OAuthCallbackHandler,
            generate_state,
            generate_code_verifier,
            generate_code_challenge,
            get_redirect_url,
        )
        import webbrowser
        
        # Initialize auth storage and callback handler
        auth_storage = MCPAuthStorage()
        callback_handler = OAuthCallbackHandler()
        
        # Generate PKCE parameters
        state = generate_state()
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)
        
        # Store state and verifier
        auth_storage.set_oauth_state(name, state)
        auth_storage.set_code_verifier(name, code_verifier)
        
        # Build authorization URL
        # Note: In a real implementation, we'd discover the auth endpoint
        # For now, we'll use a simple pattern
        redirect_uri = get_redirect_url()
        
        # Get OAuth config
        client_id = server.oauth.client_id if server.oauth else None
        scopes = " ".join(server.oauth.scopes) if server.oauth and server.oauth.scopes else ""
        
        # Build auth URL (simplified - real impl would use OIDC discovery)
        auth_url = f"{server.url}/oauth/authorize"
        auth_url += "?response_type=code"
        auth_url += f"&state={state}"
        auth_url += f"&redirect_uri={redirect_uri}"
        auth_url += f"&code_challenge={code_challenge}"
        auth_url += "&code_challenge_method=S256"
        if client_id:
            auth_url += f"&client_id={client_id}"
        if scopes:
            auth_url += f"&scope={scopes}"
        
        output.print_info("Opening browser for authentication...")
        output.print(f"  If browser doesn't open, visit: {auth_url}")
        
        # Open browser
        webbrowser.open(auth_url)
        
        output.print_info(f"Waiting for callback (timeout: {timeout}s)...")
        
        # Wait for callback
        try:
            code = callback_handler.wait_for_callback(state, timeout=timeout)
            
            # Clear temporary state
            auth_storage.clear_oauth_state(name)
            auth_storage.clear_code_verifier(name)
            
            # Store a placeholder token (real impl would exchange code for tokens)
            auth_storage.set_tokens(name, {
                "access_token": f"oauth_{code[:20]}...",
                "refresh_token": None,
            }, server_url=server.url)
            
            if output.is_json_mode:
                output.print_json({"name": name, "status": "authenticated"})
            else:
                output.print_success(f"Successfully authenticated with {name}")
                
        except TimeoutError:
            auth_storage.clear_oauth_state(name)
            auth_storage.clear_code_verifier(name)
            output.print_error(f"Authentication timed out after {timeout} seconds")
            raise typer.Exit(1)
            
    except ImportError as e:
        output.print_error(f"MCP auth modules not available: {e}")
        output.print("Install with: pip install praisonaiagents[mcp]")
        raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Authentication failed: {e}")
        raise typer.Exit(1)


@app.command("logout")
def mcp_logout(
    name: str = typer.Argument(..., help="Server name to logout from"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove OAuth credentials for an MCP server.
    
    This command clears stored OAuth tokens and client information
    for a remote MCP server.
    
    Examples:
        praisonai mcp logout github
        praisonai mcp logout tavily --yes
    """
    output = get_output_controller()
    
    try:
        from praisonaiagents.mcp import MCPAuthStorage
        
        auth_storage = MCPAuthStorage()
        
        # Check if there are credentials to remove
        entry = auth_storage.get(name)
        if not entry or not entry.get("tokens"):
            output.print_info(f"No credentials stored for: {name}")
            return
        
        if not confirm:
            confirmed = typer.confirm(f"Remove OAuth credentials for '{name}'?")
            if not confirmed:
                output.print_info("Cancelled")
                raise typer.Exit(0)
        
        # Remove credentials
        auth_storage.remove(name)
        
        if output.is_json_mode:
            output.print_json({"name": name, "status": "logged_out"})
        else:
            output.print_success(f"Removed OAuth credentials for: {name}")
            
    except ImportError as e:
        output.print_error(f"MCP auth modules not available: {e}")
        raise typer.Exit(1)
    except Exception as e:
        output.print_error(f"Logout failed: {e}")
        raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def mcp_callback(ctx: typer.Context):
    """Show MCP help or list servers."""
    if ctx.invoked_subcommand is None:
        mcp_list(json_output=False)
