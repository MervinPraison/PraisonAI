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
import weakref
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from .._lockmap import LockMap

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
        dlq: Optional[Any] = None,
        identity_resolver: Optional[Any] = None,
        ingress_journal: Optional[Any] = None,
        run_control: Optional[Any] = None,
    ) -> None:
        self._histories: Dict[str, List[Dict[str, Any]]] = {}
        self._locks = LockMap()
        self._agent_locks: "weakref.WeakKeyDictionary[Any, asyncio.Lock]" = weakref.WeakKeyDictionary()
        self._max_history = max_history
        self._store = store
        self._platform = platform
        self._last_active: Dict[str, float] = {}
        # N4: optional inbound DLQ — when set, failed agent.chat() calls
        # are persisted for later replay. Default ``None`` preserves
        # legacy behaviour (exception bubbles up untouched).
        self._dlq = dlq
        # W1: optional cross-platform identity resolver. When set, the
        # session key is the resolver-returned unified user id, so the
        # same human pinging from multiple platforms shares one history.
        self._identity_resolver = identity_resolver
        # Ingress journal: optional durable message processing with dedup.
        # When set, messages are journaled before agent processing for
        # crash recovery and webhook redelivery protection.
        self._ingress_journal = ingress_journal
        self._last_journal_key = None  # Store key for delayed completion
        # Run control for in-flight message handling
        self._run_control = run_control

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
        return self._locks.get(key)

    def _get_agent_lock(self, agent: "Agent") -> asyncio.Lock:
        """Get or create a lock for the *agent* instance (using WeakKeyDictionary)."""
        lock = self._agent_locks.get(agent)
        if lock is None:
            lock = asyncio.Lock()
            self._agent_locks[agent] = lock
        return lock

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
                if hasattr(self._store, "set_chat_history"):
                    self._store.set_chat_history(key, history)
                else:
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
        message_id: str = "",
        account: str = "",
        stream_callback: Optional[Any] = None,
    ) -> str:
        """Run ``agent.chat(prompt)`` with *user_id*-scoped history.

        The call is wrapped in ``run_in_executor`` so the sync LLM
        round-trip never blocks the event loop.

        Uses both a per-user lock (serialise same user) and a per-agent
        lock (prevent concurrent history swaps on a shared Agent).

        Args:
            stream_callback: Optional async callback for streaming events.
                            If provided, will be passed to agent.astart() for streaming.

        N4 — Inbound DLQ: if a ``dlq`` was passed to ``__init__`` and
        ``agent.chat()`` raises, the failing message is persisted to
        the dead-letter queue **before** the exception is re-raised.
        This makes the error visible to the caller (so the bot adapter
        can log / show the user a friendly message) while preserving
        the message for later replay.
        
        Ingress Journal: if an ``ingress_journal`` was passed to ``__init__``
        and ``message_id`` is provided, the message is journaled with deduplication
        and claim/complete semantics for crash-safe, exactly-once processing.
        """
        # Handle ingress journaling for durable message processing
        journal_key = None
        if self._ingress_journal is not None and message_id:
            payload = {
                "user_id": user_id,
                "prompt": prompt,
                "chat_id": chat_id,
                "thread_id": thread_id,
                "user_name": user_name,
            }
            journal_key = self._ingress_journal.receive(
                platform=self._platform or "unknown",
                account=account or "default",
                channel_id=chat_id or user_id,
                message_id=message_id,
                payload=payload
            )
            if journal_key is None:
                # Duplicate message - return empty response
                return ""
                
        self._last_active[self._storage_key(user_id)] = time.monotonic()
        user_lock = self._get_lock(user_id)
        agent_lock = self._get_agent_lock(agent)

        # W1: set task-local session context so any tool the agent
        # invokes can read platform / chat / user metadata without
        # relying on os.environ globals.
        ctx_token = None
        _clear_ctx = None
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

        try:
            # Claim journal entry if we have one
            if journal_key is not None:
                claim_ctx = self._ingress_journal.aclaim(journal_key)
                await claim_ctx.__aenter__()
            else:
                claim_ctx = None
                
            try:
                async with user_lock:
                    # Load history (may hit disk via run_in_executor for async safety)
                    loop = asyncio.get_running_loop()
                    user_history = await loop.run_in_executor(
                        None, self._load_history, user_id
                    )

                    # W1 robustness: hold ``agent_lock`` across the FULL LLM call
                    # (not only the history swap) so concurrent users on a shared
                    # Agent instance never observe each other's chat_history.
                    async with agent_lock:
                        saved_history = agent.chat_history
                        agent.chat_history = user_history
                        try:
                            # Choose streaming vs non-streaming path based on callback
                            if stream_callback:
                                # Streaming path: use agent.astart() with stream callback
                                response = await agent.astart(prompt, stream_callback=stream_callback)
                                # Handle AutonomyResult when autonomy is enabled in caller mode
                                if hasattr(response, 'output'):
                                    response = response.output
                            else:
                                # Legacy non-streaming path: use agent.chat() in executor
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
                        except Exception as exc:
                            # N4: persist the failed inbound message before bubbling.
                            if self._dlq is not None:
                                try:
                                    await loop.run_in_executor(
                                        None,
                                        lambda: self._dlq.enqueue(
                                            platform=self._platform,
                                            user_id=user_id,
                                            prompt=prompt,
                                            error=f"{type(exc).__name__}: {exc}",
                                            chat_id=chat_id,
                                            thread_id=thread_id,
                                            user_name=user_name,
                                        )
                                    )
                                except Exception as dlq_exc:  # pragma: no cover — defensive
                                    logger.error(
                                        "Failed to enqueue inbound DLQ entry: %s", dlq_exc
                                    )
                            agent.chat_history = saved_history
                            raise
                        finally:
                            agent.chat_history = saved_history

                    # Persist outside the agent_lock — it's per-user and the agent
                    # is no longer touched.
                    await loop.run_in_executor(
                        None, self._save_history, user_id, updated_history
                    )

                    # Store journal key in instance for later completion after message delivery
                    self._last_journal_key = journal_key
                    
                    return response
                    
            except Exception as e:
                # Handle any remaining exceptions and ensure claim is released 
                if claim_ctx is not None:
                    await claim_ctx.__aexit__(type(e), e, e.__traceback__)
                raise
            else:
                # Clean exit - no exception
                if claim_ctx is not None:
                    await claim_ctx.__aexit__(None, None, None)
        finally:
            # Always clear task-local session context, even if an exception occurred.
            if ctx_token is not None and _clear_ctx is not None:
                try:
                    _clear_ctx(ctx_token)
                except Exception as e:
                    logger.debug("Failed to clear task-local session context for ctx_token=%r: %s", ctx_token, e)

    async def chat_with_run_control(
        self,
        agent: "Agent",
        user_id: str,
        prompt: str,
        chat_id: str = "",
        thread_id: str = "",
        user_name: str = "",
    ) -> Dict[str, Any]:
        """Run agent.chat() with run control for better UX during long operations.
        
        This method integrates with SessionRunControl to provide:
        - Busy acknowledgment for mid-run messages
        - Pending message slot for follow-ups
        - Interrupt support via /stop command
        - Optional steering for real-time guidance
        
        Returns:
            Dict with 'response' (str) and 'metadata' (dict) keys.
            Metadata includes run control information.
        """
        if self._run_control is None:
            # Fall back to regular chat if no run control
            response = await self.chat(agent, user_id, prompt, chat_id, thread_id, user_name)
            return {"response": response, "metadata": {"run_control": False}}
        
        try:
            # Import here to avoid circular dependency
            from ._run_control import RunDecision
        except ImportError:
            # Fall back if run control not available
            response = await self.chat(agent, user_id, prompt, chat_id, thread_id, user_name)
            return {"response": response, "metadata": {"run_control": False, "error": "run_control_unavailable"}}
        
        # Submit message to run control
        decision = await self._run_control.submit(user_id, prompt)
        
        if decision in (RunDecision.QUEUED, RunDecision.MERGED):
            # Message was queued or merged, return acknowledgment
            ack_msg = await self._run_control.get_busy_ack_message(user_id, decision)
            return {
                "response": ack_msg,
                "metadata": {
                    "run_control": True,
                    "decision": decision.value,
                    "queued": True
                }
            }
        
        # We're running now (RUN_NOW or INTERRUPTED)
        run_generation = None
        interrupt_controller = None
        
        if decision == RunDecision.RUN_NOW:
            # Get the interrupt controller for this run
            interrupt_controller = self._run_control.get_interrupt_controller(user_id)
        elif decision == RunDecision.INTERRUPTED:
            # Previous run was cancelled, get new controller
            interrupt_controller = self._run_control.get_interrupt_controller(user_id)
        
        # Get current run generation for race protection
        status = self._run_control.get_run_status(user_id)
        run_generation = status.get("run_generation")
        
        try:
            # Attach interrupt controller to agent if available
            original_interrupt = None
            if interrupt_controller and hasattr(agent, '_interrupt_controller'):
                original_interrupt = getattr(agent, '_interrupt_controller', None)
                agent._interrupt_controller = interrupt_controller
            
            # Run the chat with the existing method
            response = await self.chat(agent, user_id, prompt, chat_id, thread_id, user_name)
            
            # Check for pending messages to process next
            pending = self._run_control.next_pending(user_id)
            pending_info = {}
            if pending:
                pending_info = {
                    "next_pending": pending[:100] + "..." if len(pending) > 100 else pending
                }
            
            return {
                "response": response,
                "metadata": {
                    "run_control": True,
                    "decision": decision.value,
                    "completed": True,
                    "run_generation": run_generation,
                    **pending_info
                }
            }
            
        except Exception as e:
            # Handle interruption specifically
            if interrupt_controller and interrupt_controller.is_set():
                reason = interrupt_controller.reason or "unknown"
                return {
                    "response": f"⚠️ Task cancelled: {reason}",
                    "metadata": {
                        "run_control": True,
                        "decision": decision.value,
                        "interrupted": True,
                        "reason": reason,
                        "run_generation": run_generation
                    }
                }
            else:
                # Re-raise other exceptions
                raise
                
        finally:
            # Restore original interrupt controller
            if interrupt_controller and hasattr(agent, '_interrupt_controller'):
                if original_interrupt is not None:
                    agent._interrupt_controller = original_interrupt
                else:
                    agent._interrupt_controller = None
            
            # Mark run as finished
            if run_generation is not None:
                await self._run_control.finish_run(user_id, run_generation)

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
            self._locks.drop(storage_key)
            if self._store is not None:
                key = self._persist_key(storage_key)
                try:
                    self._store.clear_session(key)
                except Exception as e:
                    logger.warning("Failed to reap session %s: %s", key, e)
        if stale:
            logger.debug("BotSessionManager: reaped %d stale sessions", len(stale))
        return len(stale)

    def complete_last_journal_entry(self) -> bool:
        """Complete the last journal entry if one exists.
        
        Call this after successfully delivering a message to the platform
        to ensure the journal entry is marked as completed.
        
        Returns True if an entry was completed, False if no entry was pending.
        """
        if self._last_journal_key is not None and self._ingress_journal is not None:
            try:
                self._ingress_journal.complete(self._last_journal_key)
                self._last_journal_key = None
                return True
            except Exception as e:
                logger.warning("Failed to complete journal entry: %s", e)
        return False

    def reset(self, user_id: str) -> bool:
        """Clear a user's session history.  Returns True if it existed."""
        storage_key = self._storage_key(user_id)
        existed = storage_key in self._histories
        self._histories.pop(storage_key, None)
        self._last_active.pop(storage_key, None)
        self._locks.drop(storage_key)

        if self._store is not None:
            persist_key = self._session_key(user_id)
            try:
                self._store.clear_session(persist_key)
            except Exception as e:
                logger.warning("Failed to clear session in store: %s", e)

        return existed

    def _add_mirror_entry_sync(self, user_id: str, entry: dict) -> bool:
        """Thread-safe method to add a mirror entry to user's history.
        
        This method coordinates with the asyncio locks used by chat() 
        to prevent race conditions. Called by mirror_to_session().
        
        Args:
            user_id: Raw platform user id
            entry: Mirror entry dict to append to history
            
        Returns:
            bool: True on success, False on failure
        """
        import asyncio
        
        def _sync_add_entry():
            # Get the event loop that owns the asyncio locks
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No event loop running - we need to use threading synchronization
                # This happens when called from sync contexts like cron jobs
                storage_key = self._storage_key(user_id)
                self._last_active[storage_key] = time.monotonic()
                
                # Create a temporary threading lock for this user to prevent concurrent
                # access to the same user's history from multiple sync threads
                import threading
                user_sync_lock = getattr(self, '_user_sync_locks', None)
                if user_sync_lock is None:
                    self._user_sync_locks = {}
                    user_sync_lock = self._user_sync_locks
                
                if storage_key not in user_sync_lock:
                    user_sync_lock[storage_key] = threading.Lock()
                
                with user_sync_lock[storage_key]:
                    history = list(self._load_history(user_id))
                    history.append(entry)
                    self._save_history(user_id, history)
                return True
                
            # There's an event loop - we need to coordinate with asyncio locks
            # This is more complex but necessary for thread safety
            future = asyncio.run_coroutine_threadsafe(
                self._add_mirror_entry_async(user_id, entry), loop
            )
            return future.result(timeout=10.0)  # 10 second timeout
        
        try:
            return _sync_add_entry()
        except Exception as e:
            logger.warning("_add_mirror_entry_sync failed: %s", e)
            return False
    
    async def _add_mirror_entry_async(self, user_id: str, entry: dict) -> bool:
        """Async helper for _add_mirror_entry_sync."""
        try:
            storage_key = self._storage_key(user_id) 
            self._last_active[storage_key] = time.monotonic()
            
            # Use the same per-user lock that chat() uses
            user_lock = self._get_lock(user_id)
            async with user_lock:
                # Load history (may hit disk via run_in_executor for async safety)
                loop = asyncio.get_running_loop()
                history = await loop.run_in_executor(
                    None, self._load_history, user_id
                )
                history = list(history)  # Ensure it's mutable
                history.append(entry)
                
                # Save updated history
                await loop.run_in_executor(
                    None, self._save_history, user_id, history
                )
            return True
        except Exception as e:
            logger.warning("_add_mirror_entry_async failed: %s", e)
            return False

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
