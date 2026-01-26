"""
Tests for recipe judge integration with the unified Judge protocol.

TDD: These tests verify that ContextEffectivenessJudge works with the new Judge protocol.
"""
from unittest.mock import patch, MagicMock
from dataclasses import is_dataclass


class TestRecipeJudgeProtocolCompliance:
    """Test that recipe judge follows Judge protocol patterns."""
    
    def test_context_effectiveness_judge_importable(self):
        """ContextEffectivenessJudge should be importable."""
        from praisonai.replay import ContextEffectivenessJudge
        assert ContextEffectivenessJudge is not None
    
    def test_context_effectiveness_judge_has_model_attribute(self):
        """Judge should have model attribute like JudgeProtocol."""
        from praisonai.replay import ContextEffectivenessJudge
        judge = ContextEffectivenessJudge()
        assert hasattr(judge, 'model')
        assert judge.model is not None
    
    def test_context_effectiveness_judge_has_temperature_attribute(self):
        """Judge should have temperature attribute like JudgeProtocol."""
        from praisonai.replay import ContextEffectivenessJudge
        judge = ContextEffectivenessJudge()
        assert hasattr(judge, 'temperature')
        assert judge.temperature == 0.1
    
    def test_judge_report_is_dataclass(self):
        """JudgeReport should be a dataclass."""
        from praisonai.replay import JudgeReport
        assert is_dataclass(JudgeReport)
    
    def test_context_effectiveness_score_is_dataclass(self):
        """ContextEffectivenessScore should be a dataclass."""
        from praisonai.replay.judge import ContextEffectivenessScore
        assert is_dataclass(ContextEffectivenessScore)


class TestRecipeJudgeRegistry:
    """Test that recipe judge can be registered in the judge registry."""
    
    def test_recipe_judge_registered(self):
        """Recipe judge should be registered in the judge registry."""
        from praisonaiagents.eval import list_judges
        judges = list_judges()
        # Should have at least accuracy and criteria
        assert "accuracy" in judges
        assert "criteria" in judges
    
    def test_can_add_recipe_judge_to_registry(self):
        """Should be able to add a recipe-style judge to registry."""
        from praisonaiagents.eval import add_judge, get_judge, Judge
        
        class TestRecipeJudge(Judge):
            """Test recipe judge."""
            criteria = "Recipe execution quality"
        
        add_judge("test_recipe", TestRecipeJudge)
        retrieved = get_judge("test_recipe")
        assert retrieved is TestRecipeJudge


class TestRecipeJudgeModes:
    """Test recipe judge evaluation modes."""
    
    def test_context_mode_default(self):
        """Default mode should be context."""
        from praisonai.replay import ContextEffectivenessJudge
        judge = ContextEffectivenessJudge()
        assert judge.mode == "context"
    
    def test_memory_mode(self):
        """Memory mode should use memory prompt template."""
        from praisonai.replay import ContextEffectivenessJudge
        judge = ContextEffectivenessJudge(mode="memory")
        assert judge.mode == "memory"
        assert "memory" in judge.prompt_template.lower()
    
    def test_knowledge_mode(self):
        """Knowledge mode should use knowledge prompt template."""
        from praisonai.replay import ContextEffectivenessJudge
        judge = ContextEffectivenessJudge(mode="knowledge")
        assert judge.mode == "knowledge"
        assert "knowledge" in judge.prompt_template.lower()


class TestRecipeJudgeDataclasses:
    """Test recipe judge dataclasses."""
    
    def test_judge_report_to_dict(self):
        """JudgeReport should have to_dict method."""
        from praisonai.replay import JudgeReport
        report = JudgeReport(
            session_id="test-123",
            timestamp="2024-01-01T00:00:00",
            total_agents=2,
            overall_score=8.5,
            agent_scores=[],
            summary="Test summary",
            recommendations=["Rec 1"],
        )
        d = report.to_dict()
        assert d["session_id"] == "test-123"
        assert d["overall_score"] == 8.5
    
    def test_judge_report_from_dict(self):
        """JudgeReport should have from_dict class method."""
        from praisonai.replay import JudgeReport
        data = {
            "session_id": "test-456",
            "timestamp": "2024-01-01T00:00:00",
            "total_agents": 1,
            "overall_score": 7.0,
            "agent_scores": [],
            "summary": "Test",
            "recommendations": [],
        }
        report = JudgeReport.from_dict(data)
        assert report.session_id == "test-456"
        assert report.overall_score == 7.0


class TestRecipeJudgeLazyLoading:
    """Test that recipe judge uses lazy loading for litellm."""
    
    def test_litellm_not_loaded_on_import(self):
        """Importing recipe judge should not load litellm."""
        import sys
        modules_before = set(sys.modules.keys())
        
        from praisonai.replay import ContextEffectivenessJudge  # noqa: F401
        
        # litellm should not be loaded just from import
        assert 'litellm' not in sys.modules or 'litellm' in modules_before
    
    def test_get_litellm_lazy_import(self):
        """_get_litellm should lazily import litellm."""
        from praisonai.replay import ContextEffectivenessJudge
        judge = ContextEffectivenessJudge()
        
        # This should work (litellm is installed)
        litellm = judge._get_litellm()
        assert litellm is not None


class TestFormatJudgeReport:
    """Test report formatting."""
    
    def test_format_judge_report_function_exists(self):
        """format_judge_report should be importable."""
        from praisonai.replay import format_judge_report
        assert callable(format_judge_report)
    
    def test_format_judge_report_output(self):
        """format_judge_report should return formatted string."""
        from praisonai.replay import JudgeReport, format_judge_report
        
        report = JudgeReport(
            session_id="test-format",
            timestamp="2024-01-01T00:00:00",
            total_agents=1,
            overall_score=8.0,
            agent_scores=[],
            summary="Test summary",
            recommendations=["Improve X"],
        )
        
        output = format_judge_report(report)
        assert "test-format" in output
        assert "8.0" in output
        assert "RECOMMENDATIONS" in output


class TestRecipeJudgeWithMockedLLM:
    """Test recipe judge with mocked LLM calls."""
    
    @patch('praisonai.replay.judge.ContextEffectivenessJudge._get_litellm')
    def test_judge_agent_returns_score(self, mock_litellm):
        """_judge_agent should return ContextEffectivenessScore."""
        from praisonai.replay.judge import ContextEffectivenessJudge, ContextEffectivenessScore
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """TASK_SCORE: 8
CONTEXT_SCORE: 7
QUALITY_SCORE: 9
INSTRUCTION_SCORE: 8
HALLUCINATION_SCORE: 10
ERROR_SCORE: 9
FAILURE_DETECTED: false
REASONING: Good performance
SUGGESTIONS:
- Improve error handling
"""
        mock_litellm.return_value.completion.return_value = mock_response
        
        judge = ContextEffectivenessJudge()
        
        agent_info = {
            "inputs": ["Test input"],
            "outputs": ["Test output"],
            "context": ["Test context"],
            "tool_calls": [],
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        
        score = judge._judge_agent("TestAgent", agent_info)
        
        assert isinstance(score, ContextEffectivenessScore)
        assert score.agent_name == "TestAgent"
        assert score.task_achievement_score == 8.0
        assert score.context_utilization_score == 7.0
        assert score.output_quality_score == 9.0
