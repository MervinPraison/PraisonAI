"""
TUI Configuration for PraisonAI.

Handles keyboard shortcuts and display settings with safe defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TUIConfig:
    """
    Configuration for TUI behavior.
    
    Safe defaults:
    - Ctrl keys disabled by default (conflict with IDEs/terminals)
    - Function keys disabled by default (conflict with IDEs/OS)
    - Single-character shortcuts enabled by default
    - Command mode (:) enabled by default
    """
    
    # Keyboard configuration
    enable_ctrl_keys: bool = False  # Ctrl+Q, Ctrl+L, etc.
    enable_fn_keys: bool = False    # F1-F12
    enable_single_char: bool = True # q, l, etc. (when not in input)
    enable_command_mode: bool = True # :quit, :clear, etc.
    leader_key: str = ":"           # Command mode prefix
    
    # Display configuration
    auto_scroll: bool = True
    show_tools_panel: bool = True
    show_queue_panel: bool = True
    
    @classmethod
    def from_env(cls) -> "TUIConfig":
        """Create config from environment variables."""
        config = cls()
        
        # Check env vars for enabling Ctrl keys (opt-in)
        if os.environ.get("PRAISONAI_TUI_CTRL_KEYS", "").lower() in ("1", "true", "yes"):
            config.enable_ctrl_keys = True
        
        # Check env vars for enabling Function keys (opt-in)
        if os.environ.get("PRAISONAI_TUI_FN_KEYS", "").lower() in ("1", "true", "yes"):
            config.enable_fn_keys = True
        
        # Check for disabling single-char shortcuts
        if os.environ.get("PRAISONAI_TUI_NO_SINGLE_CHAR", "").lower() in ("1", "true", "yes"):
            config.enable_single_char = False
        
        # Check for custom leader key
        leader = os.environ.get("PRAISONAI_TUI_LEADER", "")
        if leader and len(leader) == 1:
            config.leader_key = leader
        
        return config
    
    @classmethod
    def from_cli_args(
        cls,
        enable_ctrl_keys: bool = False,
        enable_fn_keys: bool = False,
        leader_key: Optional[str] = None,
    ) -> "TUIConfig":
        """Create config from CLI arguments, merged with env."""
        config = cls.from_env()
        
        # CLI args override env
        if enable_ctrl_keys:
            config.enable_ctrl_keys = True
        if enable_fn_keys:
            config.enable_fn_keys = True
        if leader_key and len(leader_key) == 1:
            config.leader_key = leader_key
        
        return config


# Command mode commands
COMMANDS = {
    "quit": {"aliases": ["q", "exit"], "description": "Quit the TUI"},
    "clear": {"aliases": ["cl"], "description": "Clear the chat history"},
    "help": {"aliases": ["h", "?"], "description": "Show help"},
    "tools": {"aliases": ["t"], "description": "Toggle tools panel"},
    "queue": {"aliases": ["qu"], "description": "Toggle queue panel"},
    "settings": {"aliases": ["set"], "description": "Open settings"},
    "cancel": {"aliases": ["c"], "description": "Cancel current operation"},
    "sessions": {"aliases": ["sess"], "description": "Manage sessions"},
}


def get_command(input_str: str) -> Optional[str]:
    """
    Parse command input and return the canonical command name.
    
    Args:
        input_str: The command string (without leader key)
        
    Returns:
        Canonical command name or None if not found
    """
    input_str = input_str.strip().lower()
    
    # Check direct match
    if input_str in COMMANDS:
        return input_str
    
    # Check aliases
    for cmd, info in COMMANDS.items():
        if input_str in info.get("aliases", []):
            return cmd
    
    return None


def get_help_text() -> str:
    """Get formatted help text for all commands."""
    lines = [
        "PraisonAI TUI Commands",
        "=" * 40,
        "",
        "Command Mode (press : to enter):",
    ]
    
    for cmd, info in COMMANDS.items():
        aliases = ", ".join(info.get("aliases", []))
        desc = info.get("description", "")
        if aliases:
            lines.append(f"  :{cmd} (or :{aliases}) - {desc}")
        else:
            lines.append(f"  :{cmd} - {desc}")
    
    lines.extend([
        "",
        "Single-key shortcuts (when not typing):",
        "  q - Quit",
        "  l - Clear screen",
        "  ? - Help",
        "  / - Search/filter",
        "",
        "Input shortcuts:",
        "  Enter - Send message",
        "  Shift+Enter - New line",
        "  Escape - Cancel",
        "  Up/Down - History navigation",
    ])
    
    return "\n".join(lines)
