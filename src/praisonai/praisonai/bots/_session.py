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
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from .._lockmap import LockMap
from ._reset_policy import SessionResetPolicy

if TYPE_CHECKING:
    from praisonaiagents import Agent

logger = logging.getLogger(__name__)


class BotRunTimeout(Exception):
    """Exception raised when a bot run times out."""
    pass


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
        run_timeout: float = 300.0,  # 5 minutes default timeout
        reset_policy: Optional[SessionResetPolicy] = None,
        channel_directory: Optional[Any] = None,
        inject_session_context: bool = True,
        compaction: Optional[Any] = None,
    ) -> None:
        self._histories: Dict[str, List[Dict[str, Any]]] = {}
        self._locks = LockMap()
        self._agent_locks: "weakref.WeakKeyDictionary[Any, asyncio.Lock]" = weakref.WeakKeyDictionary()
        self._max_history = max_history
        self._store = store
        self._platform = platform
        self._last_active: Dict[str, float] = {}
        self._last_reset: Dict[str, float] = {}  # Track last reset time per user
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
        # Platform awareness: channel directory and injection flag
        self._channel_directory = channel_directory
        self._inject_session_context = inject_session_context
        self._last_journal_key = None  # Store key for delayed completion
        # Run control for in-flight message handling
        self._run_control = run_control
        # Run timeout and active run tracking for cancellation support
        self._run_timeout = run_timeout
        self._active_runs: Dict[str, Any] = {}  # user_id -> InterruptController
        # Session reset policy for automatic lifecycle management
        self._reset_policy = reset_policy or SessionResetPolicy(mode="none")
        # Track storage keys we've already fired SESSION_START for, so the
        # hook fires exactly once per session lifetime (until reset).
        self._seen_sessions: set = set()
        # Per-session hook context captured when SESSION_START fires, keyed by
        # storage_key: (HookRunner, agent_name). Lets any clear path emit
        # SESSION_END with the *correct* runner/agent — never another user's.
        self._session_hook_context: Dict[str, Any] = {}
        # Optional history compaction. When configured, older turns are
        # summarised (instead of hard-truncated) once history exceeds the
        # configured budget, so long-lived conversations retain context.
        # Default ``None`` preserves the legacy tail-slice truncation.
        #
        # We store only the *config* and build a fresh ``ContextCompactor``
        # per ``_save_history`` call. The core compactor carries mutable
        # per-conversation state (iterative summary, anti-thrashing streaks),
        # so a single shared instance would leak context across users and
        # race under concurrent saves on the executor thread pool.
        self._compaction_config = compaction
        # Probe availability once so behaviour/tests can detect whether
        # compaction is active without sharing the stateful instance.
        self._compaction_enabled = self._build_compactor(compaction) is not None

    @staticmethod
    def _build_compactor(compaction: Optional[Any]) -> Optional[Any]:
        """Lazily construct a ``ContextCompactor`` from a compaction config.

        Accepts a ``SessionCompactionConfigSchema`` (or any object/dict with
        the same fields). Returns ``None`` when compaction is disabled or the
        core compaction engine is unavailable, in which case the manager falls
        back to the legacy tail-slice truncation.
        """
        if compaction is None:
            return None

        # Normalise to attribute access from either a pydantic model or dict.
        def _get(name, default=None):
            if isinstance(compaction, dict):
                return compaction.get(name, default)
            return getattr(compaction, name, default)

        if not _get("enabled", False):
            return None

        strategy = _get("strategy", "summarize")
        max_tokens = _get("max_tokens", None)
        max_messages = _get("max_messages", 100)
        keep_recent = _get("keep_recent", 10)

        try:
            from praisonaiagents.compaction import ContextCompactor, CompactionStrategy
        except Exception as e:  # pragma: no cover — optional dependency
            logger.warning(
                "Compaction requested but praisonaiagents.compaction is unavailable: %s",
                e,
            )
            return None

        try:
            strategy_enum = CompactionStrategy(strategy)
        except ValueError:
            logger.warning(
                "Unknown compaction strategy %r; falling back to 'summarize'", strategy
            )
            strategy_enum = CompactionStrategy.SUMMARIZE

        # Message-count budgets are translated to a rough token budget so the
        # core token-based compactor triggers at the intended history length.
        # ~4 chars/token and an estimated ~80 tokens/message keeps this simple
        # and avoids touching the core engine. NOTE: this is only an estimate —
        # actual compaction depth varies with message size. The caller keeps
        # ``max_history`` as a hard upper bound so short-message bots never grow
        # in-memory history unbounded before the token threshold is reached.
        if max_tokens is None:
            max_tokens = max(1, int(max_messages) * 80)

        try:
            return ContextCompactor(
                max_tokens=int(max_tokens),
                strategy=strategy_enum,
                preserve_recent=int(keep_recent),
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("Failed to build ContextCompactor: %s", e)
            return None

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

    def _maybe_fire_session_start(self, agent: "Agent", user_id: str) -> None:
        """Fire SESSION_START once per session lifetime (no-op without hooks)."""
        storage_key = self._storage_key(user_id)
        if storage_key in self._seen_sessions:
            return
        self._seen_sessions.add(storage_key)
        try:
            from ._protocol_mixin import fire_session_start, _resolve_runner_from_agent
            runner = _resolve_runner_from_agent(agent)
            agent_name = getattr(agent, "agent_name", None) or getattr(agent, "name", "bot")
            # Remember this session's runner+agent so any clear path can fire
            # SESSION_END with the correct context (never another user's agent).
            if runner is not None:
                self._session_hook_context[storage_key] = (runner, agent_name)
            fire_session_start(
                runner,
                session_id=storage_key,
                platform=self._platform,
                agent_name=agent_name,
            )
        except Exception as e:
            logger.debug("SESSION_START emit error (non-fatal): %s", e)

    def _fire_session_end(self, storage_key: str, reason: str = "clear") -> None:
        """Emit SESSION_END for *storage_key* if a session was open, then forget it.

        Idempotent and best-effort: a no-op when the session was never seen or
        no hook runner was captured. Used by every session-clear path (explicit
        reset, policy auto-reset, stale reaping, reset_all) so SESSION_START can
        fire again for the next session lifetime.
        """
        if storage_key not in self._seen_sessions:
            return
        self._seen_sessions.discard(storage_key)
        runner, agent_name = self._session_hook_context.pop(storage_key, (None, "bot"))
        if runner is None:
            return
        try:
            from ._protocol_mixin import fire_session_end
            fire_session_end(
                runner,
                session_id=storage_key,
                agent_name=agent_name,
                reason=reason,
            )
        except Exception as e:
            logger.debug("SESSION_END emit error (non-fatal): %s", e)

    def _load_history(self, user_id: str) -> List[Dict[str, Any]]:
        """Load user history from store (if available) or in-memory cache.
        
        Checks reset policy and clears history if a reset is needed.
        """
        storage_key = self._storage_key(user_id)
        
        # Check if session should be reset based on policy
        if self._should_reset_session(storage_key):
            logger.info("Auto-resetting session for user %s based on policy", user_id)
            self._clear_session_data(storage_key, user_id)
            # End the expiring session so the next message re-opens a fresh one
            # (otherwise lifecycle hooks would go permanently silent for this user).
            self._fire_session_end(storage_key, reason="policy")
            # Mark the reset time
            self._last_reset[storage_key] = time.monotonic()
            return []
        
        if self._store is not None:
            key = self._session_key(user_id)
            try:
                history = self._store.get_chat_history(key)
                if history:
                    return list(history)
            except Exception as e:
                logger.warning("Failed to load session from store: %s", e)
        return list(self._histories.get(storage_key, []))

    def _save_history(
        self, user_id: str, history: List[Dict[str, Any]]
    ) -> None:
        """Save user history to store (if available) and in-memory cache.

        When a compactor is configured, older turns are summarised (keeping a
        recent verbatim tail) instead of being permanently discarded, so
        long-lived conversations retain context across restarts. Without a
        compactor, the legacy tail-slice truncation is applied.

        A fresh ``ContextCompactor`` is built per call (not shared on the
        instance) so per-conversation state never leaks across users and
        concurrent saves on the executor pool don't race.
        """
        # Build a per-call compactor so its mutable per-conversation state
        # (iterative summary, anti-thrashing streaks) stays isolated per user.
        compactor = (
            self._build_compactor(self._compaction_config)
            if self._compaction_enabled
            else None
        )
        if compactor is not None:
            try:
                if compactor.needs_compaction(history):
                    compacted, _result = compactor.compact(history)
                    history = compacted
            except Exception as e:  # pragma: no cover — defensive
                logger.warning(
                    "History compaction failed; falling back to truncation: %s", e
                )
                if self._max_history > 0 and len(history) > self._max_history:
                    history = history[-self._max_history:]
            else:
                # Hard cap safety valve: even when the token-based compactor
                # hasn't triggered (e.g. short messages under-shoot the token
                # estimate), never let history grow unbounded. Allow headroom
                # so the cap doesn't fight compaction's recent-tail + summary.
                if self._max_history > 0:
                    hard_cap = self._max_history * 4
                    if len(history) > hard_cap:
                        history = history[-hard_cap:]
        elif self._max_history > 0 and len(history) > self._max_history:
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
                            When provided, events are bridged via agent.stream_emitter.

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
                Origin,
                ReachableTarget,
            )
            
            # Build enriched context if platform awareness is enabled
            origin = None
            reachable_targets = None
            
            if self._inject_session_context:
                # Detect chat type and build origin
                from .delivery import detect_chat_type
                chat_type = detect_chat_type(self._platform, chat_id)
                origin = Origin(
                    platform=self._platform,
                    chat_type=chat_type,
                    display_name=chat_id,  # Use chat_id as display_name since chat_name is not available
                    thread_id=thread_id,
                )
                
                # Get reachable targets from channel directory
                if self._channel_directory:
                    targets_data = self._channel_directory.describe_targets()
                    reachable_targets = [
                        ReachableTarget(
                            name=t['name'],
                            platform=t['platform'],
                            channel_id=t['channel_id'],
                            kind=t['kind'],
                        )
                        for t in targets_data
                    ]
            
            ctx_token = _set_ctx(
                platform=self._platform,
                chat_id=chat_id,
                thread_id=thread_id,
                user_id=user_id,
                user_name=user_name,
                unified_user_id=self._storage_key(user_id),
                origin=origin,
                reachable_targets=reachable_targets,
            )
        except Exception:  # pragma: no cover — defensive
            _clear_ctx = None  # type: ignore[assignment]

        # Initialize result variable
        result: Optional[str] = None
        claim_ctx = None
        
        try:
            # Claim journal entry if we have one
            if journal_key is not None:
                claim_ctx = self._ingress_journal.aclaim(journal_key)
                await claim_ctx.__aenter__()
                
            try:
                async with user_lock:
                    # Load history (may hit disk via run_in_executor for async safety)
                    loop = asyncio.get_running_loop()
                    user_history = await loop.run_in_executor(
                        None, self._load_history, user_id
                    )
                    
                    # Update last active timestamp AFTER history load and reset check
                    self._last_active[self._storage_key(user_id)] = time.monotonic()

                    # Fire SESSION_START once per session lifetime (no-op when
                    # no hooks registered).  BEFORE_AGENT / AFTER_AGENT are
                    # emitted by ``agent.chat()`` itself, so we deliberately do
                    # NOT re-fire them here to avoid double-dispatch.
                    self._maybe_fire_session_start(agent, user_id)

                    # W1 robustness: hold ``agent_lock`` across the FULL LLM call
                    # (not only the history swap) so concurrent users on a shared
                    # Agent instance never observe each other's chat_history.
                    async with agent_lock:
                        saved_history = agent.chat_history
                        agent.chat_history = user_history
                        
                        # Create interrupt controller for this run and register it
                        try:
                            from praisonaiagents.agent.interrupt import InterruptController
                        except ImportError:
                            # Fallback if InterruptController is not available
                            InterruptController = None
                        
                        controller = InterruptController() if InterruptController else None
                        storage_key = self._storage_key(user_id)
                        if controller:
                            self._active_runs[storage_key] = controller
                        
                        bridged_stream_callback = None
                        try:
                            # Choose streaming vs non-streaming path based on callback
                            if stream_callback:
                                # Streaming path: bridge events via stream_emitter because
                                # achat()/astart() do not accept stream_callback directly.
                                emitter = getattr(agent, "stream_emitter", None)
                                if emitter is not None:
                                    def bridged_stream_callback(event):
                                        try:
                                            result = stream_callback(event)
                                            if asyncio.iscoroutine(result):
                                                asyncio.get_running_loop().create_task(result)
                                        except Exception as cb_exc:
                                            logger.warning("Stream callback failed: %s", cb_exc)

                                    emitter.add_callback(bridged_stream_callback)

                                astart_kwargs = {"stream": True}
                                if controller:
                                    astart_kwargs["cancel_token"] = controller

                                try:
                                    response = await asyncio.wait_for(
                                        agent.astart(prompt, **astart_kwargs),
                                        timeout=self._run_timeout if self._run_timeout > 0 else None,
                                    )
                                    if hasattr(response, "output"):
                                        response = response.output
                                except asyncio.TimeoutError:
                                    if controller:
                                        controller.request("run timeout")
                                    raise BotRunTimeout(
                                        f"Agent run timed out after {self._run_timeout}s"
                                    )
                                finally:
                                    if emitter is not None and bridged_stream_callback is not None:
                                        emitter.remove_callback(bridged_stream_callback)
                            else:
                                # Legacy non-streaming path: use agent.chat() in executor with cancel_token and timeout
                                import contextvars
                                import inspect
                                from functools import partial
                                _ctx = contextvars.copy_context()
                                
                                # Create agent.chat call with cancel_token if supported
                                # Use inspect.signature for safer parameter checking
                                _chat_params = inspect.signature(agent.chat).parameters if (controller and hasattr(agent, 'chat')) else {}
                                if controller and 'cancel_token' in _chat_params:
                                    chat_call = partial(agent.chat, prompt, cancel_token=controller)
                                else:
                                    chat_call = partial(agent.chat, prompt)
                                
                                # Run with timeout and interruption support
                                try:
                                    response = await asyncio.wait_for(
                                        loop.run_in_executor(None, _ctx.run, chat_call),
                                        timeout=self._run_timeout if self._run_timeout > 0 else None,
                                    )
                                except asyncio.TimeoutError:
                                    if controller:
                                        controller.request("run timeout")
                                    raise BotRunTimeout(f"Agent run timed out after {self._run_timeout}s")
                            # Capture updated history before restoring caller's.
                            updated_history = agent.chat_history
                        except Exception as exc:
                            # N4: persist the failed inbound message before bubbling.
                            # Skip DLQ for timeout exceptions to prevent infinite retry loops
                            if self._dlq is not None and not isinstance(exc, BotRunTimeout):
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
                            # Clean up active run tracking
                            if controller:
                                self._active_runs.pop(storage_key, None)

                    # Persist outside the agent_lock — it's per-user and the agent
                    # is no longer touched.
                    await loop.run_in_executor(
                        None, self._save_history, user_id, updated_history
                    )

                    # Store response to return after cleanup
                    result = response
                    
            except Exception as e:
                # Handle any remaining exceptions and ensure claim is released 
                if claim_ctx is not None:
                    await claim_ctx.__aexit__(type(e), e, e.__traceback__)
                raise
            else:
                # Clean exit - mark journal complete before releasing claim
                if journal_key is not None and self._ingress_journal is not None:
                    try:
                        self._ingress_journal.complete(journal_key)
                        self._last_journal_key = None
                    except Exception as e:
                        logger.warning("Failed to complete journal entry: %s", e)
                if claim_ctx is not None:
                    await claim_ctx.__aexit__(None, None, None)
                return result or ""
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
        
        if decision == RunDecision.STEERED:
            # Message was injected into the live run via steering; the running
            # turn folds in the new guidance without a separate response here.
            ack_msg = await self._run_control.get_busy_ack_message(user_id, decision)
            return {
                "response": ack_msg,
                "metadata": {
                    "run_control": True,
                    "decision": decision.value,
                    "steered": True,
                }
            }

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

        # We're running now (RUN_NOW or INTERRUPTED): register the live agent so
        # subsequent mid-run STEER messages can be injected into it.
        if hasattr(self._run_control, "register_agent"):
            try:
                self._run_control.register_agent(user_id, agent)
            except Exception:  # noqa: BLE001 - registration is best-effort
                logger.debug("Failed to register agent for steering", exc_info=True)
        
        # We're running now (RUN_NOW or INTERRUPTED)
        current_prompt = prompt
        last_response = ""
        last_decision = decision
        pending_processed: List[str] = []

        while True:
            run_generation = None
            interrupt_controller = None

            if last_decision in (RunDecision.RUN_NOW, RunDecision.INTERRUPTED):
                interrupt_controller = self._run_control.get_interrupt_controller(user_id)

            status = self._run_control.get_run_status(user_id)
            run_generation = status.get("run_generation")

            try:
                original_interrupt = None
                if interrupt_controller and hasattr(agent, 'interrupt_controller'):
                    original_interrupt = getattr(agent, 'interrupt_controller', None)
                    agent.interrupt_controller = interrupt_controller

                last_response = await self.chat(
                    agent, user_id, current_prompt, chat_id, thread_id, user_name
                )

            except Exception as e:
                if interrupt_controller and interrupt_controller.is_set():
                    reason = interrupt_controller.reason or "unknown"
                    return {
                        "response": f"⚠️ Task cancelled: {reason}",
                        "metadata": {
                            "run_control": True,
                            "decision": last_decision.value,
                            "interrupted": True,
                            "reason": reason,
                            "run_generation": run_generation,
                        },
                    }
                raise

            finally:
                if interrupt_controller and hasattr(agent, 'interrupt_controller'):
                    if original_interrupt is not None:
                        agent.interrupt_controller = original_interrupt
                    else:
                        agent.interrupt_controller = None

                if run_generation is not None:
                    await self._run_control.finish_run(user_id, run_generation)

            pending = self._run_control.next_pending(user_id)
            if not pending:
                break

            pending_processed.append(
                pending[:100] + "..." if len(pending) > 100 else pending
            )
            current_prompt = pending
            last_decision = await self._run_control.submit(user_id, pending)

        metadata: Dict[str, Any] = {
            "run_control": True,
            "decision": decision.value,
            "completed": True,
            "run_generation": run_generation,
        }
        if pending_processed:
            metadata["pending_processed"] = pending_processed

        return {"response": last_response, "metadata": metadata}

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
            # End the session so lifecycle hooks fire and can re-open later.
            self._fire_session_end(storage_key, reason="stale")
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

    def _should_reset_session(self, storage_key: str) -> bool:
        """Check if a session should be reset based on the policy.
        
        Args:
            storage_key: The storage key for the user
            
        Returns:
            True if session should be reset
        """
        if self._reset_policy.mode == "none":
            return False
        
        # Get timestamps
        now = time.monotonic()
        last_activity = self._last_active.get(storage_key, now)
        last_reset = self._last_reset.get(storage_key, 0)
        
        # If this is a new session, initialize timestamps but don't reset
        if storage_key not in self._last_reset:
            self._last_reset[storage_key] = now
            if storage_key not in self._last_active:
                self._last_active[storage_key] = now
                return False
        
        return self._reset_policy.should_reset(
            last_activity=last_activity,
            last_reset=last_reset,
            now=now,
            current_datetime=datetime.now()
        )
    
    def _clear_session_data(self, storage_key: str, user_id: str) -> None:
        """Clear session data for a user.
        
        Args:
            storage_key: The storage key for the user
            user_id: The raw user ID
        """
        self._histories.pop(storage_key, None)
        # Don't clear last_active as we still need it for idle tracking
        # Don't drop lock here as it may still be held by caller
        
        if self._store is not None:
            persist_key = self._session_key(user_id)
            try:
                self._store.clear_session(persist_key)
            except Exception as e:
                logger.warning("Failed to clear session in store: %s", e)
    
    def reset(self, user_id: str) -> bool:
        """Clear a user's session history.  Returns True if it existed."""
        storage_key = self._storage_key(user_id)
        existed = storage_key in self._histories
        
        self._clear_session_data(storage_key, user_id)
        self._last_active.pop(storage_key, None)
        self._last_reset[storage_key] = time.monotonic()

        # Fire SESSION_END lifecycle hook (no-op when no hooks registered),
        # then forget the session so a subsequent message re-opens it.
        self._fire_session_end(storage_key, reason="clear")

        return existed

    def cancel_run(self, user_id: str, reason: str = "user_cancel") -> bool:
        """Cancel an active run for a user.
        
        Args:
            user_id: Raw platform user id
            reason: Reason for cancellation
            
        Returns:
            bool: True if there was an active run to cancel, False otherwise
        """
        storage_key = self._storage_key(user_id)
        controller = self._active_runs.get(storage_key)
        if controller:
            controller.request(reason)
            return True
        return False

    def get_active_runs(self) -> List[str]:
        """Get list of user IDs with active runs."""
        return list(self._active_runs.keys())

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

        # End every open session so lifecycle hooks fire and can re-open later.
        for storage_key in list(self._seen_sessions):
            self._fire_session_end(storage_key, reason="clear_all")

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


def build_session_manager(config, platform: str, *, run_control=None) -> BotSessionManager:
    """Build a BotSessionManager with standard configuration from a BotConfig.
    
    This helper extracts the common session manager setup logic that's duplicated
    across all bot adapters, including:
    - Session store acquisition
    - Reset policy extraction
    - Backward-compatible max_history resolution
    
    Args:
        config: BotConfig instance with session configuration
        platform: Platform identifier (e.g., "telegram", "slack")
        run_control: Optional run control for Telegram (keyword-only)
    
    Returns:
        Configured BotSessionManager instance
    """
    # Try to get the default session store
    try:
        from praisonaiagents.session import get_default_session_store
    except ImportError:
        # Module not available, fallback to in-memory
        store = None
    else:
        try:
            store = get_default_session_store()
        except Exception as exc:
            logger.warning(
                "Default session store unavailable; falling back to in-memory store: %s",
                exc,
            )
            store = None
    
    # Extract reset policy from config
    reset_policy = None
    if getattr(config, "session", None) and getattr(config.session, "reset", None):
        reset_policy = SessionResetPolicy.from_dict(config.session.reset.model_dump())

    # Extract optional history compaction config (disabled unless configured)
    compaction = None
    if getattr(config, "session", None) and getattr(config.session, "compaction", None):
        compaction = config.session.compaction
    
    # Support backward compatibility with max_history at channel level
    max_history = 100
    if getattr(config, "max_history", None) is not None:
        max_history = config.max_history
    elif getattr(config, "session", None) and getattr(config.session, "max_history", None) is not None:
        max_history = config.session.max_history
    
    return BotSessionManager(
        max_history=max_history,
        store=store,
        platform=platform,
        reset_policy=reset_policy,
        run_control=run_control,
        compaction=compaction,
    )
