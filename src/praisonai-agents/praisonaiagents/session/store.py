"""
Default Session Store for PraisonAI Agents.

JSON-based session persistence with file locking and atomic writes.
Zero dependencies beyond stdlib.
"""

import copy
import json
import logging
from praisonaiagents._logging import get_logger
import os
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

# Default session directory (uses centralized paths - DRY)
DEFAULT_SESSION_DIR = str(get_sessions_dir())

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
        for key in ("model", "llm", "total_tokens", "token_count", "cost", "source"):
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
        return cls(
            session_id=data.get("session_id", ""),
            messages=messages,
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            agent_name=data.get("agent_name"),
            user_id=data.get("user_id"),
            metadata=data.get("metadata", {}),
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
        """
        self.session_dir = session_dir or DEFAULT_SESSION_DIR
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
        
        # Ensure session directory exists
        os.makedirs(self.session_dir, exist_ok=True)
    
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

        overflow = session.messages[:-window]
        recent = session.messages[-window:]

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
                session = self._load_session_from_disk(session_id, filepath)
            with self._lock:
                self._cache[session_id] = session
            return session

        with self._lock:
            if session_id in self._cache:
                return self._cache[session_id]
            session = SessionData(session_id=session_id)
            self._cache[session_id] = session
            return session

    def _load_session_from_disk(self, session_id: str, filepath: str) -> SessionData:
        """Load session JSON from disk (caller must hold FileLock)."""
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SessionData.from_dict(data)
            except (json.JSONDecodeError, IOError):
                pass
        return SessionData(session_id=session_id)

    def _read_session_fresh(self, session_id: str) -> SessionData:
        """Reload session from disk and refresh the in-process cache."""
        filepath = self._get_session_path(session_id)
        with FileLock(filepath, self.lock_timeout):
            session = self._load_session_from_disk(session_id, filepath)
        with self._lock:
            self._cache[session_id] = session
        return session

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
            session = self._load_session_from_disk(session_id, filepath)
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
            # Always reload from disk inside lock to avoid race conditions
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    session = SessionData.from_dict(data)
                except (json.JSONDecodeError, IOError):
                    session = SessionData(session_id=session_id)
            else:
                session = SessionData(session_id=session_id)
            
            # Add message
            session.messages.append(message)
            session.updated_at = datetime.now(timezone.utc).isoformat()
            
            # Apply retention policy to the active window (Issue #2709)
            self._enforce_window(session)
            
            # Write atomically
            if not self._atomic_write_json(filepath, session.to_dict()):
                logger.error(f"Failed to save session {session_id}")
                return False

            # Update cache
            with self._lock:
                self._cache[session_id] = session

            return True
    
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

        def _apply(session: SessionData) -> None:
            session.messages.clear()
            # Issue #2741: replacing the whole transcript invalidates any prior
            # compaction anchor (its message_index no longer maps to these
            # messages). Clear it so get_working_history returns the full new
            # history instead of clamping to an empty tail and dropping messages.
            session.last_compaction = None
            for msg in messages:
                session.messages.append(
                    SessionMessage(
                        role=msg.get("role", "user"),
                        content=msg.get("content", "") or "",
                        timestamp=msg.get("timestamp", time.time()),
                        metadata=msg.get("metadata", {}),
                        # Preserve tool turns on whole-transcript saves (#3089).
                        tool_calls=msg.get("tool_calls"),
                        tool_call_id=msg.get("tool_call_id"),
                    )
                )

        return self._modify_session_locked(
            session_id, _apply, error_label="set chat history"
        )

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
        """Derive a short human-friendly title for a session."""
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

def get_default_session_store() -> DefaultSessionStore:
    """Get the global default session store instance.

    Retention is non-destructive ("compact") by default. It can be overridden
    without code changes via environment variables so the same behaviour is
    reachable from CLI/YAML surfaces (Issue #2709):

    - ``PRAISONAI_SESSION_RETENTION``: ``compact`` | ``truncate`` | ``keep_all``
    - ``PRAISONAI_SESSION_ACTIVE_WINDOW``: int, recent turns kept live
    """
    global _default_store
    
    if _default_store is None:
        with _store_lock:
            if _default_store is None:
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
                        retention=retention,
                        active_window=active_window,
                    )
                except ValueError:
                    logger.warning(
                        "Invalid PRAISONAI_SESSION_RETENTION=%r; using default",
                        retention,
                    )
                    _default_store = DefaultSessionStore(active_window=active_window)
    
    return _default_store
