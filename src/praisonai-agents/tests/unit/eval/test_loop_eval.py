"""Unit tests for LoopEvaluator and LoopHealthResult."""

import pytest


def _make_loop_result(scores, threshold=8.0, duration=1.0, mode="optimize"):
    """Build an EvaluationLoopResult from a list of scores."""
    from praisonaiagents.eval.results import IterationResult, EvaluationLoopResult

    iterations = [
        IterationResult(iteration=i + 1, output=f"out{i}", score=s, reasoning="r")
        for i, s in enumerate(scores)
    ]
    success = bool(scores) and scores[-1] >= threshold
    return EvaluationLoopResult(
        iterations=iterations,
        success=success,
        total_duration_seconds=duration,
        threshold=threshold,
        mode=mode,
    )


class TestImport:
    def test_loop_evaluator_importable(self):
        from praisonaiagents.eval import LoopEvaluator, LoopHealthResult  # noqa: F401

    def test_in_dir(self):
        import praisonaiagents.eval as e

        assert "LoopEvaluator" in dir(e)
        assert "LoopHealthResult" in dir(e)


class TestConvergence:
    def test_convergent_loop_is_healthy(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([6.0, 8.5], threshold=8.0)
        health = LoopEvaluator().run(result)

        assert health.converged is True
        assert health.iterations_to_success == 2
        assert health.wasted_iterations == 0
        assert health.doom_loop_fired is False
        assert health.success is True
        assert health.passed is True

    def test_score_deltas(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([5.0, 6.5, 9.0], threshold=8.0)
        health = LoopEvaluator().run(result)

        assert health.score_delta_per_iteration == [1.5, 2.5]

    def test_uses_threshold_from_result_when_unset(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([9.0], threshold=8.5)
        health = LoopEvaluator().run(result)

        assert health.threshold == 8.5
        assert health.converged is True


class TestNonConvergence:
    def test_non_convergent_loop_fails(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([4.0, 5.0, 6.0], threshold=8.0)
        health = LoopEvaluator().run(result)

        assert health.converged is False
        assert health.iterations_to_success == 3
        assert health.wasted_iterations == 0
        assert health.success is False


class TestWaste:
    def test_wasted_iterations_after_threshold(self):
        from praisonaiagents.eval import LoopEvaluator

        # Threshold met at iteration 2, but loop ran two more.
        result = _make_loop_result([6.0, 8.5, 8.6, 9.0], threshold=8.0)
        health = LoopEvaluator().run(result)

        assert health.iterations_to_success == 2
        assert health.wasted_iterations == 2
        assert health.success is False  # default max_wasted_iterations=0

    def test_wasted_iterations_tolerance(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([6.0, 8.5, 8.6], threshold=8.0)
        health = LoopEvaluator(max_wasted_iterations=1).run(result)

        assert health.wasted_iterations == 1
        assert health.success is True


class TestDoomLoop:
    def test_doom_loop_event_flags_failure(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([6.0, 8.5], threshold=8.0)
        health = LoopEvaluator().run(
            result, guard_events=[{"type": "doom_loop", "detail": "repetition"}]
        )

        assert health.doom_loop_fired is True
        assert health.guard_interventions == 1
        assert health.success is False

    def test_doom_loop_via_object_event(self):
        from praisonaiagents.eval import LoopEvaluator

        class Event:
            type = "loop_detected"

        result = _make_loop_result([9.0], threshold=8.0)
        health = LoopEvaluator().run(result, guard_events=[Event()])

        assert health.doom_loop_fired is True

    def test_non_doom_guard_events_counted_not_fatal(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([9.0], threshold=8.0)
        health = LoopEvaluator().run(
            result, guard_events=[{"type": "info", "msg": "noted"}]
        )

        assert health.doom_loop_fired is False
        assert health.guard_interventions == 1
        assert health.success is True

    def test_real_doom_loop_event_loop_type(self):
        """DoomLoopEvent (escalation/doom_loop.py) exposes a ``loop_type``."""
        from praisonaiagents.eval import LoopEvaluator

        class DoomLoopType:
            value = "repeated_action"

        class DoomLoopEvent:
            loop_type = DoomLoopType()
            description = "same action repeated"

        result = _make_loop_result([9.0], threshold=8.0)
        health = LoopEvaluator().run(result, guard_events=[DoomLoopEvent()])

        assert health.doom_loop_fired is True
        assert health.success is False

    def test_real_doom_loop_result_is_loop(self):
        """DoomLoopResult (permissions/doom_loop.py) exposes ``is_loop``."""
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([9.0], threshold=8.0)
        health = LoopEvaluator().run(
            result, guard_events=[{"is_loop": True, "reason": "stuck"}]
        )

        assert health.doom_loop_fired is True
        assert health.success is False

    def test_doom_loop_result_is_loop_false_not_fatal(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([9.0], threshold=8.0)
        health = LoopEvaluator().run(
            result, guard_events=[{"is_loop": False, "reason": "ok"}]
        )

        assert health.doom_loop_fired is False
        assert health.success is True

    def test_doom_loop_type_enum_value_string(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([9.0], threshold=8.0)
        health = LoopEvaluator().run(
            result, guard_events=[{"type": "resource_exhaustion"}]
        )

        assert health.doom_loop_fired is True


class TestReviewMode:
    def test_review_mode_transient_high_score_not_healthy(self):
        """Earlier high score with failing final score must not be healthy."""
        from praisonaiagents.eval import LoopEvaluator

        # scores [9.0, 8.0, 6.0]: final score 6.0 < 8.0 → loop failed.
        result = _make_loop_result([9.0, 8.0, 6.0], threshold=8.0, mode="review")
        health = LoopEvaluator(max_wasted_iterations=5).run(result)

        assert health.converged is False
        assert health.wasted_iterations == 0
        assert health.success is False

    def test_review_mode_final_score_passes(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([6.0, 7.0, 9.0], threshold=8.0, mode="review")
        health = LoopEvaluator().run(result)

        assert health.converged is True
        assert health.wasted_iterations == 0
        assert health.success is True


class TestResultSerialization:
    def test_to_dict_and_json(self):
        from praisonaiagents.eval import LoopEvaluator

        result = _make_loop_result([9.0], threshold=8.0)
        health = LoopEvaluator().run(result)

        d = health.to_dict()
        assert d["converged"] is True
        assert d["passed"] is True
        assert "score_delta_per_iteration" in d

        import json

        assert json.loads(health.to_json())["success"] is True
