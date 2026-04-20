"""Push transport protocol — implementations live in the praisonai wrapper."""
from __future__ import annotations
from typing import Any, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class PushTransportProtocol(Protocol):
    """Protocol for push client transports."""

    @property
    def is_connected(self) -> bool:
        """Whether the transport is currently connected."""
        ...

    async def connect(self) -> None:
        """Establish connection."""
        ...

    async def disconnect(self) -> None:
        """Close connection."""
        ...

    async def send(self, data: Dict[str, Any]) -> None:
        """Send a JSON message."""
        ...

    async def receive(self) -> Dict[str, Any]:
        """Receive a JSON message. Blocks until a message arrives."""
        ...