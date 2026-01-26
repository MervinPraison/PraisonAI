"""
Unit tests for the unified Judge class.

TDD: These tests are written FIRST before implementation.
"""
from unittest.mock import patch, MagicMock
from dataclasses import is_dataclass


class TestJudgeProtocol:
    """Test JudgeProtocol interface."""
    
    def test_judge_protocol_exists(self):
        """JudgeProtocol should be importable from protocols."""
        from praisonaiagents.eval.protocols import JudgeProtocol
        assert JudgeProtocol is not None
    
    def test_judge_protocol_has_run_method(self):
        """JudgeProtocol should define run method."""
        from praisonaiagents.eval.protocols import JudgeProtocol
        assert hasattr(JudgeProtocol, 'run')
    
    def test_judge_protocol_has_run_async_method(self):
        """JudgeProtocol should define run_async method."""
        from praisonaiagents.eval.protocols import JudgeProtocol
        assert hasattr(JudgeProtocol, 'run_async')


class TestJudgeResult:
    """Test JudgeResult dataclass."""
    
    def test_judge_result_exists(self):
        """JudgeResult should be importable from results."""
        from praisonaiagents.eval.results import JudgeResult
        assert JudgeResult is not None
    
    def test_judge_result_is_dataclass(self):
        """JudgeResult should be a dataclass."""
        from praisonaiagents.eval.results import JudgeResult
        assert is_dataclass(JudgeResult)
    
    def test_judge_result_has_required_fields(self):
        """JudgeResult should have score, passed, reasoning fields."""
        from praisonaiagents.eval.results import JudgeResult
        result = JudgeResult(score=8.0, passed=True, reasoning="Good output")
        assert result.score == 8.0
        assert result.passed is True
        assert result.reasoning == "Good output"
    
    def test_judge_result_to_dict(self):
        """JudgeResult should have to_dict method."""
        from praisonaiagents.eval.results import JudgeResult
        result = JudgeResult(score=8.0, passed=True, reasoning="Good")
        d = result.to_dict()
        assert d["score"] == 8.0
        assert d["passed"] is True
        assert d["reasoning"] == "Good"


class TestJudgeClass:
    """Test the unified Judge class."""
    
    def test_judge_importable(self):
        """Judge should be importable from eval module."""
        from praisonaiagents.eval import Judge
        assert Judge is not None
    
    def test_judge_default_initialization(self):
        """Judge should initialize with sensible defaults."""
        from praisonaiagents.eval import Judge
        judge = Judge()
        assert judge.model is not None
        assert judge.temperature == 0.1
    
    def test_judge_with_criteria(self):
        """Judge should accept criteria parameter."""
        from praisonaiagents.eval import Judge
        judge = Judge(criteria="Response is helpful")
        assert judge.criteria == "Response is helpful"
    
    def test_judge_with_model(self):
        """Judge should accept model parameter."""
        from praisonaiagents.eval import Judge
        judge = Judge(model="gpt-4o")
        assert judge.model == "gpt-4o"
    
    @patch('praisonaiagents.eval.judge.Judge._get_litellm')
    def test_judge_run_with_output_and_expected(self, mock_litellm):
        """Judge.run() should work with output and expected."""
        from praisonaiagents.eval import Judge
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "SCORE: 9\nREASONING: Excellent match"
        mock_litellm.return_value.completion.return_value = mock_response
        
        judge = Judge()
        result = judge.run(output="4", expected="4")
        
        assert result.score == 9.0
        assert result.passed is True
        assert "Excellent" in result.reasoning
    
    @patch('praisonaiagents.eval.judge.Judge._get_litellm')
    def test_judge_run_with_criteria(self, mock_litellm):
        """Judge.run() should work with custom criteria."""
        from praisonaiagents.eval import Judge
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "SCORE: 8\nREASONING: Meets criteria"
        mock_litellm.return_value.completion.return_value = mock_response
        
        judge = Judge(criteria="Response is helpful")
        result = judge.run(output="Hello, how can I help?")
        
        assert result.score == 8.0
        assert result.passed is True


class TestJudgeRegistry:
    """Test judge registry functions."""
    
    def test_add_judge_function_exists(self):
        """add_judge should be importable."""
        from praisonaiagents.eval import add_judge
        assert callable(add_judge)
    
    def test_get_judge_function_exists(self):
        """get_judge should be importable."""
        from praisonaiagents.eval import get_judge
        assert callable(get_judge)
    
    def test_list_judges_function_exists(self):
        """list_judges should be importable."""
        from praisonaiagents.eval import list_judges
        assert callable(list_judges)
    
    def test_add_and_get_custom_judge(self):
        """Should be able to add and retrieve custom judge."""
        from praisonaiagents.eval import add_judge, get_judge, Judge
        
        class CustomJudge(Judge):
            criteria = "Custom criteria"
        
        add_judge("custom", CustomJudge)
        retrieved = get_judge("custom")
        assert retrieved is CustomJudge
    
    def test_list_judges_includes_builtin(self):
        """list_judges should include built-in judges."""
        from praisonaiagents.eval import list_judges
        judges = list_judges()
        assert "accuracy" in judges
        assert "criteria" in judges
    
    def test_get_nonexistent_judge_returns_none(self):
        """get_judge should return None for unknown judge."""
        from praisonaiagents.eval import get_judge
        result = get_judge("nonexistent_judge_xyz")
        assert result is None


class TestJudgeConfig:
    """Test JudgeConfig dataclass."""
    
    def test_judge_config_exists(self):
        """JudgeConfig should be importable."""
        from praisonaiagents.eval import JudgeConfig
        assert JudgeConfig is not None
    
    def test_judge_config_is_dataclass(self):
        """JudgeConfig should be a dataclass."""
        from praisonaiagents.eval import JudgeConfig
        assert is_dataclass(JudgeConfig)
    
    def test_judge_config_has_model_field(self):
        """JudgeConfig should have model field."""
        from praisonaiagents.eval import JudgeConfig
        config = JudgeConfig(model="gpt-4o")
        assert config.model == "gpt-4o"
    
    def test_judge_config_defaults(self):
        """JudgeConfig should have sensible defaults."""
        from praisonaiagents.eval import JudgeConfig
        config = JudgeConfig()
        assert config.temperature == 0.1
        assert config.threshold == 7.0


class TestBackwardCompatibility:
    """Test that existing evaluators still work."""
    
    def test_accuracy_evaluator_still_works(self):
        """AccuracyEvaluator should still be importable and work."""
        from praisonaiagents.eval import AccuracyEvaluator
        assert AccuracyEvaluator is not None
    
    def test_criteria_evaluator_still_works(self):
        """CriteriaEvaluator should still be importable and work."""
        from praisonaiagents.eval import CriteriaEvaluator
        assert CriteriaEvaluator is not None
    
    def test_base_llm_grader_still_works(self):
        """BaseLLMGrader should still be importable."""
        from praisonaiagents.eval import BaseLLMGrader
        assert BaseLLMGrader is not None


class TestLazyLoading:
    """Test that lazy loading is preserved."""
    
    def test_import_does_not_load_litellm(self):
        """Importing eval should not load litellm."""
        import sys
        # Clear any cached imports
        modules_before = set(sys.modules.keys())
        
        # Import eval module - use the module directly
        import praisonaiagents.eval  # noqa: F401
        
        # litellm should not be loaded
        assert 'litellm' not in sys.modules or 'litellm' in modules_before
