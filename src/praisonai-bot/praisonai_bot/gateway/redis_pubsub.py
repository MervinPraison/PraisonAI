"""
Redis Pub/Sub Adapter for PraisonAI Push Service.

Bridges local gateway channel messaging to Redis for horizontal scaling.
Uses redis.asyncio for non-blocking operations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Coroutine, Dict, Optional

from praisonaiagents.gateway.config import RedisConfig

logger = logging.getLogger(__name__)


class RedisPubSubAdapter:
    """Async Redis adapter for cross-server push message distribution.

    Handles:
    - Pub/sub for channel messages across gateway instances
    - Presence storage in Redis hashes
    - Message persistence for delivery guarantees

    Redis is lazily imported at ``connect()`` time so the module can be
    imported without requiring the ``redis`` package.
    """

    # Owner identity recorded into the DegradedCapabilityRegistry so
    # ``gateway status`` / ``doctor`` can surface a cross-instance outage.
    _DEGRADED_OWNER_KIND = "route"
    _DEGRADED_OWNER_ID = "redis-pubsub"

    def __init__(
        self, config: RedisConfig, degraded_registry: Any = None,
    ) -> None:
        self._config = config
        self._server_id = str(uuid.uuid4())
        self._client: Any = None  # redis.asyncio.Redis
        self._pubsub: Any = None  # redis.asyncio.client.PubSub
        self._listener_task: Optional[asyncio.Task] = None
        self._subscriptions: Dict[str, Callable] = {}
        # Optional shared degraded-capability registry (Issue #3913). When a
        # cross-instance transport outage occurs the adapter records itself as a
        # degraded owner here so the outage becomes visible to the operator.
        self._degraded_registry = degraded_registry
        self._degraded = False
        # Count publish/presence writes silently dropped while disconnected so
        # the no-ops are surfaced rather than invisibly discarded.
        self._dropped_writes = 0

    # ------------------------------------------------------------------
    # Prefix helpers
    # ------------------------------------------------------------------

    def _key(self, *parts: str) -> str:
        return self._config.prefix + ":".join(parts)

    # ------------------------------------------------------------------
    # Degraded-state recording (Issue #3913)
    # ------------------------------------------------------------------

    def _mark_degraded(self, reason: str) -> None:
        """Record this transport as a degraded owner and count the outage.

        Redacted: only the exception string is surfaced (never connection URL
        or password) and it carries an actionable ``retry_hint`` so
        ``gateway status`` / ``doctor`` show the outage and its remedy.
        """
        self._degraded = True
        registry = self._degraded_registry
        if registry is None:
            return
        try:
            from praisonaiagents.gateway.degraded_state import DegradedOwner

            registry.mark(
                DegradedOwner(
                    owner_kind=self._DEGRADED_OWNER_KIND,
                    owner_id=self._DEGRADED_OWNER_ID,
                    state="stale",
                    reason=f"redis pub/sub disconnected: {reason}",
                    retry_hint="check Redis connectivity; see `praisonai gateway doctor`",
                )
            )
        except Exception as e:  # pragma: no cover - registry is best-effort
            logger.debug("Failed to mark redis-pubsub degraded: %s", e)

    def _clear_degraded(self) -> None:
        """Clear the degraded record on recovery. Idempotent."""
        if not self._degraded:
            return
        self._degraded = False
        registry = self._degraded_registry
        if registry is None:
            return
        try:
            registry.clear(self._DEGRADED_OWNER_KIND, self._DEGRADED_OWNER_ID)
        except Exception as e:  # pragma: no cover - registry is best-effort
            logger.debug("Failed to clear redis-pubsub degraded: %s", e)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Initialize the async Redis connection pool."""
        try:
            import redis.asyncio as aioredis
        except ImportError:
            raise ImportError(
                "redis[asyncio] is required for Redis push support. "
                "Install with: pip install redis"
            )

        if self._config.url:
            self._client = aioredis.from_url(
                self._config.url,
                max_connections=self._config.max_connections,
                decode_responses=True,
            )
        else:
            self._client = aioredis.Redis(
                host=self._config.host,
                port=self._config.port,
                db=self._config.db,
                password=self._config.password,
                max_connections=self._config.max_connections,
                decode_responses=True,
            )

        # Verify connection
        await self._client.ping()
        self._pubsub = self._client.pubsub()
        logger.info("Redis push adapter connected (server_id=%s)", self._server_id)

    async def disconnect(self) -> None:
        """Close Redis connections and stop the listener."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
            self._pubsub = None

        if self._client:
            await self._client.close()
            self._client = None

        logger.info("Redis push adapter disconnected")

    # ------------------------------------------------------------------
    # Channel pub/sub
    # ------------------------------------------------------------------

    async def publish(self, channel_name: str, event_dict: Dict[str, Any]) -> None:
        """Publish a serialized event to a Redis channel."""
        if self._client is None:
            self._dropped_writes += 1
            return
        payload = json.dumps({
            "server_id": self._server_id,
            "event": event_dict,
        })
        await self._client.publish(self._key("channel", channel_name), payload)

    async def subscribe(
        self,
        channel_name: str,
        callback: Callable[[Dict[str, Any]], Coroutine],
    ) -> None:
        """Subscribe to a Redis channel with an async callback."""
        if self._pubsub is None:
            return
        redis_channel = self._key("channel", channel_name)
        self._subscriptions[redis_channel] = callback
        await self._pubsub.subscribe(redis_channel)

        # Start the listener if not already running
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.ensure_future(self._run_listener())

    async def unsubscribe(self, channel_name: str) -> None:
        """Unsubscribe from a Redis channel."""
        if self._pubsub is None:
            return
        redis_channel = self._key("channel", channel_name)
        self._subscriptions.pop(redis_channel, None)
        await self._pubsub.unsubscribe(redis_channel)

    # ------------------------------------------------------------------
    # Presence storage (Redis hash)
    # ------------------------------------------------------------------

    async def set_presence(
        self, client_id: str, presence_dict: Dict[str, Any], ttl: int = 90,
    ) -> None:
        """Store presence in a Redis hash with TTL on individual keys."""
        if self._client is None:
            self._dropped_writes += 1
            return
        key = self._key("presence", client_id)
        await self._client.set(key, json.dumps(presence_dict), ex=ttl)

    async def get_presence(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Read presence from Redis."""
        if self._client is None:
            return None
        key = self._key("presence", client_id)
        raw = await self._client.get(key)
        if raw:
            return json.loads(raw)
        return None

    async def remove_presence(self, client_id: str) -> None:
        """Delete a presence entry."""
        if self._client is None:
            self._dropped_writes += 1
            return
        await self._client.delete(self._key("presence", client_id))

    async def get_all_presence(self) -> Dict[str, Dict[str, Any]]:
        """Read all presence entries (scan for presence keys)."""
        if self._client is None:
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        pattern = self._key("presence", "*")
        async for key in self._client.scan_iter(match=pattern, count=100):
            raw = await self._client.get(key)
            if raw:
                data = json.loads(raw)
                cid = data.get("client_id", key.split(":")[-1])
                result[cid] = data
        return result

    # ------------------------------------------------------------------
    # Message persistence (for delivery guarantees)
    # ------------------------------------------------------------------

    async def store_message(
        self, event_id: str, event_dict: Dict[str, Any], ttl: int = 86400,
    ) -> None:
        """Persist a message to Redis with TTL."""
        if self._client is None:
            self._dropped_writes += 1
            return
        key = self._key("msg", event_id)
        await self._client.set(key, json.dumps(event_dict), ex=ttl)

    async def get_message(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a stored message."""
        if self._client is None:
            return None
        raw = await self._client.get(self._key("msg", event_id))
        if raw:
            return json.loads(raw)
        return None

    async def delete_message(self, event_id: str) -> None:
        """Remove a stored message."""
        if self._client is None:
            self._dropped_writes += 1
            return
        await self._client.delete(self._key("msg", event_id))

    # ------------------------------------------------------------------
    # Health / status
    # ------------------------------------------------------------------

    @property
    def is_degraded(self) -> bool:
        """True while the cross-instance transport is disconnected."""
        return self._degraded

    @property
    def dropped_writes(self) -> int:
        """Count of publish/presence writes dropped while disconnected."""
        return self._dropped_writes

    # ------------------------------------------------------------------
    # Internal listener
    # ------------------------------------------------------------------

    async def _run_listener(self) -> None:
        """Background task that receives Redis pub/sub messages."""
        while True:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0,
                )
                if message is None:
                    await asyncio.sleep(0.01)
                    continue

                if message["type"] != "message":
                    continue

                channel = message["channel"]
                try:
                    payload = json.loads(message["data"])
                except (json.JSONDecodeError, TypeError):
                    continue

                # Skip messages from this server (avoid echo)
                if payload.get("server_id") == self._server_id:
                    continue

                callback = self._subscriptions.get(channel)
                if callback is not None:
                    event_data = payload.get("event", {})
                    try:
                        await callback(event_data)
                    except Exception as e:
                        logger.error("Redis listener callback error: %s", e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # A dropped Redis connection previously looped forever against
                # the same stale ``self._pubsub`` — logging errors while
                # delivering nothing and never surfacing the outage. Instead,
                # record the degradation and reconnect with bounded backoff,
                # re-subscribing every channel before resuming (Issue #3913).
                logger.error("Redis listener error: %s", e)
                # Drop the stale handles immediately so concurrent writes are
                # counted as dropped (rather than calling a closed client) and
                # ``redis_connected`` reports the outage while we reconnect
                # (Issue #3913). ``_reconnect`` best-effort-closes them again.
                self._client = None
                self._pubsub = None
                self._mark_degraded(str(e))
                recovered = await self._reconnect_with_backoff()
                if not recovered:
                    # Adapter was disconnected/cancelled while retrying; exit.
                    break
                self._clear_degraded()

    async def _reconnect_with_backoff(self) -> bool:
        """Re-establish the client + pub/sub and re-subscribe all channels.

        Uses exponential backoff capped at 30s. Returns ``True`` once the
        connection is restored, or ``False`` if the adapter has been
        disconnected (``disconnect()`` sets ``self._client`` to ``None`` and
        cancels the listener) so the caller stops looping.
        """
        delay = 1.0
        max_delay = 30.0
        while True:
            await asyncio.sleep(delay)
            # ``disconnect()`` cancels this task, but guard defensively so a
            # torn-down adapter never spins reconnecting.
            if self._listener_task is not None and self._listener_task.cancelled():
                return False
            try:
                await self._reconnect()
                logger.info(
                    "Redis push adapter reconnected (server_id=%s)", self._server_id
                )
                return True
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Redis reconnect failed, retrying: %s", e)
                delay = min(delay * 2, max_delay)

    async def _reconnect(self) -> None:
        """Rebuild the client + pub/sub handle and re-subscribe channels."""
        # Best-effort teardown of the stale handles before reconnecting.
        old_pubsub, old_client = self._pubsub, self._client
        self._pubsub = None
        if old_pubsub is not None:
            try:
                await old_pubsub.close()
            except Exception:
                pass
        if old_client is not None:
            try:
                await old_client.close()
            except Exception:
                pass

        await self.connect()
        # Re-subscribe every channel we were tracking onto the fresh pub/sub.
        channels = list(self._subscriptions.keys())
        if channels and self._pubsub is not None:
            await self._pubsub.subscribe(*channels)
