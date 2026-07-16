"""Unit tests for PromptOptimizer and the keep-the-best eval loop."""

from unittest.mock import MagicMock, patch


class TestLoopKeepsBest:
    """The eval loop must keep the highest-scoring iteration, not the last."""

    def test_loop_returns_best_not_last(self):
        from praisonaiagents.eval.loop import EvaluationLoop

        agent = MagicMock()
        agent.chat.side_effect = ["o1", "o2", "o3"]

        judge = MagicMock()
        judge.run.side_effect = [
            MagicMock(score=5.0, reasoning="r1", suggestions=[]),
            MagicMock(score=9.0, reasoning="r2", suggestions=[]),
            MagicMock(score=4.0, reasoning="r3", suggestions=[]),
        ]

        loop = EvaluationLoop(
            agent=agent,
            criteria="be good",
            threshold=8.0,
            max_iterations=3,
            mode="review",
            judge=judge,
        )
        result = loop.run("prompt")

        assert result.best_score == 9.0
        assert result.best_output == "o2"
        assert result.success is True
        # Regression guard: final (last) score is the regressed 4.0
        assert result.final_score == 4.0

    def test_loop_numeric_metric(self):
        from praisonaiagents.eval.loop import EvaluationLoop

        agent = MagicMock()
        agent.chat.side_effect = ["short", "a longer answer here"]

        def metric(output):
            return float(len(output))

        loop = EvaluationLoop(
            agent=agent,
            criteria="",
            threshold=10.0,
            max_iterations=2,
            mode="review",
            metric=metric,
        )
        result = loop.run("prompt")

        assert result.best_output == "a longer answer here"
        assert result.best_score == float(len("a longer answer here"))


class TestPromptOptimizer:
    """PromptOptimizer selects the best variant and writes it back."""

    def _make_agent(self, instructions="base instructions"):
        from praisonaiagents import Agent
        return Agent(name="t", instructions=instructions, llm="gpt-4o-mini")

    def test_optimizer_selects_highest_scoring_variant(self):
        from praisonaiagents.eval.prompt_optimizer import PromptOptimizer

        agent = self._make_agent("base")
        agent.chat = MagicMock(return_value="out")

        evalset = [("p1", "e1")]

        # base scores 3.0, candidate "A" scores 9.0, candidate "B" scores 5.0
        scores = {"base": 3.0, "A": 9.0, "B": 5.0}

        opt = PromptOptimizer(agent, evalset, metric=lambda o, e: 0.0, n_candidates=2)
        opt._propose_variants = MagicMock(return_value=["A", "B"])
        opt._score_instructions = MagicMock(side_effect=lambda instr: scores[instr])

        result = opt.optimize()

        assert result.best_instructions == "A"
        assert result.best_score == 9.0
        assert result.base_score == 3.0
        assert result.applied is True
        assert agent.instructions == "A"
        assert result.improved is True

    def test_optimizer_apply_false_restores_instructions(self):
        from praisonaiagents.eval.prompt_optimizer import PromptOptimizer

        agent = self._make_agent("original")
        evalset = [("p1", "e1")]

        scores = {"original": 3.0, "better": 9.0}

        opt = PromptOptimizer(
            agent, evalset, metric=lambda o, e: 0.0, n_candidates=1, apply=False
        )
        opt._propose_variants = MagicMock(return_value=["better"])
        opt._score_instructions = MagicMock(side_effect=lambda instr: scores[instr])

        result = opt.optimize()

        assert result.best_instructions == "better"
        assert result.applied is False
        assert agent.instructions == "original"

    def test_optimizer_score_instructions_restores_on_error(self):
        from praisonaiagents.eval.prompt_optimizer import PromptOptimizer

        agent = self._make_agent("original")
        agent.chat = MagicMock(side_effect=RuntimeError("boom"))
        evalset = [("p1", "e1")]

        opt = PromptOptimizer(agent, evalset, metric=lambda o, e: 1.0)

        try:
            opt._score_instructions("temp")
        except RuntimeError:
            pass
        assert agent.instructions == "original"

    def test_optimizer_requires_evalset(self):
        import pytest
        from praisonaiagents.eval.prompt_optimizer import PromptOptimizer

        agent = self._make_agent()
        with pytest.raises(ValueError):
            PromptOptimizer(agent, [])

    def test_agent_optimize_instructions_method(self):
        from praisonaiagents import Agent

        assert hasattr(Agent, "optimize_instructions")
        assert hasattr(Agent, "aoptimize_instructions")

    def test_lazy_exports(self):
        from praisonaiagents.eval import PromptOptimizer, OptimizeResult

        assert PromptOptimizer is not None
        assert OptimizeResult is not None
