"""
Tests for ComparisonEval - side-by-side comparison evaluator.
"""

import pytest
from unittest.mock import Mock, patch
from praisonaiagents.eval.comparison import ComparisonEval, ComparisonResult, ComparisonGrader

class TestComparisonGrader:
    """Test the ComparisonGrader class."""
    
    def test_init_default_params(self):
        """Test ComparisonGrader initialization with defaults."""
        grader = ComparisonGrader()
        assert grader.temperature == 0.1
        assert grader.max_tokens == 1000
    
    def test_init_custom_params(self):
        """Test ComparisonGrader initialization with custom parameters."""
        grader = ComparisonGrader(model="gpt-4", temperature=0.2, max_tokens=500)
        assert grader.temperature == 0.2
        assert grader.max_tokens == 500
    
    @patch.object(ComparisonGrader, '_make_llm_call')
    def test_compare_outputs_success(self, mock_llm_call):
        """Test successful output comparison."""
        # Mock LLM response
        mock_llm_call.return_value = """
Criterion: accuracy
Output A Score: 8
Output B Score: 6
Reasoning: Output A is more accurate

Criterion: clarity  
Output A Score: 7
Output B Score: 9
Reasoning: Output B is clearer

Final Assessment:
Overall Winner: A
Confidence: 8
Summary: A wins on accuracy
"""
        
        grader = ComparisonGrader()
        result = grader.compare_outputs(
            input_text="Test input",
            output_a="Output A text",
            output_b="Output B text",
            agent_a_name="Agent A",
            agent_b_name="Agent B",
            criteria=["accuracy", "clarity"]
        )
        
        assert result["winner"] == "agent_a"
        assert result["confidence"] == 8.0
        assert "accuracy" in result["scores"]
        assert result["scores"]["accuracy"]["Agent A"] == 8.0
        assert result["scores"]["clarity"]["Agent B"] == 9.0
    
    @patch.object(ComparisonGrader, '_make_llm_call')
    def test_compare_outputs_error_handling(self, mock_llm_call):
        """Test error handling in comparison."""
        mock_llm_call.side_effect = Exception("LLM error")
        
        grader = ComparisonGrader()
        result = grader.compare_outputs(
            input_text="Test input",
            output_a="Output A text",
            output_b="Output B text", 
            agent_a_name="Agent A",
            agent_b_name="Agent B",
            criteria=["accuracy"]
        )
        
        assert result["winner"] == "tie"
        assert result["confidence"] == 1.0
        assert "accuracy" in result["scores"]

class TestComparisonEval:
    """Test the ComparisonEval class."""
    
    def test_init_with_agents(self):
        """Test initialization with agents."""
        agent_a = Mock()
        agent_a.name = "Agent A"
        agent_b = Mock()
        agent_b.name = "Agent B"
        
        evaluator = ComparisonEval(
            input_text="Test input",
            agent_a=agent_a,
            agent_b=agent_b
        )
        
        assert evaluator.input_text == "Test input"
        assert evaluator.agent_a == agent_a
        assert evaluator.agent_b == agent_b
    
    def test_init_with_outputs(self):
        """Test initialization with pre-generated outputs."""
        evaluator = ComparisonEval(
            input_text="Test input",
            output_a="Output A",
            output_b="Output B"
        )
        
        assert evaluator.output_a == "Output A"
        assert evaluator.output_b == "Output B"
    
    def test_init_validation_error(self):
        """Test validation error when neither agents nor outputs provided."""
        with pytest.raises(ValueError, match="Must provide either"):
            ComparisonEval(input_text="Test input")
    
    @patch.object(ComparisonGrader, 'compare_outputs')
    def test_run_with_outputs(self, mock_compare):
        """Test running evaluation with pre-generated outputs."""
        # Mock comparison result
        mock_compare.return_value = {
            "scores": {"accuracy": {"Agent_A": 8.0, "Agent_B": 6.0}},
            "reasoning": {"accuracy": "A is better"},
            "winner": "agent_a",
            "confidence": 8.0,
            "summary": "A wins"
        }
        
        evaluator = ComparisonEval(
            input_text="Test input",
            output_a="Output A",
            output_b="Output B",
            criteria=["accuracy"]
        )
        
        result = evaluator.run(print_summary=False)
        
        assert isinstance(result, ComparisonResult)
        assert result.winner == "agent_a"
        assert result.overall_score_a == 8.0
        assert result.overall_score_b == 6.0
        assert result.confidence == 8.0
    
    @patch.object(ComparisonGrader, 'compare_outputs')
    def test_run_with_agents(self, mock_compare):
        """Test running evaluation with agents."""
        # Mock agents
        agent_a = Mock()
        agent_a.name = "Test Agent A"
        agent_a.start.return_value = "Agent A response"
        
        agent_b = Mock()
        agent_b.name = "Test Agent B"
        agent_b.start.return_value = "Agent B response"
        
        # Mock comparison result
        mock_compare.return_value = {
            "scores": {"helpfulness": {"Test Agent A": 7.0, "Test Agent B": 8.0}},
            "reasoning": {"helpfulness": "B is more helpful"},
            "winner": "agent_b",
            "confidence": 7.0,
            "summary": "B wins"
        }
        
        evaluator = ComparisonEval(
            input_text="Help me",
            agent_a=agent_a,
            agent_b=agent_b,
            criteria=["helpfulness"]
        )
        
        result = evaluator.run(print_summary=False)
        
        # Verify agents were called
        agent_a.start.assert_called_once_with("Help me")
        agent_b.start.assert_called_once_with("Help me")
        
        assert result.winner == "agent_b"
        assert result.agent_a_name == "Test Agent A"
        assert result.agent_b_name == "Test Agent B"

class TestComparisonResult:
    """Test the ComparisonResult dataclass."""
    
    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ComparisonResult(
            input_text="Test input",
            output_a="Output A",
            output_b="Output B",
            agent_a_name="Agent A",
            agent_b_name="Agent B",
            criteria=["accuracy", "clarity"],
            scores={"accuracy": {"Agent A": 8.0, "Agent B": 6.0}},
            reasoning={"accuracy": "A is better"},
            winner="agent_a",
            overall_score_a=8.0,
            overall_score_b=6.0,
            confidence=8.0,
            duration=1.5
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["input_text"] == "Test input"
        assert result_dict["winner"] == "agent_a"
        assert result_dict["outputs"]["Agent A"] == "Output A"
        assert result_dict["overall_scores"]["Agent A"] == 8.0
        assert result_dict["duration"] == 1.5

@pytest.mark.integration
class TestComparisonEvalIntegration:
    """Integration tests for ComparisonEval."""
    
    def test_smoke_test(self):
        """Basic smoke test that evaluator can be instantiated."""
        evaluator = ComparisonEval(
            input_text="What is 2+2?",
            output_a="The answer is 4",
            output_b="2 plus 2 equals 4"
        )
        
        assert evaluator.input_text == "What is 2+2?"
        assert evaluator.criteria == ["accuracy", "clarity", "helpfulness"]  # defaults