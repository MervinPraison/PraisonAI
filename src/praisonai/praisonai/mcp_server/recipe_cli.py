"""
Recipe MCP Server CLI Commands

CLI commands for serving recipes as MCP servers.

Commands:
- serve-recipe: Serve a recipe as MCP server
- list-recipes: List available recipes for MCP serving
- validate-recipe: Validate recipe MCP compatibility
- inspect-recipe: Inspect recipe MCP schema
- config-generate-recipe: Generate client config for recipe server
"""

import argparse
import json
import logging
import sys
from typing import List

logger = logging.getLogger(__name__)


class RecipeMCPCLI:
    """CLI handler for recipe MCP server commands."""
    
    EXIT_SUCCESS = 0
    EXIT_ERROR = 1
    
    def __init__(self):
        """Initialize CLI handler."""
        pass
    
    def handle(self, args: List[str]) -> int:
        """
        Handle recipe MCP CLI subcommand.
        
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
            "serve-recipe": self.cmd_serve_recipe,
            "list-recipes": self.cmd_list_recipes,
            "validate-recipe": self.cmd_validate_recipe,
            "inspect-recipe": self.cmd_inspect_recipe,
            "config-generate-recipe": self.cmd_config_generate_recipe,
            "auth": self.cmd_auth,
            "tasks": self.cmd_tasks,
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
[bold cyan]PraisonAI Recipe MCP Server (Protocol Version 2025-11-25)[/bold cyan]

Serve PraisonAI recipes as MCP servers for Claude Desktop, Cursor, Windsurf, and other MCP clients.

[bold]Usage:[/bold]
  praisonai mcp <command> [options]

[bold]Recipe Commands:[/bold]
  serve-recipe <name>       Serve a recipe as MCP server
  list-recipes              List available recipes
  validate-recipe <name>    Validate recipe MCP compatibility
  inspect-recipe <name>     Inspect recipe MCP schema
  config-generate-recipe    Generate client config for recipe

[bold]Auth Commands:[/bold]
  auth generate-key         Generate API key
  auth validate <key>       Validate API key
  auth oidc-discover <url>  Discover OIDC configuration

[bold]Tasks Commands:[/bold]
  tasks list                List tasks
  tasks get <id>            Get task details
  tasks cancel <id>         Cancel a task

[bold]Serve Recipe Options:[/bold]
  --transport <type>        Transport: stdio (default) or http-stream
  --host <host>             HTTP host (default: 127.0.0.1)
  --port <port>             HTTP port (default: 8080)
  --endpoint <path>         HTTP endpoint (default: /mcp)
  --api-key <key>           API key for authentication
  --safe-mode/--no-safe-mode Enable/disable safe mode (default: enabled)
  --expose-tools/--no-expose-tools Expose agent tools (default: yes)
  --expose-prompts/--no-expose-prompts Expose prompts (default: yes)
  --session-ttl <secs>      Session TTL in seconds (default: 3600)
  --log-level <level>       Log level: debug, info, warning, error
  --json                    Output in JSON format

[bold]Examples:[/bold]
  # Serve a recipe as STDIO MCP server
  praisonai mcp serve-recipe support-reply --transport stdio

  # Serve with HTTP Stream transport
  praisonai mcp serve-recipe ai-video-editor --transport http-stream --port 8080

  # List available recipes
  praisonai mcp list-recipes

  # Validate recipe MCP compatibility
  praisonai mcp validate-recipe support-reply

  # Inspect recipe tools/resources/prompts
  praisonai mcp inspect-recipe support-reply --tools

  # Generate Claude Desktop config for recipe
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
    
    def _print_json(self, data: dict) -> None:
        """Print JSON output."""
        print(json.dumps(data, indent=2))
    
    def cmd_serve_recipe(self, args: List[str]) -> int:
        """Serve a recipe as MCP server."""
        parser = argparse.ArgumentParser(prog="praisonai mcp serve-recipe")
        parser.add_argument("recipe_name", help="Recipe name to serve")
        parser.add_argument("--transport", default="stdio", choices=["stdio", "http-stream"])
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8080)
        parser.add_argument("--endpoint", default="/mcp")
        parser.add_argument("--api-key", default=None)
        parser.add_argument("--safe-mode", action="store_true", default=True)
        parser.add_argument("--no-safe-mode", action="store_true")
        parser.add_argument("--expose-tools", action="store_true", default=True)
        parser.add_argument("--no-expose-tools", action="store_true")
        parser.add_argument("--expose-prompts", action="store_true", default=True)
        parser.add_argument("--no-expose-prompts", action="store_true")
        parser.add_argument("--session-ttl", type=int, default=3600)
        parser.add_argument("--log-level", default="warning", choices=["debug", "info", "warning", "error"])
        parser.add_argument("--json", action="store_true")
        
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
        logging.basicConfig(level=log_levels.get(parsed.log_level, logging.WARNING), stream=sys.stderr)
        
        try:
            from .recipe_adapter import RecipeMCPAdapter, RecipeMCPConfig
            
            # Create config
            config = RecipeMCPConfig(
                recipe_name=parsed.recipe_name,
                safe_mode=not parsed.no_safe_mode,
                expose_agent_tools=not parsed.no_expose_tools,
                expose_prompts=not parsed.no_expose_prompts,
                session_ttl=parsed.session_ttl,
            )
            
            # Create adapter and load
            adapter = RecipeMCPAdapter(parsed.recipe_name, config)
            adapter.load()
            
            # Create server
            server = adapter.to_mcp_server()
            
            if parsed.transport == "stdio":
                logger.info(f"Starting recipe MCP server '{parsed.recipe_name}' on STDIO transport")
                server.run_stdio()
            else:
                if not parsed.json:
                    self._print_success(f"Starting recipe MCP server '{parsed.recipe_name}' on http://{parsed.host}:{parsed.port}{parsed.endpoint}")
                
                server.run_http_stream(
                    host=parsed.host,
                    port=parsed.port,
                    endpoint=parsed.endpoint,
                    api_key=parsed.api_key,
                    session_ttl=parsed.session_ttl,
                )
            
            return self.EXIT_SUCCESS
            
        except ValueError as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
        except ImportError as e:
            self._print_error(f"Missing dependency: {e}")
            return self.EXIT_ERROR
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
            return self.EXIT_SUCCESS
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_list_recipes(self, args: List[str]) -> int:
        """List available recipes."""
        parser = argparse.ArgumentParser(prog="praisonai mcp list-recipes")
        parser.add_argument("--tags", default=None, help="Filter by tags (comma-separated)")
        parser.add_argument("--source", default=None, choices=["local", "package", "all"])
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from ..recipe.core import list_recipes
            
            tags = parsed.tags.split(",") if parsed.tags else None
            recipes = list_recipes(tags=tags, source=parsed.source)
            
            if parsed.json:
                self._print_json({"recipes": [r.to_dict() for r in recipes]})
            else:
                if not recipes:
                    print("No recipes found")
                    return self.EXIT_SUCCESS
                
                print(f"\n[bold]Available Recipes ({len(recipes)}):[/bold]\n")
                for recipe in recipes:
                    print(f"  • {recipe.name} (v{recipe.version})")
                    print(f"    {recipe.description}")
                    if recipe.tags:
                        print(f"    Tags: {', '.join(recipe.tags)}")
                    print()
            
            return self.EXIT_SUCCESS
            
        except ImportError:
            # Fallback to template discovery
            try:
                from ..templates.discovery import TemplateDiscovery
                
                discovery = TemplateDiscovery()
                templates = discovery.discover_all()
                
                if parsed.json:
                    self._print_json({"recipes": [t.to_dict() for t in templates]})
                else:
                    if not templates:
                        print("No recipes found")
                        return self.EXIT_SUCCESS
                    
                    print(f"\n[bold]Available Recipes ({len(templates)}):[/bold]\n")
                    for template in templates:
                        print(f"  • {template.name}")
                        if template.description:
                            print(f"    {template.description}")
                        print()
                
                return self.EXIT_SUCCESS
                
            except Exception as e:
                self._print_error(str(e))
                return self.EXIT_ERROR
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_validate_recipe(self, args: List[str]) -> int:
        """Validate recipe MCP compatibility."""
        parser = argparse.ArgumentParser(prog="praisonai mcp validate-recipe")
        parser.add_argument("recipe_name", help="Recipe name to validate")
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .recipe_adapter import RecipeMCPAdapter
            
            errors = []
            warnings = []
            
            # Try to load the recipe
            try:
                adapter = RecipeMCPAdapter(parsed.recipe_name)
                adapter.load()
            except ValueError as e:
                errors.append(f"Recipe not found: {e}")
            except Exception as e:
                errors.append(f"Failed to load recipe: {e}")
            
            if not errors:
                # Check tool registry
                tools = adapter.get_tool_registry().list_all()
                if not tools:
                    warnings.append("No tools registered")
                
                # Check for dangerous tools
                for tool in tools:
                    annotations = getattr(tool, 'annotations', {}) or {}
                    if annotations.get('type') == 'agent_tool':
                        original = annotations.get('original_tool', '')
                        if 'shell' in original.lower() or 'exec' in original.lower():
                            warnings.append(f"Tool '{tool.name}' may be dangerous (shell/exec)")
            
            result = {
                "valid": len(errors) == 0,
                "recipe": parsed.recipe_name,
                "errors": errors,
                "warnings": warnings,
            }
            
            if parsed.json:
                self._print_json(result)
            else:
                if result["valid"]:
                    self._print_success(f"Recipe '{parsed.recipe_name}' is valid for MCP serving")
                else:
                    self._print_error(f"Recipe '{parsed.recipe_name}' has validation errors")
                
                if errors:
                    print("\n[bold red]Errors:[/bold red]")
                    for error in errors:
                        print(f"  ✗ {error}")
                
                if warnings:
                    print("\n[bold yellow]Warnings:[/bold yellow]")
                    for warning in warnings:
                        print(f"  ⚠ {warning}")
            
            return self.EXIT_SUCCESS if result["valid"] else self.EXIT_ERROR
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_inspect_recipe(self, args: List[str]) -> int:
        """Inspect recipe MCP schema."""
        parser = argparse.ArgumentParser(prog="praisonai mcp inspect-recipe")
        parser.add_argument("recipe_name", help="Recipe name to inspect")
        parser.add_argument("--tools", action="store_true", help="Show tools")
        parser.add_argument("--resources", action="store_true", help="Show resources")
        parser.add_argument("--prompts", action="store_true", help="Show prompts")
        parser.add_argument("--metadata", action="store_true", help="Show metadata")
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        # Default to showing all if nothing specified
        show_all = not (parsed.tools or parsed.resources or parsed.prompts or parsed.metadata)
        
        try:
            from .recipe_adapter import RecipeMCPAdapter
            
            adapter = RecipeMCPAdapter(parsed.recipe_name)
            adapter.load()
            
            result = {}
            
            if show_all or parsed.metadata:
                result["metadata"] = adapter.get_recipe_info()
            
            if show_all or parsed.tools:
                tools = adapter.get_tool_registry().list_schemas()
                result["tools"] = tools
            
            if show_all or parsed.resources:
                resources = adapter.get_resource_registry().list_schemas()
                result["resources"] = resources
            
            if show_all or parsed.prompts:
                prompts = adapter.get_prompt_registry().list_schemas()
                result["prompts"] = prompts
            
            if parsed.json:
                self._print_json(result)
            else:
                print(f"\n[bold cyan]Recipe: {parsed.recipe_name}[/bold cyan]\n")
                
                if "metadata" in result:
                    meta = result["metadata"]
                    print("[bold]Metadata:[/bold]")
                    print(f"  Version: {meta.get('version', 'unknown')}")
                    print(f"  Description: {meta.get('description', 'N/A')}")
                    if meta.get('tags'):
                        print(f"  Tags: {', '.join(meta['tags'])}")
                    print()
                
                if "tools" in result:
                    tools = result["tools"]
                    print(f"[bold]Tools ({len(tools)}):[/bold]")
                    for tool in tools:
                        print(f"  • {tool['name']}")
                        print(f"    {tool.get('description', 'No description')}")
                    print()
                
                if "resources" in result:
                    resources = result["resources"]
                    print(f"[bold]Resources ({len(resources)}):[/bold]")
                    for res in resources:
                        print(f"  • {res['uri']}")
                        print(f"    {res.get('description', 'No description')}")
                    print()
                
                if "prompts" in result:
                    prompts = result["prompts"]
                    print(f"[bold]Prompts ({len(prompts)}):[/bold]")
                    for prompt in prompts:
                        print(f"  • {prompt['name']}")
                        print(f"    {prompt.get('description', 'No description')}")
                    print()
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_config_generate_recipe(self, args: List[str]) -> int:
        """Generate client config for recipe MCP server."""
        parser = argparse.ArgumentParser(prog="praisonai mcp config-generate-recipe")
        parser.add_argument("recipe_name", help="Recipe name")
        parser.add_argument("--client", default="claude-desktop", 
                          choices=["claude-desktop", "cursor", "vscode", "windsurf", "generic"])
        parser.add_argument("--transport", default="stdio", choices=["stdio", "http-stream"])
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8080)
        parser.add_argument("--output", default=None, help="Output file path")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        # Generate config
        if parsed.transport == "stdio":
            server_config = {
                "command": "praisonai",
                "args": ["mcp", "serve-recipe", parsed.recipe_name, "--transport", "stdio"],
            }
        else:
            server_config = {
                "url": f"http://{parsed.host}:{parsed.port}/mcp",
                "transport": "http-stream",
            }
        
        if parsed.client == "claude-desktop":
            config = {
                "mcpServers": {
                    parsed.recipe_name: server_config
                }
            }
        elif parsed.client in ("cursor", "windsurf"):
            config = {
                "mcpServers": {
                    parsed.recipe_name: server_config
                }
            }
        elif parsed.client == "vscode":
            config = {
                "mcp.servers": {
                    parsed.recipe_name: server_config
                }
            }
        else:  # generic
            config = {
                "server": {
                    "name": parsed.recipe_name,
                    **server_config
                }
            }
        
        config_json = json.dumps(config, indent=2)
        
        if parsed.output:
            with open(parsed.output, 'w') as f:
                f.write(config_json)
            self._print_success(f"Config written to {parsed.output}")
        else:
            print(f"\n[bold]{parsed.client} Configuration for {parsed.recipe_name}:[/bold]\n")
            print(config_json)
            print()
        
        return self.EXIT_SUCCESS
    
    def cmd_auth(self, args: List[str]) -> int:
        """Handle auth subcommands."""
        if not args:
            print("Usage: praisonai mcp auth <subcommand>")
            print("Subcommands: generate-key, validate, oidc-discover")
            return self.EXIT_ERROR
        
        subcommand = args[0]
        remaining = args[1:]
        
        if subcommand == "generate-key":
            return self._auth_generate_key(remaining)
        elif subcommand == "validate":
            return self._auth_validate(remaining)
        elif subcommand == "oidc-discover":
            return self._auth_oidc_discover(remaining)
        else:
            self._print_error(f"Unknown auth subcommand: {subcommand}")
            return self.EXIT_ERROR
    
    def _auth_generate_key(self, args: List[str]) -> int:
        """Generate API key."""
        parser = argparse.ArgumentParser(prog="praisonai mcp auth generate-key")
        parser.add_argument("--name", default=None, help="Key name")
        parser.add_argument("--scopes", default=None, help="Comma-separated scopes")
        parser.add_argument("--expires-in", type=int, default=None, help="Expiration in seconds")
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .auth.api_key import APIKeyAuth
            
            auth = APIKeyAuth()
            scopes = parsed.scopes.split(",") if parsed.scopes else None
            
            raw_key, api_key = auth.generate_key(
                name=parsed.name,
                scopes=scopes,
                expires_in=parsed.expires_in,
            )
            
            if parsed.json:
                self._print_json({
                    "key": raw_key,
                    "key_id": api_key.key_id,
                    "name": api_key.name,
                    "scopes": api_key.scopes,
                    "expires_at": api_key.expires_at,
                })
            else:
                print("\n[bold green]Generated API Key:[/bold green]")
                print(f"  Key: {raw_key}")
                print(f"  ID: {api_key.key_id}")
                if api_key.name:
                    print(f"  Name: {api_key.name}")
                if api_key.scopes:
                    print(f"  Scopes: {', '.join(api_key.scopes)}")
                if api_key.expires_at:
                    print(f"  Expires: {api_key.expires_at}")
                print("\n[yellow]Save this key securely - it cannot be retrieved later.[/yellow]")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def _auth_validate(self, args: List[str]) -> int:
        """Validate API key."""
        parser = argparse.ArgumentParser(prog="praisonai mcp auth validate")
        parser.add_argument("key", help="API key to validate")
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .auth.api_key import APIKeyAuth
            
            auth = APIKeyAuth()
            is_valid, api_key = auth.validate(parsed.key)
            
            if parsed.json:
                self._print_json({
                    "valid": is_valid,
                    "key_id": api_key.key_id if api_key else None,
                })
            else:
                if is_valid:
                    self._print_success("API key is valid")
                else:
                    self._print_error("API key is invalid or expired")
            
            return self.EXIT_SUCCESS if is_valid else self.EXIT_ERROR
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def _auth_oidc_discover(self, args: List[str]) -> int:
        """Discover OIDC configuration."""
        parser = argparse.ArgumentParser(prog="praisonai mcp auth oidc-discover")
        parser.add_argument("issuer", help="OIDC issuer URL")
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            import asyncio
            from .auth.oidc import OIDCDiscovery
            
            discovery = OIDCDiscovery()
            config = asyncio.run(discovery.discover(parsed.issuer))
            
            if parsed.json:
                self._print_json(config.to_dict())
            else:
                print(f"\n[bold]OIDC Configuration for {parsed.issuer}:[/bold]\n")
                print(f"  Issuer: {config.issuer}")
                print(f"  Authorization: {config.authorization_endpoint}")
                print(f"  Token: {config.token_endpoint}")
                if config.userinfo_endpoint:
                    print(f"  UserInfo: {config.userinfo_endpoint}")
                if config.scopes_supported:
                    print(f"  Scopes: {', '.join(config.scopes_supported[:5])}...")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def cmd_tasks(self, args: List[str]) -> int:
        """Handle tasks subcommands."""
        if not args:
            print("Usage: praisonai mcp tasks <subcommand>")
            print("Subcommands: list, get, cancel")
            return self.EXIT_ERROR
        
        subcommand = args[0]
        remaining = args[1:]
        
        if subcommand == "list":
            return self._tasks_list(remaining)
        elif subcommand == "get":
            return self._tasks_get(remaining)
        elif subcommand == "cancel":
            return self._tasks_cancel(remaining)
        else:
            self._print_error(f"Unknown tasks subcommand: {subcommand}")
            return self.EXIT_ERROR
    
    def _tasks_list(self, args: List[str]) -> int:
        """List tasks."""
        parser = argparse.ArgumentParser(prog="praisonai mcp tasks list")
        parser.add_argument("--session", default=None, help="Filter by session ID")
        parser.add_argument("--state", default=None, choices=["pending", "running", "completed", "failed", "cancelled"])
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .tasks import get_task_manager, TaskState
            
            manager = get_task_manager()
            state = TaskState(parsed.state) if parsed.state else None
            tasks = manager.list_tasks(
                session_id=parsed.session,
                state=state,
                limit=parsed.limit,
            )
            
            if parsed.json:
                self._print_json({"tasks": [t.to_dict() for t in tasks]})
            else:
                if not tasks:
                    print("No tasks found")
                    return self.EXIT_SUCCESS
                
                print(f"\n[bold]Tasks ({len(tasks)}):[/bold]\n")
                for task in tasks:
                    print(f"  • {task.id} [{task.state.value}]")
                    print(f"    Method: {task.method}")
                    if task.progress:
                        print(f"    Progress: {task.progress.current}/{task.progress.total or '?'}")
                    print()
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def _tasks_get(self, args: List[str]) -> int:
        """Get task details."""
        parser = argparse.ArgumentParser(prog="praisonai mcp tasks get")
        parser.add_argument("task_id", help="Task ID")
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            from .tasks import get_task_manager
            
            manager = get_task_manager()
            task = manager.get_task(parsed.task_id)
            
            if not task:
                self._print_error(f"Task not found: {parsed.task_id}")
                return self.EXIT_ERROR
            
            if parsed.json:
                self._print_json(task.to_dict())
            else:
                print(f"\n[bold]Task: {task.id}[/bold]\n")
                print(f"  State: {task.state.value}")
                print(f"  Method: {task.method}")
                print(f"  Created: {task.created_at}")
                if task.progress:
                    print(f"  Progress: {task.progress.current}/{task.progress.total or '?'}")
                if task.result:
                    print(f"  Result: {task.result}")
                if task.error:
                    print(f"  Error: {task.error}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR
    
    def _tasks_cancel(self, args: List[str]) -> int:
        """Cancel a task."""
        parser = argparse.ArgumentParser(prog="praisonai mcp tasks cancel")
        parser.add_argument("task_id", help="Task ID")
        parser.add_argument("--json", action="store_true")
        
        try:
            parsed = parser.parse_args(args)
        except SystemExit:
            return self.EXIT_ERROR
        
        try:
            import asyncio
            from .tasks import get_task_manager
            
            manager = get_task_manager()
            task = asyncio.run(manager.cancel_task(parsed.task_id))
            
            if not task:
                self._print_error(f"Task not found: {parsed.task_id}")
                return self.EXIT_ERROR
            
            if parsed.json:
                self._print_json({"cancelled": True, "task": task.to_dict()})
            else:
                self._print_success(f"Task {parsed.task_id} cancelled")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_ERROR


def handle_recipe_mcp_command(args: List[str]) -> int:
    """
    Entry point for recipe MCP CLI commands.
    
    Args:
        args: Command arguments
        
    Returns:
        Exit code
    """
    cli = RecipeMCPCLI()
    return cli.handle(args)
