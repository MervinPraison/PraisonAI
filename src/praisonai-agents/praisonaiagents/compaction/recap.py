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

# A recap is a *glanceable* re-entry aid, not a full transcript. Bound the
# rendered block so a large persisted/compaction summary can never produce an
# output that overflows a delivery channel (e.g. Telegram's 4096-char message
# limit) or scrolls a terminal. Kept comfortably under that ceiling so channel
# framing/markdown never tips it over.
RECAP_MAX_CHARS = 3500


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


def build_recap(
    history: List[Dict[str, Any]],
    tail: int = 4,
    max_chars: int = RECAP_MAX_CHARS,
) -> str:
    """Render a read-only "where were we" summary of a transcript.

    Reuses the existing summariser (a persisted compaction summary when one is
    embedded, otherwise the naive summarise pass) and always tops up with the
    most recent ``tail`` messages so the recap reflects the latest activity.
    The input ``history`` is never modified and no compaction is triggered.

    The rendered block is bounded to ``max_chars`` so a large persisted summary
    can never overflow a delivery channel (e.g. Telegram's 4096-char message
    limit) or flood a terminal; the recent tail is always preserved and the
    (older) summary is what gets trimmed, keeping the most relevant context.

    Args:
        history: The conversation messages (not modified).
        tail: How many recent messages to append verbatim.
        max_chars: Upper bound on the rendered recap length. ``0`` or negative
            disables the cap.

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

    header = f"📌 {RECAP_HEADER}"

    if max_chars and max_chars > 0 and summary_text:
        # Reserve room for the header, the recent tail, and joining newlines so
        # the *most recent* activity is never dropped in favour of the older
        # summary. Only the summary is trimmed to fit the budget.
        tail_block = ""
        if tail_lines:
            tail_block = "\n".join(["Recent:", *tail_lines])
        # +2 accounts for the newlines that will join header/summary/tail.
        reserved = len(header) + len(tail_block) + 2
        budget = max_chars - reserved
        if budget <= 0:
            summary_text = ""
        elif len(summary_text) > budget:
            summary_text = summary_text[: max(0, budget - 1)].rstrip() + "…"

    parts: List[str] = [header]
    if summary_text:
        parts.append(summary_text)
    if tail_lines:
        parts.append("Recent:")
        parts.extend(tail_lines)
    return "\n".join(parts)
