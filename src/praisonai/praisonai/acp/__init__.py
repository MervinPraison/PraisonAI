"""
Agent Client Protocol (ACP) support for PraisonAI.

This module provides ACP server functionality that allows IDEs/editors
(Zed, JetBrains, VSCode, Toad) to connect to PraisonAI agents.

Usage:
    # CLI
    praisonai acp [OPTIONS]
    
    # Python API
    from praisonai.acp import serve
    serve(workspace=".", agent="default")
"""

import importlib.util

__all__ = [
    "serve",
    "ACPServer",
    "ACPSession",
    "ACPConfig",
]

# Lazy imports for performance
def __getattr__(name: str):
    """Lazy import ACP components."""
    if name == "serve":
        from .server import serve
        return serve
    if name == "ACPServer":
        from .server import ACPServer
        return ACPServer
    if name == "ACPSession":
        from .session import ACPSession
        return ACPSession
    if name == "ACPConfig":
        from .config import ACPConfig
        return ACPConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _check_acp_available() -> bool:
    """Check if agent-client-protocol package is installed."""
    return importlib.util.find_spec("acp") is not None


def _get_install_instructions() -> str:
    """Get installation instructions for ACP support."""
    return (
        "ACP support requires the agent-client-protocol package.\n"
        "Install with: pip install praisonai[acp]\n"
        "Or: pip install agent-client-protocol"
    )
