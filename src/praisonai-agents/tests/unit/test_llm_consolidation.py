"""
Tests for LLM parameter consolidation.

TDD: These tests define the expected behavior for:
1. Agent accepts `llm=` consolidated usage (new)
2. Agent accepts `model=` alias (new)
3. Agent rejects `llm_config=` and `function_calling_llm=` (removed in v4)
4. base_url/api_key remain separate and unchanged
5. No deprecation warnings for valid params
"""
import pytest
import warnings


class TestLLMConsolidation:
    """Tests for LLM parameter consolidation in Agent."""
    
    def test_agent_accepts_llm_string(self):
        """Agent accepts llm= as a string model name."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            llm="gpt-4o-mini"
        )
        assert agent.llm == "gpt-4o-mini"
    
    def test_agent_accepts_model_alias(self):
        """Agent accepts model= as an alias for llm=."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent",
            model="gpt-4o-mini"
        )
        # model= should behave identically to llm=
        assert agent.llm == "gpt-4o-mini"
    
    def test_model_and_llm_are_equivalent(self):
        """model= and llm= produce identical agents."""
        from praisonaiagents import Agent
        
        agent1 = Agent(instructions="Test", llm="gpt-4o")
        agent2 = Agent(instructions="Test", model="gpt-4o")
        
        assert agent1.llm == agent2.llm
    
    def test_llm_takes_precedence_over_model(self):
        """If both llm= and model= are provided, llm= takes precedence."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test",
            llm="gpt-4o",
            model="gpt-3.5-turbo"  # Should be ignored
        )
        assert agent.llm == "gpt-4o"
    
    def test_llm_config_removed_in_v4(self):
        """llm_config= is removed in v4 - should raise TypeError."""
        from praisonaiagents import Agent
        
        with pytest.raises(TypeError) as exc_info:
            agent = Agent(
                instructions="Test",
                llm_config={"temperature": 0.7}
            )
        assert 'llm_config' in str(exc_info.value)
    
    def test_function_calling_llm_removed_in_v4(self):
        """function_calling_llm= is removed in v4 - should raise TypeError."""
        from praisonaiagents import Agent
        
        with pytest.raises(TypeError) as exc_info:
            agent = Agent(
                instructions="Test",
                function_calling_llm="gpt-4o-mini"
            )
        assert 'function_calling_llm' in str(exc_info.value)
    
    def test_base_url_remains_separate(self):
        """base_url= remains a separate parameter, not consolidated."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test",
            llm="gpt-4o",
            base_url="https://custom.api.com/v1"
        )
        assert agent.base_url == "https://custom.api.com/v1"
    
    def test_api_key_remains_separate(self):
        """api_key= remains a separate parameter, not consolidated."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test",
            llm="gpt-4o",
            api_key="sk-test-key"
        )
        assert agent.api_key == "sk-test-key"
    
    def test_no_deprecation_warning_on_normal_path(self):
        """No deprecation warnings when using only new consolidated params."""
        from praisonaiagents import Agent
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            agent = Agent(
                instructions="Test",
                llm="gpt-4o",
                base_url="https://api.openai.com/v1",
                api_key="sk-test"
            )
            # Should NOT emit deprecation warnings for llm/base_url/api_key
            deprecation_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            llm_related = [x for x in deprecation_warnings 
                         if "llm_config" in str(x.message).lower() 
                         or "function_calling_llm" in str(x.message).lower()]
            assert len(llm_related) == 0


class TestWebFetchGating:
    """Tests for web_fetch gating (Claude-only)."""
    
    def test_non_claude_model_with_web_fetch_raises_error(self):
        """Non-Claude model + web fetch requested → error."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import WebConfig
        
        # This should raise an error or warning when fetch is explicitly requested
        with pytest.raises((ValueError, RuntimeError)) as exc_info:
            agent = Agent(
                instructions="Test",
                llm="gpt-4o",  # OpenAI model - does NOT support fetch
                web=WebConfig(fetch=True)  # Explicitly request fetch
            )
            # Force initialization to trigger the check
            _ = agent.web
        
        assert "fetch" in str(exc_info.value).lower() or "claude" in str(exc_info.value).lower()
    
    def test_claude_model_with_web_fetch_allowed(self):
        """Claude model + web fetch requested → allowed."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import WebConfig
        
        # This should work without error
        agent = Agent(
            instructions="Test",
            llm="anthropic/claude-sonnet-4",  # Claude model - supports fetch
            web=WebConfig(fetch=True)
        )
        # Should not raise
        assert agent is not None
    
    def test_web_enabled_without_fetch_works_on_any_model(self):
        """web enabled with search only (no fetch) works on any model."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import WebConfig
        
        # Web search (not fetch) should work on any model that supports it
        agent = Agent(
            instructions="Test",
            llm="gpt-4o-search-preview",  # OpenAI search model
            web=WebConfig(search=True, fetch=False)  # Explicitly disable fetch
        )
        # Should not raise - web search is allowed
        assert agent is not None
    
    def test_web_fetch_false_on_non_claude_no_error(self):
        """web=True with fetch=False on non-Claude should not error."""
        from praisonaiagents import Agent
        from praisonaiagents.config.feature_configs import WebConfig
        
        agent = Agent(
            instructions="Test",
            llm="gpt-4o",
            web=WebConfig(search=True, fetch=False)  # Explicitly disable fetch
        )
        assert agent is not None


class TestWrapperAgentConsolidation:
    """Tests for wrapper agents using consolidated params."""
    
    def test_prompt_expander_accepts_model_param(self):
        """PromptExpanderAgent accepts model= parameter."""
        from praisonaiagents.agent.prompt_expander_agent import PromptExpanderAgent
        
        agent = PromptExpanderAgent(model="gpt-4o-mini")
        # PromptExpanderAgent stores model in self.model attribute
        assert agent.model == "gpt-4o-mini"
    
    def test_prompt_expander_model_is_used(self):
        """PromptExpanderAgent uses the model parameter correctly."""
        from praisonaiagents.agent.prompt_expander_agent import PromptExpanderAgent
        
        # Should accept model= parameter without error
        agent = PromptExpanderAgent(model="gpt-4o-mini")
        assert agent is not None
        assert agent.model == "gpt-4o-mini"
    
    def test_query_rewriter_accepts_model_param(self):
        """QueryRewriterAgent accepts model= parameter."""
        from praisonaiagents.agent.query_rewriter_agent import QueryRewriterAgent
        
        agent = QueryRewriterAgent(model="gpt-4o-mini")
        assert agent.model == "gpt-4o-mini"
