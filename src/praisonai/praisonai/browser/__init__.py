"""Browser automation package for PraisonAI.

Provides a bridge server for Chrome Extension ↔ PraisonAI Agent communication.

Example:
    # Start the browser server
    praisonai browser start --port 8765
    
    # Or programmatically
    from praisonai.browser import BrowserServer
    server = BrowserServer(port=8765)
    server.start()
"""

# Lazy imports to avoid heavy dependencies at import time
# Use explicit import in __getattr__ instead of module import

def __getattr__(name: str):
    if name == "BrowserServer":
        from .server import BrowserServer
        return BrowserServer
    elif name == "BrowserAgent":
        from .agent import BrowserAgent
        return BrowserAgent
    elif name == "SessionManager":
        from .sessions import SessionManager
        return SessionManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["BrowserServer", "BrowserAgent", "SessionManager"]
