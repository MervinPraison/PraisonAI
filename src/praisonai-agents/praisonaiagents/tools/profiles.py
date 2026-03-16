"""
ToolProfile system for composable, extensible tool sets.

Provides named profiles of tools that can be combined and extended.
This eliminates DRY violations across interactive/autonomy modes.

Usage:
    from praisonaiagents.tools.profiles import resolve_profiles, AUTONOMY_PROFILE
    
    # Get tools for autonomy mode
    tools = resolve_profiles("autonomy")
    
    # Combine multiple profiles
    tools = resolve_profiles("file_ops", "web", "shell")
    
    # Register custom profile (wrapper/plugins)
    from praisonaiagents.tools.profiles import register_profile, ToolProfile
    register_profile(ToolProfile(name="custom", tools=["my_tool"]))
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ToolProfile:
    """Named, extensible collection of tool names.
    
    Attributes:
        name: Profile identifier (e.g., "file_ops", "shell", "autonomy")
        tools: List of tool name strings (resolved via TOOL_MAPPINGS)
        description: Human-readable description of the profile
    
    Example:
        profile = ToolProfile(
            name="file_ops",
            tools=["read_file", "write_file", "list_files"],
            description="File system operations"
        )
    """
    name: str
    tools: List[str] = field(default_factory=list)
    description: str = ""


# Built-in profiles (SDK ships with these)
BUILTIN_PROFILES: Dict[str, ToolProfile] = {
    "code_intelligence": ToolProfile(
        name="code_intelligence",
        tools=["ast_grep_search", "ast_grep_rewrite", "ast_grep_scan"],
        description="Structural code search and rewrite using ast-grep",
    ),
    "file_ops": ToolProfile(
        name="file_ops",
        tools=[
            "read_file", "write_file", "list_files",
            "copy_file", "move_file", "delete_file", "get_file_info"
        ],
        description="File system operations",
    ),
    "shell": ToolProfile(
        name="shell",
        tools=["execute_command", "list_processes", "get_system_info"],
        description="Shell and system tools",
    ),
    "web": ToolProfile(
        name="web",
        tools=["internet_search", "search_web", "web_crawl"],
        description="Web search and crawling",
    ),
    "code_exec": ToolProfile(
        name="code_exec",
        tools=["execute_code", "analyze_code", "format_code", "lint_code"],
        description="Python code execution and analysis",
    ),
    "schedule": ToolProfile(
        name="schedule",
        tools=["schedule_add", "schedule_list", "schedule_remove"],
        description="Agent-centric scheduling",
    ),
    "memory": ToolProfile(
        name="memory",
        tools=["store_memory", "search_memory"],
        description="Active memory store/search (requires memory=True on Agent)",
    ),
    "learning": ToolProfile(
        name="learning",
        tools=["store_learning", "search_learning"],
        description="Categorized knowledge store/search (requires learn=True on Agent)",
    ),
    "email": ToolProfile(
        name="email",
        tools=["send_email", "list_emails", "read_email"],
        description="Email send/read via AgentMail API (requires AGENTMAIL_API_KEY)",
    ),
    "smtp_email": ToolProfile(
        name="smtp_email",
        tools=["smtp_send_email", "smtp_read_inbox"],
        description="Email send/read via SMTP/IMAP with mailbox credentials (requires EMAIL_ADDRESS, EMAIL_PASSWORD)",
    ),
}


def _build_autonomy_tools() -> List[str]:
    """Build the autonomy profile tools list (deduped)."""
    tools = []
    for profile_name in ["code_intelligence", "file_ops", "shell", "web", "memory", "learning", "schedule"]:
        profile = BUILTIN_PROFILES[profile_name]
        for tool in profile.tools:
            if tool not in tools:
                tools.append(tool)
    return tools


# Composite autonomy profile - combines multiple profiles
AUTONOMY_PROFILE = ToolProfile(
    name="autonomy",
    tools=_build_autonomy_tools(),
    description="Default tools for autonomous agents (code_intelligence + file_ops + shell + web + memory + learning + schedule)",
)


# Extension registry for custom profiles (wrapper/plugins use this)
_custom_profiles: Dict[str, ToolProfile] = {}


def register_profile(profile: ToolProfile) -> None:
    """Register a custom tool profile.
    
    Custom profiles override built-in profiles with the same name.
    This allows the wrapper to extend or replace SDK profiles.
    
    Args:
        profile: ToolProfile to register
        
    Example:
        # Wrapper registers ACP/LSP tools
        register_profile(ToolProfile(
            name="acp",
            tools=["acp_create_file", "acp_edit_file"],
        ))
    """
    _custom_profiles[profile.name] = profile


def get_profile(name: str) -> ToolProfile:
    """Get a tool profile by name.
    
    Custom profiles take precedence over built-in profiles.
    
    Args:
        name: Profile name
        
    Returns:
        ToolProfile instance
        
    Raises:
        KeyError: If profile not found
    """
    if name in _custom_profiles:
        return _custom_profiles[name]
    if name in BUILTIN_PROFILES:
        return BUILTIN_PROFILES[name]
    if name == "autonomy":
        return AUTONOMY_PROFILE
    raise KeyError(f"Unknown tool profile: {name}")


def resolve_profiles(*names: str) -> List[str]:
    """Resolve multiple profile names to a flat tool list.
    
    Tools are deduplicated - each tool appears only once.
    
    Args:
        *names: Profile names to resolve
        
    Returns:
        List of tool name strings (deduped)
        
    Raises:
        KeyError: If any profile not found
        
    Example:
        # Get tools for autonomy + custom ACP
        tools = resolve_profiles("autonomy", "acp")
    """
    tools: List[str] = []
    for name in names:
        profile = get_profile(name)
        for tool in profile.tools:
            if tool not in tools:
                tools.append(tool)
    return tools


def list_profiles() -> List[str]:
    """List all available profile names.
    
    Returns:
        List of profile names (built-in + custom + autonomy)
    """
    names = set(BUILTIN_PROFILES.keys())
    names.update(_custom_profiles.keys())
    names.add("autonomy")
    return sorted(names)
