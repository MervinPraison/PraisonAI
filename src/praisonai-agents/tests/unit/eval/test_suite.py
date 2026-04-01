"""
Tests for EvalSuite - orchestrator for running multiple evaluations.
"""

import pytest
from unittest.mock import Mock, patch
from praisonaiagents.eval.suite import EvalSuite, EvalSuiteResult

class TestEvalSuiteResult:
    """Test the EvalSuiteResult dataclass."""
    
    def test_duration_property(self):
        """Test duration calculation."""
        result = EvalSuiteResult(
            suite_name="test_suite",
            start_time=100.0,
            end_time=103.5
        )
        
        assert result.duration == 3.5
    
    def test_summary_property(self):
        """Test summary property."""
        result = EvalSuiteResult(
            suite_name="test_suite",
            start_time=100.0,
            end_time=103.5,
            overall_score=8.5,
            success=True,
            evaluator_results={"eval1": Mock(), "eval2": Mock()},
            errors=["error1"]
        )
        
        summary = result.summary
        
        assert summary["suite_name"] == "test_suite"
        assert summary["duration"] == 3.5
        assert summary["overall_score"] == 8.5
        assert summary["success"] == True
        assert summary["num_evaluators"] == 2
        assert summary["errors"] == 1
    
    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = EvalSuiteResult(
            suite_name="test_suite",
            start_time=100.0,
            end_time=103.5,
            evaluator_results={"eval1": {"score": 8.0}},
            overall_score=8.0,
            success=True,
            errors=[]
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["suite_name"] == "test_suite"
        assert result_dict["duration"] == 3.5
        assert result_dict["overall_score"] == 8.0
        assert "summary" in result_dict

class TestEvalSuite:
    """Test the EvalSuite class."""
    
    def test_init_basic(self):
        """Test basic initialization."""
        evaluator1 = Mock()
        evaluator2 = Mock()
        
        suite = EvalSuite(
            evaluators=[evaluator1, evaluator2],
            name="test_suite"
        )
        
        assert suite.evaluators == [evaluator1, evaluator2]
        assert suite.name == "test_suite"
        assert suite.parallel == False
        assert suite.fail_fast == False
    
    def test_init_with_options(self):
        """Test initialization with all options."""
        evaluator = Mock()
        
        suite = EvalSuite(
            evaluators=[evaluator],
            name="advanced_suite",
            parallel=True,
            fail_fast=True,
            score_weights={"AccuracyEvaluator_0": 2.0},
            save_results_path="/tmp/results.json"
        )
        
        assert suite.parallel == True
        assert suite.fail_fast == True
        assert suite.score_weights == {"AccuracyEvaluator_0": 2.0}
        assert suite.save_results_path == "/tmp/results.json"
    
    def test_init_validation_empty_evaluators(self):
        """Test validation error with empty evaluators list."""
        with pytest.raises(ValueError, match="At least one evaluator must be provided"):
            EvalSuite(evaluators=[])
    
    def test_init_auto_name_generation(self):
        """Test automatic name generation when not provided."""
        evaluator = Mock()
        
        suite = EvalSuite(evaluators=[evaluator])
        
        assert suite.name.startswith("eval_suite_")
        assert len(suite.name) > len("eval_suite_")
    
    @patch('time.time')
    def test_run_sequential_success(self, mock_time):
        """Test successful sequential execution."""
        # Mock time progression
        mock_time.side_effect = [100.0, 105.0]  # start, end
        
        # Create mock evaluators
        evaluator1 = Mock()
        evaluator1.__class__.__name__ = "AccuracyEvaluator"
        evaluator1.run.return_value = Mock(score=8.0)
        
        evaluator2 = Mock()
        evaluator2.__class__.__name__ = "PerformanceEvaluator"
        evaluator2.run.return_value = Mock(score=7.5)
        
        suite = EvalSuite(
            evaluators=[evaluator1, evaluator2],
            name="test_suite"
        )
        
        result = suite.run(print_summary=False)
        
        # Verify evaluators were called
        evaluator1.run.assert_called_once_with(print_summary=False)
        evaluator2.run.assert_called_once_with(print_summary=False)
        
        assert result.success == True
        assert len(result.evaluator_results) == 2
        assert "AccuracyEvaluator_0" in result.evaluator_results
        assert "PerformanceEvaluator_1" in result.evaluator_results
    
    def test_run_with_evaluator_failure(self):
        """Test handling of evaluator failure."""
        # Create mock evaluators - one succeeds, one fails
        evaluator1 = Mock()
        evaluator1.__class__.__name__ = "AccuracyEvaluator"
        evaluator1.run.return_value = Mock(score=8.0)
        
        evaluator2 = Mock()
        evaluator2.__class__.__name__ = "PerformanceEvaluator"
        evaluator2.run.side_effect = Exception("Evaluator failed")
        
        suite = EvalSuite(
            evaluators=[evaluator1, evaluator2],
            name="test_suite",
            fail_fast=False
        )
        
        result = suite.run(print_summary=False)
        
        assert result.success == False
        assert len(result.errors) == 1
        assert "PerformanceEvaluator_1 failed" in result.errors[0]
        assert "AccuracyEvaluator_0" in result.evaluator_results  # First evaluator succeeded
    
    def test_run_fail_fast(self):
        """Test fail_fast behavior."""
        # Create mock evaluators
        evaluator1 = Mock()
        evaluator1.__class__.__name__ = "AccuracyEvaluator"
        evaluator1.run.side_effect = Exception("First evaluator failed")
        
        evaluator2 = Mock()
        evaluator2.__class__.__name__ = "PerformanceEvaluator"
        
        suite = EvalSuite(
            evaluators=[evaluator1, evaluator2],
            name="test_suite",
            fail_fast=True
        )
        
        with pytest.raises(RuntimeError, match="EvalSuite stopped due to fail_fast"):
            suite.run(print_summary=False)
        
        # Second evaluator should not have been called
        evaluator2.run.assert_not_called()
    
    def test_extract_score_from_result_object(self):
        """Test score extraction from result object with score attribute."""
        suite = EvalSuite(evaluators=[Mock()])
        
        # Test with object having score attribute
        result_obj = Mock()
        result_obj.score = Mock()
        result_obj.score.value = 8.5
        
        score = suite._extract_score(result_obj)
        assert score == 8.5
    
    def test_extract_score_direct_score(self):
        """Test score extraction from object with direct score."""
        suite = EvalSuite(evaluators=[Mock()])
        
        result_obj = Mock()
        result_obj.score = 7.8
        
        score = suite._extract_score(result_obj)
        assert score == 7.8
    
    def test_extract_score_overall_score(self):
        """Test score extraction from object with overall_score."""
        suite = EvalSuite(evaluators=[Mock()])
        
        result_obj = Mock()
        result_obj.overall_score = 9.2
        
        score = suite._extract_score(result_obj)
        assert score == 9.2
    
    def test_extract_score_from_dict(self):
        """Test score extraction from dictionary result."""
        suite = EvalSuite(evaluators=[Mock()])
        
        result_dict = {"score": 8.0, "other_data": "value"}
        
        score = suite._extract_score(result_dict)
        assert score == 8.0
    
    def test_extract_score_none_found(self):
        """Test score extraction when no score found."""
        suite = EvalSuite(evaluators=[Mock()])
        
        result_obj = Mock(spec=[])  # Object with no score attributes
        
        score = suite._extract_score(result_obj)
        assert score is None
    
    def test_calculate_overall_score_simple(self):
        """Test overall score calculation without weights."""
        suite = EvalSuite(evaluators=[Mock()])
        
        result = EvalSuiteResult(
            suite_name="test",
            start_time=100.0,
            end_time=100.0
        )
        result.evaluator_results = {
            "eval1": Mock(score=8.0),
            "eval2": Mock(score=6.0)
        }
        
        overall_score = suite._calculate_overall_score(result)
        assert overall_score == 7.0  # (8.0 + 6.0) / 2
    
    def test_calculate_overall_score_with_weights(self):
        """Test overall score calculation with weights."""
        suite = EvalSuite(
            evaluators=[Mock()],
            score_weights={
                "eval1": 2.0,
                "eval2": 1.0
            }
        )
        
        result = EvalSuiteResult(
            suite_name="test",
            start_time=100.0,
            end_time=100.0
        )
        result.evaluator_results = {
            "eval1": Mock(score=8.0),
            "eval2": Mock(score=6.0)
        }
        
        overall_score = suite._calculate_overall_score(result)
        # (8.0 * 2.0 + 6.0 * 1.0) / (2.0 + 1.0) = 22.0 / 3.0 ≈ 7.33
        assert abs(overall_score - 7.333333333333333) < 0.001
    
    def test_calculate_overall_score_no_results(self):
        """Test overall score calculation with no results."""
        suite = EvalSuite(evaluators=[Mock()])
        
        result = EvalSuiteResult(
            suite_name="test",
            start_time=100.0,
            end_time=100.0
        )
        result.evaluator_results = {}
        
        overall_score = suite._calculate_overall_score(result)
        assert overall_score == 0.0
    
    def test_parallel_execution_fallback(self):
        """Test that parallel execution falls back to sequential."""
        evaluator = Mock()
        evaluator.__class__.__name__ = "TestEvaluator"
        evaluator.run.return_value = Mock(score=8.0)
        
        suite = EvalSuite(
            evaluators=[evaluator],
            parallel=True  # Request parallel, but should fallback
        )
        
        result = suite.run(print_summary=False)
        
        # Should still work (fallback to sequential)
        assert result.success == True
        evaluator.run.assert_called_once()
    
    @patch('builtins.print')
    def test_print_summary(self, mock_print):
        """Test summary printing."""
        evaluator = Mock()
        evaluator.__class__.__name__ = "TestEvaluator"
        evaluator.run.return_value = Mock(score=8.0)
        
        suite = EvalSuite(evaluators=[evaluator])
        result = suite.run(print_summary=True)  # Should print
        
        # Verify print was called (summary was printed)
        assert mock_print.called
    
    @patch('pathlib.Path.mkdir')
    @patch('builtins.open', create=True)
    @patch('json.dump')
    def test_save_results(self, mock_json_dump, mock_open, mock_mkdir):
        """Test saving results to file."""
        evaluator = Mock()
        evaluator.__class__.__name__ = "TestEvaluator"
        evaluator.run.return_value = Mock(score=8.0)
        
        suite = EvalSuite(
            evaluators=[evaluator],
            save_results_path="/tmp/results_{name}.json"
        )
        
        result = suite.run(print_summary=False)
        
        # Verify file operations were attempted
        mock_mkdir.assert_called()
        mock_open.assert_called()
        mock_json_dump.assert_called()

@pytest.mark.integration
class TestEvalSuiteIntegration:
    """Integration tests for EvalSuite."""
    
    def test_smoke_test(self):
        """Basic smoke test that suite can be instantiated."""
        evaluator = Mock()
        
        suite = EvalSuite(
            evaluators=[evaluator],
            name="smoke_test"
        )
        
        assert suite.name == "smoke_test"
        assert len(suite.evaluators) == 1