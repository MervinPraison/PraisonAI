"""
Push Client for PraisonAI Agents.

Provides a Python SDK for consuming push notifications from the gateway.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Callable, Coroutine, Dict, List, Optional, Union

from praisonaiagents.gateway.protocols import PresenceInfo
from .models import ChannelMessage

logger = logging.getLogger(__name__)

# Type alias for channel message callbacks
MessageCallback = Callable[[ChannelMessage], Coroutine[Any, Any, None]]


class PushClient:
    """Client SDK for receiving push notifications from a PraisonAI gateway.

    Supports WebSocket (primary) with automatic fallback to HTTP polling.
    Handles reconnections, channel subscriptions, and message ACKs transparently.

    Example::

        client = PushClient("ws://localhost:8765/ws", auth_token="my-token")
        await client.connect()

        @client.on("channel_message")
        async def on_msg(msg: ChannelMessage):
            print(f"Got message on {msg.channel}: {msg.data}")

        await client.subscribe("alerts", on_msg)
        await client.publish("alerts", {"level": "info", "text": "hello"})

        # Block until disconnected
        await client.wait_closed()
    """

    def __init__(
        self,
        url: str,
        auth_token: Optional[str] = None,
        client_id: Optional[str] = None,
        auto_reconnect: bool = True,
        fallback_to_polling: bool = True,
    ) -> None:
        self._url = url
        self._auth_token = auth_token
        self._client_id = client_id or str(uuid.uuid4())
        self._auto_reconnect = auto_reconnect
        self._fallback_to_polling = fallback_to_polling

        self._transport: Any = None
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._connected = False
        self._closed_event = asyncio.Event()
        self._using_polling = False

        # channel_name -> list of callbacks
        self._channel_callbacks: Dict[str, List[MessageCallback]] = {}
        # event_type -> list of callbacks
        self._event_handlers: Dict[str, List[Callable]] = {}
        # Channels to re-subscribe to after reconnect
        self._subscribed_channels: set = set()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Establish connection to the gateway."""
        from .transports import WebSocketTransport

        self._transport = WebSocketTransport(self._url, self._auth_token)
        try:
            await self._transport.connect()
            self._connected = True
            self._using_polling = False
            logger.info("PushClient connected via WebSocket")
        except Exception as e:
            logger.warning("WebSocket connect failed: %s", e)
            if self._fallback_to_polling:
                await self._switch_to_polling()
            else:
                raise

        self._closed_event.clear()
        self._receive_task = asyncio.ensure_future(self._receive_loop())
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

    async def disconnect(self) -> None:
        """Gracefully close the connection."""
        self._connected = False

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._transport:
            await self._transport.disconnect()
            self._transport = None

        self._closed_event.set()
        logger.info("PushClient disconnected")

    async def wait_closed(self) -> None:
        """Block until the client is disconnected."""
        await self._closed_event.wait()

    @property
    def is_connected(self) -> bool:
        return self._connected and self._transport is not None and self._transport.is_connected

    # ------------------------------------------------------------------
    # Channel operations
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        channel: str,
        callback: Optional[MessageCallback] = None,
    ) -> None:
        """Subscribe to a push channel.

        Args:
            channel: Channel name to subscribe to
            callback: Async function called for each message on this channel
        """
        await self._send({"type": "channel.subscribe", "channel": channel})
        self._subscribed_channels.add(channel)
        if callback:
            self._channel_callbacks.setdefault(channel, []).append(callback)

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        await self._send({"type": "channel.unsubscribe", "channel": channel})
        self._subscribed_channels.discard(channel)
        self._channel_callbacks.pop(channel, None)

    async def publish(self, channel: str, data: Dict[str, Any]) -> None:
        """Publish a message to a channel."""
        await self._send({
            "type": "channel.publish",
            "channel": channel,
            "data": data,
        })

    async def create_channel(
        self, channel: str, metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a new channel on the gateway."""
        await self._send({
            "type": "channel.create",
            "channel": channel,
            "metadata": metadata or {},
        })

    # ------------------------------------------------------------------
    # Presence
    # ------------------------------------------------------------------

    async def get_presence(
        self, channel: Optional[str] = None,
    ) -> List[PresenceInfo]:
        """Query presence for a channel or all clients."""
        await self._send({
            "type": "presence.query",
            "channel": channel,
        })
        # The response will come via the receive loop
        # For a synchronous result, we'd need a request-response pattern
        # For now, presence info arrives via event handlers
        return []

    async def set_status(
        self, status: str = "online", metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update own presence status."""
        await self._send({
            "type": "presence.heartbeat",
            "status": status,
            "metadata": metadata or {},
        })

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on(self, event_type: str) -> Callable:
        """Decorator to register an event handler.

        Example::

            @client.on("presence.list")
            async def on_presence(data):
                print(data)
        """
        def decorator(func: Callable) -> Callable:
            self._event_handlers.setdefault(event_type, []).append(func)
            return func
        return decorator

    async def wait_for(
        self, channel: str, timeout: float = 30.0,
    ) -> ChannelMessage:
        """Block until the next message on a channel, or raise TimeoutError."""
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async def _one_shot(msg: ChannelMessage) -> None:
            if not future.done():
                future.set_result(msg)

        self._channel_callbacks.setdefault(channel, []).append(_one_shot)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            cbs = self._channel_callbacks.get(channel, [])
            if _one_shot in cbs:
                cbs.remove(_one_shot)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _send(self, data: Dict[str, Any]) -> None:
        """Send a message through the active transport."""
        if not (self._transport and self._transport.is_connected):
            raise ConnectionError("Push client is not connected")
        await self._transport.send(data)

    async def _receive_loop(self) -> None:
        """Background task that receives and dispatches messages."""
        reconnect_delay = 1.0
        max_reconnect_delay = 30.0

        while self._connected:
            try:
                if self._transport is None or not self._transport.is_connected:
                    if self._auto_reconnect:
                        await self._reconnect(reconnect_delay)
                        reconnect_delay = min(
                            reconnect_delay * 2, max_reconnect_delay,
                        )
                        continue
                    else:
                        break

                data = await self._transport.receive()
                reconnect_delay = 1.0  # Reset on successful receive

                msg_type = data.get("type", "")

                # Skip polling keepalives
                if msg_type == "_poll_empty":
                    continue

                # Auto-ACK for delivery guarantees (non-blocking)
                event_id = data.get("event_id")
                if event_id and msg_type not in (
                    "ack_received", "nack_received", "channel.subscribed",
                    "channel.unsubscribed", "channel.published", "channel.created",
                    "channel.list", "presence.heartbeat_ack", "presence.list",
                    "joined", "left", "error",
                ):
                    asyncio.create_task(self._send({"type": "message_ack", "event_id": event_id}))

                # Dispatch channel messages (non-blocking)
                channel = data.get("channel")
                if channel and msg_type in ("channel_message",):
                    msg = ChannelMessage.from_event_dict(data)
                    for cb in self._channel_callbacks.get(channel, []):
                        try:
                            if asyncio.iscoroutinefunction(cb):
                                asyncio.create_task(cb(msg))
                            else:
                                cb(msg)
                        except Exception as e:
                            logger.error("Channel callback error: %s", e)

                # Dispatch event handlers
                handlers = self._event_handlers.get(msg_type, [])
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(data)
                        else:
                            handler(data)
                    except Exception as e:
                        logger.error("Event handler error: %s", e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Receive loop error: %s", e)
                if self._auto_reconnect and self._connected:
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(
                        reconnect_delay * 2, max_reconnect_delay,
                    )
                else:
                    break

        self._connected = False
        self._closed_event.set()

    async def _heartbeat_loop(self) -> None:
        """Periodically send presence heartbeats."""
        while self._connected:
            try:
                await asyncio.sleep(15)
                if self._connected:
                    await self._send({
                        "type": "presence.heartbeat",
                        "status": "online",
                    })
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _reconnect(self, delay: float) -> None:
        """Attempt to reconnect after a disconnect."""
        logger.info("Reconnecting in %.1fs...", delay)
        await asyncio.sleep(delay)

        if self._transport:
            await self._transport.disconnect()

        try:
            from .transports import WebSocketTransport
            self._transport = WebSocketTransport(self._url, self._auth_token)
            await self._transport.connect()
            self._using_polling = False
            logger.info("Reconnected via WebSocket")
        except Exception as e:
            logger.warning("WebSocket reconnect failed: %s", e)
            if self._fallback_to_polling and not self._using_polling:
                await self._switch_to_polling()
            else:
                return

        # Re-subscribe to all channels
        for ch in list(self._subscribed_channels):
            try:
                await self._send({"type": "channel.subscribe", "channel": ch})
            except Exception as e:
                logger.error("Re-subscribe to %s failed: %s", ch, e)

    async def _switch_to_polling(self) -> None:
        """Switch from WebSocket to HTTP polling transport."""
        from .transports import PollingTransport
        from urllib.parse import urlparse, urlunparse

        # Derive HTTP URL from WebSocket URL using robust URL parsing
        parsed = urlparse(self._url)
        scheme = "https" if parsed.scheme == "wss" else "http"
        path = parsed.path.rstrip("/")
        if path.endswith("/ws"):
            path = path[:-3]
        
        http_url = urlunparse(parsed._replace(scheme=scheme, path=path))

        self._transport = PollingTransport(http_url, self._auth_token)
        try:
            await self._transport.connect()
            self._connected = True
            self._using_polling = True
            logger.info("Switched to polling transport")
        except Exception as e:
            logger.error("Polling transport failed: %s", e)
            self._connected = False
