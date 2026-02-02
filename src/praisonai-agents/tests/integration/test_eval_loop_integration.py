"""Integration tests for EvaluationLoop with mocked LLM."""

import pytest
from unittest.mock import MagicMock, patch


class TestEvaluationLoopIntegration:
    """Integration tests for EvaluationLoop."""
    
    def test_evaluation_loop_with_agent_and_judge(self):
        """Test full integration with Agent and Judge (mocked LLM)."""
        from praisonaiagents import Agent
        from praisonaiagents.eval import EvaluationLoop, EvaluationLoopResult
        
        with patch('praisonaiagents.agent.agent.Agent.chat') as mock_chat, \
             patch('litellm.completion') as mock_completion:
            
            mock_chat.side_effect = [
                "First attempt at analysis",
                "Improved analysis with more detail",
                "Final comprehensive analysis with all requirements",
            ]
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = """
SCORE: 9
REASONING: Excellent comprehensive analysis
SUGGESTIONS: None needed
"""
            mock_completion.return_value = mock_response
            
            agent = Agent(name="test_agent", instructions="Analyze systems")
            
            loop = EvaluationLoop(
                agent=agent,
                criteria="Analysis is thorough",
                threshold=8.0,
                max_iterations=3,
            )
            
            result = loop.run("Analyze the auth flow")
            
            assert isinstance(result, EvaluationLoopResult)
            assert result.final_score == 9.0
            assert result.success is True
    
    def test_agent_run_until_method(self):
        """Test Agent.run_until() convenience method."""
        from praisonaiagents import Agent
        from praisonaiagents.eval.results import EvaluationLoopResult
        
        with patch('praisonaiagents.agent.agent.Agent.chat') as mock_chat, \
             patch('litellm.completion') as mock_completion:
            
            mock_chat.return_value = "Good analysis output"
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = """
SCORE: 8.5
REASONING: Good quality analysis
SUGGESTIONS: Consider edge cases
"""
            mock_completion.return_value = mock_response
            
            agent = Agent(name="test_agent", instructions="Analyze systems")
            
            result = agent.run_until(
                "Analyze the codebase",
                criteria="Analysis is thorough",
                threshold=8.0,
            )
            
            assert isinstance(result, EvaluationLoopResult)
            assert result.success is True
            assert result.final_score == 8.5
    
    def test_evaluation_loop_iteration_callback(self):
        """Test that iteration callback is called correctly."""
        from praisonaiagents import Agent
        from praisonaiagents.eval import EvaluationLoop
        
        with patch('praisonaiagents.agent.agent.Agent.chat') as mock_chat, \
             patch('litellm.completion') as mock_completion:
            
            mock_chat.return_value = "Output"
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 9\nREASONING: Good"
            mock_completion.return_value = mock_response
            
            callback_results = []
            def on_iteration(result):
                callback_results.append(result)
            
            agent = Agent(name="test", instructions="Test")
            loop = EvaluationLoop(
                agent=agent,
                criteria="Be good",
                threshold=8.0,
                on_iteration=on_iteration,
            )
            
            loop.run("Test prompt")
            
            assert len(callback_results) == 1
            assert callback_results[0].score == 9.0
    
    def test_evaluation_loop_multiple_iterations(self):
        """Test loop runs multiple iterations when score is below threshold."""
        from praisonaiagents import Agent
        from praisonaiagents.eval import EvaluationLoop
        
        with patch('praisonaiagents.agent.agent.Agent.chat') as mock_chat, \
             patch('litellm.completion') as mock_completion:
            
            mock_chat.side_effect = ["Output 1", "Output 2", "Output 3"]
            
            responses = [
                "SCORE: 5\nREASONING: Needs work\nSUGGESTIONS: Improve detail",
                "SCORE: 7\nREASONING: Better\nSUGGESTIONS: Add examples",
                "SCORE: 9\nREASONING: Excellent\nSUGGESTIONS: None",
            ]
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = responses[0]
            
            call_count = [0]
            def side_effect(*args, **kwargs):
                idx = min(call_count[0], len(responses) - 1)
                mock_response.choices[0].message.content = responses[idx]
                call_count[0] += 1
                return mock_response
            
            mock_completion.side_effect = side_effect
            
            agent = Agent(name="test", instructions="Test")
            loop = EvaluationLoop(
                agent=agent,
                criteria="Be thorough",
                threshold=8.0,
                max_iterations=5,
            )
            
            result = loop.run("Test prompt")
            
            assert result.success is True
            assert len(result.iterations) == 3
            assert result.score_history == [5.0, 7.0, 9.0]
    
    def test_evaluation_loop_max_iterations_reached(self):
        """Test loop stops at max iterations even if threshold not met."""
        from praisonaiagents import Agent
        from praisonaiagents.eval import EvaluationLoop
        
        with patch('praisonaiagents.agent.agent.Agent.chat') as mock_chat, \
             patch('litellm.completion') as mock_completion:
            
            mock_chat.return_value = "Output"
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 5\nREASONING: Poor"
            mock_completion.return_value = mock_response
            
            agent = Agent(name="test", instructions="Test")
            loop = EvaluationLoop(
                agent=agent,
                criteria="Be thorough",
                threshold=8.0,
                max_iterations=3,
            )
            
            result = loop.run("Test prompt")
            
            assert result.success is False
            assert len(result.iterations) == 3
            assert result.final_score == 5.0
    
    def test_evaluation_loop_review_mode(self):
        """Test review mode runs all iterations regardless of score."""
        from praisonaiagents import Agent
        from praisonaiagents.eval import EvaluationLoop
        
        with patch('praisonaiagents.agent.agent.Agent.chat') as mock_chat, \
             patch('litellm.completion') as mock_completion:
            
            mock_chat.return_value = "Output"
            
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "SCORE: 10\nREASONING: Perfect"
            mock_completion.return_value = mock_response
            
            agent = Agent(name="test", instructions="Test")
            loop = EvaluationLoop(
                agent=agent,
                criteria="Be thorough",
                threshold=8.0,
                max_iterations=3,
                mode="review",
            )
            
            result = loop.run("Test prompt")
            
            assert result.success is True
            assert len(result.iterations) == 3


class TestEvaluationLoopResultSerialization:
    """Tests for result serialization."""
    
    def test_result_to_json(self):
        """Test EvaluationLoopResult.to_json()."""
        from praisonaiagents.eval.results import IterationResult, EvaluationLoopResult
        import json
        
        iterations = [
            IterationResult(iteration=1, output="Out1", score=7.0, reasoning="OK"),
            IterationResult(iteration=2, output="Out2", score=9.0, reasoning="Good"),
        ]
        
        result = EvaluationLoopResult(
            iterations=iterations,
            success=True,
            total_duration_seconds=5.0,
        )
        
        json_str = result.to_json()
        parsed = json.loads(json_str)
        
        assert parsed["success"] is True
        assert parsed["final_score"] == 9.0
        assert parsed["score_history"] == [7.0, 9.0]
        assert len(parsed["iterations"]) == 2
    
    def test_result_final_report(self):
        """Test EvaluationLoopResult.final_report property."""
        from praisonaiagents.eval.results import IterationResult, EvaluationLoopResult
        
        iterations = [
            IterationResult(
                iteration=1, 
                output="First output", 
                score=6.0, 
                reasoning="Needs improvement",
                findings=["Add more detail"]
            ),
            IterationResult(
                iteration=2, 
                output="Better output", 
                score=8.5, 
                reasoning="Good quality",
                findings=[]
            ),
        ]
        
        result = EvaluationLoopResult(
            iterations=iterations,
            success=True,
            total_duration_seconds=3.5,
            threshold=8.0,
        )
        
        report = result.final_report
        
        assert "# Evaluation Loop Report" in report
        assert "Success" in report or "✅" in report
        assert "8.5" in report
        assert "Iteration 1" in report
        assert "Iteration 2" in report
        assert "Add more detail" in report
