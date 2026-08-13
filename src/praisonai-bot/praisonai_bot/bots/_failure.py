"""Canonical user-facing failure replies for bot transports."""

from __future__ import annotations

from typing import Any

_GENERIC_FAILURE_TEXT = (
    "I couldn't complete that due to an unexpected error. Please resend."
)


def failure_reply_text(outcome: Any) -> str:
    """Render a failed turn without exposing raw exception text.

    Falls back to a safe generic reply if the core renderer is unavailable
    (e.g. an older ``praisonaiagents`` release), so the error path never itself
    raises and leaves the user without a reply.
    """
    try:
        from praisonaiagents.bots.failure import render_failure_reply
    except ImportError:
        return _GENERIC_FAILURE_TEXT

    return render_failure_reply(outcome).text


__all__ = ["failure_reply_text"]
