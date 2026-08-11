"""Monorepo bootstrap for ``praisonai_deploy`` and optional ``praisonai_code``."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_praisonai_deploy() -> None:
    """Ensure ``praisonai_deploy`` is importable in monorepo dev layouts."""
    try:
        import praisonai_deploy  # noqa: F401
        return
    except ImportError:
        pass

    here = Path(__file__).resolve().parents[1]  # .../src/praisonai-deploy
    if (here / "praisonai_deploy").is_dir():
        root = str(here)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_code() -> None:
    """Optional code-tier imports when co-installed."""
    try:
        import praisonai_code  # noqa: F401
        return
    except ImportError:
        pass

    deploy_src = Path(__file__).resolve().parents[1]
    code_src = deploy_src.parent / "praisonai-code"
    if (code_src / "praisonai_code").is_dir():
        root = str(code_src)
        if root not in sys.path:
            sys.path.insert(0, root)
