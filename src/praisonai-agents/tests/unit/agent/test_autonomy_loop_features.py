"""
Tests for enhanced autonomy loop features.

Tests for:
- Completion promise detection
- Prompt re-injection
- Context clearing between iterations

TDD: These tests are written FIRST, before implementation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestCompletionPromise:
    """Test completion promise detection in run_autonomous()."""
    
    def test_autonomy_config_accepts_completion_promise(self):
        """AutonomyConfig should accept completion_promise parameter."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig(completion_promise="DONE")
        assert config.completion_promise == "DONE"
    
    def test_autonomy_config_completion_promise_default_none(self):
        """AutonomyConfig.completion_promise should default to None."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig()
        assert config.completion_promise is None
    
    def test_run_autonomous_accepts_completion_promise_param(self):
        """run_autonomous() should accept completion_promise parameter."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        # Mock chat to return a response with promise
        with patch.object(agent, 'chat', return_value="Task done. <promise>DONE</promise>"):
            result = agent.run_autonomous(
                "Test task",
                max_iterations=5,
                completion_promise="DONE"
            )
        
        assert result.success == True
        assert result.completion_reason == "promise"
    
    def test_completion_promise_detected_in_response(self):
        """Agent should detect <promise>TEXT</promise> in response."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        # Mock chat to return response with promise tag
        with patch.object(agent, 'chat', return_value="I have completed the task. <promise>TASK_COMPLETE</promise>"):
            result = agent.run_autonomous(
                "Build something",
                max_iterations=10,
                completion_promise="TASK_COMPLETE"
            )
        
        assert result.success == True
        assert result.completion_reason == "promise"
        assert result.iterations == 1  # Should stop on first iteration
    
    def test_completion_promise_not_detected_without_tag(self):
        """Agent should NOT detect promise without proper tag."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        # Mock chat to return response WITHOUT promise tag
        responses = ["Working on it...", "Still working...", "Almost done. TASK_COMPLETE"]
        call_count = [0]
        
        def mock_chat(prompt):
            idx = min(call_count[0], len(responses) - 1)
            call_count[0] += 1
            return responses[idx]
        
        with patch.object(agent, 'chat', side_effect=mock_chat):
            result = agent.run_autonomous(
                "Build something",
                max_iterations=3,
                completion_promise="TASK_COMPLETE"
            )
        
        # Should NOT succeed because promise tag is missing
        assert result.completion_reason != "promise"
    
    def test_completion_promise_exact_match(self):
        """Promise detection should require exact match."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        # Mock chat with wrong promise text
        with patch.object(agent, 'chat', return_value="<promise>WRONG</promise>"):
            result = agent.run_autonomous(
                "Test task",
                max_iterations=2,
                completion_promise="DONE"
            )
        
        # Should NOT detect because promise text doesn't match
        assert result.completion_reason != "promise"


class TestPromptReinjection:
    """Test that original prompt is re-injected each iteration."""
    
    def test_original_prompt_used_every_iteration(self):
        """Original prompt should be used for every iteration, not 'Continue with task'."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        prompts_received = []
        call_count = [0]
        
        def mock_chat(prompt):
            prompts_received.append(prompt)
            call_count[0] += 1
            if call_count[0] >= 3:
                return "<promise>DONE</promise>"
            return "Working..."
        
        with patch.object(agent, 'chat', side_effect=mock_chat):
            result = agent.run_autonomous(
                "Build a REST API",
                max_iterations=5,
                completion_promise="DONE"
            )
        
        # All prompts should be the original, not "Continue with the task"
        for prompt in prompts_received:
            assert prompt == "Build a REST API", f"Expected original prompt, got: {prompt}"
    
    def test_prompt_not_continue_with_task(self):
        """Prompt should NOT be 'Continue with the task' after first iteration."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        prompts_received = []
        
        def mock_chat(prompt):
            prompts_received.append(prompt)
            if len(prompts_received) >= 2:
                return "<promise>DONE</promise>"
            return "Working..."
        
        with patch.object(agent, 'chat', side_effect=mock_chat):
            result = agent.run_autonomous(
                "My specific task",
                max_iterations=5,
                completion_promise="DONE"
            )
        
        # No prompt should be "Continue with the task"
        for prompt in prompts_received:
            assert "Continue with the task" not in prompt


class TestContextClearing:
    """Test context clearing between iterations."""
    
    def test_autonomy_config_accepts_clear_context(self):
        """AutonomyConfig should accept clear_context parameter."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig(clear_context=True)
        assert config.clear_context == True
    
    def test_autonomy_config_clear_context_default_false(self):
        """AutonomyConfig.clear_context should default to False."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig()
        assert config.clear_context == False
    
    def test_run_autonomous_accepts_clear_context_param(self):
        """run_autonomous() should accept clear_context parameter."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        with patch.object(agent, 'chat', return_value="<promise>DONE</promise>"):
            # Should not raise
            result = agent.run_autonomous(
                "Test task",
                max_iterations=5,
                completion_promise="DONE",
                clear_context=True
            )
        
        assert result.success == True
    
    def test_clear_history_called_when_clear_context_true(self):
        """clear_history() should be called between iterations when clear_context=True."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        call_count = [0]
        
        def mock_chat(prompt):
            call_count[0] += 1
            if call_count[0] >= 3:
                return "<promise>DONE</promise>"
            return "Working..."
        
        with patch.object(agent, 'chat', side_effect=mock_chat):
            with patch.object(agent, 'clear_history') as mock_clear:
                result = agent.run_autonomous(
                    "Test task",
                    max_iterations=5,
                    completion_promise="DONE",
                    clear_context=True
                )
        
        # clear_history should be called after each iteration (except the last)
        assert mock_clear.call_count >= 2  # At least 2 calls for 3 iterations
    
    def test_clear_history_not_called_when_clear_context_false(self):
        """clear_history() should NOT be called when clear_context=False."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        call_count = [0]
        
        def mock_chat(prompt):
            call_count[0] += 1
            if call_count[0] >= 2:
                return "<promise>DONE</promise>"
            return "Working..."
        
        with patch.object(agent, 'chat', side_effect=mock_chat):
            with patch.object(agent, 'clear_history') as mock_clear:
                result = agent.run_autonomous(
                    "Test task",
                    max_iterations=5,
                    completion_promise="DONE",
                    clear_context=False  # Explicitly false
                )
        
        # clear_history should NOT be called
        assert mock_clear.call_count == 0


class TestBackwardCompatibility:
    """Test that existing behavior is preserved."""
    
    def test_run_autonomous_works_without_new_params(self):
        """run_autonomous() should work without new parameters."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        # Mock to return completion signal (old style)
        with patch.object(agent, 'chat', return_value="Task completed successfully"):
            result = agent.run_autonomous(
                "Test task",
                max_iterations=5
            )
        
        # Should still work with keyword detection
        assert result.success == True
    
    def test_keyword_detection_still_works(self):
        """Old keyword-based completion detection should still work."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            autonomy=True,
            output="silent"
        )
        
        with patch.object(agent, 'chat', return_value="I have finished the task"):
            result = agent.run_autonomous(
                "Test task",
                max_iterations=5
                # No completion_promise - use old behavior
            )
        
        assert result.success == True
        assert result.completion_reason == "goal"


class TestAutonomyConfigFromDict:
    """Test AutonomyConfig.from_dict() with new fields."""
    
    def test_from_dict_with_completion_promise(self):
        """from_dict should parse completion_promise."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig.from_dict({
            "completion_promise": "TASK_DONE",
            "max_iterations": 10
        })
        
        assert config.completion_promise == "TASK_DONE"
        assert config.max_iterations == 10
    
    def test_from_dict_with_clear_context(self):
        """from_dict should parse clear_context."""
        from praisonaiagents.agent.autonomy import AutonomyConfig
        
        config = AutonomyConfig.from_dict({
            "clear_context": True
        })
        
        assert config.clear_context == True
