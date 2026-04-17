"""Shared helpers for wiring external agents into any UI entry point.

Single source of truth for:
- Listing installed external agents (lazy, cached)
- Rendering Chainlit Switch widgets / aiui settings entries
- Building the tools list from enabled agents
"""

from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional

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
            continue  # Integration module/class not available
        except Exception as e:  # noqa: BLE001 — isolate faulty integrations
            import logging
            logging.getLogger(__name__).warning(
                "Skipping external agent %s due to error: %s", toggle_id, e
            )
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


def _parse_setting_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def load_external_agent_settings_from_chainlit(
    load_setting_fn: Optional[Callable[[str], Any]] = None,
) -> Dict[str, bool]:
    """Load external agent settings from Chainlit session and persistent storage.

    Args:
        load_setting_fn: Optional callback used to load persisted settings by key.
            If omitted, falls back to importing ``praisonai.ui.chat.load_setting``
            for backward compatibility.
    """
    import chainlit as cl
    settings = {toggle_id: False for toggle_id in EXTERNAL_AGENTS}
    loader = load_setting_fn
    
    # Try to load from persistent storage (if load_setting is available)
    if loader is None:
        try:
            # Backward-compatible fallback for callers that don't pass a loader
            from praisonai.ui.chat import load_setting as loader  # type: ignore
        except ImportError:
            loader = None
    
    if loader is not None:
        legacy_claude = _parse_setting_bool(loader("claude_code_enabled"))
        
        # Load all current toggles from persistent storage first
        for toggle_id in EXTERNAL_AGENTS:
            persistent_value = loader(toggle_id)
            if persistent_value:  # non-empty string means explicitly stored
                settings[toggle_id] = _parse_setting_bool(persistent_value)
        
        # Apply legacy migration only where no explicit value was stored
        if legacy_claude and not loader("claude_enabled"):
            settings["claude_enabled"] = True
    
    # Load from session (may override persistent settings)
    # Check for legacy key in session
    if _parse_setting_bool(cl.user_session.get("claude_code_enabled", False)):
        settings["claude_enabled"] = True
    
    # Load all current toggles from session
    for toggle_id in EXTERNAL_AGENTS:
        session_value = cl.user_session.get(toggle_id)
        if session_value is not None:
            settings[toggle_id] = _parse_setting_bool(session_value)
    
    return settings


def save_external_agent_settings_to_chainlit(settings: Dict[str, bool]):
    """Save external agent settings to Chainlit session."""
    import chainlit as cl
    for toggle_id, enabled in settings.items():
        cl.user_session.set(toggle_id, enabled)
