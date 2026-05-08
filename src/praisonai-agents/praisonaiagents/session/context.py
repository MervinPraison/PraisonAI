"""Task-local session context for concurrent message handlers.

W1 — Replaces process-global ``os.environ`` based session metadata
with ``contextvars.ContextVar`` so that two messages handled
concurrently never overwrite each other's platform / chat / user IDs.

Each ``set_session_context`` call returns a token; pass it to
``clear_session_context`` in a ``finally`` block to restore the
previous state.

Usage in a bot handler::

    from praisonaiagents.session.context import (
        set_session_context,
        clear_session_context,
        get_session_context,
    )

    token = set_session_context(
        platform="telegram",
        chat_id="100",
        user_id="alice",
        unified_user_id="alice-global",
    )
    try:
        # ... agent handles message; tools can call get_session_context()
        ctx = get_session_context()
    finally:
        clear_session_context(token)
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SessionContext:
    """Snapshot of the current message-handling context."""

    platform: str = ""
    chat_id: str = ""
    chat_name: str = ""
    thread_id: str = ""
    user_id: str = ""
    user_name: str = ""
    unified_user_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionContext":
        return cls(
            platform=d.get("platform", ""),
            chat_id=d.get("chat_id", ""),
            chat_name=d.get("chat_name", ""),
            thread_id=d.get("thread_id", ""),
            user_id=d.get("user_id", ""),
            user_name=d.get("user_name", ""),
            unified_user_id=d.get("unified_user_id", ""),
        )


_CTX: ContextVar[SessionContext] = ContextVar(
    "praisonai_session_context", default=SessionContext()
)


def set_session_context(
    platform: str = "",
    chat_id: str = "",
    chat_name: str = "",
    thread_id: str = "",
    user_id: str = "",
    user_name: str = "",
    unified_user_id: str = "",
) -> Token:
    """Set the task-local session context. Returns a token for ``clear``."""
    ctx = SessionContext(
        platform=platform,
        chat_id=chat_id,
        chat_name=chat_name,
        thread_id=thread_id,
        user_id=user_id,
        user_name=user_name,
        unified_user_id=unified_user_id,
    )
    return _CTX.set(ctx)


def get_session_context() -> SessionContext:
    """Return the current task's session context (empty if unset)."""
    return _CTX.get()


def clear_session_context(token: Token) -> None:
    """Restore the previous session context using the token from ``set``."""
    try:
        _CTX.reset(token)
    except (LookupError, ValueError):
        # Token from a different context; reset to empty
        _CTX.set(SessionContext())


__all__ = [
    "SessionContext",
    "set_session_context",
    "get_session_context",
    "clear_session_context",
]
