"""
Per-user session isolation for PraisonAI bots.

Bots share a single Agent instance but each user needs independent
chat history.  BotSessionManager swaps the agent's ``chat_history``
before and after every call so conversations never leak between users.

When a ``store`` (any ``SessionStoreProtocol`` implementation) is
provided, sessions are **persisted to disk** and survive restarts.
Without a store, behaviour is identical to the original in-memory mode.

Thread-safety: an ``asyncio.Lock`` per user serialises concurrent
calls from the same user; different users run in parallel.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from praisonaiagents import Agent

logger = logging.getLogger(__name__)


class BotSessionManager:
    """Lightweight per-user session store for bot agents.

    Usage inside a bot message handler::

        # In-memory only (backward compatible)
        session_mgr = BotSessionManager()

        # With persistent store (recommended)
        from praisonaiagents.session import get_default_session_store
        session_mgr = BotSessionManager(
            store=get_default_session_store(),
            platform="telegram",
        )

        response = await session_mgr.chat(agent, user_id, text)

    The manager:
    1. Saves the agent's current ``chat_history``.
    2. Loads the user's history from the persistent store (or in-memory cache).
    3. Calls ``agent.chat(prompt)`` (via ``run_in_executor``).
    4. Persists the updated history back to the store.
    5. Restores the agent's original history.

    ``/new`` command → call ``session_mgr.reset(user_id)``.

    Multi-agent safety: Uses a per-Agent lock to serialise history
    swaps when the same Agent instance is shared across multiple bots
    (e.g. gateway multi-bot mode).
    """

    def __init__(
        self,
        max_history: int = 100,
        store: Optional[Any] = None,
        platform: str = "",
        identity_resolver: Optional[Any] = None,
    ) -> None:
        self._histories: Dict[str, List[Dict[str, Any]]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._agent_locks: Dict[int, asyncio.Lock] = {}
        self._max_history = max_history
        self._store = store
        self._platform = platform
        self._last_active: Dict[str, float] = {}
        # W1: optional cross-platform identity resolver. When set, the
        # session key is the resolver-returned unified user id, so the
        # same human pinging from multiple platforms shares one history.
        self._identity_resolver = identity_resolver

    def _storage_key(self, user_id: str) -> str:
        """Resolve a raw platform user id to the in-memory/store key.

        With an identity resolver this is the unified user id; without
        one, behaviour is unchanged (raw ``user_id``).
        """
        if self._identity_resolver is not None and self._platform:
            try:
                return self._identity_resolver.resolve(self._platform, user_id)
            except Exception as e:  # pragma: no cover — defensive
                logger.warning("identity resolver failed: %s", e)
        return user_id

    def _persist_key(self, storage_key: str) -> str:
        """Derive the persistent-store key from an in-memory storage key.

        With a resolver, ``storage_key`` is already the unified user id
        and is used directly. Without a resolver, the legacy
        ``bot_{platform}_{user_id}`` prefix is preserved for back-compat.
        """
        if self._identity_resolver is not None and self._platform:
            return storage_key
        prefix = f"bot_{self._platform}" if self._platform else "bot"
        return f"{prefix}_{storage_key}"

    def _session_key(self, user_id: str) -> str:
        """Persistent-store key for a raw platform user id (back-compat API)."""
        return self._persist_key(self._storage_key(user_id))

    def _get_lock(self, user_id: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for *user_id* (storage-keyed)."""
        key = self._storage_key(user_id)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _get_agent_lock(self, agent: "Agent") -> asyncio.Lock:
        """Get or create a lock for the *agent* instance (by id)."""
        agent_id = id(agent)
        if agent_id not in self._agent_locks:
            self._agent_locks[agent_id] = asyncio.Lock()
        return self._agent_locks[agent_id]

    def _load_history(self, user_id: str) -> List[Dict[str, Any]]:
        """Load user history from store (if available) or in-memory cache."""
        if self._store is not None:
            key = self._session_key(user_id)
            try:
                history = self._store.get_chat_history(key)
                if history:
                    return list(history)
            except Exception as e:
                logger.warning("Failed to load session from store: %s", e)
        return list(self._histories.get(self._storage_key(user_id), []))

    def _save_history(
        self, user_id: str, history: List[Dict[str, Any]]
    ) -> None:
        """Save user history to store (if available) and in-memory cache."""
        if self._max_history > 0 and len(history) > self._max_history:
            history = history[-self._max_history:]

        # Always update in-memory cache (keyed by storage key)
        self._histories[self._storage_key(user_id)] = history

        if self._store is not None:
            key = self._session_key(user_id)
            try:
                # Clear existing and re-write (atomic update)
                self._store.clear_session(key)
                for msg in history:
                    self._store.add_message(
                        key,
                        msg.get("role", "user"),
                        msg.get("content", ""),
                        msg.get("metadata"),
                    )
            except Exception as e:
                logger.warning("Failed to persist session to store: %s", e)

    async def chat(
        self,
        agent: "Agent",
        user_id: str,
        prompt: str,
        chat_id: str = "",
        thread_id: str = "",
        user_name: str = "",
    ) -> str:
        """Run ``agent.chat(prompt)`` with *user_id*-scoped history.

        The call is wrapped in ``run_in_executor`` so the sync LLM
        round-trip never blocks the event loop.

        Uses both a per-user lock (serialise same user) and a per-agent
        lock (prevent concurrent history swaps on a shared Agent).
        """
        self._last_active[self._storage_key(user_id)] = time.monotonic()
        user_lock = self._get_lock(user_id)
        agent_lock = self._get_agent_lock(agent)

        # W1: set task-local session context so any tool the agent
        # invokes can read platform / chat / user metadata without
        # relying on os.environ globals.
        ctx_token = None
        try:
            from praisonaiagents.session.context import (
                set_session_context as _set_ctx,
                clear_session_context as _clear_ctx,
            )
            ctx_token = _set_ctx(
                platform=self._platform,
                chat_id=chat_id,
                thread_id=thread_id,
                user_id=user_id,
                user_name=user_name,
                unified_user_id=self._storage_key(user_id),
            )
        except Exception:  # pragma: no cover — defensive
            _clear_ctx = None  # type: ignore[assignment]

        async with user_lock:
            # Load history (may hit disk via run_in_executor for async safety)
            loop = asyncio.get_running_loop()
            user_history = await loop.run_in_executor(
                None, self._load_history, user_id
            )

            # W1 robustness: hold ``agent_lock`` across the FULL LLM call
            # (not only the history swap) so concurrent users on a shared
            # Agent instance never observe each other's chat_history.
            # Throughput on a shared agent is then bounded by the LLM's
            # serial latency — this is correct: a single Agent's
            # ``chat_history`` is mutable and cannot be safely interleaved.
            async with agent_lock:
                saved_history = agent.chat_history
                agent.chat_history = user_history
                try:
                    # Copy current task's contextvars (incl. SessionContext)
                    # into the worker thread so tools the agent invokes can
                    # read platform/user metadata.
                    import contextvars
                    _ctx = contextvars.copy_context()
                    response = await loop.run_in_executor(
                        None, _ctx.run, agent.chat, prompt
                    )
                    # Capture updated history before restoring caller's.
                    updated_history = agent.chat_history
                finally:
                    agent.chat_history = saved_history

            # Persist outside the agent_lock — it's per-user and the agent
            # is no longer touched.
            await loop.run_in_executor(
                None, self._save_history, user_id, updated_history
            )

            # Clear task-local session context.
            if ctx_token is not None and _clear_ctx is not None:
                try:
                    _clear_ctx(ctx_token)
                except Exception:
                    pass

            return response

    def reap_stale(self, max_age_seconds: int) -> int:
        """Remove sessions older than *max_age_seconds*.  Returns count reaped.

        Call this periodically or lazily (e.g. on each chat() call) to
        auto-clean inactive sessions and free memory.
        """
        if max_age_seconds <= 0:
            return 0
        now = time.monotonic()
        stale = [
            uid for uid, ts in self._last_active.items()
            if (now - ts) > max_age_seconds
        ]
        for storage_key in stale:
            self._histories.pop(storage_key, None)
            self._last_active.pop(storage_key, None)
            self._locks.pop(storage_key, None)
            if self._store is not None:
                key = self._persist_key(storage_key)
                try:
                    self._store.clear_session(key)
                except Exception as e:
                    logger.warning("Failed to reap session %s: %s", key, e)
        if stale:
            logger.debug("BotSessionManager: reaped %d stale sessions", len(stale))
        return len(stale)

    def reset(self, user_id: str) -> bool:
        """Clear a user's session history.  Returns True if it existed."""
        key = self._storage_key(user_id)
        existed = key in self._histories
        self._histories.pop(key, None)
        self._last_active.pop(key, None)
        self._locks.pop(key, None)

        if self._store is not None:
            key = self._session_key(user_id)
            try:
                self._store.clear_session(key)
            except Exception as e:
                logger.warning("Failed to clear session in store: %s", e)

        return existed

    def reset_all(self) -> int:
        """Clear all user sessions.  Returns the count cleared."""
        count = len(self._histories)

        if self._store is not None:
            for storage_key in list(self._histories.keys()):
                key = self._persist_key(storage_key)
                try:
                    self._store.clear_session(key)
                except Exception as e:
                    logger.warning("Failed to clear session %s: %s", key, e)

        self._histories.clear()
        return count

    @property
    def active_sessions(self) -> int:
        """Number of users with stored history."""
        return len(self._histories)

    def get_user_ids(self) -> List[str]:
        """List user IDs with active sessions."""
        return list(self._histories.keys())
