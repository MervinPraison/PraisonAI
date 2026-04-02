"""
Gateway implementations for PraisonAI.

Provides WebSocket gateway server for multi-agent coordination,
plus security primitives (rate limiting, pairing, approval queue).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .server import WebSocketGateway, GatewaySession
    from .rate_limiter import AuthRateLimiter
    from .pairing import PairingStore
    from .exec_approval import ExecApprovalManager, get_exec_approval_manager
    from .gateway_approval import GatewayApprovalBackend

def __getattr__(name: str):
    """Lazy loading of gateway components."""
    if name == "WebSocketGateway":
        from .server import WebSocketGateway
        return WebSocketGateway
    if name == "GatewaySession":
        from .server import GatewaySession
        return GatewaySession
    # Security / approval primitives
    if name == "AuthRateLimiter":
        from .rate_limiter import AuthRateLimiter
        return AuthRateLimiter
    if name == "PairingStore":
        from .pairing import PairingStore
        return PairingStore
    if name == "ExecApprovalManager":
        from .exec_approval import ExecApprovalManager
        return ExecApprovalManager
    if name == "get_exec_approval_manager":
        from .exec_approval import get_exec_approval_manager
        return get_exec_approval_manager
    if name == "GatewayApprovalBackend":
        from .gateway_approval import GatewayApprovalBackend
        return GatewayApprovalBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "WebSocketGateway",
    "GatewaySession",
    "AuthRateLimiter",
    "PairingStore",
    "ExecApprovalManager",
    "get_exec_approval_manager",
    "GatewayApprovalBackend",
]
