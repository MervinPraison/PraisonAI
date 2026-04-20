"""
Push Channel Manager for PraisonAI Gateway.

Implements channel/topic-based push messaging with fan-out delivery.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from praisonaiagents.gateway.protocols import (
    ChannelInfo,
    EventType,
    GatewayEvent,
)

if TYPE_CHECKING:
    from .server import WebSocketGateway

logger = logging.getLogger(__name__)


class ChannelManager:
    """Manages push channels with subscribe/publish fan-out.

    Uses composition — receives a gateway reference for sending messages.
    Thread-safe via a reentrant lock for the channel registry.
    """

    def __init__(self, gateway: "WebSocketGateway") -> None:
        self._gateway = gateway
        self._lock = threading.RLock()
        # channel_name -> ChannelInfo
        self._channels: Dict[str, ChannelInfo] = {}
        # channel_name -> set of client_ids
        self._channel_subscribers: Dict[str, Set[str]] = {}
        # client_id -> set of channel_names (inverse index)
        self._client_channels: Dict[str, Set[str]] = {}

    # ------------------------------------------------------------------
    # Channel lifecycle
    # ------------------------------------------------------------------

    def add_channel(
        self,
        channel_name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create a named channel. Returns True if created."""
        with self._lock:
            if channel_name in self._channels:
                return False
            self._channels[channel_name] = ChannelInfo(
                name=channel_name,
                created_at=time.time(),
                metadata=metadata or {},
            )
            self._channel_subscribers[channel_name] = set()
        logger.info("Channel created: %s", channel_name)
        return True

    def remove_channel(self, channel_name: str) -> bool:
        """Delete a channel and unsubscribe all clients."""
        with self._lock:
            if channel_name not in self._channels:
                return False
            # Unsubscribe all clients from this channel
            for cid in list(self._channel_subscribers.get(channel_name, [])):
                client_set = self._client_channels.get(cid)
                if client_set:
                    client_set.discard(channel_name)
            del self._channels[channel_name]
            del self._channel_subscribers[channel_name]
        logger.info("Channel removed: %s", channel_name)
        return True

    def get_channel(self, channel_name: str) -> Optional[ChannelInfo]:
        """Get channel metadata."""
        with self._lock:
            info = self._channels.get(channel_name)
            if info is not None:
                info.subscriber_count = len(
                    self._channel_subscribers.get(channel_name, set())
                )
            return info

    def list_channels(self) -> List[str]:
        """List all active channel names."""
        with self._lock:
            return list(self._channels.keys())

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    def subscribe_client(self, client_id: str, channel_name: str) -> bool:
        """Subscribe a client to a channel."""
        with self._lock:
            if channel_name not in self._channels:
                return False
            subs = self._channel_subscribers[channel_name]
            if client_id in subs:
                return False
            subs.add(client_id)
            self._client_channels.setdefault(client_id, set()).add(channel_name)
        logger.debug("Client %s subscribed to %s", client_id, channel_name)
        return True

    def unsubscribe_client(self, client_id: str, channel_name: str) -> bool:
        """Unsubscribe a client from a channel."""
        with self._lock:
            subs = self._channel_subscribers.get(channel_name)
            if subs is None or client_id not in subs:
                return False
            subs.discard(client_id)
            client_set = self._client_channels.get(client_id)
            if client_set:
                client_set.discard(channel_name)
        logger.debug("Client %s unsubscribed from %s", client_id, channel_name)
        return True

    def unsubscribe_all(self, client_id: str) -> None:
        """Unsubscribe a client from all channels (called on disconnect)."""
        with self._lock:
            channels = list(self._client_channels.pop(client_id, set()))
            for ch in channels:
                subs = self._channel_subscribers.get(ch)
                if subs:
                    subs.discard(client_id)

    def get_subscribers(self, channel_name: str) -> List[str]:
        """List client IDs subscribed to a channel."""
        with self._lock:
            return list(self._channel_subscribers.get(channel_name, []))

    def get_client_channels(self, client_id: str) -> List[str]:
        """List channels a client is subscribed to."""
        with self._lock:
            return list(self._client_channels.get(client_id, []))

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish_to_channel(
        self,
        channel_name: str,
        event: GatewayEvent,
        exclude: Optional[List[str]] = None,
    ) -> int:
        """Fan-out an event to all subscribers of a channel.

        Returns the number of clients the event was sent to.
        """
        with self._lock:
            if channel_name not in self._channels:
                return 0
            targets = set(self._channel_subscribers[channel_name])

        exclude_set = set(exclude) if exclude else set()
        event_dict = event.to_dict()
        event_dict["channel"] = channel_name
        sent = 0

        for cid in targets:
            if cid in exclude_set:
                continue
            await self._gateway._send_to_client(cid, event_dict)
            sent += 1

        # Publish to Redis if adapter is available
        redis_adapter = getattr(self._gateway, "_redis_pubsub", None)
        if redis_adapter is not None:
            try:
                await redis_adapter.publish(channel_name, event_dict)
            except Exception as e:
                logger.error("Redis publish failed for channel %s: %s", channel_name, e)

        return sent

    # ------------------------------------------------------------------
    # WebSocket message handler
    # ------------------------------------------------------------------

    async def handle_message(
        self, client_id: str, msg_type: str, data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle channel.* message types from a WebSocket client.

        Returns a response dict to send back, or None.
        """
        channel_name = data.get("channel", "")

        if msg_type == "channel.create":
            ok = self.add_channel(channel_name, data.get("metadata"))
            return {"type": "channel.created", "channel": channel_name, "ok": ok}

        if msg_type == "channel.subscribe":
            ok = self.subscribe_client(client_id, channel_name)
            return {"type": "channel.subscribed", "channel": channel_name, "ok": ok}

        if msg_type == "channel.unsubscribe":
            ok = self.unsubscribe_client(client_id, channel_name)
            return {"type": "channel.unsubscribed", "channel": channel_name, "ok": ok}

        if msg_type == "channel.publish":
            event = GatewayEvent(
                type=EventType.CHANNEL_MESSAGE,
                data=data.get("data", {}),
                source=client_id,
            )
            count = await self.publish_to_channel(
                channel_name, event, exclude=[client_id],
            )
            return {"type": "channel.published", "channel": channel_name, "delivered": count}

        if msg_type == "channel.list":
            channels = self.list_channels()
            return {"type": "channel.list", "channels": channels}

        return None
