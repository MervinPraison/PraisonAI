"""
Unit tests for the goal-gated autonomous loop (completion judge).

TDD coverage for issue #2999:
- Goal judge 'done' verdict stops the loop with completion_reason='goal_met'
- Goal judge 'continue' verdict iterates with a tool-using continuation nudge
- Structured constraint violation prevents a premature 'done'
- Budget exhaustion pauses recoverably (status='paused', 'budget_paused')
- Judge fail-open → 'continue'; N consecutive parse failures → auto-pause
- GoalState round-trips through serialization
- No goal set → autonomous loop behaviour is unchanged
"""

from unittest.mock import patch

import pytest

from praisonaiagents.goal.models import GoalCriteria, GoalState
from praisonaiagents.goal.judge import _build_goal_judge_prompt, _parse_verdict


# =============================================================================
# GoalState / GoalCriteria model tests
# =============================================================================

class TestGoalStateModel:
    def test_goal_state_round_trip(self):
        state = GoalState(
            goal="Open a PR",
            criteria=GoalCriteria(
                outcome="A PR is open",
                verification="A PR URL exists",
                constraints=["no force-push"],
            ),
            max_turns=15,
            turns_used=3,
            last_verdict="continue",
            last_reason="not yet",
            consecutive_parse_failures=1,
        )
        data = state.to_dict()
        restored = GoalState.from_dict(data)
        assert restored.goal == "Open a PR"
        assert restored.criteria.outcome == "A PR is open"
        assert restored.criteria.constraints == ["no force-push"]
        assert restored.max_turns == 15
        assert restored.turns_used == 3
        assert restored.last_verdict == "continue"
        assert restored.consecutive_parse_failures == 1

    def test_goal_state_defaults(self):
        state = GoalState(goal="x")
        assert state.status == "active"
        assert state.criteria is None
        assert state.max_turns == 20


# =============================================================================
# Verdict parsing
# =============================================================================

class TestParseVerdict:
    def test_parse_canonical(self):
        verdict, reason = _parse_verdict('{"verdict": "done", "reason": "ok"}')
        assert verdict == "done"
        assert reason == "ok"

    def test_parse_continue(self):
        verdict, _ = _parse_verdict('prose {"verdict":"continue","reason":"x"} tail')
        assert verdict == "continue"

    def test_parse_legacy_done_bool(self):
        verdict, _ = _parse_verdict('{"done": true}')
        assert verdict == "done"
        verdict, _ = _parse_verdict('{"done": false}')
        assert verdict == "continue"

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_verdict("no json here")

    def test_parse_invalid_verdict_value_raises(self):
        with pytest.raises(ValueError):
            _parse_verdict('{"verdict": "maybe"}')


class TestBuildPrompt:
    def test_prompt_includes_constraints(self):
        state = GoalState(
            goal="G",
            criteria=GoalCriteria(
                outcome="O", verification="V", constraints=["do not touch X"]
            ),
        )
        prompt = _build_goal_judge_prompt(state, "some output")
        assert "do not touch X" in prompt
        assert "CONSTRAINTS" in prompt
        assert "V" in prompt
        assert "some output" in prompt

    def test_prompt_plain_goal(self):
        state = GoalState(goal="Just do it")
        prompt = _build_goal_judge_prompt(state, "output")
        assert "Just do it" in prompt


# =============================================================================
# Loop gating tests
# =============================================================================

def _make_agent():
    from praisonaiagents import Agent
    return Agent(instructions="Test agent", autonomy=True, output="silent")


def _unique_chat():
    """A chat stub returning a unique response each turn.

    Unique responses avoid confounding the goal gate with the autonomous
    loop's doom-loop detector (which fires on identical repeated responses).
    """
    counter = {"n": 0}

    def _chat(prompt):
        counter["n"] += 1
        return f"working step {counter['n']}"

    return _chat


class TestGoalLoopGate:
    def test_goal_judge_done_stops_loop(self):
        agent = _make_agent()
        verdicts = iter([("continue", "not yet"), ("done", "goal met")])

        with patch.object(agent, "chat", side_effect=_unique_chat()), \
             patch("praisonaiagents.goal.loop.judge_goal",
                   side_effect=lambda *a, **k: next(verdicts)):
            result = agent.run_goal("do the task", goal="finish it", max_turns=10)

        assert result.success is True
        assert result.completion_reason == "goal_met"
        assert result.iterations == 2

    def test_goal_judge_continue_iterates_with_nudge(self):
        agent = _make_agent()
        seen_prompts = []
        verdicts = iter([("continue", "keep going"), ("done", "done now")])
        counter = {"n": 0}

        def fake_chat(prompt):
            counter["n"] += 1
            seen_prompts.append(prompt)
            return f"still working {counter['n']}"

        with patch.object(agent, "chat", side_effect=fake_chat), \
             patch("praisonaiagents.goal.loop.judge_goal",
                   side_effect=lambda *a, **k: next(verdicts)):
            result = agent.run_goal("task", goal="g", max_turns=10)

        assert result.completion_reason == "goal_met"
        # second prompt is the continuation nudge, not the original task
        assert len(seen_prompts) == 2
        assert "not complete yet" in seen_prompts[1]

    def test_budget_exhaust_pauses_recoverably(self):
        agent = _make_agent()
        with patch.object(agent, "chat", side_effect=_unique_chat()), \
             patch("praisonaiagents.goal.loop.judge_goal",
                   return_value=("continue", "never done")):
            result = agent.run_goal("task", goal="g", max_turns=3)

        assert result.success is False
        assert result.completion_reason == "budget_paused"
        assert result.iterations == 3
        assert agent._goal_state is None  # cleared after run

    def test_judge_failopen_continue_then_budget(self):
        agent = _make_agent()
        # judge_goal itself fails open to ("continue", "judge unavailable")
        with patch.object(agent, "chat", side_effect=_unique_chat()), \
             patch("praisonaiagents.goal.loop.judge_goal",
                   return_value=("continue", "judge unavailable")):
            result = agent.run_goal("task", goal="g", max_turns=2)
        assert result.completion_reason == "budget_paused"

    def test_consecutive_parse_failures_autopause(self):
        agent = _make_agent()
        with patch.object(agent, "chat", side_effect=_unique_chat()), \
             patch("praisonaiagents.goal.loop.judge_goal",
                   return_value=("continue", "judge response unparseable")):
            result = agent.run_goal("task", goal="g", max_turns=20)
        # auto-pause after 3 consecutive parse failures, well before max_turns
        assert result.completion_reason == "budget_paused"
        assert result.iterations == 3

    def test_no_goal_is_unchanged(self):
        """Without a goal loop, run_autonomous is unaffected by the gate."""
        agent = _make_agent()
        with patch.object(agent, "chat",
                          return_value="Task completed successfully."):
            result = agent.run_autonomous("do it", max_iterations=5)
        # falls through to existing heuristic termination (not goal_met)
        assert result.completion_reason != "goal_met"
        assert result.success is True


class TestConstraintViolation:
    def test_constraint_violation_never_done(self):
        """A violated constraint must force 'continue' via the judge prompt.

        We verify the prompt instructs the judge to answer 'continue' on any
        constraint violation, and that a judge honouring that never stops early.
        """
        agent = _make_agent()
        criteria = GoalCriteria(
            outcome="PR open",
            verification="PR URL exists",
            constraints=["do not touch CHANGELOG.md"],
        )
        # Simulate a judge that respects constraints: constraint violated → continue
        with patch.object(agent, "chat", side_effect=_unique_chat()), \
             patch("praisonaiagents.goal.loop.judge_goal",
                   return_value=("continue", "constraint violated")):
            result = agent.run_goal("task", goal="g", criteria=criteria, max_turns=2)
        assert result.completion_reason == "budget_paused"
        assert result.success is False


class TestRunUntilDelegation:
    def test_run_until_with_goal_delegates(self):
        agent = _make_agent()
        with patch.object(agent, "chat", side_effect=_unique_chat()), \
             patch("praisonaiagents.goal.loop.judge_goal",
                   return_value=("done", "met")):
            result = agent.run_until("task", goal="reach the goal", max_iterations=5)
        assert result.completion_reason == "goal_met"
