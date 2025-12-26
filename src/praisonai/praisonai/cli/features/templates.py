"""
Templates CLI Feature Handler

Provides CLI commands for template management:
- list, search, info, install, cache clear
- run templates directly
- init projects from templates
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

[bold]Options:[/bold]
  --offline         Use only cached templates (no network)
  --source <src>    Filter by source (local, remote, cached)

[bold]Examples:[/bold]
  praisonai templates list
  praisonai templates search video
  praisonai templates info transcript-generator
  praisonai templates install github:MervinPraison/agent-recipes/transcript-generator
  praisonai templates run transcript-generator ./audio.mp3
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
        """List available templates."""
        offline = "--offline" in args
        source = "all"
        
        if "--source" in args:
            idx = args.index("--source")
            if idx + 1 < len(args):
                source = args[idx + 1]
        
        try:
            from praisonai.templates import list_templates
            templates = list_templates(source=source, offline=offline)
            
            if not templates:
                print("No templates found.")
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
                
                for t in templates:
                    table.add_row(
                        t.name,
                        t.version,
                        t.description[:50] + "..." if len(t.description) > 50 else t.description,
                        t.source or "local"
                    )
                
                console.print(table)
            except ImportError:
                print(f"{'Name':<25} {'Version':<10} {'Description':<40}")
                print("-" * 80)
                for t in templates:
                    desc = t.description[:40] + "..." if len(t.description) > 40 else t.description
                    print(f"{t.name:<25} {t.version:<10} {desc:<40}")
            
            return 0
            
        except Exception as e:
            print(f"[red]Error listing templates: {e}[/red]")
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
        """Show template details."""
        if not args or args[0].startswith("--"):
            print("Usage: praisonai templates info <template>")
            return 1
        
        uri = args[0]
        offline = "--offline" in args
        
        try:
            from praisonai.templates import load_template
            template = load_template(uri, offline=offline)
            
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

**Requirements:**
- Tools: {', '.join(template.requires.get('tools', [])) or 'None'}
- Packages: {', '.join(template.requires.get('packages', [])) or 'None'}
- Environment: {', '.join(template.requires.get('env', [])) or 'None'}

**Skills:** {', '.join(template.skills) if template.skills else 'None'}

**Path:** {template.path}
"""
                console.print(Panel(Markdown(info), title=f"Template: {template.name}"))
                
            except ImportError:
                print(f"Template: {template.name}")
                print(f"Version: {template.version}")
                print(f"Author: {template.author or 'Unknown'}")
                print(f"Description: {template.description}")
                print(f"Path: {template.path}")
            
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
            print("Usage: praisonai templates run <template> [args...]")
            return 1
        
        uri = args[0]
        template_args = args[1:]
        offline = "--offline" in args
        
        try:
            from praisonai.templates import load_template
            from praisonai.templates.loader import TemplateLoader
            
            loader = TemplateLoader(offline=offline)
            template = loader.load(uri, offline=offline)
            
            # Check requirements
            missing = loader.check_requirements(template)
            if missing["missing_packages"]:
                print(f"Missing packages: {', '.join(missing['missing_packages'])}")
                print("Install with: pip install " + " ".join(missing["missing_packages"]))
            if missing["missing_env"]:
                print(f"Missing environment variables: {', '.join(missing['missing_env'])}")
            
            if missing["missing_packages"] or missing["missing_env"]:
                return 1
            
            # Load and run workflow
            workflow_config = loader.load_workflow_config(template)
            
            # Parse template args into config
            config = self._parse_template_args(template_args, template)
            
            # Merge config
            if config:
                workflow_config = {**workflow_config, **config}
            
            # Run workflow
            from praisonaiagents import Workflow
            workflow = Workflow(**workflow_config)
            workflow.run()
            
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


def import_time():
    """Get current time (helper for cache expiry display)."""
    import time
    return time.time()


# Convenience function for CLI integration
def handle_templates_command(args: List[str]) -> int:
    """Handle templates command from main CLI."""
    handler = TemplatesHandler()
    return handler.handle(args)
