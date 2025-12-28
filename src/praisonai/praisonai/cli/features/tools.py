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
        return ["list", "info", "search", "doctor", "resolve", "discover", "show-sources", "help"]
    
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
        
        sources = {
            "built_in": "praisonaiagents.tools.TOOL_MAPPINGS",
            "package_discovery": ["praisonai_tools"],
            "default_dirs": [
                "~/.praison/tools",
                "~/.config/praison/tools",
            ],
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
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> Any:
        """Execute tools command action."""
        # Handle hyphenated action names
        if action == "show-sources":
            return self.action_show_sources(action_args, **kwargs)
        return super().execute(action, action_args, **kwargs)
