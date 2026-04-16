"""Shared helpers for wiring external agents into any UI entry point.

Single source of truth for:
- Listing installed external agents (lazy, cached)
- Rendering Chainlit Switch widgets / aiui settings entries
- Building the tools list from enabled agents
"""

from functools import lru_cache
from typing import Any, Dict, List

# Map of UI toggle id → (integration class path, pretty label)
EXTERNAL_AGENTS: Dict[str, Dict[str, str]] = {
    "claude_enabled": {"module": "claude_code", "cls": "ClaudeCodeIntegration",
                       "label": "Claude Code (coding, file edits)", "cli": "claude"},
    "gemini_enabled": {"module": "gemini_cli", "cls": "GeminiCLIIntegration",
                       "label": "Gemini CLI (analysis, search)", "cli": "gemini"},
    "codex_enabled":  {"module": "codex_cli",  "cls": "CodexCLIIntegration",
                       "label": "Codex CLI (refactoring)",       "cli": "codex"},
    "cursor_enabled": {"module": "cursor_cli", "cls": "CursorCLIIntegration",
                       "label": "Cursor CLI (IDE tasks)",        "cli": "cursor-agent"},
}


@lru_cache(maxsize=1)
def installed_external_agents() -> List[str]:
    """Return toggle ids of external agents whose CLI is on PATH."""
    import shutil
    return [toggle_id for toggle_id, meta in EXTERNAL_AGENTS.items()
            if shutil.which(meta["cli"])]


def external_agent_tools(settings: Dict[str, Any], workspace: str = ".") -> list:
    """Build tools list from settings dict of toggle_id → bool."""
    import importlib
    tools = []
    for toggle_id, enabled in settings.items():
        if not enabled or toggle_id not in EXTERNAL_AGENTS:
            continue
        meta = EXTERNAL_AGENTS[toggle_id]
        try:
            mod = importlib.import_module(f"praisonai.integrations.{meta['module']}")
            integration = getattr(mod, meta["cls"])(workspace=workspace)
            if integration.is_available:
                tools.append(integration.as_tool())
        except (ImportError, AttributeError):
            # Integration module not available, skip
            continue
    return tools


def chainlit_switches(current_settings: Dict[str, bool]):
    """Return Chainlit Switch widgets for installed external agents only."""
    from chainlit.input_widget import Switch
    return [
        Switch(id=toggle_id, label=EXTERNAL_AGENTS[toggle_id]["label"],
               initial=current_settings.get(toggle_id, False))
        for toggle_id in installed_external_agents()
    ]


def aiui_settings_entries() -> Dict[str, Any]:
    """Return aiui settings entries for installed external agents."""
    settings = {}
    for toggle_id in installed_external_agents():
        meta = EXTERNAL_AGENTS[toggle_id]
        settings[toggle_id] = {
            "type": "checkbox",
            "label": meta["label"],
            "default": False
        }
    return settings


def load_external_agent_settings_from_chainlit() -> Dict[str, bool]:
    """Load external agent settings from Chainlit session and persistent storage."""
    import chainlit as cl
    settings = {}
    
    # Try to load from persistent storage (if load_setting is available)
    try:
        # Import load_setting from the UI module where it's defined
        from praisonai.ui.chat import load_setting
        
        # Check for legacy key first
        legacy_claude = load_setting("claude_code_enabled")
        if legacy_claude and legacy_claude.lower() == "true":
            settings["claude_enabled"] = True
        
        # Load all current toggles from persistent storage
        for toggle_id in EXTERNAL_AGENTS:
            persistent_value = load_setting(toggle_id)
            if persistent_value is not None:
                settings[toggle_id] = persistent_value.lower() == "true"
            else:
                settings[toggle_id] = settings.get(toggle_id, False)
    except ImportError:
        # Fallback to session-only storage
        pass
    
    # Load from session (may override persistent settings)
    # Check for legacy key in session
    legacy_claude_session = cl.user_session.get("claude_code_enabled", False)
    if legacy_claude_session:
        settings["claude_enabled"] = True
    
    # Load all current toggles from session
    for toggle_id in EXTERNAL_AGENTS:
        session_value = cl.user_session.get(toggle_id)
        if session_value is not None:
            settings[toggle_id] = session_value
    
    return settings


def save_external_agent_settings_to_chainlit(settings: Dict[str, bool]):
    """Save external agent settings to Chainlit session."""
    import chainlit as cl
    for toggle_id, enabled in settings.items():
        cl.user_session.set(toggle_id, enabled)