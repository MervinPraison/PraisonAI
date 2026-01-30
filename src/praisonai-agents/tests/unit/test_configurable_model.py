"""
TDD Tests for Configurable Model (runtime model switching).

NOTE: llm_config parameter was removed in v4.0.0.
These tests have been updated to reflect the new API.
Runtime model configuration is done via agent.chat() config parameter.
"""

import pytest
from unittest.mock import Mock, patch


class TestConfigurableModelBasic:
    """Test basic configurable model functionality.
    
    v4.0.0 Note: llm_config parameter was removed. These tests verify
    that the Agent works correctly without it.
    """
    
    def test_agent_accepts_llm_string(self):
        """Agent should accept llm as a string."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o"
        )
        assert agent is not None
        assert agent.llm == "gpt-4o"
    
    def test_agent_accepts_model_alias(self):
        """Agent should accept model= as alias for llm=."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            model="gpt-4o-mini"
        )
        assert agent is not None
        # model= should be stored as llm
        assert agent.llm == "gpt-4o-mini"
    
    def test_llm_config_removed_in_v4(self):
        """llm_config parameter should be rejected (removed in v4)."""
        from praisonaiagents import Agent
        
        with pytest.raises(TypeError) as exc_info:
            Agent(
                name="Test",
                instructions="Test agent",
                llm="gpt-4o",
                llm_config={"configurable": True}  # Removed in v4
            )
        
        assert "llm_config" in str(exc_info.value)
    
    def test_agent_default_llm(self):
        """Agent should use default LLM if not specified."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent"
        )
        assert agent is not None
        # Should have a default or None


class TestConfigurableModelProvider:
    """Test provider configuration in agents."""
    
    def test_agent_with_provider_prefix(self):
        """Agent should accept provider/model format."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="openai/gpt-4o"
        )
        assert agent is not None
        assert "gpt-4o" in agent.llm
    
    def test_agent_with_base_url(self):
        """Agent should accept base_url for custom endpoints."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            base_url="https://custom.api.com/v1"
        )
        assert agent is not None


class TestConfigurableModelThreadSafety:
    """Test thread safety of agent model usage."""
    
    def test_concurrent_agent_creation(self):
        """Multiple agents can be created concurrently."""
        import threading
        from praisonaiagents import Agent
        
        agents = []
        errors = []
        
        def create_agent(model_name, idx):
            try:
                agent = Agent(
                    name=f"Agent_{idx}",
                    instructions="Test agent",
                    llm=model_name
                )
                agents.append(agent)
            except Exception as e:
                errors.append(e)
        
        threads = [
            threading.Thread(target=create_agent, args=("gpt-4o", 1)),
            threading.Thread(target=create_agent, args=("gpt-4o-mini", 2)),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(agents) == 2


class TestConfigurableModelValidation:
    """Test validation of model settings."""
    
    def test_empty_llm_accepted(self):
        """Agent should accept empty/None llm (uses env default)."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm=None
        )
        assert agent is not None
    
    def test_llm_with_api_key(self):
        """Agent should accept api_key separately."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            llm="gpt-4o",
            api_key="test-key-not-real"
        )
        assert agent is not None
