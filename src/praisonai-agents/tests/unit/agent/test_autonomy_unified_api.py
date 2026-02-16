"""
TDD tests for unified autonomy API.

Goal: Agent(autonomy=True) + agent.start("Task") should automatically
use the autonomous loop. No need to call run_autonomous() separately.

Current (redundant):
    agent = Agent(autonomy=True)
    result = agent.run_autonomous("Task")  # Why two steps?

Proposed (unified):
    agent = Agent(autonomy=True)
    result = agent.start("Task")  # Automatically uses autonomy loop!
"""

import pytest
from unittest.mock import patch, MagicMock


class TestUnifiedAutonomyAPI:
    """Test that start() automatically uses autonomy when enabled."""
    
    def test_start_uses_autonomy_when_enabled(self):
        """start() should route to run_autonomous when autonomy=True."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'run_autonomous') as mock_run_auto:
            mock_run_auto.return_value = MagicMock(
                success=True,
                output="Task completed",
                completion_reason="goal",
                iterations=1,
            )
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=True,
                llm="gpt-4o-mini",
            )
            
            result = agent.start("Do something")
            
            # Should have called run_autonomous, not chat
            mock_run_auto.assert_called_once()
            call_kwargs = mock_run_auto.call_args[1]
            assert call_kwargs.get("prompt") == "Do something"
    
    def test_start_uses_chat_when_autonomy_disabled(self):
        """start() should use regular chat when autonomy is not enabled."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'chat') as mock_chat:
            mock_chat.return_value = "Hello response"
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=False,  # Disabled
                llm="gpt-4o-mini",
            )
            
            # Force non-streaming for test
            result = agent.start("Hello", stream=False)
            
            # Should have called chat, not run_autonomous
            mock_chat.assert_called()
    
    def test_start_returns_autonomy_result_when_autonomy_enabled(self):
        """start() should return AutonomyResult when autonomy is enabled."""
        from praisonaiagents import Agent
        from praisonaiagents.agent.autonomy import AutonomyResult
        
        with patch.object(Agent, 'run_autonomous') as mock_run_auto:
            mock_result = AutonomyResult(
                success=True,
                output="Done!",
                completion_reason="goal",
                iterations=2,
            )
            mock_run_auto.return_value = mock_result
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=True,
                llm="gpt-4o-mini",
            )
            
            result = agent.start("Task")
            
            assert isinstance(result, AutonomyResult)
            assert result.success is True
            assert result.output == "Done!"
    
    def test_start_passes_autonomy_config_to_run_autonomous(self):
        """start() should pass autonomy config values to run_autonomous."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'run_autonomous') as mock_run_auto:
            mock_run_auto.return_value = MagicMock(success=True, output="OK")
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy={
                    "max_iterations": 15,
                    "completion_promise": "DONE",
                    "clear_context": True,
                },
                llm="gpt-4o-mini",
            )
            
            agent.start("Task")
            
            call_kwargs = mock_run_auto.call_args[1]
            assert call_kwargs.get("max_iterations") == 15
            assert call_kwargs.get("completion_promise") == "DONE"
            assert call_kwargs.get("clear_context") is True
    
    def test_start_timeout_passed_to_run_autonomous(self):
        """start(timeout=X) should pass timeout to run_autonomous."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'run_autonomous') as mock_run_auto:
            mock_run_auto.return_value = MagicMock(success=True, output="OK")
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=True,
                llm="gpt-4o-mini",
            )
            
            agent.start("Task", timeout=60.0)
            
            call_kwargs = mock_run_auto.call_args[1]
            assert call_kwargs.get("timeout_seconds") == 60.0
    
    def test_default_agent_uses_single_turn_chat(self):
        """Default agent (no autonomy) should use single-turn chat."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'chat') as mock_chat:
            mock_chat.return_value = "Response"
            
            # No autonomy parameter = default = single-turn
            agent = Agent(
                name="test",
                instructions="Test agent",
                llm="gpt-4o-mini",
            )
            
            assert agent.autonomy_enabled is False
            
            agent.start("Hello", stream=False)
            mock_chat.assert_called()
    
    def test_autonomy_false_explicit_uses_single_turn(self):
        """autonomy=False should use single-turn chat."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'chat') as mock_chat:
            mock_chat.return_value = "Response"
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=False,
                llm="gpt-4o-mini",
            )
            
            assert agent.autonomy_enabled is False
            
            agent.start("Hello", stream=False)
            mock_chat.assert_called()


class TestRunAutonomousStillWorks:
    """Ensure run_autonomous() still works for explicit calls (backward compat)."""
    
    def test_run_autonomous_explicit_call_works(self):
        """run_autonomous() should still work when called explicitly."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'chat') as mock_chat:
            mock_chat.return_value = "Task completed successfully"
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=True,
                llm="gpt-4o-mini",
            )
            
            result = agent.run_autonomous("Do something", max_iterations=2)
            
            assert result.success is True
            assert result.iterations >= 1
    
    def test_run_autonomous_without_autonomy_enabled_raises(self):
        """run_autonomous() should raise if autonomy not enabled."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test",
            instructions="Test agent",
            autonomy=False,
            llm="gpt-4o-mini",
        )
        
        with pytest.raises(ValueError, match="Autonomy must be enabled"):
            agent.run_autonomous("Task")


class TestAsyncUnifiedAPI:
    """Test async variant of unified API."""
    
    @pytest.mark.asyncio
    async def test_astart_uses_autonomy_when_enabled(self):
        """astart() should route to run_autonomous_async when autonomy=True."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'run_autonomous_async') as mock_run_auto:
            mock_run_auto.return_value = MagicMock(
                success=True,
                output="Task completed",
                completion_reason="goal",
                iterations=1,
            )
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=True,
                llm="gpt-4o-mini",
            )
            
            result = await agent.astart("Do something")
            
            mock_run_auto.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_astart_uses_achat_when_autonomy_disabled(self):
        """astart() should use achat when autonomy is not enabled."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'achat') as mock_achat:
            mock_achat.return_value = "Hello response"
            
            agent = Agent(
                name="test",
                instructions="Test agent",
                autonomy=False,
                llm="gpt-4o-mini",
            )
            
            result = await agent.astart("Hello")
            
            mock_achat.assert_called()


class TestCLISimplification:
    """Test that CLI can use simplified API."""
    
    def test_cli_can_use_start_for_loop(self):
        """CLI loop command should be able to use agent.start() directly."""
        from praisonaiagents import Agent
        
        with patch.object(Agent, 'run_autonomous') as mock_run_auto:
            mock_run_auto.return_value = MagicMock(
                success=True,
                output="Done",
                completion_reason="goal",
                iterations=3,
                duration_seconds=5.0,
                started_at="2024-01-01T00:00:00Z",
            )
            
            # This is what CLI should do - simple!
            agent = Agent(
                name="loop_agent",
                instructions="Complete the task",
                autonomy={
                    "max_iterations": 10,
                    "completion_promise": "DONE",
                },
                llm="gpt-4o-mini",
            )
            
            result = agent.start("Build something")
            
            assert result.success is True
            mock_run_auto.assert_called_once()
