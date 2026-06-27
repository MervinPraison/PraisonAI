"""
Integration tests for handoff runtime resolution.

This test suite validates that handoffs now use turn-time runtime resolution
instead of construction-time pins, addressing issue #1938.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio

from praisonaiagents.agent.handoff import Handoff, HandoffConfig, ContextPolicy, HandoffResult


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
        source_agent.chat_history = [{"role": "user", "content": "Complete this task"}]
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
    
    @patch.object(MockAgent, 'chat')
    def test_runtime_resolution_uses_agent_chat(self, mock_chat):
        """Handoff must execute via agent.chat, not a bare LLM runtime."""
        mock_chat.return_value = "Agent chat response"
        source_agent = MockAgent("SourceAgent", "gpt-3.5-turbo")
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        
        handoff = Handoff(agent=target_agent)
        
        response = handoff._execute_with_runtime_resolution(
            source_agent=source_agent,
            prompt="Test prompt",
            effective_tools=[],
            context={}
        )
        
        mock_chat.assert_called_once_with("Test prompt", tools=[])
        assert response == "Agent chat response"
    
    @pytest.mark.asyncio
    async def test_async_runtime_resolution_uses_agent_achat(self):
        """Async handoff must execute via agent.achat, not a bare LLM runtime."""
        source_agent = MockAgent("SourceAgent", "gpt-4")
        target_agent = MockAgent("TargetAgent", "claude-3-sonnet")
        
        with patch.object(target_agent, 'achat', new_callable=AsyncMock) as mock_achat:
            mock_achat.return_value = "Async agent chat response"
            handoff = Handoff(agent=target_agent)
            
            response = await handoff._execute_with_runtime_resolution_async(
                source_agent=source_agent,
                prompt="Test async prompt",
                effective_tools=[],
                context={}
            )
            
            mock_achat.assert_called_once_with("Test async prompt", tools=[])
            assert response == "Async agent chat response"
    
    def test_runtime_resolution_uses_agent_chat_even_when_resolve_available(self):
        """Regression: bare resolve_runtime must not bypass agent instructions."""
        source_agent = MockAgent("SourceAgent", "gpt-4")
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        
        handoff = Handoff(agent=target_agent)
        
        with patch('praisonaiagents.runtime.resolve.resolve_runtime') as mock_resolve:
            mock_runtime = Mock()
            mock_runtime.execute.return_value = "Bare runtime response"
            mock_resolve.return_value = mock_runtime
            
            with patch.object(target_agent, 'chat', wraps=target_agent.chat) as mock_chat:
                response = handoff._execute_with_runtime_resolution(
                    source_agent=source_agent,
                    prompt="Test fallback",
                    effective_tools=[],
                    context={}
                )
                
                mock_resolve.assert_not_called()
                mock_runtime.execute.assert_not_called()
                mock_chat.assert_called_once()
                assert "Response from TargetAgent using gpt-4o" in response
    
    @pytest.mark.asyncio
    async def test_async_runtime_resolution_uses_agent_chat(self):
        """Async handoff should route through agent chat, not bare runtime."""
        source_agent = MockAgent("SourceAgent", "gpt-4")
        target_agent = MockAgent("TargetAgent", "claude-3-haiku")
        
        handoff = Handoff(agent=target_agent)
        
        with patch('praisonaiagents.runtime.resolve.resolve_runtime') as mock_resolve:
            mock_resolve.side_effect = Exception("Should not be called")
            
            response = await handoff._execute_with_runtime_resolution_async(
                source_agent=source_agent,
                prompt="Test async fallback",
                effective_tools=[], 
                context={}
            )
            
            mock_resolve.assert_not_called()
            assert "Response from TargetAgent using claude-3-haiku" in response
    
    def test_extract_model_ref_from_llm_object(self):
        """Model extraction should handle LLM objects, not pass them to resolvers."""
        source_agent = MockAgent("SourceAgent", "gpt-4")
        target_agent = MockAgent("TargetAgent", "gpt-4o")
        llm_object = Mock()
        llm_object.model = "claude-3-opus"
        target_agent.llm = llm_object
        
        handoff = Handoff(agent=target_agent)
        assert handoff._extract_model_ref(target_agent) == "claude-3-opus"


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
        
        with patch.object(target_agent, 'chat', wraps=target_agent.chat) as mock_chat:
            handoff._execute_with_runtime_resolution(
                source_agent=source_agent,
                prompt="Test with new model",
                effective_tools=[],
                context={}
            )
            
            mock_chat.assert_called_once()
            assert handoff._extract_model_ref(target_agent) == "gpt-4o"
    
    def test_sub_agent_tool_respects_current_model(self):
        """Test that as_tool() handoffs route through the target agent chat path."""
        parent_agent = MockAgent("ParentAgent", "gpt-4")
        parent_agent.chat_history = [{"role": "user", "content": "Complete subtask"}]
        sub_agent = MockAgent("SubAgent", "claude-3-sonnet")
        
        handoff = Handoff(agent=sub_agent)
        sub_agent.llm = "claude-3-opus"
        sub_agent.model = "claude-3-opus"
        
        with patch.object(sub_agent, 'chat', wraps=sub_agent.chat) as mock_chat:
            tool_func = handoff.to_tool_function(parent_agent)
            result = tool_func(task="Complete subtask")
            
            mock_chat.assert_called_once()
            assert "claude-3-opus" in result
            assert handoff._extract_model_ref(sub_agent) == "claude-3-opus"
            
    def test_multiple_handoffs_different_models(self):
        """Test multiple handoffs with different models work correctly."""
        source_agent = MockAgent("SourceAgent", "gpt-3.5-turbo")
        target_a = MockAgent("TargetA", "gpt-4o") 
        target_b = MockAgent("TargetB", "claude-3-sonnet")
        
        handoff_a = Handoff(agent=target_a)
        handoff_b = Handoff(agent=target_b)
        
        response_a = handoff_a._execute_with_runtime_resolution(
            source_agent, "Task A", [], {}
        )
        response_b = handoff_b._execute_with_runtime_resolution(
            source_agent, "Task B", [], {}
        )
        
        assert "gpt-4o" in response_a
        assert "claude-3-sonnet" in response_b
        assert handoff_a._extract_model_ref(target_a) == "gpt-4o"
        assert handoff_b._extract_model_ref(target_b) == "claude-3-sonnet"


# Run tests 
if __name__ == "__main__":
    pytest.main([__file__, "-v"])