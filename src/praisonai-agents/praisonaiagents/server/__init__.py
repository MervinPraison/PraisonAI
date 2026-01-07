"""
Server Module for PraisonAI Agents.

Provides an optional HTTP server with SSE event streaming
for real-time agent communication.

Features:
- REST API for agent operations
- Server-Sent Events (SSE) for real-time updates
- Event bus integration
- Multi-project support
- CORS handling

Usage:
    from praisonaiagents.server import AgentServer
    
    # Create and start server
    server = AgentServer(port=8080)
    server.start()
    
    # Or use as context manager
    with AgentServer(port=8080) as server:
        # Server is running
        pass
"""

__all__ = [
    "AgentServer",
    "ServerConfig",
]


def __getattr__(name: str):
    """Lazy load module components."""
    if name == "AgentServer":
        from .server import AgentServer
        return AgentServer
    
    if name == "ServerConfig":
        from .server import ServerConfig
        return ServerConfig
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
