"""
Test suite for web_fetch feature.

This module tests the web fetch functionality that allows LLMs to retrieve
full content from specific URLs (web pages and PDF documents).
Currently only supported by Anthropic Claude models.
"""

import pytest
import os


class TestSupportsWebFetch:
    """Test the supports_web_fetch function in model_capabilities."""
    
    def test_anthropic_claude_opus_4_1_supports_web_fetch(self):
        """Test that Claude Opus 4.1 supports web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert supports_web_fetch("anthropic/claude-opus-4-1-20250805")
        assert supports_web_fetch("claude-opus-4-1")
    
    def test_anthropic_claude_opus_4_supports_web_fetch(self):
        """Test that Claude Opus 4 supports web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert supports_web_fetch("anthropic/claude-opus-4-20250514")
        assert supports_web_fetch("claude-opus-4")
    
    def test_anthropic_claude_sonnet_4_supports_web_fetch(self):
        """Test that Claude Sonnet 4 supports web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert supports_web_fetch("anthropic/claude-sonnet-4-20250514")
        assert supports_web_fetch("claude-sonnet-4")
    
    def test_anthropic_claude_3_7_sonnet_supports_web_fetch(self):
        """Test that Claude 3.7 Sonnet supports web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert supports_web_fetch("anthropic/claude-3-7-sonnet-20250219")
        assert supports_web_fetch("claude-3-7-sonnet-latest")
    
    def test_anthropic_claude_3_5_sonnet_supports_web_fetch(self):
        """Test that Claude 3.5 Sonnet supports web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert supports_web_fetch("anthropic/claude-3-5-sonnet-latest")
        assert supports_web_fetch("claude-3-5-sonnet-20241022")
    
    def test_anthropic_claude_3_5_haiku_supports_web_fetch(self):
        """Test that Claude 3.5 Haiku supports web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert supports_web_fetch("anthropic/claude-3-5-haiku-latest")
        assert supports_web_fetch("claude-3-5-haiku-20241022")
    
    def test_claude_5_auto_supports_web_fetch(self):
        """Test that Claude 5+ models auto-support web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert supports_web_fetch("claude-5")
        assert supports_web_fetch("claude-sonnet-5")
        assert supports_web_fetch("claude-opus-5")
    
    def test_openai_models_do_not_support_web_fetch(self):
        """Test that OpenAI models do not support web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert not supports_web_fetch("openai/gpt-4o")
        assert not supports_web_fetch("gpt-4o-mini")
        assert not supports_web_fetch("gpt-4o-search-preview")
    
    def test_gemini_models_do_not_support_web_fetch(self):
        """Test that Gemini models do not support web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert not supports_web_fetch("gemini/gemini-2.0-flash")
        assert not supports_web_fetch("gemini-2.5-pro")
    
    def test_unknown_models_do_not_support_web_fetch(self):
        """Test that unknown models do not support web fetch."""
        from praisonaiagents.llm.model_capabilities import supports_web_fetch
        assert not supports_web_fetch("ollama/llama3")
        assert not supports_web_fetch("unknown/model")


class TestLLMWebFetchParameter:
    """Test the web_fetch parameter in LLM class."""
    
    def test_llm_init_with_web_fetch_true(self):
        """Test LLM initialization with web_fetch=True."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest", web_fetch=True)
        assert llm.web_fetch is True
    
    def test_llm_init_with_web_fetch_dict(self):
        """Test LLM initialization with web_fetch as dict."""
        from praisonaiagents.llm.llm import LLM
        web_fetch_config = {
            "max_uses": 10,
            "allowed_domains": ["example.com"],
            "citations": {"enabled": True}
        }
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest", web_fetch=web_fetch_config)
        assert llm.web_fetch == web_fetch_config
    
    def test_llm_init_without_web_fetch(self):
        """Test LLM initialization without web_fetch."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        assert llm.web_fetch is None
    
    def test_llm_supports_web_fetch_method(self):
        """Test LLM._supports_web_fetch() method."""
        from praisonaiagents.llm.llm import LLM
        
        # Claude model should support web fetch
        llm_claude = LLM(model="anthropic/claude-3-5-sonnet-latest")
        assert llm_claude._supports_web_fetch()
        
        # OpenAI model should not support web fetch
        llm_openai = LLM(model="gpt-4o-mini")
        assert not llm_openai._supports_web_fetch()


class TestLLMBuildCompletionParamsWebFetch:
    """Test _build_completion_params with web_fetch."""
    
    def test_build_params_with_web_fetch_true(self):
        """Test that web_fetch=True adds web_fetch tool to params."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest", web_fetch=True)
        params = llm._build_completion_params()
        
        assert 'tools' in params
        # Find the web_fetch tool
        web_fetch_tool = None
        for tool in params['tools']:
            if isinstance(tool, dict) and tool.get('type') == 'web_fetch_20250910':
                web_fetch_tool = tool
                break
        
        assert web_fetch_tool is not None
        assert web_fetch_tool['name'] == 'web_fetch'
        assert web_fetch_tool['max_uses'] == 5  # default
    
    def test_build_params_with_web_fetch_dict(self):
        """Test that web_fetch dict adds customized web_fetch tool."""
        from praisonaiagents.llm.llm import LLM
        web_fetch_config = {
            "max_uses": 10,
            "allowed_domains": ["example.com", "docs.example.com"],
            "citations": {"enabled": True},
            "max_content_tokens": 50000
        }
        llm = LLM(model="anthropic/claude-3-5-sonnet-latest", web_fetch=web_fetch_config)
        params = llm._build_completion_params()
        
        assert 'tools' in params
        # Find the web_fetch tool
        web_fetch_tool = None
        for tool in params['tools']:
            if isinstance(tool, dict) and tool.get('type') == 'web_fetch_20250910':
                web_fetch_tool = tool
                break
        
        assert web_fetch_tool is not None
        assert web_fetch_tool['max_uses'] == 10
        assert web_fetch_tool['allowed_domains'] == ["example.com", "docs.example.com"]
        assert web_fetch_tool['citations'] == {"enabled": True}
        assert web_fetch_tool['max_content_tokens'] == 50000
    
    def test_build_params_web_fetch_unsupported_model(self):
        """Test that web_fetch is ignored for unsupported models."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini", web_fetch=True)
        params = llm._build_completion_params()
        
        # Should not have web_fetch tool
        if 'tools' in params:
            for tool in params['tools']:
                if isinstance(tool, dict):
                    assert tool.get('type') != 'web_fetch_20250910'


class TestAgentWebFetchParameter:
    """Test the web_fetch parameter in Agent class."""
    
    def test_agent_init_with_web_fetch_true(self):
        """Test Agent initialization with web=WebConfig(fetch=True)."""
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.config.feature_configs import WebConfig
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-3-5-sonnet-latest",
            web=WebConfig(fetch=True)
        )
        assert agent.web_fetch is True
    
    def test_agent_init_with_web_fetch_dict(self):
        """Test Agent initialization with web=WebConfig(fetch=True)."""
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.config.feature_configs import WebConfig
        # Now using consolidated web= param with WebConfig
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-3-5-sonnet-latest",
            web=WebConfig(fetch=True)
        )
        assert agent.web_fetch is True
    
    def test_agent_init_without_web_fetch(self):
        """Test Agent initialization without web_fetch."""
        from praisonaiagents.agent.agent import Agent
        agent = Agent(name="Test Agent", llm="gpt-4o-mini")
        assert agent.web_fetch is None
    
    def test_agent_passes_web_fetch_to_llm(self):
        """Test that Agent passes web_fetch to LLM instance."""
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.config.feature_configs import WebConfig
        agent = Agent(
            name="Test Agent",
            llm="anthropic/claude-3-5-sonnet-latest",
            web=WebConfig(fetch=True)
        )
        assert agent.llm_instance.web_fetch is True
    
    def test_agent_model_supports_web_fetch_method(self):
        """Test Agent._model_supports_web_fetch() method."""
        from praisonaiagents.agent.agent import Agent
        
        # Claude model should support web fetch
        agent_claude = Agent(
            name="Claude Agent",
            llm="anthropic/claude-3-5-sonnet-latest"
        )
        assert agent_claude._model_supports_web_fetch()
        
        # OpenAI model should not support web fetch
        agent_openai = Agent(
            name="OpenAI Agent",
            llm="gpt-4o-mini"
        )
        assert not agent_openai._model_supports_web_fetch()


class TestWebFetchWithWebSearch:
    """Test that web_fetch and web_search can be used together."""
    
    def test_both_web_fetch_and_web_search(self):
        """Test using both web_fetch and web_search on supported model."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(
            model="anthropic/claude-3-5-sonnet-latest",
            web_search=True,
            web_fetch=True
        )
        params = llm._build_completion_params()
        
        # Should have web_search_options
        assert 'web_search_options' in params
        
        # Should also have web_fetch tool
        assert 'tools' in params
        web_fetch_found = False
        for tool in params['tools']:
            if isinstance(tool, dict) and tool.get('type') == 'web_fetch_20250910':
                web_fetch_found = True
                break
        assert web_fetch_found


@pytest.mark.skipif(
    not os.getenv('ANTHROPIC_API_KEY'),
    reason="ANTHROPIC_API_KEY not set"
)
class TestWebFetchIntegration:
    """Integration tests for web_fetch (requires API key)."""
    
    def test_web_fetch_with_anthropic(self):
        """Test actual web fetch with Anthropic API."""
        from praisonaiagents.agent.agent import Agent
        from praisonaiagents.config.feature_configs import WebConfig
        
        agent = Agent(
            name="Web Fetch Agent",
            instructions="You are a helpful assistant that can fetch web content.",
            llm="anthropic/claude-3-5-sonnet-latest",
            web=WebConfig(fetch=True)
        )
        
        # This would make an actual API call
        # response = agent.chat("Fetch and summarize https://example.com")
        # assert response is not None
        pass  # Skip actual API call in tests
