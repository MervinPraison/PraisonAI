"""
Push transport abstractions for PraisonAI Agents.

Provides WebSocket and polling transports for the PushClient.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


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


class WebSocketTransport:
    """WebSocket transport using the ``websockets`` library."""

    def __init__(
        self,
        url: str,
        auth_token: Optional[str] = None,
    ) -> None:
        self._url = url
        self._auth_token = auth_token
        self._ws: Any = None  # websockets connection

    @property
    def is_connected(self) -> bool:
        return self._ws is not None and self._ws.open

    async def connect(self) -> None:
        try:
            import websockets
        except ImportError:
            raise ImportError(
                "websockets is required for WebSocket transport. "
                "Install with: pip install websockets"
            )

        url = self._url
        if self._auth_token:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}token={self._auth_token}"

        self._ws = await websockets.connect(url)
        logger.debug("WebSocket transport connected to %s", self._url)

    async def disconnect(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def send(self, data: Dict[str, Any]) -> None:
        if self._ws is None:
            raise ConnectionError("WebSocket not connected")
        await self._ws.send(json.dumps(data))

    async def receive(self) -> Dict[str, Any]:
        if self._ws is None:
            raise ConnectionError("WebSocket not connected")
        raw = await self._ws.recv()
        return json.loads(raw)


class PollingTransport:
    """HTTP long-polling transport using ``aiohttp``."""

    def __init__(
        self,
        base_url: str,
        auth_token: Optional[str] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._poll_token: Optional[str] = None
        self._client_id: Optional[str] = None
        self._session: Any = None  # aiohttp.ClientSession
        self._connected = False
        self._message_buffer: list = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        try:
            import aiohttp
        except ImportError:
            raise ImportError(
                "aiohttp is required for polling transport. "
                "Install with: pip install aiohttp"
            )

        self._session = aiohttp.ClientSession()
        headers = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        async with self._session.post(
            f"{self._base_url}/api/push/poll/register",
            json={},
            headers=headers,
        ) as resp:
            data = await resp.json()
            self._poll_token = data["poll_token"]
            self._client_id = data["client_id"]
            self._connected = True
            logger.debug("Polling transport registered: %s", self._client_id)

    async def disconnect(self) -> None:
        self._connected = False
        if self._session:
            await self._session.close()
            self._session = None

    async def send(self, data: Dict[str, Any]) -> None:
        if not self._connected or self._session is None:
            raise ConnectionError("Polling transport not connected")

        msg_type = data.get("type", "")
        headers = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        # Map message types to polling endpoints
        if msg_type == "channel.subscribe":
            await self._session.post(
                f"{self._base_url}/api/push/poll/subscribe",
                json={"poll_token": self._poll_token, "channel": data.get("channel", "")},
                headers=headers,
            )
        elif msg_type == "channel.unsubscribe":
            await self._session.post(
                f"{self._base_url}/api/push/poll/unsubscribe",
                json={"poll_token": self._poll_token, "channel": data.get("channel", "")},
                headers=headers,
            )
        elif msg_type == "message_ack":
            await self._session.post(
                f"{self._base_url}/api/push/poll/ack",
                json={"poll_token": self._poll_token, "event_id": data.get("event_id", "")},
                headers=headers,
            )
        elif msg_type == "presence.heartbeat":
            await self._session.post(
                f"{self._base_url}/api/push/poll/heartbeat",
                json={"poll_token": self._poll_token, "status": data.get("status", "online")},
                headers=headers,
            )

    async def receive(self) -> Dict[str, Any]:
        """Long-poll for the next message."""
        if not self._connected or self._session is None:
            raise ConnectionError("Polling transport not connected")

        # Return buffered messages first
        if self._message_buffer:
            return self._message_buffer.pop(0)

        headers = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        async with self._session.post(
            f"{self._base_url}/api/push/poll/messages",
            json={"poll_token": self._poll_token, "timeout": 30},
            headers=headers,
        ) as resp:
            data = await resp.json()
            messages = data.get("messages", [])
            if messages:
                self._message_buffer.extend(messages[1:])
                return messages[0]

        # Empty poll — return a keepalive-style empty dict
        # The client receive loop should handle this
        return {"type": "_poll_empty"}
