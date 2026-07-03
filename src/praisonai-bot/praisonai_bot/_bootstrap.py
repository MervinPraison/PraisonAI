"""Monorepo bootstrap for ``praisonai_bot`` and optional ``praisonai_code``."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_praisonai_bot() -> None:
    """Ensure ``praisonai_bot`` is importable in monorepo dev layouts."""
    try:
        import praisonai_bot  # noqa: F401
        return
    except ImportError:
        pass

    here = Path(__file__).resolve().parents[1]  # .../src/praisonai-bot
    if (here / "praisonai_bot").is_dir():
        root = str(here)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_code() -> None:
    """Optional code-tier imports (tool resolver, llm env) when co-installed."""
    try:
        import praisonai_code  # noqa: F401
        return
    except ImportError:
        pass

    bot_src = Path(__file__).resolve().parents[1]
    code_src = bot_src.parent / "praisonai-code"
    if (code_src / "praisonai_code").is_dir():
        root = str(code_src)
        if root not in sys.path:
            sys.path.insert(0, root)
