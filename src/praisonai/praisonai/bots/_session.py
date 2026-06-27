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
from functools import partial
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
        delivery_router: Optional[Any] = None,
        session_scope: str = "per_user",
        attribution: str = "[{sender}] ",
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
        # Issue #2372: the running gateway's DeliveryRouter. When set, each
        # agent turn registers a concrete ``BotOutboundMessenger`` into the
        # per-turn context so the built-in core ``send_message`` tool can
        # proactively reach the user mid-task. ``None`` preserves legacy
        # behaviour (the tool returns its "no gateway available" message).
        self._delivery_router = delivery_router
        self._last_journal_key = None  # Store key for delayed completion
        # Run control for in-flight message handling
        self._run_control = run_control
        # Run timeout and active run tracking for cancellation support
        self._run_timeout = run_timeout
        self._active_runs: Dict[str, Any] = {}  # user_id -> InterruptController
        # In-run progress liveness (Issue #2393): wall-clock timestamp of the
        # most recent real run progress (run start, streamed token/draft edit,
        # tool event). Channel health reads this via ``last_run_progress`` so a
        # long, actively-progressing run keeps the channel BUSY instead of being
        # restarted mid-run once its wall-clock crosses ``stuck_after``. A run
        # that emits nothing for ``stuck_after`` leaves this frozen and is still
        # correctly flagged STUCK.
        self._last_run_progress: Optional[float] = None
        # Per-user model overrides set via the /model command. Applied per-turn
        # inside the agent lock in chat() and restored afterwards so a shared
        # Agent instance never leaks one user's model to another. Keyed by
        # storage_key (same as _histories).
        self._model_overrides: Dict[str, Any] = {}
        # Per-route toolset scope staged by a routing handler that cannot thread
        # ``tool_policy`` through the adapter's own ``chat()`` call (Issue #2298).
        # The gateway's injected on_message handler runs synchronously right
        # before the adapter's ``_session.chat()`` in the same dispatch, so it
        # stages the resolved policy here keyed by agent identity; ``chat()``
        # consumes-and-clears it when no explicit ``tool_policy`` was passed.
        # Keyed by ``id(agent)`` so a shared session serving multiple agents
        # never crosses policies.
        self._pending_tool_policies: Dict[int, Any] = {}
        # Session reset policy for automatic lifecycle management
        self._reset_policy = reset_policy or SessionResetPolicy(mode="none")
        # Per-user last agent-emitted presentation. ``chat()`` keeps the return
        # type ``str`` for backward compatibility; when an agent (or hook)
        # returns a MessagePresentation/AgentReply, the portable presentation is
        # captured here so channel adapters can render interactive UI via the
        # existing per-channel renderers (text fallback otherwise). Keyed by
        # storage_key and consumed via ``pop_last_presentation``.
        self._last_presentation: Dict[str, Any] = {}
        # Track storage keys we've already fired SESSION_START for, so the
        # hook fires exactly once per session lifetime (until reset).
        self._seen_sessions: set = set()
        # Per-session hook context captured when SESSION_START fires, keyed by
        # storage_key: (HookRunner, agent_name). Lets any clear path emit
        # SESSION_END with the *correct* runner/agent — never another user's.
        self._session_hook_context: Dict[str, Any] = {}
        # Group/channel session scope (Issue #2376). ``per_user`` (default)
        # preserves today's per-sender isolation. ``per_chat`` routes a
        # group/channel chat to a single shared session keyed by
        # ``(platform, chat_id, thread_id)`` so the agent sees one coherent
        # multi-party transcript, and prefixes each turn with the sender so
        # statements can be attributed. DMs always stay per_user even when
        # ``per_chat`` is set, so private conversations never collide.
        scope = (session_scope or "per_user").strip().lower()
        if scope not in ("per_user", "per_chat"):
            logger.warning(
                "Unknown session_scope %r; falling back to 'per_user'", session_scope
            )
            scope = "per_user"
        self._session_scope = scope
        # Attribution template applied to each turn's content in per_chat mode.
        # Supports ``{sender}`` and ``{time}`` placeholders. Empty disables it.
        self._attribution = attribution if attribution is not None else "[{sender}] "
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

    def _attribute(self, prompt: str, sender: str) -> str:
        """Prefix *prompt* with the sender per the attribution template.

        Used in ``per_chat`` scope so a multi-party transcript records who
        said what (Issue #2376). The template supports ``{sender}`` and
        ``{time}`` placeholders; an empty template or missing sender leaves
        the prompt unchanged. Best-effort — any formatting error falls back
        to the original prompt so a malformed template never breaks chat.
        """
        if not self._attribution or not sender:
            return prompt
        try:
            prefix = self._attribution.format(
                sender=sender,
                time=datetime.now().strftime("%H:%M"),
            )
        except (KeyError, IndexError, ValueError) as e:  # pragma: no cover — defensive
            logger.warning("Invalid attribution template %r: %s", self._attribution, e)
            return prompt
        return f"{prefix}{prompt}"

    def _scope_for(self, chat_type: str = "") -> str:
        """Resolve the effective session scope for a given chat type.

        ``per_chat`` only applies to multi-party chat types (group/channel,
        or an undisambiguated ``unknown`` group on platforms like Telegram
        supergroups). Direct messages always stay ``per_user`` so private
        conversations are never merged into a shared transcript.

        Callers that only have a ``chat_id`` (e.g. ``reset()`` from a ``/new``
        handler) should derive ``chat_type`` via :func:`detect_chat_type`
        before calling so a DM never falls through to ``per_chat`` — see
        ``_storage_key``, which does this automatically.
        """
        if self._session_scope != "per_chat":
            return "per_user"
        if chat_type and chat_type.lower() in ("direct", "dm", "private"):
            return "per_user"
        return "per_chat"

    def _storage_key(
        self,
        user_id: str,
        *,
        account: str = "",
        chat_id: str = "",
        thread_id: str = "",
        chat_type: str = "",
    ) -> str:
        """Resolve a raw platform user id to the in-memory/store key.

        With an identity resolver this is the unified user id; without
        one, behaviour is unchanged (raw ``user_id``).

        When ``session_scope='per_chat'`` and the message arrives in a
        group/channel (``chat_id`` present, not a DM), the key is shared
        across participants — ``{platform}:acct:{account}:chat:{chat_id}:{thread_id}`` —
        so the agent sees one coherent multi-party transcript (Issue #2376).
        ``account`` namespaces the key so two gateway accounts on the same
        platform that happen to reuse a chat/thread id never collide.

        ``chat_type`` is derived from ``chat_id`` when omitted (e.g. a
        ``reset()`` call from a ``/new`` handler that only has the chat id)
        so a DM never accidentally resolves to a shared per_chat key.
        """
        effective_chat_type = chat_type
        if (
            not effective_chat_type
            and chat_id
            and self._session_scope == "per_chat"
        ):
            try:
                from .delivery import detect_chat_type
                effective_chat_type = detect_chat_type(self._platform, chat_id)
            except Exception:  # pragma: no cover — defensive
                effective_chat_type = ""
        if self._scope_for(effective_chat_type) == "per_chat" and chat_id:
            prefix = self._platform or "bot"
            account_key = account or "default"
            return f"{prefix}:acct:{account_key}:chat:{chat_id}:{thread_id}"
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

    def _session_key(self, user_id: str, **route: str) -> str:
        """Persistent-store key for a raw platform user id (back-compat API).

        Accepts optional ``chat_id``/``thread_id``/``chat_type`` so per_chat
        scope persists to a shared key (Issue #2376); without them behaviour
        is unchanged.
        """
        return self._persist_key(self._storage_key(user_id, **route))

    def _get_lock(self, user_id: str, **route: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for *user_id* (storage-keyed)."""
        key = self._storage_key(user_id, **route)
        return self._locks.get(key)

    def _get_agent_lock(self, agent: "Agent") -> asyncio.Lock:
        """Get or create a lock for the *agent* instance (using WeakKeyDictionary)."""
        lock = self._agent_locks.get(agent)
        if lock is None:
            lock = asyncio.Lock()
            self._agent_locks[agent] = lock
        return lock

    def _maybe_fire_session_start(self, agent: "Agent", user_id: str, **route: str) -> None:
        """Fire SESSION_START once per session lifetime (no-op without hooks)."""
        storage_key = self._storage_key(user_id, **route)
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

    def _load_history(self, user_id: str, **route: str) -> List[Dict[str, Any]]:
        """Load user history from store (if available) or in-memory cache.
        
        Checks reset policy and clears history if a reset is needed.
        """
        storage_key = self._storage_key(user_id, **route)
        
        # Check if session should be reset based on policy
        if self._should_reset_session(storage_key):
            logger.info("Auto-resetting session for user %s based on policy", user_id)
            self._clear_session_data(storage_key, self._persist_key(storage_key))
            # End the expiring session so the next message re-opens a fresh one
            # (otherwise lifecycle hooks would go permanently silent for this user).
            self._fire_session_end(storage_key, reason="policy")
            # Mark the reset time
            self._last_reset[storage_key] = time.monotonic()
            return []
        
        if self._store is not None:
            key = self._session_key(user_id, **route)
            try:
                history = self._store.get_chat_history(key)
                if history:
                    return list(history)
            except Exception as e:
                logger.warning("Failed to load session from store: %s", e)
        return list(self._histories.get(storage_key, []))

    def _save_history(
        self, user_id: str, history: List[Dict[str, Any]], **route: str
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
        self._histories[self._storage_key(user_id, **route)] = history

        if self._store is not None:
            key = self._session_key(user_id, **route)
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

    def set_pending_tool_policy(
        self, agent: "Agent", tool_policy: Optional[Any]
    ) -> None:
        """Stage a per-route toolset scope for ``agent``'s next ``chat()`` turn.

        Used by routing handlers (e.g. the gateway's injected Discord/Slack
        ``on_message``) that resolve a :class:`ToolPolicy` but cannot thread it
        through the adapter's own ``_session.chat()`` call (Issue #2298). The
        handler runs synchronously right before that ``chat()`` in the same
        dispatch, so the staged policy is consumed-and-cleared by the very next
        ``chat()`` for the same agent. ``None`` clears any prior staging so a
        trusted route never inherits an earlier untrusted route's scope.
        """
        if agent is None:
            return
        key = id(agent)
        if tool_policy is None:
            self._pending_tool_policies.pop(key, None)
        else:
            self._pending_tool_policies[key] = tool_policy

    @staticmethod
    def _apply_tool_policy(
        agent: "Agent", tool_policy: Optional[Any]
    ) -> Optional[Any]:
        """Scope ``agent.tools`` per ``tool_policy`` for one turn (Issue #2298).

        Returns a zero-arg callable that restores the agent's original tools,
        or ``None`` when no scoping was applied (no policy, no tools, or the
        policy removed nothing). The apply/restore mirrors the scheduler's
        proven ``_apply_toolset_scope`` so attended/trusted uses of the same
        shared agent are never affected.
        """
        if tool_policy is None:
            return None
        filter_tools = getattr(tool_policy, "filter_tools", None)
        if not callable(filter_tools):
            return None
        original = getattr(agent, "tools", None)
        if not original:
            return None
        try:
            filtered = filter_tools(list(original))
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Tool policy could not scope agent tools: %s", e)
            return None
        if len(filtered) == len(original):
            return None
        try:
            agent.tools = filtered
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Tool policy could not assign scoped tools: %s", e)
            return None

        removed = len(original) - len(filtered)
        logger.info(
            "Route tool policy scoped agent tools for inbound turn: "
            "%d -> %d (%d removed)",
            len(original),
            len(filtered),
            removed,
        )

        def _restore() -> None:
            try:
                agent.tools = original
            except Exception as e:  # pragma: no cover - defensive
                logger.warning("Tool policy could not restore agent tools: %s", e)

        return _restore

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
        tool_policy: Optional[Any] = None,
        correlation_id: str = "",
        attachments: Optional[List[str]] = None,
    ) -> str:
        """Run ``agent.chat(prompt)`` with *user_id*-scoped history.

        The call is wrapped in ``run_in_executor`` so the sync LLM
        round-trip never blocks the event loop.

        Uses both a per-user lock (serialise same user) and a per-agent
        lock (prevent concurrent history swaps on a shared Agent).

        Args:
            stream_callback: Optional async callback for streaming events.
                            When provided, events are bridged via agent.stream_emitter.
            tool_policy: Optional per-route toolset scope (Issue #2298). When
                            supplied, the agent's tools are filtered to the
                            policy-allowed subset for the duration of this turn
                            and restored afterwards, so an untrusted inbound
                            route never advertises dangerous tools to the model
                            while attended/trusted uses of the same shared agent
                            stay unaffected. Anything exposing ``filter_tools``
                            is accepted (e.g. ``ToolPolicy`` / ``RunPolicy``).
            attachments: Optional list of local file paths for inbound media
                            (images/documents) sent by the user (Issue #2350).
                            Forwarded to ``agent.chat(prompt, attachments=...)``
                            so the agent's existing vision capability can act on
                            them. Ephemeral per-turn (never persisted to history).

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
        # Consume any per-route toolset scope staged by a routing handler that
        # could not thread it through this call directly (Issue #2298). The
        # staged policy is always popped (so it applies exactly once and never
        # leaks into a later turn — including the dedup early-return below); an
        # explicit ``tool_policy`` argument wins, otherwise the staged one is
        # used. ``None`` here means "no policy resolved" (full toolset), so an
        # absent explicit arg safely inherits a fail-closed staged scope.
        staged_policy = self._pending_tool_policies.pop(id(agent), None)
        if tool_policy is None:
            tool_policy = staged_policy

        # Mint/adopt an end-to-end correlation id and bind it for this turn so
        # ingress, the agent run, and outbound delivery share one stable id in
        # structured logs. Adopts an explicit correlation_id, else the platform
        # message_id, else a fresh id. No-op import failure is non-fatal.
        cid = None
        cid_token = None
        try:
            from ._correlation import correlation_id_from, set_correlation_id
            cid = correlation_id_from(
                {"correlation_id": correlation_id, "message_id": message_id}
            )
            cid_token = set_correlation_id(cid)
            logger.debug(
                "bot turn start", extra={"correlation_id": cid, "platform": self._platform}
            )
        except Exception:  # pragma: no cover — defensive
            cid = correlation_id or message_id or None

        # Handle ingress journaling for durable message processing
        journal_key = None
        if self._ingress_journal is not None and message_id:
            payload = {
                "user_id": user_id,
                "prompt": prompt,
                "chat_id": chat_id,
                "thread_id": thread_id,
                "user_name": user_name,
                "correlation_id": cid,
            }
            journal_key = self._ingress_journal.receive(
                platform=self._platform or "unknown",
                account=account or "default",
                channel_id=chat_id or user_id,
                message_id=message_id,
                payload=payload
            )
            if journal_key is None:
                # Duplicate message - restore the correlation id before the
                # early return so the contextvar set for this turn never leaks
                # into an unrelated subsequent call sharing the same task.
                if cid_token is not None:
                    try:
                        from ._correlation import reset_correlation_id
                        reset_correlation_id(cid_token)
                    except Exception as e:  # pragma: no cover — defensive
                        logger.debug("Failed to reset correlation id: %s", e)
                return ""
                
        # Resolve the routing context once so per_chat scope (Issue #2376)
        # keys the session and locks by the shared chat — not the sender —
        # for group/channel chats, while DMs and per_user stay sender-keyed.
        # ``route`` is empty in per_user mode so every keyed helper behaves
        # exactly as before (full back-compat).
        chat_type = ""
        route: Dict[str, str] = {}
        if self._session_scope == "per_chat":
            try:
                from .delivery import detect_chat_type
                chat_type = detect_chat_type(self._platform, chat_id)
            except Exception:  # pragma: no cover — defensive
                chat_type = ""
            if self._scope_for(chat_type) == "per_chat" and chat_id:
                route = {
                    "account": account,
                    "chat_id": chat_id,
                    "thread_id": thread_id,
                    "chat_type": chat_type,
                }
                # Attribute each turn to its sender so the agent can follow a
                # multi-party thread ("who said what"). Only applied in the
                # shared per_chat session; per_user content is untouched.
                prompt = self._attribute(prompt, user_name or user_id)

        user_lock = self._get_lock(user_id, **route)
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

        # Issue #2372: register a concrete outbound messenger for this turn so
        # the built-in core ``send_message`` tool can proactively reach the
        # user. Bound to the running gateway's DeliveryRouter and this turn's
        # origin so ``send_message("origin", ...)`` replies on the channel the
        # message came from. Cleared in the finally below so it never leaks
        # into an unrelated turn. No router -> no-op (legacy behaviour).
        messenger_token = None
        _clear_messenger = None
        if self._delivery_router is not None:
            try:
                from ._outbound_messenger import BotOutboundMessenger
                from .delivery import SessionSource
                from praisonaiagents.session.context import (
                    register_outbound_messenger as _register_messenger,
                    clear_outbound_messenger as _clear_messenger,
                )

                origin_source = None
                if self._platform and chat_id:
                    origin_source = SessionSource(
                        platform=self._platform,
                        channel_id=chat_id,
                        user_id=user_id,
                        thread_id=thread_id,
                    )
                messenger = BotOutboundMessenger(
                    self._delivery_router, origin=origin_source
                )
                messenger_token = _register_messenger(messenger)
            except Exception as e:  # pragma: no cover — defensive
                logger.debug("Failed to register outbound messenger: %s", e)
                _clear_messenger = None  # type: ignore[assignment]

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
                        None, partial(self._load_history, user_id, **route)
                    )
                    
                    # Update last active timestamp AFTER history load and reset check
                    self._last_active[self._storage_key(user_id, **route)] = time.monotonic()

                    # Fire SESSION_START once per session lifetime (no-op when
                    # no hooks registered).  BEFORE_AGENT / AFTER_AGENT are
                    # emitted by ``agent.chat()`` itself, so we deliberately do
                    # NOT re-fire them here to avoid double-dispatch.
                    self._maybe_fire_session_start(agent, user_id, **route)

                    # W1 robustness: hold ``agent_lock`` across the FULL LLM call
                    # (not only the history swap) so concurrent users on a shared
                    # Agent instance never observe each other's chat_history.
                    async with agent_lock:
                        saved_history = agent.chat_history
                        agent.chat_history = user_history

                        # Per-route toolset scope (Issue #2298): swap the
                        # agent's tools to the policy-allowed subset for this
                        # turn so untrusted inbound routes never advertise
                        # dangerous tools to the model. Restored in the finally
                        # below alongside chat_history/model, so a shared Agent
                        # instance never leaks a scoped toolset to another turn.
                        _restore_tools = self._apply_tool_policy(agent, tool_policy)

                        # Apply a per-user model override (set via the /model
                        # command) for the duration of this turn only. The swap
                        # happens inside the per-agent lock and is restored in
                        # the finally below, so a shared Agent instance never
                        # leaks one user's model to another concurrent user.
                        _model_overridden = False
                        _saved_llm = None
                        _override = self._model_overrides.get(self._storage_key(user_id))
                        if _override is not None and hasattr(agent, "llm"):
                            _saved_llm = agent.llm
                            if _override != _saved_llm:
                                agent.llm = _override
                                _model_overridden = True

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
                        # In-run progress liveness (Issue #2393): mark progress
                        # at run start so a fresh long run is never STUCK on a
                        # stale inbound timestamp; streamed events refresh it
                        # below while the turn executes.
                        self.note_run_progress()

                        bridged_stream_callback = None
                        try:
                            # Choose streaming vs non-streaming path based on callback
                            if stream_callback:
                                # Streaming path: bridge events via stream_emitter because
                                # achat()/astart() do not accept stream_callback directly.
                                emitter = getattr(agent, "stream_emitter", None)
                                if emitter is not None:
                                    def bridged_stream_callback(event):
                                        # In-run progress liveness (Issue #2393):
                                        # every streamed token/draft edit/tool
                                        # event is real progress, so refresh the
                                        # heartbeat to keep the channel BUSY for
                                        # the full duration of a long stream.
                                        self.note_run_progress()
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
                                # Thread inbound media to the agent's vision path
                                # only when astart() accepts it (Issue #2350), so
                                # agents without an attachments param keep working.
                                if attachments:
                                    import inspect as _inspect
                                    try:
                                        _astart_params = _inspect.signature(agent.astart).parameters
                                    except (ValueError, TypeError):
                                        _astart_params = {}
                                    if "attachments" in _astart_params or any(
                                        p.kind == p.VAR_KEYWORD for p in _astart_params.values()
                                    ):
                                        astart_kwargs["attachments"] = attachments

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
                                _ctx = contextvars.copy_context()

                                # In-run progress liveness (Issue #2393): attach a
                                # progress-only callback to the agent's event
                                # emitter so internal tool/token events during a
                                # non-streamed run still refresh the heartbeat,
                                # keeping a long, actively-progressing run BUSY.
                                # A genuinely-hung run emits nothing, leaving the
                                # timestamp frozen so STUCK is still detectable.
                                progress_emitter = getattr(agent, "stream_emitter", None)
                                progress_callback = None
                                if progress_emitter is not None and hasattr(progress_emitter, "add_callback"):
                                    def progress_callback(_event):  # noqa: ANN001
                                        self.note_run_progress()
                                    try:
                                        progress_emitter.add_callback(progress_callback)
                                    except Exception:  # noqa: BLE001 — best-effort liveness
                                        progress_callback = None

                                # Create agent.chat call with cancel_token if supported
                                # Use inspect.signature for safer parameter checking
                                _chat_params = inspect.signature(agent.chat).parameters if hasattr(agent, 'chat') else {}
                                _chat_kwargs = {}
                                if controller and 'cancel_token' in _chat_params:
                                    _chat_kwargs['cancel_token'] = controller
                                # Thread inbound media to the agent's vision path
                                # when the agent supports it (Issue #2350). Honor
                                # wrappers that forward **kwargs to a vision-capable
                                # agent, matching the streaming (astart) path.
                                if attachments and (
                                    'attachments' in _chat_params
                                    or any(
                                        p.kind == p.VAR_KEYWORD
                                        for p in _chat_params.values()
                                    )
                                ):
                                    _chat_kwargs['attachments'] = attachments
                                chat_call = partial(agent.chat, prompt, **_chat_kwargs)
                                
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
                                finally:
                                    if progress_emitter is not None and progress_callback is not None:
                                        try:
                                            progress_emitter.remove_callback(progress_callback)
                                        except Exception:  # noqa: BLE001 — best-effort cleanup
                                            pass
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
                            # Restore the agent's original toolset if a
                            # per-route policy scoped it for this turn.
                            if _restore_tools is not None:
                                _restore_tools()
                            # Restore the agent's original model if we applied a
                            # per-user override for this turn.
                            if _model_overridden:
                                agent.llm = _saved_llm
                            # Clean up active run tracking
                            if controller:
                                self._active_runs.pop(storage_key, None)

                    # Persist outside the agent_lock — it's session-scoped and
                    # the agent is no longer touched. ``route`` keys the shared
                    # per_chat session when active (empty otherwise).
                    await loop.run_in_executor(
                        None,
                        partial(self._save_history, user_id, updated_history, **route),
                    )

                    # Normalise an agent-emitted presentation (if any) into
                    # (text, presentation). Agents/hooks may return a plain str
                    # (unchanged), a MessagePresentation, or an AgentReply. The
                    # portable presentation is captured per-user so channel
                    # adapters can render interactive UI; the text is returned as
                    # before so the str contract and text fallback are preserved.
                    try:
                        from praisonaiagents.bots.agent_reply import extract_presentation
                        storage_key = self._storage_key(user_id)
                        text, presentation = extract_presentation(response)
                        # Always normalise to plain text so chat() never leaks a
                        # non-str (e.g. AgentReply) past its str contract.
                        response = text
                        if presentation is not None:
                            self._last_presentation[storage_key] = presentation
                        else:
                            # Clear any stale UI from an earlier turn so a later
                            # plain-text turn cannot reuse it via run-control.
                            self._last_presentation.pop(storage_key, None)
                    except Exception as e:  # pragma: no cover — defensive
                        logger.debug("presentation extraction skipped: %s", e)

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
            # Issue #2372: clear the per-turn outbound messenger so it never
            # leaks into an unrelated subsequent call sharing the same task.
            if messenger_token is not None and _clear_messenger is not None:
                try:
                    _clear_messenger(messenger_token)
                except Exception as e:  # pragma: no cover — defensive
                    logger.debug("Failed to clear outbound messenger: %s", e)
            # Restore the previous correlation id so the contextvar never leaks
            # the id of this turn into an unrelated subsequent call.
            if cid_token is not None:
                try:
                    from ._correlation import reset_correlation_id
                    reset_correlation_id(cid_token)
                except Exception as e:  # pragma: no cover — defensive
                    logger.debug("Failed to reset correlation id: %s", e)

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

        # We're running now (RUN_NOW or INTERRUPTED)
        current_prompt = prompt
        last_response = ""
        last_decision = decision
        pending_processed: List[str] = []

        while True:
            run_generation = None
            interrupt_controller = None

            if last_decision in (RunDecision.RUN_NOW, RunDecision.INTERRUPTED):
                # Register the live agent for each fresh run so that mid-run
                # STEER messages can be injected into it. finish_run() clears the
                # handle after every turn, so re-register on each pending iteration
                # too (otherwise STEER silently falls back to QUEUE after the
                # first run).
                if hasattr(self._run_control, "register_agent"):
                    try:
                        self._run_control.register_agent(user_id, agent)
                    except Exception:  # noqa: BLE001 - registration is best-effort
                        logger.debug("Failed to register agent for steering", exc_info=True)

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

        # Surface any agent-emitted presentation captured during the run(s) so
        # run-control callers can render interactive UI alongside the text reply.
        presentation = self.pop_last_presentation(user_id)
        if presentation is not None:
            metadata["presentation"] = presentation

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
    
    def _clear_session_data(self, storage_key: str, persist_key: str) -> None:
        """Clear session data for a session.

        Args:
            storage_key: The in-memory storage key for the session
            persist_key: The persistent-store key for the session (already
                derived via ``_session_key``/``_persist_key`` so per_chat
                scope clears the shared key, not a re-derived per_user one).
        """
        self._histories.pop(storage_key, None)
        # Don't clear last_active as we still need it for idle tracking
        # Don't drop lock here as it may still be held by caller
        
        if self._store is not None:
            try:
                self._store.clear_session(persist_key)
            except Exception as e:
                logger.warning("Failed to clear session in store: %s", e)
    
    def pop_last_presentation(self, user_id: str) -> Optional[Any]:
        """Return and clear the last agent-emitted presentation for *user_id*.

        Channel adapters call this immediately after ``chat()`` to check whether
        the agent attached interactive UI to its reply. Returns the portable
        ``MessagePresentation`` (which the adapter renders via the per-channel
        renderer) or ``None`` when the reply was plain text. Consuming clears it
        so a later text-only turn never re-renders stale buttons.
        """
        return self._last_presentation.pop(self._storage_key(user_id), None)

    def reset(self, user_id: str, **route: str) -> bool:
        """Clear a session's history.  Returns True if it existed.

        Accepts optional ``chat_id``/``thread_id``/``chat_type`` so a ``/new``
        command issued in a group/channel clears the shared per_chat session
        (Issue #2376); without them behaviour is unchanged (per_user).
        """
        storage_key = self._storage_key(user_id, **route)
        existed = storage_key in self._histories
        
        self._clear_session_data(storage_key, self._persist_key(storage_key))
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

    def note_run_progress(self) -> None:
        """Record in-run progress for channel-health liveness (Issue #2393).

        Called when a run makes real progress (run start, a streamed
        token/draft edit bridged through ``stream_callback``, or a tool event)
        so the health monitor can tell an actively-progressing long run from a
        genuinely-hung one. Best-effort and side-effect-free beyond the
        timestamp; never raises.
        """
        self._last_run_progress = time.time()

    def last_run_progress(self) -> Optional[float]:
        """Return the most recent in-run progress timestamp (or ``None``).

        Read by the bot adapter's health builder so the evaluator's busy branch
        can use ``max(last_activity, last_run_progress)`` — keeping a streaming
        or tool-calling run BUSY rather than mistaking its wall-clock for a
        stuck socket.
        """
        return self._last_run_progress

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


def resolve_durable_store_dir(platform: str = ""):
    """Resolve the canonical per-platform SQLite store directory for durability.

    Returns ``~/.praisonai/state/<platform>/`` (created if missing), where the
    inbound journal, inbound DLQ and outbound queue databases for a given
    platform live so all durable components share one canonical store instead of
    three ad-hoc file paths. ``PRAISONAI_HOME`` overrides the base directory when
    set.

    The store is scoped by ``platform`` so that bots on different platforms
    (telegram, discord, slack, ...) running under the same ``PRAISONAI_HOME`` do
    not share a journal/DLQ. This prevents one platform's DLQ replay from
    consuming another platform's failed inbound events and avoids dedup-tuple
    collisions across platforms.
    """
    from pathlib import Path
    import os as _os
    import re as _re

    base = _os.environ.get("PRAISONAI_HOME")
    root = Path(base).expanduser() if base else Path.home() / ".praisonai"
    store_dir = root / "state"
    # Scope by platform so each adapter gets an isolated journal + DLQ.
    safe_platform = _re.sub(r"[^A-Za-z0-9_.-]", "_", platform).strip("_") if platform else ""
    if safe_platform:
        store_dir = store_dir / safe_platform
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir


def _build_durable_components(config, platform: str):
    """Default-construct the inbound journal + DLQ for durable delivery.

    Durability is on by default for gateway/bot runs. Reads an optional
    ``delivery`` config block (``durable`` flag + ``store`` override); when
    durability is enabled, builds an :class:`InboundJournal` (dedup + crash
    replay) and an :class:`InboundDLQ` (failed-inbound replay) against one
    canonical per-agent SQLite store. Returns ``(ingress_journal, dlq)``;
    either may be ``None`` if durability is disabled or construction fails
    (in which case the manager safely falls back to in-memory behaviour).
    """
    delivery = getattr(config, "delivery", None) if config is not None else None
    # Default ON: durability is the safe default unless explicitly disabled.
    durable = True if delivery is None else getattr(delivery, "durable", True)
    if not durable:
        return None, None

    try:
        from pathlib import Path
        store_override = getattr(delivery, "store", None) if delivery is not None else None
        if store_override:
            store_dir = Path(store_override).expanduser()
            # Allow either a directory or an explicit file path. When a file is
            # given, place sibling DBs next to it so all components share a dir.
            if store_dir.suffix:
                store_dir = store_dir.parent
            store_dir.mkdir(parents=True, exist_ok=True)
        else:
            store_dir = resolve_durable_store_dir(platform)

        from ._ingress import InboundJournal
        from ._dlq import InboundDLQ

        ingress_journal = InboundJournal(path=str(store_dir / "ingress.sqlite"))
        dlq = InboundDLQ(path=str(store_dir / "inbound_dlq.sqlite"))
        logger.info(
            "Durable delivery enabled for %s (store=%s)",
            platform or "bot",
            store_dir,
        )
        return ingress_journal, dlq
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "Durable delivery requested but could not be initialised; "
            "falling back to in-memory delivery: %s",
            exc,
        )
        return None, None


def build_session_manager(config, platform: str, *, run_control=None) -> BotSessionManager:
    """Build a BotSessionManager with standard configuration from a BotConfig.
    
    This helper extracts the common session manager setup logic that's duplicated
    across all bot adapters, including:
    - Session store acquisition
    - Reset policy extraction
    - Backward-compatible max_history resolution
    - Durable inbound delivery (journal + DLQ) wired by default
    
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

    # Extract group/channel session scope + attribution (Issue #2376).
    # Defaults preserve per_user isolation when unset.
    session_scope = "per_user"
    attribution = "[{sender}] "
    if getattr(config, "session", None):
        session_scope = getattr(config.session, "session_scope", None) or session_scope
        _attr = getattr(config.session, "attribution", None)
        if _attr is not None:
            attribution = _attr
    
    # Support backward compatibility with max_history at channel level
    max_history = 100
    if getattr(config, "max_history", None) is not None:
        max_history = config.max_history
    elif getattr(config, "session", None) and getattr(config.session, "max_history", None) is not None:
        max_history = config.session.max_history
    
    # Durable inbound delivery (on by default for gateway/bot runs): wire a
    # deduplicating inbound journal and an inbound DLQ against one canonical
    # per-agent SQLite store so a crash mid-turn or a platform webhook
    # redelivery never silently loses or double-processes a message.
    ingress_journal, dlq = _build_durable_components(config, platform)

    return BotSessionManager(
        max_history=max_history,
        store=store,
        platform=platform,
        reset_policy=reset_policy,
        run_control=run_control,
        compaction=compaction,
        ingress_journal=ingress_journal,
        dlq=dlq,
        session_scope=session_scope,
        attribution=attribution,
    )
