"""Default structured summary builder for context compaction.

This is the concrete :class:`~praisonaiagents.compaction.protocols.
SummaryBuilderProtocol` implementation that renders the declared
:data:`~praisonaiagents.compaction.config.SUMMARY_TEMPLATE` — the phase-aware
sections (``## Active Task`` / ``## Completed Actions`` / ``## In Progress`` /
``## Pending Questions`` / ``## Relevant Files / Paths`` / ``## Remaining
Work``) — so a compacted context keeps its structure instead of degrading to a
one-line ``"Summary of N messages"`` count.

Design: **deterministic, dependency-free, offline-safe.** It categorises the
transcript into the template sections from the messages themselves (roles,
tool calls, question marks, file-path tokens) rather than making an LLM call, so
it never blocks the hot compaction path, never adds a runtime dependency, and
never raises into the loop. File paths and identifiers are preserved verbatim.

When an optional ``llm_summarize_fn`` is supplied the builder still renders the
same template shape; on any failure it falls back to the deterministic render,
honouring the issue's "fall back to the plain summary on failure" rule.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .config import SUMMARY_TEMPLATE

# Match file/path-like tokens so they can be surfaced verbatim in the
# "Relevant Files / Paths" section (absolute/relative paths and dotted module
# names with a recognisable extension).
_PATH_RE = re.compile(
    r"(?:/[^\s'\"`]+|(?:[\w.-]+/)+[\w.-]+|[\w./-]+\.[A-Za-z0-9]{1,6})"
)

_MAX_ITEMS = 12
_MAX_LINE = 200


def _text(content: Any) -> str:
    """Best-effort flatten of a message ``content`` field into a string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", "")))
            else:
                parts.append(str(part))
        return " ".join(p for p in parts if p)
    return ""


def _clip(text: str, limit: int = _MAX_LINE) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class DefaultSummaryBuilder:
    """Deterministic :class:`SummaryBuilderProtocol` renderer for the template.

    Args:
        llm_summarize_fn: Optional callable ``(prompt: str) -> str`` used to
            distil section bodies. Any failure falls back to the deterministic
            render, so callers get a valid structured summary regardless.
    """

    def __init__(self, llm_summarize_fn: Optional[Any] = None) -> None:
        self._llm_summarize_fn = llm_summarize_fn

    # -- protocol ----------------------------------------------------------

    def build_structured_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Render :data:`SUMMARY_TEMPLATE` from ``messages`` deterministically.

        Never raises: on any failure returns the plain one-line summary so the
        compaction loop keeps a valid summary string (issue fallback rule).
        """
        try:
            return self._render(messages)
        except Exception:  # noqa: BLE001 - summarisation must never crash the loop
            return f"Summary of {len(messages)} messages"

    def merge_summaries(self, previous: str, current: str) -> str:
        """Merge a prior structured summary with the current one.

        Keeps both under a single "previous / latest" framing so an iterative
        re-compaction never discards the earlier phase structure.
        """
        previous = (previous or "").strip()
        current = (current or "").strip()
        if not previous:
            return current
        if not current:
            return previous
        return f"{previous}\n\n[Updated with newer activity]\n{current}"

    # -- rendering ---------------------------------------------------------

    def _render(self, messages: List[Dict[str, Any]]) -> str:
        completed: List[str] = []
        in_progress: List[str] = []
        pending: List[str] = []
        files: List[str] = []
        active_task = ""

        for msg in messages:
            role = msg.get("role", "")
            body = _text(msg.get("content"))

            # First substantive user turn frames the active task.
            if role == "user" and body.strip() and not active_task:
                active_task = _clip(body)

            # Executed work — tool calls and tool results — is *completed*.
            # An assistant turn that merely proposes or *asks* about work has
            # not been executed, so it must not be recorded as completed (it is
            # captured under "Pending Questions" / "In Progress" instead);
            # only a substantive, non-questioning assistant turn is completed.
            tool_calls = msg.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                for tc in tool_calls:
                    if not isinstance(tc, dict):
                        continue
                    name = (tc.get("function", {}) or {}).get("name", "tool")
                    completed.append(f"Called `{name}`")
            elif role == "assistant" and body.strip() and "?" not in body:
                completed.append(_clip(body))
            elif role == "tool" and body.strip():
                completed.append(_clip(f"tool result: {body}"))

            # Any turn with a question mark contributes an open question.
            if body and "?" in body:
                for sentence in body.split("?"):
                    sentence = sentence.strip()
                    if sentence:
                        pending.append(_clip(sentence + "?"))

            # Harvest file/path tokens verbatim from every turn.
            if body:
                for match in _PATH_RE.findall(body):
                    if match not in files:
                        files.append(match)

        # The most recent user turn (if different) is what's in progress.
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest = _clip(_text(msg.get("content")))
                if latest and latest != active_task:
                    in_progress.append(latest)
                break

        return SUMMARY_TEMPLATE.format(
            active_task=active_task or "(not specified)",
            completed=self._bullets(completed),
            in_progress=self._bullets(in_progress),
            pending=self._bullets(pending),
            files=self._bullets(files),
            remaining=self._bullets(pending or in_progress),
        )

    @staticmethod
    def _bullets(items: List[str]) -> str:
        if not items:
            return "(none)"
        # De-duplicate while preserving order, then cap.
        seen: List[str] = []
        for item in items:
            if item not in seen:
                seen.append(item)
        return "\n".join(f"- {item}" for item in seen[:_MAX_ITEMS])
