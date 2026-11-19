"""Session management and search tools.

This module provides tools for cross-session conversation recall — letting an
agent search its *own* past conversation transcripts. It is backed by the
default session store (``~/.praisonai/sessions/*.json``) and requires no
optional dependencies. For scale, ``praisonaiagents.session.SqliteSessionStore``
provides a stdlib ``sqlite3`` + FTS5 index so recall is a bounded lookup
rather than a full-directory scan (Issue #2927).

The ``session_search`` tool has three shapes:

- **discovery** — ``session_search(query="billing migration")`` → top matching
  sessions, each with a short window of messages around the hit.
- **scroll** — ``session_search(session_id="...", around_message_id="42")`` →
  ±N surrounding messages to read more.
- **browse** — ``session_search()`` (no query) → most recent sessions for
  "what was I working on?".
"""

import json
import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_active_session_store():
    """Return the active session store backend.

    Defaults to the dependency-free :class:`DefaultSessionStore`. Wrappers may
    override the global store (e.g. an FTS-backed implementation).
    """
    from ..session.store import get_default_session_store

    return get_default_session_store()


def _caller_scope() -> Optional[tuple]:
    """Who is asking: ``("user_id", id)`` when a bot set the user for this turn,
    else ``("agent_name", name)`` for the calling agent, else ``None``."""
    from ..session.context import get_session_context
    from .injected import get_current_state

    user_id = get_session_context().user_id
    if user_id:
        return ("user_id", user_id)
    state = get_current_state()
    name = state and ((state.metadata or {}).get("agent_name") or state.agent_id)
    return ("agent_name", name) if name else None


def _owned(store, session_id: str, scope: tuple) -> bool:
    """True when the stored session records the caller's user id / agent name."""
    get = getattr(store, "get_session", None)
    try:
        data = get(session_id) if callable(get) else None
    except Exception:  # unreadable session: not shown
        return False
    return bool(scope[1]) and getattr(data, scope[0], None) == scope[1]


class SessionTools:
    """Tools for cross-session conversation recall.

    Results are limited to the caller's own sessions: the user id a bot sets in
    the session context, or, without one, the calling agent's name. A call with
    neither (outside an agent run) is refused.
    """

    def __init__(self, workspace=None, store=None):
        """Initialize SessionTools.

        Args:
            workspace: Optional Workspace instance for path containment.
            store: Optional session store implementing the searchable protocol.
                Defaults to the active session store.
        """
        self._workspace = workspace
        self._store = store
        self._store_lock = threading.Lock()

    @property
    def store(self):
        if self._store is None:
            with self._store_lock:
                if self._store is None:
                    self._store = get_active_session_store()
        return self._store

    def session_search(
        self,
        query: str = "",
        session_id: str = "",
        around_message_id: str = "",
        limit: int = 5,
        window: int = 5,
    ) -> str:
        """Search past conversations, scroll a session, or browse recent ones.

        Args:
            query: Free-text query → discovery of matching sessions in context.
            session_id: Session to scroll/read (used when no query is given).
            around_message_id: Anchor message index for scroll mode.
            limit: Maximum number of sessions/results to return.
            window: Number of messages to include around a hit/anchor.

        Returns:
            JSON string with the search/scroll/browse results.
        """
        try:
            store = self.store
            scope = _caller_scope()
            if scope is None:
                raise PermissionError("session_search runs as an agent tool; no calling user or agent")
            fetch = max(limit, 1) * 5  # other callers' sessions are filtered out below

            if query:  # discovery
                hits = store.search(query, limit=fetch, window=window)
                results = [h.as_dict() for h in hits if _owned(store, h.session_id, scope)][:limit]
                return json.dumps(
                    {
                        "success": True,
                        "mode": "discovery",
                        "query": query,
                        "total_found": len(results),
                        "results": results,
                    },
                    indent=2,
                    ensure_ascii=False,
                )

            if session_id:  # scroll / read
                if not _owned(store, session_id, scope):
                    raise PermissionError(f"session {session_id!r} is not one of the caller's sessions")
                anchor = around_message_id or None
                messages = store.window(session_id, anchor, window=window)
                return json.dumps(
                    {
                        "success": True,
                        "mode": "scroll",
                        "session_id": session_id,
                        "around_message_id": around_message_id,
                        "messages": messages,
                    },
                    indent=2,
                    ensure_ascii=False,
                )

            # browse — most recent sessions
            summaries = store.recent(limit=fetch)
            results = [s.as_dict() for s in summaries if _owned(store, s.session_id, scope)][:limit]
            return json.dumps(
                {
                    "success": True,
                    "mode": "browse",
                    "total_found": len(results),
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
        except Exception as e:
            mode = "discovery" if query else ("scroll" if session_id else "browse")
            return json.dumps(
                {
                    "success": False,
                    "tool": "session_search",
                    "mode": mode,
                    "session_id": session_id or None,
                    "error": f"{type(e).__name__}: {e!s}",
                    "hint": "Verify store availability and parameters (query/session_id/window/limit).",
                },
                ensure_ascii=False,
            )


# Create default instance for direct function access
_session_tools = SessionTools()


def session_search(
    query: str = "",
    session_id: str = "",
    around_message_id: str = "",
    limit: int = 5,
    window: int = 5,
) -> str:
    """Search past conversations, scroll a session, or browse recent ones.

    Three shapes:
    - discovery: ``session_search(query="...")`` → matching sessions in context.
    - scroll: ``session_search(session_id="...", around_message_id="42")`` → ±N
      surrounding messages.
    - browse: ``session_search()`` → most recent sessions.

    Args:
        query: Free-text query for discovery mode.
        session_id: Session to scroll/read in scroll mode.
        around_message_id: Anchor message index for scroll mode.
        limit: Maximum number of sessions/results to return.
        window: Number of messages to include around a hit/anchor.

    Returns:
        JSON string with results.
    """
    return _session_tools.session_search(
        query=query,
        session_id=session_id,
        around_message_id=around_message_id,
        limit=limit,
        window=window,
    )


def create_session_tools(workspace=None, store: Optional[Any] = None) -> SessionTools:
    """Create SessionTools instance with optional workspace/store.

    Args:
        workspace: Optional Workspace instance for path containment.
        store: Optional session store implementing the searchable protocol.

    Returns:
        SessionTools instance.
    """
    return SessionTools(workspace=workspace, store=store)
