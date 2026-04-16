"""
Unified tool alias mapping for managed agents.

Consolidates the tool mapping logic that was previously split between
managed_agents.TOOL_MAPPING and managed_local.TOOL_ALIAS_MAP.
"""

from typing import List


# Canonical tool alias mapping for all managed agent backends
UNIFIED_TOOL_MAPPING = {
    "bash": "execute_command",
    "read": "read_file", 
    "write": "write_file",
    "edit": "apply_diff",  # Use apply_diff for structured edits
    "glob": "list_files",
    "grep": "search_file",  # Use search_file for content search
    "web_fetch": "web_fetch",  # Keep as web_fetch for consistency
    "web_crawl": "web_fetch",  # Alias for web_crawl
    "search": "search_web",
    "web_search": "search_web",
}


def map_managed_tools(managed_tools: List[str]) -> List[str]:
    """Map managed agent tool names to PraisonAI tool names.
    
    Uses unified mapping that resolves conflicts between Anthropic and Local backends:
    - edit → apply_diff (structured diff edits preferred)
    - grep → search_file (file content search preferred over shell command)
    - web_fetch → web_fetch (canonical name)
    
    Args:
        managed_tools: List of tool names from managed agent configuration
        
    Returns:
        List of PraisonAI tool names
    """
    return [UNIFIED_TOOL_MAPPING.get(tool, tool) for tool in managed_tools]


def get_tool_alias(tool_name: str) -> str:
    """Get the canonical PraisonAI tool name for a managed tool.
    
    Args:
        tool_name: Original tool name (e.g. 'bash', 'grep')
        
    Returns:
        Canonical PraisonAI tool name (e.g. 'execute_command', 'search_file')
    """
    return UNIFIED_TOOL_MAPPING.get(tool_name, tool_name)