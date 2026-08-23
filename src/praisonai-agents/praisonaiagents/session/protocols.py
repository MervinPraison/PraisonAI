"""
Session Store Protocol for PraisonAI Agents.

Defines the minimal interface contract for session persistence backends.
Any class implementing these methods can be used as a session store.

Built-in implementations:
- DefaultSessionStore (JSON file-based)
- HierarchicalSessionStore (extends DefaultSessionStore with fork/snapshot)

Custom implementations (e.g. Redis, MongoDB, PostgreSQL) can implement
this protocol for seamless swapping.

Usage:
    from praisonaiagents.session.protocols import SessionStoreProtocol
    
    class RedisSessionStore:
        def add_message(self, session_id, role, content, metadata=None):
            ...  # Store in Redis
        
        def get_chat_history(self, session_id, max_messages=None):
            ...  # Retrieve from Redis
        
        # ... other methods
    
    # Type-check at runtime
    store: SessionStoreProtocol = RedisSessionStore()
    assert isinstance(store, SessionStoreProtocol)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class SessionHit:
    """A single cross-session search match with surrounding context.

    Returned by :meth:`SearchableSessionStoreProtocol.search` so the agent
    gets the match *in context* (a short window of messages around the hit).
    """

    session_id: str
    title: str = ""
    when: Optional[str] = None
    snippet: str = ""
    score: float = 0.0
    anchor_index: int = -1
    messages: List[Dict[str, Any]] = field(default_factory=list)
    # Anchored discovery: the first/last N user+assistant messages of the
    # session so the agent can reconstruct goal → match → resolution in one
    # call. ``{"opening": [...], "closing": [...]}``. Empty when unavailable.
    bookends: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serialisable dict."""
        result = {
            "session_id": self.session_id,
            "title": self.title,
            "when": self.when,
            "snippet": self.snippet,
            "score": self.score,
            "anchor_index": self.anchor_index,
            "messages": self.messages,
        }
        if self.bookends:
            result["bookends"] = self.bookends
        return result


@dataclass
class SessionSummary:
    """A lightweight summary of a session for "browse" / recent listings."""

    session_id: str
    title: str = ""
    when: Optional[str] = None
    message_count: int = 0

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serialisable dict."""
        return {
            "session_id": self.session_id,
            "title": self.title,
            "when": self.when,
            "message_count": self.message_count,
        }


@dataclass
class ImportReport:
    """Outcome of a :meth:`PortableSessionStoreProtocol.import_sessions` call.

    A structured, JSON-serialisable summary so an operator (or the gateway CLI)
    can see exactly what a restore did: how many sessions were imported vs
    skipped, and why. ``skipped`` entries carry ``{"session_id", "reason"}`` so
    a rejected record (cap exceeded, malformed, duplicate) is observable rather
    than silently dropped.
    """

    imported: int = 0
    skipped: List[Dict[str, str]] = field(default_factory=list)
    version: int = 1

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    def as_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serialisable dict."""
        return {
            "imported": self.imported,
            "skipped": self.skipped,
            "skipped_count": self.skipped_count,
            "version": self.version,
        }


@runtime_checkable
class SessionStoreProtocol(Protocol):
    """Protocol for session persistence backends.
    
    Defines the minimal interface for storing and retrieving
    agent conversation sessions. Implementations must provide
    these five core methods.
    
    Built-in implementations:
    - DefaultSessionStore (JSON files with atomic writes)
    - HierarchicalSessionStore (fork, snapshot, revert)
    
    Example custom implementation::
    
        class MyStore:
            def add_message(self, session_id, role, content, metadata=None):
                ...
            def get_chat_history(self, session_id, max_messages=None):
                return [{"role": "user", "content": "Hi"}]
            def clear_session(self, session_id):
                return True
            def delete_session(self, session_id):
                return True
            def session_exists(self, session_id):
                return False
        
        store: SessionStoreProtocol = MyStore()
        assert isinstance(store, SessionStoreProtocol)  # True
    """
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a message to a session.
        
        Args:
            session_id: Unique session identifier.
            role: Message role ("user", "assistant", "system").
            content: Message content text.
            metadata: Optional metadata dict.
            
        Returns:
            True if saved successfully.
        """
        ...
    
    def get_chat_history(
        self,
        session_id: str,
        max_messages: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """Get chat history in LLM-compatible format.
        
        Args:
            session_id: Unique session identifier.
            max_messages: Maximum messages to return (most recent).
            
        Returns:
            List of {"role": "...", "content": "..."} dicts.
        """
        ...
    
    def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session (keep session metadata).
        
        Args:
            session_id: Unique session identifier.
            
        Returns:
            True if cleared successfully.
        """
        ...
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session completely (data + metadata).
        
        Args:
            session_id: Unique session identifier.
            
        Returns:
            True if deleted successfully.
        """
        ...
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists.
        
        Args:
            session_id: Unique session identifier.
            
        Returns:
            True if the session exists.
        """
        ...


@runtime_checkable
class PortableSessionStoreProtocol(Protocol):
    """Protocol for portable backup / restore / migration of sessions.

    Extends the storage contract with a store-agnostic way to export a
    versioned, JSON-serialisable payload and import it back on another host or
    into another store — so a gateway operator can back up, move, or restore
    conversation state without hand-copying opaque store files.

    The payload shape is deliberately simple and versioned::

        {"version": 1, "sessions": [ <session dict>, ... ]}

    Each session dict is the same portable shape produced by
    ``SessionData.to_dict`` (round-trips through ``SessionData.from_dict``), so
    export/import is symmetric across the built-in stores. ``import_sessions``
    is *hardened*: it caps how much it will ingest and, by default, resets live
    routing/activity fields so restored state is inert until re-bound (an
    imported record must not masquerade as an active connection).

    Example::

        data = store.export_all()
        report = other_store.import_sessions(data)
        print(report.imported, report.skipped_count)
    """

    def export_session(
        self, session_id: str, *, include_lineage: bool = True
    ) -> Dict[str, Any]:
        """Export a single session to a portable, versioned payload.

        Args:
            session_id: The session to export.
            include_lineage: When True, also include any compacted/rotated
                ancestors of this conversation so it round-trips as one logical
                session.

        Returns:
            ``{"version": ..., "sessions": [...]}`` (empty ``sessions`` when the
            id is unknown).
        """
        ...

    def export_all(self) -> Dict[str, Any]:
        """Export every stored session to a portable, versioned payload.

        Returns:
            ``{"version": ..., "sessions": [...]}`` covering all sessions.
        """
        ...

    def import_sessions(
        self,
        payload: Dict[str, Any],
        *,
        max_sessions: int = 10_000,
        reset_live_fields: bool = True,
        overwrite: bool = False,
    ) -> "ImportReport":
        """Import sessions from an exported payload (hardened).

        Args:
            payload: A payload previously produced by ``export_session`` /
                ``export_all``.
            max_sessions: Cap on how many sessions to ingest; the remainder is
                skipped and reported (guards against an oversized payload).
            reset_live_fields: When True (default), clear live routing/activity
                fields on each imported record so restored state is inert until
                re-bound (does not masquerade as an active connection).
            overwrite: When False (default), an existing session id is skipped
                rather than clobbered.

        Returns:
            An :class:`ImportReport` summarising imported vs skipped sessions.
        """
        ...


@runtime_checkable
class SearchableSessionStoreProtocol(Protocol):
    """Protocol for cross-session conversation recall.

    Extends the storage contract with the ability for an agent to search its
    own past conversations: full-text *discovery* over transcripts, *scroll*
    around an anchor message, and *browse* of recent sessions.

    The default JSON store implements this with a dependency-free substring
    scan. ``SqliteSessionStore`` provides a stdlib ``sqlite3`` + FTS5-backed
    implementation for scale (Issue #2927), turning recall into a bounded
    index lookup instead of a full-directory scan.

    Example::

        store: SearchableSessionStoreProtocol = DefaultSessionStore()
        hits = store.search("billing migration", limit=5, window=5)
        more = store.window("session-123", around_message_id="42", window=10)
        recent = store.recent(limit=10)
    """

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        window: int = 5,
    ) -> List[SessionHit]:
        """Full-text search across stored sessions.

        Args:
            query: Free-text query to match against message content.
            limit: Maximum number of matching sessions to return.
            window: Number of messages to include around each hit for context.

        Returns:
            List of :class:`SessionHit`, best matches first.
        """
        ...

    def window(
        self,
        session_id: str,
        around_message_id: Optional[str] = None,
        *,
        window: int = 5,
    ) -> List[Dict[str, Any]]:
        """Return ±``window`` messages around an anchor message in a session.

        Args:
            session_id: The session to read from.
            around_message_id: Index (as string) of the anchor message. If
                omitted or invalid, the most recent messages are returned.
            window: Number of messages to include on each side of the anchor.

        Returns:
            List of message dicts with their index for further scrolling.
        """
        ...

    def recent(self, *, limit: int = 10) -> List[SessionSummary]:
        """Return the most recently updated sessions.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            List of :class:`SessionSummary`, most recent first.
        """
        ...


@runtime_checkable
class RuntimeStateMirroringProtocol(Protocol):
    """Protocol for runtime state mirroring in sessions (Issue #1943).
    
    Enables native runtime to persist lightweight runtime-specific execution 
    artifacts for replay, debugging, or cross-turn mirroring when users mix 
    runtimes in one session.
    """
    
    def set_runtime_state(
        self, 
        session_id: str, 
        runtime_id: str, 
        turn_id: str, 
        state: Dict[str, Any],
        mirror_enabled: bool = True
    ) -> bool:
        """Set runtime state for a specific runtime and turn.
        
        Args:
            session_id: Session identifier
            runtime_id: Runtime identifier (e.g., "native", "plugin_harness") 
            turn_id: Turn identifier within the runtime
            state: Runtime state data (tool call ids, transcript slices, etc.)
            mirror_enabled: Whether runtime state mirroring is enabled (from SessionConfig.mirror_runtime_state)
            
        Returns:
            True if saved successfully
        """
        ...
    
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
        ...
    
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
        ...


@runtime_checkable
class SessionMirrorProtocol(Protocol):
    """Protocol for mirroring session transcripts to a remote backend (Issue #3646).

    A mirror is a *pluggable, local-first* sink: the session store keeps
    writing to local disk exactly as today, and — when a mirror is configured
    — new append-only records are also handed to the mirror so a session can
    be continued on another machine. The contract is deliberately tiny:

    - :meth:`append` receives the records produced by a turn (each an already
      timestamped, id-tagged dict, so mirroring is conflict-free by
      construction — last-writer per record id, no merge logic);
    - :meth:`load` returns all mirrored records for a session so a
      non-local id can be hydrated on resume;
    - :meth:`list_sessions` (optional) enumerates mirrored sessions for a
      ``session list --remote`` surface.

    The mirror must be safe to call off the local write path: an implementation
    is expected to be tolerant of transient outages, since the caller queues
    records and never lets a mirror failure block or corrupt the local session.

    Wrapper backends (postgres/supabase/turso/sqlite, …) adapt the existing
    ``praisonai.persistence.conversation`` stores onto this protocol; core
    ships only the contract (zero new dependencies).

    Example::

        store: SessionMirrorProtocol = MyRemoteMirror()
        store.append("s_abc", [{"id": "m1", "role": "user", "content": "hi",
                                 "timestamp": 1.0}])
        records = store.load("s_abc")  # full transcript, incl. tool calls
    """

    def append(self, session_id: str, records: List[Dict[str, Any]]) -> None:
        """Append append-only transcript records for a session.

        Args:
            session_id: The session these records belong to.
            records: New records to mirror. Each is a JSON-serialisable dict
                carrying at least an ``id`` and ``timestamp`` so re-appends are
                idempotent (last-writer per record id).
        """
        ...

    def load(self, session_id: str) -> List[Dict[str, Any]]:
        """Load all mirrored records for a session.

        Args:
            session_id: The session to hydrate.

        Returns:
            The full ordered list of mirrored records (empty if unknown).
        """
        ...

    def list_sessions(
        self, *, user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Enumerate mirrored sessions (optional).

        Args:
            user_id: Optional filter to a single user's sessions.

        Returns:
            List of session metadata dicts (at minimum ``session_id``).
        """
        ...


@runtime_checkable
class CheckpointQueryProtocol(Protocol):
    """Read path for session checkpoints / rollback snapshots."""

    def list_checkpoints(self, session_id: str) -> List[Dict[str, Any]]:
        """Return checkpoint metadata for a session."""
        ...

    def get_checkpoint(self, session_id: str, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Return a single checkpoint payload."""
        ...
