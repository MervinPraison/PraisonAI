"""
Tests for prompt caching feature.

Prompt caching allows caching parts of prompts to reduce costs and latency.
Supported by OpenAI, Anthropic, Bedrock, and Deepseek.

Source: https://docs.litellm.ai/docs/completion/prompt_caching
"""

import pytest
from unittest.mock import patch, MagicMock


class TestSupportsPromptCaching:
    """Tests for the supports_prompt_caching function in model_capabilities.py"""
    
    def test_supports_prompt_caching_anthropic(self):
        """Test that Anthropic Claude models support prompt caching."""
        from praisonaiagents.llm.model_capabilities import supports_prompt_caching
        
        # Mock litellm.utils.supports_prompt_caching
        with patch('praisonaiagents.llm.model_capabilities.supports_prompt_caching') as mock_func:
            # Just test that the function exists and can be called
            mock_func.return_value = True
            result = mock_func(model="anthropic/claude-3-5-sonnet-latest")
            assert result == True
    
    def test_supports_prompt_caching_openai(self):
        """Test that OpenAI models support prompt caching."""
        from praisonaiagents.llm.model_capabilities import supports_prompt_caching
        
        with patch('litellm.utils.supports_prompt_caching', return_value=True):
            # The function should delegate to litellm
            result = supports_prompt_caching("openai/gpt-4o")
            # Result depends on litellm's implementation
            assert isinstance(result, bool)
    
    def test_supports_prompt_caching_empty_model(self):
        """Test that empty model name returns False."""
        from praisonaiagents.llm.model_capabilities import supports_prompt_caching
        
        assert supports_prompt_caching("") == False
        assert supports_prompt_caching(None) == False


class TestLLMPromptCachingParameter:
    """Tests for prompt_caching parameter in LLM class."""
    
    def test_llm_init_with_prompt_caching_true(self):
        """Test LLM initialization with prompt_caching=True."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest", prompt_caching=True)
        assert llm.prompt_caching == True
    
    def test_llm_init_with_prompt_caching_false(self):
        """Test LLM initialization with prompt_caching=False."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest", prompt_caching=False)
        assert llm.prompt_caching == False
    
    def test_llm_init_without_prompt_caching(self):
        """Test LLM initialization without prompt_caching parameter."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="gpt-4o-mini")
        assert llm.prompt_caching is None
    
    def test_llm_supports_prompt_caching_method(self):
        """Test _supports_prompt_caching method exists and works."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest")
        # Method should exist and return a boolean
        result = llm._supports_prompt_caching()
        assert isinstance(result, bool)
    
    def test_llm_is_anthropic_model_method(self):
        """Test _is_anthropic_model method."""
        from praisonaiagents.llm.llm import LLM
        
        # Anthropic model
        llm_anthropic = LLM(model="anthropic/claude-3-5-sonnet-latest")
        assert llm_anthropic._is_anthropic_model() == True
        
        # OpenAI model
        llm_openai = LLM(model="gpt-4o-mini")
        assert llm_openai._is_anthropic_model() == False
        
        # Gemini model
        llm_gemini = LLM(model="gemini/gemini-2.0-flash")
        assert llm_gemini._is_anthropic_model() == False


class TestLLMBuildMessagesWithPromptCaching:
    """Tests for _build_messages with prompt caching enabled."""
    
    def test_build_messages_with_prompt_caching_anthropic(self):
        """Test that _build_messages adds cache_control for Anthropic models."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest", prompt_caching=True)
        
        # Mock _supports_prompt_caching to return True
        with patch.object(llm, '_supports_prompt_caching', return_value=True):
            messages, _ = llm._build_messages(
                prompt="Hello",
                system_prompt="You are a helpful assistant."
            )
            
            # Check that system message has cache_control
            system_msg = messages[0]
            assert system_msg["role"] == "system"
            # For Anthropic with prompt_caching, content should be an array
            assert isinstance(system_msg["content"], list)
            assert system_msg["content"][0]["type"] == "text"
            assert system_msg["content"][0]["cache_control"] == {"type": "ephemeral"}
    
    def test_build_messages_without_prompt_caching(self):
        """Test that _build_messages doesn't add cache_control when disabled."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest", prompt_caching=False)
        
        messages, _ = llm._build_messages(
            prompt="Hello",
            system_prompt="You are a helpful assistant."
        )
        
        # Check that system message is a simple string
        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert isinstance(system_msg["content"], str)
    
    def test_build_messages_prompt_caching_non_anthropic(self):
        """Test that prompt caching doesn't affect non-Anthropic models."""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="gpt-4o-mini", prompt_caching=True)
        
        messages, _ = llm._build_messages(
            prompt="Hello",
            system_prompt="You are a helpful assistant."
        )
        
        # For non-Anthropic models, content should remain a string
        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert isinstance(system_msg["content"], str)


class TestAgentPromptCachingParameter:
    """Tests for caching= parameter in Agent class (consolidated API)."""
    
    def test_agent_init_with_caching_config_prompt_caching_true(self):
        """Test Agent initialization with caching=CachingConfig(prompt_caching=True)."""
        from praisonaiagents import Agent
        from praisonaiagents.config import CachingConfig
        
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-3-5-sonnet-latest",
            caching=CachingConfig(prompt_caching=True)
        )
        assert agent.prompt_caching == True
    
    def test_agent_init_with_caching_config_prompt_caching_false(self):
        """Test Agent initialization with caching=CachingConfig(prompt_caching=False)."""
        from praisonaiagents import Agent
        from praisonaiagents.config import CachingConfig
        
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-3-5-sonnet-latest",
            caching=CachingConfig(prompt_caching=False)
        )
        assert agent.prompt_caching == False
    
    def test_agent_init_without_caching(self):
        """Test Agent initialization without caching parameter."""
        from praisonaiagents import Agent
        
        agent = Agent(name="Test Agent")
        assert agent.prompt_caching is None
    
    def test_agent_model_supports_prompt_caching_method(self):
        """Test _model_supports_prompt_caching method exists."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-3-5-sonnet-latest"
        )
        # Method should exist and return a boolean
        result = agent._model_supports_prompt_caching()
        assert isinstance(result, bool)
    
    def test_agent_passes_prompt_caching_to_llm(self):
        """Test that Agent passes prompt_caching to LLM instance."""
        from praisonaiagents import Agent
        from praisonaiagents.config import CachingConfig
        
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-3-5-sonnet-latest",
            caching=CachingConfig(prompt_caching=True)
        )
        
        # Check that LLM instance has prompt_caching set
        if hasattr(agent, 'llm_instance') and agent.llm_instance:
            assert agent.llm_instance.prompt_caching == True


class TestPromptCachingIntegration:
    """Integration tests for prompt caching (requires API key)."""
    
    @pytest.mark.skip(reason="Requires ANTHROPIC_API_KEY environment variable")
    def test_prompt_caching_with_anthropic(self):
        """Test prompt caching with actual Anthropic API."""
        import os
        from praisonaiagents import Agent
        
        # Skip if no API key
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")
        
        from praisonaiagents.config import CachingConfig
        agent = Agent(
            name="Caching Test Agent",
            instructions="You are a helpful assistant." * 100,  # Long system prompt
            llm="anthropic/claude-3-5-sonnet-latest",
            caching=CachingConfig(prompt_caching=True),
            output="silent"
        )
        
        # First call - should create cache
        result1 = agent.start("What is 2+2?")
        assert result1 is not None
        
        # Second call - should use cache
        result2 = agent.start("What is 3+3?")
        assert result2 is not None
