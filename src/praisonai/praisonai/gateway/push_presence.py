"""
Push Presence Manager for PraisonAI Gateway.

Tracks connected clients' online/idle/offline status with background sweeping.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from praisonaiagents.gateway.config import PresenceConfig
from praisonaiagents.gateway.protocols import (
    EventType,
    GatewayEvent,
    PresenceInfo,
)

if TYPE_CHECKING:
    from .server import WebSocketGateway

logger = logging.getLogger(__name__)


class PresenceManager:
    """Tracks client presence with heartbeat-based offline detection.

    Uses composition — receives a gateway reference for broadcasting
    presence changes to channel subscribers.
    """

    def __init__(
        self,
        gateway: "WebSocketGateway",
        config: PresenceConfig,
    ) -> None:
        self._gateway = gateway
        self._config = config
        self._lock = threading.RLock()
        self._presence_store: Dict[str, PresenceInfo] = {}
        self._sweeper_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_sweeper(self) -> None:
        """Start the background presence sweeper task."""
        if not self._config.enabled:
            return
        self._sweeper_task = asyncio.ensure_future(self._run_sweeper())
        logger.info("Presence sweeper started (interval=%ds)", self._config.heartbeat_interval)

    async def stop_sweeper(self) -> None:
        """Stop the background sweeper."""
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
        self._sweeper_task = None

    # ------------------------------------------------------------------
    # Presence tracking
    # ------------------------------------------------------------------

    async def track_presence(
        self,
        client_id: str,
        status: str = "online",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Set or update a client's presence."""
        channel_mgr = getattr(self._gateway, "_channel_mgr", None)
        channels = channel_mgr.get_client_channels(client_id) if channel_mgr else []

        is_new = False
        with self._lock:
            existing = self._presence_store.get(client_id)
            if existing is None:
                is_new = True
            self._presence_store[client_id] = PresenceInfo(
                client_id=client_id,
                status=status,
                last_seen=time.time(),
                metadata=metadata or (existing.metadata if existing else {}),
                channels=channels,
            )

        # Broadcast presence change
        if self._config.broadcast_changes:
            event_type = EventType.PRESENCE_JOIN if is_new else EventType.PRESENCE_UPDATE
            await self._broadcast_presence_event(client_id, event_type, status, channels)

        # Update Redis if available
        redis_adapter = getattr(self._gateway, "_redis_pubsub", None)
        if redis_adapter is not None:
            try:
                info = self._presence_store.get(client_id)
                if info:
                    await redis_adapter.set_presence(
                        client_id,
                        info.to_dict(),
                        ttl=self._config.offline_timeout * 2,
                    )
            except Exception as e:
                logger.error("Redis presence update failed: %s", e)

    async def remove_presence(self, client_id: str) -> None:
        """Remove a client's presence (on disconnect)."""
        with self._lock:
            info = self._presence_store.pop(client_id, None)

        if info and self._config.broadcast_changes:
            await self._broadcast_presence_event(
                client_id, EventType.PRESENCE_LEAVE, "offline", info.channels,
            )

        redis_adapter = getattr(self._gateway, "_redis_pubsub", None)
        if redis_adapter is not None:
            try:
                await redis_adapter.remove_presence(client_id)
            except Exception as e:
                logger.error("Redis presence remove failed: %s", e)

    def get_presence(self, client_id: str) -> Optional[PresenceInfo]:
        """Get a single client's presence."""
        with self._lock:
            return self._presence_store.get(client_id)

    def get_all_presence(
        self, channel_name: Optional[str] = None,
    ) -> List[PresenceInfo]:
        """Get presence info, optionally filtered by channel."""
        with self._lock:
            if channel_name is None:
                return list(self._presence_store.values())
            return [
                p for p in self._presence_store.values()
                if channel_name in p.channels
            ]

    def get_online_count(self, channel_name: Optional[str] = None) -> int:
        """Count online clients."""
        entries = self.get_all_presence(channel_name)
        return sum(1 for p in entries if p.status == "online")

    # ------------------------------------------------------------------
    # WebSocket message handler
    # ------------------------------------------------------------------

    async def handle_message(
        self, client_id: str, msg_type: str, data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle presence.* message types."""
        if msg_type == "presence.heartbeat":
            await self.track_presence(
                client_id,
                status=data.get("status", "online"),
                metadata=data.get("metadata"),
            )
            return {"type": "presence.heartbeat_ack", "ok": True}

        if msg_type == "presence.query":
            channel = data.get("channel")
            entries = self.get_all_presence(channel)
            return {
                "type": "presence.list",
                "channel": channel,
                "presence": [p.to_dict() for p in entries],
            }

        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_sweeper(self) -> None:
        """Background task that marks stale clients as offline."""
        while True:
            try:
                await asyncio.sleep(self._config.heartbeat_interval)
                now = time.time()
                stale_ids: List[str] = []

                with self._lock:
                    for cid, info in self._presence_store.items():
                        if info.status != "offline" and (
                            now - info.last_seen > self._config.offline_timeout
                        ):
                            stale_ids.append(cid)

                for cid in stale_ids:
                    with self._lock:
                        info = self._presence_store.get(cid)
                        if info:
                            info.status = "offline"
                    if info and self._config.broadcast_changes:
                        await self._broadcast_presence_event(
                            cid, EventType.PRESENCE_LEAVE, "offline", info.channels,
                        )
                    logger.debug("Client %s marked offline (stale)", cid)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Presence sweeper error: %s", e)

    async def _broadcast_presence_event(
        self,
        client_id: str,
        event_type: EventType,
        status: str,
        channels: List[str],
    ) -> None:
        """Broadcast a presence change to relevant channel subscribers."""
        channel_mgr = getattr(self._gateway, "_channel_mgr", None)
        if channel_mgr is None:
            return

        event = GatewayEvent(
            type=event_type,
            data={"client_id": client_id, "status": status},
            source=client_id,
        )
        for ch in channels:
            try:
                await channel_mgr.publish_to_channel(ch, event, exclude=[client_id])
            except Exception as e:
                logger.error("Presence broadcast to %s failed: %s", ch, e)
