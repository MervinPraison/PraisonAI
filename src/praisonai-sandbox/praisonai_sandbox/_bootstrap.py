"""Monorepo bootstrap for ``praisonai_sandbox`` and optional ``praisonai_code``."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_praisonai_sandbox() -> None:
    try:
        import praisonai_sandbox  # noqa: F401
        return
    except ImportError:
        pass

    here = Path(__file__).resolve().parents[1]
    if (here / "praisonai_sandbox").is_dir():
        root = str(here)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_code() -> None:
    try:
        import praisonai_code  # noqa: F401
        return
    except ImportError:
        pass

    sandbox_src = Path(__file__).resolve().parents[1]
    code_src = sandbox_src.parent / "praisonai-code"
    if (code_src / "praisonai_code").is_dir():
        root = str(code_src)
        if root not in sys.path:
            sys.path.insert(0, root)
