"""Lazy access from praisonai-mcp to optional praisonai-code modules."""

from __future__ import annotations

import importlib
from typing import Any

from praisonai_mcp._bootstrap import ensure_praisonai_code


def code_available() -> bool:
    ensure_praisonai_code()
    try:
        import praisonai_code  # noqa: F401
        return True
    except ImportError:
        return False


def import_code_module(name: str) -> Any:
    ensure_praisonai_code()
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ImportError(
            f"Optional code module {name!r} requires praisonai-code. "
            "Install with: pip install praisonai-code"
        ) from exc
