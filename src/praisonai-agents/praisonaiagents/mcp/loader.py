"""
MCP Tools Loader for PraisonAI Agents.

Provides a thin helper function to load MCP tools for agents
following the agent-centric design principles in AGENTS.md.
"""

from typing import List, Optional

from ..memory.mcp_config import MCPConfig, MCPConfigManager
from .mcp import MCP


def _sanitize_server_name(name: str) -> str:
    """Sanitize a server name for use as a stable, deterministic tool prefix."""
    import re
    return re.sub(r"[^0-9A-Za-z_]", "_", name or "").strip("_")


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
            are loaded to avoid collisions (default: True). When more than
            one server is loaded, each server's tools are namespaced as
            ``<server_name>_<tool_name>`` (e.g. ``filesystem_read_file``).
            Single-server loads keep bare tool names for backward
            compatibility.

    Raises:
        ValueError: If two loaded configs share the same (sanitized) server
            name, which would produce ambiguous namespaced tool names.
    
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
    
    enabled_configs = [c for c in target_configs if c and c.enabled]

    # Detect residual collisions: two servers whose sanitized names are
    # identical would produce ambiguous namespaced tool names. Fail loudly
    # instead of silently shadowing (the very bug this loader guards against).
    if prefix_tools and len(enabled_configs) > 1:
        seen: dict = {}
        for config in enabled_configs:
            sanitized = _sanitize_server_name(config.name)
            if sanitized in seen and seen[sanitized] != config.name:
                raise ValueError(
                    f"MCP server name collision: '{config.name}' and "
                    f"'{seen[sanitized]}' both map to prefix '{sanitized}'. "
                    "Use distinct server names to keep tool namespacing unambiguous."
                )
            seen[sanitized] = config.name

    multiple_servers = len(enabled_configs) > 1

    for config in enabled_configs:
        # Convert config to MCP instance
        mcp = config.to_mcp_instance()
        if mcp:
            # Apply include/exclude tool filtering if configured (B3).
            # Filters may be declared on the config (forward-compatible via
            # getattr so older MCPConfig objects without these fields work).
            allowed = getattr(config, "allowed_tools", None) or getattr(config, "include_tools", None)
            disabled = getattr(config, "disabled_tools", None) or getattr(config, "exclude_tools", None)
            if allowed or disabled:
                mcp.allowed_tools = allowed
                mcp.disabled_tools = disabled
                mcp._tools = mcp._apply_tool_filters(mcp._tools)

            # Apply tool prefix if multiple servers (B4) to avoid collisions.
            if prefix_tools and multiple_servers:
                mcp.with_tool_prefix(config.name)

            mcp_clients.append(mcp)

    return mcp_clients