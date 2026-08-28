"""
Default Session Store for PraisonAI Agents.

JSON-based session persistence with file locking and atomic writes.
Zero dependencies beyond stdlib.
"""

import copy
import json
from praisonaiagents._logging import get_logger
import os
import queue
import sys
import tempfile
import threading
import time

# fcntl is Unix-only; on Windows, use msvcrt for file locking
try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from ..paths import get_sessions_dir

logger = get_logger(__name__)

# Module-level sentinel to track if we've warned about degraded locking
_WARNED_NO_FCNTL = False

# Default session directory (uses centralized paths - DRY).
#
# Deliberately NOT a module constant. Evaluating ``get_sessions_dir()`` at
# import time froze the store root to whatever ``PRAISONAI_HOME`` resolved to
# during the first import of this module, so any later override -- a container
# exporting ``PRAISONAI_HOME`` after the package was imported, a test
# monkeypatching ``get_sessions_dir`` -- was silently ignored and reads/writes
# went to the wrong store. It is resolved live instead.
#
# ``DEFAULT_SESSION_DIR`` remains readable as a module attribute (resolved at
# access time via the PEP 562 ``__getattr__`` below) and remains assignable as
# an explicit override, so existing importers and tests keep working.


def _resolve_default_session_dir() -> str:
    """Resolve the default session directory *now*.

    An explicit ``praisonaiagents.session.store.DEFAULT_SESSION_DIR = ...``
    assignment still wins (a documented test/embedding hook); with no
    assignment the value is resolved live from :func:`get_sessions_dir`.
    """
    override = globals().get("DEFAULT_SESSION_DIR")
    if override:
        return str(override)
    return str(get_sessions_dir())


def __getattr__(name: str):
    """Module-level attribute hook (PEP 562).

    Keeps ``from praisonaiagents.session.store import DEFAULT_SESSION_DIR``
    working, but resolves the value at access time instead of at import time.
    """
    if name == "DEFAULT_SESSION_DIR":
        return _resolve_default_session_dir()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# Default limits
DEFAULT_MAX_MESSAGES = 100
DEFAULT_LOCK_TIMEOUT = 5.0  # seconds

# Retention policies for the active-window overflow (Issue #2709).
# - "compact":  summarise overflow into one synthetic message + archive raw turns
#               (non-destructive default; nothing is silently dropped)
# - "truncate": legacy behaviour — hard-slice to the tail, dropping older turns
# - "keep_all": never trim the active window (unbounded history)
RETENTION_COMPACT = "compact"
RETENTION_TRUNCATE = "truncate"
RETENTION_KEEP_ALL = "keep_all"
DEFAULT_RETENTION = RETENTION_COMPACT

# Emit a one-off warning once archived_messages under "compact" retention grows
# past this many entries, so operators can spot runaway sessions on disk.
ARCHIVE_WARN_THRESHOLD = 10_000

@dataclass
class SessionMessage:
    """A single message in a session.

    Beyond plain user/assistant text, a message may carry a structured
    tool turn so a resumed session reconstructs the exact message list the
    model saw before (Issue #3089):

    - ``tool_calls``: on an assistant turn, the tool calls it requested
      (list of ``{"id", "type", "function": {"name", "arguments"}}`` dicts).
    - ``tool_call_id``: on a ``role="tool"`` result turn, the id of the
      assistant tool call it answers.

    Both are optional and additive — old text-only session files (four keys:
    role/content/timestamp/metadata) still load unchanged.
    """
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Optional structured tool turn (Issue #3089). Empty/None for text turns.
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Tool fields are only emitted when present, preserving the legacy
        four-key JSON shape for plain text turns (backward compatible).
        """
        data: Dict[str, Any] = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
        if self.tool_calls:
            data["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            data["tool_call_id"] = self.tool_call_id
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMessage":
        """Create from dictionary (tolerant of missing tool fields)."""
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )

    def to_llm_message(self) -> Dict[str, Any]:
        """Render as an LLM-compatible message, preserving tool turns.

        Text turns collapse to the canonical ``{"role", "content"}`` shape;
        turns carrying tool calls / a tool_call_id additionally surface those
        keys so a resumed message list is identical in shape to the original.
        """
        msg: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        return msg

@dataclass
class CompactionCheckpoint:
    """A durable checkpoint of an in-run context compaction (Issue #2741).

    Persists the summary produced by ``compact_conversation`` plus the number
    of messages that were live in the session at the time of compaction, so a
    later ``--continue`` / ``resume`` can reconstruct the *compacted* working
    history (summary + tail) instead of replaying the raw transcript.
    """
    summary: str
    # Length of ``SessionData.messages`` at compaction time. Messages appended
    # after this index are the "tail" that follow the summary on resume.
    message_index: int = 0
    role: str = "system"  # Role to use when replaying the summary as a message
    tokens_before: int = 0
    tokens_after: int = 0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary,
            "message_index": self.message_index,
            "role": self.role,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CompactionCheckpoint":
        return cls(
            summary=data.get("summary", ""),
            message_index=data.get("message_index", 0),
            role=data.get("role", "system"),
            tokens_before=data.get("tokens_before", 0),
            tokens_after=data.get("tokens_after", 0),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
        )

    def as_message(self) -> Dict[str, str]:
        """Render this checkpoint's summary as an LLM-compatible message."""
        return {"role": self.role, "content": self.summary}


@dataclass
class SessionData:
    """Complete session data structure."""
    session_id: str
    messages: List[SessionMessage] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_name: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Gap S3: Gateway integration - link session to gateway session
    gateway_session_id: Optional[str] = None
    agent_id: Optional[str] = None  # Gateway agent ID (different from agent_name)
    # Runtime state for native transcript mirroring - Issue #1943
    runtime_state: Dict[str, Dict[str, Dict[str, Any]]] = field(default_factory=dict)  # {runtime_id: {turn_id: state}}
    # Durable append-only archive of turns rolled out of the active window
    # under the "compact" retention policy - Issue #2709. Nothing is silently
    # dropped: the active `messages` window is summary + recent turns, while the
    # full record lives here for the record / later inspection.
    archived_messages: List[SessionMessage] = field(default_factory=list)
    # Compaction checkpoint for cheap resume - Issue #2741 (optional, backward compatible)
    last_compaction: Optional[CompactionCheckpoint] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = {
            "session_id": self.session_id,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "agent_name": self.agent_name,
            "user_id": self.user_id,
            "metadata": self.metadata,
            "gateway_session_id": self.gateway_session_id,
            "agent_id": self.agent_id,
            "runtime_state": self.runtime_state,
            "archived_messages": [m.to_dict() for m in self.archived_messages],
        }
        if self.last_compaction is not None:
            data["last_compaction"] = self.last_compaction.to_dict()
        for key in ("model", "llm", "total_tokens", "token_count", "cost", "source",
                    "reasoning_effort"):
            if key in self.metadata:
                data[key] = self.metadata[key]
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        """Create from dictionary."""
        messages = [
            SessionMessage.from_dict(m) 
            for m in data.get("messages", [])
        ]
        archived = [
            SessionMessage.from_dict(m)
            for m in (data.get("archived_messages") or [])
        ]
        last_compaction_data = data.get("last_compaction")
        last_compaction = (
            CompactionCheckpoint.from_dict(last_compaction_data)
            if last_compaction_data
            else None
        )
        # Backward compatibility: `to_dict` mirrors select metadata keys to the
        # top level, and older/externally-written session files may carry
        # `model`/`llm` (etc.) only there. Fold those back into `metadata` so
        # resume can recover the recorded model instead of silently reverting to
        # the current default (Issue #3685). Existing metadata always wins.
        metadata = dict(data.get("metadata") or {})
        for key in ("model", "llm", "total_tokens", "token_count", "cost", "source",
                    "reasoning_effort"):
            if key not in metadata and data.get(key) is not None:
                metadata[key] = data[key]
        return cls(
            session_id=data.get("session_id", ""),
            messages=messages,
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            agent_name=data.get("agent_name"),
            user_id=data.get("user_id"),
            metadata=metadata,
            gateway_session_id=data.get("gateway_session_id"),
            agent_id=data.get("agent_id"),
            runtime_state=data.get("runtime_state") or {},
            archived_messages=archived,
            last_compaction=last_compaction,
        )
    
    @staticmethod
    def _trim_preserving_tool_exchanges(
        messages: List["SessionMessage"], max_messages: int
    ) -> List["SessionMessage"]:
        """Keep the most recent ``max_messages`` without splitting a tool
        exchange (Issue #3089).

        A count-based tail can otherwise begin on an orphaned ``role="tool"``
        result (a tool output whose originating assistant tool-call was trimmed
        off), which providers reject as an invalid transcript. We nudge the
        boundary forward past any leading tool results so history always starts
        on a self-contained turn.
        """
        if not max_messages or len(messages) <= max_messages:
            return messages
        start = len(messages) - max_messages
        while start < len(messages) and messages[start].role == "tool":
            start += 1
        return messages[start:]

    def get_chat_history(self, max_messages: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Get chat history in LLM-compatible format.
        
        Returns list of {"role": "user/assistant", "content": "..."} dicts.
        """
        messages = self._trim_preserving_tool_exchanges(self.messages, max_messages)
        # Preserve tool-call / tool-result turns so a resumed message list is
        # identical in shape to the pre-resume one (Issue #3089).
        return [m.to_llm_message() for m in messages]

    def trim_messages(self, max_messages: int) -> None:
        """Trim the transcript head to ``max_messages``, keeping the checkpoint
        anchor consistent (Issue #2741).

        When older messages are dropped, the compaction checkpoint's
        ``message_index`` is shifted by the same amount so the retained tail
        continues to line up on resume.
        """
        overflow = len(self.messages) - max_messages
        if overflow <= 0:
            return
        self.messages = self.messages[-max_messages:]
        if self.last_compaction is not None:
            self.last_compaction.message_index = max(
                0, self.last_compaction.message_index - overflow
            )

    def get_working_history(
        self, max_messages: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """Reconstruct compacted working history for cheap resume (Issue #2741).

        If a compaction checkpoint exists, returns the summary followed by the
        messages appended *after* compaction (the retained tail). Falls back to
        the full raw history when no checkpoint is present, keeping pre-existing
        sessions fully backward compatible.
        """
        checkpoint = self.last_compaction
        if checkpoint is None:
            return self.get_chat_history(max_messages)

        # Messages appended after the compaction point are the retained tail.
        index = max(0, min(checkpoint.message_index, len(self.messages)))
        tail = self.messages[index:]
        history = [checkpoint.as_message()]
        # Preserve tool-call / tool-result turns in the retained tail (#3089).
        history.extend(m.to_llm_message() for m in tail)
        if max_messages and len(history) > max_messages:
            # Always preserve the summary at the head, trim the tail.
            head = history[:1]
            body = history[1:][-(max_messages - 1):] if max_messages > 1 else []
            # Don't let the trimmed tail begin on an orphaned tool result whose
            # assistant tool-call was cut off (Issue #3089).
            while body and body[0].get("role") == "tool":
                body = body[1:]
            history = head + body
        return history

class FileLock:
    """
    Cross-platform file locking.
    
    Uses fcntl on Unix and msvcrt on Windows.
    """
    
    def __init__(self, filepath: str, timeout: float = DEFAULT_LOCK_TIMEOUT):
        self.filepath = filepath
        self.timeout = timeout
        self._lock_file = None
        self._lock_path = filepath + ".lock"
    
    def __enter__(self):
        if not self.acquire():
            raise IOError(f"Failed to acquire file lock for {self.filepath} after {self.timeout}s")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
    
    def acquire(self) -> bool:
        """Acquire the file lock."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self._lock_path) or ".", exist_ok=True)
        
        start_time = time.time()
        while True:
            try:
                self._lock_file = open(self._lock_path, "w")
                if sys.platform == "win32":
                    # Windows locking
                    import msvcrt
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    # Unix locking
                    if _HAS_FCNTL:
                        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    else:
                        # Warn once about degraded locking on non-Windows platforms without fcntl
                        global _WARNED_NO_FCNTL
                        if not _WARNED_NO_FCNTL:
                            logger.warning(
                                "File locking unavailable on this platform (fcntl not available); "
                                "concurrent writers may corrupt session files."
                            )
                            _WARNED_NO_FCNTL = True
                return True
            except (IOError, OSError, BlockingIOError):
                if self._lock_file:
                    self._lock_file.close()
                    self._lock_file = None
                
                if time.time() - start_time > self.timeout:
                    logger.warning(f"Failed to acquire lock for {self.filepath} after {self.timeout}s")
                    return False
                
                time.sleep(0.05)  # Wait 50ms before retry
    
    def release(self) -> None:
        """Release the file lock."""
        if self._lock_file:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    if _HAS_FCNTL:
                        fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                    # Note: No warning needed in release() as it mirrors acquire() logic
            except (IOError, OSError):
                pass
            finally:
                self._lock_file.close()
                self._lock_file = None
                # Note: We don't remove the lock file to avoid race conditions
                # where another process has opened but not yet locked the file

# Bounded queue for the optional background mirror writer (Issue #3646).
# A mirror outage must never block the local turn, so appends are enqueued and
# flushed on a daemon thread; the bound keeps a slow/broken mirror from growing
# memory without limit (overflow is dropped-to-log, local disk is untouched).
DEFAULT_MIRROR_QUEUE_SIZE = 1000
DEFAULT_MIRROR_MAX_RETRIES = 3


class _SessionMirrorWriter:
    """Background, non-blocking writer that flushes records to a mirror.

    Local-first guarantee (Issue #3646): the session store always writes local
    disk first; this writer runs on a daemon thread and drains a bounded queue,
    so a mirror's latency or outage never delays or fails a turn. On a full
    queue we drop-to-log rather than block; on a permanent per-record failure
    we log and move on. The local session file remains the source of truth.
    """

    def __init__(
        self,
        mirror: Any,
        *,
        max_queue: int = DEFAULT_MIRROR_QUEUE_SIZE,
        max_retries: int = DEFAULT_MIRROR_MAX_RETRIES,
    ):
        self._mirror = mirror
        self._max_retries = max_retries
        self._queue: "queue.Queue" = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="praisonai-session-mirror", daemon=True
        )
        self._thread.start()

    def enqueue(self, session_id: str, records: List[Dict[str, Any]]) -> None:
        """Queue records for the mirror without ever blocking the caller."""
        if not records:
            return
        # After close() the draining thread has exited; queuing here would leave
        # records stranded with no consumer while the local write reports
        # success. Drop-to-log instead so the gap is observable (and `session
        # sync` can reconcile) rather than silently lost (Issue #3646).
        if self._stop.is_set():
            logger.warning(
                "session mirror is closed; dropping %d record(s) for %s "
                "(local write unaffected; run `session sync` to reconcile)",
                len(records),
                session_id,
            )
            return
        try:
            self._queue.put_nowait((session_id, records))
        except queue.Full:
            # Never block the turn on a slow mirror; the local write already
            # succeeded and `session sync` can reconcile the gap later.
            logger.warning(
                "session mirror queue full; dropping %d record(s) for %s "
                "(local write unaffected; run `session sync` to reconcile)",
                len(records),
                session_id,
            )

    def _run(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                session_id, records = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                self._flush_one(session_id, records)
            finally:
                self._queue.task_done()

    def _flush_one(self, session_id: str, records: List[Dict[str, Any]]) -> None:
        delay = 0.05
        for attempt in range(1, self._max_retries + 1):
            try:
                self._mirror.append(session_id, records)
                return
            except Exception as e:  # pragma: no cover - defensive; mirror is external
                if attempt >= self._max_retries:
                    logger.error(
                        "session mirror append failed for %s after %d attempts: %s "
                        "(local write unaffected)",
                        session_id,
                        attempt,
                        e,
                    )
                    return
                time.sleep(delay)
                delay = min(delay * 2, 1.0)

    def flush(self, timeout: Optional[float] = None) -> bool:
        """Block until queued records are flushed (test/`sync` convenience).

        Waits for every enqueued item to be *processed* (``task_done``), not
        merely dequeued, so a slow in-flight ``append`` is counted as pending.
        """
        deadline = None if timeout is None else time.time() + timeout
        # queue.Queue exposes unfinished_tasks under its internal mutex; poll it
        # so we honour the timeout without a blocking join() that can't be
        # interrupted.
        while True:
            with self._queue.all_tasks_done:
                if self._queue.unfinished_tasks == 0:
                    return True
            if deadline is not None and time.time() > deadline:
                return False
            time.sleep(0.01)

    def close(self, timeout: float = 5.0) -> None:
        """Stop the writer, draining any queued records first."""
        self._stop.set()
        self._thread.join(timeout=timeout)


class DefaultSessionStore:
    """
    JSON-based session persistence with file locking.
    
    Features:
    - Zero configuration required
    - Automatic file locking for multi-process safety
    - Atomic writes to prevent corruption
    - Configurable message limits
    - Thread-safe operations
    
    Usage:
        store = DefaultSessionStore()
        
        # Add messages
        store.add_message("session-123", "user", "Hello")
        store.add_message("session-123", "assistant", "Hi there!")
        
        # Get history
        history = store.get_chat_history("session-123")
        # [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]
        
        # Restore in new process
        store2 = DefaultSessionStore()
        history = store2.get_chat_history("session-123")  # Same history!
    """
    
    def __init__(
        self,
        session_dir: Optional[str] = None,
        max_messages: int = DEFAULT_MAX_MESSAGES,
        lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
        retention: Optional[str] = None,
        active_window: Optional[int] = None,
        mirror: Optional[Any] = None,
    ):
        """
        Initialize session store.
        
        Args:
            session_dir: Directory for session files. Defaults to ~/.praisonai/sessions/
            max_messages: Maximum messages to keep in the active window per
                session. When ``retention`` is not given and a non-default
                ``max_messages`` is passed explicitly, the store keeps the
                legacy hard-truncate behaviour for backward compatibility.
            lock_timeout: Timeout for file lock acquisition.
            retention: Overflow policy for the active window (Issue #2709):
                - ``"compact"`` (default): summarise the oldest turns into a
                  single synthetic summary message and archive the raw turns
                  in the durable record — nothing is silently dropped.
                - ``"truncate"``: legacy behaviour — hard-slice to the tail,
                  permanently dropping older turns.
                - ``"keep_all"``: never trim the active window.
            active_window: Number of recent turns kept live in ``messages``
                (defaults to ``max_messages``). Older turns are compacted or
                truncated per ``retention``.
            mirror: Optional :class:`~praisonaiagents.session.protocols.SessionMirrorProtocol`
                sink (Issue #3646). When set, every persisted message is *also*
                appended to the mirror on a background thread (local-first: the
                local write always happens first and a mirror outage never
                blocks or fails the turn). Left ``None`` there is zero overhead.
        """
        self.session_dir = session_dir or _resolve_default_session_dir()
        self.max_messages = max_messages
        self.lock_timeout = lock_timeout

        # Backward compatibility: an explicit non-default max_messages with no
        # retention set keeps the old "truncate to tail" behaviour. New callers
        # opt into non-destructive compaction via retention="compact" (default
        # when nothing is specified).
        if retention is None:
            retention = (
                RETENTION_TRUNCATE
                if max_messages != DEFAULT_MAX_MESSAGES
                else DEFAULT_RETENTION
            )
        if retention not in (RETENTION_COMPACT, RETENTION_TRUNCATE, RETENTION_KEEP_ALL):
            raise ValueError(
                f"Invalid retention {retention!r}; expected one of "
                f"{RETENTION_COMPACT!r}, {RETENTION_TRUNCATE!r}, {RETENTION_KEEP_ALL!r}"
            )
        self.retention = retention
        self.active_window = active_window if active_window is not None else max_messages

        self._lock = threading.RLock()
        self._cache: Dict[str, SessionData] = {}

        self._mirror = mirror

        # Ensure session directory exists. Do this *before* spinning up the
        # mirror writer so a construction failure on an unusable session dir
        # never leaks an idle daemon thread for a store that won't exist.
        os.makedirs(self.session_dir, exist_ok=True)

        # Optional local-first mirror (Issue #3646). Only spun up when a mirror
        # is provided, so the default store keeps its zero-dependency, no-thread
        # behaviour untouched.
        self._mirror_writer: Optional[_SessionMirrorWriter] = (
            _SessionMirrorWriter(mirror) if mirror is not None else None
        )
    
    @staticmethod
    def _summarise_overflow(
        new_turns: List["SessionMessage"],
        prior_summary: Optional["SessionMessage"] = None,
    ) -> "SessionMessage":
        """Roll up newly overflowed turns into one synthetic summary message.

        Reuses the dependency-free deterministic summary shape from
        ``context.compressor.ContextCompressor._create_fallback_summary`` so a
        resumed session retains the *gist* of dropped-from-window turns without
        any LLM call, network, or optional dependency (Issue #2709).

        ``prior_summary`` (when present) is carried forward so repeated rollups
        don't collapse to "2 messages": its text is prepended and its
        ``compacted_count`` accumulates the true number of archived turns.
        """
        payload = [
            {"role": m.role, "content": m.content, "name": m.metadata.get("name")}
            for m in new_turns
        ]
        try:
            from ..context.compressor import ContextCompressor
            summary_text = ContextCompressor(
                enable_session_tracking=False
            )._create_fallback_summary(payload)
        except Exception:  # pragma: no cover - summariser must never break persistence
            summary_text = f"Previous conversation: {len(new_turns)} messages compacted."

        prior_count = 0
        if prior_summary is not None:
            prior_count = int(prior_summary.metadata.get("compacted_count", 0) or 0)
            prior_text = prior_summary.content
            # Strip our own "[Session Summary]\n" prefix before carrying forward.
            prefix = "[Session Summary]\n"
            if prior_text.startswith(prefix):
                prior_text = prior_text[len(prefix):]
            summary_text = f"{prior_text}\n---\n{summary_text}"

        return SessionMessage(
            role="system",
            content=f"[Session Summary]\n{summary_text}",
            metadata={
                "compaction": True,
                "compacted_count": prior_count + len(new_turns),
            },
        )

    def _enforce_window(self, session: SessionData) -> None:
        """Apply the retention policy to the active message window.

        - ``keep_all``: no-op (unbounded history).
        - ``truncate``: legacy hard-slice to the tail (destructive, logged once).
        - ``compact``: summarise the oldest overflow turns into a single
          synthetic message, archive the raw turns in the durable record, and
          keep ``[summary, *recent]`` as the active window (non-destructive).
        """
        window = self.active_window
        if window is None or window <= 0:
            return
        if len(session.messages) <= window:
            return

        if self.retention == RETENTION_KEEP_ALL:
            return

        # Nudge the window boundary forward past any leading orphaned
        # ``role="tool"`` results so the retained tail never starts mid
        # tool-exchange (would be rejected by strict providers). Reuses the
        # same guard as get_chat_history (Issue #3089).
        recent = SessionData._trim_preserving_tool_exchanges(session.messages, window)
        overflow = session.messages[: len(session.messages) - len(recent)]

        if self.retention == RETENTION_TRUNCATE:
            session.messages = recent
            # Keep the compaction checkpoint anchor aligned with the retained
            # tail after the head is dropped (Issue #2741).
            self._shift_checkpoint_anchor(session, len(overflow))
            logger.info(
                "session %s: truncated %d early turns (retention=truncate)",
                session.session_id,
                len(overflow),
            )
            return

        # retention == "compact": archive raw overflow, then roll up.
        # An existing summary already at the head of the overflow is carried
        # forward (not re-archived) so repeated writes don't nest summaries.
        prior_summary = None
        if overflow and overflow[0].metadata.get("compaction"):
            prior_summary = overflow[0]
            to_archive = overflow[1:]
        else:
            to_archive = overflow

        # Metadata-only re-writes can push the window over by re-adding the
        # existing summary alone (no new raw turns). Nothing to compact — avoid
        # a misleading "compacted 0 early turns" log and a redundant rollup.
        if not to_archive:
            new_messages = [prior_summary, *recent] if prior_summary else recent
            self._shift_checkpoint_anchor(
                session, len(session.messages) - len(new_messages)
            )
            session.messages = new_messages
            return

        session.archived_messages.extend(to_archive)
        if len(session.archived_messages) > ARCHIVE_WARN_THRESHOLD:
            logger.warning(
                "session %s: archived_messages has grown to %d entries; "
                "consider retention='truncate' or pruning old sessions.",
                session.session_id,
                len(session.archived_messages),
            )
        summary = self._summarise_overflow(to_archive, prior_summary=prior_summary)
        new_messages = [summary, *recent]
        self._shift_checkpoint_anchor(
            session, len(session.messages) - len(new_messages)
        )
        session.messages = new_messages
        logger.info(
            "session %s: compacted %d early turns into a summary (retention=compact)",
            session.session_id,
            len(to_archive),
        )

    @staticmethod
    def _shift_checkpoint_anchor(session: SessionData, dropped: int) -> None:
        """Shift the compaction checkpoint anchor after ``dropped`` head
        messages are removed from the active window (Issue #2741)."""
        if dropped <= 0 or session.last_compaction is None:
            return
        session.last_compaction.message_index = max(
            0, session.last_compaction.message_index - dropped
        )

    def _get_session_path(self, session_id: str) -> str:
        """Get the file path for a session."""
        # Sanitize session_id for filesystem
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
        return os.path.join(self.session_dir, f"{safe_id}.json")
    
    def _load_session(self, session_id: str) -> SessionData:
        """Load session from disk with file locking."""
        filepath = self._get_session_path(session_id)

        # When a session file exists, always reload under FileLock so reads
        # from another DefaultSessionStore instance (or process) are visible.
        if os.path.exists(filepath):
            with FileLock(filepath, self.lock_timeout):
                try:
                    session = self._load_session_from_disk(session_id, filepath)
                except OSError:
                    # Read-only path: a transient failure must not raise into
                    # callers. Prefer any cached copy over an empty session so
                    # existing history stays visible; nothing is written here.
                    with self._lock:
                        if session_id in self._cache:
                            return self._cache[session_id]
                    return SessionData(session_id=session_id)
                # Issue #3597: fold any turns spilled on a prior write failure
                # back into the session, then delete the consumed spill files.
                self._reingest_spill(session_id, session)
            with self._lock:
                self._cache[session_id] = session
            return session

        with self._lock:
            if session_id in self._cache:
                return self._cache[session_id]
            session = SessionData(session_id=session_id)
            self._cache[session_id] = session
        # Even with no on-disk file yet, a prior write failure may have spilled
        # turns for this session — recover them on first load (Issue #3597).
        with FileLock(filepath, self.lock_timeout):
            self._reingest_spill(session_id, session)
        with self._lock:
            self._cache[session_id] = session
        return session

    def _load_session_from_disk(self, session_id: str, filepath: str) -> SessionData:
        """Load session JSON from disk (caller must hold FileLock).

        Distinguishes three cases so a transient read error never silently
        destroys real history on the next write:

        * File does not exist yet → return a fresh empty session.
        * File is malformed JSON → the durable copy is unusable, but its raw
          bytes may still be recoverable, so it is *quarantined* (renamed
          aside to ``<file>.corrupt-<ts>``) before starting fresh rather than
          left in place to be silently overwritten by the next write. The
          quarantine is surfaced via the ``SESSION_PERSIST_FAILED`` hook so a
          corruption event is observable, not just a log line.
        * File exists but the read itself fails with an OS-level error
          (``PermissionError``, an NFS/network hiccup, an antivirus lock,
          disk-full-during-read, …) → re-raise ``OSError`` so the caller
          aborts the write instead of overwriting valid data with an empty
          session. ``json.JSONDecodeError`` is a subclass of ``ValueError``,
          not ``OSError``, so genuine corruption is handled separately.
        """
        if not os.path.exists(filepath):
            return SessionData(session_id=session_id)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionData.from_dict(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # Malformed content — the parsed data is unusable, but the raw file
            # may still hold recoverable bytes. Quarantine it aside so the next
            # write cannot silently overwrite (and permanently destroy) it, and
            # surface the event instead of leaving only a log line.
            # ``UnicodeDecodeError`` (invalid UTF-8, e.g. a truncated/binary
            # file) is a ``ValueError`` subclass like ``JSONDecodeError`` but is
            # raised by the decoder before JSON parsing, so it is handled here
            # too rather than being allowed to propagate.
            quarantine_path = self._quarantine_corrupt(filepath)
            logger.error(
                "Session file %s contains invalid JSON; quarantined to %s and "
                "starting fresh: %s",
                filepath,
                quarantine_path or "<quarantine failed>",
                e,
            )
            self._fire_corruption_hook(session_id, str(e), quarantine_path)
            return SessionData(session_id=session_id)
        except OSError as e:
            # Transient I/O failure on a file that *does* exist — do NOT
            # substitute an empty session, which would cause the next write to
            # destroy real history. Propagate so the caller aborts the write.
            logger.error(
                f"Transient read error loading session {filepath}; "
                f"refusing to overwrite existing data: {e}"
            )
            raise

    def _read_session_fresh(self, session_id: str) -> SessionData:
        """Reload session from disk and refresh the in-process cache."""
        filepath = self._get_session_path(session_id)
        with FileLock(filepath, self.lock_timeout):
            try:
                session = self._load_session_from_disk(session_id, filepath)
            except OSError:
                # Read-only path: fall back to any cached copy on a transient
                # failure rather than raising or caching an empty session.
                with self._lock:
                    if session_id in self._cache:
                        return self._cache[session_id]
                return SessionData(session_id=session_id)
            # Issue #3597: recover any turns spilled on a prior write failure.
            self._reingest_spill(session_id, session)
        with self._lock:
            self._cache[session_id] = session
        return session

    def _quarantine_corrupt(self, filepath: str) -> Optional[str]:
        """Move a corrupt session file aside so it is never silently overwritten.

        Renames ``<file>.json`` to ``<file>.json.corrupt-<epoch_ms>`` (best
        effort) so the raw, possibly-recoverable bytes survive instead of being
        clobbered by the next atomic write. Returns the quarantine path on
        success, else ``None``. Caller must hold the session ``FileLock``.
        """
        try:
            base = f"{filepath}.corrupt-{int(time.time() * 1000)}"
            # Guard against clobbering an earlier quarantine that landed in the
            # same millisecond: pick the first non-existing suffix so every
            # corrupt copy is preserved distinctly.
            quarantine_path = base
            attempt = 1
            while os.path.exists(quarantine_path):
                quarantine_path = f"{base}-{attempt}"
                attempt += 1
            os.replace(filepath, quarantine_path)
            return quarantine_path
        except OSError as e:  # pragma: no cover - defensive
            logger.error("Failed to quarantine corrupt session %s: %s", filepath, e)
            return None

    def _fire_corruption_hook(
        self, session_id: str, error: str, quarantine_path: Optional[str]
    ) -> None:
        """Surface a corrupt-session read via ``SESSION_PERSIST_FAILED``.

        Reuses the existing persistence-failure observability seam so a silent
        corruption reset becomes a recorded non-outcome. Fully guarded and a
        no-op when no such hook is registered (zero overhead).
        """
        try:
            from ..hooks.registry import get_default_registry
            from ..hooks.types import HookEvent

            registry = get_default_registry()
            if not registry.has_hooks(HookEvent.SESSION_PERSIST_FAILED):
                return

            from ..hooks.events import SessionPersistFailedInput
            from ..hooks.runner import HookRunner

            event_input = SessionPersistFailedInput(
                session_id=session_id,
                cwd=os.getcwd(),
                event_name=HookEvent.SESSION_PERSIST_FAILED.value,
                timestamp=datetime.now(timezone.utc).isoformat(),
                role="",
                content="",
                error=f"corrupt session file: {error}",
                spilled=quarantine_path is not None,
                spill_path=quarantine_path,
            )
            HookRunner(registry).execute_sync(
                HookEvent.SESSION_PERSIST_FAILED, event_input
            )
        except Exception:  # pragma: no cover - observability must never break load
            logger.debug("SESSION corruption hook failed", exc_info=True)

    def _atomic_write_json(self, filepath: str, data: Any) -> bool:
        """Atomically write JSON data to disk (temp file + os.replace)."""
        temp_path = None
        try:
            dir_path = os.path.dirname(filepath) or "."
            os.makedirs(dir_path, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=dir_path,
                delete=False,
                suffix=".tmp",
            ) as f:
                temp_path = f.name
                json.dump(data, f, indent=2, ensure_ascii=False)

            os.replace(temp_path, filepath)
            return True
        except (IOError, OSError, TypeError, ValueError) as e:
            logger.error(f"Atomic write failed for {filepath}: {e}")
            try:
                if temp_path is not None:
                    os.remove(temp_path)
            except (IOError, OSError):
                pass
            return False

    def _spill_dir(self) -> str:
        """Directory for last-resort salvage files (Issue #3597)."""
        from ..paths import get_session_spill_dir
        return str(get_session_spill_dir())

    def _spill(
        self, session_id: str, messages: List["SessionMessage"]
    ) -> Optional[str]:
        """Salvage already-produced turns to an atomic fallback file.

        On a durable-write failure the message survives only in memory; this
        writes it to ``~/.praisonai/state/session_spill/*.json`` (0600, temp
        file + ``os.replace`` + best-effort dir fsync) so a shutdown/crash does
        not silently lose it. Stdlib-only and best-effort: any failure here is
        swallowed (the caller already returns False and fires the hook).

        Returns the spill file path on success, else ``None``.
        """
        if not messages:
            return None
        try:
            spill_dir = self._spill_dir()
            os.makedirs(spill_dir, exist_ok=True)
            safe_id = "".join(
                c if c.isalnum() or c in "-_" else "_" for c in session_id
            )
            # A monotonic ms timestamp keeps files sortable/attributable, but a
            # short random token guarantees uniqueness so consecutive failures
            # within the same PID+millisecond never overwrite an earlier spill
            # (each unpersisted turn keeps its own recoverable file).
            unique = os.urandom(4).hex()
            filename = (
                f"{safe_id}.{int(time.time() * 1000)}.{os.getpid()}.{unique}.json"
            )
            filepath = os.path.join(spill_dir, filename)
            payload = {
                "session_id": session_id,
                "spilled_at": datetime.now(timezone.utc).isoformat(),
                "messages": [m.to_dict() for m in messages],
            }
            fd, temp_path = tempfile.mkstemp(dir=spill_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.chmod(temp_path, 0o600)
                except OSError:
                    pass
                os.replace(temp_path, filepath)
                temp_path = None
            finally:
                if temp_path is not None:
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
            # Best-effort directory fsync so the rename is durable.
            try:
                dir_fd = os.open(spill_dir, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
            return filepath
        except (IOError, OSError, TypeError, ValueError) as e:
            logger.error(f"Session spill failed for {session_id}: {e}")
            return None

    def _fire_persist_failed_hook(
        self,
        session_id: str,
        message: "SessionMessage",
        error: str,
        spill_path: Optional[str],
    ) -> None:
        """Emit SESSION_PERSIST_FAILED so a silent failure is observable.

        Best-effort and fully guarded: hooks are optional and must never turn a
        persistence failure into a raised exception on the caller's hot path.
        Skipped entirely when no such hook is registered (zero overhead).
        """
        try:
            from ..hooks.registry import get_default_registry
            from ..hooks.types import HookEvent

            registry = get_default_registry()
            if not registry.has_hooks(HookEvent.SESSION_PERSIST_FAILED):
                return

            from ..hooks.events import SessionPersistFailedInput
            from ..hooks.runner import HookRunner

            event_input = SessionPersistFailedInput(
                session_id=session_id,
                cwd=os.getcwd(),
                event_name=HookEvent.SESSION_PERSIST_FAILED.value,
                timestamp=datetime.now(timezone.utc).isoformat(),
                role=message.role,
                content=message.content,
                error=error,
                spilled=spill_path is not None,
                spill_path=spill_path,
            )
            HookRunner(registry).execute_sync(
                HookEvent.SESSION_PERSIST_FAILED, event_input
            )
        except Exception:  # pragma: no cover - observability must never break persistence
            logger.debug("SESSION_PERSIST_FAILED hook failed", exc_info=True)

    def _on_write_failure(
        self, session_id: str, messages: List["SessionMessage"], error: str
    ) -> None:
        """Spill salvage + fire the observability hook on a durable-write failure."""
        if not messages:
            return
        spill_path = self._spill(session_id, messages)
        self._fire_persist_failed_hook(
            session_id, messages[-1], error, spill_path
        )

    def _reingest_spill(self, session_id: str, session: SessionData) -> None:
        """Re-ingest any spilled turns for a session on load (Issue #3597).

        Merges salvaged messages that are not already present (matched on
        role+content+timestamp) back into the loaded session, then persists and
        deletes each spill file only after it is successfully folded in. Fully
        guarded: a failure here must never break loading a session.
        """
        try:
            spill_dir = self._spill_dir()
            if not os.path.isdir(spill_dir):
                return
            safe_id = "".join(
                c if c.isalnum() or c in "-_" else "_" for c in session_id
            )
            prefix = f"{safe_id}."
            candidates = sorted(
                f for f in os.listdir(spill_dir)
                if f.startswith(prefix) and f.endswith(".json")
            )
        except (IOError, OSError):
            return

        seen = {
            (m.role, m.content, m.timestamp) for m in session.messages
        }
        recovered: List[tuple] = []  # (filepath, [SessionMessage])
        for filename in candidates:
            filepath = os.path.join(spill_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError, OSError):
                continue
            # A syntactically valid spill can still carry an unexpected shape
            # (non-object root, non-list messages, non-object message). Guard
            # each level so one malformed spill can't raise AttributeError /
            # TypeError and block recovery of the rest.
            if not isinstance(data, dict):
                continue
            if data.get("session_id") != session_id:
                continue
            raw_messages = data.get("messages")
            if not isinstance(raw_messages, list):
                continue
            msgs = []
            for raw in raw_messages:
                if not isinstance(raw, dict):
                    continue
                msg = SessionMessage.from_dict(raw)
                key = (msg.role, msg.content, msg.timestamp)
                if key in seen:
                    continue
                seen.add(key)
                msgs.append(msg)
            recovered.append((filepath, msgs))

        if not recovered:
            return

        new_messages = [m for _, msgs in recovered for m in msgs]
        if new_messages:
            session.messages.extend(new_messages)
            filepath = self._get_session_path(session_id)
            session.updated_at = datetime.now(timezone.utc).isoformat()
            # Recovered turns extend the active window like any other append, so
            # they must go through the same retention policy (compact/truncate)
            # every ordinary write uses — otherwise recovery could persist and
            # expose an oversized transcript that stays inconsistent until a
            # later mutation happens to compact it.
            self._enforce_window(session)
            if not self._atomic_write_json(filepath, session.to_dict()):
                # Could not fold the salvage back in durably — leave the spill
                # files in place so a later load can retry.
                return

        # Persisted (or nothing new to persist) — delete the consumed spills.
        for filepath, _ in recovered:
            try:
                os.remove(filepath)
            except OSError:
                pass

    def _modify_session_locked(
        self,
        session_id: str,
        mutator: Callable[[SessionData], None],
        *,
        error_label: str = "modify session",
    ) -> bool:
        """Apply mutator after reloading from disk under FileLock."""
        filepath = self._get_session_path(session_id)

        with FileLock(filepath, self.lock_timeout):
            try:
                session = self._load_session_from_disk(session_id, filepath)
            except OSError:
                # Transient read failure — abort rather than overwrite the
                # existing (still valid) session file with partial data.
                logger.error(f"Failed to {error_label} {session_id}: could not read existing session")
                return False
            mutator(session)
            session.updated_at = datetime.now(timezone.utc).isoformat()

            self._enforce_window(session)

            if not self._atomic_write_json(filepath, session.to_dict()):
                logger.error(f"Failed to {error_label} {session_id}")
                return False

            with self._lock:
                self._cache[session_id] = session

            return True
    
    def _save_session(self, session: SessionData) -> bool:
        """Save session to disk with atomic write."""
        filepath = self._get_session_path(session.session_id)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        
        # Apply retention policy to the active window (Issue #2709)
        self._enforce_window(session)
        
        with FileLock(filepath, self.lock_timeout):
            if not self._atomic_write_json(filepath, session.to_dict()):
                logger.error(f"Failed to save session {session.session_id}")
                return False
            return True
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        tool_call_id: Optional[str] = None,
    ) -> bool:
        """
        Add a message to a session.
        
        Args:
            session_id: The session ID.
            role: Message role ("user", "assistant", "system", "tool").
            content: Message content.
            metadata: Optional metadata.
            tool_calls: Optional structured tool calls for an assistant turn
                (Issue #3089), each ``{"id", "type", "function": {...}}``.
            tool_call_id: Optional id linking a ``role="tool"`` result turn
                back to the assistant tool call it answers (Issue #3089).
            
        Returns:
            True if saved successfully.
        """
        filepath = self._get_session_path(session_id)
        
        message = SessionMessage(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
        )
        
        # Use file lock for atomic read-modify-write
        with FileLock(filepath, self.lock_timeout):
            # Always reload from disk inside lock to avoid race conditions.
            # A transient read error must NOT be collapsed into an empty
            # session here, or appending this one message and writing would
            # permanently destroy all prior history while reporting success.
            try:
                session = self._load_session_from_disk(session_id, filepath)
            except OSError as e:
                logger.error(
                    f"Failed to save session {session_id}: could not read existing session"
                )
                # Issue #3597: the read failed, so the durable file is intact
                # but this turn is unpersisted — salvage it and signal instead
                # of losing it silently.
                self._on_write_failure(session_id, [message], str(e))
                return False

            # Add message
            session.messages.append(message)
            session.updated_at = datetime.now(timezone.utc).isoformat()
            
            # Apply retention policy to the active window (Issue #2709)
            self._enforce_window(session)
            
            # Write atomically
            if not self._atomic_write_json(filepath, session.to_dict()):
                logger.error(f"Failed to save session {session_id}")
                # Issue #3597: durable write failed (disk-full / corruption).
                # Spill just this turn to a fallback file and fire the
                # SESSION_PERSIST_FAILED hook so the loss is observable and
                # recoverable on next load.
                self._on_write_failure(session_id, [message], "atomic write failed")
                return False

            # Update cache
            with self._lock:
                self._cache[session_id] = session

        # Local write succeeded → mirror the new record (non-blocking, off the
        # lock). A mirror outage never reaches here as a failure (Issue #3646).
        self._mirror_append(session_id, [message])
        return True

    def _mirror_append(
        self, session_id: str, messages: List["SessionMessage"]
    ) -> None:
        """Hand newly persisted messages to the background mirror writer.

        No-op (zero overhead) when no mirror is configured. Records are the
        message dicts tagged with a stable per-record id so re-appends are
        idempotent (last-writer per id) — the append-only, conflict-free shape
        the mirror protocol expects (Issue #3646).
        """
        writer = self._mirror_writer
        if writer is None or not messages:
            return
        records = []
        for m in messages:
            record = m.to_dict()
            record.setdefault(
                "id", f"{session_id}:{record.get('timestamp', time.time())}"
            )
            record["session_id"] = session_id
            records.append(record)
        writer.enqueue(session_id, records)

    def flush_mirror(self, timeout: Optional[float] = None) -> bool:
        """Block until queued mirror records are flushed.

        Returns ``True`` immediately when no mirror is configured; otherwise
        drains the background queue (bounded by ``timeout`` when given). Handy
        for a future ``session sync`` and for deterministic tests.
        """
        writer = self._mirror_writer
        if writer is None:
            return True
        return writer.flush(timeout)

    def close_mirror(self) -> None:
        """Stop the background mirror writer, draining queued records first."""
        writer = self._mirror_writer
        if writer is not None:
            writer.close()

    def add_user_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a user message to a session."""
        return self.add_message(session_id, "user", content, metadata)
    
    def add_assistant_message(
        self,
        session_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add an assistant message to a session."""
        return self.add_message(session_id, "assistant", content, metadata)
    
    def get_chat_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        Get chat history for a session in LLM-compatible format.
        
        Args:
            session_id: The session ID.
            max_messages: Maximum messages to return (defaults to store limit).
            
        Returns:
            List of {"role": "user/assistant", "content": "..."} dicts.
        """
        session = self._read_session_fresh(session_id)
        # The active window is already bounded on write by the retention policy
        # (compact/truncate) or intentionally unbounded (keep_all), so by
        # default we return the full stored window rather than re-capping it at
        # the legacy max_messages tail — that silent tail-cap was the defect in
        # Issue #2709. Explicit max_messages still overrides.
        return session.get_chat_history(max_messages)
    
    def get_session(self, session_id: str) -> SessionData:
        """Get full session data."""
        return self._read_session_fresh(session_id)

    def get_session_model(self, session_id: str) -> Optional[str]:
        """Return the model a session was created / last run with (Issue #3685).

        Resolves the session-level model recorded in metadata (written by the
        wrapper's session-continuity path as ``metadata["model"]``); if absent,
        falls back to the most recent turn that carried a ``model`` in its own
        metadata. Returns ``None`` when no model was ever recorded, so a caller
        can fall back to default model resolution.

        This lets a resume read "the model this session used" without scanning
        or re-resolving the current default, so a change to the user's default
        between runs no longer silently switches the model mid-conversation.
        """
        try:
            session = self._read_session_fresh(session_id)
        except Exception:
            return None
        model = session.metadata.get("model") or session.metadata.get("llm")
        if isinstance(model, str) and model:
            return model
        for message in reversed(session.messages):
            recorded = (message.metadata or {}).get("model")
            if isinstance(recorded, str) and recorded:
                return recorded
        return None

    def get_session_reasoning_effort(self, session_id: str) -> Optional[str]:
        """Return the reasoning effort a session was last run with (Issue #4452).

        Mirrors :meth:`get_session_model`: resolves the session-level
        ``reasoning_effort`` recorded in metadata so a resume (``--continue`` /
        ``--session``) can restore the graded effort alongside the model. Returns
        ``None`` when none was recorded, so a caller falls back to the default /
        per-invocation value.
        """
        try:
            session = self._read_session_fresh(session_id)
        except Exception:
            return None
        effort = session.metadata.get("reasoning_effort")
        if isinstance(effort, str) and effort:
            return effort
        for message in reversed(session.messages):
            recorded = (message.metadata or {}).get("reasoning_effort")
            if isinstance(recorded, str) and recorded:
                return recorded
        return None

    def set_agent_info(
        self,
        session_id: str,
        agent_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Set agent info for a session."""

        def _apply(session: SessionData) -> None:
            if agent_name:
                session.agent_name = agent_name
            if user_id:
                session.user_id = user_id

        return self._modify_session_locked(
            session_id, _apply, error_label="set agent info for session"
        )
    
    def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session."""

        def _apply(session: SessionData) -> None:
            session.messages.clear()
            # Issue #2741: drop the compaction anchor too so a subsequently
            # rebuilt transcript is not misread as a compacted tail.
            session.last_compaction = None

        return self._modify_session_locked(
            session_id, _apply, error_label="clear session"
        )

    def set_chat_history(
        self,
        session_id: str,
        messages: List[Dict[str, str]],
    ) -> bool:
        """Replace session messages atomically (file-locked read-modify-write)."""

        # Capture the built messages so a configured mirror sees whole-transcript
        # replacements too (Issue #3646). The Session API's ``save_state`` and the
        # bot session manager persist history through this path, not
        # ``add_message`` — mirroring only there would omit that history remotely.
        built: List["SessionMessage"] = []

        def _apply(session: SessionData) -> None:
            session.messages.clear()
            built.clear()
            # Issue #2741: replacing the whole transcript invalidates any prior
            # compaction anchor (its message_index no longer maps to these
            # messages). Clear it so get_working_history returns the full new
            # history instead of clamping to an empty tail and dropping messages.
            session.last_compaction = None
            for msg in messages:
                sm = SessionMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content", "") or "",
                    timestamp=msg.get("timestamp", time.time()),
                    metadata=msg.get("metadata", {}),
                    # Preserve tool turns on whole-transcript saves (#3089).
                    tool_calls=msg.get("tool_calls"),
                    tool_call_id=msg.get("tool_call_id"),
                )
                session.messages.append(sm)
                built.append(sm)

        ok = self._modify_session_locked(
            session_id, _apply, error_label="set chat history"
        )
        if ok:
            # Mirror the replaced transcript (non-blocking, off the lock). Records
            # carry a stable ``id`` so a re-append is idempotent last-writer per
            # id — the append-only, conflict-free shape the mirror expects.
            self._mirror_append(session_id, built)
        return ok

    def append_compaction_checkpoint(
        self,
        session_id: str,
        summary: str,
        *,
        role: str = "system",
        tokens_before: int = 0,
        tokens_after: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Persist a compaction checkpoint so resume is cheap (Issue #2741).

        Records the summary produced by an in-run ``compact_conversation`` and
        anchors it to the current end of the persisted transcript. On resume,
        :meth:`get_working_history` replays this summary followed by any
        messages appended afterward, instead of the full raw log.

        Backward compatible: sessions without a checkpoint resume from raw
        messages exactly as before.

        A blank/whitespace-only summary is treated as a no-op so we never
        replay an empty ``{"role": "system", "content": ""}`` message into the
        LLM context on resume.
        """
        summary = summary or ""
        if not summary.strip():
            return False

        def _apply(session: SessionData) -> None:
            session.last_compaction = CompactionCheckpoint(
                summary=summary,
                message_index=len(session.messages),
                role=role,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                metadata=metadata or {},
            )

        return self._modify_session_locked(
            session_id, _apply, error_label="append compaction checkpoint"
        )

    def get_working_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Get compacted working history for cheap resume (Issue #2741).

        Uses the latest compaction checkpoint when present (summary + retained
        tail); otherwise falls back to raw chat history for backward
        compatibility.
        """
        session = self._read_session_fresh(session_id)
        limit = max_messages or self.max_messages
        return session.get_working_history(limit)

    def update_session_metadata(self, session_id: str, **fields: Any) -> bool:
        """Merge run stats / metadata fields into a persisted session."""
        if not fields:
            return True

        def _apply(session: SessionData) -> None:
            for key, value in fields.items():
                if value is None:
                    continue
                session.metadata[key] = value
                if key in ("agent_id", "agent_name", "user_id"):
                    setattr(session, key, value)

        return self._modify_session_locked(
            session_id, _apply, error_label="update session metadata"
        )

    def rename_session(self, session_id: str, title: str) -> bool:
        """Give a session a human-readable title (Issue #3737).

        Stores the title in ``metadata["title"]`` via the locked read-modify-write
        path so ``session list`` / ``/sessions`` can display a friendly name
        instead of an opaque id. Passing an empty/whitespace-only title clears
        any existing title (falling back to the derived snippet on display).
        Backward compatible: sessions without a title keep resolving by id.
        """
        title = (title or "").strip()

        def _apply(session: SessionData) -> None:
            if title:
                session.metadata["title"] = title
            else:
                session.metadata.pop("title", None)

        return self._modify_session_locked(
            session_id, _apply, error_label="rename session"
        )

    def delete_session(self, session_id: str) -> bool:
        """Delete a session completely."""
        filepath = self._get_session_path(session_id)
        
        with self._lock:
            if session_id in self._cache:
                del self._cache[session_id]
        
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List all sessions with metadata."""
        sessions = []
        
        try:
            for filename in os.listdir(self.session_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.session_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        sessions.append({
                            "session_id": data.get("session_id", filename[:-5]),
                            "id": data.get("session_id", filename[:-5]),
                            "agent_name": data.get("agent_name"),
                            # Human-readable title set via `session rename` /
                            # `/rename` (Issue #3737); None when never renamed.
                            "title": (data.get("metadata") or {}).get("title"),
                            "agent_id": data.get("agent_id") or (data.get("metadata") or {}).get("agent_id"),
                            "source": data.get("source") or (data.get("metadata") or {}).get("source"),
                            # Surface parentage so callers can distinguish root
                            # sessions from sub-agent/forked children (Issue #2655).
                            "parent_id": data.get("parent_id") or (data.get("metadata") or {}).get("parent_id"),
                            "parent_session_id": data.get("parent_session_id") or (data.get("metadata") or {}).get("parent_session_id"),
                            # Surface the agent_key tag written by Session._save_agent_chat_histories
                            # so bulk restore resolves it exactly (no prefix-parse ambiguity).
                            "agent_key": data.get("agent_key") or (data.get("metadata") or {}).get("agent_key"),
                            "created_at": data.get("created_at"),
                            "updated_at": data.get("updated_at"),
                            "message_count": len(data.get("messages", [])),
                            "model": data.get("model") or data.get("llm") or (data.get("metadata") or {}).get("model"),
                            "total_tokens": data.get("total_tokens") or data.get("token_count") or (data.get("metadata") or {}).get("total_tokens"),
                            "cost": data.get("cost") or (data.get("metadata") or {}).get("cost"),
                        })
                    except (json.JSONDecodeError, IOError):
                        continue
        except (IOError, OSError):
            pass
        
        # Sort by updated_at descending
        sessions.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return sessions[:limit]
    
    # ── Agent-Level Queries (Gap S4) ──────────────────────────────────
    
    def list_sessions_by_agent(self, agent_name: str, limit: int = 50) -> List[str]:
        """List session IDs for a specific agent.
        
        Gap S4: Enables querying sessions by agent instead of just session ID.
        
        Args:
            agent_name: The agent name to filter by
            limit: Maximum number of session IDs to return
            
        Returns:
            List of session IDs belonging to the specified agent
        """
        session_ids = []
        
        try:
            for filename in os.listdir(self.session_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.session_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if data.get("agent_name") == agent_name:
                            session_ids.append(data.get("session_id", filename[:-5]))
                    except (json.JSONDecodeError, IOError):
                        continue
        except (IOError, OSError):
            pass
        
        return session_ids[:limit]
    
    def get_sessions_by_agent(
        self,
        agent_name: str,
        limit: int = 10,
    ) -> List[SessionData]:
        """Get full session data for a specific agent.
        
        Gap S4: Enables retrieving all sessions for an agent.
        
        Args:
            agent_name: The agent name to filter by
            limit: Maximum number of sessions to return
            
        Returns:
            List of SessionData objects for the specified agent
        """
        session_ids = self.list_sessions_by_agent(agent_name, limit)
        return [self._read_session_fresh(sid) for sid in session_ids]
    
    def get_agent_chat_history(
        self,
        agent_name: str,
        max_messages: Optional[int] = None,
        max_sessions: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get combined chat history across all sessions for an agent.
        
        Gap S4: Enables retrieving conversation history by agent.
        
        Args:
            agent_name: The agent name to filter by
            max_messages: Maximum messages per session
            max_sessions: Maximum number of sessions to include
            
        Returns:
            List of messages with session context
        """
        sessions = self.get_sessions_by_agent(agent_name, max_sessions)
        messages = []
        
        for session in sessions:
            history = session.get_chat_history(max_messages)
            for msg in history:
                messages.append({
                    **msg,
                    "session_id": session.session_id,
                    "agent_name": agent_name,
                })
        
        return messages
    
    # ── Gateway Integration (Gap S3) ──────────────────────────────────
    
    def set_gateway_info(
        self,
        session_id: str,
        gateway_session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> bool:
        """Link a session to a gateway session.
        
        Gap S3: Enables memory to be scoped to gateway agents/sessions.
        
        Args:
            session_id: The local session ID
            gateway_session_id: The gateway session ID to link to
            agent_id: The gateway agent ID
            
        Returns:
            True if saved successfully
        """
        def _apply(session: SessionData) -> None:
            if gateway_session_id:
                session.gateway_session_id = gateway_session_id
            if agent_id:
                session.agent_id = agent_id

        return self._modify_session_locked(
            session_id, _apply, error_label="set gateway info for session"
        )
    
    def get_by_gateway_session(self, gateway_session_id: str) -> Optional[SessionData]:
        """Get session data linked to a gateway session.
        
        Gap S3: Enables retrieving memory by gateway session ID.
        
        Args:
            gateway_session_id: The gateway session ID to look up
            
        Returns:
            SessionData if found, None otherwise
        """
        try:
            for filename in os.listdir(self.session_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.session_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if data.get("gateway_session_id") == gateway_session_id:
                            return SessionData.from_dict(data)
                    except (json.JSONDecodeError, IOError):
                        continue
        except (IOError, OSError):
            pass
        
        return None
    
    def list_sessions_by_gateway_agent(self, agent_id: str, limit: int = 50) -> List[str]:
        """List session IDs linked to a gateway agent.
        
        Gap S3: Enables querying sessions by gateway agent ID.
        
        Args:
            agent_id: The gateway agent ID to filter by
            limit: Maximum number of session IDs to return
            
        Returns:
            List of session IDs linked to the gateway agent
        """
        session_ids = []
        
        try:
            for filename in os.listdir(self.session_dir):
                if filename.endswith(".json"):
                    filepath = os.path.join(self.session_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        if data.get("agent_id") == agent_id:
                            session_ids.append(data.get("session_id", filename[:-5]))
                    except (json.JSONDecodeError, IOError):
                        continue
        except (IOError, OSError):
            pass
        
        return session_ids[:limit]
    
    # ── Cross-Session Recall (Issue #2184) ────────────────────────────
    #
    # Lets an agent search its *own* past conversation transcripts:
    #   - search(query)  → discovery: top matching sessions with context
    #   - window(...)     → scroll: ±N messages around an anchor message
    #   - recent()        → browse: most recent sessions ("what was I doing?")
    #
    # Dependency-free substring/keyword scan over stored sessions. A wrapper
    # may provide a real FTS5/SQLite index for scale.

    @staticmethod
    def _session_title(data: Dict[str, Any]) -> str:
        """Derive a short human-friendly title for a session.

        An explicit title set via ``rename_session`` (Issue #3737) wins; then the
        agent name; then the first user message snippet; finally the id.
        """
        explicit = (data.get("metadata") or {}).get("title")
        if explicit:
            return str(explicit)
        agent_name = data.get("agent_name")
        if agent_name:
            return str(agent_name)
        messages = data.get("messages", [])
        if isinstance(messages, list):
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                if msg.get("role") == "user" and msg.get("content"):
                    text = " ".join(str(msg["content"]).split())
                    return text[:60]
        return str(data.get("session_id", ""))

    # Number of leading/trailing user+assistant messages returned as
    # "bookends" so a discovery hit reconstructs goal → match → resolution.
    BOOKEND_SIZE = 2
    # Sessions whose per-message rate exceeds this (messages / hour of span)
    # are treated as high-volume automated runs and demoted in ranking so
    # they cannot crowd a user's interactive history out of the top results.
    AUTOMATED_RATE_THRESHOLD = 60.0
    AUTOMATED_DEMOTION = 0.25  # multiply score by this when demoted

    @staticmethod
    def _is_automated_session(data: Dict[str, Any], messages: List[Any]) -> bool:
        """Heuristically decide if a session is a high-volume automated run.

        A session is treated as automated when it is explicitly tagged
        (``source``/``metadata.source`` in {scheduled, automated, cron, system})
        or when its message rate far exceeds interactive pace.
        """
        source = str(
            data.get("source")
            or (data.get("metadata") or {}).get("source")
            or ""
        ).lower()
        if source in {"scheduled", "automated", "cron", "system", "batch"}:
            return True
        if (data.get("metadata") or {}).get("automated") is True:
            return True

        if len(messages) < 4:
            return False
        try:
            stamps = [
                float(m.get("timestamp"))
                for m in messages
                if isinstance(m, dict) and m.get("timestamp") is not None
            ]
        except (TypeError, ValueError):
            return False
        if len(stamps) < 4:
            return False
        span_hours = (max(stamps) - min(stamps)) / 3600.0
        if span_hours <= 0:
            return False
        return (len(stamps) / span_hours) > DefaultSessionStore.AUTOMATED_RATE_THRESHOLD

    @staticmethod
    def _lineage_key(data: Dict[str, Any]) -> Optional[str]:
        """Return a stable lineage id so reset/compacted continuations of one
        conversation collapse to a single hit. ``None`` if no lineage is known.

        Only *chain* identifiers are used: ``lineage_id``, ``root_session_id``
        and ``thread_id`` each identify a single continuation chain. We
        deliberately exclude ``parent_session_id`` — it points at an *immediate*
        parent, so two independent children forked from the same parent would
        otherwise share a key and suppress each other in results (they are
        distinct conversations, not a reset/compaction of one).
        """
        meta = data.get("metadata") or {}
        for key in ("lineage_id", "root_session_id", "thread_id"):
            val = data.get(key) or meta.get(key)
            if val:
                return str(val)
        return None

    @staticmethod
    def _bookends(messages: List[Any], size: int) -> Dict[str, List[Dict[str, Any]]]:
        """Return the first and last ``size`` user/assistant messages."""
        convo = [
            {
                "index": i,
                "role": m.get("role", ""),
                "content": m.get("content", ""),
                "timestamp": m.get("timestamp"),
            }
            for i, m in enumerate(messages)
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        ]
        if not convo:
            return {}
        opening = convo[:size]
        closing = convo[-size:]
        # Avoid duplicating messages in short sessions.
        if len(convo) <= size:
            closing = []
        return {"opening": opening, "closing": closing}

    @staticmethod
    def _make_snippet(content: str, query: str, width: int = 120) -> str:
        """Build a short snippet centred on the first query match."""
        text = " ".join(str(content).split())
        pos = text.lower().find(query.lower())
        if pos < 0:
            return text[:width]
        start = max(0, pos - width // 2)
        end = min(len(text), start + width)
        snippet = text[start:end]
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet = snippet + "…"
        return snippet

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        window: int = 5,
    ) -> List["SessionHit"]:
        """Full-text search across stored session transcripts.

        Returns the best-matching sessions, each with a short window of
        messages around the first hit so the match is returned *in context*.
        """
        from .protocols import SessionHit

        query = (query or "").strip()
        if not query:
            return []

        needle = query.lower()
        terms = [t for t in needle.split() if t]
        hits: List[tuple] = []

        try:
            filenames = os.listdir(self.session_dir)
        except (IOError, OSError):
            return []

        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.session_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                continue

            messages = data.get("messages", [])
            if not isinstance(messages, list):
                continue
            best_index = -1
            best_score = 0.0
            total_score = 0.0
            for idx, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    continue
                content = str(msg.get("content", ""))
                if not content:
                    continue
                lowered = content.lower()
                score = 0.0
                if needle in lowered:
                    score += 2.0
                score += sum(1.0 for term in terms if term in lowered)
                total_score += score
                if score > best_score:
                    best_score = score
                    best_index = idx

            if best_index < 0:
                continue

            start = max(0, best_index - window)
            end = min(len(messages), best_index + window + 1)
            context = []
            for i in range(start, end):
                msg_i = messages[i]
                if not isinstance(msg_i, dict):
                    continue
                context.append(
                    {
                        "index": i,
                        "role": msg_i.get("role", ""),
                        "content": msg_i.get("content", ""),
                        "timestamp": msg_i.get("timestamp"),
                    }
                )

            # Recall ranking: demote high-volume automated sessions so they
            # can't crowd a user's interactive history out of the top results.
            if self._is_automated_session(data, messages):
                total_score *= self.AUTOMATED_DEMOTION

            hit = SessionHit(
                session_id=data.get("session_id", filename[:-5]),
                title=self._session_title(data),
                when=data.get("updated_at") or data.get("created_at"),
                snippet=self._make_snippet(
                    messages[best_index].get("content", ""), query
                ),
                score=total_score,
                anchor_index=best_index,
                messages=context,
                bookends=self._bookends(messages, self.BOOKEND_SIZE),
            )
            hit_lineage = self._lineage_key(data)
            hits.append((hit_lineage, hit))

        hits.sort(key=lambda item: (item[1].score, item[1].when or ""), reverse=True)

        # Lineage-aware dedup: a reset/compacted continuation of a conversation
        # collapses to a single (best-scoring) hit.
        deduped: List[SessionHit] = []
        seen_lineage: set = set()
        for lineage, hit in hits:
            if lineage is not None:
                if lineage in seen_lineage:
                    continue
                seen_lineage.add(lineage)
            deduped.append(hit)
            if len(deduped) >= limit:
                break
        return deduped

    def window(
        self,
        session_id: str,
        around_message_id: Optional[str] = None,
        *,
        window: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return ±``window`` messages around an anchor message in a session."""
        session = self._read_session_fresh(session_id)
        messages = session.messages
        if not messages:
            return []

        anchor = len(messages) - 1
        if around_message_id is not None and str(around_message_id) != "":
            try:
                anchor = int(around_message_id)
            except (TypeError, ValueError):
                anchor = len(messages) - 1
        anchor = max(0, min(anchor, len(messages) - 1))

        start = max(0, anchor - window)
        end = min(len(messages), anchor + window + 1)
        return [
            {
                "index": i,
                "role": messages[i].role,
                "content": messages[i].content,
                "timestamp": messages[i].timestamp,
            }
            for i in range(start, end)
        ]

    def recent(self, *, limit: int = 10) -> List["SessionSummary"]:
        """Return the most recently updated sessions (browse mode)."""
        from .protocols import SessionSummary

        summaries = [
            SessionSummary(
                session_id=s.get("session_id", ""),
                title=s.get("agent_name") or s.get("session_id", ""),
                when=s.get("updated_at") or s.get("created_at"),
                message_count=s.get("message_count", 0),
            )
            for s in self.list_sessions(limit=limit)
        ]
        return summaries

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        filepath = self._get_session_path(session_id)
        return os.path.exists(filepath)

    # ── Portable export / import / migration (Issue #4267) ────────────────
    #
    # Store-agnostic backup/restore/migration for the gateway's own store.
    # The payload is a simple, versioned envelope carrying the same portable
    # session dicts that ``SessionData.to_dict`` already produces, so it
    # round-trips through ``from_dict`` and is symmetric across the built-in
    # stores (``SqliteSessionStore`` inherits this behaviour unchanged).

    # Bumped only on a breaking payload-shape change; import tolerates older/
    # unversioned payloads (best-effort) rather than rejecting them.
    PORTABLE_VERSION = 1

    # Live routing / activity fields cleared on import (unless opted out) so a
    # restored record is inert until re-bound and cannot masquerade as an active
    # connection. Kept intentionally small: transcript + identity survive; only
    # the gateway's live wiring is reset.
    _LIVE_FIELDS = ("gateway_session_id", "agent_id")

    def export_session(
        self, session_id: str, *, include_lineage: bool = True
    ) -> Dict[str, Any]:
        """Export a single session to a portable, versioned payload.

        Reuses the existing ``SessionData.to_dict`` shape (so the payload
        round-trips through ``import_sessions``). When ``include_lineage`` is
        set, any compacted/rotated ancestors sharing this session's lineage id
        are included so the conversation restores as one logical session.
        """
        session = self._read_session_fresh(session_id)
        if not self.session_exists(session_id):
            return {"version": self.PORTABLE_VERSION, "sessions": []}

        sessions = [session.to_dict()]
        if include_lineage:
            for extra in self._collect_lineage(session, exclude=session_id):
                sessions.append(extra)
        return {"version": self.PORTABLE_VERSION, "sessions": sessions}

    def export_all(self) -> Dict[str, Any]:
        """Export every stored session to a portable, versioned payload."""
        sessions: List[Dict[str, Any]] = []
        try:
            filenames = os.listdir(self.session_dir)
        except (IOError, OSError):
            filenames = []
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.session_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    sessions.append(json.load(f))
            except (json.JSONDecodeError, IOError, OSError):
                continue
        return {"version": self.PORTABLE_VERSION, "sessions": sessions}

    def _collect_lineage(
        self, session: SessionData, *, exclude: str
    ) -> List[Dict[str, Any]]:
        """Return other on-disk sessions sharing this session's lineage id.

        Uses the same *chain* identifiers as recall's lineage dedup
        (``lineage_id`` / ``root_session_id`` / ``thread_id``) so a compacted /
        rotated continuation exports alongside its logical session. Returns the
        raw session dicts (already portable). Empty when no lineage is known.
        """
        lineage = self._lineage_key(session.to_dict())
        if not lineage:
            return []
        out: List[Dict[str, Any]] = []
        try:
            filenames = os.listdir(self.session_dir)
        except (IOError, OSError):
            return []
        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(self.session_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError, OSError):
                continue
            if data.get("session_id") == exclude:
                continue
            if self._lineage_key(data) == lineage:
                out.append(data)
        return out

    def _save_imported_session(self, session: SessionData) -> bool:
        """Persist a restored session verbatim (no retention/window applied).

        Mirrors ``_save_session`` (timestamp + atomic, file-locked write) but
        deliberately skips ``_enforce_window`` so importing a valid larger
        export is not truncated/compacted by the destination's own retention
        settings before it lands on disk.
        """
        filepath = self._get_session_path(session.session_id)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        with FileLock(filepath, self.lock_timeout):
            if not self._atomic_write_json(filepath, session.to_dict()):
                logger.error(f"Failed to save imported session {session.session_id}")
                return False
            return True

    def import_sessions(
        self,
        payload: Dict[str, Any],
        *,
        max_sessions: int = 10_000,
        reset_live_fields: bool = True,
        overwrite: bool = False,
    ) -> "ImportReport":
        """Import sessions from an exported payload (hardened).

        Validates the payload shape, caps ingest at ``max_sessions``, skips
        malformed / duplicate records (reported, not silently dropped) and —
        unless opted out — resets live routing/activity fields so restored
        state is inert until re-bound.
        """
        from .protocols import ImportReport

        report = ImportReport(version=self.PORTABLE_VERSION)
        if not isinstance(payload, dict):
            return report
        # Reject payloads from a newer, breaking export format: a future shape
        # could otherwise slip through ``from_dict`` with silently defaulted
        # fields and corrupt restored state. Older/unversioned payloads are
        # still accepted (best-effort) since v1 is the compatible baseline.
        payload_version = payload.get("version")
        if isinstance(payload_version, int) and payload_version > self.PORTABLE_VERSION:
            report.skipped.append(
                {
                    "session_id": "",
                    "reason": (
                        f"unsupported payload version {payload_version} "
                        f"(supported <= {self.PORTABLE_VERSION})"
                    ),
                }
            )
            return report
        raw_sessions = payload.get("sessions")
        if not isinstance(raw_sessions, list):
            return report

        seen_ids: set = set()
        for index, raw in enumerate(raw_sessions):
            if report.imported >= max_sessions:
                report.skipped.append(
                    {"session_id": "", "reason": f"max_sessions={max_sessions} cap reached"}
                )
                # Everything after the cap is skipped for the same reason; stop.
                break
            if not isinstance(raw, dict):
                report.skipped.append(
                    {"session_id": "", "reason": f"malformed record at index {index}"}
                )
                continue
            session_id = str(raw.get("session_id") or "").strip()
            if not session_id:
                report.skipped.append(
                    {"session_id": "", "reason": f"missing session_id at index {index}"}
                )
                continue
            # Cycle / duplicate guard: the same id appearing twice in one payload
            # is ingested once (first wins) so a self-referential lineage export
            # cannot double-write.
            if session_id in seen_ids:
                report.skipped.append(
                    {"session_id": session_id, "reason": "duplicate in payload"}
                )
                continue
            seen_ids.add(session_id)

            if not overwrite and self.session_exists(session_id):
                report.skipped.append(
                    {"session_id": session_id, "reason": "already exists (use overwrite)"}
                )
                continue

            try:
                data = dict(raw)
                if reset_live_fields:
                    for field_name in self._LIVE_FIELDS:
                        data.pop(field_name, None)
                    meta = data.get("metadata")
                    if isinstance(meta, dict):
                        # Copy before mutating so the caller's payload (and any
                        # later import with reset_live_fields=False) keeps its
                        # original live fields intact (data = dict(raw) is shallow).
                        meta = dict(meta)
                        for field_name in self._LIVE_FIELDS:
                            meta.pop(field_name, None)
                        data["metadata"] = meta
                session = SessionData.from_dict(data)
                session.session_id = session_id
                # Persist the imported record verbatim: an import is a restore,
                # so the destination's retention/active_window must not truncate
                # or compact a valid larger export before it lands on disk.
                if not self._save_imported_session(session):
                    report.skipped.append(
                        {"session_id": session_id, "reason": "write failed"}
                    )
                    continue
                with self._lock:
                    self._cache[session_id] = session
                report.imported += 1
            except Exception as e:  # pragma: no cover - defensive; one bad record
                report.skipped.append(
                    {"session_id": session_id, "reason": f"import error: {e}"}
                )
        return report
    
    def invalidate_cache(self, session_id: Optional[str] = None) -> None:
        """Invalidate cache for a session or all sessions."""
        with self._lock:
            if session_id:
                self._cache.pop(session_id, None)
            else:
                self._cache.clear()
    
    # ── Runtime State Management (Issue #1943) ────────────────────────────
    # 
    # Runtime state mirroring allows native runtime to persist lightweight
    # execution artifacts for replay, debugging, and cross-turn mirroring.
    #
    # SIZE LIMITS & REDACTION POLICY:
    # - Keep runtime state lightweight (tool call IDs, not full outputs)
    # - Recommended max: 1KB per turn, 10KB per runtime
    # - Redact sensitive data (API keys, credentials, PII) before storage
    # - Use transcript slices, not full conversation history
    # - Consider compression for larger state objects
    
    def set_runtime_state(
        self, 
        session_id: str, 
        runtime_id: str, 
        turn_id: str, 
        state: Dict[str, Any],
        mirror_enabled: bool = True  # Default True for backward compatibility
    ) -> bool:
        """Set runtime state for a specific runtime and turn.
        
        Args:
            session_id: Session identifier
            runtime_id: Runtime identifier (e.g., "native", "plugin_harness") 
            turn_id: Turn identifier within the runtime
            state: Runtime state data (tool call ids, transcript slices, etc.)
                  Should be lightweight - avoid storing large outputs or sensitive data
            mirror_enabled: Whether runtime state mirroring is enabled (from SessionConfig.mirror_runtime_state)
                          Default True for backward compatibility. Set to False to skip storage.
            
        Returns:
            True if saved successfully (or skipped when mirror_enabled=False)
            
        Note:
            Keep state lightweight (<1KB per turn recommended). Redact sensitive
            data before storage. This is for handoff replay, not full state dumps.
        """
        # Honor the opt-in flag to avoid storage bloat
        if not mirror_enabled:
            return True  # Successfully "saved" (by not saving)
        
        def _apply(session: SessionData) -> None:
            if runtime_id not in session.runtime_state:
                session.runtime_state[runtime_id] = {}
            session.runtime_state[runtime_id][turn_id] = copy.deepcopy(state)

        return self._modify_session_locked(
            session_id, _apply, error_label="set runtime state"
        )
    
    def get_runtime_state(
        self, 
        session_id: str, 
        runtime_id: str, 
        turn_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get runtime state for a specific runtime and optionally a turn.
        
        Args:
            session_id: Session identifier
            runtime_id: Runtime identifier
            turn_id: Optional turn identifier (if None, returns all turns for runtime)
            
        Returns:
            Runtime state data
        """
        session = self._read_session_fresh(session_id)
        runtime_state = session.runtime_state.get(runtime_id, {})
        
        if turn_id is not None:
            return copy.deepcopy(runtime_state.get(turn_id, {}))
        
        return copy.deepcopy(runtime_state)
    
    def clear_runtime_state(
        self, 
        session_id: str, 
        runtime_id: Optional[str] = None
    ) -> bool:
        """Clear runtime state for a session, optionally filtered by runtime_id.
        
        Args:
            session_id: Session identifier
            runtime_id: Optional runtime identifier (if None, clears all runtime state)
            
        Returns:
            True if cleared successfully
        """
        def _apply(session: SessionData) -> None:
            if runtime_id is None:
                session.runtime_state.clear()
            else:
                session.runtime_state.pop(runtime_id, None)

        return self._modify_session_locked(
            session_id, _apply, error_label="clear runtime state"
        )

# Global session store instance (lazy initialized)
_default_store: Optional[DefaultSessionStore] = None
_store_lock = threading.Lock()

# Attribute stamped on any store this module auto-created, recording the session
# directory it was built for. A store injected by a caller
# (``store._default_store = my_store`` -- a widely used test/embedding hook)
# never carries this marker and so is honoured verbatim, while one we created
# ourselves is rebuilt when the resolved session directory changes.
#
# The marker lives on the *instance* rather than a single module-level identity
# pointer so a partial teardown that restores ``_default_store`` without also
# restoring an out-of-band tracking variable cannot misclassify a previously
# auto-created store as caller-injected (and pin it to a stale directory).
_AUTOCREATED_DIR_ATTR = "_praison_autocreated_session_dir"

def get_default_session_store() -> DefaultSessionStore:
    """Get the global default session store instance.

    Retention is non-destructive ("compact") by default. It can be overridden
    without code changes via environment variables so the same behaviour is
    reachable from CLI/YAML surfaces (Issue #2709):

    - ``PRAISONAI_SESSION_RETENTION``: ``compact`` | ``truncate`` | ``keep_all``
    - ``PRAISONAI_SESSION_ACTIVE_WINDOW``: int, recent turns kept live
    """
    global _default_store

    # The singleton is keyed on the *currently* resolved session directory. A
    # process that changes PRAISONAI_HOME (or a test that repoints
    # get_sessions_dir) must not keep reading and deleting sessions in the
    # directory that happened to be active when this module was first imported.
    resolved_dir = _resolve_default_session_dir()

    def _usable(candidate: Optional["DefaultSessionStore"]) -> bool:
        if candidate is None:
            return False
        # A store we auto-created carries a marker recording the directory it
        # was built for; only rebuild when that directory no longer matches.
        # Any store without the marker was injected by a caller -- honour it
        # verbatim (never second-guess an explicit ``_default_store = ...``).
        autocreated_dir = getattr(candidate, _AUTOCREATED_DIR_ATTR, None)
        if autocreated_dir is None:
            return True
        return autocreated_dir == resolved_dir

    store = _default_store
    if _usable(store):
        return store

    with _store_lock:
        store = _default_store
        if _usable(store):
            return store

        retention = os.environ.get("PRAISONAI_SESSION_RETENTION")
        active_window_env = os.environ.get("PRAISONAI_SESSION_ACTIVE_WINDOW")
        active_window: Optional[int] = None
        if active_window_env:
            try:
                active_window = int(active_window_env)
            except ValueError:
                logger.warning(
                    "Invalid PRAISONAI_SESSION_ACTIVE_WINDOW=%r; ignoring",
                    active_window_env,
                )
        try:
            _default_store = DefaultSessionStore(
                session_dir=resolved_dir,
                retention=retention,
                active_window=active_window,
            )
        except ValueError:
            logger.warning(
                "Invalid PRAISONAI_SESSION_RETENTION=%r; using default",
                retention,
            )
            _default_store = DefaultSessionStore(
                session_dir=resolved_dir,
                active_window=active_window,
            )
        # Stamp the auto-created store with the directory it was built for so a
        # later resolved-dir change rebuilds it, while a caller-injected store
        # (which never carries this marker) is always honoured verbatim.
        setattr(_default_store, _AUTOCREATED_DIR_ATTR, resolved_dir)

    return _default_store
