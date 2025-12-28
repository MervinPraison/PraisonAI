"""
Templates CLI Feature Handler

Provides CLI commands for template management:
- list, search, info, install, cache clear
- run templates directly
- init projects from templates
- Custom templates directory support with precedence
"""

import shutil
from pathlib import Path
from typing import Any, Dict, List


class TemplatesHandler:
    """
    CLI handler for template operations.
    
    Commands:
    - list: List available templates
    - search: Search templates by query
    - info: Show template details
    - install: Install a template to cache
    - cache: Cache management (clear, list)
    - run: Run a template directly
    - init: Initialize a project from template
    """
    
    def __init__(self):
        """Initialize the handler with lazy-loaded dependencies."""
        self._loader = None
        self._registry = None
        self._cache = None
    
    @property
    def loader(self):
        """Lazy load template loader."""
        if self._loader is None:
            from praisonai.templates import TemplateLoader
            self._loader = TemplateLoader()
        return self._loader
    
    @property
    def registry(self):
        """Lazy load template registry."""
        if self._registry is None:
            from praisonai.templates import TemplateRegistry
            self._registry = TemplateRegistry()
        return self._registry
    
    @property
    def cache(self):
        """Lazy load template cache."""
        if self._cache is None:
            from praisonai.templates import TemplateCache
            self._cache = TemplateCache()
        return self._cache
    
    def handle(self, args: List[str]) -> int:
        """
        Handle templates subcommand.
        
        Args:
            args: Command arguments
            
        Returns:
            Exit code (0 for success)
        """
        if not args:
            self._print_help()
            return 0
        
        command = args[0]
        remaining = args[1:]
        
        commands = {
            "list": self.cmd_list,
            "search": self.cmd_search,
            "info": self.cmd_info,
            "install": self.cmd_install,
            "cache": self.cmd_cache,
            "run": self.cmd_run,
            "init": self.cmd_init,
            "add": self.cmd_add,
            "add-sources": self.cmd_add_sources,
            "remove-sources": self.cmd_remove_sources,
            "help": lambda _: self._print_help() or 0,
        }
        
        if command in commands:
            return commands[command](remaining)
        else:
            print(f"[red]Unknown command: {command}[/red]")
            self._print_help()
            return 1
    
    def _print_help(self):
        """Print help message."""
        help_text = """
[bold cyan]PraisonAI Templates[/bold cyan]

[bold]Usage:[/bold]
  praisonai templates <command> [options]

[bold]Commands:[/bold]
  list              List available templates
  search <query>    Search templates by name or tags
  info <template>   Show template details
  install <uri>     Install a template to cache
  cache clear       Clear the template cache
  cache list        List cached templates
  run <template>    Run a template directly
  init <name>       Initialize a project from template
  add <source>      Add template from GitHub or local path
  add-sources <src> Add a template source to persistent config
  remove-sources    Remove a template source from config

[bold]Options:[/bold]
  --offline         Use only cached templates (no network)
  --source <src>    Filter by source (custom, package, all)
  --custom-dir <path>  Add custom templates directory
  --paths           Show template search paths

[bold]Examples:[/bold]
  praisonai templates list
  praisonai templates search video
  praisonai templates info transcript-generator
  praisonai templates install github:MervinPraison/agent-recipes/transcript-generator
  praisonai templates run transcript-generator ./audio.mp3
  praisonai templates add github:user/repo/my-template
  praisonai templates add-sources github:MervinPraison/Agent-Recipes
  praisonai init my-project --template transcript-generator
"""
        try:
            from rich import print as rprint
            rprint(help_text)
        except ImportError:
            print(help_text.replace("[bold cyan]", "").replace("[/bold cyan]", "")
                  .replace("[bold]", "").replace("[/bold]", "")
                  .replace("[red]", "").replace("[/red]", ""))
    
    def cmd_list(self, args: List[str]) -> int:
        """List available templates from all sources including custom directories."""
        source_filter = None
        custom_dirs = []
        show_paths = "--paths" in args
        
        # Parse --source filter
        if "--source" in args:
            idx = args.index("--source")
            if idx + 1 < len(args):
                source_filter = args[idx + 1]
        
        # Parse --custom-dir (can be specified multiple times)
        i = 0
        while i < len(args):
            if args[i] == "--custom-dir" and i + 1 < len(args):
                custom_dirs.append(args[i + 1])
                i += 2
            else:
                i += 1
        
        try:
            from praisonai.templates.discovery import TemplateDiscovery
            
            discovery = TemplateDiscovery(
                custom_dirs=custom_dirs if custom_dirs else None,
                include_package=True,
                include_defaults=True
            )
            
            # Show search paths if requested
            if show_paths:
                print("\nTemplate Search Paths (in priority order):")
                for path, source, exists in discovery.get_search_paths():
                    status = "✓" if exists else "✗"
                    print(f"  {status} [{source}] {path}")
                print()
            
            # Discover templates
            templates = discovery.list_templates(source_filter=source_filter)
            
            if not templates:
                print("No templates found.")
                if not show_paths:
                    print("Use --paths to see search locations.")
                return 0
            
            try:
                from rich.console import Console
                from rich.table import Table
                
                console = Console()
                table = Table(title="Available Templates")
                table.add_column("Name", style="cyan")
                table.add_column("Version", style="green")
                table.add_column("Description")
                table.add_column("Source", style="dim")
                
                for t in sorted(templates, key=lambda x: (x.priority, x.name)):
                    desc = t.description or ""
                    table.add_row(
                        t.name,
                        t.version or "1.0.0",
                        desc[:50] + "..." if len(desc) > 50 else desc,
                        t.source
                    )
                
                console.print(table)
            except ImportError:
                print(f"{'Name':<25} {'Version':<10} {'Source':<10} {'Description':<35}")
                print("-" * 80)
                for t in sorted(templates, key=lambda x: (x.priority, x.name)):
                    desc = (t.description or "")[:35]
                    if len(t.description or "") > 35:
                        desc += "..."
                    print(f"{t.name:<25} {t.version or '1.0.0':<10} {t.source:<10} {desc:<35}")
            
            return 0
            
        except Exception as e:
            print(f"Error listing templates: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    def cmd_search(self, args: List[str]) -> int:
        """Search templates by query."""
        if not args or args[0].startswith("--"):
            print("Usage: praisonai templates search <query>")
            return 1
        
        query = args[0]
        offline = "--offline" in args
        
        try:
            from praisonai.templates import search_templates
            templates = search_templates(query, offline=offline)
            
            if not templates:
                print(f"No templates found matching '{query}'")
                return 0
            
            print(f"Found {len(templates)} template(s) matching '{query}':\n")
            for t in templates:
                print(f"  • {t.name} (v{t.version})")
                if t.description:
                    print(f"    {t.description}")
                if t.tags:
                    print(f"    Tags: {', '.join(t.tags)}")
                print()
            
            return 0
            
        except Exception as e:
            print(f"Error searching templates: {e}")
            return 1
    
    def cmd_info(self, args: List[str]) -> int:
        """Show template details with custom directory support."""
        if not args or args[0].startswith("--"):
            print("Usage: praisonai templates info <template>")
            return 1
        
        name_or_uri = args[0]
        offline = "--offline" in args
        custom_dirs = []
        
        # Parse --custom-dir
        i = 0
        while i < len(args):
            if args[i] == "--custom-dir" and i + 1 < len(args):
                custom_dirs.append(args[i + 1])
                i += 2
            else:
                i += 1
        
        try:
            # First try to find in custom/local directories
            from praisonai.templates.discovery import TemplateDiscovery
            
            discovery = TemplateDiscovery(
                custom_dirs=custom_dirs if custom_dirs else None,
                include_package=True,
                include_defaults=True
            )
            
            discovered = discovery.find_template(name_or_uri)
            
            if discovered:
                # Load from discovered path
                from praisonai.templates import load_template
                template = load_template(str(discovered.path), offline=offline)
            else:
                # Fall back to URI resolution
                from praisonai.templates import load_template
                template = load_template(name_or_uri, offline=offline)
            
            # Check dependency availability
            from praisonai.templates.dependency_checker import DependencyChecker
            checker = DependencyChecker()
            deps = checker.check_template_dependencies(template)
            
            # Build availability strings
            def format_dep_list(items, key="available"):
                result = []
                for item in items:
                    status = "✓" if item.get(key, False) else "✗"
                    hint = ""
                    if not item.get(key, False):
                        if item.get("install_hint"):
                            hint = f" ({item['install_hint']})"
                    result.append(f"{status} {item['name']}{hint}")
                return result
            
            tools_status = format_dep_list(deps["tools"])
            pkgs_status = format_dep_list(deps["packages"])
            env_status = format_dep_list(deps["env"])
            
            try:
                from rich.console import Console
                from rich.panel import Panel
                from rich.markdown import Markdown
                
                console = Console()
                
                info = f"""
**Name:** {template.name}
**Version:** {template.version}
**Author:** {template.author or 'Unknown'}
**License:** {template.license or 'Not specified'}

**Description:**
{template.description}

**Tags:** {', '.join(template.tags) if template.tags else 'None'}

**Skills:** {', '.join(template.skills) if template.skills else 'None'}

**Path:** {template.path}
"""
                console.print(Panel(Markdown(info), title=f"Template: {template.name}"))
                
                # Print dependency status
                all_ok = "✓" if deps["all_satisfied"] else "✗"
                console.print(f"\n[bold]Dependencies Status:[/bold] {all_ok}")
                
                if tools_status:
                    console.print("\n[bold]Required Tools:[/bold]")
                    for t in tools_status:
                        color = "green" if t.startswith("✓") else "red"
                        console.print(f"  [{color}]{t}[/{color}]")
                
                if pkgs_status:
                    console.print("\n[bold]Required Packages:[/bold]")
                    for p in pkgs_status:
                        color = "green" if p.startswith("✓") else "red"
                        console.print(f"  [{color}]{p}[/{color}]")
                
                if env_status:
                    console.print("\n[bold]Required Environment:[/bold]")
                    for e in env_status:
                        color = "green" if e.startswith("✓") else "red"
                        console.print(f"  [{color}]{e}[/{color}]")
                
                # Print install hints if any missing
                if not deps["all_satisfied"]:
                    hints = checker.get_install_hints(template)
                    if hints:
                        console.print("\n[bold yellow]To fix missing dependencies:[/bold yellow]")
                        for hint in hints:
                            console.print(f"  • {hint}")
                
            except ImportError:
                print(f"Template: {template.name}")
                print(f"Version: {template.version}")
                print(f"Author: {template.author or 'Unknown'}")
                print(f"Description: {template.description}")
                print(f"Path: {template.path}")
                print(f"\nDependencies: {'All satisfied' if deps['all_satisfied'] else 'Some missing'}")
                if tools_status:
                    print("\nRequired Tools:")
                    for t in tools_status:
                        print(f"  {t}")
                if pkgs_status:
                    print("\nRequired Packages:")
                    for p in pkgs_status:
                        print(f"  {p}")
                if env_status:
                    print("\nRequired Environment:")
                    for e in env_status:
                        print(f"  {e}")
            
            return 0
            
        except Exception as e:
            print(f"Error loading template info: {e}")
            return 1
    
    def cmd_install(self, args: List[str]) -> int:
        """Install a template to cache."""
        if not args or args[0].startswith("--"):
            print("Usage: praisonai templates install <uri>")
            return 1
        
        uri = args[0]
        
        try:
            from praisonai.templates import install_template
            
            print(f"Installing template: {uri}")
            cached = install_template(uri)
            print(f"✓ Template installed to: {cached.path}")
            
            return 0
            
        except Exception as e:
            print(f"Error installing template: {e}")
            return 1
    
    def cmd_cache(self, args: List[str]) -> int:
        """Cache management commands."""
        if not args:
            print("Usage: praisonai templates cache <clear|list|size>")
            return 1
        
        subcmd = args[0]
        
        if subcmd == "clear":
            source = None
            if len(args) > 1:
                source = args[1]
            
            try:
                from praisonai.templates import clear_cache
                count = clear_cache(source)
                print(f"✓ Cleared {count} cached template(s)")
                return 0
            except Exception as e:
                print(f"Error clearing cache: {e}")
                return 1
        
        elif subcmd == "list":
            try:
                cached = self.cache.list_cached()
                if not cached:
                    print("No cached templates.")
                    return 0
                
                print(f"Cached templates ({len(cached)}):\n")
                for path, meta in cached:
                    status = "pinned" if meta.is_pinned else "expires in " + str(int(meta.ttl_seconds - (import_time() - meta.fetched_at))) + "s"
                    print(f"  • {path.name}")
                    print(f"    Path: {path}")
                    print(f"    Status: {status}")
                    print()
                
                return 0
            except Exception as e:
                print(f"Error listing cache: {e}")
                return 1
        
        elif subcmd == "size":
            size = self.cache.get_cache_size()
            print(f"Cache size: {size / 1024 / 1024:.2f} MB")
            return 0
        
        else:
            print(f"Unknown cache command: {subcmd}")
            return 1
    
    def cmd_run(self, args: List[str]) -> int:
        """Run a template directly."""
        if not args or args[0].startswith("--"):
            print("Usage: praisonai templates run <template> [args...] [--strict-tools] [--offline]")
            return 1
        
        uri = args[0]
        template_args = args[1:]
        offline = "--offline" in args
        strict_tools = "--strict-tools" in args
        no_template_tools_py = "--no-template-tools-py" in args
        
        # Parse --tools, --tools-dir, --tools-source overrides
        tools_files = []
        tools_dirs = []
        tools_sources_override = []
        i = 0
        while i < len(args):
            if args[i] == "--tools" and i + 1 < len(args):
                tools_files.append(args[i + 1])
                i += 2
            elif args[i] == "--tools-dir" and i + 1 < len(args):
                tools_dirs.append(args[i + 1])
                i += 2
            elif args[i] == "--tools-source" and i + 1 < len(args):
                tools_sources_override.append(args[i + 1])
                i += 2
            else:
                i += 1
        
        try:
            from praisonai.templates.loader import TemplateLoader
            from praisonai.templates.discovery import TemplateDiscovery
            
            # First try to find in custom/local directories
            discovery = TemplateDiscovery(
                custom_dirs=tools_dirs if tools_dirs else None,
                include_package=True,
                include_defaults=True
            )
            
            discovered = discovery.find_template(uri)
            
            loader = TemplateLoader(offline=offline)
            
            if discovered:
                # Load from discovered path
                template = loader.load(str(discovered.path), offline=offline)
            else:
                # Fall back to URI resolution
                template = loader.load(uri, offline=offline)
            
            # Strict mode: fail-fast on missing dependencies
            if strict_tools:
                from praisonai.templates.dependency_checker import DependencyChecker, StrictModeError
                checker = DependencyChecker()
                try:
                    checker.enforce_strict_mode(template)
                    print("✓ All dependencies satisfied (strict mode)")
                except StrictModeError as e:
                    print(f"✗ Strict mode check failed:\n{e}")
                    return 1
            else:
                # Non-strict: warn but continue
                missing = loader.check_requirements(template)
                if missing["missing_packages"]:
                    print(f"Warning: Missing packages: {', '.join(missing['missing_packages'])}")
                    print("Install with: pip install " + " ".join(missing["missing_packages"]))
                if missing["missing_env"]:
                    print(f"Warning: Missing environment variables: {', '.join(missing['missing_env'])}")
            
            # Load tool overrides if specified
            tool_registry = None
            from praisonai.templates.tool_override import create_tool_registry_with_overrides, resolve_tools
            
            # Get template directory for local tools.py autoload (unless disabled)
            template_dir = None
            if not no_template_tools_py:
                template_dir = str(template.path) if template.path else None
            
            # Get tools_sources from template requires + CLI overrides
            tools_sources = []
            if template.requires and isinstance(template.requires, dict):
                ts = template.requires.get("tools_sources", [])
                if ts:
                    tools_sources.extend(ts)
            # Add CLI --tools-source overrides
            if tools_sources_override:
                tools_sources.extend(tools_sources_override)
            
            # Always build registry (includes defaults + template sources)
            tool_registry = create_tool_registry_with_overrides(
                override_files=tools_files if tools_files else None,
                override_dirs=tools_dirs if tools_dirs else None,
                include_defaults=True,
                tools_sources=tools_sources if tools_sources else None,
                template_dir=template_dir,
            )
            
            if tools_files or tools_dirs:
                print(f"✓ Loaded {len(tool_registry)} tools from overrides")
            
            # Load and run workflow
            workflow_config = loader.load_workflow_config(template)
            
            # Parse template args into config
            config = self._parse_template_args(template_args, template)
            
            # Merge config
            if config:
                workflow_config = {**workflow_config, **config}
            
            # Run workflow - determine which class to use based on config structure
            if "agents" in workflow_config and "tasks" in workflow_config:
                # PraisonAIAgents format (agents + tasks)
                from praisonaiagents import Agent, Task, PraisonAIAgents
                
                # Build agents
                agents_config = workflow_config.get("agents", [])
                agents = []
                agent_map = {}
                
                for agent_cfg in agents_config:
                    # Resolve tool names to callable tools
                    agent_tool_names = agent_cfg.get("tools", [])
                    resolved_agent_tools = resolve_tools(
                        agent_tool_names,
                        registry=tool_registry,
                        template_dir=template_dir
                    )
                    
                    agent = Agent(
                        name=agent_cfg.get("name", "Agent"),
                        role=agent_cfg.get("role", ""),
                        goal=agent_cfg.get("goal", ""),
                        backstory=agent_cfg.get("backstory", ""),
                        tools=resolved_agent_tools,
                        llm=agent_cfg.get("llm"),
                        verbose=agent_cfg.get("verbose", True)
                    )
                    agents.append(agent)
                    agent_map[agent_cfg.get("name", "Agent")] = agent
                
                # Build tasks
                tasks_config = workflow_config.get("tasks", [])
                tasks = []
                
                for task_cfg in tasks_config:
                    agent_name = task_cfg.get("agent", "")
                    agent = agent_map.get(agent_name, agents[0] if agents else None)
                    
                    task = Task(
                        name=task_cfg.get("name", "Task"),
                        description=task_cfg.get("description", ""),
                        expected_output=task_cfg.get("expected_output", ""),
                        agent=agent
                    )
                    tasks.append(task)
                
                # Run
                praison_agents = PraisonAIAgents(
                    agents=agents,
                    tasks=tasks,
                    process=workflow_config.get("process", "sequential"),
                    verbose=workflow_config.get("verbose", 1)
                )
                praison_agents.start()
            elif "steps" in workflow_config:
                # Workflow format (steps) - resolve tools in each step's agent
                from praisonaiagents import Workflow
                
                # Resolve tools for each step's agent if specified
                steps = workflow_config.get("steps", [])
                for step in steps:
                    if "agent" in step and isinstance(step["agent"], dict):
                        agent_cfg = step["agent"]
                        if "tools" in agent_cfg:
                            agent_cfg["tools"] = resolve_tools(
                                agent_cfg["tools"],
                                registry=tool_registry,
                                template_dir=template_dir
                            )
                
                workflow = Workflow(**workflow_config)
                workflow.run()
            else:
                raise ValueError("Invalid workflow config: must have 'agents'+'tasks' or 'steps'")
            
            print(f"\n✓ Template '{template.name}' completed successfully")
            return 0
            
        except Exception as e:
            print(f"Error running template: {e}")
            import traceback
            traceback.print_exc()
            return 1
    
    def cmd_init(self, args: List[str]) -> int:
        """Initialize a project from template."""
        if not args or args[0].startswith("--"):
            print("Usage: praisonai templates init <project-name> --template <template>")
            return 1
        
        project_name = args[0]
        template_uri = None
        offline = "--offline" in args
        
        if "--template" in args:
            idx = args.index("--template")
            if idx + 1 < len(args):
                template_uri = args[idx + 1]
        
        if not template_uri:
            print("Error: --template is required")
            return 1
        
        try:
            from praisonai.templates import load_template
            
            template = load_template(template_uri, offline=offline)
            
            # Create project directory
            project_dir = Path(project_name)
            if project_dir.exists():
                print(f"Error: Directory '{project_name}' already exists")
                return 1
            
            project_dir.mkdir(parents=True)
            
            # Copy template files
            for item in template.path.iterdir():
                if item.name.startswith("."):
                    continue
                if item.is_file():
                    shutil.copy2(item, project_dir / item.name)
                elif item.is_dir():
                    shutil.copytree(item, project_dir / item.name)
            
            print(f"✓ Created project '{project_name}' from template '{template.name}'")
            print("Next steps:")
            print(f"  cd {project_name}")
            print("  praisonai run workflow.yaml")
            
            return 0
            
        except Exception as e:
            print(f"Error initializing project: {e}")
            return 1
    
    def _parse_template_args(
        self,
        args: List[str],
        template
    ) -> Dict[str, Any]:
        """Parse template-specific arguments."""
        config = {}
        
        # Handle positional args based on CLI config
        cli_config = template.cli
        if cli_config and "args" in cli_config:
            positional_idx = 0
            for arg_def in cli_config["args"]:
                if arg_def.get("positional"):
                    if positional_idx < len(args) and not args[positional_idx].startswith("--"):
                        config[arg_def["name"]] = args[positional_idx]
                        positional_idx += 1
        
        # Handle named args
        i = 0
        while i < len(args):
            if args[i].startswith("--"):
                key = args[i][2:].replace("-", "_")
                if i + 1 < len(args) and not args[i + 1].startswith("--"):
                    config[key] = args[i + 1]
                    i += 2
                else:
                    config[key] = True
                    i += 1
            else:
                i += 1
        
        return config
    
    def _get_templates_config_path(self):
        """Get the path to the templates config file."""
        config_dir = Path.home() / ".praison"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "templates_sources.yaml"
    
    def _load_templates_config(self) -> Dict[str, Any]:
        """Load templates config from file."""
        import yaml
        config_path = self._get_templates_config_path()
        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        return {"sources": []}
    
    def _save_templates_config(self, config: Dict[str, Any]):
        """Save templates config to file."""
        import yaml
        config_path = self._get_templates_config_path()
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
    
    def cmd_add(self, args: List[str]) -> int:
        """
        Add template from GitHub or local path.
        
        Args:
            args: [source] - github:user/repo/template or local path
        """
        if not args:
            print("[red]Usage: praisonai templates add <source>[/red]")
            print("  source: github:user/repo/template or local path")
            return 1
        
        source = args[0]
        
        # Check if it's a local directory
        if source.startswith("./") or source.startswith("/"):
            path = Path(source).resolve()
            if path.exists() and path.is_dir():
                # Check for TEMPLATE.yaml
                template_yaml = path / "TEMPLATE.yaml"
                if not template_yaml.exists():
                    print(f"[red]Not a valid template: {path} (missing TEMPLATE.yaml)[/red]")
                    return 1
                
                # Copy to ~/.praison/templates/
                templates_dir = Path.home() / ".praison" / "templates"
                templates_dir.mkdir(parents=True, exist_ok=True)
                dest = templates_dir / path.name
                
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(path, dest)
                
                print(f"\n✅ Added template: {path.name}")
                print(f"   Copied to: {dest}")
                return 0
            else:
                print(f"[red]Directory not found: {source}[/red]")
                return 1
        
        # Check if it's a GitHub reference
        elif source.startswith("github:"):
            github_path = source[7:]  # Remove "github:"
            parts = github_path.split("/")
            if len(parts) < 3:
                print("[red]Invalid GitHub format. Use: github:user/repo/template-name[/red]")
                return 1
            
            user, repo = parts[0], parts[1]
            template_path = "/".join(parts[2:])
            
            # Download from GitHub
            import urllib.request
            import tempfile
            import zipfile
            
            try:
                # Download repo as zip
                zip_url = f"https://github.com/{user}/{repo}/archive/refs/heads/main.zip"
                print(f"Downloading from: {zip_url}")
                
                with tempfile.TemporaryDirectory() as tmpdir:
                    zip_path = Path(tmpdir) / "repo.zip"
                    urllib.request.urlretrieve(zip_url, zip_path)
                    
                    # Extract
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(tmpdir)
                    
                    # Find the template
                    extracted_dir = Path(tmpdir) / f"{repo}-main"
                    template_src = extracted_dir / template_path
                    
                    if not template_src.exists():
                        # Try common paths
                        for alt_path in [
                            extracted_dir / "agent_recipes" / "templates" / template_path,
                            extracted_dir / "templates" / template_path,
                        ]:
                            if alt_path.exists():
                                template_src = alt_path
                                break
                    
                    if not template_src.exists():
                        print(f"[red]Template not found: {template_path}[/red]")
                        return 1
                    
                    # Copy to ~/.praison/templates/
                    templates_dir = Path.home() / ".praison" / "templates"
                    templates_dir.mkdir(parents=True, exist_ok=True)
                    dest = templates_dir / template_src.name
                    
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(template_src, dest)
                    
                    print(f"\n✅ Added template from GitHub: {user}/{repo}/{template_path}")
                    print(f"   Saved to: {dest}")
                    return 0
                    
            except Exception as e:
                print(f"[red]Failed to download from GitHub: {e}[/red]")
                return 1
        
        else:
            print(f"[red]Unknown source format: {source}[/red]")
            print("Use: github:user/repo/template or ./local-path")
            return 1
    
    def cmd_add_sources(self, args: List[str]) -> int:
        """
        Add a template source to persistent config.
        
        Args:
            args: [source] - github:user/repo or URL
        """
        if not args:
            print("[red]Usage: praisonai templates add-sources <source>[/red]")
            return 1
        
        source = args[0]
        config = self._load_templates_config()
        
        if "sources" not in config:
            config["sources"] = []
        
        if source in config["sources"]:
            print(f"[yellow]Source '{source}' already in config[/yellow]")
            return 0
        
        config["sources"].append(source)
        self._save_templates_config(config)
        
        print(f"\n✅ Added template source: {source}")
        print(f"   Config saved to: {self._get_templates_config_path()}")
        return 0
    
    def cmd_remove_sources(self, args: List[str]) -> int:
        """
        Remove a template source from persistent config.
        
        Args:
            args: [source] - source to remove
        """
        if not args:
            print("[red]Usage: praisonai templates remove-sources <source>[/red]")
            return 1
        
        source = args[0]
        config = self._load_templates_config()
        
        if "sources" not in config or source not in config["sources"]:
            print(f"[yellow]Source '{source}' not found in config[/yellow]")
            return 1
        
        config["sources"].remove(source)
        self._save_templates_config(config)
        
        print(f"\n✅ Removed template source: {source}")
        return 0


def import_time():
    """Get current time (helper for cache expiry display)."""
    import time
    return time.time()


# Convenience function for CLI integration
def handle_templates_command(args: List[str]) -> int:
    """Handle templates command from main CLI."""
    handler = TemplatesHandler()
    return handler.handle(args)
