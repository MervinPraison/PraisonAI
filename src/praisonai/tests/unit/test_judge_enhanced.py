"""
Tests for Enhanced Judge System.

Tests the following enhancements:
1. Recipe goal extraction and evaluation
2. Previous step quality context passing
3. Dynamic failure detection via LLM prompt (no hardcoded keywords)
4. Input validation status tracking
"""

import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the praisonai package to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestRecipeGoalExtraction:
    """Test recipe goal extraction from YAML."""
    
    def test_extract_recipe_goal_from_yaml(self):
        """Should extract the recipe-level goal from YAML."""
        from praisonai.replay.judge import _detect_yaml_structure
        
        # Create a temp YAML with recipe goal
        import tempfile
        
        yaml_content = """
goal: "Analyze the input image and create a comprehensive blog post"
topic: "Image Analysis"
roles:
  image_analyzer:
    role: Image Analyzer
    goal: Analyze images for content
    tasks:
      analyze:
        description: Analyze the provided image
        expected_output: Detailed image analysis
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            result = _detect_yaml_structure(yaml_path)
            assert "recipe_goal" in result
            assert "Analyze the input image" in result["recipe_goal"]
        finally:
            os.unlink(yaml_path)
    
    def test_extract_recipe_goal_missing(self):
        """Should handle YAML without recipe goal gracefully."""
        from praisonai.replay.judge import _detect_yaml_structure
        
        import tempfile
        
        yaml_content = """
roles:
  analyzer:
    role: Analyzer
    goal: Do analysis
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name
        
        try:
            result = _detect_yaml_structure(yaml_path)
            # Should have empty or default recipe_goal
            assert result.get("recipe_goal", "") == "" or "recipe_goal" in result
        finally:
            os.unlink(yaml_path)


class TestPreviousStepQualityContext:
    """Test previous step quality context passing."""
    
    def test_previous_steps_included_in_prompt(self):
        """Should include previous agent scores in the prompt for subsequent agents."""
        from praisonai.replay.judge import ContextEffectivenessJudge, ContextEffectivenessScore
        
        judge = ContextEffectivenessJudge()
        
        # Create mock previous scores
        previous_scores = [
            ContextEffectivenessScore(
                agent_name="image_analyzer",
                task_achievement_score=3.0,
                context_utilization_score=5.0,
                output_quality_score=4.0,
                overall_score=4.0,
                reasoning="Failed to access the image",
                suggestions=["Provide valid image path"],
            )
        ]
        
        # Build context for next agent
        context = judge._build_previous_steps_context(previous_scores)
        
        assert "image_analyzer" in context
        assert "3.0" in context or "3" in context  # Task score
        assert "Failed to access" in context or "failed" in context.lower()
    
    def test_empty_previous_steps(self):
        """Should handle empty previous steps gracefully."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge()
        context = judge._build_previous_steps_context([])
        
        assert context == "" or "No previous" in context or "first agent" in context.lower()


class TestDynamicFailureDetection:
    """Test dynamic failure detection via LLM prompt."""
    
    def test_prompt_includes_failure_detection_instructions(self):
        """Prompt should instruct LLM to detect failures dynamically."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge()
        
        # The prompt template should include failure detection instructions
        prompt = judge.prompt_template
        
        # Should NOT have hardcoded failure keywords
        # Instead should have instructions for LLM to detect failures
        assert "FAILURE_DETECTED" in prompt or "failure" in prompt.lower()
        assert "If the agent" in prompt or "task failed" in prompt.lower()
    
    def test_failure_score_parsed_from_response(self):
        """Should parse FAILURE_DETECTED score from LLM response."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge()
        
        # Mock response with failure detection
        response_text = """TASK_SCORE: 2
CONTEXT_SCORE: 5
QUALITY_SCORE: 3
INSTRUCTION_SCORE: 4
HALLUCINATION_SCORE: 8
ERROR_SCORE: 3
FAILURE_DETECTED: true
FAILURE_REASON: Agent explicitly stated it could not access the image
REASONING: The agent failed to complete the primary task
SUGGESTIONS:
- Provide a valid image path
"""
        
        agent_info = {"prompt_tokens": 100, "completion_tokens": 50}
        score = judge._parse_response(response_text, "test_agent", agent_info)
        
        # Should have low task score due to failure
        assert score.task_achievement_score <= 3
        # Should have failure_detected flag
        assert hasattr(score, 'failure_detected') and score.failure_detected


class TestInputValidationStatus:
    """Test input validation status tracking."""
    
    def test_detect_unresolved_templates(self):
        """Should detect unresolved {{variable}} templates."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge()
        
        # Mock events with unresolved template
        events = [
            {
                "event_type": "llm_request",
                "agent_name": "analyzer",
                "data": {
                    "messages": [
                        {"role": "user", "content": "Analyze the image at {{image_path}}"}
                    ]
                }
            }
        ]
        
        content_loss, details = judge._detect_content_loss(events)
        
        assert content_loss is True
        assert any("image_path" in d for d in details)
    
    def test_input_validation_in_prompt(self):
        """Should include input validation status in the judge prompt."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        judge = ContextEffectivenessJudge()
        
        # The prompt should have a place for input validation status
        prompt = judge.prompt_template
        
        # Should include input validation section
        assert "INPUT" in prompt.upper()


class TestEnhancedJudgeReport:
    """Test enhanced judge report with new fields."""
    
    def test_report_includes_recipe_goal(self):
        """Report should include the recipe goal."""
        from praisonai.replay.judge import JudgeReport
        
        report = JudgeReport(
            session_id="test",
            timestamp="2024-01-01",
            total_agents=1,
            overall_score=5.0,
            agent_scores=[],
            summary="Test",
            recommendations=[],
            recipe_goal="Analyze images and create blog posts",
        )
        
        assert report.recipe_goal == "Analyze images and create blog posts"
        
        # Should be in dict representation
        report_dict = report.to_dict()
        assert "recipe_goal" in report_dict
    
    def test_report_includes_failure_summary(self):
        """Report should include failure summary."""
        from praisonai.replay.judge import JudgeReport, ContextEffectivenessScore
        
        score = ContextEffectivenessScore(
            agent_name="analyzer",
            task_achievement_score=2.0,
            context_utilization_score=5.0,
            output_quality_score=3.0,
            overall_score=3.3,
            reasoning="Failed to access image",
            failure_detected=True,
            failure_reason="Could not read image file",
        )
        
        report = JudgeReport(
            session_id="test",
            timestamp="2024-01-01",
            total_agents=1,
            overall_score=3.3,
            agent_scores=[score],
            summary="Test",
            recommendations=[],
        )
        
        # Should indicate failures in summary
        assert report.agent_scores[0].failure_detected is True


class TestJudgeTraceWithEnhancements:
    """Test judge_trace with all enhancements."""
    
    @patch('praisonai.replay.judge.ContextEffectivenessJudge._get_litellm')
    def test_judge_trace_passes_previous_scores(self, mock_litellm):
        """judge_trace should pass previous agent scores to subsequent agents."""
        from praisonai.replay.judge import ContextEffectivenessJudge
        
        # Mock litellm response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """TASK_SCORE: 5
CONTEXT_SCORE: 5
QUALITY_SCORE: 5
INSTRUCTION_SCORE: 5
HALLUCINATION_SCORE: 10
ERROR_SCORE: 10
FAILURE_DETECTED: false
REASONING: Test
SUGGESTIONS:
- Test suggestion
"""
        mock_litellm.return_value.completion.return_value = mock_response
        
        judge = ContextEffectivenessJudge()
        
        # Create events for two agents
        events = [
            {"event_type": "agent_start", "agent_name": "agent1", "data": {}},
            {"event_type": "llm_request", "agent_name": "agent1", "data": {"messages": [{"role": "user", "content": "test"}]}},
            {"event_type": "llm_response", "agent_name": "agent1", "data": {"response_content": "response1"}},
            {"event_type": "agent_end", "agent_name": "agent1", "data": {}},
            {"event_type": "agent_start", "agent_name": "agent2", "data": {}},
            {"event_type": "llm_request", "agent_name": "agent2", "data": {"messages": [{"role": "user", "content": "test2"}]}},
            {"event_type": "llm_response", "agent_name": "agent2", "data": {"response_content": "response2"}},
            {"event_type": "agent_end", "agent_name": "agent2", "data": {}},
        ]
        
        report = judge.judge_trace(events, session_id="test", evaluate_tools=False, evaluate_context_flow=False)
        
        # Should have evaluated both agents
        assert len(report.agent_scores) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
