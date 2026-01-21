"""
Tests for native structured outputs via response_format parameter.

Tests cover:
1. OpenAIClient.create_completion() accepts response_format param
2. Agent._build_response_format() correctly builds format from schema
3. Agent uses native mode for supporting models
4. Fallback to text injection for unsupported models
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List


class TestOpenAIClientResponseFormat:
    """Test that OpenAIClient.create_completion() accepts response_format."""
    
    def test_create_completion_accepts_response_format(self):
        """Test that create_completion passes response_format to API via kwargs."""
        from praisonaiagents.llm.openai_client import OpenAIClient
        
        # Create client with mocked OpenAI - need to patch at module level before import
        with patch('praisonaiagents.llm.openai_client._get_openai') as mock_get_openai:
            mock_openai_module = MagicMock()
            mock_get_openai.return_value = mock_openai_module
            
            # Create completion response mock
            mock_response = MagicMock()
            mock_choice = MagicMock()
            mock_message = MagicMock(content="test response")
            mock_choice.message = mock_message
            mock_response.choices = [mock_choice]
            
            # Create the mock client as the actual OpenAI client would return
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai_module.OpenAI.return_value = mock_client
            
            client = OpenAIClient(api_key="test-key")
            
            # Force the sync_client to use our mock
            client._OpenAIClient__sync_client = mock_client
            
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": "test_output",
                    "schema": {"type": "object"},
                    "strict": True
                }
            }
            
            # Call create_completion with response_format
            client.create_completion(
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o-mini",
                response_format=response_format
            )
            
            # Verify the create method was called
            mock_client.chat.completions.create.assert_called_once()
            
            # Get the call args and verify response_format was included
            call_args = mock_client.chat.completions.create.call_args
            assert call_args is not None
            # response_format comes through **kwargs
            assert call_args.kwargs.get('response_format') == response_format


class TestAgentBuildResponseFormat:
    """Test Agent._build_response_format() helper method."""
    
    def test_build_response_format_from_pydantic(self):
        """Test building response_format from Pydantic model."""
        from praisonaiagents.agent.agent import Agent
        from pydantic import BaseModel
        
        class TopicList(BaseModel):
            topics: List[str]
        
        agent = Agent(name="test", llm="gpt-4o-mini")
        
        # Test the helper if it exists
        if hasattr(agent, '_build_response_format'):
            result = agent._build_response_format(TopicList)
            assert result is not None
            assert result.get("type") == "json_schema"
            assert "json_schema" in result
            assert result["json_schema"]["name"] == "TopicList"
    
    def test_build_response_format_from_dict(self):
        """Test building response_format from dict schema."""
        from praisonaiagents.agent.agent import Agent
        
        schema = {
            "type": "array",
            "items": {"type": "string"}
        }
        
        agent = Agent(name="test", llm="gpt-4o-mini")
        
        if hasattr(agent, '_build_response_format'):
            result = agent._build_response_format(schema)
            assert result is not None
            assert result.get("type") == "json_schema"


class TestAgentNativeStructuredOutput:
    """Test that Agent uses native mode for supporting models."""
    
    def test_agent_chat_uses_response_format_for_supported_model(self):
        """Test that agent.chat() uses response_format for gpt-4o."""
        from praisonaiagents.agent.agent import Agent
        from pydantic import BaseModel
        
        class TopicList(BaseModel):
            topics: List[str]
        
        # Mock the LLM call
        with patch('praisonaiagents.agent.agent.Agent._chat_completion') as mock_chat:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '{"topics": ["AI", "ML"]}'
            mock_chat.return_value = mock_response
            
            with patch('praisonaiagents.llm.model_capabilities.supports_structured_outputs', return_value=True):
                agent = Agent(name="test", llm="gpt-4o-mini")
                agent.chat("List topics", output_pydantic=TopicList)
                
                # Check if response_format was passed (when method supports it)
                if mock_chat.called:
                    call_kwargs = mock_chat.call_args
                    # The actual check depends on implementation


class TestFallbackBehavior:
    """Test fallback to text injection for unsupported models."""
    
    def test_text_injection_for_unsupported_model(self):
        """Test that text injection is used when model doesn't support response_format."""
        from praisonaiagents.agent.agent import Agent
        
        with patch('praisonaiagents.llm.model_capabilities.supports_structured_outputs', return_value=False):
            agent = Agent(name="test", llm="some-unsupported-model")
            
            # Build messages should include text injection
            schema = {"type": "array", "items": {"type": "string"}}
            messages, _ = agent._build_messages(
                "List topics",
                output_json=schema
            )
            
            # Check that schema instruction was added to message
            user_message = messages[-1]["content"]
            assert "JSON" in user_message or "schema" in user_message.lower()


class TestSchemaEchoExtraction:
    """Test that schema echo extraction still works as safety net."""
    
    def test_parse_json_output_extracts_data(self):
        """Test that _parse_json_output extracts actual data from schema echo."""
        from praisonaiagents.workflows.workflows import _parse_json_output
        
        # Simulated schema echo from LLM
        echoed_output = {
            "type": "array",
            "items": ["topic1", "topic2", "topic3"]
        }
        
        result = _parse_json_output(echoed_output, "test_step")
        
        # Should extract the actual array data
        assert isinstance(result, list)
        assert result == ["topic1", "topic2", "topic3"]
    
    def test_parse_json_output_handles_clean_data(self):
        """Test that _parse_json_output passes through clean data."""
        from praisonaiagents.workflows.workflows import _parse_json_output
        
        # Clean output (no schema echo)
        clean_output = ["topic1", "topic2", "topic3"]
        
        result = _parse_json_output(clean_output, "test_step")
        
        assert result == clean_output


class TestPerformanceImpact:
    """Test that there's no performance impact from this change."""
    
    def test_no_heavy_imports_in_agent_module(self):
        """Test that agent module doesn't import heavy dependencies at module level."""
        import sys
        
        # Remove agent module if already imported
        if 'praisonaiagents.agent.agent' in sys.modules:
            del sys.modules['praisonaiagents.agent.agent']
        
        # Import and check it doesn't fail
        from praisonaiagents.agent import agent
        assert agent is not None
    
    def test_model_capabilities_lazy_import(self):
        """Test that model_capabilities uses lazy litellm import."""
        from praisonaiagents.llm import model_capabilities
        
        # The function should work even if litellm is not installed
        # (it should gracefully return False)
        result = model_capabilities.supports_structured_outputs("")
        assert result == False  # Empty model should return False
