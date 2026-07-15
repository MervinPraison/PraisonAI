"""
MCP Transport Implementations

Provides STDIO and HTTP Stream transports for the MCP server.
"""

__all__ = ["StdioTransport", "HTTPStreamTransport"]


def __getattr__(name):
    """Lazy load transports."""
    if name == "StdioTransport":
        from .stdio import StdioTransport
        return StdioTransport
    elif name == "HTTPStreamTransport":
        from .http_stream import HTTPStreamTransport
        return HTTPStreamTransport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
