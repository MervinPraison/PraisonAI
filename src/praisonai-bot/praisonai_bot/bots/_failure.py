"""Canonical user-facing failure replies for bot transports."""

from __future__ import annotations

from typing import Any


def failure_reply_text(outcome: Any) -> str:
    """Render a failed turn without exposing raw exception text."""
    from praisonaiagents.bots.failure import render_failure_reply

    return render_failure_reply(outcome).text


__all__ = ["failure_reply_text"]
