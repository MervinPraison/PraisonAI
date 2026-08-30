"""
Memory, caching, and session persistence mixin for the Agent class.

Contains all methods for chat history management, caching, session
persistence, auto-memory, and auto-learning. Extracted from agent.py
for maintainability.
"""

import os
import inspect
import logging
import threading
import contextvars
from typing import Optional, Dict

# Per-turn ownership of appended chat-history messages. Each chat()/achat() turn
# runs in its own thread (sync) or task (async); both get an isolated copy of
# this context var. The append helpers record every message THIS turn appends
# into its own list, so a failing turn's rollback removes only its own messages
# and never a concurrent turn's - even though all turns share one chat_history.
_active_turn_owned: "contextvars.ContextVar[Optional[list]]" = contextvars.ContextVar(
    "praisonai_active_turn_owned", default=None
)

# Registry of the ownership lists of every currently in-flight chat()/achat()
# turn, keyed by id() of the list. A turn registers its list in
# _begin_turn_tracking and removes it in _end_turn_tracking. ephemeral() reads
# this at exit so a message a *concurrent live turn* appended is preserved even
# when that append did not flow through the ephemeral tracker (e.g. the turn
# ran on another thread that never entered this block's context). Guarded by
# _live_turns_lock because turns on different threads mutate it concurrently.
_live_turn_owners: "Dict[int, list]" = {}
_live_turns_lock = threading.Lock()


def _register_live_turn(owned: list) -> None:
    with _live_turns_lock:
        _live_turn_owners[id(owned)] = owned


def _unregister_live_turn(owned: Optional[list]) -> None:
    if owned is None:
        return
    with _live_turns_lock:
        _live_turn_owners.pop(id(owned), None)


def _live_turn_message_ids() -> set:
    """ids of every message any currently in-flight turn has appended so far."""
    with _live_turns_lock:
        owners = list(_live_turn_owners.values())
    ids = set()
    for owned in owners:
        ids.update(id(m) for m in owned)
    return ids

# Shared lazy display helpers (cached, thread-safe; avoid circular imports)
from ._lazy_display import _get_console, _get_live, _get_display_functions

logger = logging.getLogger(__name__)



import contextlib
from typing import Optional, Dict, Generator, TYPE_CHECKING
from collections import OrderedDict

if TYPE_CHECKING:
    pass


class MemoryMixin:
    """Mixin providing memory methods for the Agent class."""

    def _cache_put(self, cache_dict, key, value):
        """Thread-safe LRU cache put operation.
        
        Args:
            cache_dict: The cache dictionary (OrderedDict)
            key: Cache key 
            value: Value to cache
        """
        with self._cache_lock:
            # Move to end if already exists (LRU update)
            if key in cache_dict:
                del cache_dict[key]
            
            # Add new entry
            cache_dict[key] = value
            
            # Evict oldest if over limit
            while len(cache_dict) > self._max_cache_size:
                cache_dict.popitem(last=False)  # Remove oldest (FIFO)

    def _add_to_chat_history(self, role, content):
        """Thread-safe method to add messages to chat history.
        
        Args:
            role: Message role ("user", "assistant", "system")
            content: Message content
        """
        with self._history_lock:
            msg = {"role": role, "content": content}
            self.chat_history.append(msg)
            owned = _active_turn_owned.get()
            if owned is not None:
                owned.append(msg)

    def _add_to_chat_history_if_not_duplicate(self, role, content) -> bool:
        """Thread-safe method to add messages to chat history only if not duplicate.
        
        Atomically checks for duplicate and adds message under the same lock to prevent TOCTOU races.
        
        Args:
            role: Message role ("user", "assistant", "system") 
            content: Message content
            
        Returns:
            bool: True if message was added, False if duplicate was detected
        """
        with self._history_lock:
            # Check for duplicate within the same critical section
            if (self.chat_history and 
                self.chat_history[-1].get("role") == role and 
                self.chat_history[-1].get("content") == content):
                return False
            
            # Not a duplicate, add the message
            msg = {"role": role, "content": content}
            self.chat_history.append(msg)
            owned = _active_turn_owned.get()
            if owned is not None:
                owned.append(msg)
            return True

    def _get_chat_history_length(self):
        """Thread-safe method to get chat history length."""
        with self._history_lock:
            return len(self.chat_history)

    def _truncate_chat_history(self, length):
        """Thread-safe method to truncate chat history to specified length.
        
        Args:
            length: Target length for chat history
        """
        with self._history_lock:
            self.chat_history = self.chat_history[:length]

    def _begin_turn_tracking(self):
        """Start recording the messages appended by the current turn.

        Returns a token to reset the context var when the turn ends. Each turn
        runs in its own thread (sync ``chat``) or task (async ``achat``), so the
        context var copy is isolated per turn. Safe to call unconditionally; when
        a turn opts in, its rollback removes only its own messages by identity.

        The list is also registered in the process-wide live-turn registry so a
        concurrent ``ephemeral()`` block on another thread can preserve messages
        this in-flight turn appends (see ``_live_turn_message_ids``).
        """
        owned: list = []
        _register_live_turn(owned)
        return _active_turn_owned.set(owned)

    def _end_turn_tracking(self, token):
        """Stop recording for the current turn and drop its ownership list."""
        _unregister_live_turn(_active_turn_owned.get())
        try:
            _active_turn_owned.reset(token)
        except (ValueError, LookupError):
            _active_turn_owned.set(None)

    def _clear_turn_tracking(self):
        """Drop any per-turn ownership list from a prior turn on this context.

        Used at the start of an async turn (whose control flow has no single
        wrapping ``finally``) so a stale list from a completed turn on the same
        task cannot accumulate messages from unrelated turns. Also unregisters
        that stale list from the live-turn registry so it cannot linger there.
        """
        _unregister_live_turn(_active_turn_owned.get())
        _active_turn_owned.set(None)

    def _rollback_chat_history_to(self, rollback_length):
        """Thread-safe rollback that never clobbers a concurrent turn's messages.

        A turn snapshots ``len(self.chat_history)`` before a multi-second LLM
        call, then rolls back to that length on failure.

        Ownership-safe path (default for ``chat``/``achat`` turns): when the turn
        opted into per-turn tracking via ``_begin_turn_tracking()``, remove ONLY
        the messages this turn actually appended, identified by object identity.
        A concurrent turn that interleaved its own messages after this snapshot
        keeps every one of them - the old positional ``del chat_history[n:]``
        would have erased them and corrupted the transcript.

        Positional fallback (untracked callers): remove the tail from
        ``rollback_length`` onward, and only if the history actually grew that
        far. Backward compatible for any path that does not track ownership.

        Args:
            rollback_length: History length to roll back to (this turn's snapshot).
        """
        owned = _active_turn_owned.get()
        with self._history_lock:
            if owned is not None:
                owned_ids = {id(m) for m in owned}
                self.chat_history[:] = [
                    m for m in self.chat_history if id(m) not in owned_ids
                ]
                owned.clear()
                return

            # Untracked turn (or nothing appended): safe positional rollback.
            if len(self.chat_history) > rollback_length:
                del self.chat_history[rollback_length:]

    def _cache_get(self, cache_dict, key):
        """Thread-safe LRU cache get operation.
        
        Args:
            cache_dict: The cache dictionary (OrderedDict)
            key: Cache key
        
        Returns:
            Value if found, None otherwise
        """
        with self._cache_lock:
            if key not in cache_dict:
                return None
            
            # Move to end (mark as recently used)
            value = cache_dict[key]
            del cache_dict[key]
            cache_dict[key] = value
            return value

    def clear_history(self):
        """Clear all chat history.
        
        Also resets _auto_save_last_index to prevent silent message loss
        when auto_save is enabled.
        """
        # Hold the same lock every other history mutator takes so a concurrent
        # _add_to_chat_history append can't land on the list object we discard.
        with self._history_lock:
            self.chat_history = []
            # Reset auto-save index to prevent stale index causing message loss
            self._auto_save_last_index = 0

    def prune_history(self, keep_last: int = 5) -> int:
        """
        Prune chat history to keep only the last N messages.
        
        Useful for cleaning up large history after image analysis sessions
        to prevent context window saturation.
        
        Args:
            keep_last: Number of recent messages to keep
            
        Returns:
            Number of messages deleted
        """
        with self._history_lock:
            if len(self.chat_history) <= keep_last:
                return 0
            
            deleted_count = len(self.chat_history) - keep_last
            self.chat_history = self.chat_history[-keep_last:]
            # Reset auto-save index to match new history length
            self._auto_save_last_index = len(self.chat_history)
            return deleted_count

    def delete_history(self, index: int) -> bool:
        """
        Delete a specific message from chat history by index.
        
        Supports negative indexing (-1 for last message, etc.).
        
        Args:
            index: Message index (0-based, supports negative indexing)
            
        Returns:
            True if deleted, False if index out of range
        """
        with self._history_lock:
            try:
                del self.chat_history[index]
                # Adjust auto-save index if deletion affects saved range
                if hasattr(self, '_auto_save_last_index'):
                    self._auto_save_last_index = min(
                        self._auto_save_last_index,
                        len(self.chat_history)
                    )
                return True
            except IndexError:
                return False

    def delete_history_matching(self, pattern: str) -> int:
        """
        Delete all messages matching a pattern.
        
        Useful for removing all image-related messages after processing.
        
        Args:
            pattern: Substring to match in message content
            
        Returns:
            Number of messages deleted
        """
        with self._history_lock:
            original_len = len(self.chat_history)
            self.chat_history = [
                msg for msg in self.chat_history
                if pattern.lower() not in msg.get("content", "").lower()
            ]
            deleted_count = original_len - len(self.chat_history)
            # Adjust auto-save index if deletion affects saved range
            if deleted_count > 0 and hasattr(self, '_auto_save_last_index'):
                self._auto_save_last_index = min(
                    self._auto_save_last_index,
                    len(self.chat_history)
                )
            return deleted_count

    def get_history_size(self) -> int:
        """Get the current number of messages in chat history."""
        return len(self.chat_history)

    @contextlib.contextmanager
    def ephemeral(self) -> Generator[None, None, None]:
        """
        Context manager for ephemeral conversations.
        
        Messages within this block are NOT permanently stored in chat_history.
        History is restored to pre-block state after exiting.
        
        Example:
            with agent.ephemeral():
                response = agent.chat("[IMAGE] Analyze this")
                # After block, history is restored - image NOT persisted
        """
        # Restore by identity, not by a blind ``chat_history = saved_history``.
        # A message a concurrent chat()/achat() turn on the same shared Agent
        # commits during the block must survive; only the ephemeral additions go.
        #
        # A message is KEPT on exit when it is either:
        #   * present in the pre-block snapshot (it predates the block), or
        #   * owned by a chat()/achat() turn that is still in flight (a live
        #     concurrent turn appended it - preserving it is the fix for the
        #     history-loss race).
        # Everything else that appeared during the block is an ephemeral addition
        # and is removed. This also drops direct ``chat_history.append`` writes
        # made inside the block, which carry no turn ownership. Nested blocks
        # compose: the inner block removes its own additions first, and the outer
        # block's snapshot still holds everything that predates it.
        with self._history_lock:
            snapshot_ids = {id(m) for m in self.chat_history}

        try:
            yield
        finally:
            live_ids = _live_turn_message_ids()
            keep_ids = snapshot_ids | live_ids
            with self._history_lock:
                self.chat_history[:] = [
                    m for m in self.chat_history if id(m) in keep_ids
                ]

    def _init_db_session(self):
        """Initialize DB session if db adapter is provided (lazy, first chat only)."""
        if self._db is None or self._db_initialized:
            return
        
        # Generate session_id if not provided: default to per-hour ID (YYYYMMDDHH-agentname)
        # Protected by history lock to prevent race condition between concurrent chat() calls
        if self._session_id is None:
            if hasattr(self._history_lock, 'is_async_context') and self._history_lock.is_async_context():
                # Cannot use asyncio.Lock in sync context - use thread lock as fallback
                import hashlib
                import uuid
                from datetime import datetime, timezone
                with self._history_lock._lock._thread_lock:
                    if self._session_id is None:  # Double-check after acquiring lock
                        hour_str = datetime.now(timezone.utc).strftime("%Y%m%d%H")
                        agent_hash = hashlib.sha256((self.name or "agent").encode()).hexdigest()[:6]
                        # per-instance suffix so same-named agents can never collide
                        self._session_id = f"{hour_str}-{agent_hash}-{uuid.uuid4().hex[:8]}"
            else:
                # Use sync lock directly
                import hashlib
                import uuid
                from datetime import datetime, timezone
                with self._history_lock.lock():
                    if self._session_id is None:  # Double-check after acquiring lock
                        hour_str = datetime.now(timezone.utc).strftime("%Y%m%d%H")
                        agent_hash = hashlib.sha256((self.name or "agent").encode()).hexdigest()[:6]
                        # per-instance suffix so same-named agents can never collide
                        self._session_id = f"{hour_str}-{agent_hash}-{uuid.uuid4().hex[:8]}"
        
        # Call db adapter's on_agent_start to get previous messages
        try:
            history = self._db.on_agent_start(
                agent_name=self.name,
                session_id=self._session_id,
                user_id=self.user_id,
                metadata={"role": self.role, "goal": self.goal}
            )
            
            # Restore chat history from previous session
            if history:
                for msg in history:
                    self.chat_history.append({
                        "role": msg.role,
                        "content": msg.content
                    })
                logging.info(f"Resumed session {self._session_id} with {len(history)} messages")
        except Exception as e:
            logging.warning(f"Failed to initialize DB session: {e}")
        
        self._db_initialized = True
        self._current_run_id = None  # Track current run

    def _init_session_store(self):
        """
        Initialize session store for JSON-based persistence (lazy, first chat only).
        
        This is used when session_id is provided but no DB adapter.
        Enables automatic session persistence with zero configuration.
        """
        if self._session_store_initialized:
            return
        
        # Only initialize if session_id is provided and no DB adapter
        if self._session_id is None or self._db is not None:
            self._session_store_initialized = True
            return
        
        try:
            if self._session_store is None:
                from ..session import get_default_session_store
                self._session_store = get_default_session_store()
            
            # Restore chat history from previous session. Prefer the compacted
            # working history (summary + retained tail) when a compaction
            # checkpoint exists so resume is cheap and won't overflow context
            # (Issue #2741). Falls back to raw chat history for backward compat.
            if hasattr(self._session_store, "get_working_history"):
                history = self._session_store.get_working_history(self._session_id)
            else:
                history = self._session_store.get_chat_history(self._session_id)
            if history:
                # Only restore if chat_history is empty (avoid duplicates)
                if not self.chat_history:
                    for msg in history:
                        self.chat_history.append({
                            "role": msg["role"],
                            "content": msg["content"]
                        })
                    logging.info(f"Restored session {self._session_id} with {len(history)} messages from JSON store")
            
            # Set agent info
            self._session_store.set_agent_info(
                self._session_id,
                agent_name=self.name,
                user_id=self.user_id,
            )
        except Exception as e:
            logging.warning(f"Failed to initialize session store: {e}")
            self._session_store = None
        
        self._session_store_initialized = True

    def _start_run(self, input_content: str):
        """Start a new run (turn) for persistence tracking."""
        if self._db is None:
            return
        
        import uuid
        self._current_run_id = f"run-{uuid.uuid4().hex[:12]}"
        
        try:
            if hasattr(self._db, 'on_run_start'):
                self._db.on_run_start(
                    session_id=self._session_id,
                    run_id=self._current_run_id,
                    input_content=input_content,
                    metadata={"agent_name": self.name}
                )
        except Exception as e:
            logging.warning(f"Failed to start run: {e}")

    def _end_run(self, output_content: str, status: str = "completed", metrics: dict = None):
        """End the current run (turn)."""
        if self._db is None or self._current_run_id is None:
            return
        
        try:
            if hasattr(self._db, 'on_run_end'):
                self._db.on_run_end(
                    session_id=self._session_id,
                    run_id=self._current_run_id,
                    output_content=output_content,
                    status=status,
                    metrics=metrics or {},
                    metadata={"agent_name": self.name}
                )
        except Exception as e:
            logging.warning(f"Failed to end run: {e}")
        
        self._current_run_id = None

    def _persist_message(
        self,
        role: str,
        content: str,
        tool_calls=None,
        tool_call_id: Optional[str] = None,
    ):
        """Persist a message to the DB or session store.

        Args:
            role: Message role ("user", "assistant", "system", "tool").
            content: Message text.
            tool_calls: Optional structured tool calls on an assistant turn
                (Issue #3089). Persisted faithfully to the default JSON store
                so a resumed tool-using session reconstructs the same message
                list the model saw before.
            tool_call_id: Optional id linking a ``role="tool"`` result turn to
                the assistant tool call it answers (Issue #3089).
        """
        # Try DB adapter first
        if self._db is not None:
            try:
                if role == "user":
                    self._db.on_user_message(self._session_id, content)
                elif role == "assistant":
                    self._db.on_agent_message(self._session_id, content)
            except Exception as e:
                logging.warning(f"Failed to persist message to DB: {e}")
            return
        
        # Fall back to session store (JSON-based)
        if self._session_store is not None and self._session_id is not None:
            try:
                if role == "user":
                    self._session_store.add_user_message(self._session_id, content)
                elif role == "assistant":
                    # Faithful transcript: carry any tool calls the assistant
                    # requested so resume replays them (Issue #3089). Falls back
                    # to a plain text turn for stores predating the tool fields.
                    if tool_calls:
                        self._add_message_with_tool_fields(
                            "assistant", content, tool_calls=tool_calls
                        )
                    else:
                        self._session_store.add_assistant_message(
                            self._session_id, content
                        )
                elif role == "tool":
                    # Persist the tool-result turn linked to its call id so the
                    # resumed message list interleaves results in order (#3089).
                    self._add_message_with_tool_fields(
                        "tool", content, tool_call_id=tool_call_id
                    )
                # Keep auto_save index in sync when per-turn persist shares session_id
                if self.auto_save and self.auto_save == self._session_id:
                    with self._history_lock:
                        self._auto_save_last_index = (
                            getattr(self, "_auto_save_last_index", 0) + 1
                        )
                self._persist_session_stats()
            except Exception as e:
                logging.warning(f"Failed to persist message to session store: {e}")

    async def _apersist_message(
        self,
        role: str,
        content: str,
        tool_calls=None,
        tool_call_id: Optional[str] = None,
    ):
        """Async wrapper for :meth:`_persist_message`.

        The default JSON session store performs a file-locked, blocking
        read-modify-write to disk on every turn. Calling ``_persist_message``
        directly from ``_achat_impl`` would stall the entire event loop (other
        agents, streaming, background tasks) for the duration of that I/O on
        every user/assistant/tool turn. Offloading to a worker thread — the
        same treatment ``_persist_compaction_checkpoint`` already gets — keeps
        ``achat()`` non-blocking as documented.
        """
        import asyncio
        await asyncio.to_thread(
            self._persist_message, role, content, tool_calls, tool_call_id
        )

    def _add_message_with_tool_fields(self, role, content, **tool_fields):
        """Add a message carrying tool fields, tolerating stores without them.

        The default JSON store and the SQLite store accept ``tool_calls`` /
        ``tool_call_id``, but custom stores implementing the older
        ``SessionStoreProtocol`` (and the built-in ``HierarchicalSessionStore``)
        only accept ``(session_id, role, content, metadata)``. Passing the new
        keywords to those would raise ``TypeError`` and drop the turn entirely
        (Issue #3089). We feature-detect once via the call signature and fall
        back to a plain-text turn so no exchange is silently lost.
        """
        add_message = self._session_store.add_message
        if self._store_supports_tool_fields(add_message):
            add_message(self._session_id, role, content, **tool_fields)
            return
        # Legacy store: preserve the turn as plain text so resume still sees it.
        add_message(self._session_id, role, content)

    def _store_supports_tool_fields(self, add_message) -> bool:
        """Return True if ``add_message`` accepts the tool keyword fields."""
        cached = getattr(self, "_session_store_tool_fields", None)
        if cached is not None:
            return cached
        supported = True
        try:
            params = inspect.signature(add_message).parameters
            has_var_kw = any(
                p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
            )
            supported = has_var_kw or (
                "tool_calls" in params and "tool_call_id" in params
            )
        except (TypeError, ValueError):
            # Builtins / C-callables without introspectable signatures: assume
            # the conservative legacy shape.
            supported = False
        self._session_store_tool_fields = supported
        return supported

    def _persist_session_stats(self):
        """Flush agent cost/token stats into session JSON metadata."""
        store = getattr(self, "_session_store", None)
        session_id = getattr(self, "_session_id", None)
        if store is None or session_id is None:
            return
        if not hasattr(store, "update_session_metadata"):
            return
        try:
            summary = getattr(self, "cost_summary", {}) or {}
            llm = getattr(self, "llm", None)
            model = str(llm) if llm is not None else None
            store.update_session_metadata(
                session_id,
                model=model,
                total_tokens=summary.get("tokens_in", 0) + summary.get("tokens_out", 0),
                cost=summary.get("cost", 0),
                source=getattr(self, "_session_source", "chat"),
                agent_id=getattr(self, "agent_id", None) or getattr(self, "_agent_id", None),
            )
        except Exception as e:
            logging.debug(f"Session stats persist skipped: {e}")

    def session_id(self) -> Optional[str]:
        """Get the current session ID."""
        return self._session_id

    def _load_history_context(self):
        """Load history from past sessions into context.
        
        Note: This functionality is now handled via context= param with ManagerConfig.
        This method is kept for backward compatibility but is a no-op.
        Use context=ManagerConfig(history_sessions=N) to load past sessions.
        """
        pass

    def _process_auto_memory(self, user_message: str, assistant_response: str):
        """Process auto-memory extraction after agent response.
        
        Called after each agent response when auto_memory=True in MemoryConfig.
        Uses AutoMemory to extract and store memorable content (names, preferences,
        facts) from the conversation. No-op when auto_memory is disabled.
        
        Args:
            user_message: The user's input message
            assistant_response: The agent's response
        """
        if not self._auto_memory or not self._memory_instance:
            return
        
        try:
            from ..memory.auto_memory import AutoMemory
            # Lazy-create AutoMemory wrapper on first use
            if not hasattr(self, '_auto_memory_instance') or self._auto_memory_instance is None:
                self._auto_memory_instance = AutoMemory(
                    self._memory_instance,
                    enabled=True,
                    verbose=1 if getattr(self, 'verbose', False) else 0
                )
            self._auto_memory_instance.process_interaction(
                user_message=str(user_message),
                assistant_response=str(assistant_response),
            )
        except Exception as e:
            logging.debug(f"Auto-memory extraction failed: {e}")

    def _process_auto_learning(self):
        """Process auto-learning extraction after agent response.
        
        Called after each agent response when LearnMode.AGENTIC is set.
        Uses LearnManager.process_conversation() to extract and store learnings
        (persona, insights, patterns) from the conversation. No-op when learning
        is disabled or mode is not AGENTIC.
        """
        # Quick exit if no learn config or mode is not AGENTIC
        if not self._learn_config:
            return
        
        # Check if mode is AGENTIC (auto-extract learnings)
        from ..memory.learn.protocols import LearnMode
        mode = getattr(self._learn_config, 'mode', None)
        
        # Handle PROPOSE mode — extract but store as pending for user approval
        if (isinstance(mode, LearnMode) and mode == LearnMode.PROPOSE) or \
           (isinstance(mode, str) and mode == 'propose'):
            learn_manager = None
            if self._memory_instance and hasattr(self._memory_instance, 'learn'):
                learn_manager = self._memory_instance.learn
            if learn_manager:
                try:
                    recent_messages = self.chat_history[-2:] if len(self.chat_history) >= 2 else self.chat_history
                    if recent_messages:
                        # Use same extraction as AGENTIC, but don't auto-store
                        result = learn_manager.process_conversation(
                            messages=recent_messages,
                            llm=getattr(self._learn_config, 'llm', None) or self.llm,
                            extract_only=True,
                        )
                        # Move extracted items to pending queue
                        if result:
                            for p in result.get("persona", []):
                                if p:
                                    learn_manager.add_pending(p, category="persona")
                            for i in result.get("insights", []):
                                if i:
                                    learn_manager.add_pending(i, category="insights")
                            for pt in result.get("patterns", []):
                                if pt:
                                    learn_manager.add_pending(pt, category="patterns")
                except Exception as e:
                    logging.debug(f"PROPOSE mode learning extraction failed: {e}")
            return
        
        if mode is None or (isinstance(mode, LearnMode) and mode != LearnMode.AGENTIC):
            return
        if isinstance(mode, str) and mode != 'agentic':
            return
        
        # Get LearnManager from memory instance
        learn_manager = None
        if self._memory_instance and hasattr(self._memory_instance, 'learn'):
            learn_manager = self._memory_instance.learn
        
        if not learn_manager:
            return
        
        try:
            # Process recent conversation (last 2 messages: user + assistant)
            recent_messages = self.chat_history[-2:] if len(self.chat_history) >= 2 else self.chat_history
            if recent_messages:
                learn_manager.process_conversation(
                    messages=recent_messages,
                    llm=getattr(self._learn_config, 'llm', None) or self.llm,
                )
        except Exception as e:
            logging.debug(f"Auto-learning extraction failed: {e}")

    def _maybe_emit_nudge(self, user_message: str) -> Optional[str]:
        """Return a system note to append to the next user turn, or None.
        
        Implements the nudge mechanism for self-improving agents.
        When nudge_interval > 0, this increments a turn counter and emits
        a nudge prompt every N turns to encourage knowledge persistence.
        """
        if not self._learn_config or self._learn_config.nudge_interval <= 0:
            return None
            
        # Initialize/increment turn counter
        self._turns_since_nudge = getattr(self, "_turns_since_nudge", 0) + 1
        
        if self._turns_since_nudge < self._learn_config.nudge_interval:
            return None
            
        # Reset counter and emit nudge
        self._turns_since_nudge = 0
        
        # Optional: only nudge if agent has done meaningful work
        min_iters = getattr(self._learn_config, 'nudge_min_tool_iters', 3)
        tool_calls_count = getattr(self, '_recent_tool_calls_count', 0)
        if tool_calls_count < min_iters:
            return None
            
        return (
            "\n\n[System nudge] Review the recent conversation. If you discovered a "
            "non-trivial procedure or pattern, consider using available tools to "
            "persist this knowledge for future use. Skip if nothing noteworthy."
        )

    def _auto_save_session(self):
        """Auto-save session if auto_save is enabled.
        
        G-1 FIX: Routes to SessionStore instead of Memory.save_session() to
        maintain clean separation between conversation history (SessionStore)
        and semantic memory (Memory).
        
        Issue 1 FIX: Track last saved index to avoid duplicate insertion when
        called multiple times in the same session.
        """
        if not self.auto_save:
            return
        
        try:
            # Filter out history markers before saving
            clean_history = [
                {k: v for k, v in msg.items() if k != "_from_history"}
                for msg in self.chat_history
            ]
            
            # Issue 1 FIX: Only save NEW messages since last save
            # Track last saved index to avoid duplicates
            last_saved = getattr(self, '_auto_save_last_index', 0)
            new_messages = clean_history[last_saved:]
            
            if not new_messages:
                return  # Nothing new to save
            
            # G-1 FIX: Use SessionStore for conversation history persistence
            # This maintains clean separation: Memory = facts, SessionStore = turns
            if self._session_store is not None:
                # Persist only NEW messages to SessionStore
                for msg in new_messages:
                    self._session_store.add_message(
                        self.auto_save,  # Use auto_save name as session_id
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                    )
                # Update last saved index
                self._auto_save_last_index = len(clean_history)
                logging.debug(f"Auto-saved {len(new_messages)} new messages to SessionStore: {self.auto_save}")
            elif self._memory_instance and hasattr(self._memory_instance, 'save_session'):
                # Fallback to Memory.save_session() for backward compatibility
                # Memory.save_session() replaces entire history, so no duplicate issue
                self._memory_instance.save_session(
                    name=self.auto_save,
                    conversation_history=clean_history,
                    metadata={"agent_name": self.name, "user_id": self.user_id}
                )
                logging.debug(f"Auto-saved session to Memory: {self.auto_save}")
        except Exception as e:
            logging.debug(f"Error auto-saving session: {e}")

    def _save_output_to_file(self, content: str) -> bool:
        """Save agent output to file if output_file is configured.
        
        Args:
            content: The response content to save
            
        Returns:
            True if file was saved, False otherwise
        """
        if not self._output_file:
            return False
        
        try:
            import os
            from praisonaiagents.tools.path_safety import resolve_within_root

            project_root = os.environ.get("PRAISONAI_PROJECT_ROOT") or os.getcwd()
            file_path = resolve_within_root(self._output_file, project_root)
            if file_path is None:
                logging.warning(
                    "Output file %r is outside project root %r; skipping save",
                    self._output_file,
                    project_root,
                )
                print(f"⚠️ Output path outside project root: {self._output_file}")
                return False
            
            # Create parent directories if they don't exist
            parent_dir = os.path.dirname(file_path)
            if parent_dir and not os.path.exists(parent_dir):
                os.makedirs(parent_dir, exist_ok=True)
            
            # Write content to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(content))
            
            # Print success message to terminal
            print(f"✅ Output saved to {file_path}")
            logging.debug(f"Output saved to file: {file_path}")
            return True
            
        except Exception as e:
            logging.warning(f"Failed to save output to file '{self._output_file}': {e}")
            print(f"⚠️ Failed to save output to {self._output_file}: {e}")
            return False

