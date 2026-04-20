"""Backward compatibility shim for praisonaiagents.push.transports.

This module maintains backward compatibility for existing imports like:
    from praisonaiagents.push.transports import WebSocketTransport, PollingTransport

The actual implementations have been moved to the praisonai wrapper package.
"""
from . import WebSocketTransport, PollingTransport

__all__ = ["WebSocketTransport", "PollingTransport"]