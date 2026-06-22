"""Per-key asyncio.Lock map with bounded LRU eviction and optional TTL.

Use this anywhere you need 'a lock per (user_id|chat_id|key)' instead of
re-implementing the dict-of-Lock pattern.
"""
from __future__ import annotations
import asyncio
import time
import weakref
from collections import OrderedDict
from typing import Hashable, Dict


class LockMap:
    """Asyncio-safe per-key asyncio.Lock map with automatic cleanup.
    
    Provides a lock per key with LRU eviction and TTL-based cleanup to prevent
    unbounded memory growth in long-running applications.
    
    Note: Safe for use within a single asyncio event loop (cooperative
    multitasking means no interleaving between non-awaited calls), but NOT
    safe for concurrent access from multiple OS threads.
    """

    def __init__(self, *, max_entries: int = 10_000, ttl_seconds: float = 3600.0):
        """Initialize LockMap with bounds.
        
        Args:
            max_entries: Maximum number of locks to cache (LRU eviction)
            ttl_seconds: Time-to-live for unused locks in seconds
        """
        # Bucket locks by event loop to avoid cross-loop issues
        self._buckets: Dict[int, "OrderedDict[Hashable, tuple[asyncio.Lock, float]]"] = {}
        self._loop_refs: Dict[int, weakref.ref] = {}
        self._max = max_entries
        self._ttl = ttl_seconds

    def get(self, key: Hashable) -> asyncio.Lock:
        """Get or create a lock for the given key.
        
        Args:
            key: The key to get a lock for
            
        Returns:
            asyncio.Lock for the key
        """
        # Get the current running loop
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        
        # Clean up dead loops
        self._cleanup_dead_loops()
        
        # Get or create bucket for this loop
        if loop_id not in self._buckets:
            self._buckets[loop_id] = OrderedDict()
            self._loop_refs[loop_id] = weakref.ref(loop)
        
        bucket = self._buckets[loop_id]
        now = time.monotonic()
        
        entry = bucket.get(key)
        if entry is not None:
            lock, _ = entry
            # Move to end (most recently used) and update timestamp
            bucket.move_to_end(key)
            bucket[key] = (lock, now)
            return lock
        
        # Create new lock + insert + LRU/TTL evict
        lock = asyncio.Lock()
        bucket[key] = (lock, now)
        self._evict_stale_from_bucket(bucket, now)
        return lock

    def _evict_stale_from_bucket(self, bucket: "OrderedDict", now: float) -> None:
        """Evict expired and excess entries from a bucket."""
        # Expire by TTL (only if not currently locked)
        expired = [
            k for k, (lock, ts) in bucket.items()
            if (now - ts) > self._ttl and not lock.locked()
        ]
        for k in expired:
            bucket.pop(k, None)
        
        # Cap by LRU (don't evict locks currently held)
        seen = set()
        while len(bucket) > self._max:
            k, (lock, _) = next(iter(bucket.items()))
            if k in seen:
                # All remaining locks are held; give up to avoid infinite loop
                break
            if lock.locked():
                # Don't evict locks currently held; bump them to the end
                bucket.move_to_end(k)
                seen.add(k)
                # Continue trying to evict other unlocked entries
                continue
            bucket.popitem(last=False)
            break
    
    def _cleanup_dead_loops(self) -> None:
        """Remove buckets for event loops that no longer exist."""
        dead_loops = []
        for loop_id, ref in self._loop_refs.items():
            loop = ref()
            if loop is None or loop.is_closed():
                dead_loops.append(loop_id)
        
        for loop_id in dead_loops:
            del self._loop_refs[loop_id]
            if loop_id in self._buckets:
                del self._buckets[loop_id]

    def drop(self, key: Hashable) -> None:
        """Manually remove a lock for the given key."""
        # Get the current running loop
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        if loop_id in self._buckets:
            self._buckets[loop_id].pop(key, None)

    def size(self) -> int:
        """Return current number of cached locks across all buckets."""
        return sum(len(bucket) for bucket in self._buckets.values())