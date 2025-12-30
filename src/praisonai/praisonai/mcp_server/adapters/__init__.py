"""
MCP Adapters

Adapters that convert PraisonAI capabilities, CLI features, and agent operations
into MCP tools, resources, and prompts.
"""

__all__ = [
    "register_all",
    "register_all_tools",
    "register_capability_tools",
    "register_extended_capability_tools",
    "register_agent_tools",
    "register_memory_tools",
    "register_knowledge_tools",
    "register_cli_tools",
    "register_mcp_resources",
    "register_mcp_prompts",
    "register_praisonai_tools",
    "is_bridge_available",
]


def __getattr__(name):
    """Lazy load adapters."""
    if name == "register_all":
        from .capabilities import register_all_tools
        from .extended_capabilities import register_extended_capability_tools
        from .cli_tools import register_cli_tools
        from .resources import register_mcp_resources
        from .prompts import register_mcp_prompts
        
        def _register_all():
            register_all_tools()
            register_extended_capability_tools()
            register_cli_tools()
            register_mcp_resources()
            register_mcp_prompts()
        
        return _register_all
    elif name == "register_all_tools":
        from .capabilities import register_all_tools
        return register_all_tools
    elif name == "register_capability_tools":
        from .capabilities import register_capability_tools
        return register_capability_tools
    elif name == "register_extended_capability_tools":
        from .extended_capabilities import register_extended_capability_tools
        return register_extended_capability_tools
    elif name == "register_agent_tools":
        from .agents import register_agent_tools
        return register_agent_tools
    elif name == "register_memory_tools":
        from .memory import register_memory_tools
        return register_memory_tools
    elif name == "register_knowledge_tools":
        from .knowledge import register_knowledge_tools
        return register_knowledge_tools
    elif name == "register_cli_tools":
        from .cli_tools import register_cli_tools
        return register_cli_tools
    elif name == "register_mcp_resources":
        from .resources import register_mcp_resources
        return register_mcp_resources
    elif name == "register_mcp_prompts":
        from .prompts import register_mcp_prompts
        return register_mcp_prompts
    elif name == "register_praisonai_tools":
        from .tools_bridge import register_praisonai_tools
        return register_praisonai_tools
    elif name == "is_bridge_available":
        from .tools_bridge import is_bridge_available
        return is_bridge_available
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
