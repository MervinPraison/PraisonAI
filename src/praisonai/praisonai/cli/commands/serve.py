"""
Serve command group for PraisonAI CLI.

Provides unified server management for ALL PraisonAI server types.
All server commands are consolidated under `praisonai serve <type>`.

Server Types:
- agents: HTTP REST API for agents
- gateway: WebSocket multi-agent coordination
- mcp: MCP server (Model Context Protocol)
- acp: ACP server (Agent Client Protocol for IDEs)
- lsp: Language Server Protocol
- ui: Web UI (Chainlit)
- rag: RAG query server
- registry: Package registry server
- docs: Documentation preview server
- scheduler: Background job scheduler
- recipe: Recipe runner server
- a2a: Agent-to-Agent protocol
- a2u: Agent-to-User event stream
- unified: All providers combined
"""

from typing import Optional
import re

import typer

from ..output.console import get_output_controller

app = typer.Typer(
    help="Unified server management - start any PraisonAI server",
    no_args_is_help=False,
)


@app.command("start")
def serve_start(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    agents_file: Optional[str] = typer.Option(None, "--agents", "-a", help="Agents YAML file"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of workers"),
):
    """Start API server."""
    output = get_output_controller()
    
    # Build args for existing handler
    args = [
        "start",
        "--host", host,
        "--port", str(port),
        "--workers", str(workers),
    ]
    
    if agents_file:
        args.extend(["--agents", agents_file])
    if reload:
        args.append("--reload")
    
    try:
        from ..features.serve import handle_serve_command
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"Serve module not available: {e}")
        raise typer.Exit(4)


@app.command("stop")
def serve_stop():
    """Stop API server."""
    output = get_output_controller()
    
    try:
        from ..features.serve import handle_serve_command
        exit_code = handle_serve_command(["stop"])
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"Serve module not available: {e}")
        raise typer.Exit(4)


@app.command("status")
def serve_status(
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Show server status."""
    output = get_output_controller()
    
    args = ["status"]
    if json_output:
        args.append("--json")
    
    try:
        from ..features.serve import handle_serve_command
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"Serve module not available: {e}")
        raise typer.Exit(4)


@app.callback(invoke_without_command=True)
def serve_callback(ctx: typer.Context):
    """Show all available serve commands."""
    if ctx.invoked_subcommand is None:
        help_text = """
[bold cyan]PraisonAI Serve - Unified Server Management[/bold cyan]

Start any PraisonAI server with: praisonai serve <type>

[bold]Server Types:[/bold]
  [green]agents[/green]      HTTP REST API for agents (port 8000)
  [green]gateway[/green]     WebSocket multi-agent coordination (port 8765)
  [green]mcp[/green]         MCP server for Claude/Cursor (port 8080)
  [green]acp[/green]         Agent Client Protocol for IDEs (STDIO)
  [green]lsp[/green]         Language Server Protocol (STDIO)
  [green]ui[/green]          Chainlit web interface (port 8082)
  [green]rag[/green]         RAG query server (port 9000)
  [green]registry[/green]    Package registry server (port 7777)
  [green]docs[/green]        Documentation preview (port 3000)
  [green]scheduler[/green]   Background job scheduler
  [green]recipe[/green]      Recipe runner server (port 8765)
  [green]a2a[/green]         Agent-to-Agent protocol (port 8001)
  [green]a2u[/green]         Agent-to-User events (port 8002)
  [green]unified[/green]     All providers combined (port 8765)

[bold]Management:[/bold]
  [yellow]start[/yellow]       Start legacy API server
  [yellow]stop[/yellow]        Stop running server
  [yellow]status[/yellow]      Show server status

[bold]Examples:[/bold]
  praisonai serve agents --port 8000
  praisonai serve gateway --port 8765
  praisonai serve mcp --transport sse
  praisonai serve unified

[bold]Discovery:[/bold]
  All HTTP servers expose /__praisonai__/discovery for endpoint discovery.
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            plain = re.sub(r'\[/?[^\]]+\]', '', help_text)
            print(plain)


# =============================================================================
# UNIFIED SERVER COMMANDS - All server types under `praisonai serve <type>`
# =============================================================================

@app.command("agents")
def serve_agents(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind to"),
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Agents YAML file"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key for authentication"),
):
    """Start agents as HTTP REST API server.
    
    Examples:
        praisonai serve agents
        praisonai serve agents --file my-agents.yaml --port 8000
    """
    try:
        from ..features.serve import handle_serve_command
        args = ["agents", "--host", host, "--port", str(port), "--file", file]
        if reload:
            args.append("--reload")
        if api_key:
            args.extend(["--api-key", api_key])
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Serve module not available: {e}")
        raise typer.Exit(4)


@app.command("gateway")
def serve_gateway(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to bind to"),
    agents_file: Optional[str] = typer.Option(None, "--agents", "-a", help="Agents YAML file"),
):
    """Start WebSocket gateway for multi-agent coordination.
    
    The gateway provides real-time bidirectional communication for
    multi-agent systems with session management.
    
    Examples:
        praisonai serve gateway
        praisonai serve gateway --port 8765 --agents agents.yaml
    """
    output = get_output_controller()
    
    try:
        from ..features.gateway import GatewayHandler
        handler = GatewayHandler()
        handler.start(host=host, port=port, agent_file=agents_file)
    except ImportError as e:
        output.print_error(f"Gateway module not available: {e}")
        output.print("Install with: pip install praisonai[api]")
        raise typer.Exit(4)


@app.command("mcp")
def serve_mcp(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8080, "--port", "-p", help="Port to bind to"),
    transport: str = typer.Option("stdio", "--transport", "-T", help="Transport: stdio, sse, http-stream"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Server name from config"),
):
    """Start MCP server (Model Context Protocol).
    
    Exposes tools to Claude Desktop, Cursor, and other MCP clients.
    
    Examples:
        praisonai serve mcp --transport stdio
        praisonai serve mcp --transport sse --port 8080
        praisonai serve mcp --name my-server
    """
    output = get_output_controller()
    
    if name:
        # Run configured server
        try:
            from ..configuration.loader import get_config_loader
            loader = get_config_loader()
            config = loader.load()
            
            if name not in config.mcp.servers:
                output.print_error(f"Server not found: {name}")
                raise typer.Exit(1)
            
            server = config.mcp.servers[name]
            import subprocess
            import os
            import sys
            
            cmd = [server.command] + server.args
            env = os.environ.copy()
            if server.env:
                env.update(server.env)
            
            output.print_info(f"Starting MCP server: {name}")
            output.print(f"  Command: {server.command} {' '.join(server.args)}")
            output.print(f"  Transport: {transport}")
            
            if transport == "stdio":
                proc = subprocess.Popen(cmd, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, env=env)
                proc.wait()
            else:
                from praisonaiagents.mcp import MCP, ToolsMCPServer
                cmd_string = " ".join(cmd)
                mcp = MCP(cmd_string, timeout=60, env=server.env or {})
                tools = mcp.get_tools()
                output.print(f"  Exposing {len(tools)} tools via {transport}")
                mcp_server = ToolsMCPServer(name=name, tools=tools)
                mcp_server.run_sse(host=host, port=port)
                
        except ImportError as e:
            output.print_error(f"MCP module not available: {e}")
            output.print("Install with: pip install praisonaiagents[mcp]")
            raise typer.Exit(4)
    else:
        # Start default MCP server
        try:
            from praisonaiagents.mcp import ToolsMCPServer
            output.print_info(f"Starting MCP server on {host}:{port}")
            output.print(f"  Transport: {transport}")
            
            mcp_server = ToolsMCPServer(name="praisonai-mcp")
            if transport == "stdio":
                mcp_server.run()
            else:
                mcp_server.run_sse(host=host, port=port)
        except ImportError as e:
            output.print_error(f"MCP module not available: {e}")
            output.print("Install with: pip install praisonaiagents[mcp]")
            raise typer.Exit(4)


@app.command("acp")
def serve_acp(
    workspace: str = typer.Option(".", "--workspace", "-w", help="Workspace root directory"),
    agent: str = typer.Option("default", "--agent", "-a", help="Agent name or config file"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model to use"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """Start ACP server (Agent Client Protocol for IDEs).
    
    Provides IDE integration for Windsurf, Cursor, and other editors.
    
    Examples:
        praisonai serve acp
        praisonai serve acp --workspace ./my-project
        praisonai serve acp --model gpt-4o
    """
    output = get_output_controller()
    
    try:
        from ..features.acp import ACPHandler
        args_list = ["--workspace", workspace, "--agent", agent]
        if model:
            args_list.extend(["--model", model])
        if debug:
            args_list.append("--debug")
        
        import argparse
        parser = argparse.ArgumentParser()
        ACPHandler.add_arguments(parser)
        args = parser.parse_args(args_list)
        exit_code = ACPHandler.handle(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"ACP module not available: {e}")
        output.print("Install with: pip install praisonai[acp]")
        raise typer.Exit(4)


@app.command("lsp")
def serve_lsp(
    language: str = typer.Option("python", "--language", "-l", help="Language server type"),
):
    """Start Language Server Protocol server.
    
    Examples:
        praisonai serve lsp
        praisonai serve lsp --language python
    """
    output = get_output_controller()
    
    try:
        from ..features.lsp_cli import handle_lsp_command
        import argparse
        args = argparse.Namespace(lsp_command="start", language=language)
        handle_lsp_command(args)
    except ImportError as e:
        output.print_error(f"LSP module not available: {e}")
        raise typer.Exit(4)


@app.command("ui")
def serve_ui(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8082, "--port", "-p", help="Port to bind to"),
    ui_type: str = typer.Option("agents", "--type", "-t", help="UI type: agents, chat, code, realtime"),
):
    """Start Chainlit web UI server.
    
    Examples:
        praisonai serve ui
        praisonai serve ui --type chat --port 8084
        praisonai serve ui --type code --port 8086
    """
    output = get_output_controller()
    
    try:
        from .ui import _launch_chainlit_ui
        _launch_chainlit_ui(ui_type, port, host, False)
    except ImportError as e:
        output.print_error(f"UI module not available: {e}")
        output.print("Install with: pip install praisonai[ui]")
        raise typer.Exit(4)


@app.command("rag")
def serve_rag(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(9000, "--port", "-p", help="Port to bind to"),
    collection: str = typer.Option("default", "--collection", "-c", help="Collection name"),
):
    """Start RAG query server.
    
    Examples:
        praisonai serve rag
        praisonai serve rag --collection research --port 9000
    """
    output = get_output_controller()
    
    try:
        from .rag import rag_serve
        # Call the existing rag serve function
        rag_serve(host=host, port=port, collection=collection)
    except ImportError as e:
        output.print_error(f"RAG module not available: {e}")
        raise typer.Exit(4)
    except Exception as e:
        output.print_error(f"Failed to start RAG server: {e}")
        raise typer.Exit(1)


@app.command("registry")
def serve_registry(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(7777, "--port", "-p", help="Port to bind to"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Authentication token"),
    read_only: bool = typer.Option(False, "--read-only", help="Read-only mode"),
):
    """Start package registry server.
    
    Examples:
        praisonai serve registry
        praisonai serve registry --port 7777 --token mysecret
    """
    output = get_output_controller()
    
    try:
        from ..features.registry import RegistryHandler
        handler = RegistryHandler()
        args = ["--host", host, "--port", str(port)]
        if token:
            args.extend(["--token", token])
        if read_only:
            args.append("--read-only")
        exit_code = handler.cmd_serve(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output.print_error(f"Registry module not available: {e}")
        raise typer.Exit(4)


@app.command("docs")
def serve_docs(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(3000, "--port", "-p", help="Port to bind to"),
    path: str = typer.Option(".", "--path", help="Documentation path"),
):
    """Start documentation preview server.
    
    Examples:
        praisonai serve docs
        praisonai serve docs --port 3000 --path ./docs
    """
    output = get_output_controller()
    
    try:
        from .docs import docs_serve
        docs_serve(host=host, port=port, path=path)
    except ImportError as e:
        output.print_error(f"Docs module not available: {e}")
        raise typer.Exit(4)
    except Exception as e:
        output.print_error(f"Failed to start docs server: {e}")
        raise typer.Exit(1)


@app.command("scheduler")
def serve_scheduler(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Scheduler config file"),
    daemon: bool = typer.Option(False, "--daemon", "-d", help="Run as daemon"),
):
    """Start background job scheduler.
    
    Examples:
        praisonai serve scheduler
        praisonai serve scheduler --config schedule.yaml --daemon
    """
    output = get_output_controller()
    
    try:
        from .schedule import schedule_start
        schedule_start(config=config, daemon=daemon)
    except ImportError as e:
        output.print_error(f"Scheduler module not available: {e}")
        raise typer.Exit(4)
    except Exception as e:
        output.print_error(f"Failed to start scheduler: {e}")
        raise typer.Exit(1)


@app.command("recipe")
def serve_recipe(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to bind to"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Config file path"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """Start recipe runner server.
    
    Examples:
        praisonai serve recipe
        praisonai serve recipe --port 8765 --reload
    """
    try:
        from ..features.serve import handle_serve_command
        args = ["recipe", "--host", host, "--port", str(port)]
        if config:
            args.extend(["--config", config])
        if reload:
            args.append("--reload")
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Recipe serve module not available: {e}")
        raise typer.Exit(4)


@app.command("a2a")
def serve_a2a(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8001, "--port", "-p", help="Port to bind to"),
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Agents YAML file"),
):
    """Start Agent-to-Agent protocol server.
    
    Enables agent-to-agent communication via JSON-RPC.
    
    Examples:
        praisonai serve a2a
        praisonai serve a2a --port 8001
    """
    try:
        from ..features.serve import handle_serve_command
        args = ["a2a", "--host", host, "--port", str(port), "--file", file]
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"A2A serve module not available: {e}")
        raise typer.Exit(4)


@app.command("a2u")
def serve_a2u(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8002, "--port", "-p", help="Port to bind to"),
):
    """Start Agent-to-User event stream server.
    
    Provides SSE event streaming for UI integration.
    
    Examples:
        praisonai serve a2u
        praisonai serve a2u --port 8002
    """
    try:
        from ..features.serve import handle_serve_command
        args = ["a2u", "--host", host, "--port", str(port)]
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"A2U serve module not available: {e}")
        raise typer.Exit(4)


@app.command("unified")
def serve_unified(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to bind to"),
    file: str = typer.Option("agents.yaml", "--file", "-f", help="Agents YAML file"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
):
    """Start unified server with all providers.
    
    Combines agents-api, recipe, mcp, a2a, and a2u in one server.
    
    Examples:
        praisonai serve unified
        praisonai serve unified --port 8765 --reload
    """
    try:
        from ..features.serve import handle_serve_command
        args = ["unified", "--host", host, "--port", str(port), "--file", file]
        if reload:
            args.append("--reload")
        exit_code = handle_serve_command(args)
        raise typer.Exit(exit_code)
    except ImportError as e:
        output = get_output_controller()
        output.print_error(f"Unified serve module not available: {e}")
        raise typer.Exit(4)
