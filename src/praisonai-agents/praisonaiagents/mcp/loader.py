"""
MCP Tools Loader for PraisonAI Agents.

Provides a thin helper function to load MCP tools for agents
following the agent-centric design principles in AGENTS.md.
"""

from typing import List, Optional

from ..memory.mcp_config import MCPConfig, MCPConfigManager
from .mcp import MCP


def load_mcp_tools(
    names: Optional[List[str]] = None,
    *,
    configs: Optional[List[MCPConfig]] = None,
    prefix_tools: bool = True,
) -> List[MCP]:
    """
    Load MCP tools for use with agents.
    
    This is a thin helper that bridges the gap between configuration
    and agent tool setup, following the "few lines to run an agent"
    principle from AGENTS.md.
    
    Args:
        names: Specific config names to load (None = all enabled)
        configs: Optional injected configs from wrapper TOML loader
        prefix_tools: Whether to prefix tool names when multiple servers
            are loaded to avoid collisions (default: True).
            NOTE: Currently not implemented - collisions possible with multiple servers.
    
    Returns:
        List of MCP client instances ready for agent use
    
    Examples:
        # Load all enabled MCP servers from JSON config
        >>> from praisonaiagents import Agent
        >>> from praisonaiagents.mcp import load_mcp_tools
        >>> agent = Agent(name="assistant", tools=load_mcp_tools())
        
        # Load specific servers only
        >>> tools = load_mcp_tools(["filesystem", "github"])
        >>> agent = Agent(name="coder", tools=tools)
        
        # Inject configs from wrapper TOML
        >>> from praisonai.cli.configuration import get_config_loader
        >>> loader = get_config_loader()
        >>> config = loader.load()
        >>> toml_configs = [MCPConfig(...) for server in config.mcp.servers]
        >>> tools = load_mcp_tools(configs=toml_configs)
    """
    mcp_clients: List[MCP] = []
    
    if configs is not None:
        # Use injected configs from wrapper (TOML loading)
        target_configs = configs
        if names:
            # Filter by names if specified
            target_configs = [c for c in configs if c.name in names]
    else:
        # Load from MCPConfigManager (JSON files)
        manager = MCPConfigManager()
        if names:
            target_configs = [manager.get_config(name) for name in names]
            target_configs = [c for c in target_configs if c and c.enabled]
        else:
            target_configs = manager.get_enabled_configs()
    
    for config in target_configs:
        if not config.enabled:
            continue
            
        # Convert config to MCP instance
        mcp = config.to_mcp_instance()
        if mcp:
            # Apply tool filtering if configured (B3)
            # TODO: Wire include/exclude filters when B3 is implemented
            
            # Apply tool prefix if multiple servers (B4)
            if prefix_tools and len(target_configs) > 1:
                # Sanitize server name for use as prefix
                server_name = config.name.replace('-', '_').replace(' ', '_')
                # TODO: Tool name prefixing not yet implemented
                # Need to modify tool names in MCP instance to avoid collisions
                # e.g., "read_file" -> "filesystem_read_file"
                pass
            
            mcp_clients.append(mcp)
    
    return mcp_clients