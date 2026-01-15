"""Browser automation package for PraisonAI.

Provides a bridge server for Chrome Extension ↔ PraisonAI Agent communication.

Example:
    # Start the browser server
    praisonai browser start --port 8765
    
    # Or programmatically
    from praisonai.browser import BrowserServer
    server = BrowserServer(port=8765)
    server.start()
    
    # Or use CDP agent directly
    from praisonai.browser import CDPBrowserAgent, run_hybrid
    result = await run_hybrid("Search for AI on Google")
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
    elif name == "CDPBrowserAgent":
        from .cdp_agent import CDPBrowserAgent
        return CDPBrowserAgent
    elif name == "run_cdp_only":
        from .cdp_agent import run_cdp_only
        return run_cdp_only
    elif name == "run_hybrid":
        from .cdp_agent import run_hybrid
        return run_hybrid
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "BrowserServer", 
    "BrowserAgent", 
    "SessionManager",
    "CDPBrowserAgent",
    "run_cdp_only",
    "run_hybrid",
]
