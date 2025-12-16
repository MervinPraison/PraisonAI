"""
MCP Handler for CLI.

Provides Model Context Protocol server integration.
Usage: praisonai "prompt" --mcp "npx -y @modelcontextprotocol/server-filesystem ."
"""

import shlex
from typing import Any, Dict, Tuple, List
from .base import FlagHandler


class MCPHandler(FlagHandler):
    """
    Handler for --mcp flag.
    
    Integrates MCP (Model Context Protocol) servers as tools for agents.
    
    Example:
        praisonai "List files" --mcp "npx -y @modelcontextprotocol/server-filesystem ."
        praisonai "Search web" --mcp "npx -y @modelcontextprotocol/server-brave-search" --mcp-env "BRAVE_API_KEY=xxx"
    """
    
    @property
    def feature_name(self) -> str:
        return "mcp"
    
    @property
    def flag_name(self) -> str:
        return "mcp"
    
    @property
    def flag_help(self) -> str:
        return "MCP server command (e.g., 'npx -y @modelcontextprotocol/server-filesystem .')"
    
    def check_dependencies(self) -> Tuple[bool, str]:
        """Check if MCP is available."""
        try:
            import importlib.util
            if importlib.util.find_spec("praisonaiagents") is not None:
                # Check if MCP module is available
                from praisonaiagents import MCP
                if MCP is not None:
                    return True, ""
            return False, "MCP requires praisonaiagents with MCP support"
        except ImportError:
            return False, "praisonaiagents not installed. Install with: pip install praisonaiagents"
    
    def parse_mcp_command(self, command: str, env_vars: str = None) -> Tuple[str, List[str], Dict[str, str]]:
        """
        Parse MCP command string into command, args, and environment.
        
        Args:
            command: Full MCP command string
            env_vars: Optional comma-separated environment variables (KEY=value,KEY2=value2)
            
        Returns:
            Tuple of (command, args, env_dict)
        """
        # Parse command using shell-like splitting
        parts = shlex.split(command)
        if not parts:
            return "", [], {}
        
        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        # Parse environment variables
        env = {}
        if env_vars:
            for pair in env_vars.split(','):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    env[key.strip()] = value.strip()
        
        return cmd, args, env
    
    def create_mcp_tools(self, command: str, env_vars: str = None, timeout: int = 30) -> Any:
        """
        Create MCP tools from command.
        
        Args:
            command: MCP server command
            env_vars: Optional environment variables
            timeout: Connection timeout in seconds
            
        Returns:
            MCP instance or None if unavailable
        """
        available, msg = self.check_dependencies()
        if not available:
            self.print_status(msg, "error")
            return None
        
        from praisonaiagents import MCP
        
        cmd, args, env = self.parse_mcp_command(command, env_vars)
        
        if not cmd:
            self.print_status("Invalid MCP command", "error")
            return None
        
        try:
            mcp = MCP(
                command=cmd,
                args=args,
                env=env if env else None,
                timeout=timeout
            )
            self.print_status(f"🔌 MCP server connected: {cmd}", "success")
            return mcp
        except Exception as e:
            self.print_status(f"Failed to connect to MCP server: {e}", "error")
            return None
    
    def apply_to_agent_config(self, config: Dict[str, Any], flag_value: Any) -> Dict[str, Any]:
        """
        Apply MCP configuration to agent config.
        
        Args:
            config: Agent configuration dictionary
            flag_value: MCP command string or dict with command and env
            
        Returns:
            Modified configuration with MCP tools
        """
        if not flag_value:
            return config
        
        # Handle both string and dict formats
        if isinstance(flag_value, str):
            mcp = self.create_mcp_tools(flag_value)
        elif isinstance(flag_value, dict):
            mcp = self.create_mcp_tools(
                flag_value.get('command', ''),
                flag_value.get('env', ''),
                flag_value.get('timeout', 30)
            )
        else:
            return config
        
        if mcp:
            # Add MCP tools to existing tools
            existing_tools = config.get('tools', [])
            if isinstance(existing_tools, list):
                existing_tools.extend(list(mcp))
            else:
                existing_tools = list(mcp)
            config['tools'] = existing_tools
            config['_mcp_instance'] = mcp  # Store for cleanup
        
        return config
    
    def execute(self, command: str = None, env_vars: str = None, **kwargs) -> Any:
        """
        Execute MCP setup.
        
        Args:
            command: MCP server command
            env_vars: Environment variables
            
        Returns:
            MCP instance or None
        """
        if not command:
            self.print_status("No MCP command provided", "error")
            return None
        
        return self.create_mcp_tools(command, env_vars)
