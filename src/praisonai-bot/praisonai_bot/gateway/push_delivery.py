"""
Push Delivery Guarantee Manager for PraisonAI Gateway.

Provides at-least-once message delivery with ack tracking and retry logic.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from praisonaiagents.gateway.config import DeliveryConfig
from praisonaiagents.gateway.protocols import (
    EventType,
    GatewayEvent,
)

if TYPE_CHECKING:
    from .server import WebSocketGateway

logger = logging.getLogger(__name__)


@dataclass
class PendingDelivery:
    """Tracks a message pending acknowledgement from a client."""

    event: GatewayEvent
    sent_at: float = field(default_factory=time.time)
    retry_count: int = 0
    next_retry_at: float = 0.0


class DeliveryGuaranteeManager:
    """Ensures at-least-once delivery with ack tracking and retries.

    Uses composition — receives a gateway reference for resending messages.
    """

    def __init__(
        self,
        gateway: "WebSocketGateway",
        config: DeliveryConfig,
    ) -> None:
        self._gateway = gateway
        self._config = config
        self._lock = threading.RLock()
        # event_id -> GatewayEvent
        self._message_store: Dict[str, GatewayEvent] = {}
        # client_id -> {event_id -> PendingDelivery}
        self._pending_acks: Dict[str, Dict[str, PendingDelivery]] = {}
        self._sweeper_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_sweeper(self) -> None:
        """Start the background retry sweeper."""
        if not self._config.enabled:
            return
        self._sweeper_task = asyncio.ensure_future(self._run_sweeper())
        logger.info(
            "Delivery sweeper started (ack_timeout=%ds, max_retries=%d)",
            self._config.ack_timeout,
            self._config.max_retries,
        )

    async def stop_sweeper(self) -> None:
        """Stop the retry sweeper."""
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
        self._sweeper_task = None

    # ------------------------------------------------------------------
    # Message storage
    # ------------------------------------------------------------------

    async def store_message(self, event: GatewayEvent) -> str:
        """Persist a message to the in-memory store."""
        with self._lock:
            self._message_store[event.event_id] = event

        # Also persist to Redis if configured
        redis_adapter = getattr(self._gateway, "_redis_pubsub", None)
        if redis_adapter is not None and self._config.store_backend == "redis":
            try:
                await redis_adapter.store_message(
                    event.event_id,
                    event.to_dict(),
                    ttl=self._config.message_ttl,
                )
            except Exception as e:
                logger.error("Redis message store failed: %s", e)

        return event.event_id

    # ------------------------------------------------------------------
    # Delivery tracking
    # ------------------------------------------------------------------

    async def track_delivery(self, client_id: str, event: GatewayEvent) -> None:
        """Record that an event was sent to a client and needs an ACK."""
        if not self._config.enabled:
            return

        await self.store_message(event)

        now = time.time()
        pending = PendingDelivery(
            event=event,
            sent_at=now,
            retry_count=0,
            next_retry_at=now + self._config.ack_timeout,
        )
        with self._lock:
            self._pending_acks.setdefault(client_id, {})[event.event_id] = pending

    async def acknowledge(self, client_id: str, event_id: str) -> bool:
        """Mark a message as acknowledged by a client."""
        with self._lock:
            client_pending = self._pending_acks.get(client_id)
            if client_pending is None or event_id not in client_pending:
                return False
            del client_pending[event_id]
            if not client_pending:
                del self._pending_acks[client_id]
        logger.debug("ACK from %s for %s", client_id, event_id)
        return True

    async def nack(self, client_id: str, event_id: str) -> None:
        """Negative ack — schedule immediate redelivery."""
        with self._lock:
            client_pending = self._pending_acks.get(client_id, {})
            pending = client_pending.get(event_id)
            if pending:
                pending.next_retry_at = time.time()  # immediate retry
        logger.debug("NACK from %s for %s", client_id, event_id)

    async def get_unacknowledged(
        self, client_id: str, limit: int = 100,
    ) -> List[GatewayEvent]:
        """Get pending unacknowledged messages for a client."""
        with self._lock:
            client_pending = self._pending_acks.get(client_id, {})
            entries = sorted(
                client_pending.values(), key=lambda p: p.sent_at,
            )[:limit]
            return [p.event for p in entries]

    async def retry_unacknowledged(self, client_id: str) -> int:
        """Redeliver all unacknowledged messages to a client."""
        events = await self.get_unacknowledged(client_id)
        count = 0
        for event in events:
            event_dict = event.to_dict()
            event_dict["_redelivered"] = True
            await self._gateway._send_to_client(client_id, event_dict)
            count += 1
        return count

    async def purge_acknowledged(self, max_age_seconds: int = 86400) -> int:
        """Remove old messages from the store."""
        cutoff = time.time() - max_age_seconds
        purged = 0

        # Collect IDs still pending
        pending_ids: set = set()
        with self._lock:
            for client_pending in self._pending_acks.values():
                pending_ids.update(client_pending.keys())

            to_remove = [
                eid for eid, ev in self._message_store.items()
                if ev.timestamp < cutoff and eid not in pending_ids
            ]
            for eid in to_remove:
                del self._message_store[eid]
                purged += 1

        return purged

    def remove_client(self, client_id: str) -> None:
        """Remove all pending acks for a disconnected client.

        Note: pending messages are kept in the store for redelivery
        when the client reconnects.
        """
        with self._lock:
            self._pending_acks.pop(client_id, None)

    # ------------------------------------------------------------------
    # WebSocket message handler
    # ------------------------------------------------------------------

    async def handle_message(
        self, client_id: str, msg_type: str, data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Handle message_ack / message_nack message types."""
        event_id = data.get("event_id", "")

        if msg_type == "message_ack":
            ok = await self.acknowledge(client_id, event_id)
            return {"type": "ack_received", "event_id": event_id, "ok": ok}

        if msg_type == "message_nack":
            await self.nack(client_id, event_id)
            return {"type": "nack_received", "event_id": event_id, "ok": True}

        return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_sweeper(self) -> None:
        """Background task that retries unacknowledged messages."""
        while True:
            try:
                await asyncio.sleep(5)
                now = time.time()

                retry_targets: List[tuple] = []  # (client_id, event_id, PendingDelivery)
                dead_letters: List[tuple] = []

                with self._lock:
                    for cid, client_pending in list(self._pending_acks.items()):
                        for eid, pending in list(client_pending.items()):
                            if now < pending.next_retry_at:
                                continue
                            if pending.retry_count >= self._config.max_retries:
                                dead_letters.append((cid, eid))
                            else:
                                retry_targets.append((cid, eid, pending))

                # Process retries
                for cid, eid, pending in retry_targets:
                    event_dict = pending.event.to_dict()
                    event_dict["_redelivered"] = True
                    event_dict["_retry_count"] = pending.retry_count + 1
                    await self._gateway._send_to_client(cid, event_dict)

                    with self._lock:
                        pending.retry_count += 1
                        backoff = self._config.ack_timeout * (
                            self._config.retry_backoff ** pending.retry_count
                        )
                        pending.next_retry_at = now + backoff

                    logger.debug(
                        "Retry %d for event %s to client %s",
                        pending.retry_count, eid, cid,
                    )

                # Process dead letters
                for cid, eid in dead_letters:
                    with self._lock:
                        client_pending = self._pending_acks.get(cid, {})
                        client_pending.pop(eid, None)
                        if not client_pending and cid in self._pending_acks:
                            del self._pending_acks[cid]
                    logger.warning(
                        "Dead letter: event %s for client %s after %d retries",
                        eid, cid, self._config.max_retries,
                    )

                # Periodic purge of old acknowledged messages
                await self.purge_acknowledged(self._config.message_ttl)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Delivery sweeper error: %s", e)
