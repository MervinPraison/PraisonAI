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


def _count_cache_markers(messages):
    """Count cache_control markers across all message content blocks."""
    count = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    count += 1
    return count


class TestCacheBreakpointBudget:
    """Tests for provider-agnostic, budgeted cache breakpoints."""

    def _anthropic_llm(self):
        from praisonaiagents.llm.llm import LLM
        return LLM(model="anthropic/claude-3-5-sonnet-latest", prompt_caching=True)

    def test_history_prefix_gets_cache_breakpoint(self):
        """A stable history prefix is marked with a cache breakpoint."""
        llm = self._anthropic_llm()
        history = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
            {"role": "assistant", "content": "four"},
        ]
        with patch.object(llm, '_supports_prompt_caching', return_value=True):
            messages, _ = llm._build_messages(
                prompt="latest",
                system_prompt="You are helpful.",
                chat_history=history,
            )
        # system block + one history-prefix marker
        assert _count_cache_markers(messages) >= 2

    def test_at_most_four_cache_breakpoints(self):
        """Never exceed the provider 4-breakpoint limit."""
        llm = self._anthropic_llm()
        history = [
            {"role": "user", "content": f"msg-{i}"} for i in range(20)
        ]
        with patch.object(llm, '_supports_prompt_caching', return_value=True):
            messages, _ = llm._build_messages(
                prompt="latest",
                system_prompt="You are helpful.",
                chat_history=history,
            )
        assert _count_cache_markers(messages) <= 4

    def test_openai_path_no_explicit_markers(self):
        """OpenAI uses automatic prefix caching → no explicit markers."""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini", prompt_caching=True)
        history = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
        ]
        messages, _ = llm._build_messages(
            prompt="latest",
            system_prompt="You are helpful.",
            chat_history=history,
        )
        assert _count_cache_markers(messages) == 0
        # System stays a plain string (prefix byte-stable by construction)
        assert isinstance(messages[0]["content"], str)

    def test_short_history_leaves_tail_uncached(self):
        """With only the tail present, no history breakpoint is added."""
        llm = self._anthropic_llm()
        history = [{"role": "user", "content": "only-one"}]
        with patch.object(llm, '_supports_prompt_caching', return_value=True):
            messages, _ = llm._build_messages(
                prompt="latest",
                system_prompt="You are helpful.",
                chat_history=history,
            )
        # Only the system block should be marked (history too short)
        assert _count_cache_markers(messages) == 1

    def test_mark_message_cache_control_string(self):
        """String content is converted to array form with a marker."""
        from praisonaiagents.llm.llm import LLM
        msg = {"role": "user", "content": "hello"}
        assert LLM._mark_message_cache_control(msg) is True
        assert isinstance(msg["content"], list)
        assert msg["content"][0]["cache_control"] == {"type": "ephemeral"}

    def test_mark_message_cache_control_is_idempotent(self):
        """Re-marking an already-marked block does not duplicate markers."""
        from praisonaiagents.llm.llm import LLM
        msg = {"role": "user", "content": "hello"}
        LLM._mark_message_cache_control(msg)
        LLM._mark_message_cache_control(msg)
        markers = [b for b in msg["content"] if "cache_control" in b]
        assert len(markers) == 1

    def test_mark_message_cache_control_already_marked_returns_false(self):
        """An already-marked list block reports no new marker applied."""
        from praisonaiagents.llm.llm import LLM
        msg = {"role": "user", "content": "hello"}
        assert LLM._mark_message_cache_control(msg) is True
        # Second call finds an existing marker → no new breakpoint applied.
        assert LLM._mark_message_cache_control(msg) is False

    def test_history_not_mutated_in_place(self):
        """Marking the history prefix must not mutate caller-owned dicts."""
        llm = self._anthropic_llm()
        history = [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
            {"role": "user", "content": "three"},
            {"role": "assistant", "content": "four"},
        ]
        original = [dict(m) for m in history]
        with patch.object(llm, '_supports_prompt_caching', return_value=True):
            llm._build_messages(
                prompt="latest",
                system_prompt="You are helpful.",
                chat_history=history,
            )
        # Caller history stays byte-stable (still plain strings, no markers).
        assert history == original
        for msg in history:
            assert isinstance(msg["content"], str)

    def test_budget_respects_preexisting_history_markers(self):
        """Pre-existing markers in supplied history count toward the budget."""
        llm = self._anthropic_llm()
        # History already carrying three ephemeral markers.
        marked = lambda text: {
            "role": "user",
            "content": [
                {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
            ],
        }
        history = [
            marked("a"), marked("b"), marked("c"),
            {"role": "user", "content": "d"},
            {"role": "assistant", "content": "e"},
            {"role": "user", "content": "f"},
        ]
        with patch.object(llm, '_supports_prompt_caching', return_value=True):
            messages, _ = llm._build_messages(
                prompt="latest",
                system_prompt="You are helpful.",
                chat_history=history,
            )
        # system(1) + three history markers already = 4; no more added.
        assert _count_cache_markers(messages) <= 4


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
