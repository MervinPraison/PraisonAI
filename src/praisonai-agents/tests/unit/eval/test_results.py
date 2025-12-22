"""Unit tests for evaluation result dataclasses."""

import pytest
import json
from datetime import datetime

from praisonaiagents.eval.results import (
    EvaluationScore,
    AccuracyResult,
    PerformanceMetrics,
    PerformanceResult,
    ToolCallResult,
    ReliabilityResult,
    CriteriaScore,
    CriteriaResult,
)


class TestEvaluationScore:
    """Tests for EvaluationScore dataclass."""
    
    def test_creation(self):
        """Test basic creation of EvaluationScore."""
        score = EvaluationScore(
            score=8.5,
            reasoning="Good response",
            input_text="What is 2+2?",
            output_text="4",
            expected_output="4"
        )
        assert score.score == 8.5
        assert score.reasoning == "Good response"
        assert score.input_text == "What is 2+2?"
        assert score.output_text == "4"
        assert score.expected_output == "4"
    
    def test_timestamp_auto_generated(self):
        """Test that timestamp is auto-generated."""
        score = EvaluationScore(
            score=8.0,
            reasoning="Test",
            input_text="test",
            output_text="test"
        )
        assert score.timestamp is not None
        datetime.fromisoformat(score.timestamp)
    
    def test_metadata_default(self):
        """Test that metadata defaults to empty dict."""
        score = EvaluationScore(
            score=8.0,
            reasoning="Test",
            input_text="test",
            output_text="test"
        )
        assert score.metadata == {}


class TestAccuracyResult:
    """Tests for AccuracyResult dataclass."""
    
    def test_empty_result(self):
        """Test empty AccuracyResult."""
        result = AccuracyResult()
        assert result.evaluations == []
        assert result.avg_score == 0.0
        assert result.min_score == 0.0
        assert result.max_score == 0.0
        assert result.std_dev == 0.0
        assert result.passed is False
    
    def test_single_evaluation(self):
        """Test AccuracyResult with single evaluation."""
        result = AccuracyResult()
        result.evaluations.append(EvaluationScore(
            score=8.0,
            reasoning="Good",
            input_text="test",
            output_text="test"
        ))
        assert result.avg_score == 8.0
        assert result.min_score == 8.0
        assert result.max_score == 8.0
        assert result.std_dev == 0.0
        assert result.passed is True
    
    def test_multiple_evaluations(self):
        """Test AccuracyResult with multiple evaluations."""
        result = AccuracyResult()
        for score in [6.0, 8.0, 10.0]:
            result.evaluations.append(EvaluationScore(
                score=score,
                reasoning="Test",
                input_text="test",
                output_text="test"
            ))
        assert result.avg_score == 8.0
        assert result.min_score == 6.0
        assert result.max_score == 10.0
        assert result.passed is True
    
    def test_passed_threshold(self):
        """Test passed property with different scores."""
        result = AccuracyResult()
        result.evaluations.append(EvaluationScore(
            score=6.0,
            reasoning="Below threshold",
            input_text="test",
            output_text="test"
        ))
        assert result.passed is False
        
        result.evaluations.append(EvaluationScore(
            score=8.0,
            reasoning="Above threshold",
            input_text="test",
            output_text="test"
        ))
        assert result.passed is True
    
    def test_to_dict(self):
        """Test to_dict method."""
        result = AccuracyResult(eval_id="test123", name="test_eval")
        result.evaluations.append(EvaluationScore(
            score=8.0,
            reasoning="Good",
            input_text="test",
            output_text="test"
        ))
        d = result.to_dict()
        assert d["eval_id"] == "test123"
        assert d["name"] == "test_eval"
        assert d["avg_score"] == 8.0
        assert d["num_evaluations"] == 1
    
    def test_to_json(self):
        """Test to_json method."""
        result = AccuracyResult(eval_id="test123")
        result.evaluations.append(EvaluationScore(
            score=8.0,
            reasoning="Good",
            input_text="test",
            output_text="test"
        ))
        json_str = result.to_json()
        data = json.loads(json_str)
        assert data["eval_id"] == "test123"


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics dataclass."""
    
    def test_creation(self):
        """Test basic creation."""
        metrics = PerformanceMetrics(
            run_time=0.5,
            memory_usage=10.5,
            iteration=1
        )
        assert metrics.run_time == 0.5
        assert metrics.memory_usage == 10.5
        assert metrics.iteration == 1


class TestPerformanceResult:
    """Tests for PerformanceResult dataclass."""
    
    def test_empty_result(self):
        """Test empty PerformanceResult."""
        result = PerformanceResult()
        assert result.metrics == []
        assert result.avg_run_time == 0.0
        assert result.min_run_time == 0.0
        assert result.max_run_time == 0.0
        assert result.avg_memory == 0.0
    
    def test_with_metrics(self):
        """Test PerformanceResult with metrics."""
        result = PerformanceResult()
        for i, (time, mem) in enumerate([(0.1, 5.0), (0.2, 10.0), (0.3, 15.0)]):
            result.metrics.append(PerformanceMetrics(
                run_time=time,
                memory_usage=mem,
                iteration=i + 1
            ))
        assert result.avg_run_time == 0.2
        assert result.min_run_time == 0.1
        assert result.max_run_time == 0.3
        assert result.avg_memory == 10.0
        assert result.max_memory == 15.0
    
    def test_median_and_p95(self):
        """Test median and p95 calculations."""
        result = PerformanceResult()
        for i in range(100):
            result.metrics.append(PerformanceMetrics(
                run_time=float(i + 1) / 100,
                memory_usage=1.0,
                iteration=i + 1
            ))
        assert 0.49 <= result.median_run_time <= 0.51
        assert result.p95_run_time >= 0.95
    
    def test_to_dict(self):
        """Test to_dict method."""
        result = PerformanceResult(warmup_runs=5, eval_id="perf123")
        result.metrics.append(PerformanceMetrics(
            run_time=0.5,
            memory_usage=10.0,
            iteration=1
        ))
        d = result.to_dict()
        assert d["warmup_runs"] == 5
        assert d["eval_id"] == "perf123"
        assert d["num_iterations"] == 1


class TestToolCallResult:
    """Tests for ToolCallResult dataclass."""
    
    def test_creation(self):
        """Test basic creation."""
        tc = ToolCallResult(
            tool_name="search",
            expected=True,
            actual=True,
            passed=True
        )
        assert tc.tool_name == "search"
        assert tc.expected is True
        assert tc.actual is True
        assert tc.passed is True


class TestReliabilityResult:
    """Tests for ReliabilityResult dataclass."""
    
    def test_empty_result(self):
        """Test empty ReliabilityResult."""
        result = ReliabilityResult()
        assert result.tool_results == []
        assert result.pass_rate == 0.0
        assert result.status == "PASSED"
        assert result.passed is True
    
    def test_with_tool_calls(self):
        """Test ReliabilityResult with tool calls."""
        result = ReliabilityResult()
        result.tool_results.append(ToolCallResult(
            tool_name="search",
            expected=True,
            actual=True,
            passed=True
        ))
        result.tool_results.append(ToolCallResult(
            tool_name="calculate",
            expected=True,
            actual=False,
            passed=False
        ))
        assert len(result.passed_calls) == 1
        assert len(result.failed_calls) == 1
        assert result.pass_rate == 0.5
        assert result.status == "FAILED"
        assert result.passed is False
    
    def test_all_passed(self):
        """Test when all tool calls pass."""
        result = ReliabilityResult()
        for name in ["tool1", "tool2", "tool3"]:
            result.tool_results.append(ToolCallResult(
                tool_name=name,
                expected=True,
                actual=True,
                passed=True
            ))
        assert result.pass_rate == 1.0
        assert result.passed is True


class TestCriteriaScore:
    """Tests for CriteriaScore dataclass."""
    
    def test_creation(self):
        """Test basic creation."""
        score = CriteriaScore(
            score=8.0,
            passed=True,
            reasoning="Meets criteria",
            output_text="test output",
            criteria="Be helpful"
        )
        assert score.score == 8.0
        assert score.passed is True
        assert score.reasoning == "Meets criteria"


class TestCriteriaResult:
    """Tests for CriteriaResult dataclass."""
    
    def test_empty_result(self):
        """Test empty CriteriaResult."""
        result = CriteriaResult(criteria="Be helpful")
        assert result.evaluations == []
        assert result.avg_score == 0.0
        assert result.pass_rate == 0.0
    
    def test_numeric_scoring(self):
        """Test numeric scoring mode."""
        result = CriteriaResult(
            criteria="Be helpful",
            scoring_type="numeric",
            threshold=7.0
        )
        result.evaluations.append(CriteriaScore(
            score=8.0,
            passed=True,
            reasoning="Good",
            output_text="test",
            criteria="Be helpful"
        ))
        assert result.avg_score == 8.0
        assert result.passed is True
    
    def test_binary_scoring(self):
        """Test binary scoring mode."""
        result = CriteriaResult(
            criteria="Be helpful",
            scoring_type="binary"
        )
        result.evaluations.append(CriteriaScore(
            score=10.0,
            passed=True,
            reasoning="Pass",
            output_text="test",
            criteria="Be helpful"
        ))
        result.evaluations.append(CriteriaScore(
            score=0.0,
            passed=False,
            reasoning="Fail",
            output_text="test",
            criteria="Be helpful"
        ))
        assert result.pass_rate == 0.5
        assert result.passed is True
    
    def test_to_dict(self):
        """Test to_dict method."""
        result = CriteriaResult(
            criteria="Be helpful",
            scoring_type="numeric",
            threshold=7.0,
            eval_id="crit123"
        )
        d = result.to_dict()
        assert d["criteria"] == "Be helpful"
        assert d["scoring_type"] == "numeric"
        assert d["threshold"] == 7.0
