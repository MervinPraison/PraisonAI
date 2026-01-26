"""
Recipe CLI Feature Handler

Provides CLI commands for recipe management and execution:
- list, search, info, validate, run
- init, test, pack, unpack
- export, replay
- serve

All commands use the canonical `praisonai recipe` prefix.
"""

import json
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class RecipeHandler:
    """
    CLI handler for recipe operations.
    
    Commands:
    - list: List available recipes
    - search: Search recipes by query
    - info: Show recipe details
    - validate: Validate a recipe
    - run: Run a recipe
    - init: Initialize a new recipe
    - test: Test a recipe
    - pack: Create a recipe bundle
    - unpack: Extract a recipe bundle
    - export: Export a run bundle
    - replay: Replay from a run bundle
    - serve: Start HTTP recipe runner
    """
    
    # Stable exit codes
    EXIT_SUCCESS = 0
    EXIT_GENERAL_ERROR = 1
    EXIT_VALIDATION_ERROR = 2
    EXIT_RUNTIME_ERROR = 3
    EXIT_POLICY_DENIED = 4
    EXIT_TIMEOUT = 5
    EXIT_MISSING_DEPS = 6
    EXIT_NOT_FOUND = 7
    
    def __init__(self):
        """Initialize the handler."""
        self._recipe_module = None
    
    @property
    def recipe(self):
        """Lazy load recipe module."""
        if self._recipe_module is None:
            from praisonai import recipe
            self._recipe_module = recipe
        return self._recipe_module
    
    def handle(self, args: List[str]) -> int:
        """
        Handle recipe subcommand.
        
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
            "list": self.cmd_list,
            "search": self.cmd_search,
            "info": self.cmd_info,
            "validate": self.cmd_validate,
            "run": self.cmd_run,
            "init": self.cmd_init,
            "test": self.cmd_test,
            "pack": self.cmd_pack,
            "unpack": self.cmd_unpack,
            "export": self.cmd_export,
            "replay": self.cmd_replay,
            "serve": self.cmd_serve,
            "publish": self.cmd_publish,
            "pull": self.cmd_pull,
            "sbom": self.cmd_sbom,
            "audit": self.cmd_audit,
            "sign": self.cmd_sign,
            "verify": self.cmd_verify,
            "runs": self.cmd_runs,
            "policy": self.cmd_policy,
            "judge": self.cmd_judge,
            "apply": self.cmd_apply,
            "create": self.cmd_create,
            "optimize": self.cmd_optimize,
            "help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "--help": lambda _: self._print_help() or self.EXIT_SUCCESS,
            "-h": lambda _: self._print_help() or self.EXIT_SUCCESS,
        }
        
        if command in commands:
            return commands[command](remaining)
        else:
            self._print_error(f"Unknown command: {command}")
            self._print_help()
            return self.EXIT_GENERAL_ERROR
    
    def _print_help(self):
        """Print help message."""
        help_text = """
[bold cyan]PraisonAI Recipe[/bold cyan]

[bold]Usage:[/bold]
  praisonai recipe <command> [options]

[bold]Commands:[/bold]
  list              List available recipes
  search <query>    Search recipes by name or tags
  info <recipe>     Show recipe details and dependencies
  validate <recipe> Validate a recipe
  run <recipe>      Run a recipe
  init <name>       Initialize a new recipe project
  test <recipe>     Run recipe tests
  pack <recipe>     Create a recipe bundle (.praison)
  unpack <bundle>   Extract a recipe bundle
  export <run_id>   Export a run bundle for replay
  replay <bundle>   Replay from a run bundle
  serve             Start HTTP recipe runner
  publish <bundle>  Publish recipe to registry
  pull <name>       Pull recipe from registry
  runs              List/manage run history
  judge <trace_id>  Judge a trace with LLM (--memory, --knowledge, --context)
  apply <plan>      Apply fixes from a judge plan
  create <goal>     Create recipe from natural language goal (auto-optimize)
  optimize <name>   Optimize existing recipe with judge feedback
  sbom <recipe>     Generate SBOM (Software Bill of Materials)
  audit <recipe>    Audit dependencies for vulnerabilities
  sign <bundle>     Sign a recipe bundle
  verify <bundle>   Verify bundle signature
  policy            Manage policy packs

[bold]Run Options:[/bold]
  --input, -i       Input JSON or file path
  --config, -c      Config JSON overrides
  --session, -s     Session ID for state grouping
  --output, -o      Output mode: silent, status, trace, verbose, debug, json
  --json            Output JSON (for parsing)
  --stream          Stream output events (SSE-like)
  --dry-run         Validate without executing
  --explain         Show execution plan
  --verbose, -v     Alias for --output verbose
  --timeout <sec>   Timeout in seconds (default: 300)
  --non-interactive Disable prompts (for CI)
  --export <path>   Export run bundle after execution
  --policy <file>   Policy file path
  --mode dev|prod   Execution mode (default: dev)

[bold]Serve Options:[/bold]
  --port <num>      Server port (default: 8765)
  --host <addr>     Server host (default: 127.0.0.1)
  --auth <type>     Auth type: none, api-key, jwt
  --reload          Enable hot reload (dev mode)

[bold]Exit Codes:[/bold]
  0  Success
  2  Validation error
  3  Runtime error
  4  Policy denied
  5  Timeout
  6  Missing dependencies
  7  Recipe not found

[bold]Examples:[/bold]
  praisonai recipe list
  praisonai recipe search video
  praisonai recipe info transcript-generator
  praisonai recipe validate support-reply
  praisonai recipe run support-reply --input '{"ticket_id": "T-123"}'
  praisonai recipe run transcript-generator ./audio.mp3 --json
  praisonai recipe init my-recipe
  praisonai recipe serve --port 8765
"""
        self._print_rich(help_text)
    
    def _print_rich(self, text: str):
        """Print with rich formatting if available."""
        try:
            from rich import print as rprint
            rprint(text)
        except ImportError:
            # Strip rich formatting
            import re
            plain = re.sub(r'\[/?[^\]]+\]', '', text)
            print(plain)
    
    def _print_error(self, message: str):
        """Print error message."""
        try:
            from rich import print as rprint
            rprint(f"[red]Error: {message}[/red]")
        except ImportError:
            print(f"Error: {message}", file=sys.stderr)
    
    def _print_success(self, message: str):
        """Print success message."""
        try:
            from rich import print as rprint
            rprint(f"[green]✓ {message}[/green]")
        except ImportError:
            print(f"✓ {message}")
    
    def _print_json(self, data: Any):
        """Print JSON output."""
        print(json.dumps(data, indent=2, default=str))
    
    def _parse_args(self, args: List[str], spec: Dict[str, Any]) -> Dict[str, Any]:
        """Parse command arguments based on spec."""
        result = {k: v.get("default") for k, v in spec.items()}
        # Initialize multi-value options as empty lists
        for k, v in spec.items():
            if v.get("multi"):
                result[k] = []
        positional_keys = [k for k, v in spec.items() if v.get("positional")]
        positional_idx = 0
        
        i = 0
        while i < len(args):
            arg = args[i]
            
            if arg.startswith("--"):
                key = arg[2:].replace("-", "_")
                if key in spec:
                    if spec[key].get("flag"):
                        result[key] = True
                    elif i + 1 < len(args):
                        # Support multi-value options (--var can be used multiple times)
                        if spec[key].get("multi"):
                            result[key].append(args[i + 1])
                        else:
                            result[key] = args[i + 1]
                        i += 1
                i += 1
            elif arg.startswith("-") and len(arg) == 2:
                # Short flag
                for key, val in spec.items():
                    if val.get("short") == arg:
                        if val.get("flag"):
                            result[key] = True
                        elif i + 1 < len(args):
                            if val.get("multi"):
                                result[key].append(args[i + 1])
                            else:
                                result[key] = args[i + 1]
                            i += 1
                        break
                i += 1
            else:
                # Positional argument
                if positional_idx < len(positional_keys):
                    result[positional_keys[positional_idx]] = arg
                    positional_idx += 1
                i += 1
        
        return result
    
    def _parse_agents_spec(self, spec_str: str) -> Dict[str, Dict[str, Any]]:
        """Parse agents specification string.
        
        Format: name:role=X,goal=Y;name2:role=Z,goal=W
        
        Returns:
            Dict of agent_name -> {role, goal, backstory}
        """
        if not spec_str or not spec_str.strip():
            return {}
        
        agents = {}
        for agent_spec in spec_str.split(";"):
            agent_spec = agent_spec.strip()
            if not agent_spec or ":" not in agent_spec:
                continue
            
            parts = agent_spec.split(":", 1)
            agent_name = parts[0].strip()
            
            agent_config = {}
            if len(parts) > 1:
                for prop in parts[1].split(","):
                    if "=" in prop:
                        key, value = prop.split("=", 1)
                        agent_config[key.strip()] = value.strip()
            
            agents[agent_name] = agent_config
        
        return agents
    
    def _parse_tools_spec(self, spec_str: str) -> Dict[str, List[str]]:
        """Parse tools specification string.
        
        Format: agent:tool1,tool2;agent2:tool3,tool4
        
        Returns:
            Dict of agent_name -> [tool1, tool2, ...]
        """
        if not spec_str or not spec_str.strip():
            return {}
        
        tools = {}
        for tool_spec in spec_str.split(";"):
            tool_spec = tool_spec.strip()
            if not tool_spec or ":" not in tool_spec:
                continue
            
            parts = tool_spec.split(":", 1)
            agent_name = parts[0].strip()
            
            if len(parts) > 1:
                tool_list = [t.strip() for t in parts[1].split(",") if t.strip()]
                tools[agent_name] = tool_list
        
        return tools
    
    def _parse_agent_types_spec(self, spec_str: str) -> Dict[str, str]:
        """Parse agent types specification string.
        
        Format: agent:image;agent2:audio
        
        Returns:
            Dict of agent_name -> type
        """
        if not spec_str or not spec_str.strip():
            return {}
        
        agent_types = {}
        for type_spec in spec_str.split(";"):
            type_spec = type_spec.strip()
            if not type_spec or ":" not in type_spec:
                continue
            
            parts = type_spec.split(":", 1)
            agent_name = parts[0].strip()
            
            if len(parts) > 1:
                agent_types[agent_name] = parts[1].strip()
        
        return agent_types
    
    def cmd_list(self, args: List[str]) -> int:
        """List available recipes."""
        spec = {
            "source": {"default": None},
            "tags": {"default": None},
            "registry": {"default": None},
            "token": {"default": None},
            "json": {"flag": True, "default": False},
            "offline": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        try:
            # If registry URL provided, list from that registry
            if parsed["registry"]:
                from praisonai.recipe.registry import get_registry
                import os
                registry = get_registry(
                    registry=parsed["registry"],
                    token=parsed["token"] or os.environ.get("PRAISONAI_REGISTRY_TOKEN")
                )
                result = registry.list_recipes(
                    tags=parsed["tags"].split(",") if parsed["tags"] else None
                )
                recipes = result.get("recipes", []) if isinstance(result, dict) else result
                
                if parsed["json"]:
                    self._print_json(recipes)
                    return self.EXIT_SUCCESS
                
                if not recipes:
                    print("No recipes found in registry.")
                    return self.EXIT_SUCCESS
                
                try:
                    from rich.console import Console
                    from rich.table import Table
                    
                    console = Console()
                    table = Table(title=f"Recipes from {parsed['registry']}")
                    table.add_column("Name", style="cyan")
                    table.add_column("Version", style="green")
                    table.add_column("Description")
                    table.add_column("Tags", style="yellow")
                    
                    for r in recipes:
                        table.add_row(
                            r.get("name", ""),
                            r.get("version", ""),
                            (r.get("description", "")[:50] + "...") if len(r.get("description", "")) > 50 else r.get("description", ""),
                            ", ".join(r.get("tags", [])[:3]),
                        )
                    
                    console.print(table)
                except ImportError:
                    for r in recipes:
                        print(f"{r.get('name')} ({r.get('version')}): {r.get('description', '')}")
                
                return self.EXIT_SUCCESS
            
            # Default: list local recipes
            recipes = self.recipe.list_recipes(
                source_filter=parsed["source"],
                tags=parsed["tags"].split(",") if parsed["tags"] else None,
                offline=parsed["offline"],
            )
            
            if parsed["json"]:
                self._print_json([r.to_dict() for r in recipes])
                return self.EXIT_SUCCESS
            
            if not recipes:
                print("No recipes found.")
                return self.EXIT_SUCCESS
            
            try:
                from rich.console import Console
                from rich.table import Table
                
                console = Console()
                table = Table(title="Available Recipes")
                table.add_column("Name", style="cyan")
                table.add_column("Version", style="green")
                table.add_column("Description")
                table.add_column("Tags", style="yellow")
                
                for r in recipes:
                    desc = r.description or ""
                    table.add_row(
                        r.name,
                        r.version or "",
                        desc[:50] + "..." if len(desc) > 50 else desc,
                        ", ".join(r.tags[:3]) if r.tags else "",
                    )
                
                console.print(table)
            except ImportError:
                for r in recipes:
                    print(f"{r.name} ({r.version}): {r.description}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_search(self, args: List[str]) -> int:
        """Search recipes by query."""
        spec = {
            "query": {"positional": True, "default": ""},
            "registry": {"default": None},
            "token": {"default": None},
            "json": {"flag": True, "default": False},
            "offline": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["query"]:
            self._print_error("Search query required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            # If registry URL provided, search that registry
            if parsed["registry"]:
                from praisonai.recipe.registry import get_registry
                import os
                registry = get_registry(
                    registry=parsed["registry"],
                    token=parsed["token"] or os.environ.get("PRAISONAI_REGISTRY_TOKEN")
                )
                result = registry.search(parsed["query"])
                matches = result.get("results", []) if isinstance(result, dict) else result
                
                if parsed["json"]:
                    self._print_json(matches)
                    return self.EXIT_SUCCESS
                
                if not matches:
                    print(f"No recipes found matching '{parsed['query']}' in registry")
                    return self.EXIT_SUCCESS
                
                print(f"Found {len(matches)} recipe(s) matching '{parsed['query']}':")
                for r in matches:
                    print(f"  {r.get('name')}: {r.get('description', '')}")
                
                return self.EXIT_SUCCESS
            
            # Default: search local recipes
            recipes = self.recipe.list_recipes(offline=parsed["offline"])
            query = parsed["query"].lower()
            
            # Filter by query
            matches = []
            for r in recipes:
                if (query in r.name.lower() or 
                    query in r.description.lower() or
                    any(query in t.lower() for t in r.tags)):
                    matches.append(r)
            
            if parsed["json"]:
                self._print_json([r.to_dict() for r in matches])
                return self.EXIT_SUCCESS
            
            if not matches:
                print(f"No recipes found matching '{parsed['query']}'")
                return self.EXIT_SUCCESS
            
            print(f"Found {len(matches)} recipe(s) matching '{parsed['query']}':")
            for r in matches:
                print(f"  {r.name}: {r.description}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_info(self, args: List[str]) -> int:
        """Show recipe details."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "json": {"flag": True, "default": False},
            "offline": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe name required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            info = self.recipe.describe(parsed["recipe"], offline=parsed["offline"])
            
            if info is None:
                self._print_error(f"Recipe not found: {parsed['recipe']}")
                return self.EXIT_NOT_FOUND
            
            if parsed["json"]:
                self._print_json(info.to_dict())
                return self.EXIT_SUCCESS
            
            self._print_rich(f"\n[bold cyan]{info.name}[/bold cyan] v{info.version}")
            if info.description:
                print(f"\n{info.description}")
            
            if info.author:
                print(f"\nAuthor: {info.author}")
            if info.license:
                print(f"License: {info.license}")
            if info.tags:
                print(f"Tags: {', '.join(info.tags)}")
            
            # Dependencies
            print("\n[bold]Dependencies:[/bold]")
            pkgs = info.get_required_packages()
            if pkgs:
                print(f"  Packages: {', '.join(pkgs)}")
            env = info.get_required_env()
            if env:
                print(f"  Env vars: {', '.join(env)}")
            ext = info.get_external_deps()
            if ext:
                names = [e.get("name", e) if isinstance(e, dict) else e for e in ext]
                print(f"  External: {', '.join(names)}")
            
            # Tool permissions
            allowed = info.get_allowed_tools()
            denied = info.get_denied_tools()
            if allowed or denied:
                print("\n[bold]Tool Permissions:[/bold]")
                if allowed:
                    print(f"  Allow: {', '.join(allowed)}")
                if denied:
                    print(f"  Deny: {', '.join(denied)}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_validate(self, args: List[str]) -> int:
        """Validate a recipe."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "json": {"flag": True, "default": False},
            "offline": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe name required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            result = self.recipe.validate(parsed["recipe"], offline=parsed["offline"])
            
            if parsed["json"]:
                self._print_json(result.to_dict())
                return self.EXIT_SUCCESS if result.valid else self.EXIT_VALIDATION_ERROR
            
            if result.valid:
                self._print_success(f"Recipe '{result.recipe}' is valid")
            else:
                self._print_error(f"Recipe '{result.recipe}' validation failed")
            
            if result.errors:
                print("\nErrors:")
                for err in result.errors:
                    print(f"  ✗ {err}")
            
            if result.warnings:
                print("\nWarnings:")
                for warn in result.warnings:
                    print(f"  ⚠ {warn}")
            
            # Show dependency status
            deps = result.dependencies
            if deps:
                print("\nDependencies:")
                for pkg in deps.get("packages", []):
                    status = "✓" if pkg["available"] else "✗"
                    print(f"  {status} {pkg['name']}")
                for env in deps.get("env", []):
                    status = "✓" if env["available"] else "✗"
                    print(f"  {status} ${env['name']}")
            
            return self.EXIT_SUCCESS if result.valid else self.EXIT_VALIDATION_ERROR
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_run(self, args: List[str]) -> int:
        """Run a recipe."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "input": {"short": "-i", "default": None},
            "config": {"short": "-c", "default": None},
            "session": {"short": "-s", "default": None},
            "var": {"multi": True},  # --var key=value, can be used multiple times
            "json": {"flag": True, "default": False},
            "stream": {"flag": True, "default": False},
            "background": {"flag": True, "default": False},
            "dry_run": {"flag": True, "default": False},
            "explain": {"flag": True, "default": False},
            "verbose": {"short": "-v", "flag": True, "default": False},
            "output": {"short": "-o", "default": None},  # Output mode: silent, status, trace, verbose, debug
            "timeout": {"default": "300"},
            "non_interactive": {"flag": True, "default": False},
            "export": {"default": None},
            "policy": {"default": None},
            "mode": {"default": "dev"},
            "offline": {"flag": True, "default": False},
            "force": {"flag": True, "default": False},
            "allow_dangerous_tools": {"flag": True, "default": False},
            "save": {"flag": True, "default": False},  # Save replay trace
            "name": {"short": "-n", "default": None},  # Custom trace name
            "debug": {"flag": True, "default": False},  # Debug mode
            "profile": {"flag": True, "default": False},  # Profiling mode
            "deep_profile": {"flag": True, "default": False},  # Deep profiling mode
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe name required")
            return self.EXIT_VALIDATION_ERROR
        
        # Parse input
        input_data = {}
        if parsed["input"]:
            if parsed["input"].startswith("{"):
                try:
                    input_data = json.loads(parsed["input"])
                except json.JSONDecodeError:
                    self._print_error("Invalid JSON input")
                    return self.EXIT_VALIDATION_ERROR
            elif os.path.isfile(parsed["input"]):
                input_data = {"input": parsed["input"]}
            else:
                input_data = {"input": parsed["input"]}
        
        # Check for positional input after recipe name
        remaining_positional = [a for a in args[1:] if not a.startswith("-")]
        if remaining_positional and not parsed["input"]:
            input_data = {"input": remaining_positional[0]}
        
        # Merge --var key=value pairs into input_data (variables)
        if parsed.get("var"):
            for v in parsed["var"]:
                if "=" in v:
                    key, value = v.split("=", 1)
                    input_data[key] = value
        
        # Parse config
        config = {}
        if parsed["config"]:
            try:
                config = json.loads(parsed["config"])
            except json.JSONDecodeError:
                self._print_error("Invalid JSON config")
                return self.EXIT_VALIDATION_ERROR
        
        # Build options
        # Map --verbose to --output verbose for backward compatibility
        output_mode = parsed.get("output")
        if not output_mode and parsed.get("verbose"):
            output_mode = "verbose"
        
        options = {
            "dry_run": parsed["dry_run"] or parsed["explain"],
            "verbose": parsed["verbose"],
            "output": output_mode,  # New: output mode (status, trace, verbose, etc.)
            "timeout_sec": int(parsed["timeout"]),
            "mode": parsed["mode"],
            "offline": parsed["offline"],
            "force": parsed["force"],
            "allow_dangerous_tools": parsed["allow_dangerous_tools"],
            "save_replay": parsed["save"],  # Save replay trace for debugging
            "trace_name": parsed.get("name"),  # Custom trace name (overwrites if exists)
            "debug": parsed.get("debug", False),  # Debug mode
            "profile": parsed.get("profile", False),  # Profiling mode
            "deep_profile": parsed.get("deep_profile", False),  # Deep profiling mode
        }
        
        try:
            # Background execution mode
            if parsed["background"]:
                return self._run_background(
                    parsed["recipe"], input_data, config,
                    parsed["session"], options, parsed["json"]
                )
            
            if parsed["stream"]:
                return self._run_stream(
                    parsed["recipe"], input_data, config,
                    parsed["session"], options, parsed["json"]
                )
            
            result = self.recipe.run(
                parsed["recipe"],
                input=input_data,
                config=config,
                session_id=parsed["session"],
                options=options,
            )
            
            # Output
            if parsed["json"]:
                self._print_json(result.to_dict())
            else:
                if result.ok:
                    self._print_success(f"Recipe '{result.recipe}' completed successfully")
                    print(f"  Run ID: {result.run_id}")
                    print(f"  Duration: {result.metrics.get('duration_sec', 0):.2f}s")
                    if result.output:
                        print("\nOutput:")
                        if isinstance(result.output, dict):
                            for k, v in result.output.items():
                                print(f"  {k}: {v}")
                        else:
                            print(f"  {result.output}")
                else:
                    self._print_error(f"Recipe '{result.recipe}' failed")
                    print(f"  Status: {result.status}")
                    print(f"  Error: {result.error}")
            
            # Export if requested
            if parsed["export"] and result.ok:
                self._export_run(result, parsed["export"])
            
            return result.to_exit_code()
            
        except Exception as e:
            if parsed["json"]:
                self._print_json({"ok": False, "error": str(e)})
            else:
                self._print_error(str(e))
            return self.EXIT_RUNTIME_ERROR
    
    def _run_background(
        self,
        recipe_name: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        session_id: Optional[str],
        options: Dict[str, Any],
        json_output: bool,
    ) -> int:
        """Run recipe as a background task."""
        try:
            from praisonai.recipe.operations import run_background
            
            task = run_background(
                recipe_name,
                input=input_data or None,
                config=config or None,
                session_id=session_id,
                timeout_sec=options.get('timeout_sec', 300),
            )
            
            if json_output:
                self._print_json({
                    "ok": True,
                    "task_id": task.task_id,
                    "recipe": task.recipe_name,
                    "session_id": task.session_id,
                    "message": "Task submitted to background"
                })
            else:
                self._print_success(f"Recipe '{recipe_name}' submitted to background")
                print(f"  Task ID: {task.task_id}")
                print(f"  Session: {task.session_id}")
                print(f"\nCheck status with: praisonai background status {task.task_id}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            if json_output:
                self._print_json({"ok": False, "error": str(e)})
            else:
                self._print_error(f"Failed to submit background task: {e}")
            return self.EXIT_RUNTIME_ERROR
    
    def _run_stream(
        self,
        recipe_name: str,
        input_data: Dict[str, Any],
        config: Dict[str, Any],
        session_id: Optional[str],
        options: Dict[str, Any],
        json_output: bool,
    ) -> int:
        """Run recipe with streaming output."""
        try:
            for event in self.recipe.run_stream(
                recipe_name,
                input=input_data,
                config=config,
                session_id=session_id,
                options=options,
            ):
                if json_output:
                    print(event.to_sse(), end="", flush=True)
                else:
                    if event.event_type == "started":
                        print(f"Started: {event.data.get('run_id')}")
                    elif event.event_type == "progress":
                        print(f"  [{event.data.get('step')}] {event.data.get('message', '')}")
                    elif event.event_type == "output":
                        print(f"Output: {event.data.get('output')}")
                    elif event.event_type == "completed":
                        status = event.data.get("status", "unknown")
                        duration = event.data.get("duration_sec", 0)
                        print(f"Completed: {status} ({duration:.2f}s)")
                    elif event.event_type == "error":
                        print(f"Error: {event.data.get('message')}")
                        return self.EXIT_RUNTIME_ERROR
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_RUNTIME_ERROR
    
    def _export_run(self, result, path: str):
        """Export run result to a bundle."""
        import json
        
        bundle = {
            "run_id": result.run_id,
            "recipe": result.recipe,
            "version": result.version,
            "status": result.status,
            "output": result.output,
            "metrics": result.metrics,
            "trace": result.trace,
            "exported_at": self._get_timestamp(),
        }
        
        with open(path, "w") as f:
            json.dump(bundle, f, indent=2, default=str)
        
        self._print_success(f"Run exported to {path}")
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    
    def cmd_init(self, args: List[str]) -> int:
        """Initialize a new recipe project."""
        spec = {
            "name": {"positional": True, "default": ""},
            "template": {"short": "-t", "default": None},
            "output": {"short": "-o", "default": "."},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["name"]:
            self._print_error("Recipe name required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            output_dir = Path(parsed["output"]) / parsed["name"]
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create agents.yaml with metadata block (simplified 2-file structure)
            agents_yaml = f'''# Recipe metadata (optional, for registry/sharing)
metadata:
  name: {parsed["name"]}
  version: "1.0.0"
  description: |
    Description of your recipe.
  author: your-name
  license: Apache-2.0
  tags:
    - example
  requires:
    env:
      - OPENAI_API_KEY

framework: praisonai
topic: ""

agents:
  assistant:
    role: AI Assistant
    goal: Complete the task
    backstory: You are a helpful AI assistant.
    tools:
      - read_file
      - write_file

steps:
  - agent: assistant
    action: "Process the input: {{{{input}}}}"
    expected_output: Processed result
'''
            (output_dir / "agents.yaml").write_text(agents_yaml)
            
            # Create tools.py
            tools_py = '''"""Custom tools for this recipe."""

# Define your custom tools here
# Example:
# def my_custom_tool(query: str) -> str:
#     """A custom tool."""
#     return f"Result: {query}"

# Dynamic variables can also be defined here
# CUSTOM_VAR = "value"
'''
            (output_dir / "tools.py").write_text(tools_py)
            
            # Create README.md
            readme = f'''# {parsed["name"]}

A PraisonAI recipe.

## Usage

```bash
praisonai recipe run {parsed["name"]} --input "your input"
```

## Configuration

See agents.yaml for configuration options (metadata block for registry info).
'''
            (output_dir / "README.md").write_text(readme)
            
            # Create .env.example
            env_example = '''# Required environment variables
OPENAI_API_KEY=your-api-key
'''
            (output_dir / ".env.example").write_text(env_example)
            
            self._print_success(f"Recipe '{parsed['name']}' initialized at {output_dir}")
            print("\nNext steps:")
            print(f"  1. cd {output_dir}")
            print("  2. Edit agents.yaml and tools.py")
            print(f"  3. praisonai recipe validate {parsed['name']}")
            print(f"  4. praisonai recipe run {parsed['name']} --input 'test'")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_test(self, args: List[str]) -> int:
        """Run recipe tests."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "json": {"flag": True, "default": False},
            "verbose": {"short": "-v", "flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe name required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            # First validate
            result = self.recipe.validate(parsed["recipe"])
            
            if not result.valid:
                if parsed["json"]:
                    self._print_json({"ok": False, "errors": result.errors})
                else:
                    self._print_error("Recipe validation failed")
                    for err in result.errors:
                        print(f"  ✗ {err}")
                return self.EXIT_VALIDATION_ERROR
            
            # Run dry-run test
            run_result = self.recipe.run(
                parsed["recipe"],
                input={},
                options={"dry_run": True, "verbose": parsed["verbose"]},
            )
            
            if parsed["json"]:
                self._print_json({
                    "ok": run_result.ok,
                    "validation": result.to_dict(),
                    "dry_run": run_result.to_dict(),
                })
            else:
                self._print_success(f"Recipe '{parsed['recipe']}' tests passed")
                print("  ✓ Validation passed")
                print("  ✓ Dry run passed")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            if parsed["json"]:
                self._print_json({"ok": False, "error": str(e)})
            else:
                self._print_error(str(e))
            return self.EXIT_RUNTIME_ERROR
    
    def cmd_pack(self, args: List[str]) -> int:
        """Create a recipe bundle."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "output": {"short": "-o", "default": None},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe name required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            import tarfile
            import hashlib
            
            info = self.recipe.describe(parsed["recipe"])
            if info is None:
                self._print_error(f"Recipe not found: {parsed['recipe']}")
                return self.EXIT_NOT_FOUND
            
            if not info.path:
                self._print_error("Recipe path not available")
                return self.EXIT_GENERAL_ERROR
            
            recipe_dir = Path(info.path)
            output_name = parsed["output"] or f"{info.name}-{info.version}.praison"
            
            # Create tarball
            with tarfile.open(output_name, "w:gz") as tar:
                # Add manifest
                manifest = {
                    "name": info.name,
                    "version": info.version,
                    "created_at": self._get_timestamp(),
                    "files": [],
                }
                
                for file_path in recipe_dir.rglob("*"):
                    if file_path.is_file() and not file_path.name.startswith("."):
                        rel_path = file_path.relative_to(recipe_dir)
                        tar.add(file_path, arcname=str(rel_path))
                        
                        # Calculate checksum
                        with open(file_path, "rb") as f:
                            checksum = hashlib.sha256(f.read()).hexdigest()
                        manifest["files"].append({
                            "path": str(rel_path),
                            "checksum": checksum,
                        })
                
                # Add manifest
                import io
                manifest_bytes = json.dumps(manifest, indent=2).encode()
                manifest_info = tarfile.TarInfo(name="manifest.json")
                manifest_info.size = len(manifest_bytes)
                tar.addfile(manifest_info, io.BytesIO(manifest_bytes))
            
            if parsed["json"]:
                self._print_json({
                    "ok": True,
                    "bundle": output_name,
                    "recipe": info.name,
                    "version": info.version,
                })
            else:
                self._print_success(f"Bundle created: {output_name}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_unpack(self, args: List[str]) -> int:
        """Extract a recipe bundle."""
        spec = {
            "bundle": {"positional": True, "default": ""},
            "output": {"short": "-o", "default": "."},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["bundle"]:
            self._print_error("Bundle path required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            import tarfile
            
            bundle_path = Path(parsed["bundle"])
            if not bundle_path.exists():
                self._print_error(f"Bundle not found: {parsed['bundle']}")
                return self.EXIT_NOT_FOUND
            
            output_dir = Path(parsed["output"])
            
            with tarfile.open(bundle_path, "r:gz") as tar:
                # Read manifest
                manifest_file = tar.extractfile("manifest.json")
                if manifest_file:
                    manifest = json.load(manifest_file)
                    recipe_name = manifest.get("name", "recipe")
                else:
                    recipe_name = bundle_path.stem.split("-")[0]
                
                # Extract to recipe directory
                recipe_dir = output_dir / recipe_name
                recipe_dir.mkdir(parents=True, exist_ok=True)
                
                for member in tar.getmembers():
                    if member.name != "manifest.json":
                        tar.extract(member, recipe_dir)
            
            if parsed["json"]:
                self._print_json({
                    "ok": True,
                    "recipe": recipe_name,
                    "path": str(recipe_dir),
                })
            else:
                self._print_success(f"Bundle extracted to {recipe_dir}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_export(self, args: List[str]) -> int:
        """Export a run bundle."""
        spec = {
            "run_id": {"positional": True, "default": ""},
            "output": {"short": "-o", "default": None},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["run_id"]:
            self._print_error("Run ID required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            from praisonai.recipe.history import get_history
            
            history = get_history()
            output_path = history.export(
                run_id=parsed["run_id"],
                output_path=Path(parsed["output"]) if parsed["output"] else None,
            )
            
            if parsed["json"]:
                self._print_json({"ok": True, "path": str(output_path)})
            else:
                self._print_success(f"Exported to {output_path}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_replay(self, args: List[str]) -> int:
        """Replay from a run bundle."""
        spec = {
            "bundle": {"positional": True, "default": ""},
            "compare": {"flag": True, "default": False},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["bundle"]:
            self._print_error("Bundle path required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            bundle_path = Path(parsed["bundle"])
            if not bundle_path.exists():
                self._print_error(f"Bundle not found: {parsed['bundle']}")
                return self.EXIT_NOT_FOUND
            
            with open(bundle_path) as f:
                bundle = json.load(f)
            
            # Re-run the recipe
            result = self.recipe.run(
                bundle["recipe"],
                input=bundle.get("input", {}),
                config=bundle.get("config", {}),
            )
            
            if parsed["compare"]:
                # Compare with original
                original_output = bundle.get("output")
                new_output = result.output
                
                drift = original_output != new_output
                
                if parsed["json"]:
                    self._print_json({
                        "ok": result.ok,
                        "drift": drift,
                        "original": original_output,
                        "new": new_output,
                    })
                else:
                    if drift:
                        print("⚠ Output drift detected")
                        print(f"  Original: {original_output}")
                        print(f"  New: {new_output}")
                    else:
                        self._print_success("No drift detected")
            else:
                if parsed["json"]:
                    self._print_json(result.to_dict())
                else:
                    if result.ok:
                        self._print_success(f"Replay completed: {result.run_id}")
                    else:
                        self._print_error(f"Replay failed: {result.error}")
            
            return result.to_exit_code()
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_serve(self, args: List[str]) -> int:
        """Start HTTP recipe runner."""
        spec = {
            "port": {"default": "8765"},
            "host": {"default": "127.0.0.1"},
            "auth": {"default": "none"},
            "reload": {"flag": True, "default": False},
            "preload": {"flag": True, "default": False},
            "recipes": {"default": None},
            "config": {"default": None},
            "api_key": {"default": None},
            "workers": {"default": "1"},
            "rate_limit": {"default": None},
            "max_request_size": {"default": None},
            "enable_metrics": {"flag": True, "default": False},
            "enable_admin": {"flag": True, "default": False},
            "trace_exporter": {"default": "none"},
        }
        parsed = self._parse_args(args, spec)
        
        # Load config file if specified
        config = {}
        if parsed["config"]:
            try:
                from praisonai.recipe.serve import load_config
                config = load_config(parsed["config"])
            except Exception as e:
                self._print_error(f"Failed to load config: {e}")
                return self.EXIT_VALIDATION_ERROR
        
        # CLI flags override config file
        port = int(parsed["port"]) if parsed["port"] != "8765" or "port" not in config else config.get("port", 8765)
        host = parsed["host"] if parsed["host"] != "127.0.0.1" or "host" not in config else config.get("host", "127.0.0.1")
        auth = parsed["auth"] if parsed["auth"] != "none" or "auth" not in config else config.get("auth", "none")
        workers = int(parsed["workers"]) if parsed["workers"] != "1" or "workers" not in config else config.get("workers", 1)
        
        # Update config with CLI overrides
        config["auth"] = auth
        if parsed["api_key"]:
            config["api_key"] = parsed["api_key"]
        if parsed["recipes"]:
            config["recipes"] = parsed["recipes"].split(",")
        if parsed["rate_limit"]:
            config["rate_limit"] = int(parsed["rate_limit"])
        if parsed["max_request_size"]:
            config["max_request_size"] = int(parsed["max_request_size"])
        if parsed["enable_metrics"]:
            config["enable_metrics"] = True
        if parsed["enable_admin"]:
            config["enable_admin"] = True
        if parsed["trace_exporter"] != "none":
            config["trace_exporter"] = parsed["trace_exporter"]
        
        # Safety check: require auth for non-localhost
        if host != "127.0.0.1" and host != "localhost" and auth == "none":
            self._print_error("Auth required for non-localhost binding. Use --auth api-key or --auth jwt")
            return self.EXIT_POLICY_DENIED
        
        try:
            from praisonai.recipe.serve import serve
            
            print(f"Starting Recipe Runner on http://{host}:{port}")
            if workers > 1:
                print(f"Workers: {workers}")
            if auth != "none":
                print(f"Auth: {auth}")
            print("Press Ctrl+C to stop")
            print("\nEndpoints:")
            print("  GET  /health              - Health check")
            print("  GET  /v1/recipes          - List recipes")
            print("  GET  /v1/recipes/{name}   - Describe recipe")
            print("  POST /v1/recipes/run      - Run recipe")
            print("  POST /v1/recipes/stream   - Stream recipe")
            print("  GET  /openapi.json        - OpenAPI spec")
            if config.get("enable_metrics"):
                print("  GET  /metrics             - Prometheus metrics")
            if config.get("enable_admin"):
                print("  POST /admin/reload        - Hot reload registry")
            
            # Preload recipes if requested
            if parsed["preload"]:
                print("\nPreloading recipes...")
                from praisonai import recipe
                recipes = recipe.list_recipes()
                print(f"  Loaded {len(recipes)} recipes")
            
            serve(host=host, port=port, reload=parsed["reload"], config=config, workers=workers)
            
            return self.EXIT_SUCCESS
            
        except ImportError:
            self._print_error("Serve dependencies not installed. Run: pip install praisonai[serve]")
            return self.EXIT_MISSING_DEPS
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR


    def cmd_publish(self, args: List[str]) -> int:
        """Publish recipe to registry."""
        spec = {
            "bundle": {"positional": True, "default": ""},
            "registry": {"default": None},
            "token": {"default": None},
            "force": {"flag": True, "default": False},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["bundle"]:
            self._print_error("Bundle or recipe directory required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            from praisonai.recipe.registry import get_registry
            
            bundle_path = Path(parsed["bundle"])
            
            # If directory, pack it first
            if bundle_path.is_dir():
                # Pack the recipe first
                import tarfile
                import hashlib
                
                info = self.recipe.describe(str(bundle_path))
                if info is None:
                    self._print_error(f"Invalid recipe directory: {bundle_path}")
                    return self.EXIT_VALIDATION_ERROR
                
                bundle_name = f"{info.name}-{info.version}.praison"
                bundle_path_new = Path(bundle_name)
                
                with tarfile.open(bundle_path_new, "w:gz") as tar:
                    manifest = {
                        "name": info.name,
                        "version": info.version,
                        "description": info.description,
                        "tags": info.tags,
                        "created_at": self._get_timestamp(),
                        "files": [],
                    }
                    
                    for file_path in bundle_path.rglob("*"):
                        if file_path.is_file() and not file_path.name.startswith("."):
                            rel_path = file_path.relative_to(bundle_path)
                            tar.add(file_path, arcname=str(rel_path))
                            with open(file_path, "rb") as f:
                                checksum = hashlib.sha256(f.read()).hexdigest()
                            manifest["files"].append({"path": str(rel_path), "checksum": checksum})
                    
                    import io
                    manifest_bytes = json.dumps(manifest, indent=2).encode()
                    manifest_info = tarfile.TarInfo(name="manifest.json")
                    manifest_info.size = len(manifest_bytes)
                    tar.addfile(manifest_info, io.BytesIO(manifest_bytes))
                
                bundle_path = bundle_path_new
            
            # Get registry
            registry = get_registry(
                registry=parsed["registry"],
                token=parsed["token"] or os.environ.get("PRAISONAI_REGISTRY_TOKEN"),
            )
            
            # Publish
            result = registry.publish(
                bundle_path=bundle_path,
                force=parsed["force"],
            )
            
            if parsed["json"]:
                self._print_json({"ok": True, **result})
            else:
                self._print_success(f"Published {result['name']}@{result['version']}")
                print(f"  Registry: {parsed['registry'] or '~/.praison/registry'}")
                print(f"  Checksum: {result['checksum'][:16]}...")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_pull(self, args: List[str]) -> int:
        """Pull recipe from registry."""
        spec = {
            "name": {"positional": True, "default": ""},
            "registry": {"default": None},
            "token": {"default": None},
            "output": {"short": "-o", "default": "."},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["name"]:
            self._print_error("Recipe name required (e.g., my-recipe@1.0.0)")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            from praisonai.recipe.registry import get_registry
            
            # Parse name@version
            name = parsed["name"]
            version = None
            if "@" in name:
                name, version = name.rsplit("@", 1)
            
            # Get registry
            registry = get_registry(
                registry=parsed["registry"],
                token=parsed["token"] or os.environ.get("PRAISONAI_REGISTRY_TOKEN"),
            )
            
            # Pull
            result = registry.pull(
                name=name,
                version=version,
                output_dir=Path(parsed["output"]),
            )
            
            if parsed["json"]:
                self._print_json({"ok": True, **result})
            else:
                self._print_success(f"Pulled {result['name']}@{result['version']}")
                print(f"  Path: {result['path']}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_runs(self, args: List[str]) -> int:
        """List/manage run history."""
        spec = {
            "action": {"positional": True, "default": "list"},
            "recipe": {"default": None},
            "session": {"default": None},
            "limit": {"default": "20"},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        try:
            from praisonai.recipe.history import get_history
            
            history = get_history()
            action = parsed["action"]
            
            if action == "list":
                runs = history.list_runs(
                    recipe=parsed["recipe"],
                    session_id=parsed["session"],
                    limit=int(parsed["limit"]),
                )
                
                if parsed["json"]:
                    self._print_json({"runs": runs, "count": len(runs)})
                else:
                    if not runs:
                        print("No runs found")
                    else:
                        print(f"Recent runs ({len(runs)}):\n")
                        for run in runs:
                            status_icon = "✓" if run.get("status") == "success" else "✗"
                            print(f"  {status_icon} {run['run_id']}")
                            print(f"    Recipe: {run.get('recipe', 'unknown')}")
                            print(f"    Status: {run.get('status', 'unknown')}")
                            print(f"    Time: {run.get('stored_at', 'unknown')}")
                            print()
            
            elif action == "stats":
                stats = history.get_stats()
                if parsed["json"]:
                    self._print_json(stats)
                else:
                    print("Run History Stats:")
                    print(f"  Total runs: {stats['total_runs']}")
                    print(f"  Storage size: {stats['total_size_bytes'] / 1024:.1f} KB")
                    print(f"  Path: {stats['storage_path']}")
            
            elif action == "cleanup":
                deleted = history.cleanup()
                if parsed["json"]:
                    self._print_json({"deleted": deleted})
                else:
                    self._print_success(f"Cleaned up {deleted} old runs")
            
            else:
                self._print_error(f"Unknown action: {action}. Use: list, stats, cleanup")
                return self.EXIT_VALIDATION_ERROR
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_sbom(self, args: List[str]) -> int:
        """Generate SBOM for a recipe."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "format": {"default": "cyclonedx"},
            "output": {"short": "-o", "default": None},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe path required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            from praisonai.recipe.security import generate_sbom
            
            recipe_path = Path(parsed["recipe"])
            if not recipe_path.exists():
                # Try to find recipe by name
                info = self.recipe.describe(parsed["recipe"])
                if info and info.path:
                    recipe_path = Path(info.path)
                else:
                    self._print_error(f"Recipe not found: {parsed['recipe']}")
                    return self.EXIT_NOT_FOUND
            
            sbom = generate_sbom(
                recipe_path=recipe_path,
                format=parsed["format"],
            )
            
            if parsed["output"]:
                with open(parsed["output"], "w") as f:
                    json.dump(sbom, f, indent=2)
                self._print_success(f"SBOM written to {parsed['output']}")
            elif parsed["json"]:
                self._print_json(sbom)
            else:
                print(f"SBOM ({parsed['format']}):")
                print(f"  Components: {len(sbom.get('components', []))}")
                for comp in sbom.get("components", [])[:10]:
                    print(f"    - {comp['name']}@{comp['version']}")
                if len(sbom.get("components", [])) > 10:
                    print(f"    ... and {len(sbom['components']) - 10} more")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_audit(self, args: List[str]) -> int:
        """Audit recipe dependencies."""
        spec = {
            "recipe": {"positional": True, "default": ""},
            "json": {"flag": True, "default": False},
            "strict": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["recipe"]:
            self._print_error("Recipe path required")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            from praisonai.recipe.security import audit_dependencies
            
            recipe_path = Path(parsed["recipe"])
            if not recipe_path.exists():
                info = self.recipe.describe(parsed["recipe"])
                if info and info.path:
                    recipe_path = Path(info.path)
                else:
                    self._print_error(f"Recipe not found: {parsed['recipe']}")
                    return self.EXIT_NOT_FOUND
            
            report = audit_dependencies(recipe_path)
            
            if parsed["json"]:
                self._print_json(report)
            else:
                print(f"Audit Report: {report['recipe']}")
                print(f"  Lockfile: {report['lockfile'] or 'Not found'}")
                print(f"  Dependencies: {len(report['dependencies'])}")
                
                if report["vulnerabilities"]:
                    print(f"\n  [red]Vulnerabilities ({len(report['vulnerabilities'])}):[/red]")
                    for vuln in report["vulnerabilities"]:
                        print(f"    - {vuln['package']}: {vuln['vulnerability_id']}")
                
                if report["warnings"]:
                    print("\n  Warnings:")
                    for warn in report["warnings"]:
                        print(f"    - {warn}")
                
                if report["passed"]:
                    self._print_success("Audit passed")
                else:
                    self._print_error("Audit failed")
            
            if parsed["strict"] and not report["passed"]:
                return self.EXIT_VALIDATION_ERROR
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_sign(self, args: List[str]) -> int:
        """Sign a recipe bundle."""
        spec = {
            "bundle": {"positional": True, "default": ""},
            "key": {"default": None},
            "output": {"short": "-o", "default": None},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["bundle"]:
            self._print_error("Bundle path required")
            return self.EXIT_VALIDATION_ERROR
        
        if not parsed["key"]:
            self._print_error("Private key path required (--key)")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            from praisonai.recipe.security import sign_bundle
            
            sig_path = sign_bundle(
                bundle_path=parsed["bundle"],
                private_key_path=parsed["key"],
                output_path=parsed["output"],
            )
            
            if parsed["json"]:
                self._print_json({"ok": True, "signature": str(sig_path)})
            else:
                self._print_success(f"Bundle signed: {sig_path}")
            
            return self.EXIT_SUCCESS
            
        except ImportError:
            self._print_error("cryptography package required. Install with: pip install cryptography")
            return self.EXIT_MISSING_DEPS
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_verify(self, args: List[str]) -> int:
        """Verify bundle signature."""
        spec = {
            "bundle": {"positional": True, "default": ""},
            "key": {"default": None},
            "signature": {"default": None},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed["bundle"]:
            self._print_error("Bundle path required")
            return self.EXIT_VALIDATION_ERROR
        
        if not parsed["key"]:
            self._print_error("Public key path required (--key)")
            return self.EXIT_VALIDATION_ERROR
        
        try:
            from praisonai.recipe.security import verify_bundle
            
            valid, message = verify_bundle(
                bundle_path=parsed["bundle"],
                public_key_path=parsed["key"],
                signature_path=parsed["signature"],
            )
            
            if parsed["json"]:
                self._print_json({"valid": valid, "message": message})
            else:
                if valid:
                    self._print_success(message)
                else:
                    self._print_error(message)
            
            return self.EXIT_SUCCESS if valid else self.EXIT_VALIDATION_ERROR
            
        except ImportError:
            self._print_error("cryptography package required. Install with: pip install cryptography")
            return self.EXIT_MISSING_DEPS
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def cmd_policy(self, args: List[str]) -> int:
        """Manage policy packs."""
        spec = {
            "action": {"positional": True, "default": "show"},
            "file": {"positional": True, "default": None},
            "output": {"short": "-o", "default": None},
            "json": {"flag": True, "default": False},
        }
        parsed = self._parse_args(args, spec)
        
        try:
            from praisonai.recipe.policy import PolicyPack, get_default_policy
            
            action = parsed["action"]
            
            if action == "show":
                # Show default or loaded policy
                if parsed["file"]:
                    policy = PolicyPack.load(parsed["file"])
                else:
                    policy = get_default_policy()
                
                if parsed["json"]:
                    self._print_json(policy.to_dict())
                else:
                    print(f"Policy: {policy.name}")
                    print(f"\nAllowed tools ({len(policy.allowed_tools)}):")
                    for tool in list(policy.allowed_tools)[:5]:
                        print(f"  - {tool}")
                    print(f"\nDenied tools ({len(policy.denied_tools)}):")
                    for tool in list(policy.denied_tools)[:5]:
                        print(f"  - {tool}")
                    print(f"\nPII mode: {policy.pii_mode}")
            
            elif action == "init":
                # Create a new policy file
                output = parsed["output"] or "policy.yaml"
                policy = get_default_policy()
                policy.save(output)
                self._print_success(f"Policy template created: {output}")
            
            elif action == "validate":
                if not parsed["file"]:
                    self._print_error("Policy file required")
                    return self.EXIT_VALIDATION_ERROR
                
                policy = PolicyPack.load(parsed["file"])
                self._print_success(f"Policy valid: {policy.name}")
            
            else:
                self._print_error(f"Unknown action: {action}. Use: show, init, validate")
                return self.EXIT_VALIDATION_ERROR
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_GENERAL_ERROR
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
    
    def cmd_judge(self, args: List[str]) -> int:
        """Judge a recipe execution trace and generate fix recommendations.
        
        Usage:
            praisonai recipe judge <trace_id> [options]
        
        Options:
            --yaml, -y <file>     YAML file path for fix recommendations
            --output, -o <file>   Output plan file (default: judge_plan.yaml)
            --dry-run             Show plan without saving
            --context             Evaluate context flow between agents (default)
            --memory              Evaluate memory utilization (store/search effectiveness)
            --knowledge           Evaluate knowledge retrieval effectiveness
        """
        spec = {
            "trace_id": {"positional": True},
            "yaml": {"short": "-y"},
            "output": {"short": "-o"},
            "dry_run": {"flag": True},
            "context": {"flag": True},
            "memory": {"flag": True},
            "knowledge": {"flag": True},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed.get("trace_id"):
            self._print_error("Trace ID required")
            print("\nUsage: praisonai recipe judge <trace_id> [--memory|--knowledge|--context]")
            print("\nExamples:")
            print("  praisonai recipe judge run-abc123")
            print("  praisonai recipe judge run-abc123 --memory")
            print("  praisonai recipe judge run-abc123 --knowledge")
            print("  praisonai recipe judge run-abc123 --yaml agents.yaml --output plan.yaml")
            return self.EXIT_VALIDATION_ERROR
        
        trace_id = parsed["trace_id"]
        yaml_file = parsed.get("yaml")
        output_file = parsed.get("output")
        dry_run = parsed.get("dry_run", False)
        
        # Determine evaluation mode (default to context)
        mode = "context"
        if parsed.get("memory"):
            mode = "memory"
        elif parsed.get("knowledge"):
            mode = "knowledge"
        
        mode_emoji = {"context": "🔄", "memory": "🧠", "knowledge": "📚"}
        print(f"{mode_emoji.get(mode, '🔍')} Judging trace: {trace_id} (mode: {mode})")
        
        try:
            from praisonai.replay import (
                ContextTraceReader,
                ContextEffectivenessJudge,
            )
            from praisonai.replay.judge import (
                generate_plan_from_report,
                format_judge_report,
            )
            
            reader = ContextTraceReader(trace_id)
            events = reader.get_all()
            
            if not events:
                self._print_error(f"No events found for trace: {trace_id}")
                return self.EXIT_NOT_FOUND
            
            print(f"  📊 Found {len(events)} events")
            
            # Run judge with mode-specific evaluation
            judge = ContextEffectivenessJudge(mode=mode)
            report = judge.judge_trace(events, session_id=trace_id, yaml_file=yaml_file)
            
            # Display report
            print(format_judge_report(report))
            
            # Generate plan if yaml_file provided
            if yaml_file:
                plan = generate_plan_from_report(report, yaml_file=yaml_file)
                print(plan.format_summary())
                
                if not dry_run:
                    out_file = output_file or "judge_plan.yaml"
                    plan.save(out_file)
                    self._print_success(f"Plan saved to: {out_file}")
                    print(f"   Run 'praisonai recipe apply {out_file}' to apply fixes")
            else:
                print("\n💡 Tip: Add --yaml <file> to generate actionable fix recommendations")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            import traceback
            traceback.print_exc()
            return self.EXIT_RUNTIME_ERROR
    
    def cmd_apply(self, args: List[str]) -> int:
        """Apply fixes from a judge plan to YAML files.
        
        Usage:
            praisonai recipe apply <plan_file> [options]
        
        Options:
            --confirm             Apply without confirmation prompts
            --fix-ids <ids>       Apply only specific fixes (comma-separated)
            --dry-run             Show changes without applying
        """
        spec = {
            "plan_file": {"type": "positional", "required": True},
            "confirm": {"type": "flag"},
            "fix_ids": {"type": "option", "name": "fix-ids"},
            "dry_run": {"type": "flag", "name": "dry-run"},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed.get("plan_file"):
            self._print_error("Plan file required")
            print("\nUsage: praisonai recipe apply <plan_file> [--confirm] [--dry-run]")
            return self.EXIT_VALIDATION_ERROR
        
        plan_file = parsed["plan_file"]
        confirm = parsed.get("confirm", False)
        fix_ids_str = parsed.get("fix_ids")
        dry_run = parsed.get("dry_run", False)
        
        fix_ids = None
        if fix_ids_str:
            fix_ids = [f.strip() for f in fix_ids_str.split(",")]
        
        try:
            from praisonai.replay.judge import JudgePlan
            
            plan = JudgePlan.load(plan_file)
            print(f"📋 Loaded plan: {plan_file}")
            print(f"   Fixes: {len(plan.fixes)}")
            
            if dry_run:
                print("\n[DRY RUN] Would apply the following fixes:")
                for fix in plan.fixes:
                    if fix_ids and fix.fix_id not in fix_ids:
                        continue
                    print(f"  - {fix.fix_id}: {fix.description}")
                return self.EXIT_SUCCESS
            
            # Apply fixes
            applied = plan.apply(fix_ids=fix_ids, confirm=confirm)
            self._print_success(f"Applied {applied} fixes")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            return self.EXIT_RUNTIME_ERROR


    def cmd_create(self, args: List[str]) -> int:
        """Create a new recipe from a natural language goal.
        
        Usage:
            praisonai recipe create "GOAL" [options]
        
        Options:
            --output, -o <dir>    Output directory (default: current dir)
            --no-optimize         Skip optimization loop
            --iterations <n>      Optimization iterations (default: 3)
            --threshold <n>       Score threshold to stop (default: 8.0)
            --agents <spec>       Custom agents (format: name:role=X,goal=Y;name2:...)
            --tools <spec>        Custom tools per agent (format: agent:tool1,tool2;...)
            --agent-types <spec>  Agent types (format: agent:image;agent2:audio;...)
        """
        spec = {
            "goal": {"positional": True},
            "output": {"short": "-o", "default": "."},
            "no_optimize": {"flag": True, "default": False},
            "iterations": {"default": "3"},
            "threshold": {"default": "8.0"},
            "agents": {"default": ""},
            "tools": {"default": ""},
            "agent_types": {"default": ""},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed.get("goal"):
            self._print_error("Goal required")
            print("\nUsage: praisonai recipe create \"GOAL\" [options]")
            print("\nExamples:")
            print('  praisonai recipe create "Build a web scraper for news"')
            print('  praisonai recipe create "Research AI trends" --no-optimize')
            print('  praisonai recipe create "Research AI" --agents "researcher:role=AI Researcher,goal=Find papers"')
            print('  praisonai recipe create "Research AI" --tools "researcher:internet_search,arxiv"')
            return self.EXIT_VALIDATION_ERROR
        
        goal = parsed["goal"]
        output_dir = Path(parsed["output"])
        no_optimize = parsed.get("no_optimize", False)
        iterations = int(parsed.get("iterations", 3))
        threshold = float(parsed.get("threshold", 8.0))
        
        # Parse customization options
        agents = self._parse_agents_spec(parsed.get("agents", ""))
        tools = self._parse_tools_spec(parsed.get("tools", ""))
        agent_types = self._parse_agent_types_spec(parsed.get("agent_types", ""))
        
        print(f"🚀 Creating recipe for: {goal}")
        if agents:
            print(f"   📋 Custom agents: {', '.join(agents.keys())}")
        if tools:
            print(f"   🔧 Custom tools: {sum(len(v) for v in tools.values())} tools")
        if agent_types:
            print(f"   🏷️  Agent types: {', '.join(f'{k}={v}' for k, v in agent_types.items())}")
        
        try:
            from .recipe_creator import RecipeCreator
            
            creator = RecipeCreator()
            recipe_path = creator.create(
                goal,
                output_dir=output_dir,
                agents=agents if agents else None,
                tools=tools if tools else None,
                agent_types=agent_types if agent_types else None,
            )
            
            self._print_success(f"Created recipe: {recipe_path}")
            print("   📄 agents.yaml  (agent definitions + metadata)")
            print("   📄 tools.py     (custom functions)")
            
            if not no_optimize:
                print(f"\n🔄 Starting optimization loop ({iterations} iterations, threshold: {threshold})")
                
                from .recipe_optimizer import RecipeOptimizer
                
                optimizer = RecipeOptimizer(
                    max_iterations=iterations,
                    score_threshold=threshold,
                )
                
                final_report = optimizer.optimize(recipe_path)
                
                if final_report:
                    score = getattr(final_report, 'overall_score', 0)
                    print(f"\n✅ Optimization complete! Final score: {score}/10")
            
            print(f"\n📁 Recipe ready at: {recipe_path}")
            print(f"   Run with: praisonai recipe run {recipe_path.name}")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            import traceback
            traceback.print_exc()
            return self.EXIT_RUNTIME_ERROR
    
    def cmd_optimize(self, args: List[str]) -> int:
        """Optimize an existing recipe using judge feedback.
        
        Usage:
            praisonai recipe optimize <NAME> [WHAT] [options]
        
        Options:
            --iterations <n>      Optimization iterations (default: 3)
            --threshold <n>       Score threshold to stop (default: 8.0)
            --input <text>        Input data for recipe runs
        """
        spec = {
            "name": {"positional": True},
            "target": {"positional": True, "default": ""},
            "iterations": {"default": "3"},
            "threshold": {"default": "8.0"},
            "input": {"short": "-i", "default": ""},
        }
        parsed = self._parse_args(args, spec)
        
        if not parsed.get("name"):
            self._print_error("Recipe name required")
            print("\nUsage: praisonai recipe optimize <NAME> [WHAT] [options]")
            print("\nExamples:")
            print('  praisonai recipe optimize my-recipe')
            print('  praisonai recipe optimize my-recipe "improve error handling"')
            return self.EXIT_VALIDATION_ERROR
        
        name = parsed["name"]
        target = parsed.get("target", "")
        iterations = int(parsed.get("iterations", 3))
        threshold = float(parsed.get("threshold", 8.0))
        input_data = parsed.get("input", "")
        
        # Find recipe path
        recipe_path = Path(name)
        if not recipe_path.exists():
            # Try as recipe name in current directory
            recipe_path = Path.cwd() / name
        if not recipe_path.exists():
            # Try in recipes directory
            try:
                recipe_path = self.recipe.get_recipe_path(name)
            except Exception:
                pass
        
        if not recipe_path.exists():
            self._print_error(f"Recipe not found: {name}")
            return self.EXIT_NOT_FOUND
        
        print(f"🔄 Optimizing recipe: {recipe_path.name}")
        if target:
            print(f"   Target: {target}")
        
        try:
            from .recipe_optimizer import RecipeOptimizer
            
            optimizer = RecipeOptimizer(
                max_iterations=iterations,
                score_threshold=threshold,
            )
            
            final_report = optimizer.optimize(
                recipe_path,
                input_data=input_data,
                optimization_target=target if target else None,
            )
            
            if final_report:
                score = getattr(final_report, 'overall_score', 0)
                self._print_success(f"Optimization complete! Final score: {score}/10")
            
            return self.EXIT_SUCCESS
            
        except Exception as e:
            self._print_error(str(e))
            import traceback
            traceback.print_exc()
            return self.EXIT_RUNTIME_ERROR


def handle_recipe_command(args: List[str]) -> int:
    """Entry point for recipe command."""
    handler = RecipeHandler()
    return handler.handle(args)
