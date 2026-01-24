"""
Test file for web_search feature (TDD approach).

Tests the LiteLLM native web search integration with fallback to DuckDuckGo.
"""

import pytest
import os
from unittest.mock import patch


class TestWebSearchSupport:
    """Test web search capability detection."""
    
    def test_supports_web_search_openai_search_preview(self):
        """Test that gpt-4o-search-preview is detected as supporting web search."""
        from praisonaiagents.llm.model_capabilities import supports_web_search
        assert supports_web_search("openai/gpt-4o-search-preview") == True
    
    def test_supports_web_search_xai_grok(self):
        """Test that xai/grok-3 is detected as supporting web search."""
        from praisonaiagents.llm.model_capabilities import supports_web_search
        assert supports_web_search("xai/grok-3") == True
    
    def test_supports_web_search_anthropic_claude(self):
        """Test that claude-3-5-sonnet-latest is detected as supporting web search."""
        from praisonaiagents.llm.model_capabilities import supports_web_search
        assert supports_web_search("anthropic/claude-3-5-sonnet-latest") == True
    
    def test_supports_web_search_gemini(self):
        """Test that gemini-2.0-flash is detected as supporting web search."""
        from praisonaiagents.llm.model_capabilities import supports_web_search
        assert supports_web_search("gemini-2.0-flash") == True
    
    def test_supports_web_search_ollama_false(self):
        """Test that ollama models don't support native web search."""
        from praisonaiagents.llm.model_capabilities import supports_web_search
        assert supports_web_search("ollama/llama3") == False
    
    def test_supports_web_search_unknown_model(self):
        """Test that unknown models default to False."""
        from praisonaiagents.llm.model_capabilities import supports_web_search
        assert supports_web_search("unknown/model") == False


class TestLLMWebSearchParameter:
    """Test LLM class web_search parameter."""
    
    def test_llm_init_with_web_search_true(self):
        """Test LLM initialization with web_search=True."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini", web_search=True)
        assert llm.web_search == True
    
    def test_llm_init_with_web_search_dict(self):
        """Test LLM initialization with web_search as dict."""
        from praisonaiagents.llm.llm import LLM
        web_search_options = {"search_context_size": "high"}
        llm = LLM(model="gpt-4o-mini", web_search=web_search_options)
        assert llm.web_search == web_search_options
    
    def test_llm_init_with_web_search_false(self):
        """Test LLM initialization with web_search=False."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini", web_search=False)
        assert llm.web_search == False
    
    def test_llm_init_without_web_search(self):
        """Test LLM initialization without web_search (default None)."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        assert llm.web_search is None
    
    def test_llm_supports_web_search_method(self):
        """Test LLM._supports_web_search() method."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="openai/gpt-4o-search-preview")
        assert llm._supports_web_search() == True
    
    def test_llm_supports_web_search_method_ollama(self):
        """Test LLM._supports_web_search() returns False for Ollama."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="ollama/llama3")
        assert llm._supports_web_search() == False


class TestLLMBuildCompletionParams:
    """Test _build_completion_params includes web_search_options."""
    
    def test_build_params_with_web_search_true(self):
        """Test that web_search=True adds web_search_options to params."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="openai/gpt-4o-search-preview", web_search=True)
        
        with patch.object(llm, '_supports_web_search', return_value=True):
            params = llm._build_completion_params(messages=[{"role": "user", "content": "test"}])
            assert "web_search_options" in params
            assert params["web_search_options"] == {"search_context_size": "medium"}
    
    def test_build_params_with_web_search_dict(self):
        """Test that web_search dict is passed correctly."""
        from praisonaiagents.llm.llm import LLM
        web_search_options = {"search_context_size": "high"}
        llm = LLM(model="openai/gpt-4o-search-preview", web_search=web_search_options)
        
        with patch.object(llm, '_supports_web_search', return_value=True):
            params = llm._build_completion_params(messages=[{"role": "user", "content": "test"}])
            assert "web_search_options" in params
            assert params["web_search_options"] == {"search_context_size": "high"}
    
    def test_build_params_without_web_search(self):
        """Test that web_search_options is not added when web_search is None."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        params = llm._build_completion_params(messages=[{"role": "user", "content": "test"}])
        assert "web_search_options" not in params
    
    def test_build_params_web_search_unsupported_model(self):
        """Test that web_search_options is not added for unsupported models."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="ollama/llama3", web_search=True)
        
        with patch.object(llm, '_supports_web_search', return_value=False):
            params = llm._build_completion_params(messages=[{"role": "user", "content": "test"}])
            assert "web_search_options" not in params


class TestAgentWebSearchParameter:
    """Test Agent class web= parameter (consolidated API)."""
    
    def test_agent_init_with_web_search(self):
        """Test Agent initialization with web=WebConfig(search=True, fetch=False)."""
        from praisonaiagents import Agent
        from praisonaiagents.config import WebConfig
        agent = Agent(
            name="Test Agent",
            instructions="Test",
            web=WebConfig(search=True, fetch=False)
        )
        assert agent.web_search == True
    
    def test_agent_init_with_web_config_search_only(self):
        """Test Agent initialization with WebConfig search only."""
        from praisonaiagents import Agent
        from praisonaiagents.config import WebConfig
        agent = Agent(
            name="Test Agent",
            instructions="Test",
            web=WebConfig(search=True, fetch=False)
        )
        assert agent.web_search == True
    
    def test_agent_init_without_web(self):
        """Test Agent initialization without web (default None)."""
        from praisonaiagents import Agent
        agent = Agent(
            name="Test Agent",
            instructions="Test"
        )
        assert agent.web_search is None
    
    def test_agent_with_custom_llm_passes_web_search(self):
        """Test that Agent passes web_search to custom LLM instance."""
        from praisonaiagents import Agent
        from praisonaiagents.config import WebConfig
        agent = Agent(
            name="Test Agent",
            instructions="Test",
            llm="openai/gpt-4o-search-preview",
            web=WebConfig(search=True, fetch=False)
        )
        # When using custom LLM (with /), it creates llm_instance
        assert hasattr(agent, 'llm_instance')
        assert agent.llm_instance.web_search == True


class TestWebSearchFallback:
    """Test fallback to DuckDuckGo when native web search not supported."""
    
    def test_fallback_tool_injection_for_unsupported_model(self):
        """Test that DuckDuckGo tool is injected for unsupported models."""
        from praisonaiagents import Agent
        from praisonaiagents.config import WebConfig
        agent = Agent(
            name="Test Agent",
            instructions="Test",
            llm="ollama/llama3",
            web=WebConfig(search=True, fetch=False)
        )
        # Check that internet_search tool was added to tools
        tool_names = [getattr(t, '__name__', str(t)) for t in agent.tools]
        assert 'internet_search' in tool_names or 'duckduckgo' in tool_names
    
    def test_no_fallback_for_supported_model(self):
        """Test that no fallback tool is added for supported models."""
        from praisonaiagents import Agent
        from praisonaiagents.config import WebConfig
        agent = Agent(
            name="Test Agent",
            instructions="Test",
            llm="openai/gpt-4o-search-preview",
            web=WebConfig(search=True, fetch=False),
            tools=[]  # Explicitly empty tools
        )
        # For supported models, tools should remain empty (native web search used)
        # Only check if no DuckDuckGo tool was auto-added
        tool_names = [getattr(t, '__name__', str(t)) for t in agent.tools]
        # internet_search should NOT be auto-added for supported models
        assert 'internet_search' not in tool_names


class TestDuckDuckGoToolPreservation:
    """Test that DuckDuckGo tools still work as before."""
    
    def test_duckduckgo_import(self):
        """Test that DuckDuckGo tools can still be imported."""
        from praisonaiagents.tools import internet_search, duckduckgo
        assert callable(internet_search)
        assert callable(duckduckgo)
    
    def test_explicit_duckduckgo_tool_usage(self):
        """Test that explicit DuckDuckGo tool usage still works."""
        from praisonaiagents import Agent
        from praisonaiagents.tools import internet_search
        
        agent = Agent(
            name="Test Agent",
            instructions="Test",
            tools=[internet_search]
        )
        assert internet_search in agent.tools


class TestWebSearchIntegration:
    """Integration tests for web search (requires API keys)."""
    
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set"
    )
    def test_web_search_with_openai(self):
        """Test actual web search with OpenAI (integration test)."""
        from praisonaiagents import Agent
        from praisonaiagents.config import WebConfig
        
        agent = Agent(
            name="Researcher",
            instructions="You are a helpful research assistant.",
            llm="openai/gpt-4o-search-preview",
            web=WebConfig(search=True, fetch=False)
        )
        
        result = agent.start("What is the current weather in San Francisco?")
        assert result is not None
        assert len(result) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
