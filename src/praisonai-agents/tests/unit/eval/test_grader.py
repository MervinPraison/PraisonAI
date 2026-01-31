"""
Tests for BaseLLMGrader and GradeResult.

TDD: Tests for the DRY base grader implementation.
"""

import pytest
import importlib
from unittest.mock import patch, MagicMock

from praisonaiagents.eval.grader import BaseLLMGrader, GradeResult


class TestGradeResult:
    """Tests for GradeResult dataclass."""
    
    def test_grade_result_creation(self):
        """Test creating a GradeResult."""
        result = GradeResult(
            score=8.5,
            reasoning="Good response",
            suggestions=["Add more detail"],
            input_text="What is Python?",
            output="Python is a programming language",
            expected_output="Python is a high-level programming language",
        )
        
        assert result.score == 8.5
        assert result.reasoning == "Good response"
        assert result.suggestions == ["Add more detail"]
        assert result.input_text == "What is Python?"
        assert result.output == "Python is a programming language"
        assert result.expected_output == "Python is a high-level programming language"
    
    def test_grade_result_defaults(self):
        """Test GradeResult default values."""
        result = GradeResult(score=7.0, reasoning="OK")
        
        assert result.suggestions == []
        assert result.input_text == ""
        assert result.output == ""
        assert result.expected_output is None
        assert result.timestamp  # Should have a timestamp
    
    def test_grade_result_to_dict(self):
        """Test GradeResult.to_dict()."""
        result = GradeResult(
            score=9.0,
            reasoning="Excellent",
            suggestions=["Minor improvement"],
            input_text="test input",
            output="test output",
        )
        
        d = result.to_dict()
        
        assert d["score"] == 9.0
        assert d["reasoning"] == "Excellent"
        assert d["suggestions"] == ["Minor improvement"]
        assert d["input_text"] == "test input"
        assert d["output"] == "test output"
        assert "timestamp" in d
    
    def test_grade_result_from_dict(self):
        """Test GradeResult.from_dict()."""
        data = {
            "score": 8.0,
            "reasoning": "Good",
            "suggestions": ["Suggestion 1"],
            "input_text": "input",
            "output": "output",
            "expected_output": "expected",
            "timestamp": "2024-01-01T00:00:00",
        }
        
        result = GradeResult.from_dict(data)
        
        assert result.score == 8.0
        assert result.reasoning == "Good"
        assert result.suggestions == ["Suggestion 1"]
        assert result.input_text == "input"
        assert result.output == "output"
        assert result.expected_output == "expected"
        assert result.timestamp == "2024-01-01T00:00:00"


class TestBaseLLMGrader:
    """Tests for BaseLLMGrader."""
    
    def test_grader_initialization(self):
        """Test grader initialization with defaults."""
        grader = BaseLLMGrader()
        
        assert grader.model == "gpt-4o-mini"
        assert grader.temperature == 0.1
        assert grader.max_tokens == 500
    
    def test_grader_custom_model(self):
        """Test grader with custom model."""
        grader = BaseLLMGrader(model="gpt-4", temperature=0.5, max_tokens=1000)
        
        assert grader.model == "gpt-4"
        assert grader.temperature == 0.5
        assert grader.max_tokens == 1000
    
    def test_build_prompt_without_expected(self):
        """Test prompt building without expected output."""
        grader = BaseLLMGrader()
        
        prompt = grader._build_prompt(
            input_text="What is Python?",
            output="Python is a programming language",
        )
        
        assert "What is Python?" in prompt
        assert "Python is a programming language" in prompt
        assert "EXPECTED OUTPUT" not in prompt
        assert "SCORE:" in prompt
        assert "REASONING:" in prompt
        assert "SUGGESTIONS:" in prompt
    
    def test_build_prompt_with_expected(self):
        """Test prompt building with expected output."""
        grader = BaseLLMGrader()
        
        prompt = grader._build_prompt(
            input_text="What is Python?",
            output="Python is a programming language",
            expected_output="Python is a high-level programming language",
        )
        
        assert "What is Python?" in prompt
        assert "Python is a programming language" in prompt
        assert "EXPECTED OUTPUT" in prompt
        assert "Python is a high-level programming language" in prompt
    
    def test_parse_response_valid(self):
        """Test parsing a valid LLM response."""
        grader = BaseLLMGrader()
        
        response = """SCORE: 8
REASONING: Good response with accurate information
SUGGESTIONS:
- Add more examples
- Include code snippets"""
        
        result = grader._parse_response(
            response,
            input_text="test",
            output="test output",
            expected_output=None,
        )
        
        assert result.score == 8.0
        assert "Good response" in result.reasoning
        assert len(result.suggestions) == 2
        assert "Add more examples" in result.suggestions
        assert "Include code snippets" in result.suggestions
    
    def test_parse_response_no_suggestions(self):
        """Test parsing response with no suggestions."""
        grader = BaseLLMGrader()
        
        response = """SCORE: 10
REASONING: Perfect response
SUGGESTIONS: None"""
        
        result = grader._parse_response(
            response,
            input_text="test",
            output="test output",
            expected_output=None,
        )
        
        assert result.score == 10.0
        assert result.suggestions == []
    
    def test_parse_response_clamps_score(self):
        """Test that scores are clamped to 1-10 range."""
        grader = BaseLLMGrader()
        
        # Test score > 10
        response = """SCORE: 15
REASONING: Over the top"""
        
        result = grader._parse_response(response, "", "", None)
        assert result.score == 10.0
        
        # Test score < 1
        response = """SCORE: -5
REASONING: Way too low"""
        
        result = grader._parse_response(response, "", "", None)
        assert result.score == 1.0
    
    def test_parse_response_invalid_score(self):
        """Test parsing response with invalid score."""
        grader = BaseLLMGrader()
        
        response = """SCORE: not a number
REASONING: Invalid"""
        
        result = grader._parse_response(response, "", "", None)
        assert result.score == 5.0  # Default
    
    def test_get_litellm_import_error(self):
        """Test that missing litellm raises ImportError."""
        grader = BaseLLMGrader()
        
        with patch.dict('sys.modules', {'litellm': None}):
            with pytest.raises(ImportError) as exc_info:
                grader._get_litellm()
            
            assert "litellm" in str(exc_info.value)
    
    def test_grade_success(self):
        """Test successful grading."""
        # Reload module to get fresh reference for patching
        import praisonaiagents.eval.grader as grader_module
        importlib.reload(grader_module)
        
        # Mock litellm
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """SCORE: 8
REASONING: Good response
SUGGESTIONS: None"""
        mock_litellm.completion.return_value = mock_response
        
        with patch.object(grader_module.BaseLLMGrader, '_get_litellm', return_value=mock_litellm):
            grader = grader_module.BaseLLMGrader()
            result = grader.grade(
                input_text="What is Python?",
                output="Python is a programming language",
            )
        
            assert result.score == 8.0
            assert "Good response" in result.reasoning
            mock_litellm.completion.assert_called_once()
    
    def test_grade_error_handling(self):
        """Test grading error handling."""
        # Reload module to get fresh reference for patching
        import praisonaiagents.eval.grader as grader_module
        importlib.reload(grader_module)
        
        mock_litellm = MagicMock()
        mock_litellm.completion.side_effect = Exception("API Error")
        
        with patch.object(grader_module.BaseLLMGrader, '_get_litellm', return_value=mock_litellm):
            grader = grader_module.BaseLLMGrader()
            result = grader.grade(
                input_text="test",
                output="test output",
            )
        
            assert result.score == 5.0
            assert "Grading error" in result.reasoning
    
    @pytest.mark.asyncio
    async def test_grade_async_success(self):
        """Test async grading."""
        # Reload module to get fresh reference for patching
        import praisonaiagents.eval.grader as grader_module
        importlib.reload(grader_module)
        
        mock_litellm = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """SCORE: 9
REASONING: Excellent
SUGGESTIONS: None"""
        
        # Mock async completion
        async def mock_acompletion(*args, **kwargs):
            return mock_response
        
        mock_litellm.acompletion = mock_acompletion
        
        with patch.object(grader_module.BaseLLMGrader, '_get_litellm', return_value=mock_litellm):
            grader = grader_module.BaseLLMGrader()
            result = await grader.grade_async(
                input_text="test",
                output="test output",
            )
        
            assert result.score == 9.0
            assert "Excellent" in result.reasoning


class TestProtocolCompliance:
    """Test that BaseLLMGrader complies with GraderProtocol."""
    
    def test_grader_protocol_compliance(self):
        """Test that BaseLLMGrader has required protocol attributes."""
        from praisonaiagents.eval.protocols import GraderProtocol
        
        grader = BaseLLMGrader()
        
        # Check required attributes
        assert hasattr(grader, 'model')
        assert hasattr(grader, 'temperature')
        assert hasattr(grader, 'grade')
        
        # Check it's runtime checkable
        assert isinstance(grader, GraderProtocol)
    
    def test_grade_result_protocol_compliance(self):
        """Test that GradeResult has required protocol attributes."""
        from praisonaiagents.eval.protocols import GradeResultProtocol
        
        result = GradeResult(score=8.0, reasoning="Good")
        
        # Check required attributes
        assert hasattr(result, 'score')
        assert hasattr(result, 'reasoning')
        assert hasattr(result, 'to_dict')
        
        # Check it's runtime checkable
        assert isinstance(result, GradeResultProtocol)
