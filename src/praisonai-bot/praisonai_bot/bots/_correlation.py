"""
End-to-end correlation IDs for the PraisonAI gateway message flow.

A single correlation id is minted at inbound (or adopted from the platform
message id) and threaded through ingress -> session -> agent run -> outbound
delivery so operators can answer "what happened to *this* message?" by joining
otherwise-disjoint log lines on one stable id.

Design constraints (per PraisonAI principles):
  - Wrapper-only — no core SDK changes required; core ``run_id`` can be seeded
    from the correlation id by callers that want it.
  - Lazy / zero-dependency: stdlib ``uuid`` + ``contextvars`` only.
  - Optional & backward compatible: if no correlation id is set, helpers fall
    back to minting one; nothing breaks when the feature is unused.

Usage::

    from praisonai_bot.bots import correlation_id_from, use_correlation_id, current_correlation_id

    cid = correlation_id_from({"message_id": "55"})
    with use_correlation_id(cid):
        ...                       # every hop in this block reads the same id
        logger.info("dispatch", extra={"correlation_id": current_correlation_id()})
"""

from __future__ import annotations

import contextvars
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

# Task-local correlation id. ``None`` means "not in a correlated turn".
_CORRELATION_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "praisonai_correlation_id", default=None
)

# Keys we probe (in order) when adopting an id from an inbound payload.
_ADOPT_KEYS = ("correlation_id", "message_id", "id")


def new_correlation_id() -> str:
    """Mint a fresh short correlation id (first 8 hex chars of a uuid4)."""
    return uuid.uuid4().hex[:8]


def correlation_id_from(inbound: Any = None) -> str:
    """Derive a correlation id from an inbound message, or mint a new one.

    Adopts an existing identifier from ``inbound`` when present (a dict with a
    ``correlation_id``/``message_id``/``id`` key, or any object exposing those
    attributes); otherwise mints a new id. Always returns a non-empty string.
    """
    if inbound is not None:
        for key in _ADOPT_KEYS:
            value = None
            if isinstance(inbound, dict):
                value = inbound.get(key)
            else:
                value = getattr(inbound, key, None)
            if value:
                return str(value)
    return new_correlation_id()


def current_correlation_id() -> Optional[str]:
    """Return the correlation id for the current task, or ``None`` if unset."""
    return _CORRELATION_ID.get()


def ensure_correlation_id() -> str:
    """Return the current correlation id, minting and setting one if absent."""
    cid = _CORRELATION_ID.get()
    if cid is None:
        cid = new_correlation_id()
        _CORRELATION_ID.set(cid)
    return cid


def set_correlation_id(cid: Optional[str]) -> "contextvars.Token[Optional[str]]":
    """Set the task-local correlation id, returning a reset token."""
    return _CORRELATION_ID.set(cid)


def reset_correlation_id(token: "contextvars.Token[Optional[str]]") -> None:
    """Reset the task-local correlation id using a token from ``set_correlation_id``."""
    try:
        _CORRELATION_ID.reset(token)
    except (ValueError, LookupError):
        # Token created in a different context; clear defensively.
        _CORRELATION_ID.set(None)


@contextmanager
def use_correlation_id(cid: Optional[str] = None) -> Iterator[str]:
    """Bind a correlation id for the duration of a ``with`` block.

    If ``cid`` is ``None`` a new id is minted. Yields the effective id and
    restores the previous value on exit.
    """
    effective = cid or new_correlation_id()
    token = _CORRELATION_ID.set(effective)
    try:
        yield effective
    finally:
        reset_correlation_id(token)


def correlation_log_fields(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build a structured-log ``extra`` dict carrying the current correlation id.

    Merges any ``extra`` mapping with ``{"correlation_id": <current>}`` so every
    hop logs the same id without each call site re-reading the contextvar.
    """
    fields: Dict[str, Any] = dict(extra or {})
    cid = current_correlation_id()
    if cid is not None:
        fields.setdefault("correlation_id", cid)
    return fields


__all__ = [
    "new_correlation_id",
    "correlation_id_from",
    "current_correlation_id",
    "ensure_correlation_id",
    "set_correlation_id",
    "reset_correlation_id",
    "use_correlation_id",
    "correlation_log_fields",
]
