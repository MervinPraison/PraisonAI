"""
Tools Handler for CLI.

Provides tool registry management.
Usage: praisonai tools list
       praisonai tools info internet_search
"""

from typing import Any, Dict, List
from .base import CommandHandler


class ToolsHandler(CommandHandler):
    """
    Handler for tools command.
    
    Manages tool registry and provides tool information.
    
    Example:
        praisonai tools list
        praisonai tools info internet_search
        praisonai tools search "web"
    """
    
    def __init__(self, verbose: bool = False):
        super().__init__(verbose)
        self._registry = None
    
    @property
    def feature_name(self) -> str:
        return "tools"
    
    def get_actions(self) -> List[str]:
        return ["list", "info", "search", "doctor", "resolve", "discover", "show-sources", "add", "add-sources", "remove-sources", "help"]
    
    def get_help_text(self) -> str:
        return """
Tools Commands:
  praisonai tools list                   - List all available tools
  praisonai tools info <name>            - Show tool details
  praisonai tools search <query>         - Search tools by name/description
  praisonai tools doctor                 - Diagnose tool availability and dependencies
  praisonai tools doctor --json          - Output diagnosis as JSON
  praisonai tools resolve <name>         - Resolve a tool name to its source
  praisonai tools discover               - Discover tools from installed packages
  praisonai tools show-sources           - Show all tool sources for a template
  praisonai tools add <source>           - Add tools from package, file, or GitHub
  praisonai tools add-sources <source>   - Add a tool source to persistent config
  praisonai tools remove-sources <source> - Remove a tool source from config

Add Examples:
  praisonai tools add pandas             - Wrap pandas functions as tools
  praisonai tools add ./my_tools.py      - Add local tools file
  praisonai tools add github:user/repo   - Add tools from GitHub

Built-in tools include: internet_search, calculator, file operations, etc.
"""
    
    def _get_registry(self):
        """Get tool registry lazily."""
        if self._registry is None:
            try:
                from praisonaiagents.tools import get_registry
                self._registry = get_registry()
            except ImportError:
                self.print_status(
                    "Tools require praisonaiagents. Install with: pip install praisonaiagents",
                    "error"
                )
                return None
        return self._registry
    
    def _get_builtin_tools(self) -> Dict[str, Any]:
        """Get dictionary of built-in tools."""
        tools = {}
        try:
            from praisonaiagents.tools import TOOL_MAPPINGS
            tools.update(TOOL_MAPPINGS)
        except ImportError:
            pass
        
        # Add common tool descriptions
        tool_descriptions = {
            "internet_search": "Search the internet using DuckDuckGo",
            "calculator": "Perform mathematical calculations",
            "read_file": "Read contents of a file",
            "write_file": "Write content to a file",
            "list_files": "List files in a directory",
            "execute_code": "Execute Python code",
            "shell_command": "Execute shell commands",
            "wikipedia_search": "Search Wikipedia",
            "arxiv_search": "Search arXiv papers",
            "tavily_search": "Search using Tavily API",
            "csv_read": "Read CSV files",
            "json_read": "Read JSON files",
            "yaml_read": "Read YAML files",
        }
        
        for name, desc in tool_descriptions.items():
            if name not in tools:
                tools[name] = {"description": desc, "available": name in tools}
        
        return tools
    
    def action_list(self, args: List[str], **kwargs) -> List[str]:
        """
        List all available tools.
        
        Returns:
            List of tool names
        """
        tools = self._get_builtin_tools()
        
        self.print_status("\n🔧 Available Tools:", "info")
        self.print_status("-" * 50, "info")
        
        # Group by category
        categories = {
            "Search": ["internet_search", "wikipedia_search", "arxiv_search", "tavily_search"],
            "File": ["read_file", "write_file", "list_files", "csv_read", "json_read", "yaml_read"],
            "Code": ["execute_code", "shell_command", "calculator"],
        }
        
        for category, tool_names in categories.items():
            self.print_status(f"\n  {category}:", "info")
            for name in tool_names:
                if name in tools:
                    desc = tools[name].get("description", "No description") if isinstance(tools[name], dict) else "Available"
                    self.print_status(f"    • {name}: {desc}", "info")
        
        # List any uncategorized tools
        categorized = set(t for tools_list in categories.values() for t in tools_list)
        uncategorized = [t for t in tools.keys() if t not in categorized]
        
        if uncategorized:
            self.print_status("\n  Other:", "info")
            for name in uncategorized[:10]:  # Limit to 10
                self.print_status(f"    • {name}", "info")
        
        # Show added tool sources from config
        config = self._load_config()
        if config.get("sources"):
            self.print_status("\n  Added Sources (use with Agent):", "info")
            for source in config["sources"]:
                self.print_status(f"    • {source}", "info")
        
        return list(tools.keys())
    
    def action_info(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Show tool information.
        
        Args:
            args: List containing tool name
            
        Returns:
            Dictionary of tool info
        """
        if not args:
            self.print_status("Usage: praisonai tools info <tool_name>", "error")
            return {}
        
        tool_name = args[0]
        
        try:
            import praisonaiagents.tools as tools_module
            
            if hasattr(tools_module, tool_name):
                tool = getattr(tools_module, tool_name)
                
                info = {
                    "name": tool_name,
                    "type": type(tool).__name__,
                    "doc": tool.__doc__ or "No documentation",
                }
                
                # Get function signature if available
                if callable(tool):
                    import inspect
                    try:
                        sig = inspect.signature(tool)
                        info["signature"] = str(sig)
                        info["parameters"] = list(sig.parameters.keys())
                    except (ValueError, TypeError):
                        pass
                
                self.print_status(f"\n🔧 Tool: {tool_name}", "info")
                self.print_status("-" * 40, "info")
                for key, value in info.items():
                    if key == "doc":
                        self.print_status(f"\nDescription:\n{value}", "info")
                    else:
                        self.print_status(f"  {key}: {value}", "info")
                
                return info
            else:
                self.print_status(f"Tool '{tool_name}' not found", "error")
                return {}
                
        except ImportError:
            self.print_status("Could not load tools module", "error")
            return {}
    
    def action_search(self, args: List[str], **kwargs) -> List[str]:
        """
        Search tools by name or description.
        
        Args:
            args: List containing search query
            
        Returns:
            List of matching tool names
        """
        if not args:
            self.print_status("Usage: praisonai tools search <query>", "error")
            return []
        
        query = ' '.join(args).lower()
        tools = self._get_builtin_tools()
        
        matches = []
        for name, info in tools.items():
            desc = info.get("description", "") if isinstance(info, dict) else ""
            if query in name.lower() or query in desc.lower():
                matches.append(name)
        
        if matches:
            self.print_status(f"\n🔍 Tools matching '{query}':", "info")
            for name in matches:
                self.print_status(f"  • {name}", "info")
        else:
            self.print_status(f"No tools found matching '{query}'", "warning")
        
        return matches
    
    def action_doctor(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Diagnose tool availability and dependencies.
        
        Args:
            args: List containing optional flags (--json)
            
        Returns:
            Dict with diagnostic results
        """
        json_output = "--json" in args
        
        try:
            from praisonai.templates.tools_doctor import ToolsDoctor
            
            doctor = ToolsDoctor()
            
            if json_output:
                print(doctor.diagnose_json())
            else:
                print(doctor.diagnose_human())
            
            return doctor.diagnose()
            
        except Exception as e:
            self.print_status(f"Error running diagnostics: {e}", "error")
            return {}
    
    def action_resolve(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Resolve a tool name to its source.
        
        Args:
            args: [tool_name, --template <template>, --tools <file>, --tools-dir <dir>]
        """
        if not args:
            self.print_status("Usage: praisonai tools resolve <tool_name> [--template <template>]", "error")
            return {}
        
        tool_name = args[0]
        template_name = None
        tools_files = []
        tools_dirs = []
        
        # Parse flags
        i = 1
        while i < len(args):
            if args[i] == "--template" and i + 1 < len(args):
                template_name = args[i + 1]
                i += 2
            elif args[i] == "--tools" and i + 1 < len(args):
                tools_files.append(args[i + 1])
                i += 2
            elif args[i] == "--tools-dir" and i + 1 < len(args):
                tools_dirs.append(args[i + 1])
                i += 2
            else:
                i += 1
        
        try:
            from praisonai.templates.tool_override import create_tool_registry_with_overrides, resolve_tools
            
            registry = create_tool_registry_with_overrides(
                override_files=tools_files if tools_files else None,
                override_dirs=tools_dirs if tools_dirs else None,
                include_defaults=True,
            )
            
            resolved = resolve_tools([tool_name], registry=registry)
            
            if resolved:
                tool = resolved[0]
                info = {
                    "name": tool_name,
                    "resolved": True,
                    "type": type(tool).__name__,
                    "module": getattr(tool, "__module__", "unknown"),
                }
                self.print_status(f"\n✓ Tool '{tool_name}' resolved:", "success")
                for k, v in info.items():
                    self.print_status(f"  {k}: {v}", "info")
                return info
            else:
                self.print_status(f"✗ Tool '{tool_name}' not found", "error")
                return {"name": tool_name, "resolved": False}
                
        except Exception as e:
            self.print_status(f"Error resolving tool: {e}", "error")
            return {}
    
    def action_discover(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Discover tools from installed packages.
        
        Args:
            args: [--include <package>, --entrypoints]
        """
        include_packages = []
        use_entrypoints = "--entrypoints" in args
        
        i = 0
        while i < len(args):
            if args[i] == "--include" and i + 1 < len(args):
                include_packages.append(args[i + 1])
                i += 2
            else:
                i += 1
        
        discovered = {}
        
        # Try praisonai_tools package
        try:
            import praisonai_tools
            pkg_tools = []
            
            # Check for video module
            try:
                from praisonai_tools import video
                pkg_tools.append("praisonai_tools.video")
            except ImportError:
                pass
            
            # Check for tools module
            try:
                import praisonai_tools.tools as ext_tools
                for name in dir(ext_tools):
                    if not name.startswith('_'):
                        obj = getattr(ext_tools, name, None)
                        if callable(obj):
                            pkg_tools.append(name)
            except ImportError:
                pass
            
            if pkg_tools:
                discovered["praisonai_tools"] = pkg_tools
        except ImportError:
            pass
        
        # Try praisonaiagents built-in tools
        try:
            from praisonaiagents.tools import TOOL_MAPPINGS
            discovered["praisonaiagents.tools"] = list(TOOL_MAPPINGS.keys())[:20]  # Limit
        except ImportError:
            pass
        
        # Additional packages from --include
        for pkg in include_packages:
            try:
                import importlib
                mod = importlib.import_module(pkg)
                tools = [n for n in dir(mod) if not n.startswith('_') and callable(getattr(mod, n, None))]
                if tools:
                    discovered[pkg] = tools[:20]
            except ImportError:
                self.print_status(f"Package '{pkg}' not found", "warning")
        
        self.print_status("\n🔍 Discovered Tools:", "info")
        for pkg, tools in discovered.items():
            self.print_status(f"\n  {pkg}:", "info")
            for t in tools[:10]:
                self.print_status(f"    • {t}", "info")
            if len(tools) > 10:
                self.print_status(f"    ... and {len(tools) - 10} more", "info")
        
        return discovered
    
    def action_show_sources(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Show all tool sources for a template.
        
        Args:
            args: [--template <template>]
        """
        template_name = None
        
        i = 0
        while i < len(args):
            if args[i] == "--template" and i + 1 < len(args):
                template_name = args[i + 1]
                i += 2
            else:
                i += 1
        
        from pathlib import Path
        
        # Check if tools.py exists in current directory
        cwd_tools_py = Path.cwd() / "tools.py"
        
        sources = {
            "built_in": "praisonaiagents.tools.TOOL_MAPPINGS",
            "package_discovery": ["praisonai_tools"],
            "default_dirs": [
                "~/.praison/tools",
                "~/.config/praison/tools",
            ],
            "cwd_tools_py": str(cwd_tools_py) if cwd_tools_py.exists() else "(not found: ./tools.py)",
        }
        
        if template_name:
            try:
                from praisonai.templates.loader import TemplateLoader
                loader = TemplateLoader()
                template = loader.load_template(template_name)
                
                if template.requires and isinstance(template.requires, dict):
                    ts = template.requires.get("tools_sources", [])
                    if ts:
                        sources["template_tools_sources"] = ts
                
                if template.path:
                    from pathlib import Path
                    tools_py = Path(template.path) / "tools.py"
                    if tools_py.exists():
                        sources["template_local_tools_py"] = str(tools_py)
                        
            except Exception as e:
                self.print_status(f"Could not load template: {e}", "warning")
        
        self.print_status("\n📦 Tool Sources:", "info")
        for source_type, value in sources.items():
            if isinstance(value, list):
                self.print_status(f"\n  {source_type}:", "info")
                for v in value:
                    self.print_status(f"    • {v}", "info")
            else:
                self.print_status(f"\n  {source_type}: {value}", "info")
        
        return sources
    
    def _get_config_path(self):
        """Get the path to the tools config file."""
        from pathlib import Path
        config_dir = Path.home() / ".praison"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "tools_sources.yaml"
    
    def _load_config(self) -> Dict[str, Any]:
        """Load tools config from file."""
        config_path = self._get_config_path()
        if config_path.exists():
            import yaml
            with open(config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        return {"sources": []}
    
    def _save_config(self, config: Dict[str, Any]):
        """Save tools config to file."""
        import yaml
        config_path = self._get_config_path()
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
    
    def action_add(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Add tools from package, file, or GitHub.
        
        Args:
            args: [source] - package name, file path, or github:user/repo
            
        Examples:
            praisonai tools add pandas
            praisonai tools add ./my_tools.py
            praisonai tools add github:user/repo/tools
        """
        if not args:
            self.print_status("Usage: praisonai tools add <source>", "error")
            self.print_status("  source: package name, file path, or github:user/repo", "info")
            return {"success": False, "error": "No source provided"}
        
        source = args[0]
        result = {"source": source, "success": False, "tools": []}
        
        from pathlib import Path
        
        # Check if it's a local file
        if source.startswith("./") or source.startswith("/") or source.endswith(".py"):
            path = Path(source).resolve()
            if path.exists():
                # Copy to ~/.praison/tools/
                tools_dir = Path.home() / ".praison" / "tools"
                tools_dir.mkdir(parents=True, exist_ok=True)
                dest = tools_dir / path.name
                
                import shutil
                shutil.copy(path, dest)
                
                self.print_status(f"\n✅ Added tools file: {path.name}", "success")
                self.print_status(f"   Copied to: {dest}", "info")
                
                # Discover tools in the file
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("tools_module", dest)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    tools = [n for n in dir(module) if not n.startswith('_') and callable(getattr(module, n, None))]
                    result["tools"] = tools
                    self.print_status(f"   Found {len(tools)} tools: {', '.join(tools[:5])}", "info")
                except Exception as e:
                    self.print_status(f"   Warning: Could not inspect tools: {e}", "warning")
                
                result["success"] = True
                return result
            else:
                self.print_status(f"File not found: {source}", "error")
                return result
        
        # Check if it's a GitHub reference
        elif source.startswith("github:"):
            github_path = source[7:]  # Remove "github:"
            parts = github_path.split("/")
            if len(parts) < 2:
                self.print_status("Invalid GitHub format. Use: github:user/repo/path", "error")
                return result
            
            user, repo = parts[0], parts[1]
            path = "/".join(parts[2:]) if len(parts) > 2 else ""
            
            # Download from GitHub
            import urllib.request
            
            if path:
                raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/main/{path}"
                if not path.endswith(".py"):
                    raw_url += "/tools.py"
            else:
                raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/main/tools.py"
            
            try:
                self.print_status(f"Downloading from: {raw_url}", "info")
                
                tools_dir = Path.home() / ".praison" / "tools"
                tools_dir.mkdir(parents=True, exist_ok=True)
                
                filename = f"{user}_{repo}_{path.replace('/', '_')}.py" if path else f"{user}_{repo}_tools.py"
                dest = tools_dir / filename
                
                urllib.request.urlretrieve(raw_url, dest)
                
                self.print_status(f"\n✅ Added tools from GitHub: {user}/{repo}", "success")
                self.print_status(f"   Saved to: {dest}", "info")
                
                result["success"] = True
                return result
            except Exception as e:
                self.print_status(f"Failed to download from GitHub: {e}", "error")
                return result
        
        # Assume it's a package name - but warn that packages need wrapper tools
        else:
            try:
                import importlib
                module = importlib.import_module(source)
                
                # Get callable functions from the module
                tools = [n for n in dir(module) if not n.startswith('_') and callable(getattr(module, n, None))]
                
                self.print_status(f"\n⚠️  Package '{source}' is installed but NOT directly usable as tools", "warning")
                self.print_status(f"   Found {len(tools)} callable items in package", "info")
                self.print_status("", "info")
                self.print_status("   To use this package with agents, create wrapper tools:", "info")
                self.print_status("   1. Create a file: ~/.praison/tools/my_tools.py", "info")
                self.print_status("   2. Define wrapper functions with docstrings", "info")
                self.print_status("   3. Tools will be auto-discovered", "info")
                self.print_status("", "info")
                self.print_status("   Example wrapper:", "info")
                self.print_status(f"   def my_{source}_tool(data: str) -> str:", "info")
                self.print_status(f'       """Use {source} to process data."""', "info")
                self.print_status(f"       import {source}", "info")
                self.print_status("       # Your logic here", "info")
                self.print_status("       return result", "info")
                
                result["success"] = True
                result["tools"] = tools[:10]
                result["note"] = "Package requires wrapper tools"
                return result
            except ImportError:
                self.print_status(f"Package '{source}' not found. Install with: pip install {source}", "error")
                return result
    
    def action_add_sources(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Add a tool source to persistent config.
        
        Args:
            args: [source] - package name, file path, or github:user/repo
        """
        if not args:
            self.print_status("Usage: praisonai tools add-sources <source>", "error")
            return {"success": False, "error": "No source provided"}
        
        source = args[0]
        config = self._load_config()
        
        if "sources" not in config:
            config["sources"] = []
        
        if source in config["sources"]:
            self.print_status(f"Source '{source}' already in config", "warning")
            return {"success": True, "already_exists": True}
        
        config["sources"].append(source)
        self._save_config(config)
        
        self.print_status(f"\n✅ Added tool source: {source}", "success")
        self.print_status(f"   Config saved to: {self._get_config_path()}", "info")
        
        return {"success": True, "source": source}
    
    def action_remove_sources(self, args: List[str], **kwargs) -> Dict[str, Any]:
        """
        Remove a tool source from persistent config.
        
        Args:
            args: [source] - source to remove
        """
        if not args:
            self.print_status("Usage: praisonai tools remove-sources <source>", "error")
            return {"success": False, "error": "No source provided"}
        
        source = args[0]
        config = self._load_config()
        
        if "sources" not in config or source not in config["sources"]:
            self.print_status(f"Source '{source}' not found in config", "warning")
            return {"success": False, "not_found": True}
        
        config["sources"].remove(source)
        self._save_config(config)
        
        self.print_status(f"\n✅ Removed tool source: {source}", "success")
        
        return {"success": True, "source": source}
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> Any:
        """Execute tools command action."""
        # Handle hyphenated action names
        if action == "show-sources":
            return self.action_show_sources(action_args, **kwargs)
        elif action == "add-sources":
            return self.action_add_sources(action_args, **kwargs)
        elif action == "remove-sources":
            return self.action_remove_sources(action_args, **kwargs)
        return super().execute(action, action_args, **kwargs)
