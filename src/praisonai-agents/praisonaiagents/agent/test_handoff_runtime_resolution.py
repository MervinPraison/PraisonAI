"""
Integration tests for handoff runtime resolution.

This test suite validates that handoffs now use turn-time runtime resolution
instead of construction-time pins, addressing issue #1938.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
import asyncio

from .handoff import Handoff, HandoffConfig, ContextPolicy, HandoffResult
from ..runtime.resolve import SessionContext


class MockAgent:
    """Mock agent for testing handoff scenarios."""
    
    def __init__(self, name, model="gpt-4o", agent_id=None, session_id="test"):
        self.name = name
        self.llm = model
        self.model = model  
        self.agent_id = agent_id or name
        self._session_id = session_id
        self.chat_history = []
    
    def chat(self, prompt, **kwargs):
        """Mock chat method that returns a simple response."""
        response = f"Response from {self.name} using {self.model}: {prompt[:50]}..."
        self.chat_history.append({"role": "user", "content": prompt})
        self.chat_history.append({"role": "assistant", "content": response})
        return response
    
    async def achat(self, prompt, **kwargs):
        """Mock async chat method."""
        return self.chat(prompt, **kwargs)


class TestHandoffRuntimeResolution:
    """Test handoff runtime resolution functionality."""
    
    def test_handoff_uses_turn_time_resolution(self):
        """Test that handoff uses turn-time runtime resolution instead of construction-time."""
        # Create agents with different models
        source_agent = MockAgent("SourceAgent", "gpt-3.5-turbo")
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        
        # Create handoff
        handoff = Handoff(
            agent=target_agent,
            config=HandoffConfig(context_policy=ContextPolicy.NONE)
        )
        
        # Mock the runtime resolution to verify it's called
        with patch.object(handoff, '_execute_with_runtime_resolution') as mock_execute:
            mock_execute.return_value = "Resolved response"
            
            # Execute programmatic handoff
            result = handoff.execute_programmatic(
                source_agent=source_agent,
                prompt="Test handoff",
                context={}
            )
            
            # Verify runtime resolution was called instead of direct agent.chat
            mock_execute.assert_called_once()
            args = mock_execute.call_args[0]
            assert args[0] == source_agent  # source_agent
            assert "Test handoff" in args[1]  # full_prompt with context
            assert args[3] == {}  # context kwargs
    
    @pytest.mark.asyncio
    async def test_async_handoff_uses_turn_time_resolution(self):
        """Test that async handoff uses turn-time runtime resolution."""
        source_agent = MockAgent("SourceAgent", "gpt-3.5-turbo") 
        target_agent = MockAgent("TargetAgent", "claude-3-sonnet")
        
        handoff = Handoff(
            agent=target_agent,
            config=HandoffConfig(context_policy=ContextPolicy.NONE)
        )
        
        # Mock the async runtime resolution
        with patch.object(handoff, '_execute_with_runtime_resolution_async') as mock_execute_async:
            mock_execute_async.return_value = "Async resolved response"
            
            # Execute async handoff
            result = await handoff.execute_async(
                source_agent=source_agent,
                prompt="Test async handoff", 
                context={}
            )
            
            # Verify async runtime resolution was called
            mock_execute_async.assert_called_once()
            args = mock_execute_async.call_args[0]
            assert args[0] == source_agent
            assert "Test async handoff" in args[1]
    
    def test_handoff_tool_function_uses_runtime_resolution(self):
        """Test that handoff tool function uses runtime resolution."""
        source_agent = MockAgent("SourceAgent", "gpt-4")
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        
        handoff = Handoff(
            agent=target_agent,
            config=HandoffConfig(context_policy=ContextPolicy.SUMMARY)
        )
        
        # Get tool function
        tool_func = handoff.to_tool_function(source_agent)
        
        # Mock the runtime resolution
        with patch.object(handoff, '_execute_with_runtime_resolution') as mock_execute:
            mock_execute.return_value = "Tool resolved response"
            
            # Execute tool function
            result = tool_func(task="Complete this task")
            
            # Verify runtime resolution was called
            mock_execute.assert_called_once()
            args = mock_execute.call_args[0]
            assert args[0] == source_agent
    
    @patch('praisonaiagents.runtime.resolve.resolve_runtime')
    def test_runtime_resolution_with_model_override(self, mock_resolve_runtime):
        """Test runtime resolution respects target agent's model."""
        # Setup mock runtime
        mock_runtime = Mock()
        mock_runtime.execute.return_value = "Runtime response"
        mock_runtime.provider = "openai"
        mock_runtime.model_ref = "gpt-4o"
        mock_resolve_runtime.return_value = mock_runtime
        
        source_agent = MockAgent("SourceAgent", "gpt-3.5-turbo")
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        
        handoff = Handoff(agent=target_agent)
        
        # Execute handoff runtime resolution directly
        response = handoff._execute_with_runtime_resolution(
            source_agent=source_agent,
            prompt="Test prompt",
            effective_tools=[],
            context={}
        )
        
        # Verify resolve_runtime was called with target agent's model
        mock_resolve_runtime.assert_called_once()
        args = mock_resolve_runtime.call_args[0]
        agent_id, model_ref, session_ctx = args
        
        assert agent_id == target_agent.agent_id
        assert model_ref == "gpt-4o"  # target agent's model
        assert isinstance(session_ctx, SessionContext)
        assert session_ctx.session_id == source_agent._session_id
        assert session_ctx.parent_agent_id == source_agent.name
        
        # Verify runtime was used for execution
        mock_runtime.execute.assert_called_once_with("Test prompt", tools=[])
        assert response == "Runtime response"
    
    @patch('praisonaiagents.runtime.resolve.resolve_runtime')
    @pytest.mark.asyncio 
    async def test_async_runtime_resolution_with_model_override(self, mock_resolve_runtime):
        """Test async runtime resolution respects target agent's model."""
        # Setup mock runtime
        mock_runtime = Mock()
        mock_runtime.aexecute.return_value = asyncio.Future()
        mock_runtime.aexecute.return_value.set_result("Async runtime response")
        mock_runtime.provider = "anthropic"
        mock_runtime.model_ref = "claude-3-sonnet"
        mock_resolve_runtime.return_value = mock_runtime
        
        source_agent = MockAgent("SourceAgent", "gpt-4")
        target_agent = MockAgent("TargetAgent", "claude-3-sonnet")
        
        handoff = Handoff(agent=target_agent)
        
        # Execute async handoff runtime resolution
        response = await handoff._execute_with_runtime_resolution_async(
            source_agent=source_agent,
            prompt="Test async prompt",
            effective_tools=[],
            context={}
        )
        
        # Verify resolve_runtime was called with target agent's model
        mock_resolve_runtime.assert_called_once()
        args = mock_resolve_runtime.call_args[0]
        agent_id, model_ref, session_ctx = args
        
        assert model_ref == "claude-3-sonnet"  # target agent's model
        assert session_ctx.handoff_depth > 0  # Should track handoff depth
        
        # Verify async runtime was used
        mock_runtime.aexecute.assert_called_once_with("Test async prompt", tools=[])
        assert response == "Async runtime response"
    
    def test_runtime_resolution_fallback_on_error(self):
        """Test fallback to agent.chat when runtime resolution fails."""
        source_agent = MockAgent("SourceAgent", "gpt-4")
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        
        handoff = Handoff(agent=target_agent)
        
        # Mock resolve_runtime to raise an exception
        with patch('praisonaiagents.runtime.resolve.resolve_runtime') as mock_resolve:
            mock_resolve.side_effect = Exception("Runtime resolution failed")
            
            # Execute should fallback to agent.chat
            response = handoff._execute_with_runtime_resolution(
                source_agent=source_agent,
                prompt="Test fallback",
                effective_tools=[],
                context={}
            )
            
            # Should get response from fallback (agent.chat)
            assert "Response from TargetAgent using gpt-4o" in response
            assert "Test fallback" in response
    
    @pytest.mark.asyncio
    async def test_async_runtime_resolution_fallback(self):
        """Test async fallback when runtime resolution fails."""
        source_agent = MockAgent("SourceAgent", "gpt-4")
        target_agent = MockAgent("TargetAgent", "claude-3-haiku")
        
        handoff = Handoff(agent=target_agent)
        
        # Mock resolve_runtime to raise an exception
        with patch('praisonaiagents.runtime.resolve.resolve_runtime') as mock_resolve:
            mock_resolve.side_effect = Exception("Async resolution failed")
            
            # Execute should fallback to agent async execution 
            response = await handoff._execute_with_runtime_resolution_async(
                source_agent=source_agent,
                prompt="Test async fallback",
                effective_tools=[], 
                context={}
            )
            
            # Should get response from fallback
            assert "Response from TargetAgent using claude-3-haiku" in response
    
    def test_session_context_creation_in_handoff(self):
        """Test that handoffs create proper session context."""
        source_agent = MockAgent("SourceAgent", "gpt-4", session_id="session_123")
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        
        handoff = Handoff(agent=target_agent)
        
        # Mock to capture SessionContext
        with patch('praisonaiagents.runtime.resolve.resolve_runtime') as mock_resolve:
            mock_runtime = Mock()
            mock_runtime.execute.return_value = "Test response"
            mock_resolve.return_value = mock_runtime
            
            # Simulate handoff depth
            with patch('praisonaiagents.agent.handoff._get_handoff_depth', return_value=2):
                handoff._execute_with_runtime_resolution(
                    source_agent=source_agent,
                    prompt="Test",
                    effective_tools=[],
                    context={}
                )
            
            # Verify SessionContext was created properly
            args = mock_resolve.call_args[0]
            session_ctx = args[2]
            
            assert session_ctx.session_id == "session_123"
            assert session_ctx.parent_agent_id == "SourceAgent" 
            assert session_ctx.handoff_depth == 2
            assert session_ctx.timestamp > 0


class TestConstructionVsTurnTimeRegression:
    """
    Regression tests for construction-time vs turn-time resolution.
    
    These tests specifically validate that the fix for issue #1938 works correctly.
    """
    
    def test_model_change_after_handoff_creation(self):
        """
        Test the core regression case: model change after handoff creation.
        
        Before fix: handoff would use construction-time model
        After fix: handoff should use turn-time model
        """
        source_agent = MockAgent("SourceAgent", "gpt-3.5-turbo")
        target_agent = MockAgent("TargetAgent", "gpt-4")
        
        # Create handoff with initial target model
        handoff = Handoff(agent=target_agent)
        
        # Target agent changes model (router decision, user preference, etc.)
        target_agent.llm = "gpt-4o"
        target_agent.model = "gpt-4o"
        
        # Mock runtime resolution to verify NEW model is used
        with patch('praisonaiagents.runtime.resolve.resolve_runtime') as mock_resolve:
            mock_runtime = Mock()
            mock_runtime.execute.return_value = "New model response"
            mock_resolve.return_value = mock_runtime
            
            # Execute handoff - should use NEW model (gpt-4o), not construction-time (gpt-4)
            handoff._execute_with_runtime_resolution(
                source_agent=source_agent,
                prompt="Test with new model",
                effective_tools=[],
                context={}
            )
            
            # Verify resolution was called with NEW model
            args = mock_resolve.call_args[0]
            model_ref = args[1]
            assert model_ref == "gpt-4o"  # NEW model, not gpt-4
    
    def test_sub_agent_tool_respects_current_model(self):
        """Test that as_tool() handoffs also respect turn-time model resolution."""
        parent_agent = MockAgent("ParentAgent", "gpt-4")
        sub_agent = MockAgent("SubAgent", "claude-3-sonnet")
        
        # Create sub-agent tool (as_tool() creates a Handoff internally)
        from ..execution_mixin import ExecutionMixin
        class TestAgent(MockAgent, ExecutionMixin):
            pass
        
        sub_agent_with_mixin = TestAgent("SubAgent", "claude-3-sonnet")
        sub_agent_tool = sub_agent_with_mixin.as_tool("Sub-agent for specialized tasks")
        
        # Sub-agent changes model after tool creation
        sub_agent_with_mixin.llm = "claude-3-opus"
        sub_agent_with_mixin.model = "claude-3-opus"
        
        # Mock runtime resolution 
        with patch.object(sub_agent_tool, '_execute_with_runtime_resolution') as mock_execute:
            mock_execute.return_value = "Sub-agent response"
            
            # Execute tool function
            tool_func = sub_agent_tool.to_tool_function(parent_agent)
            tool_func(task="Complete subtask")
            
            # Verify runtime resolution uses current model, not construction-time
            mock_execute.assert_called_once()
            # The handoff should resolve using sub_agent's current model (claude-3-opus)
            
    def test_multiple_handoffs_different_models(self):
        """Test multiple handoffs with different models work correctly."""
        source_agent = MockAgent("SourceAgent", "gpt-3.5-turbo")
        target_a = MockAgent("TargetA", "gpt-4o") 
        target_b = MockAgent("TargetB", "claude-3-sonnet")
        
        handoff_a = Handoff(agent=target_a)
        handoff_b = Handoff(agent=target_b)
        
        # Mock runtime resolution
        with patch('praisonaiagents.runtime.resolve.resolve_runtime') as mock_resolve:
            def mock_resolver(agent_id, model_ref, session_ctx):
                mock_runtime = Mock()
                mock_runtime.execute.return_value = f"Response for {model_ref}"
                mock_runtime.model_ref = model_ref
                return mock_runtime
            
            mock_resolve.side_effect = mock_resolver
            
            # Execute both handoffs
            response_a = handoff_a._execute_with_runtime_resolution(
                source_agent, "Task A", [], {}
            )
            response_b = handoff_b._execute_with_runtime_resolution(
                source_agent, "Task B", [], {}
            )
            
            # Verify each used the correct model
            assert "gpt-4o" in response_a
            assert "claude-3-sonnet" in response_b
            
            # Verify resolve_runtime was called with correct models
            assert mock_resolve.call_count == 2
            call_args = mock_resolve.call_args_list
            
            # Extract model_refs from calls
            models_used = {args[0][1] for args in call_args}
            assert models_used == {"gpt-4o", "claude-3-sonnet"}


# Run tests 
if __name__ == "__main__":
    pytest.main([__file__, "-v"])