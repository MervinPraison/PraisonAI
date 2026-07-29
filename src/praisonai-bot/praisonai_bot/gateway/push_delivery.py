"""
Push Delivery Guarantee Manager for PraisonAI Gateway.

Provides at-least-once message delivery with ack tracking and retry logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from praisonaiagents.gateway.config import DeliveryConfig
from praisonaiagents.gateway.protocols import (
    EventType,
    GatewayEvent,
)

if TYPE_CHECKING:
    from .server import WebSocketGateway

logger = logging.getLogger(__name__)

# Default durable store path, mirroring OutboundQueue's ~/.praisonai/state layout.
_DEFAULT_SQLITE_PATH = "~/.praisonai/state/push_delivery.sqlite"


class SqlitePushStore:
    """SQLite-backed durable store for pending push-delivery events.

    Mirrors the established ``OutboundQueue`` pattern (WAL journal, stdlib
    ``sqlite3``, per-instance lock, TTL eviction) so the at-least-once push
    guarantee survives a gateway restart without any external service. Each
    row records the recipient ``client_id`` alongside the event so pending
    deliveries can be reconstructed on startup; each is evicted on ack or once
    older than ``message_ttl``.
    """

    def __init__(self, path: Union[str, Path] = _DEFAULT_SQLITE_PATH) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            return conn
        except Exception:
            conn.close()
            raise

    def _init_schema(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS push_delivery (
                    event_id TEXT PRIMARY KEY,
                    client_id TEXT,
                    ts REAL NOT NULL,
                    payload TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_push_ts ON push_delivery(ts)")
            # Backfill the recipient column for stores created before the
            # durable-recipient fix so pre-existing rows still load cleanly.
            cols = {
                row[1]
                for row in conn.execute("PRAGMA table_info(push_delivery)").fetchall()
            }
            if "client_id" not in cols:
                conn.execute("ALTER TABLE push_delivery ADD COLUMN client_id TEXT")
            conn.commit()

    def put(
        self,
        event_id: str,
        payload: Dict[str, Any],
        ts: float,
        client_id: Optional[str] = None,
    ) -> None:
        """Persist (or replace) a pending event and its recipient."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO push_delivery(event_id, client_id, ts, payload) "
                "VALUES (?, ?, ?, ?)",
                (event_id, client_id, ts, json.dumps(payload)),
            )
            conn.commit()

    def delete(self, event_id: str) -> None:
        """Remove an event once acknowledged or expired."""
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "DELETE FROM push_delivery WHERE event_id = ?", (event_id,)
            )
            conn.commit()

    def evict_expired(self, cutoff: float, keep: Optional[set] = None) -> int:
        """Delete events older than ``cutoff`` (unless still in ``keep``)."""
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT event_id FROM push_delivery WHERE ts < ?", (cutoff,)
            ).fetchall()
            purged = 0
            for (eid,) in rows:
                if keep and eid in keep:
                    continue
                conn.execute(
                    "DELETE FROM push_delivery WHERE event_id = ?", (eid,)
                )
                purged += 1
            conn.commit()
            return purged

    def load_all(self) -> List[tuple]:
        """Return all persisted ``(client_id, GatewayEvent)`` (for crash replay).

        ``client_id`` is ``None`` for rows persisted without a recipient (e.g.
        via ``store_message`` outside a tracked delivery, or legacy rows).
        """
        with self._lock, closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT client_id, payload FROM push_delivery ORDER BY ts ASC"
            ).fetchall()
        events: List[tuple] = []
        for client_id, payload in rows:
            try:
                events.append((client_id, GatewayEvent.from_dict(json.loads(payload))))
            except Exception:  # pragma: no cover - defensive
                continue
        return events


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
        *,
        sqlite_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self._gateway = gateway
        self._config = config
        self._lock = threading.RLock()
        # event_id -> GatewayEvent
        self._message_store: Dict[str, GatewayEvent] = {}
        # client_id -> {event_id -> PendingDelivery}
        self._pending_acks: Dict[str, Dict[str, PendingDelivery]] = {}
        self._sweeper_task: Optional[asyncio.Task] = None
        # Durable SQLite store (default backend). Zero external dependency, so
        # pending events survive a gateway restart and are re-delivered on
        # reconnect. Only initialised for the "sqlite" backend; "redis" mirrors
        # to the redis adapter and "memory" is the ephemeral opt-out.
        self._sqlite_store: Optional[SqlitePushStore] = None
        if config.store_backend == "sqlite":
            self._sqlite_store = SqlitePushStore(
                sqlite_path or _DEFAULT_SQLITE_PATH
            )
            self._replay_persisted()

    def _replay_persisted(self) -> None:
        """Reload persisted pending events after a restart into the cache.

        Both the event cache *and* the per-client pending-ack state are
        reconstructed so the durable at-least-once guarantee actually holds:
        the retry sweeper and reconnect redelivery both read ``_pending_acks``,
        so a persisted event with a known recipient is scheduled for retry
        immediately (``next_retry_at=now``) rather than being silently dropped.
        """
        if self._sqlite_store is None:
            return
        try:
            now = time.time()
            for client_id, event in self._sqlite_store.load_all():
                self._message_store[event.event_id] = event
                if not client_id:
                    continue
                self._pending_acks.setdefault(client_id, {})[event.event_id] = (
                    PendingDelivery(
                        event=event,
                        sent_at=event.timestamp or now,
                        retry_count=0,
                        next_retry_at=now,
                    )
                )
        except Exception as e:  # pragma: no cover - defensive
            logger.error("Failed to replay persisted push events: %s", e)

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

    async def store_message(
        self, event: GatewayEvent, client_id: Optional[str] = None,
    ) -> str:
        """Persist a message to the in-memory cache and durable backend.

        ``client_id`` is the intended recipient; it is persisted so the pending
        delivery can be reconstructed and redelivered after a restart.
        """
        with self._lock:
            self._message_store[event.event_id] = event

        # Durable by default: persist to the local SQLite store so pending
        # events survive a gateway restart with no external service.
        if self._sqlite_store is not None:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None,
                    self._sqlite_store.put,
                    event.event_id,
                    event.to_dict(),
                    event.timestamp,
                    client_id,
                )
            except Exception as e:
                logger.error("SQLite message store failed: %s", e)

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

        await self.store_message(event, client_id=client_id)

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
            # Drop from the in-memory cache too, unless another client is still
            # awaiting the same event.
            still_pending = any(
                event_id in pend for pend in self._pending_acks.values()
            )
            if not still_pending:
                self._message_store.pop(event_id, None)

        # Evict from the durable store so acked events are not reloaded and
        # redelivered after a restart.
        if self._sqlite_store is not None and not still_pending:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._sqlite_store.delete, event_id,
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.error("SQLite push store delete failed: %s", e)
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

        # Mirror the eviction to the durable store so it does not grow unbounded.
        if self._sqlite_store is not None:
            try:
                self._sqlite_store.evict_expired(cutoff, keep=pending_ids)
            except Exception as e:  # pragma: no cover - defensive
                logger.error("SQLite push store eviction failed: %s", e)

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
