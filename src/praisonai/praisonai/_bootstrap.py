"""Monorepo bootstrap for the extracted ``praisonai_code`` package.

When developing from the PraisonAI source tree with the historical
``PYTHONPATH=src/praisonai-agents:src/praisonai`` layout (no separate
``praisonai-code`` entry), make ``praisonai_code`` importable from the
sibling ``src/praisonai-code`` directory. Installed wheels/sdists are
unchanged — this only runs when the import would otherwise fail.
"""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_praisonai_code() -> None:
    """Ensure ``praisonai_code`` can be imported in monorepo dev layouts."""
    try:
        import praisonai_code  # noqa: F401
        return
    except ImportError:
        pass

    wrapper_src = Path(__file__).resolve().parents[1]  # .../src/praisonai
    code_src = wrapper_src.parent / "praisonai-code"
    if (code_src / "praisonai_code").is_dir():
        root = str(code_src)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_bot() -> None:
    """Ensure ``praisonai_bot`` can be imported in monorepo dev layouts."""
    try:
        import praisonai_bot  # noqa: F401
        return
    except ImportError:
        pass

    wrapper_src = Path(__file__).resolve().parents[1]  # .../src/praisonai
    bot_src = wrapper_src.parent / "praisonai-bot"
    if (bot_src / "praisonai_bot").is_dir():
        root = str(bot_src)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_train() -> None:
    """Ensure ``praisonai_train`` can be imported in monorepo dev layouts."""
    try:
        import praisonai_train  # noqa: F401
        return
    except ImportError:
        pass

    wrapper_src = Path(__file__).resolve().parents[1]  # .../src/praisonai
    train_src = wrapper_src.parent / "praisonai-train"
    if (train_src / "praisonai_train").is_dir():
        root = str(train_src)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_browser() -> None:
    """Ensure ``praisonai_browser`` can be imported in monorepo dev layouts."""
    try:
        import praisonai_browser  # noqa: F401
        return
    except ImportError:
        pass

    wrapper_src = Path(__file__).resolve().parents[1]  # .../src/praisonai
    browser_src = wrapper_src.parent / "praisonai-browser"
    if (browser_src / "praisonai_browser").is_dir():
        root = str(browser_src)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_mcp() -> None:
    """Ensure ``praisonai_mcp`` can be imported in monorepo dev layouts."""
    try:
        import praisonai_mcp  # noqa: F401
        return
    except ImportError:
        pass

    wrapper_src = Path(__file__).resolve().parents[1]  # .../src/praisonai
    mcp_src = wrapper_src.parent / "praisonai-mcp"
    if (mcp_src / "praisonai_mcp").is_dir():
        root = str(mcp_src)
        if root not in sys.path:
            sys.path.insert(0, root)


def ensure_praisonai_sandbox() -> None:
    """Ensure ``praisonai_sandbox`` can be imported in monorepo dev layouts."""
    try:
        import praisonai_sandbox  # noqa: F401
        return
    except ImportError:
        pass

    wrapper_src = Path(__file__).resolve().parents[1]  # .../src/praisonai
    sandbox_src = wrapper_src.parent / "praisonai-sandbox"
    if (sandbox_src / "praisonai_sandbox").is_dir():
        root = str(sandbox_src)
        if root not in sys.path:
            sys.path.insert(0, root)
