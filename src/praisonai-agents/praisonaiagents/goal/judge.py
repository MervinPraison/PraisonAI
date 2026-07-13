"""
Completion judge for goal-gated autonomous loops.

An *independent* acceptance-criteria judge that gates the autonomous loop
against the agent's stated goal. Unlike the heuristic completion signals
("done"/"finished"/promise tag), this judge evaluates the run so far against
the goal's acceptance criteria and returns a structured verdict::

    {"verdict": "done" | "continue", "reason": "..."}

Design principles:
- **Independent**: uses a separate judge model/context (not the acting model
  self-grading) to avoid self-enhancement bias.
- **Fail-open**: a broken/timed-out judge yields ``continue`` so a weak judge
  never wedges progress. The caller caps consecutive parse failures and pauses.
- **Cheap & cache-friendly**: judges only the goal + a truncated tail of the
  latest agent output, not the whole transcript.

Reuses :class:`~praisonaiagents.eval.judge.Judge` for its lazy litellm loader
(DRY) while producing a raw JSON verdict instead of a numeric score.
"""

import json
import os
import re
from typing import Optional, Tuple, TYPE_CHECKING

from praisonaiagents._logging import get_logger

if TYPE_CHECKING:
    from .models import GoalState

logger = get_logger(__name__)


_VALID_VERDICTS = ("done", "continue")


def _default_judge_model() -> str:
    return os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini")


def _tail(text: str, limit: int = 4000) -> str:
    """Return the trailing ``limit`` characters of ``text`` (cache-friendly)."""
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[-limit:]


def _build_goal_judge_prompt(state: "GoalState", transcript_tail: str) -> str:
    """Build a strict, criteria-anchored, JSON-only judge prompt."""
    lines = [
        "You are an independent completion judge for an autonomous agent.",
        "Decide whether the agent's GOAL has been ACHIEVED based on the "
        "evidence in the agent output below.",
        "",
        f"GOAL: {state.goal}",
    ]
    criteria = state.criteria
    if criteria is not None:
        if criteria.outcome:
            lines.append(f"DEFINITION OF DONE: {criteria.outcome}")
        if criteria.verification:
            lines.append(
                "VERIFICATION (mark done ONLY with concrete evidence meeting "
                f"this bar): {criteria.verification}"
            )
        if criteria.constraints:
            lines.append("CONSTRAINTS (must NOT be violated):")
            for c in criteria.constraints:
                lines.append(f"  - {c}")
            lines.append(
                "If ANY constraint is violated, you MUST answer 'continue'."
            )
    lines += [
        "",
        "AGENT OUTPUT (most recent):",
        transcript_tail,
        "",
        "Do NOT accept mere claims of completion (e.g. the word 'done') as "
        "evidence. Require concrete evidence that the goal is actually met.",
        "Respond with ONLY a JSON object, no prose, in this exact form:",
        '{"verdict": "done" | "continue", "reason": "<one sentence>"}',
    ]
    return "\n".join(lines)


def _parse_verdict(raw: str) -> Tuple[str, str]:
    """Parse a judge response into ``(verdict, reason)``.

    Accepts the canonical ``{"verdict","reason"}`` shape and a legacy
    ``{"done": bool}`` shape. Raises ``ValueError`` if nothing parseable.
    """
    text = str(raw or "")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object in judge response")
    data = json.loads(match.group(0))
    if "verdict" in data:
        verdict = str(data.get("verdict", "")).strip().lower()
        if verdict not in _VALID_VERDICTS:
            raise ValueError(f"invalid verdict: {verdict!r}")
        reason = str(data.get("reason", "")).strip()
        return verdict, reason
    if "done" in data:
        verdict = "done" if bool(data.get("done")) else "continue"
        reason = str(data.get("reason", "")).strip()
        return verdict, reason
    raise ValueError("judge response missing 'verdict'/'done'")


def judge_goal(
    state: "GoalState",
    transcript_tail: str,
    *,
    judge_model: Optional[str] = None,
) -> Tuple[str, str]:
    """Judge whether ``state.goal`` is met given the latest agent output.

    Args:
        state: The active :class:`~praisonaiagents.goal.models.GoalState`.
        transcript_tail: The (already truncated) latest agent output.
        judge_model: Model to use for the independent judge. Defaults to
            ``OPENAI_MODEL_NAME`` or ``gpt-4o-mini``.

    Returns:
        ``(verdict, reason)`` where verdict is ``"done"`` or ``"continue"``.
        Fails open to ``("continue", "judge unavailable")`` on any error.
    """
    from ..eval.judge import Judge

    prompt = _build_goal_judge_prompt(state, transcript_tail)
    try:
        judge = Judge(model=judge_model or _default_judge_model(), temperature=0.0)
        litellm = judge._get_litellm()
        response = litellm.completion(
            model=judge.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=300,
        )
        raw = response.choices[0].message.content or ""
    except Exception as exc:  # pragma: no cover - network/optional dep
        logger.warning("Goal judge unavailable: %s", exc)
        return "continue", "judge unavailable"

    try:
        return _parse_verdict(raw)
    except (ValueError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("Goal judge response unparseable: %s", exc)
        return "continue", "judge response unparseable"
