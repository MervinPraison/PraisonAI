"""
LoopEvaluator - Scores loop *health* (convergence, waste, doom-loop guards).

Where ``EvaluationLoop`` measures output *quality* per iteration (judge score,
success flag, iteration count), ``LoopEvaluator`` measures loop *health*:
how efficiently the loop converged, how many iterations were wasted after the
threshold was met, and whether doom-loop safety guards fired.

It consumes an existing ``EvaluationLoopResult`` plus an optional list of
structured guard events (e.g. from ``doom_loop.py`` / ``loop_detection_plugin``)
and produces a ``LoopHealthResult`` consumable by ``EvalSuite``/``EvalReport``.

Example:
    from praisonaiagents.eval import EvaluationLoop, LoopEvaluator

    loop = EvaluationLoop(agent=my_agent, criteria="Analysis is thorough")
    loop_result = loop.run("Analyze the auth flow")

    evaluator = LoopEvaluator(threshold=8.0)
    health = evaluator.run(loop_result, guard_events=[])

    print(health.wasted_iterations)   # 0
    print(health.doom_loop_fired)     # False
    print(health.passed)              # True
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json

from .base import BaseEvaluator


@dataclass
class LoopHealthResult:
    """
    Result container for loop-health evaluation.

    Attributes:
        iterations_to_success: Iteration index (1-based) at which the threshold
            was first met, or the total iterations if it was never met.
        wasted_iterations: Iterations that ran after the threshold was first met
            (redundant work in optimize/review mode).
        doom_loop_fired: Whether a doom-loop guard event was observed.
        guard_interventions: Total number of guard/safety events observed.
        total_duration_s: Total wall-clock duration of the loop in seconds.
        score_delta_per_iteration: Per-iteration change in judge score
            (len == num_iterations - 1).
        converged: Whether the loop reached its threshold at all.
        success: Whether the loop is considered healthy (converged, no doom-loop).
        threshold: The score threshold used for convergence.
        reasoning: Human-readable explanation of the health assessment.
        metadata: Additional metadata.
    """

    iterations_to_success: int
    wasted_iterations: int
    doom_loop_fired: bool
    guard_interventions: int
    total_duration_s: float
    score_delta_per_iteration: List[float] = field(default_factory=list)
    converged: bool = False
    success: bool = False
    threshold: float = 8.0
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Alias for success to match other evaluator results."""
        return self.success

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "iterations_to_success": self.iterations_to_success,
            "wasted_iterations": self.wasted_iterations,
            "doom_loop_fired": self.doom_loop_fired,
            "guard_interventions": self.guard_interventions,
            "total_duration_s": self.total_duration_s,
            "score_delta_per_iteration": self.score_delta_per_iteration,
            "converged": self.converged,
            "success": self.success,
            "passed": self.passed,
            "threshold": self.threshold,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def print_summary(self) -> None:
        """Print a summary of the loop-health results."""
        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()

            table = Table(title="Loop Health Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", style="green" if self.success else "red")

            table.add_row("Status", "✅ HEALTHY" if self.success else "❌ UNHEALTHY")
            table.add_row("Converged", "✅" if self.converged else "❌")
            table.add_row("Iterations to Success", str(self.iterations_to_success))
            table.add_row("Wasted Iterations", str(self.wasted_iterations))
            table.add_row("Doom-Loop Fired", "⚠️ YES" if self.doom_loop_fired else "no")
            table.add_row("Guard Interventions", str(self.guard_interventions))
            table.add_row("Duration", f"{self.total_duration_s:.2f}s")
            if self.score_delta_per_iteration:
                table.add_row(
                    "Score Deltas",
                    " → ".join(f"{d:+.1f}" for d in self.score_delta_per_iteration),
                )

            console.print(table)
        except ImportError:
            print("Loop Health Summary")
            print(f"  Status: {'HEALTHY' if self.success else 'UNHEALTHY'}")
            print(f"  Converged: {self.converged}")
            print(f"  Iterations to Success: {self.iterations_to_success}")
            print(f"  Wasted Iterations: {self.wasted_iterations}")
            print(f"  Doom-Loop Fired: {self.doom_loop_fired}")
            print(f"  Guard Interventions: {self.guard_interventions}")
            print(f"  Duration: {self.total_duration_s:.2f}s")


# Guard event "type" values that indicate a doom-loop was detected. This
# covers both the generic markers used by callers and the concrete
# ``DoomLoopType`` values emitted by ``escalation/doom_loop.py``.
_DOOM_LOOP_EVENT_TYPES = frozenset(
    {
        "doom_loop",
        "doom-loop",
        "doomloop",
        "repetition",
        "loop_detected",
        # DoomLoopType enum values (escalation/doom_loop.py)
        "repeated_action",
        "repeated_failure",
        "no_progress",
        "circular_plan",
        "resource_exhaustion",
        "repeated_output",
    }
)


class LoopEvaluator(BaseEvaluator):
    """
    Evaluate the *health* of an evaluation/agent loop.

    Unlike ``EvaluationLoop`` (which scores output quality), this evaluator
    derives loop-health metrics from a completed ``EvaluationLoopResult`` and
    optional structured guard events.

    Args:
        threshold: Score threshold used to determine convergence. If not
            provided, the threshold recorded on the ``EvaluationLoopResult`` is
            used.
        max_wasted_iterations: Maximum wasted iterations tolerated before the
            loop is considered unhealthy (default: 0).
        name: Optional name for this evaluation run.
        verbose: Enable verbose output.

    Example:
        evaluator = LoopEvaluator(threshold=8.0)
        health = evaluator.run(loop_result, guard_events=guard_events)
        assert not health.doom_loop_fired
    """

    def __init__(
        self,
        threshold: Optional[float] = None,
        max_wasted_iterations: int = 0,
        name: Optional[str] = None,
        save_results_path: Optional[str] = None,
        verbose: bool = False,
    ):
        super().__init__(name=name, save_results_path=save_results_path, verbose=verbose)
        self.threshold = threshold
        self.max_wasted_iterations = max_wasted_iterations

    @staticmethod
    def _event_field(event: Any, *names: str, default: Any = None) -> Any:
        """Read a field from an event that may be a dict or an object."""
        if isinstance(event, dict):
            for name in names:
                if name in event:
                    return event[name]
            return default
        for name in names:
            if hasattr(event, name):
                return getattr(event, name)
        return default

    @classmethod
    def _is_doom_loop_event(cls, event: Any) -> bool:
        """
        Return True if a guard event indicates a doom-loop was detected.

        Handles the package's real guard shapes as well as generic markers:
        - ``DoomLoopEvent`` (``escalation/doom_loop.py``): presence of a
          ``loop_type`` (a ``DoomLoopType`` enum) means a loop fired.
        - ``DoomLoopResult`` (``permissions/doom_loop.py``): ``is_loop`` bool.
        - Generic dict/object markers via ``type``/``event`` fields or an
          explicit ``doom_loop``/``doom_loop_fired`` flag.
        """
        # DoomLoopResult-style: explicit boolean loop flag.
        is_loop = cls._event_field(event, "is_loop")
        if is_loop is not None:
            return bool(is_loop)

        # DoomLoopEvent-style: presence of a loop_type means a loop fired.
        loop_type = cls._event_field(event, "loop_type")
        if loop_type is not None:
            return True

        # Explicit doom-loop flags.
        if cls._event_field(event, "doom_loop", "doom_loop_fired", default=False):
            return True

        # Generic type/event markers (strings or enums).
        raw_type = cls._event_field(event, "type", "event", default="")
        event_type = str(getattr(raw_type, "value", raw_type)).lower()
        return event_type in _DOOM_LOOP_EVENT_TYPES

    def run(
        self,
        loop_result: Any,
        guard_events: Optional[List[Any]] = None,
        **kwargs,
    ) -> LoopHealthResult:
        """
        Score loop health from a completed loop result.

        Args:
            loop_result: An ``EvaluationLoopResult`` (or any object exposing
                ``score_history``, ``threshold`` and ``total_duration_seconds``).
            guard_events: Optional list of structured guard events. Each event
                may be a dict or object with a ``type``/``event`` field; events
                whose type indicates a doom-loop set ``doom_loop_fired``.

        Returns:
            LoopHealthResult with computed health metrics.
        """
        self.before_run()

        guard_events = guard_events or []

        score_history: List[float] = list(getattr(loop_result, "score_history", []) or [])
        threshold = self.threshold
        if threshold is None:
            threshold = float(getattr(loop_result, "threshold", 8.0))
        total_duration = float(getattr(loop_result, "total_duration_seconds", 0.0))
        num_iterations = len(score_history)

        # The loop mode and its own success verdict, when available. In
        # "review" mode ``EvaluationLoop`` runs every iteration and derives
        # success from the *final* score, so a transient earlier score above
        # the threshold must not be treated as convergence (an earlier high
        # score followed by a lower final score is a failed run).
        mode = str(getattr(loop_result, "mode", "optimize") or "optimize").lower()
        loop_success = getattr(loop_result, "success", None)

        # Iteration (1-based) at which threshold was first met.
        iterations_to_success = num_iterations
        converged = False
        for idx, score in enumerate(score_history, start=1):
            if score >= threshold:
                iterations_to_success = idx
                converged = True
                break

        # In review mode, defer to the final score / loop's own success so the
        # health verdict never disagrees with the loop result itself.
        if mode == "review" and num_iterations:
            final_converged = score_history[-1] >= threshold
            if loop_success is not None:
                final_converged = bool(loop_success)
            converged = final_converged
            iterations_to_success = num_iterations

        # Iterations that ran after threshold was first met = wasted work.
        # Only meaningful in optimize mode, where the loop stops on success;
        # review mode intentionally runs all iterations.
        wasted_iterations = (
            num_iterations - iterations_to_success
            if (converged and mode != "review")
            else 0
        )

        # Per-iteration score deltas.
        score_delta_per_iteration = [
            round(score_history[i] - score_history[i - 1], 4)
            for i in range(1, num_iterations)
        ]

        # Guard / doom-loop analysis.
        guard_interventions = len(guard_events)
        doom_loop_fired = any(self._is_doom_loop_event(e) for e in guard_events)

        success = (
            converged
            and not doom_loop_fired
            and wasted_iterations <= self.max_wasted_iterations
        )

        reasoning = self._build_reasoning(
            converged=converged,
            iterations_to_success=iterations_to_success,
            num_iterations=num_iterations,
            wasted_iterations=wasted_iterations,
            doom_loop_fired=doom_loop_fired,
            guard_interventions=guard_interventions,
        )

        result = LoopHealthResult(
            iterations_to_success=iterations_to_success,
            wasted_iterations=wasted_iterations,
            doom_loop_fired=doom_loop_fired,
            guard_interventions=guard_interventions,
            total_duration_s=total_duration,
            score_delta_per_iteration=score_delta_per_iteration,
            converged=converged,
            success=success,
            threshold=threshold,
            reasoning=reasoning,
            metadata={"num_iterations": num_iterations},
        )

        self._result = result
        self.after_run(result)

        if self.verbose:
            result.print_summary()

        return result

    @staticmethod
    def _build_reasoning(
        converged: bool,
        iterations_to_success: int,
        num_iterations: int,
        wasted_iterations: int,
        doom_loop_fired: bool,
        guard_interventions: int,
    ) -> str:
        """Build a human-readable explanation of the health assessment."""
        parts: List[str] = []
        if converged:
            parts.append(
                f"Converged in {iterations_to_success} iteration(s)."
            )
        else:
            parts.append(
                f"Did not converge after {num_iterations} iteration(s)."
            )
        if wasted_iterations:
            parts.append(f"{wasted_iterations} wasted iteration(s) after threshold.")
        if doom_loop_fired:
            parts.append("Doom-loop guard fired.")
        if guard_interventions:
            parts.append(f"{guard_interventions} guard intervention(s).")
        return " ".join(parts)


__all__ = [
    "LoopEvaluator",
    "LoopHealthResult",
]
