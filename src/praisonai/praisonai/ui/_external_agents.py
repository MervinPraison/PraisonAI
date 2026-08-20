"""Shared helpers for wiring external agents into any UI entry point.

Single source of truth for:
- Listing installed external agents (lazy, cached)
- Rendering aiui settings entries
- Building the tools list from enabled agents
"""

from collections.abc import Mapping
from typing import Any, Dict, Iterator, List


class _RegistryAgents(Mapping):
    """Live map of UI toggle id -> integration metadata, from the registry.

    Was a hand-written copy of the four built-in names, so an agent published
    under the "praisonai.external_agents" entry-point group never reached the
    UI. Kept as a Mapping so existing `in` / iteration / `[]` usage is unchanged.
    """

    @staticmethod
    def _catalog() -> Dict[str, Dict[str, Any]]:
        from praisonai.integrations.registry import external_agent_catalog
        return {f"{name}_enabled": meta
                for name, meta in external_agent_catalog().items()}

    def __getitem__(self, key: str) -> Dict[str, Any]:
        return self._catalog()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._catalog())

    def __len__(self) -> int:
        return len(self._catalog())


EXTERNAL_AGENTS: Mapping = _RegistryAgents()


def installed_external_agents() -> List[str]:
    """Return toggle ids of external agents whose CLI is on PATH."""
    import shutil
    return [toggle_id for toggle_id, meta in EXTERNAL_AGENTS.items()
            if shutil.which(meta["cli"])]


def external_agent_tools(settings: Dict[str, Any], workspace: str = ".") -> list:
    """Build tools list from settings dict of toggle_id → bool."""
    tools = []
    for toggle_id, enabled in settings.items():
        if not enabled or toggle_id not in EXTERNAL_AGENTS:
            continue
        meta = EXTERNAL_AGENTS[toggle_id]
        try:
            integration = meta["cls"](workspace=workspace)
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
