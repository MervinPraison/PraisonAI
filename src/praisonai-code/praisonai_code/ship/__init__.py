"""``praisonai ship`` / ``praisonai steward``: commit, open a draft PR, watch it. Never merge."""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def is_ship_disabled(config: Any = None) -> Optional[str]:
    """Return a human-readable reason if ship/steward is disabled, or ``None`` if enabled.

    Precedence: ``PRAISONAI_DISABLE_SHIP`` environment variable overrides config
    (``[ship] enabled = false``). Missing or unreadable config defaults to enabled.
    """
    raw = os.environ.get("PRAISONAI_DISABLE_SHIP", "").strip().lower()
    if raw in _TRUTHY:
        return "ship is disabled by PRAISONAI_DISABLE_SHIP"
    if raw in _FALSY:
        return None
    if config is None:
        try:
            from praisonai_code.cli.configuration.loader import ConfigLoader

            config = ConfigLoader().load()
        except Exception as exc:
            logger.debug("Could not load config for ship off-switch; defaulting to enabled: %s", exc)
            return None
    ship_cfg = config.get("ship") if isinstance(config, dict) else getattr(config, "ship", None)
    enabled = ship_cfg.get("enabled", True) if isinstance(ship_cfg, dict) else getattr(ship_cfg, "enabled", True)
    if enabled is False:
        return "ship is disabled in configuration (ship.enabled = false)"
    return None


def __getattr__(name: str):
    if name in ("ship", "ShipResult"):
        from praisonai_code.ship import orchestrate
        return getattr(orchestrate, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
