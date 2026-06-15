"""Per-key asyncio.Lock map with bounded LRU eviction and optional TTL.

Use this anywhere you need 'a lock per (user_id|chat_id|key)' instead of
re-implementing the dict-of-Lock pattern.
"""
from __future__ import annotations
import asyncio
import time
from collections import OrderedDict
from typing import Hashable


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
        self._locks: "OrderedDict[Hashable, tuple[asyncio.Lock, float]]" = OrderedDict()
        self._max = max_entries
        self._ttl = ttl_seconds

    def get(self, key: Hashable) -> asyncio.Lock:
        """Get or create a lock for the given key.
        
        Args:
            key: The key to get a lock for
            
        Returns:
            asyncio.Lock for the key
        """
        now = time.monotonic()
        entry = self._locks.get(key)
        if entry is not None:
            lock, _ = entry
            # Move to end (most recently used) and update timestamp
            self._locks.move_to_end(key)
            self._locks[key] = (lock, now)
            return lock
        
        # Create new lock + insert + LRU/TTL evict
        lock = asyncio.Lock()
        self._locks[key] = (lock, now)
        self._evict_stale(now)
        return lock

    def _evict_stale(self, now: float) -> None:
        """Evict expired and excess entries."""
        # Expire by TTL (only if not currently locked)
        expired = [
            k for k, (lock, ts) in self._locks.items()
            if (now - ts) > self._ttl and not lock.locked()
        ]
        for k in expired:
            self._locks.pop(k, None)
        
        # Cap by LRU (don't evict locks currently held)
        while len(self._locks) > self._max:
            k, (lock, _) = next(iter(self._locks.items()))
            if lock.locked():
                # Don't evict locks currently held; bump them to the end
                self._locks.move_to_end(k)
                # Continue trying to evict other unlocked entries
                continue
            self._locks.popitem(last=False)
            break

    def drop(self, key: Hashable) -> None:
        """Manually remove a lock for the given key."""
        self._locks.pop(key, None)

    def size(self) -> int:
        """Return current number of cached locks."""
        return len(self._locks)