"""
End-to-end integration test for LLM_SUMMARIZE compaction strategy.

This test demonstrates the full functionality of LLM-based context compaction
with a real agent in a conversation that exceeds token limits.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from praisonaiagents.agent import Agent
from praisonaiagents.config.feature_configs import ExecutionConfig
from praisonaiagents.compaction.strategy import CompactionStrategy


class TestLLMSummarizeCompactionE2E:
    """End-to-end tests for LLM_SUMMARIZE compaction strategy."""

    @pytest.mark.asyncio
    async def test_agent_llm_summarize_compaction_real(self):
        """Test real agent with LLM_SUMMARIZE compaction."""
        # Create agent with LLM_SUMMARIZE compaction strategy
        execution_config = ExecutionConfig(
            context_compaction=True,
            max_context_tokens=50,  # Very low to trigger compaction
            compaction_strategy=CompactionStrategy.LLM_SUMMARIZE
        )
        
        agent = Agent(
            name="test_agent",
            instructions="You are a helpful assistant.",
            llm="openai:gpt-4o-mini",  # Use cheap model for testing
            execution=execution_config
        )
        
        # Mock the LLM response for summarization to avoid real API calls in tests
        mock_summary_response = "Previous conversation: User asked about weather, assistant explained lacking weather data access."
        
        with patch.object(agent, '_execute_unified_achat_completion', new_callable=AsyncMock) as mock_unified_chat:
            # Set up mock to return different responses for different calls
            mock_unified_chat.side_effect = [
                {"choices": [{"message": {"content": mock_summary_response}}]},  # Summarization call
                {"choices": [{"message": {"content": "I can help you with that!"}}]}  # Actual response
            ]
            
            # Mock the response content extraction to work with our mock
            with patch.object(agent, '_extract_llm_response_content') as mock_extract:
                mock_extract.side_effect = [mock_summary_response, "I can help you with that!"]
                
                # Fill up the conversation with enough content to trigger compaction
                long_conversation = [
                    {"role": "user", "content": "What's the weather like today? This is a long question with lots of details about the weather and climate and seasonal patterns."},
                    {"role": "assistant", "content": "I don't have access to current weather data. This is a long response explaining weather services and how to check weather."},
                    {"role": "user", "content": "Can you tell me about climate change? This is another long message about environmental concerns and global warming trends."},
                    {"role": "assistant", "content": "Climate change is a complex topic involving global temperature changes due to greenhouse gas emissions and human activities."},
                    {"role": "user", "content": "What about renewable energy? Solar panels, wind turbines, and other sustainable energy sources are important for the future."},
                ]
                
                # Add messages to agent's chat history to simulate a long conversation
                agent._chat_history = long_conversation.copy()
                
                # Make a new request that should trigger compaction
                response = await agent.achat("Can you help me understand machine learning? I'm particularly interested in neural networks and deep learning algorithms.")
                
                # Verify that the response was generated
                assert response is not None
                assert "I can help you with that!" in str(response)
                
                # Verify that the unified chat was called twice (once for summarization, once for actual response)
                assert mock_unified_chat.call_count == 2
                
                # Check the first call was for summarization
                first_call_args = mock_unified_chat.call_args_list[0]
                assert len(first_call_args[1]["messages"]) == 1  # Should be just the summarization prompt
                assert "Summarise the following conversation" in first_call_args[1]["messages"][0]["content"]
                
                # Check that temperature was lowered for summarization
                assert first_call_args[1]["temperature"] == 0.3
                
                # Check the second call was for the actual response
                second_call_args = mock_unified_chat.call_args_list[1]
                actual_messages = second_call_args[1]["messages"]
                
                # Should have system message, summary, and user's new question
                assert len(actual_messages) >= 2
                
                # Check that a summary message was inserted
                summary_found = False
                for msg in actual_messages:
                    if msg.get("role") == "system" and msg.get("_llm_generated"):
                        summary_found = True
                        assert "Previous conversation" in msg["content"]
                        break
                
                assert summary_found, "LLM-generated summary message not found"

    @pytest.mark.asyncio
    async def test_agent_llm_summarize_compaction_fallback(self):
        """Test agent with LLM_SUMMARIZE compaction when summarization fails."""
        execution_config = ExecutionConfig(
            context_compaction=True,
            max_context_tokens=50,
            compaction_strategy=CompactionStrategy.LLM_SUMMARIZE
        )
        
        agent = Agent(
            name="test_agent",
            instructions="You are a helpful assistant.",
            llm="openai:gpt-4o-mini",
            execution=execution_config
        )
        
        # Mock the summarization to fail, but main chat to succeed
        with patch.object(agent, '_execute_unified_achat_completion', new_callable=AsyncMock) as mock_unified_chat:
            # First call (summarization) fails, second call (actual response) succeeds
            mock_unified_chat.side_effect = [
                Exception("API error during summarization"),
                {"choices": [{"message": {"content": "I'm working despite the summarization failure!"}}]}
            ]
            
            with patch.object(agent, '_extract_llm_response_content') as mock_extract:
                mock_extract.return_value = "I'm working despite the summarization failure!"
                
                # Fill up conversation history
                agent._chat_history = [
                    {"role": "user", "content": "This is a very long conversation that should trigger compaction when we exceed the token limit."},
                    {"role": "assistant", "content": "This is a long response that adds to the token count and should be compacted."},
                    {"role": "user", "content": "More conversation content to ensure we exceed the token limit."},
                ] * 3  # Repeat to ensure token limit is exceeded
                
                # Should not crash despite summarization failure
                response = await agent.achat("New question")
                
                assert response is not None
                assert "I'm working despite the summarization failure!" in str(response)
                
                # Should have called summarization once (failed) and then the actual response
                assert mock_unified_chat.call_count == 2

    def test_agent_llm_summarize_sync_chat(self):
        """Test sync chat with LLM_SUMMARIZE compaction strategy."""
        execution_config = ExecutionConfig(
            context_compaction=True,
            max_context_tokens=50,
            compaction_strategy=CompactionStrategy.LLM_SUMMARIZE
        )
        
        agent = Agent(
            name="test_agent",
            instructions="You are a helpful assistant.",
            llm="openai:gpt-4o-mini",
            execution=execution_config
        )
        
        # Mock the LLM calls
        with patch.object(agent, '_chat_completion') as mock_chat:
            mock_chat.return_value = "Sync response with compaction"
            
            # Fill up conversation history to trigger compaction
            agent._chat_history = [
                {"role": "user", "content": "Long message content that exceeds token limits when combined with other messages."},
                {"role": "assistant", "content": "Long assistant response that adds to the total token count significantly."},
            ] * 5
            
            # Should use sync compaction (falls back to naive summarization for LLM_SUMMARIZE in sync mode)
            response = agent.chat("Test question")
            
            assert response is not None
            assert "Sync response with compaction" == response

    @pytest.mark.asyncio 
    async def test_execution_config_compaction_strategy_integration(self):
        """Test that ExecutionConfig.compaction_strategy integrates properly with agent."""
        # Test with None strategy (default)
        config_none = ExecutionConfig(context_compaction=True)
        assert config_none.compaction_strategy is None
        
        # Test with LLM_SUMMARIZE strategy  
        config_llm = ExecutionConfig(
            context_compaction=True,
            compaction_strategy=CompactionStrategy.LLM_SUMMARIZE
        )
        assert config_llm.compaction_strategy == CompactionStrategy.LLM_SUMMARIZE
        
        # Test serialization
        data = config_llm.to_dict()
        assert data["context_compaction"] is True
        assert data["compaction_strategy"] == "llm_summarize"
        
        # Test that agent accepts the config
        agent = Agent(
            instructions="Test agent",
            llm="openai:gpt-4o-mini",
            execution=config_llm
        )
        
        assert hasattr(agent, 'execution')
        assert agent.execution.compaction_strategy == CompactionStrategy.LLM_SUMMARIZE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])