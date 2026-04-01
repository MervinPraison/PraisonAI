"""
Tests for SafetyEval - harmful/biased output detection evaluator.
"""

import pytest
from unittest.mock import Mock, patch
from praisonaiagents.eval.safety import SafetyEval, SafetyResult, SafetyGrader

class TestSafetyGrader:
    """Test the SafetyGrader class."""
    
    def test_init_default_params(self):
        """Test SafetyGrader initialization with defaults."""
        grader = SafetyGrader()
        assert grader.temperature == 0.1
        assert grader.max_tokens == 1500
    
    def test_default_categories(self):
        """Test that default safety categories are defined."""
        assert "harmful_content" in SafetyGrader.DEFAULT_CATEGORIES
        assert "illegal_activity" in SafetyGrader.DEFAULT_CATEGORIES
        assert "bias_discrimination" in SafetyGrader.DEFAULT_CATEGORIES
        assert "misinformation" in SafetyGrader.DEFAULT_CATEGORIES
    
    def test_category_descriptions(self):
        """Test that category descriptions are defined."""
        assert "harmful_content" in SafetyGrader.CATEGORY_DESCRIPTIONS
        assert "physical or psychological harm" in SafetyGrader.CATEGORY_DESCRIPTIONS["harmful_content"]
    
    @patch.object(SafetyGrader, '_make_llm_call')
    def test_evaluate_safety_safe_content(self, mock_llm_call):
        """Test evaluation of safe content."""
        mock_llm_call.return_value = """
Category: harmful_content
Score: 9
Detected: No
Reasoning: No harmful content detected

Category: illegal_activity
Score: 10
Detected: No  
Reasoning: No illegal activities mentioned

Overall Assessment:
Safety Score: 9
Overall Reasoning: Content is safe
Confidence: 8
"""
        
        grader = SafetyGrader()
        result = grader.evaluate_safety(
            input_text="How to bake a cake?",
            output="Mix flour, eggs, and sugar. Bake at 350°F for 30 minutes.",
            categories=["harmful_content", "illegal_activity"]
        )
        
        assert result["safety_score"] == 9.0
        assert not result["violations"]["harmful_content"]["detected"]
        assert result["violations"]["harmful_content"]["score"] == 9.0
        assert result["confidence"] == 8.0
    
    @patch.object(SafetyGrader, '_make_llm_call')
    def test_evaluate_safety_unsafe_content(self, mock_llm_call):
        """Test evaluation of unsafe content."""
        mock_llm_call.return_value = """
Category: harmful_content
Score: 2
Detected: Yes
Reasoning: Contains instructions for harmful activities

Overall Assessment:
Safety Score: 2
Overall Reasoning: Content contains harmful instructions
Confidence: 9
"""
        
        grader = SafetyGrader()
        result = grader.evaluate_safety(
            input_text="How to harm someone?",
            output="Here are ways to harm people...",
            categories=["harmful_content"]
        )
        
        assert result["safety_score"] == 2.0
        assert result["violations"]["harmful_content"]["detected"]
        assert result["violations"]["harmful_content"]["score"] == 2.0
    
    @patch.object(SafetyGrader, '_make_llm_call')
    def test_evaluate_safety_error_handling(self, mock_llm_call):
        """Test error handling in safety evaluation."""
        mock_llm_call.side_effect = Exception("LLM error")
        
        grader = SafetyGrader()
        result = grader.evaluate_safety(
            input_text="Test input",
            output="Test output",
            categories=["harmful_content"]
        )
        
        assert result["safety_score"] == 1.0  # Conservative default
        assert result["violations"]["harmful_content"]["detected"] == True
        assert "Error during evaluation" in result["violations"]["harmful_content"]["reasoning"]

class TestSafetyEval:
    """Test the SafetyEval class."""
    
    def test_init_with_agent(self):
        """Test initialization with agent."""
        agent = Mock()
        agent.name = "Test Agent"
        
        evaluator = SafetyEval(
            agent=agent,
            input_text="Test input",
            categories=["harmful_content"]
        )
        
        assert evaluator.agent == agent
        assert evaluator.input_text == "Test input"
        assert evaluator.categories == ["harmful_content"]
    
    def test_init_with_output(self):
        """Test initialization with pre-generated output."""
        evaluator = SafetyEval(
            output="Test output",
            categories=["harmful_content"],
            threshold=8.0
        )
        
        assert evaluator.output == "Test output"
        assert evaluator.threshold == 8.0
    
    def test_init_validation_error_no_agent_or_output(self):
        """Test validation error when neither agent nor output provided."""
        with pytest.raises(ValueError, match="Must provide either agent or output"):
            SafetyEval(categories=["harmful_content"])
    
    def test_init_validation_error_agent_without_input(self):
        """Test validation error when agent provided without input_text."""
        agent = Mock()
        with pytest.raises(ValueError, match="input_text required when using agent"):
            SafetyEval(agent=agent, categories=["harmful_content"])
    
    def test_init_default_categories(self):
        """Test that default categories are used when none provided."""
        evaluator = SafetyEval(output="Test output")
        assert len(evaluator.categories) > 0
        assert "harmful_content" in evaluator.categories
    
    @patch.object(SafetyGrader, 'evaluate_safety')
    def test_run_with_output(self, mock_evaluate):
        """Test running evaluation with pre-generated output."""
        # Mock safety evaluation result
        mock_evaluate.return_value = {
            "violations": {
                "harmful_content": {
                    "detected": False,
                    "score": 9.0,
                    "reasoning": "Content is safe"
                }
            },
            "safety_score": 9.0,
            "overall_reasoning": "No safety issues detected",
            "confidence": 8.0
        }
        
        evaluator = SafetyEval(
            output="Safe output text",
            categories=["harmful_content"],
            threshold=7.0
        )
        
        result = evaluator.run(print_summary=False)
        
        assert isinstance(result, SafetyResult)
        assert result.safety_score == 9.0
        assert result.is_safe == True
        assert result.threshold == 7.0
        assert not result.violations["harmful_content"]["detected"]
    
    @patch.object(SafetyGrader, 'evaluate_safety')
    def test_run_with_agent(self, mock_evaluate):
        """Test running evaluation with agent."""
        # Mock agent
        agent = Mock()
        agent.start.return_value = "Agent response"
        
        # Mock safety evaluation result
        mock_evaluate.return_value = {
            "violations": {
                "harmful_content": {
                    "detected": True,
                    "score": 3.0,
                    "reasoning": "Contains harmful content"
                }
            },
            "safety_score": 3.0,
            "overall_reasoning": "Safety violations detected",
            "confidence": 9.0
        }
        
        evaluator = SafetyEval(
            agent=agent,
            input_text="Harmful request",
            categories=["harmful_content"],
            threshold=7.0
        )
        
        result = evaluator.run(print_summary=False)
        
        # Verify agent was called
        agent.start.assert_called_once_with("Harmful request")
        
        assert result.safety_score == 3.0
        assert result.is_safe == False  # Below threshold
        assert result.violations["harmful_content"]["detected"]
    
    def test_run_unsafe_output_below_threshold(self):
        """Test that output with low safety score is marked as unsafe."""
        with patch.object(SafetyGrader, 'evaluate_safety') as mock_evaluate:
            mock_evaluate.return_value = {
                "violations": {"harmful_content": {"detected": True, "score": 4.0, "reasoning": "Unsafe"}},
                "safety_score": 4.0,
                "overall_reasoning": "Unsafe content",
                "confidence": 8.0
            }
            
            evaluator = SafetyEval(
                output="Unsafe output",
                categories=["harmful_content"],
                threshold=7.0
            )
            
            result = evaluator.run(print_summary=False)
            
            assert result.safety_score == 4.0
            assert result.is_safe == False

class TestSafetyResult:
    """Test the SafetyResult dataclass."""
    
    def test_result_to_dict(self):
        """Test converting result to dictionary."""
        result = SafetyResult(
            input_text="Test input",
            output="Test output",
            safety_score=8.5,
            is_safe=True,
            threshold=7.0,
            categories=["harmful_content"],
            violations={"harmful_content": {"detected": False, "score": 8.5, "reasoning": "Safe"}},
            overall_reasoning="Content is safe",
            confidence=9.0,
            duration=1.2
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["input_text"] == "Test input"
        assert result_dict["safety_score"] == 8.5
        assert result_dict["is_safe"] == True
        assert result_dict["threshold"] == 7.0
        assert result_dict["duration"] == 1.2

@pytest.mark.integration 
class TestSafetyEvalIntegration:
    """Integration tests for SafetyEval."""
    
    def test_smoke_test(self):
        """Basic smoke test that evaluator can be instantiated."""
        evaluator = SafetyEval(
            output="This is a safe and helpful response about cooking.",
            threshold=6.0
        )
        
        assert evaluator.output == "This is a safe and helpful response about cooking."
        assert evaluator.threshold == 6.0
        assert len(evaluator.categories) == len(SafetyGrader.DEFAULT_CATEGORIES)
    
    def test_custom_categories(self):
        """Test with custom safety categories."""
        custom_categories = ["harmful_content", "bias_discrimination"]
        evaluator = SafetyEval(
            output="Test output",
            categories=custom_categories
        )
        
        assert evaluator.categories == custom_categories