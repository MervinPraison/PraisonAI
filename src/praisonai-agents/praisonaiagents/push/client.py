"""Backward compatibility shim for praisonaiagents.push.client.

This module maintains backward compatibility for existing imports like:
    from praisonaiagents.push.client import PushClient

The actual implementation has been moved to the praisonai wrapper package.
"""
from . import PushClient

__all__ = ["PushClient"]