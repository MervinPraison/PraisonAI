"""
MCP Server CLI Integration

Provides CLI commands for managing the MCP server:
- praisonai mcp serve --transport stdio|http-stream
- praisonai mcp list-tools
- praisonai mcp config-generate
"""

import argparse
import json
import logging
import sys
from typing import List

logger = logging.getLogger(__name__)


class MCPServerCLI:
    """CLI handler for MCP server commands."""
    
    EXIT_SUCCESS = 0
    EXIT_ERROR = 1
    
    def __init__(self):
        """Initialize CLI handler."""
        self._server = None
    
    def handle(self, args: List[str]) -> int:
        """
        Handle MCP CLI subcommand.
        
        Args:
            args: Command arguments
            
        Returns:
            Exit code
        """
        if not args:
            self._print_help()
            return self.EXIT_SUCCESS
        
        command = args[0]
        remaining = args[1:]
        
        commands = {
            "serve": self.cmd_serve,
            "serve-recipe": self.cmd_serve_recipe,
            "list-tools": self.cmd_list_tools,
            "list-resources": self.cmd_list_resources,
            "list-prompts": self.cmd_list_prompts,
            "list-recipes": self.cmd_list_recipes,
            "tools": self.cmd_tools,  # New: tools subcommand
            "validate-recipe": self.cmd_validate_recipe,
            "inspect-recipe": self.cmd_inspect_recipe,
            "config-generate": self.cmd_config_generate,
            "config-generate-recipe": self.cmd_config_generate_recipe,
            "auth": self.cmd_auth,
            "tasks": self.cmd_tasks,
            "doctor": self.cmd_doctor,
            "help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "--help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "-h": lambda _: self._print_help() or self.EXIT_SUCCESS,
        }
        
        if command in commands:
            return commands[command](remaining)
        else:
            self._print_error(f"Unknown command: {command}")
            self._print_help()
            return self.EXIT_ERROR
    
    def _print_help(self) -> None:
        """Print help message."""
        help_text = """
[bold cyan]PraisonAI MCP Server (Protocol Version 2025-11-25)[/bold cyan]

Run PraisonAI as an MCP server for Claude Desktop, Cursor, Windsurf, and other MCP clients.

[bold]Usage:[/bold]
  praisonai mcp <command> [options]

[bold]Commands:[/bold]
  serve             Start the MCP server
  serve-recipe      Serve a recipe as MCP server
  list-tools        List available MCP tools
  list-resources    List available MCP resources
  list-prompts      List available MCP prompts
  list-recipes      List available recipes
  tools             Tool management commands (search, info, schema)
  validate-recipe   Validate recipe MCP compatibility
  inspect-recipe    Inspect recipe MCP schema
  config-generate   Generate client configuration
  config-generate-recipe  Generate config for recipe server
  auth              Authentication commands
  tasks             Tasks API commands
  doctor            Check MCP server health

[bold]Serve Options:[/bold]
  --transport <type>      Transport: stdio (default) or http-stream
  --host <host>           HTTP host (default: 127.0.0.1)
  --port <port>           HTTP port (default: 8080)
  --endpoint <path>       HTTP endpoint (default: /mcp)
  --api-key <key>         API key for authentication
  --name <name>           Server name (default: praisonai)
  --response-mode <mode>  Response mode: batch (default) or stream
  --cors-origins <list>   Comma-separated CORS origins
  --allowed-origins <list> Comma-separated allowed origins for security
  --session-ttl <secs>    Session TTL in seconds (default: 3600)
  --no-termination        Disable client session termination
  --resumability          Enable SSE resumability (default: true)
  --log-level <level>     Log level: debug, info, warning, error
  --json                  Output in JSON format

[bold]Config Generate Options:[/bold]
  --client <name>       Client type: claude-desktop, cursor, vscode, windsurf
  --output <path>       Output file path
  --transport <type>    Transport for config

[bold]Examples:[/bold]
  # Start STDIO server (for Claude Desktop)
  praisonai mcp serve --transport stdio

  # Start HTTP Stream server with authentication
  praisonai mcp serve --transport http-stream --port 8080 --api-key mykey

  # Start with custom allowed origins
  praisonai mcp serve --transport http-stream --allowed-origins "http://localhost:3000"

  # Generate Claude Desktop config
  praisonai mcp config-generate --client claude-desktop

  # List available tools
  praisonai mcp list-tools

  # Check MCP server health
  praisonai mcp doctor

[bold]Recipe Server Examples:[/bold]
  # Serve a recipe as STDIO MCP server
  praisonai mcp serve-recipe support-reply --transport stdio

  # Serve with HTTP Stream transport
  praisonai mcp serve-recipe ai-video-editor --transport http-stream --port 8080

  # Generate config for recipe server
  praisonai mcp config-generate-recipe support-reply --client claude-desktop
"""
        self._print_rich(help_text)
    
    def _print_rich(self, text: str) -> None:
        """Print with rich formatting if available."""
        try:
            from rich import print as rprint
            rprint(text)
        except ImportError:
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', text)
            print(plain)
    
    def _print_error(self, message: str) -> None:
        """Print error message."""
        try:
            from rich import print as rprint
            rprint(f"[red]Error: {message}[/red]")
        except ImportError:
            print(f"Error: {message}", file=sys.stderr)
    
    def _print_success(self, message: str) -> None:
        """Print success message."""
        try:
            from rich import print as rprint
            rprint(f"[green]✓ {message}[/green]")
        except ImportError:
            print(f"✓ {message}")
    
    def cmd_serve(self, args: List[str]) -> int:
        """Start the MCP server."""
        parser = argparse.ArgumentParser(prog="praisonai mcp serve")
        parser.add_argument("--transport", default="stdio", choices=["stdio", "http-stream"])
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8080)
        parser.add_argument("--endpoint", default="/mcp")
        parser.add_argument("--api-key", default=None)
        parser.add_argument("--name", default="praisonai")
        parser.add_argument("--debug", action="store_true")
        parser.add_argument("--response-mode", default="batch", choices=["batch", "stream"])
        parser.add_argument("--cors-origins", default=None, help="Comma-separated CORS origins")
        parser.add_argument("--allowed-origins", default=None, help="Comma-separated allowed origins for security")
        parser.add_argument("--session-ttl", type=int, default=3600, help="Session TTL in seconds")
        parser.add_argument("--allow-termination", action="store_true", default=True, help="Allow client session termination")
        parser.add_argument("--no-termination", action="store_true", help="Disable client session termination")
        parser.add_argument("--resumability", action="store_true", default=True, help="Enable SSE resumability")
        parser.add_argument("--log-level", default="warning", choices=["debug", "info", "warning", "error"])
        parser.add_argument("--json", action="store_true", help="Output in JSON format")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        # Configure logging
        log_levels = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
        }
        log_level = log_levels.get(parsed.log_level, logging.WARNING)
        if parsed.debug:
            log_level = logging.DEBUG
        logging.basicConfig(level=log_level, stream=sys.stderr)
        
        try:
            from .server import MCPServer
            from .adapters import register_all
            
            # Register all tools, resources, and prompts
            register_all()
            
            # Create server
            server = MCPServer(
                name=parsed.name,
                instructions="PraisonAI MCP Server - AI agent capabilities exposed via MCP protocol.",
            )
            
            if parsed.transport == "stdio":
                # STDIO mode - minimal output to stderr
                logger.info(f"Starting MCP server '{parsed.name}' on STDIO transport")
                server.run_stdio()
            else:
                # HTTP Stream mode
                cors_origins = parsed.cors_origins.split(",") if parsed.cors_origins else None
                allowed_origins = parsed.allowed_origins.split(",") if parsed.allowed_origins else None
                allow_termination = not parsed.no_termination
                
                if not parsed.json:
                    self._print_success(f"Starting MCP server '{parsed.name}' on http://{parsed.host}:{parsed.port}{parsed.endpoint}")
                
                server.run_http_stream(
                    host=parsed.host,
                    port=parsed.port,
                    endpoint=parsed.endpoint,
                    api_key=parsed.api_key,
                    cors_origins=cors_origins,
                    allowed_origins=allowed_origins,
                    session_ttl=parsed.session_ttl,
                    allow_client_termination=allow_termination,
                    response_mode=parsed.response_mode,
                    resumability_enabled=parsed.resumability,
                )
            
            return self.EXIT_SUCCESS
            
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            print("Install with: pip install praisonai[mcp]", file=sys.stderr)
            return self.EXIT_ERROR
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
            return self.EXIT_SUCCESS
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_list_tools(self, args: List[str]) -> int:
        """List available MCP tools."""
        parser = argparse.ArgumentParser(prog="praisonai mcp list-tools")
        parser.add_argument("--json", action="store_true", help="Output in JSON format")
        parser.add_argument("--cursor", default=None, help="Pagination cursor")
        parser.add_argument("--limit", type=int, default=50, help="Max tools to show")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .adapters import register_all_tools
            from .registry import get_tool_registry
            
            # Register all tools
            register_all_tools()
            
            registry = get_tool_registry()
            tools, next_cursor = registry.list_paginated(
                cursor=parsed.cursor,
                page_size=parsed.limit
            )
            
            if parsed.json:
                result = {"tools": tools}
                if next_cursor:
                    result["nextCursor"] = next_cursor
                print(json.dumps(result, indent=2))
                return self.EXIT_SUCCESS
            
            if not tools:
                print("No tools registered")
                return self.EXIT_SUCCESS
            
            total = len(registry.list_all())
            self._print_rich(f"\n[bold]Available MCP Tools ({len(tools)} of {total}):[/bold]\n")
            for tool in tools:
                name = tool.get("name", "unknown")
                desc = tool.get("description", "No description")
                annotations = tool.get("annotations", {})
                hints = []
                if annotations.get("readOnlyHint"):
                    hints.append("read-only")
                if annotations.get("destructiveHint"):
                    hints.append("destructive")
                hint_str = f" [{', '.join(hints)}]" if hints else ""
                print(f"  • {name}{hint_str}")
                print(f"    {desc}\n")
            
            if next_cursor:
                print(f"[dim]More results available. Use --cursor {next_cursor}[/dim]\n")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_tools(self, args: List[str]) -> int:
        """Handle tools subcommands: search, info, schema."""
        if not args:
            self._print_tools_help()
            return self.EXIT_SUCCESS
        
        subcommand = args[0]
        remaining = args[1:]
        
        subcommands = {
            "search": self.cmd_tools_search,
            "info": self.cmd_tools_info,
            "schema": self.cmd_tools_schema,
            "list": lambda a: self.cmd_list_tools(a),
            "help": lambda _: self._print_tools_help() or self.EXIT_SUCCESS,
            "--help": lambda _: self._print_tools_help() or self.EXIT_SUCCESS,
            "-h": lambda _: self._print_tools_help() or self.EXIT_SUCCESS,
        }
        
        if subcommand in subcommands:
            return subcommands[subcommand](remaining)
        else:
            self._print_error(f"Unknown tools subcommand: {subcommand}")
            self._print_tools_help()
            return self.EXIT_ERROR
    
    def _print_tools_help(self) -> None:
        """Print tools subcommand help."""
        help_text = """
[bold cyan]PraisonAI MCP Tools Management[/bold cyan]

[bold]Usage:[/bold]
  praisonai mcp tools <subcommand> [options]

[bold]Subcommands:[/bold]
  search    Search tools by query, category, or tags
  info      Get detailed information about a tool
  schema    Get the JSON schema for a tool
  list      List all tools (alias for list-tools)

[bold]Search Options:[/bold]
  praisonai mcp tools search "<query>" [options]
    --category <cat>    Filter by category
    --tag <tag>         Filter by tag (can repeat)
    --read-only         Show only read-only tools
    --json              Output in JSON format
    --limit <n>         Max results (default: 50)
    --cursor <cursor>   Pagination cursor

[bold]Info Options:[/bold]
  praisonai mcp tools info <tool-name>
    --json              Output in JSON format

[bold]Schema Options:[/bold]
  praisonai mcp tools schema <tool-name>
    --json              Output in JSON format (default)

[bold]Examples:[/bold]
  # Search for web-related tools
  praisonai mcp tools search "web"

  # Search read-only tools in memory category
  praisonai mcp tools search --category memory --read-only

  # Get tool info
  praisonai mcp tools info praisonai.memory.show

  # Get tool schema
  praisonai mcp tools schema praisonai.workflow.run
"""
        self._print_rich(help_text)
    
    def cmd_tools_search(self, args: List[str]) -> int:
        """Search tools by query, category, or tags."""
        parser = argparse.ArgumentParser(prog="praisonai mcp tools search")
        parser.add_argument("query", nargs="?", default=None, help="Search query")
        parser.add_argument("--category", default=None, help="Filter by category")
        parser.add_argument("--tag", action="append", dest="tags", help="Filter by tag")
        parser.add_argument("--read-only", action="store_true", help="Show only read-only tools")
        parser.add_argument("--json", action="store_true", help="Output in JSON format")
        parser.add_argument("--limit", type=int, default=50, help="Max results")
        parser.add_argument("--cursor", default=None, help="Pagination cursor")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .adapters import register_all_tools
            from .registry import get_tool_registry
            
            register_all_tools()
            registry = get_tool_registry()
            
            read_only = True if parsed.read_only else None
            
            tools, next_cursor, total = registry.search(
                query=parsed.query,
                category=parsed.category,
                tags=parsed.tags,
                read_only=read_only,
                cursor=parsed.cursor,
                page_size=parsed.limit,
            )
            
            if parsed.json:
                result = {"tools": tools, "total": total}
                if next_cursor:
                    result["nextCursor"] = next_cursor
                print(json.dumps(result, indent=2))
                return self.EXIT_SUCCESS
            
            if not tools:
                print("No tools found matching your criteria")
                return self.EXIT_SUCCESS
            
            self._print_rich(f"\n[bold]Search Results ({len(tools)} of {total}):[/bold]\n")
            for tool in tools:
                name = tool.get("name", "unknown")
                desc = tool.get("description", "No description")
                annotations = tool.get("annotations", {})
                hints = []
                if annotations.get("readOnlyHint"):
                    hints.append("read-only")
                if annotations.get("destructiveHint"):
                    hints.append("destructive")
                hint_str = f" [{', '.join(hints)}]" if hints else ""
                print(f"  • {name}{hint_str}")
                print(f"    {desc}\n")
            
            if next_cursor:
                print(f"[dim]More results available. Use --cursor {next_cursor}[/dim]\n")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_tools_info(self, args: List[str]) -> int:
        """Get detailed information about a tool."""
        parser = argparse.ArgumentParser(prog="praisonai mcp tools info")
        parser.add_argument("name", help="Tool name")
        parser.add_argument("--json", action="store_true", help="Output in JSON format")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .adapters import register_all_tools
            from .registry import get_tool_registry
            
            register_all_tools()
            registry = get_tool_registry()
            
            tool = registry.get(parsed.name)
            if tool is None:
                self._print_error(f"Tool not found: {parsed.name}")
                return self.EXIT_ERROR
            
            schema = tool.to_mcp_schema()
            
            if parsed.json:
                print(json.dumps(schema, indent=2))
                return self.EXIT_SUCCESS
            
            self._print_rich(f"\n[bold cyan]Tool: {tool.name}[/bold cyan]\n")
            print(f"[bold]Description:[/bold] {tool.description}")
            
            annotations = schema.get("annotations", {})
            print("\n[bold]Annotations:[/bold]")
            print(f"  • readOnlyHint: {annotations.get('readOnlyHint', False)}")
            print(f"  • destructiveHint: {annotations.get('destructiveHint', True)}")
            print(f"  • idempotentHint: {annotations.get('idempotentHint', False)}")
            print(f"  • openWorldHint: {annotations.get('openWorldHint', True)}")
            
            if tool.category:
                print(f"  • category: {tool.category}")
            if tool.tags:
                print(f"  • tags: {', '.join(tool.tags)}")
            
            input_schema = schema.get("inputSchema", {})
            props = input_schema.get("properties", {})
            required = input_schema.get("required", []) or []
            
            if props:
                print("\n[bold]Parameters:[/bold]")
                for param_name, param_info in props.items():
                    req = " (required)" if param_name in required else ""
                    ptype = param_info.get("type", "any")
                    pdesc = param_info.get("description", "")
                    print(f"  • {param_name}: {ptype}{req}")
                    if pdesc:
                        print(f"    {pdesc}")
            
            print()
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_tools_schema(self, args: List[str]) -> int:
        """Get the JSON schema for a tool."""
        parser = argparse.ArgumentParser(prog="praisonai mcp tools schema")
        parser.add_argument("name", help="Tool name")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .adapters import register_all_tools
            from .registry import get_tool_registry
            
            register_all_tools()
            registry = get_tool_registry()
            
            tool = registry.get(parsed.name)
            if tool is None:
                self._print_error(f"Tool not found: {parsed.name}")
                return self.EXIT_ERROR
            
            schema = tool.to_mcp_schema()
            print(json.dumps(schema, indent=2))
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_list_resources(self, args: List[str]) -> int:
        """List available MCP resources."""
        try:
            from .registry import get_resource_registry
            
            registry = get_resource_registry()
            resources = registry.list_schemas()
            
            if not resources:
                print("No resources registered")
                return self.EXIT_SUCCESS
            
            print(f"\n[bold]Available MCP Resources ({len(resources)}):[/bold]\n")
            for res in resources:
                uri = res.get("uri", "unknown")
                desc = res.get("description", "No description")
                print(f"  • {uri}")
                print(f"    {desc}\n")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_list_prompts(self, args: List[str]) -> int:
        """List available MCP prompts."""
        try:
            from .registry import get_prompt_registry
            
            registry = get_prompt_registry()
            prompts = registry.list_schemas()
            
            if not prompts:
                print("No prompts registered")
                return self.EXIT_SUCCESS
            
            print(f"\n[bold]Available MCP Prompts ({len(prompts)}):[/bold]\n")
            for prompt in prompts:
                name = prompt.get("name", "unknown")
                desc = prompt.get("description", "No description")
                print(f"  • {name}")
                print(f"    {desc}\n")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_config_generate(self, args: List[str]) -> int:
        """Generate client configuration."""
        parser = argparse.ArgumentParser(prog="praisonai mcp config-generate")
        parser.add_argument("--client", default="claude-desktop", 
                          choices=["claude-desktop", "cursor", "vscode", "windsurf"])
        parser.add_argument("--output", default=None)
        parser.add_argument("--transport", default="stdio", choices=["stdio", "http-stream"])
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8080)
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        # Generate config based on client type
        if parsed.client == "claude-desktop":
            config = self._generate_claude_desktop_config(parsed)
        elif parsed.client == "cursor":
            config = self._generate_cursor_config(parsed)
        elif parsed.client == "vscode":
            config = self._generate_vscode_config(parsed)
        elif parsed.client == "windsurf":
            config = self._generate_windsurf_config(parsed)
        else:
            config = self._generate_claude_desktop_config(parsed)
        
        # Output config
        config_json = json.dumps(config, indent=2)
        
        if parsed.output:
            with open(parsed.output, 'w') as f:
                f.write(config_json)
            self._print_success(f"Config written to {parsed.output}")
        else:
            print(f"\n[bold]{parsed.client} Configuration:[/bold]\n")
            print(config_json)
            print()
        
        return self.EXIT_SUCCESS
    
    def _generate_claude_desktop_config(self, args) -> dict:
        """Generate Claude Desktop config."""
        if args.transport == "stdio":
            return {
                "mcpServers": {
                    "praisonai": {
                        "command": "praisonai",
                        "args": ["mcp", "serve", "--transport", "stdio"],
                    }
                }
            }
        else:
            return {
                "mcpServers": {
                    "praisonai": {
                        "url": f"http://{args.host}:{args.port}/mcp",
                        "transport": "http-stream",
                    }
                }
            }
    
    def _generate_cursor_config(self, args) -> dict:
        """Generate Cursor config."""
        if args.transport == "stdio":
            return {
                "mcpServers": {
                    "praisonai": {
                        "command": "praisonai",
                        "args": ["mcp", "serve", "--transport", "stdio"],
                    }
                }
            }
        else:
            return {
                "mcpServers": {
                    "praisonai": {
                        "url": f"http://{args.host}:{args.port}/mcp",
                    }
                }
            }
    
    def _generate_vscode_config(self, args) -> dict:
        """Generate VSCode MCP config."""
        if args.transport == "stdio":
            return {
                "mcp.servers": {
                    "praisonai": {
                        "command": "praisonai",
                        "args": ["mcp", "serve", "--transport", "stdio"],
                    }
                }
            }
        else:
            return {
                "mcp.servers": {
                    "praisonai": {
                        "url": f"http://{args.host}:{args.port}/mcp",
                    }
                }
            }
    
    def _generate_windsurf_config(self, args) -> dict:
        """Generate Windsurf config."""
        return self._generate_cursor_config(args)
    
    def cmd_doctor(self, args: List[str]) -> int:
        """Check MCP server health and configuration."""
        try:
            from .server import PROTOCOL_VERSION, SUPPORTED_VERSIONS
            from .registry import get_tool_registry, get_resource_registry, get_prompt_registry
            from .adapters import register_all
            
            print("\n[bold cyan]PraisonAI MCP Server Health Check[/bold cyan]\n")
            
            # Register all components
            register_all()
            
            # Check protocol version
            print(f"[bold]Protocol Version:[/bold] {PROTOCOL_VERSION}")
            print(f"[bold]Supported Versions:[/bold] {', '.join(SUPPORTED_VERSIONS)}")
            print()
            
            # Check registries
            tools = get_tool_registry().list_all()
            resources = get_resource_registry().list_all()
            prompts = get_prompt_registry().list_all()
            
            print("[bold]Registered Components:[/bold]")
            print(f"  • Tools: {len(tools)}")
            print(f"  • Resources: {len(resources)}")
            print(f"  • Prompts: {len(prompts)}")
            print()
            
            # Check environment
            import os
            env_checks = {
                "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
                "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
                "GOOGLE_API_KEY": bool(os.environ.get("GOOGLE_API_KEY")),
            }
            
            print("[bold]Environment:[/bold]")
            for key, present in env_checks.items():
                status = "[green]✓[/green]" if present else "[yellow]○[/yellow]"
                print(f"  {status} {key}")
            print()
            
            # Check dependencies
            deps = {
                "starlette": False,
                "uvicorn": False,
                "praisonaiagents": False,
            }
            
            for dep in deps:
                try:
                    __import__(dep)
                    deps[dep] = True
                except ImportError:
                    pass
            
            print("[bold]Dependencies:[/bold]")
            for dep, available in deps.items():
                status = "[green]✓[/green]" if available else "[red]✗[/red]"
                print(f"  {status} {dep}")
            print()
            
            # Overall status
            all_deps = all(deps.values())
            any_api_key = any(env_checks.values())
            
            if all_deps and any_api_key:
                self._print_success("MCP server is ready to run")
            elif not all_deps:
                self._print_error("Missing required dependencies. Install with: pip install praisonai[mcp]")
                return self.EXIT_ERROR
            else:
                print("[yellow]Warning: No API keys configured. Some tools may not work.[/yellow]")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR


    def cmd_serve_recipe(self, args: List[str]) -> int:
        """Serve a recipe as MCP server."""
        from .recipe_cli import RecipeMCPCLI
        cli = RecipeMCPCLI()
        return cli.cmd_serve_recipe(args)
    
    def cmd_list_recipes(self, args: List[str]) -> int:
        """List available recipes."""
        from .recipe_cli import RecipeMCPCLI
        cli = RecipeMCPCLI()
        return cli.cmd_list_recipes(args)
    
    def cmd_validate_recipe(self, args: List[str]) -> int:
        """Validate recipe MCP compatibility."""
        from .recipe_cli import RecipeMCPCLI
        cli = RecipeMCPCLI()
        return cli.cmd_validate_recipe(args)
    
    def cmd_inspect_recipe(self, args: List[str]) -> int:
        """Inspect recipe MCP schema."""
        from .recipe_cli import RecipeMCPCLI
        cli = RecipeMCPCLI()
        return cli.cmd_inspect_recipe(args)
    
    def cmd_config_generate_recipe(self, args: List[str]) -> int:
        """Generate client config for recipe server."""
        from .recipe_cli import RecipeMCPCLI
        cli = RecipeMCPCLI()
        return cli.cmd_config_generate_recipe(args)
    
    def cmd_auth(self, args: List[str]) -> int:
        """Handle auth subcommands."""
        from .recipe_cli import RecipeMCPCLI
        cli = RecipeMCPCLI()
        return cli.cmd_auth(args)
    
    def cmd_tasks(self, args: List[str]) -> int:
        """Handle tasks subcommands."""
        from .recipe_cli import RecipeMCPCLI
        cli = RecipeMCPCLI()
        return cli.cmd_tasks(args)


def handle_mcp_command(args: List[str]) -> int:
    """
    Entry point for MCP CLI commands.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    cli = MCPServerCLI()
    return cli.handle(args)
