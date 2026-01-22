"""
TDD Tests for Agent Training Grader.

Tests for TrainingGrader class that grades agent outputs using LLM-as-judge.
DRY: Reuses AccuracyEvaluator pattern from praisonaiagents.eval.
"""

from unittest.mock import Mock, patch
import sys


class TestTrainingGrader:
    """Tests for TrainingGrader class."""
    
    def test_create_grader_default(self):
        """Test creating grader with defaults."""
        from praisonai.train.agents.grader import TrainingGrader
        
        grader = TrainingGrader()
        
        assert grader.model == "gpt-4o-mini"
    
    def test_create_grader_custom_model(self):
        """Test creating grader with custom model."""
        from praisonai.train.agents.grader import TrainingGrader
        
        grader = TrainingGrader(model="gpt-4o")
        
        assert grader.model == "gpt-4o"
    
    def test_grade_output_returns_score(self):
        """Test grading returns a score between 1-10."""
        from praisonai.train.agents.grader import TrainingGrader
        
        # Mock litellm module
        mock_litellm = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "SCORE: 8\nREASONING: Good response"
        mock_litellm.completion.return_value = mock_response
        
        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            grader = TrainingGrader()
            result = grader.grade(
                input_text="What is Python?",
                output="Python is a programming language",
                expected_output="Python is a high-level programming language"
            )
        
        assert result.score == 8.0
        assert "Good response" in result.reasoning
    
    def test_grade_output_clamps_score(self):
        """Test that scores are clamped to 1-10 range."""
        from praisonai.train.agents.grader import TrainingGrader
        
        # Mock LLM returning out-of-range score
        mock_litellm = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "SCORE: 15\nREASONING: Amazing"
        mock_litellm.completion.return_value = mock_response
        
        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            grader = TrainingGrader()
            result = grader.grade(
                input_text="Test",
                output="Output"
            )
        
        assert result.score == 10.0  # Clamped to max
    
    def test_grade_without_expected_output(self):
        """Test grading without expected output (quality assessment only)."""
        from praisonai.train.agents.grader import TrainingGrader
        
        mock_litellm = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "SCORE: 7\nREASONING: Decent quality"
        mock_litellm.completion.return_value = mock_response
        
        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            grader = TrainingGrader()
            result = grader.grade(
                input_text="Explain AI",
                output="AI is artificial intelligence that mimics human thinking"
            )
        
        assert result.score == 7.0
    
    def test_grade_returns_suggestions(self):
        """Test that grading returns improvement suggestions."""
        from praisonai.train.agents.grader import TrainingGrader
        
        mock_litellm = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = """SCORE: 6
REASONING: Could be better
SUGGESTIONS:
- Add more detail
- Include examples
- Be more concise"""
        mock_litellm.completion.return_value = mock_response
        
        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            grader = TrainingGrader()
            result = grader.grade(
                input_text="Test",
                output="Output"
            )
        
        assert len(result.suggestions) >= 1
    
    def test_grade_handles_malformed_response(self):
        """Test graceful handling of malformed LLM response."""
        from praisonai.train.agents.grader import TrainingGrader
        
        mock_litellm = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "This is not formatted correctly"
        mock_litellm.completion.return_value = mock_response
        
        with patch.dict(sys.modules, {'litellm': mock_litellm}):
            grader = TrainingGrader()
            result = grader.grade(
                input_text="Test",
                output="Output"
            )
        
        # Should return default score, not crash
        assert 1.0 <= result.score <= 10.0
    
    def test_grade_result_dataclass(self):
        """Test GradeResult dataclass structure."""
        from praisonai.train.agents.grader import GradeResult
        
        result = GradeResult(
            score=8.5,
            reasoning="Good work",
            suggestions=["Add examples"],
            input_text="Input",
            output="Output"
        )
        
        assert result.score == 8.5
        assert result.reasoning == "Good work"
        assert result.suggestions == ["Add examples"]
    
    def test_grade_result_to_dict(self):
        """Test converting GradeResult to dictionary."""
        from praisonai.train.agents.grader import GradeResult
        
        result = GradeResult(
            score=7.0,
            reasoning="OK",
            suggestions=[],
            input_text="In",
            output="Out"
        )
        
        d = result.to_dict()
        assert d["score"] == 7.0
        assert "reasoning" in d
        assert "suggestions" in d


class TestTrainingGraderPrompts:
    """Tests for grader prompt generation."""
    
    def test_prompt_includes_input(self):
        """Test that grading prompt includes input text."""
        from praisonai.train.agents.grader import TrainingGrader
        
        grader = TrainingGrader()
        prompt = grader._build_prompt(
            input_text="What is machine learning?",
            output="ML is a subset of AI"
        )
        
        assert "What is machine learning?" in prompt
    
    def test_prompt_includes_output(self):
        """Test that grading prompt includes agent output."""
        from praisonai.train.agents.grader import TrainingGrader
        
        grader = TrainingGrader()
        prompt = grader._build_prompt(
            input_text="Test",
            output="This is the agent's response"
        )
        
        assert "This is the agent's response" in prompt
    
    def test_prompt_includes_expected_when_provided(self):
        """Test that prompt includes expected output when provided."""
        from praisonai.train.agents.grader import TrainingGrader
        
        grader = TrainingGrader()
        prompt = grader._build_prompt(
            input_text="Test",
            output="Output",
            expected_output="Expected response here"
        )
        
        assert "Expected response here" in prompt
    
    def test_prompt_requests_score_format(self):
        """Test that prompt requests specific score format."""
        from praisonai.train.agents.grader import TrainingGrader
        
        grader = TrainingGrader()
        prompt = grader._build_prompt(
            input_text="Test",
            output="Output"
        )
        
        assert "SCORE:" in prompt
        assert "REASONING:" in prompt
