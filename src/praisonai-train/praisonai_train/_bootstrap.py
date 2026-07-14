"""Monorepo bootstrap for ``praisonai_train`` and optional ``praisonai_code``."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_praisonai_train() -> None:
    """Ensure ``praisonai_train`` is importable in monorepo dev layouts."""
    try:
        import praisonai_train  # noqa: F401
        return
    except ImportError:
        pass

    here = Path(__file__).resolve().parents[1]  # .../src/praisonai-train
    if (here / "praisonai_train").is_dir():
        root = str(here)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_code() -> None:
    """Optional code-tier imports (YAML agent loading, legacy dispatch) when co-installed."""
    try:
        import praisonai_code  # noqa: F401
        return
    except ImportError:
        pass

    train_src = Path(__file__).resolve().parents[1]
    code_src = train_src.parent / "praisonai-code"
    if (code_src / "praisonai_code").is_dir():
        root = str(code_src)
        if root not in sys.path:
            sys.path.insert(0, root)
