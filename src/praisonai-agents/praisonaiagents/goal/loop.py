"""
Goal-loop mixin for the Agent class.

Provides the goal-gated autonomous loop surface as a mixin so ``agent.py`` stays
lean. The completion judge (:func:`~praisonaiagents.goal.judge.judge_goal`)
gates the tool-using ``run_autonomous`` loop against the agent's stated goal.

Off by default: when ``self._goal_state`` is ``None`` the autonomous loop is
byte-for-byte unchanged. Set it via :meth:`GoalLoopMixin.run_goal` (or the
``goal=``/``goal_criteria=`` params on ``start``).
"""

from typing import Any, Optional, Tuple, TYPE_CHECKING

from praisonaiagents._logging import get_logger

from .judge import judge_goal, _tail

if TYPE_CHECKING:
    from .models import GoalCriteria, GoalState

logger = get_logger(__name__)

# Fail-open safety valve: after this many consecutive unparseable judge
# responses, auto-pause so a weak judge cannot silently burn the whole budget.
_MAX_CONSECUTIVE_PARSE_FAILURES = 3


class GoalLoopMixin:
    """Goal-gated autonomous loop helpers for :class:`Agent`."""

    # -- state -----------------------------------------------------------------

    def _init_goal_state(self) -> None:
        """Initialise goal-loop attributes (default: disabled)."""
        self._goal_state: Optional["GoalState"] = None
        self._goal_judge_model: Optional[str] = None

    # -- persistence -----------------------------------------------------------

    def _goal_state_key(self) -> str:
        session_id = getattr(self, "_session_id", None) or getattr(
            self, "session_id", None
        ) or "default"
        return f"goal:{session_id}"

    def _persist_goal_state(self) -> None:
        """Persist the current GoalState into the session store, if available."""
        state = getattr(self, "_goal_state", None)
        if state is None:
            return
        store = getattr(self, "_session_store", None) or getattr(
            self, "session_store", None
        )
        if store is None:
            return
        try:
            store.update_session_metadata(
                self._goal_state_key().split(":", 1)[1],
                goal_state=state.to_dict(),
            )
        except Exception as exc:  # pragma: no cover - persistence is best-effort
            logger.debug("Persisting goal state failed: %s", exc)

    def _load_goal_state(self) -> Optional["GoalState"]:
        """Load a persisted GoalState from the session store, if any."""
        store = getattr(self, "_session_store", None) or getattr(
            self, "session_store", None
        )
        if store is None:
            return None
        try:
            session = store.get_session(
                self._goal_state_key().split(":", 1)[1]
            )
            data = getattr(session, "metadata", {}).get("goal_state")
        except Exception:  # pragma: no cover - persistence is best-effort
            return None
        if not data:
            return None
        from .models import GoalState

        self._goal_state = GoalState.from_dict(data)
        return self._goal_state

    # -- judge gate ------------------------------------------------------------

    def _goal_continuation_prompt(self, state: "GoalState") -> str:
        """Return a self-contained continuation nudge.

        Restates the goal (and acceptance criteria, if any) so the loop keeps
        working even when history-clearing configs (``clear_context=True``)
        strip the earlier turns, which would otherwise leave the model with no
        idea what task to continue.
        """
        reason = state.last_reason or "the goal is not yet met"
        lines = [
            "The goal is not complete yet. Keep working with your tools until "
            "the acceptance criteria are met.",
            f"GOAL: {state.goal}",
        ]
        criteria = state.criteria
        if criteria is not None:
            if criteria.outcome:
                lines.append(f"DEFINITION OF DONE: {criteria.outcome}")
            if criteria.verification:
                lines.append(f"VERIFICATION: {criteria.verification}")
            if criteria.constraints:
                lines.append(
                    "CONSTRAINTS (never violate): "
                    + "; ".join(criteria.constraints)
                )
        lines.append(f"Reason it is not done yet: {reason}")
        return "\n".join(lines)

    def _goal_gate(self, response: str) -> Optional[Tuple[str, str]]:
        """Evaluate the goal judge after an autonomous iteration.

        Returns:
            ``None`` when no goal loop is active (caller falls through to the
            existing heuristics), otherwise a ``(outcome, reason)`` tuple where
            outcome is one of:
              - ``"done"``          → goal met, stop with success
              - ``"budget_paused"`` → budget exhausted, recoverable pause
              - ``"continue"``      → run another iteration with a nudge
        """
        state = getattr(self, "_goal_state", None)
        if state is None or state.status != "active":
            return None

        state.turns_used += 1
        verdict, reason = judge_goal(
            state,
            _tail(response),
            judge_model=getattr(self, "_goal_judge_model", None),
        )
        state.last_verdict, state.last_reason = verdict, reason

        # Track consecutive judge parse failures; auto-pause a wedged judge.
        if reason == "judge response unparseable":
            state.consecutive_parse_failures += 1
        else:
            state.consecutive_parse_failures = 0

        if verdict == "done":
            state.status = "done"
            self._persist_goal_state()
            return "done", reason

        if state.consecutive_parse_failures >= _MAX_CONSECUTIVE_PARSE_FAILURES:
            state.status = "paused"
            self._persist_goal_state()
            return "budget_paused", "judge repeatedly unparseable"

        if state.turns_used >= state.max_turns:
            state.status = "paused"
            self._persist_goal_state()
            return "budget_paused", reason

        self._persist_goal_state()
        return "continue", reason

    # -- public API ------------------------------------------------------------

    def _resume_or_new_goal_state(
        self,
        goal: str,
        criteria: Optional["GoalCriteria"],
        max_turns: int,
        resume: bool,
    ) -> "GoalState":
        """Resume a persisted paused state for the same goal, else start fresh."""
        from .models import GoalState

        if resume:
            saved = self._load_goal_state()
            if (
                saved is not None
                and saved.status == "paused"
                and saved.goal == goal
            ):
                # Resume the paused run in place (keep turns_used/verdict).
                saved.status = "active"
                if criteria is not None:
                    saved.criteria = criteria
                saved.max_turns = max_turns
                saved.consecutive_parse_failures = 0
                self._goal_state = saved
                return saved
        state = GoalState(goal=goal, criteria=criteria, max_turns=max_turns)
        self._goal_state = state
        return state

    def run_goal(
        self,
        task: str,
        goal: str,
        *,
        criteria: Optional["GoalCriteria"] = None,
        max_turns: int = 20,
        judge_model: Optional[str] = None,
        resume: bool = True,
        **kwargs: Any,
    ):
        """Run a goal-gated autonomous loop.

        Loops with tools; after each iteration an independent completion judge
        evaluates the run against the goal's acceptance criteria. Stops on
        ``done``; pauses recoverably when ``max_turns`` is reached.

        Args:
            task: The task/prompt to execute.
            goal: The goal text.
            criteria: Optional structured :class:`GoalCriteria`.
            max_turns: Judged iterations before a recoverable pause.
            judge_model: Independent judge model (defaults to gpt-4o-mini).
            resume: When ``True`` (default), a previously persisted ``paused``
                run for the same goal is resumed (turns are not reset) instead
                of restarting at ``turns_used=0``.

        Returns:
            :class:`~praisonaiagents.agent.autonomy.AutonomyResult`.
        """
        self._ensure_goal_autonomy()
        self._resume_or_new_goal_state(goal, criteria, max_turns, resume)
        self._goal_judge_model = judge_model
        try:
            return self.run_autonomous(task, **kwargs)
        finally:
            # Persist a terminal/paused state before clearing so a later call
            # can resume it; do not clobber the store on the way out.
            self._persist_goal_state()
            self._goal_state = None
            self._goal_judge_model = None

    def _ensure_goal_autonomy(self) -> None:
        """Enable an iterative autonomy loop for goal runs if not already on."""
        if not getattr(self, "autonomy_enabled", False):
            self._init_autonomy({"level": "full_auto", "mode": "iterative"})

    async def run_goal_async(
        self,
        task: str,
        goal: str,
        *,
        criteria: Optional["GoalCriteria"] = None,
        max_turns: int = 20,
        judge_model: Optional[str] = None,
        resume: bool = True,
        **kwargs: Any,
    ):
        """Async variant of :meth:`run_goal`."""
        self._ensure_goal_autonomy()
        self._resume_or_new_goal_state(goal, criteria, max_turns, resume)
        self._goal_judge_model = judge_model
        try:
            return await self.run_autonomous_async(task, **kwargs)
        finally:
            self._persist_goal_state()
            self._goal_state = None
            self._goal_judge_model = None
