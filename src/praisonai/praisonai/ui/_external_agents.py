"""Shared helpers for wiring external agents into any UI entry point.

Single source of truth for:
- Listing installed external agents (lazy, cached)
- Rendering aiui settings entries
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
            continue  # Integration module/class not available
        except Exception as e:  # noqa: BLE001 — isolate faulty integrations
            import logging
            logging.getLogger(__name__).warning(
                "Skipping external agent %s due to error: %s", toggle_id, e
            )
            continue
    return tools


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
