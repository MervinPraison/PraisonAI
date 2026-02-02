"""Unit tests for EvaluationLoop class and related dataclasses."""

import pytest
import time
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime


class TestIterationResult:
    """Tests for IterationResult dataclass."""
    
    def test_iteration_result_creation(self):
        """Test basic IterationResult creation."""
        from praisonaiagents.eval.results import IterationResult
        
        result = IterationResult(
            iteration=1,
            output="Test output",
            score=8.5,
            reasoning="Good quality",
            findings=["Finding 1", "Finding 2"],
        )
        
        assert result.iteration == 1
        assert result.output == "Test output"
        assert result.score == 8.5
        assert result.reasoning == "Good quality"
        assert result.findings == ["Finding 1", "Finding 2"]
        assert result.timestamp is not None
    
    def test_iteration_result_defaults(self):
        """Test IterationResult with default values."""
        from praisonaiagents.eval.results import IterationResult
        
        result = IterationResult(
            iteration=1,
            output="Test",
            score=7.0,
            reasoning="OK",
        )
        
        assert result.findings == []
        assert result.metadata == {}
    
    def test_iteration_result_to_dict(self):
        """Test IterationResult to_dict method."""
        from praisonaiagents.eval.results import IterationResult
        
        result = IterationResult(
            iteration=1,
            output="Test",
            score=8.0,
            reasoning="Good",
            findings=["F1"],
        )
        
        d = result.to_dict()
        assert d["iteration"] == 1
        assert d["output"] == "Test"
        assert d["score"] == 8.0
        assert d["reasoning"] == "Good"
        assert d["findings"] == ["F1"]
        assert "timestamp" in d
    
    def test_iteration_result_passed_property(self):
        """Test IterationResult passed property."""
        from praisonaiagents.eval.results import IterationResult
        
        # Default threshold is 7.0
        result_pass = IterationResult(iteration=1, output="", score=8.0, reasoning="")
        result_fail = IterationResult(iteration=1, output="", score=5.0, reasoning="")
        
        assert result_pass.passed is True
        assert result_fail.passed is False


class TestEvaluationLoopResult:
    """Tests for EvaluationLoopResult dataclass."""
    
    def test_evaluation_loop_result_creation(self):
        """Test basic EvaluationLoopResult creation."""
        from praisonaiagents.eval.results import EvaluationLoopResult, IterationResult
        
        iterations = [
            IterationResult(iteration=1, output="Out1", score=6.0, reasoning="R1"),
            IterationResult(iteration=2, output="Out2", score=7.5, reasoning="R2"),
            IterationResult(iteration=3, output="Out3", score=8.5, reasoning="R3"),
        ]
        
        result = EvaluationLoopResult(
            iterations=iterations,
            success=True,
            total_duration_seconds=5.5,
        )
        
        assert len(result.iterations) == 3
        assert result.success is True
        assert result.total_duration_seconds == 5.5
    
    def test_evaluation_loop_result_final_score(self):
        """Test final_score property returns last iteration score."""
        from praisonaiagents.eval.results import EvaluationLoopResult, IterationResult
        
        iterations = [
            IterationResult(iteration=1, output="", score=6.0, reasoning=""),
            IterationResult(iteration=2, output="", score=8.5, reasoning=""),
        ]
        
        result = EvaluationLoopResult(iterations=iterations, success=True)
        assert result.final_score == 8.5
    
    def test_evaluation_loop_result_score_history(self):
        """Test score_history property."""
        from praisonaiagents.eval.results import EvaluationLoopResult, IterationResult
        
        iterations = [
            IterationResult(iteration=1, output="", score=5.0, reasoning=""),
            IterationResult(iteration=2, output="", score=6.5, reasoning=""),
            IterationResult(iteration=3, output="", score=8.0, reasoning=""),
        ]
        
        result = EvaluationLoopResult(iterations=iterations, success=True)
        assert result.score_history == [5.0, 6.5, 8.0]
    
    def test_evaluation_loop_result_findings(self):
        """Test accumulated_findings property."""
        from praisonaiagents.eval.results import EvaluationLoopResult, IterationResult
        
        iterations = [
            IterationResult(iteration=1, output="", score=5.0, reasoning="", findings=["F1", "F2"]),
            IterationResult(iteration=2, output="", score=7.0, reasoning="", findings=["F3"]),
        ]
        
        result = EvaluationLoopResult(iterations=iterations, success=True)
        assert result.accumulated_findings == ["F1", "F2", "F3"]
    
    def test_evaluation_loop_result_final_output(self):
        """Test final_output property."""
        from praisonaiagents.eval.results import EvaluationLoopResult, IterationResult
        
        iterations = [
            IterationResult(iteration=1, output="First", score=5.0, reasoning=""),
            IterationResult(iteration=2, output="Final", score=8.0, reasoning=""),
        ]
        
        result = EvaluationLoopResult(iterations=iterations, success=True)
        assert result.final_output == "Final"
    
    def test_evaluation_loop_result_to_dict(self):
        """Test to_dict method."""
        from praisonaiagents.eval.results import EvaluationLoopResult, IterationResult
        
        iterations = [
            IterationResult(iteration=1, output="Out", score=8.0, reasoning="Good"),
        ]
        
        result = EvaluationLoopResult(
            iterations=iterations,
            success=True,
            total_duration_seconds=2.5,
        )
        
        d = result.to_dict()
        assert d["success"] is True
        assert d["final_score"] == 8.0
        assert d["score_history"] == [8.0]
        assert d["total_duration_seconds"] == 2.5
        assert len(d["iterations"]) == 1
    
    def test_evaluation_loop_result_to_json(self):
        """Test to_json method."""
        from praisonaiagents.eval.results import EvaluationLoopResult, IterationResult
        import json
        
        iterations = [
            IterationResult(iteration=1, output="Out", score=8.0, reasoning="Good"),
        ]
        
        result = EvaluationLoopResult(iterations=iterations, success=True)
        
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["success"] is True
        assert parsed["final_score"] == 8.0
    
    def test_evaluation_loop_result_final_report(self):
        """Test final_report property generates markdown."""
        from praisonaiagents.eval.results import EvaluationLoopResult, IterationResult
        
        iterations = [
            IterationResult(iteration=1, output="Out1", score=6.0, reasoning="Needs work", findings=["F1"]),
            IterationResult(iteration=2, output="Out2", score=8.5, reasoning="Good", findings=["F2"]),
        ]
        
        result = EvaluationLoopResult(
            iterations=iterations,
            success=True,
            total_duration_seconds=3.0,
        )
        
        report = result.final_report
        assert "# Evaluation Loop Report" in report
        assert "8.5" in report  # Final score
        assert "Success" in report or "✅" in report
        assert "Iteration 1" in report
        assert "Iteration 2" in report
    
    def test_evaluation_loop_result_empty_iterations(self):
        """Test with empty iterations list."""
        from praisonaiagents.eval.results import EvaluationLoopResult
        
        result = EvaluationLoopResult(iterations=[], success=False)
        
        assert result.final_score == 0.0
        assert result.score_history == []
        assert result.final_output == ""
        assert result.accumulated_findings == []


class TestEvaluationLoop:
    """Tests for EvaluationLoop class."""
    
    def test_evaluation_loop_init_defaults(self):
        """Test EvaluationLoop initialization with defaults."""
        from praisonaiagents.eval.loop import EvaluationLoop
        
        agent = MagicMock()
        loop = EvaluationLoop(
            agent=agent,
            criteria="Be helpful",
        )
        
        assert loop.agent == agent
        assert loop.criteria == "Be helpful"
        assert loop.threshold == 8.0
        assert loop.max_iterations == 5
        assert loop.mode == "optimize"
    
    def test_evaluation_loop_init_custom(self):
        """Test EvaluationLoop initialization with custom values."""
        from praisonaiagents.eval.loop import EvaluationLoop
        
        agent = MagicMock()
        judge = MagicMock()
        callback = MagicMock()
        
        loop = EvaluationLoop(
            agent=agent,
            criteria="Custom criteria",
            threshold=9.0,
            max_iterations=10,
            mode="review",
            judge=judge,
            on_iteration=callback,
            verbose=True,
        )
        
        assert loop.threshold == 9.0
        assert loop.max_iterations == 10
        assert loop.mode == "review"
        assert loop.judge == judge
        assert loop.on_iteration == callback
        assert loop.verbose is True
    
    def test_evaluation_loop_run_single_iteration_passes(self):
        """Test run() when first iteration passes threshold."""
        from praisonaiagents.eval.loop import EvaluationLoop
        from praisonaiagents.eval.results import EvaluationLoopResult
        
        agent = MagicMock()
        agent.chat.return_value = "Good output"
        
        judge = MagicMock()
        judge_result = MagicMock()
        judge_result.score = 9.0
        judge_result.reasoning = "Excellent"
        judge_result.suggestions = []
        judge.run.return_value = judge_result
        
        loop = EvaluationLoop(
            agent=agent,
            criteria="Be helpful",
            threshold=8.0,
            judge=judge,
        )
        
        result = loop.run("Test prompt")
        
        assert isinstance(result, EvaluationLoopResult)
        assert result.success is True
        assert result.final_score == 9.0
        assert len(result.iterations) == 1
    
    def test_evaluation_loop_run_multiple_iterations(self):
        """Test run() with multiple iterations before passing."""
        from praisonaiagents.eval.loop import EvaluationLoop
        
        agent = MagicMock()
        agent.chat.side_effect = ["Output 1", "Output 2", "Output 3"]
        
        judge = MagicMock()
        judge_results = [
            MagicMock(score=5.0, reasoning="Poor", suggestions=["Improve"]),
            MagicMock(score=7.0, reasoning="Better", suggestions=["More"]),
            MagicMock(score=8.5, reasoning="Good", suggestions=[]),
        ]
        judge.run.side_effect = judge_results
        
        loop = EvaluationLoop(
            agent=agent,
            criteria="Be helpful",
            threshold=8.0,
            max_iterations=5,
            judge=judge,
        )
        
        result = loop.run("Test prompt")
        
        assert result.success is True
        assert result.final_score == 8.5
        assert len(result.iterations) == 3
        assert result.score_history == [5.0, 7.0, 8.5]
    
    def test_evaluation_loop_run_max_iterations_reached(self):
        """Test run() when max iterations reached without passing."""
        from praisonaiagents.eval.loop import EvaluationLoop
        
        agent = MagicMock()
        agent.chat.return_value = "Output"
        
        judge = MagicMock()
        judge_result = MagicMock(score=5.0, reasoning="Poor", suggestions=["Improve"])
        judge.run.return_value = judge_result
        
        loop = EvaluationLoop(
            agent=agent,
            criteria="Be helpful",
            threshold=8.0,
            max_iterations=3,
            judge=judge,
        )
        
        result = loop.run("Test prompt")
        
        assert result.success is False
        assert len(result.iterations) == 3
        assert result.final_score == 5.0
    
    def test_evaluation_loop_run_review_mode(self):
        """Test run() in review mode (runs all iterations)."""
        from praisonaiagents.eval.loop import EvaluationLoop
        
        agent = MagicMock()
        agent.chat.return_value = "Output"
        
        judge = MagicMock()
        # Even high score shouldn't stop in review mode
        judge_result = MagicMock(score=9.0, reasoning="Great", suggestions=[])
        judge.run.return_value = judge_result
        
        loop = EvaluationLoop(
            agent=agent,
            criteria="Be helpful",
            threshold=8.0,
            max_iterations=3,
            mode="review",
            judge=judge,
        )
        
        result = loop.run("Test prompt")
        
        # Review mode runs all iterations
        assert len(result.iterations) == 3
        assert result.success is True
    
    def test_evaluation_loop_on_iteration_callback(self):
        """Test on_iteration callback is called."""
        from praisonaiagents.eval.loop import EvaluationLoop
        
        agent = MagicMock()
        agent.chat.return_value = "Output"
        
        judge = MagicMock()
        judge_result = MagicMock(score=9.0, reasoning="Good", suggestions=[])
        judge.run.return_value = judge_result
        
        callback_calls = []
        def on_iteration(iteration_result):
            callback_calls.append(iteration_result)
        
        loop = EvaluationLoop(
            agent=agent,
            criteria="Be helpful",
            threshold=8.0,
            judge=judge,
            on_iteration=on_iteration,
        )
        
        loop.run("Test prompt")
        
        assert len(callback_calls) == 1
        assert callback_calls[0].score == 9.0
    
    def test_evaluation_loop_extracts_findings(self):
        """Test that findings are extracted from suggestions."""
        from praisonaiagents.eval.loop import EvaluationLoop
        
        agent = MagicMock()
        agent.chat.return_value = "Output"
        
        judge = MagicMock()
        judge_result = MagicMock(
            score=9.0, 
            reasoning="Good", 
            suggestions=["Finding 1", "Finding 2"]
        )
        judge.run.return_value = judge_result
        
        loop = EvaluationLoop(
            agent=agent,
            criteria="Be helpful",
            threshold=8.0,
            judge=judge,
        )
        
        result = loop.run("Test prompt")
        
        assert result.iterations[0].findings == ["Finding 1", "Finding 2"]


class TestEvaluationLoopAsync:
    """Tests for EvaluationLoop async methods."""
    
    @pytest.mark.asyncio
    async def test_evaluation_loop_run_async(self):
        """Test run_async() method."""
        from praisonaiagents.eval.loop import EvaluationLoop
        from praisonaiagents.eval.results import EvaluationLoopResult
        
        agent = MagicMock()
        agent.chat_async = AsyncMock(return_value="Output")
        
        judge = MagicMock()
        judge_result = MagicMock(score=9.0, reasoning="Good", suggestions=[])
        judge.run_async = AsyncMock(return_value=judge_result)
        
        loop = EvaluationLoop(
            agent=agent,
            criteria="Be helpful",
            threshold=8.0,
            judge=judge,
        )
        
        result = await loop.run_async("Test prompt")
        
        assert isinstance(result, EvaluationLoopResult)
        assert result.success is True
        assert result.final_score == 9.0


class TestAgentRunUntil:
    """Tests for Agent.run_until() method."""
    
    def test_agent_run_until_exists(self):
        """Test that Agent has run_until method."""
        from praisonaiagents import Agent
        
        assert hasattr(Agent, 'run_until')
    
    def test_agent_run_until_basic(self):
        """Test Agent.run_until() basic usage."""
        from praisonaiagents import Agent
        from praisonaiagents.eval.results import EvaluationLoopResult
        
        with patch('praisonaiagents.eval.loop.EvaluationLoop') as MockLoop:
            mock_result = MagicMock(spec=EvaluationLoopResult)
            mock_result.success = True
            mock_result.final_score = 8.5
            
            mock_loop_instance = MagicMock()
            mock_loop_instance.run.return_value = mock_result
            MockLoop.return_value = mock_loop_instance
            
            agent = Agent(name="test", instructions="Be helpful")
            result = agent.run_until(
                "Test prompt",
                criteria="Be helpful",
                threshold=8.0,
            )
            
            assert result.success is True
            MockLoop.assert_called_once()


class TestEvaluationLoopProtocol:
    """Tests for EvaluationLoopProtocol."""
    
    def test_protocol_exists(self):
        """Test that EvaluationLoopProtocol exists."""
        from praisonaiagents.eval.protocols import EvaluationLoopProtocol
        
        assert EvaluationLoopProtocol is not None
    
    def test_evaluation_loop_implements_protocol(self):
        """Test that EvaluationLoop implements the protocol."""
        from praisonaiagents.eval.loop import EvaluationLoop
        from praisonaiagents.eval.protocols import EvaluationLoopProtocol
        
        # Check that EvaluationLoop has required methods
        assert hasattr(EvaluationLoop, 'run')
        assert hasattr(EvaluationLoop, 'run_async')


class TestLazyLoading:
    """Tests for lazy loading of EvaluationLoop."""
    
    def test_lazy_import_from_eval(self):
        """Test that EvaluationLoop can be imported from eval module."""
        from praisonaiagents.eval import EvaluationLoop
        
        assert EvaluationLoop is not None
    
    def test_lazy_import_results(self):
        """Test that result classes can be imported from eval module."""
        from praisonaiagents.eval import IterationResult, EvaluationLoopResult
        
        assert IterationResult is not None
        assert EvaluationLoopResult is not None
