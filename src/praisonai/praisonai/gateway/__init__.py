"""
Gateway implementations for PraisonAI.

Provides WebSocket gateway server for multi-agent coordination.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import WebSocketGateway, GatewaySession

def __getattr__(name: str):
    """Lazy loading of gateway components."""
    if name == "WebSocketGateway":
        from .server import WebSocketGateway
        return WebSocketGateway
    if name == "GatewaySession":
        from .server import GatewaySession
        return GatewaySession
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["WebSocketGateway", "GatewaySession"]
