"""
Progress-feed compositor for PraisonAI streaming.

Turns the typed :class:`StreamEvent` stream into a stable, bounded, multi-line
status view suitable for edit-in-place delivery (bot channels today, TUI/web
later). This is a pure, dependency-free data transformation that mirrors how
``strip_reasoning_tags`` is a pure transform over streamed text — no third-party
imports, no I/O, no transport concerns.

The two public functions are:

- :func:`merge_progress_line` — fold a ``StreamEvent`` into a list of
  :class:`ProgressLine`, updating the line that shares the event's correlation
  id (so a tool's "running" line becomes "done"/"error" in place) or appending
  a new line otherwise.
- :func:`render_progress` — render a list of lines as a bounded, word-aware
  rolling window (last N lines, per-line char cap) ready for ``DraftStreamer``.

Design principles:
- Zero third-party dependencies (pure stdlib).
- Deterministic and side-effect free (easy to unit test).
- Stable correlation: a start event and its matching finish event share one id
  so updates rewrite their own line instead of appending spam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .events import StreamEvent


# State markers rendered as a leading glyph per line.
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_ERROR = "error"

_STATE_GLYPHS = {
    STATE_RUNNING: "⏳",
    STATE_DONE: "✓",
    STATE_ERROR: "✗",
}


@dataclass
class ProgressLine:
    """A single line in the progress feed.

    Attributes:
        id: Correlation key (tool call id, plan step id, approval id). A start
            event and its matching finish event share this id so the line is
            updated in place rather than duplicated.
        kind: One of ``"tool"``, ``"plan"``, ``"approval"``, ``"command-output"``.
        text: Human-readable status text for this line.
        state: One of ``"running"``, ``"done"``, ``"error"``.
    """

    id: str
    kind: str
    text: str
    state: str = STATE_RUNNING


def _event_correlation_id(event: "StreamEvent") -> Optional[str]:
    """Derive a stable correlation id for an event, if any.

    Prefers an explicit id carried on the tool-call payload or metadata; falls
    back to the tool name so repeated calls without ids still coalesce sensibly.
    Returns ``None`` when the event carries no progress-worthy signal.
    """
    tool_call = getattr(event, "tool_call", None)
    if isinstance(tool_call, dict):
        for key in ("id", "call_id", "tool_call_id"):
            val = tool_call.get(key)
            if val:
                return str(val)
        name = tool_call.get("name")
        if name:
            return f"tool:{name}"

    metadata = getattr(event, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("id", "correlation_id", "step_id", "approval_id"):
            val = metadata.get(key)
            if val:
                return str(val)

    return None


def _tool_text(event: "StreamEvent", state: str) -> str:
    """Compose a tool line's text from the event payload."""
    tool_call = getattr(event, "tool_call", None) or {}
    name = tool_call.get("name") or "tool"
    detail = None
    if isinstance(tool_call, dict):
        detail = tool_call.get("result_summary") or tool_call.get("summary")
    if detail:
        return f"{name} — {detail}"
    return str(name)


def merge_progress_line(
    lines: List[ProgressLine], event: "StreamEvent"
) -> List[ProgressLine]:
    """Fold ``event`` into ``lines``, updating or appending a :class:`ProgressLine`.

    The line sharing the event's correlation id is updated in place (its state
    and text advance); otherwise a new line is appended. Events that carry no
    progress signal leave ``lines`` unchanged. A new list is returned; the input
    is not mutated.

    Args:
        lines: Current feed lines (not mutated).
        event: The streaming event to fold in.

    Returns:
        The updated list of progress lines.
    """
    # Lazy import to keep this module import-cheap and avoid any cycle.
    from .events import StreamEventType

    etype = getattr(event, "type", None)

    # Map event types to (kind, state). Only progress-worthy events produce a
    # line; everything else is a no-op passthrough.
    kind: Optional[str] = None
    state: Optional[str] = None

    if etype in (StreamEventType.TOOL_CALL_START, StreamEventType.DELTA_TOOL_CALL):
        kind, state = "tool", STATE_RUNNING
    elif etype in (StreamEventType.TOOL_CALL_END, StreamEventType.TOOL_CALL_RESULT):
        kind, state = "tool", STATE_DONE
    elif etype == StreamEventType.TOOL_PROGRESS:
        kind, state = "command-output", STATE_RUNNING
    elif etype == StreamEventType.ERROR:
        kind, state = "tool", STATE_ERROR
    else:
        return lines

    corr = _event_correlation_id(event)
    if corr is None:
        # Command-output/error without a correlation id: append a fresh line
        # keyed by position so it still appears, but never coalesces.
        corr = f"{kind}:{len(lines)}"

    if kind == "tool":
        text = _tool_text(event, state)
    elif kind == "command-output":
        text = (getattr(event, "content", None) or "").strip() or "output"
    else:
        text = (getattr(event, "content", None) or "").strip() or kind

    result = list(lines)
    for i, line in enumerate(result):
        if line.id == corr:
            # Error takes precedence; a done event never downgrades a running
            # line back, and a running update refreshes text.
            new_state = state
            if line.state == STATE_ERROR:
                new_state = STATE_ERROR
            result[i] = ProgressLine(id=corr, kind=line.kind, text=text, state=new_state)
            return result

    result.append(ProgressLine(id=corr, kind=kind, text=text, state=state))
    return result


def _truncate_word_aware(text: str, max_chars: int) -> str:
    """Truncate ``text`` to ``max_chars``, preferring a word boundary."""
    text = text.replace("\n", " ").strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    budget = max_chars - 1  # room for the ellipsis
    clipped = text[:budget]
    cut = clipped.rfind(" ")
    if cut > 0 and cut >= budget // 2:
        clipped = clipped[:cut]
    return clipped.rstrip() + "…"


def render_progress(
    lines: List[ProgressLine],
    *,
    max_lines: int = 8,
    max_line_chars: int = 120,
) -> str:
    """Render a bounded, word-aware rolling window for edit-in-place delivery.

    Only the last ``max_lines`` lines are shown; each line is prefixed with a
    state glyph and truncated (word-aware) to ``max_line_chars``.

    Args:
        lines: Progress lines to render.
        max_lines: Maximum number of trailing lines to include.
        max_line_chars: Per-line character cap (including the glyph prefix).

    Returns:
        A newline-joined string ready to feed to ``DraftStreamer``.
    """
    if not lines:
        return ""
    window = lines[-max_lines:] if max_lines > 0 else list(lines)
    rendered: List[str] = []
    for line in window:
        glyph = _STATE_GLYPHS.get(line.state, "⏳")
        prefix = f"{glyph} "
        body_budget = max_line_chars - len(prefix) if max_line_chars > 0 else 0
        body = _truncate_word_aware(line.text, body_budget) if body_budget > 0 else line.text
        rendered.append(f"{prefix}{body}")
    return "\n".join(rendered)
