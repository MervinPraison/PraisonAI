"""
Unit tests for the Goal Engineering module.

Tests cover:
- Goal / SuccessCriterion models (progress, achievement, serialization)
- GoalConfig defaults
- GoalEngineer decomposition (without network) and verification (mocked judge)
- Public exports from the package root
"""

import pytest

from praisonaiagents.goal import (
    Goal,
    GoalConfig,
    GoalEngineer,
    GoalVerificationResult,
    SuccessCriterion,
)
from praisonaiagents.goal.engineer import GoalEngineer as EngineerClass


# =============================================================================
# Model tests
# =============================================================================

class TestGoalModels:
    def test_add_criterion_and_progress(self):
        goal = Goal(statement="Write a haiku")
        assert goal.progress == 0.0
        assert not goal.is_achieved

        c1 = goal.add_criterion("Has three lines")
        goal.add_criterion("Follows 5-7-5")
        assert len(goal.criteria) == 2

        c1.status = "met"
        assert 0.0 < goal.progress < 1.0
        assert not goal.is_achieved

        for c in goal.criteria:
            c.status = "met"
        assert goal.progress == 1.0
        assert goal.is_achieved

    def test_weighted_progress(self):
        goal = Goal(statement="Ship feature")
        a = goal.add_criterion("Core done", weight=3.0)
        goal.add_criterion("Docs done", weight=1.0)
        a.status = "met"
        assert goal.progress == pytest.approx(0.75)

    def test_serialization_round_trip(self):
        goal = Goal(statement="Do X", constraints=["No side effects"])
        goal.add_criterion("Criterion 1")
        data = goal.to_dict()
        restored = Goal.from_dict(data)
        assert restored.statement == goal.statement
        assert restored.constraints == goal.constraints
        assert len(restored.criteria) == 1
        assert restored.criteria[0].description == "Criterion 1"

    def test_to_prompt_includes_parts(self):
        goal = Goal(statement="Summarise", constraints=["Under 100 words"])
        goal.add_criterion("Key points kept")
        prompt = goal.to_prompt()
        assert "Summarise" in prompt
        assert "Key points kept" in prompt
        assert "Under 100 words" in prompt

    def test_criterion_serialization(self):
        c = SuccessCriterion(description="D", weight=2.0, status="met")
        assert SuccessCriterion.from_dict(c.to_dict()).weight == 2.0


# =============================================================================
# Config tests
# =============================================================================

class TestGoalConfig:
    def test_defaults(self):
        cfg = GoalConfig()
        assert cfg.model is not None
        assert cfg.max_criteria == 5
        assert cfg.threshold == 8.0
        assert cfg.auto_decompose is True


# =============================================================================
# Engineer tests (no network)
# =============================================================================

class TestGoalEngineer:
    def test_engineer_with_explicit_criteria(self):
        engineer = GoalEngineer(auto_decompose=False)
        goal = engineer.engineer(
            "Summarise the report",
            criteria=["Under 100 words", "Preserves findings"],
            constraints=["No hallucinations"],
        )
        assert isinstance(goal, Goal)
        assert len(goal.criteria) == 2
        assert goal.constraints == ["No hallucinations"]

    def test_engineer_no_auto_decompose_leaves_empty(self):
        engineer = GoalEngineer(auto_decompose=False)
        goal = engineer.engineer("Some goal")
        assert goal.criteria == []

    def test_parse_criteria_json(self):
        parsed = EngineerClass._parse_criteria('["a", "b", "c"]')
        assert parsed == ["a", "b", "c"]

    def test_parse_criteria_bullets(self):
        parsed = EngineerClass._parse_criteria("- first\n- second\n1. third")
        assert parsed == ["first", "second", "third"]

    def test_verify_with_mocked_judge(self, monkeypatch):
        engineer = GoalEngineer(auto_decompose=False, threshold=8.0)
        goal = engineer.engineer("Answer correctly", criteria=["Correct"])

        class FakeJudgeResult:
            score = 9.0
            reasoning = "Looks correct"

        class FakeJudge:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, output=""):
                return FakeJudgeResult()

        import praisonaiagents.eval as eval_mod
        monkeypatch.setattr(eval_mod, "Judge", FakeJudge, raising=False)

        result = engineer.verify(goal, "The answer is 4")
        assert isinstance(result, GoalVerificationResult)
        assert result.score == 9.0
        assert result.achieved is True
        assert all(c.status == "met" for c in result.criteria)

    def test_verify_below_threshold(self, monkeypatch):
        engineer = GoalEngineer(auto_decompose=False, threshold=8.0)
        goal = engineer.engineer("Answer correctly", criteria=["Correct"])

        class FakeJudgeResult:
            score = 3.0
            reasoning = "Wrong"

        class FakeJudge:
            def __init__(self, *args, **kwargs):
                pass

            def run(self, output=""):
                return FakeJudgeResult()

        import praisonaiagents.eval as eval_mod
        monkeypatch.setattr(eval_mod, "Judge", FakeJudge, raising=False)

        result = engineer.verify(goal, "Nope")
        assert result.achieved is False
        assert all(c.status == "unmet" for c in result.criteria)


# =============================================================================
# Export tests
# =============================================================================

class TestExports:
    def test_root_exports(self):
        import praisonaiagents as pa

        assert pa.GoalEngineer is GoalEngineer
        assert pa.Goal is Goal
        assert pa.GoalConfig is GoalConfig
        assert pa.SuccessCriterion is SuccessCriterion
        assert pa.GoalVerificationResult is GoalVerificationResult
