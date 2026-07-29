"""Monorepo bootstrap for the extracted ``praisonai_*`` sibling packages.

When developing from the PraisonAI source tree with the historical
``PYTHONPATH=src/praisonai-agents:src/praisonai`` layout (no separate
sibling entries), make optional siblings such as ``praisonai_code`` importable
from their ``src/praisonai-*`` directories. Installed wheels/sdists are
unchanged — this only runs when the import would otherwise fail.
"""

from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

_SIBLING_LOCK = threading.Lock()

# module name -> sibling directory (relative to src/)
_SIBLINGS: dict[str, str] = {
    "praisonai_code": "praisonai-code",
    "praisonai_bot": "praisonai-bot",
    "praisonai_train": "praisonai-train",
    "praisonai_browser": "praisonai-browser",
    "praisonai_mcp": "praisonai-mcp",
    "praisonai_sandbox": "praisonai-sandbox",
}


def _ensure_sibling(module_name: str) -> None:
    """Make an optional monorepo sibling importable — single source of truth."""
    try:
        if importlib.util.find_spec(module_name) is not None:
            return
    except (ImportError, ValueError):
        # A discoverable-but-broken parent/package can make find_spec raise
        # (e.g. its __init__ errors during spec resolution). Fall through to
        # the monorepo checkout so a working sibling source can shadow it.
        pass

    dir_name = _SIBLINGS.get(module_name)
    if dir_name is None:
        return

    wrapper_src = Path(__file__).resolve().parents[1]  # .../src/praisonai
    sibling_root = wrapper_src.parent / dir_name
    if not (sibling_root / module_name).is_dir():
        return

    root = str(sibling_root)
    # Thread-safe insertion so concurrent first-imports don't double-insert.
    with _SIBLING_LOCK:
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_code() -> None:
    """Ensure ``praisonai_code`` can be imported in monorepo dev layouts."""
    _ensure_sibling("praisonai_code")


def ensure_praisonai_bot() -> None:
    """Ensure ``praisonai_bot`` can be imported in monorepo dev layouts."""
    _ensure_sibling("praisonai_bot")


def ensure_praisonai_train() -> None:
    """Ensure ``praisonai_train`` can be imported in monorepo dev layouts."""
    _ensure_sibling("praisonai_train")


def ensure_praisonai_browser() -> None:
    """Ensure ``praisonai_browser`` can be imported in monorepo dev layouts."""
    _ensure_sibling("praisonai_browser")


def ensure_praisonai_mcp() -> None:
    """Ensure ``praisonai_mcp`` can be imported in monorepo dev layouts."""
    _ensure_sibling("praisonai_mcp")


def ensure_praisonai_sandbox() -> None:
    """Ensure ``praisonai_sandbox`` can be imported in monorepo dev layouts."""
    _ensure_sibling("praisonai_sandbox")
