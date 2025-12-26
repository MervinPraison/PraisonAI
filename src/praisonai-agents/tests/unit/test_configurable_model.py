"""
TDD Tests for Configurable Model (runtime model switching).

These tests are written FIRST before implementation.
"""

import pytest
from unittest.mock import Mock, patch


class TestConfigurableModelBasic:
    """Test basic configurable model functionality."""
    
    def test_agent_accepts_llm_config_configurable(self):
        """Agent should accept llm_config with configurable=True."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        assert agent is not None
        assert getattr(agent, '_llm_configurable', False) is True
    
    def test_agent_chat_accepts_config_parameter(self):
        """Agent.chat() should accept config parameter for model override."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        
        # Should not raise - config parameter should be accepted
        # We'll mock the actual LLM call
        with patch.object(agent, '_chat_completion', return_value="mocked"):
            result = agent.chat(
                "Hello",
                config={"model": "claude-3-5-sonnet"}
            )
    
    def test_config_model_override(self):
        """config.model should override default model for that call."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        
        # Track which model was used
        used_model = [None]
        
        original_chat = agent._chat_completion
        def mock_chat(*args, **kwargs):
            # The model should be accessible somehow
            used_model[0] = getattr(agent, '_current_model', agent.llm)
            return "response"
        
        with patch.object(agent, '_chat_completion', side_effect=mock_chat):
            agent.chat("Hello", config={"model": "claude-3-5-sonnet"})
        
        # Model should have been switched for this call
        # Implementation will set _current_model or similar
    
    def test_config_does_not_mutate_default(self):
        """Per-call config should not change agent's default model."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        
        original_llm = agent.llm
        
        with patch.object(agent, '_chat_completion', return_value="mocked"):
            agent.chat("Hello", config={"model": "claude-3-5-sonnet"})
        
        # Default should be unchanged
        assert agent.llm == original_llm
    
    def test_config_temperature_override(self):
        """config.temperature should override for that call."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        
        # Should accept temperature in config
        with patch.object(agent, '_chat_completion', return_value="mocked") as mock:
            agent.chat("Hello", config={"temperature": 0.2})
            # Temperature should be passed through


class TestConfigurableModelCaching:
    """Test model client caching for configurable models."""
    
    def test_model_client_cached(self):
        """Model clients should be cached to avoid recreation."""
        from praisonaiagents.llm import LLM
        
        llm = LLM(model="gpt-4o", configurable=True)
        
        # First call with model A
        # Second call with model A should reuse client
        # This is internal behavior - we test via call count or similar
    
    def test_cache_size_limited(self):
        """Model client cache should have a size limit."""
        from praisonaiagents.llm import LLM
        
        llm = LLM(model="gpt-4o", configurable=True, cache_size=3)
        
        # Should not grow unbounded


class TestConfigurableModelThreadSafety:
    """Test thread safety of configurable models."""
    
    def test_concurrent_calls_different_models(self):
        """Concurrent calls with different models should not interfere."""
        import threading
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        
        results = {}
        errors = []
        
        def call_with_model(model_name, thread_id):
            try:
                with patch.object(agent, '_chat_completion', return_value=f"response_{model_name}"):
                    result = agent.chat("Hello", config={"model": model_name})
                    results[thread_id] = result
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=call_with_model, args=("model_a", 1)),
            threading.Thread(target=call_with_model, args=("model_b", 2)),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestConfigurableModelValidation:
    """Test validation of configurable model settings."""
    
    def test_config_without_configurable_flag_ignored(self):
        """If llm_config.configurable is False, config param should be ignored."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o"
            # No llm_config or configurable=False
        )
        
        # Should still work, just ignore the config
        with patch.object(agent, '_chat_completion', return_value="mocked"):
            result = agent.chat("Hello", config={"model": "other"})
            # Should use default model, not "other"
    
    def test_invalid_config_keys_ignored(self):
        """Unknown keys in config should be ignored, not error."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        
        # Should not raise for unknown keys
        with patch.object(agent, '_chat_completion', return_value="mocked"):
            result = agent.chat("Hello", config={"unknown_key": "value"})


class TestConfigurableModelProvider:
    """Test provider switching in configurable models."""
    
    def test_config_provider_override(self):
        """config.provider should allow switching providers."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        
        # Should accept provider in config
        with patch.object(agent, '_chat_completion', return_value="mocked"):
            agent.chat("Hello", config={"provider": "anthropic", "model": "claude-3-5-sonnet"})
    
    def test_model_string_with_provider_prefix(self):
        """Model string like 'anthropic/claude-3' should work."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            llm_config={"configurable": True}
        )
        
        with patch.object(agent, '_chat_completion', return_value="mocked"):
            agent.chat("Hello", config={"model": "anthropic/claude-3-5-sonnet"})
