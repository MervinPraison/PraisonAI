"""Continuation-prompt assembler for cross-context resume ("session handoff").

When a long run loses its context — compaction, a fresh session, a new machine —
the next context should be handed a *generated continuation prompt built from
durable state*, not left to reconstruct history by scrolling. Every durable
ingredient already exists (session recap, goal state, workflow checkpoints); this
module is the missing assembler.

:func:`build_handoff_prompt` performs **deterministic assembly with no LLM call**:
it collects a persisted recap/summary, the persisted :class:`GoalState`, and (when
supplied) a workflow checkpoint, and renders a self-contained continuation prompt.
Sections whose store has no data are omitted, and the output is hard-capped with
tail-biasing so it can never overflow a delivery channel or terminal.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

HANDOFF_MAX_CHARS = 4000

_PREAMBLE = (
    "You are resuming an interrupted run. Recover from durable state; do not "
    "trust memory of a previous conversation."
)


def _goal_sections(goal_state: Optional[Dict[str, Any]]) -> List[str]:
    """Render GOAL / DEFINITION OF DONE / CONSTRAINTS from persisted GoalState."""
    if not isinstance(goal_state, dict):
        return []
    lines: List[str] = []
    goal = (goal_state.get("goal") or "").strip()
    if goal:
        lines.append(f"GOAL: {goal}")
    criteria = goal_state.get("criteria")
    if isinstance(criteria, dict):
        outcome = (criteria.get("outcome") or "").strip()
        verification = (criteria.get("verification") or "").strip()
        dod = outcome
        if verification:
            dod = f"{dod} (verify: {verification})" if dod else f"verify: {verification}"
        if dod:
            lines.append(f"DEFINITION OF DONE: {dod}")
        constraints = criteria.get("constraints")
        if isinstance(constraints, list) and constraints:
            lines.append(
                "CONSTRAINTS (never violate): "
                + "; ".join(str(c) for c in constraints)
            )
    reason = (goal_state.get("last_reason") or "").strip()
    if reason:
        lines.append(f"STATUS: {reason}")
    return lines


def _progress_section(checkpoint: Optional[Dict[str, Any]]) -> List[str]:
    """Render PROGRESS from a workflow checkpoint dict, if any."""
    if not isinstance(checkpoint, dict):
        return []
    completed = checkpoint.get("completed_steps")
    total = checkpoint.get("total_steps") or checkpoint.get("step_count")
    last = checkpoint.get("last_step") or checkpoint.get("current_step")
    if completed is None and last is None:
        return []
    if total:
        head = f"PROGRESS: {completed or 0} of {total} workflow steps done"
    else:
        head = f"PROGRESS: {completed or 0} workflow steps done"
    if last:
        head += f"; last completed: {last}"
    return [head]


def _recent_actions(recap_text: str) -> List[str]:
    """Derive a RECENT ACTIONS block from a recap/summary string, if present."""
    recap_text = (recap_text or "").strip()
    if not recap_text:
        return []
    return ["RECENT ACTIONS (recap-derived):", recap_text]


_ELLIPSIS = "\n…\n"


def _cap(text: str, tail: str, max_chars: int) -> str:
    """Cap the prompt to ``max_chars`` while preserving the ``NEXT:`` tail.

    The closing ``NEXT:`` guidance is the most actionable line for a resuming
    context, so a naive head-truncation would silently drop it. Instead we keep
    the head (preamble/goal/progress) and the ``tail`` verbatim, and trim from
    the middle recap block. Only if the tail alone already exceeds the budget do
    we fall back to a plain truncation.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    tail = tail.strip()
    # If even the tail cannot fit, fall back to a plain head-truncation.
    if not tail or len(tail) + len(_ELLIPSIS) >= max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    # Preserve the tail verbatim; spend the remaining budget on the head, then
    # bridge the trimmed middle with an ellipsis marker.
    head_budget = max_chars - len(tail) - len(_ELLIPSIS)
    head = text[:head_budget].rstrip()
    return f"{head}{_ELLIPSIS}{tail}"


def build_handoff_prompt(
    *,
    recap: str = "",
    goal_state: Optional[Dict[str, Any]] = None,
    workflow_checkpoint: Optional[Dict[str, Any]] = None,
    recent_actions: Optional[List[str]] = None,
    key_files: Optional[List[str]] = None,
    max_chars: int = HANDOFF_MAX_CHARS,
) -> str:
    """Assemble a self-contained continuation prompt from durable state.

    Deterministic: makes **no LLM call**. Sections whose source has no data are
    omitted. The result is capped to ``max_chars``.

    Args:
        recap: A persisted compaction summary / recap string (may be empty).
        goal_state: A persisted ``GoalState.to_dict()`` mapping, if any.
        workflow_checkpoint: A workflow checkpoint dict, if any.
        recent_actions: Explicit recent-action lines (e.g. journal-derived).
            When omitted, a recap-derived block is used instead.
        key_files: File paths to surface under KEY FILES.
        max_chars: Upper bound on the rendered prompt. ``0`` disables the cap.

    Returns:
        The continuation prompt string.
    """
    sections: List[str] = [_PREAMBLE, ""]

    goal_lines = _goal_sections(goal_state)
    if goal_lines:
        sections.extend(goal_lines)

    progress_lines = _progress_section(workflow_checkpoint)
    if progress_lines:
        sections.extend(progress_lines)

    if recent_actions:
        sections.append("RECENT ACTIONS:")
        sections.extend(f"  - {line}" for line in recent_actions)
    else:
        sections.extend(_recent_actions(recap))

    if key_files:
        seen: List[str] = []
        for path in key_files:
            if path and path not in seen:
                seen.append(path)
        if seen:
            sections.append("KEY FILES: " + ", ".join(seen))

    next_tail = (
        "NEXT: continue toward the remaining work. First verify the current "
        "state on disk before acting."
    )
    sections.append(next_tail)

    return _cap("\n".join(sections).strip(), next_tail, max_chars)
