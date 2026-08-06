"""Read-only session recap built on the existing summariser.

The compaction machinery in this package normally runs to *shrink* context.
``build_recap`` reuses that same summariser purely to *inform* the user: it
renders a short "where were we" block from a transcript **without mutating the
conversation or triggering compaction**. This is the shared core primitive
behind the ``/recap`` bot command and ``praisonai session show --recap``.
"""

from __future__ import annotations

from typing import Any, Dict, List

RECAP_HEADER = "Recap — where we were:"


def _persisted_summary(history: List[Dict[str, Any]]) -> str:
    """Return an already-distilled summary embedded in the transcript, if any.

    Prefers the most recent compaction checkpoint (a system message tagged
    ``_compacted``) or the naive ``[Previous conversation summary]`` line, so a
    recap can start cheaply from what the model already carries (Issue #3062).
    """
    found = ""
    for msg in history:
        content = msg.get("content")
        if msg.get("_compacted") and isinstance(content, str):
            found = content
        elif (
            msg.get("role") == "system"
            and isinstance(content, str)
            and content.startswith("[Previous conversation summary]")
        ):
            found = content
    return found


def _naive_summary(history: List[Dict[str, Any]]) -> str:
    """Distil older turns with the compactor's offline summarise pass.

    Operates on a shallow copy so the caller's transcript is never modified and
    no compaction event is emitted. Returns ``""`` on any failure so recap can
    never crash a chat.
    """
    try:
        from .compactor import ContextCompactor
        from .strategy import CompactionStrategy

        compactor = ContextCompactor(strategy=CompactionStrategy.SUMMARIZE)
        summarised = compactor._summarize([dict(m) for m in history])
        for msg in summarised:
            content = msg.get("content")
            if (
                msg.get("role") == "system"
                and isinstance(content, str)
                and content.startswith("[Previous conversation summary]")
            ):
                return content
    except Exception:  # noqa: BLE001 - recap must never raise
        return ""
    return ""


def build_recap(history: List[Dict[str, Any]], tail: int = 4) -> str:
    """Render a read-only "where were we" summary of a transcript.

    Reuses the existing summariser (a persisted compaction summary when one is
    embedded, otherwise the naive summarise pass) and always tops up with the
    most recent ``tail`` messages so the recap reflects the latest activity.
    The input ``history`` is never modified and no compaction is triggered.

    Args:
        history: The conversation messages (not modified).
        tail: How many recent messages to append verbatim.

    Returns:
        A short, human-readable recap block, or a "nothing yet" note.
    """
    if not history:
        return "Nothing to recap yet — this session has no messages."

    summary_text = _persisted_summary(history) or _naive_summary(history)

    tail_lines: List[str] = []
    for msg in history[-tail:] if tail > 0 else []:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            snippet = content.strip().replace("\n", " ")
            if len(snippet) > 160:
                snippet = snippet[:160] + "…"
            tail_lines.append(f"• {role}: {snippet}")

    parts: List[str] = [f"📌 {RECAP_HEADER}"]
    if summary_text:
        parts.append(summary_text)
    if tail_lines:
        parts.append("Recent:")
        parts.extend(tail_lines)
    return "\n".join(parts)
