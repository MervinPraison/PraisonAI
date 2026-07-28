"""Lazy access from praisonai-bot to optional praisonai-browser modules."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def _ensure_praisonai_browser() -> None:
    """Ensure ``praisonai_browser`` is importable in monorepo dev layouts."""
    try:
        import praisonai_browser  # noqa: F401
        return
    except ImportError:
        pass

    bot_src = Path(__file__).resolve().parents[1]
    browser_src = bot_src.parent / "praisonai-browser"
    if (browser_src / "praisonai_browser").is_dir():
        root = str(browser_src)
        if root not in sys.path:
            sys.path.insert(0, root)


def browser_available() -> bool:
    """Return True only when local Playwright automation can actually run.

    Both ``praisonai_browser`` *and* its Playwright runtime must be importable;
    Playwright is lazily imported inside ``PlaywrightBrowserAgent._launch``, so a
    base install without the Playwright extra would otherwise select the local
    tool and fail at invocation instead of using the cloud ``BrowserBaseTool``
    fallback.
    """
    _ensure_praisonai_browser()
    try:
        import praisonai_browser  # noqa: F401
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def import_browser_attr(name: str) -> Any:
    _ensure_praisonai_browser()
    try:
        from praisonai_browser.playwright_agent import PlaywrightBrowserAgent
    except ImportError as exc:
        raise ImportError(
            "Local browser automation requires praisonai-browser. "
            "Install with: pip install praisonai-browser && playwright install chromium"
        ) from exc
    if name == "PlaywrightBrowserAgent":
        return PlaywrightBrowserAgent
    raise AttributeError(name)
