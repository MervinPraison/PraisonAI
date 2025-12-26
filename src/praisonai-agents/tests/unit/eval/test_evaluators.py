"""Unit tests for evaluator classes."""

import pytest
import time
from unittest.mock import MagicMock, patch, AsyncMock

from praisonaiagents.eval.accuracy import AccuracyEvaluator
from praisonaiagents.eval.performance import PerformanceEvaluator
from praisonaiagents.eval.reliability import ReliabilityEvaluator
from praisonaiagents.eval.criteria import CriteriaEvaluator
from praisonaiagents.eval.results import (
    AccuracyResult,
    PerformanceResult,
    ReliabilityResult,
    CriteriaResult,
)


class TestAccuracyEvaluator:
    """Tests for AccuracyEvaluator class."""
    
    def test_init_with_func(self):
        """Test initialization with function."""
        func = lambda x: "test output"
        evaluator = AccuracyEvaluator(
            func=func,
            input_text="test input",
            expected_output="test output"
        )
        assert evaluator.func == func
        assert evaluator.input_text == "test input"
        assert evaluator.expected_output == "test output"
    
    def test_init_with_agent(self):
        """Test initialization with agent."""
        agent = MagicMock()
        evaluator = AccuracyEvaluator(
            agent=agent,
            input_text="test",
            expected_output="expected"
        )
        assert evaluator.agent == agent
    
    def test_init_requires_agent_or_func(self):
        """Test that either agent or func must be provided."""
        with pytest.raises(ValueError, match="Either 'agent' or 'func' must be provided"):
            AccuracyEvaluator(
                input_text="test",
                expected_output="expected"
            )
    
    def test_get_output_from_func(self):
        """Test getting output from function."""
        func = lambda x: f"output for {x}"
        evaluator = AccuracyEvaluator(
            func=func,
            input_text="test",
            expected_output="expected"
        )
        output = evaluator._get_output()
        assert output == "output for test"
    
    def test_get_output_from_agent_chat(self):
        """Test getting output from agent with chat method."""
        agent = MagicMock()
        agent.chat.return_value = "agent response"
        
        evaluator = AccuracyEvaluator(
            agent=agent,
            input_text="test",
            expected_output="expected"
        )
        output = evaluator._get_output()
        assert output == "agent response"
        agent.chat.assert_called_once_with("test")
    
    def test_get_output_from_agent_start(self):
        """Test getting output from agent with start method."""
        agent = MagicMock(spec=['start'])
        result = MagicMock()
        result.raw = "agent result"
        agent.start.return_value = result
        
        evaluator = AccuracyEvaluator(
            agent=agent,
            input_text="test",
            expected_output="expected"
        )
        output = evaluator._get_output()
        assert output == "agent result"
    
    def test_judge_output(self):
        """Test LLM judging of output."""
        with patch('litellm.completion') as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 8\nREASONING: Good match"
            mock_completion.return_value = mock_response
            
            def test_func(x):
                return "4"
            
            evaluator = AccuracyEvaluator(
                func=test_func,
                input_text="What is 2+2?",
                expected_output="4"
            )
            
            score = evaluator._judge_output("4")
            assert score.score == 8.0
            assert "Good match" in score.reasoning
    
    def test_run_returns_accuracy_result(self):
        """Test that run returns AccuracyResult."""
        with patch('litellm.completion') as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 9\nREASONING: Excellent"
            mock_completion.return_value = mock_response
            
            def test_func(x):
                return "4"
            
            evaluator = AccuracyEvaluator(
                func=test_func,
                input_text="What is 2+2?",
                expected_output="4",
                num_iterations=2
            )
            
            result = evaluator.run()
            assert isinstance(result, AccuracyResult)
            assert len(result.evaluations) == 2
    
    def test_evaluate_output(self):
        """Test evaluate_output method for pre-generated outputs."""
        with patch('litellm.completion') as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 10\nREASONING: Perfect"
            mock_completion.return_value = mock_response
            
            def test_func(x):
                return "unused"
            
            evaluator = AccuracyEvaluator(
                func=test_func,
                input_text="What is 2+2?",
                expected_output="4"
            )
            
            result = evaluator.evaluate_output("4")
            assert isinstance(result, AccuracyResult)
            assert len(result.evaluations) == 1
            assert result.evaluations[0].score == 10.0


class TestPerformanceEvaluator:
    """Tests for PerformanceEvaluator class."""
    
    def test_init_with_func(self):
        """Test initialization with function."""
        func = lambda: time.sleep(0.01)
        evaluator = PerformanceEvaluator(
            func=func,
            num_iterations=5,
            warmup_runs=2
        )
        assert evaluator.func == func
        assert evaluator.num_iterations == 5
        assert evaluator.warmup_runs == 2
    
    def test_init_with_agent(self):
        """Test initialization with agent."""
        agent = MagicMock()
        evaluator = PerformanceEvaluator(
            agent=agent,
            input_text="test",
            num_iterations=3
        )
        assert evaluator.agent == agent
        assert evaluator.input_text == "test"
    
    def test_init_requires_func_or_agent(self):
        """Test that either func or agent must be provided."""
        with pytest.raises(ValueError, match="Either 'func' or 'agent' must be provided"):
            PerformanceEvaluator()
    
    def test_run_measures_time(self):
        """Test that run measures execution time."""
        call_count = 0
        def slow_func():
            nonlocal call_count
            call_count += 1
            time.sleep(0.01)
        
        evaluator = PerformanceEvaluator(
            func=slow_func,
            num_iterations=3,
            warmup_runs=1,
            track_memory=False
        )
        
        result = evaluator.run()
        assert isinstance(result, PerformanceResult)
        assert len(result.metrics) == 3
        assert all(m.run_time >= 0.01 for m in result.metrics)
        assert call_count == 4  # 1 warmup + 3 iterations
    
    def test_run_with_agent(self):
        """Test run with agent."""
        agent = MagicMock()
        agent.chat.return_value = "response"
        
        evaluator = PerformanceEvaluator(
            agent=agent,
            input_text="test",
            num_iterations=2,
            warmup_runs=1,
            track_memory=False
        )
        
        result = evaluator.run()
        assert isinstance(result, PerformanceResult)
        assert len(result.metrics) == 2
        assert agent.chat.call_count == 3  # 1 warmup + 2 iterations


class TestReliabilityEvaluator:
    """Tests for ReliabilityEvaluator class."""
    
    def test_init(self):
        """Test initialization."""
        agent = MagicMock()
        evaluator = ReliabilityEvaluator(
            agent=agent,
            input_text="test",
            expected_tools=["search", "calculate"]
        )
        assert evaluator.agent == agent
        assert evaluator.expected_tools == {"search", "calculate"}
    
    def test_init_requires_agent(self):
        """Test that agent must be provided."""
        with pytest.raises(ValueError, match="'agent' must be provided"):
            ReliabilityEvaluator(
                input_text="test",
                expected_tools=["search"]
            )
    
    def test_evaluate_tool_calls(self):
        """Test evaluate_tool_calls method."""
        agent = MagicMock()
        evaluator = ReliabilityEvaluator(
            agent=agent,
            input_text="test",
            expected_tools=["search", "calculate"],
            forbidden_tools=["delete"]
        )
        
        result = evaluator.evaluate_tool_calls(["search", "calculate"])
        assert isinstance(result, ReliabilityResult)
        assert result.passed is True
        assert len(result.passed_calls) == 3  # 2 expected + 1 forbidden not called
    
    def test_evaluate_tool_calls_with_failures(self):
        """Test evaluate_tool_calls with missing tools."""
        agent = MagicMock()
        evaluator = ReliabilityEvaluator(
            agent=agent,
            input_text="test",
            expected_tools=["search", "calculate"]
        )
        
        result = evaluator.evaluate_tool_calls(["search"])  # missing calculate
        assert result.passed is False
        assert len(result.failed_calls) == 1
    
    def test_forbidden_tools(self):
        """Test forbidden tools detection."""
        agent = MagicMock()
        evaluator = ReliabilityEvaluator(
            agent=agent,
            input_text="test",
            expected_tools=[],
            forbidden_tools=["delete", "drop"]
        )
        
        result = evaluator.evaluate_tool_calls(["delete"])  # called forbidden tool
        assert result.passed is False
        assert len(result.failed_calls) == 1


class TestCriteriaEvaluator:
    """Tests for CriteriaEvaluator class."""
    
    def test_init(self):
        """Test initialization."""
        evaluator = CriteriaEvaluator(
            criteria="Response is helpful",
            func=lambda x: "test",
            input_text="test"
        )
        assert evaluator.criteria == "Response is helpful"
        assert evaluator.scoring_type == "numeric"
        assert evaluator.threshold == 7.0
    
    def test_init_binary_scoring(self):
        """Test initialization with binary scoring."""
        evaluator = CriteriaEvaluator(
            criteria="Response is helpful",
            func=lambda x: "test",
            scoring_type="binary"
        )
        assert evaluator.scoring_type == "binary"
    
    def test_judge_output_numeric(self):
        """Test numeric scoring."""
        with patch('litellm.completion') as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 8\nREASONING: Good"
            mock_completion.return_value = mock_response
            
            def test_func(x):
                return "test"
            
            evaluator = CriteriaEvaluator(
                criteria="Be helpful",
                func=test_func,
                scoring_type="numeric",
                threshold=7.0
            )
            
            score = evaluator._judge_output("test output")
            assert score.score == 8.0
            assert score.passed is True
    
    def test_judge_output_binary(self):
        """Test binary scoring."""
        with patch('litellm.completion') as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "RESULT: PASS\nREASONING: Meets criteria"
            mock_completion.return_value = mock_response
            
            def test_func(x):
                return "test"
            
            evaluator = CriteriaEvaluator(
                criteria="Be helpful",
                func=test_func,
                scoring_type="binary"
            )
            
            score = evaluator._judge_output("test output")
            assert score.score == 10.0
            assert score.passed is True
    
    def test_on_fail_callback(self):
        """Test on_fail callback is called."""
        with patch('litellm.completion') as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 3\nREASONING: Poor"
            mock_completion.return_value = mock_response
            
            on_fail_called = []
            def on_fail(score):
                on_fail_called.append(score)
            
            def test_func(x):
                return "test"
            
            evaluator = CriteriaEvaluator(
                criteria="Be helpful",
                func=test_func,
                threshold=7.0,
                on_fail=on_fail
            )
            
            evaluator.run()
            assert len(on_fail_called) == 1
            assert on_fail_called[0].score == 3.0
    
    def test_evaluate_output_criteria(self):
        """Test evaluate_output method."""
        with patch('litellm.completion') as mock_completion:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 9\nREASONING: Great"
            mock_completion.return_value = mock_response
            
            def test_func(x):
                return "unused"
            
            evaluator = CriteriaEvaluator(
                criteria="Be helpful",
                func=test_func
            )
            
            result = evaluator.evaluate_output("pre-generated output")
            assert isinstance(result, CriteriaResult)
            assert len(result.evaluations) == 1
