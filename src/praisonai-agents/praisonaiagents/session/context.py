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

import asyncio
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Any

if TYPE_CHECKING:
    from ..gateway.protocols import OutboundMessengerProtocol


@dataclass(frozen=True)
class Origin:
    """Information about where a message originated."""
    platform: str = ""
    chat_type: str = ""  # e.g. "group", "direct", "channel"
    display_name: str = ""  # e.g. channel name, group name, or user name
    thread_id: str = ""


@dataclass(frozen=True)
class ReachableTarget:
    """A channel/chat the agent can deliver messages to."""
    name: str  # Friendly name or alias
    platform: str
    channel_id: str
    kind: str = "alias"  # "home" or "alias"


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
    # New fields for platform awareness
    origin: Optional[Origin] = None
    reachable_targets: Optional[List[ReachableTarget]] = None

    def to_dict(self) -> dict:
        # asdict already recursively converts nested dataclasses
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionContext":
        # Parse origin if present
        origin = None
        if "origin" in d and d["origin"]:
            origin_data = d["origin"]
            origin = Origin(
                platform=origin_data.get("platform", ""),
                chat_type=origin_data.get("chat_type", ""),
                display_name=origin_data.get("display_name", ""),
                thread_id=origin_data.get("thread_id", ""),
            )
        
        # Parse reachable_targets if present
        targets = None
        if "reachable_targets" in d and d["reachable_targets"]:
            targets = [
                ReachableTarget(
                    name=t.get("name", ""),
                    platform=t.get("platform", ""),
                    channel_id=t.get("channel_id", ""),
                    kind=t.get("kind", "alias"),
                )
                for t in d["reachable_targets"]
            ]
        
        return cls(
            platform=d.get("platform", ""),
            chat_id=d.get("chat_id", ""),
            chat_name=d.get("chat_name", ""),
            thread_id=d.get("thread_id", ""),
            user_id=d.get("user_id", ""),
            user_name=d.get("user_name", ""),
            unified_user_id=d.get("unified_user_id", ""),
            origin=origin,
            reachable_targets=targets,
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
    origin: Optional[Origin] = None,
    reachable_targets: Optional[List[ReachableTarget]] = None,
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
        origin=origin,
        reachable_targets=reachable_targets,
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


# ---------------------------------------------------------------------------
# Outbound messenger (Issue #2183)
#
# The running gateway/bot registers a concrete OutboundMessengerProtocol impl
# into this task-local slot so the built-in ``send_message`` tool can reach the
# user proactively mid-task. ``SessionContext`` is frozen, so the messenger is
# tracked in its own ContextVar rather than as a context field.
# ---------------------------------------------------------------------------

_MESSENGER: ContextVar[Optional["OutboundMessengerProtocol"]] = ContextVar(
    "praisonai_outbound_messenger", default=None
)


def register_outbound_messenger(
    messenger: Optional["OutboundMessengerProtocol"],
) -> Token:
    """Register the active outbound messenger for this task. Returns a token."""
    return _MESSENGER.set(messenger)


def get_outbound_messenger() -> Optional["OutboundMessengerProtocol"]:
    """Return the active outbound messenger, or ``None`` if no gateway is running."""
    return _MESSENGER.get()


def clear_outbound_messenger(token: Token) -> None:
    """Restore the previous outbound messenger using the token from register."""
    try:
        _MESSENGER.reset(token)
    except (LookupError, ValueError):
        _MESSENGER.set(None)


# ---------------------------------------------------------------------------
# Gateway event loop registry (Issue #2183)
#
# Sync agent tools (e.g. ``send_message``) usually execute in an executor
# worker thread while the bot's event loop runs in another thread. A
# ContextVar would NOT propagate across that thread boundary, so the running
# gateway records its loop here (process-global) to let sync tools schedule
# loop-bound coroutines via ``run_coroutine_threadsafe`` on the correct loop.
# ---------------------------------------------------------------------------

_GATEWAY_LOOP: Optional["asyncio.AbstractEventLoop"] = None


def register_gateway_loop(loop: "asyncio.AbstractEventLoop") -> None:
    """Record the running gateway event loop for cross-thread coroutine scheduling."""
    global _GATEWAY_LOOP
    _GATEWAY_LOOP = loop


def get_gateway_loop() -> Optional["asyncio.AbstractEventLoop"]:
    """Return the registered gateway event loop, or ``None`` if none is set."""
    return _GATEWAY_LOOP


def clear_gateway_loop() -> None:
    """Clear the registered gateway event loop (on gateway shutdown)."""
    global _GATEWAY_LOOP
    _GATEWAY_LOOP = None


__all__ = [
    "SessionContext",
    "Origin",
    "ReachableTarget",
    "set_session_context",
    "get_session_context",
    "clear_session_context",
    "register_outbound_messenger",
    "get_outbound_messenger",
    "clear_outbound_messenger",
    "register_gateway_loop",
    "get_gateway_loop",
    "clear_gateway_loop",
]
