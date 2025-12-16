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
        return ["list", "info", "search", "help"]
    
    def get_help_text(self) -> str:
        return """
Tools Commands:
  praisonai tools list                   - List all available tools
  praisonai tools info <name>            - Show tool details
  praisonai tools search <query>         - Search tools by name/description

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
    
    def execute(self, action: str, action_args: List[str], **kwargs) -> Any:
        """Execute tools command action."""
        return super().execute(action, action_args, **kwargs)
