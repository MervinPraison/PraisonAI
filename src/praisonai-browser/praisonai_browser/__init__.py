"""Browser automation package for PraisonAI.

Provides a bridge server for Chrome Extension ↔ PraisonAI Agent communication.

Example:
    praisonai-browser start --port 8765

    from praisonai_browser import BrowserServer
    server = BrowserServer(port=8765)
    server.start()
"""

from __future__ import annotations

from praisonai_browser._version import __version__


def __getattr__(name: str):
    if name == "BrowserServer":
        from .server import BrowserServer
        return BrowserServer
    if name == "BrowserAgent":
        from .agent import BrowserAgent
        return BrowserAgent
    if name == "SessionManager":
        from .sessions import SessionManager
        return SessionManager
    if name == "CDPBrowserAgent":
        from .cdp_agent import CDPBrowserAgent
        return CDPBrowserAgent
    if name == "run_cdp_only":
        from .cdp_agent import run_cdp_only
        return run_cdp_only
    if name == "run_hybrid":
        from .cdp_agent import run_hybrid
        return run_hybrid
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
    "BrowserServer",
    "BrowserAgent",
    "SessionManager",
    "CDPBrowserAgent",
    "run_cdp_only",
    "run_hybrid",
]
