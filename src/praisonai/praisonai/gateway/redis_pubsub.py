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

    def __init__(self, config: RedisConfig) -> None:
        self._config = config
        self._server_id = str(uuid.uuid4())
        self._client: Any = None  # redis.asyncio.Redis
        self._pubsub: Any = None  # redis.asyncio.client.PubSub
        self._listener_task: Optional[asyncio.Task] = None
        self._subscriptions: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Prefix helpers
    # ------------------------------------------------------------------

    def _key(self, *parts: str) -> str:
        return self._config.prefix + ":".join(parts)

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
            return
        await self._client.delete(self._key("msg", event_id))

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
                logger.error("Redis listener error: %s", e)
                await asyncio.sleep(1)
