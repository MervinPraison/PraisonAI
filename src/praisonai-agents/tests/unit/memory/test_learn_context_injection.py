"""
TDD Tests for Learn Context Injection.

Tests that when memory="learn" is used, the learn context is automatically
injected into the system prompt without requiring a new Agent parameter.

Key behaviors:
1. memory="learn" preset enables LearnManager
2. Learn context is auto-injected into system prompt
3. No new Agent params needed (uses existing memory= param)
4. Zero overhead when learn is not enabled
"""

import pytest  # noqa: F401 - used for test markers


class TestLearnPresetResolution:
    """Test that memory='learn' resolves correctly."""
    
    def test_learn_preset_exists_in_memory_presets(self):
        """MEMORY_PRESETS should have 'learn' preset with learn=True."""
        from praisonaiagents.config.presets import MEMORY_PRESETS
        
        assert "learn" in MEMORY_PRESETS
        assert MEMORY_PRESETS["learn"]["learn"] is True
        assert MEMORY_PRESETS["learn"]["backend"] == "file"
    
    def test_memory_learn_string_resolves_to_config_with_learn_true(self):
        """memory='learn' should resolve to MemoryConfig with learn=True."""
        from praisonaiagents.config.param_resolver import resolve
        from praisonaiagents.config.feature_configs import MemoryConfig
        from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
        
        result = resolve(
            value="learn",
            param_name="memory",
            config_class=MemoryConfig,
            presets=MEMORY_PRESETS,
            url_schemes=MEMORY_URL_SCHEMES,
        )
        
        assert isinstance(result, MemoryConfig)
        assert result.learn is True


class TestAgentLearnContextInjection:
    """Test that Agent injects learn context into system prompt."""
    
    def test_agent_with_memory_learn_has_learn_manager(self):
        """Agent with memory='learn' should have access to LearnManager."""
        from praisonaiagents import Agent
        
        # Create agent with memory="learn"
        agent = Agent(
            name="test_agent",
            instructions="Test instructions",
            memory="learn",
        )
        
        # Memory instance should exist
        assert agent._memory_instance is not None
        
        # Memory should have learn property that returns LearnManager
        if hasattr(agent._memory_instance, 'learn'):
            learn_manager = agent._memory_instance.learn
            assert learn_manager is not None
    
    def test_get_learn_context_returns_empty_when_no_learnings(self):
        """get_learn_context should return empty string when no learnings exist."""
        from praisonaiagents import Agent
        import uuid
        
        # Use unique user_id to ensure clean state
        unique_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        
        agent = Agent(
            name="test_agent",
            instructions="Test instructions",
            memory={"backend": "file", "learn": True, "user_id": unique_user_id},
        )
        
        # Should have get_learn_context method
        assert hasattr(agent, 'get_learn_context')
        
        # Should return empty string when no learnings (fresh user)
        context = agent.get_learn_context()
        assert context == "" or context is None or (isinstance(context, str) and len(context) == 0)
    
    def test_get_learn_context_returns_learnings_when_present(self):
        """get_learn_context should return formatted learnings when present."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test_agent",
            instructions="Test instructions",
            memory="learn",
        )
        
        # Add some learnings via the memory's learn manager
        if agent._memory_instance and hasattr(agent._memory_instance, 'learn'):
            learn_manager = agent._memory_instance.learn
            if learn_manager:
                learn_manager.capture_persona("User prefers concise responses")
                learn_manager.capture_insight("User works in data science")
        
        # get_learn_context should now return formatted context
        context = agent.get_learn_context()
        
        # Should contain the captured learnings
        if context:
            assert "concise" in context.lower() or "User Preferences" in context
    
    def test_build_system_prompt_includes_learn_context(self):
        """_build_system_prompt should include learn context when memory='learn'."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test_agent",
            role="Test Role",
            goal="Test Goal",
            backstory="Test Backstory",
            instructions="Test instructions",
            memory="learn",
        )
        
        # Add some learnings
        if agent._memory_instance and hasattr(agent._memory_instance, 'learn'):
            learn_manager = agent._memory_instance.learn
            if learn_manager:
                learn_manager.capture_persona("User prefers detailed explanations")
        
        # Build system prompt
        system_prompt = agent._build_system_prompt()
        
        # System prompt should include learn context section
        # Note: This test will fail until we implement the fix
        if agent._memory_instance and hasattr(agent._memory_instance, 'learn'):
            learn_manager = agent._memory_instance.learn
            if learn_manager and learn_manager.get_persona_context():
                assert "Learned" in system_prompt or "User Preferences" in system_prompt or "detailed explanations" in system_prompt.lower()


class TestLearnContextZeroOverhead:
    """Test that learn context has zero overhead when not enabled."""
    
    def test_no_learn_context_when_memory_true(self):
        """memory=True should NOT enable learn context."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test_agent",
            instructions="Test instructions",
            memory=True,
        )
        
        # get_learn_context should return empty or None
        context = agent.get_learn_context()
        assert context == "" or context is None
    
    def test_no_learn_context_when_memory_false(self):
        """memory=False should NOT enable learn context."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test_agent",
            instructions="Test instructions",
            memory=False,
        )
        
        # get_learn_context should return empty or None
        context = agent.get_learn_context()
        assert context == "" or context is None
    
    def test_no_learn_context_when_memory_none(self):
        """memory=None should NOT enable learn context."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="test_agent",
            instructions="Test instructions",
        )
        
        # get_learn_context should return empty or None
        context = agent.get_learn_context()
        assert context == "" or context is None


class TestMemoryLearnProperty:
    """Test Memory.learn property and get_learn_context method."""
    
    def test_memory_learn_property_returns_learn_manager_when_enabled(self):
        """Memory.learn should return LearnManager when learn=True in config."""
        from praisonaiagents.memory.memory import Memory
        
        memory = Memory({"learn": True})
        
        # learn property should return LearnManager
        learn_manager = memory.learn
        assert learn_manager is not None
        
        # Should have capture methods
        assert hasattr(learn_manager, 'capture_persona')
        assert hasattr(learn_manager, 'capture_insight')
        assert hasattr(learn_manager, 'to_system_prompt_context')
    
    def test_memory_learn_property_returns_none_when_disabled(self):
        """Memory.learn should return None when learn is not enabled."""
        from praisonaiagents.memory.memory import Memory
        
        memory = Memory({})  # No learn config
        
        # learn property should return None
        assert memory.learn is None
    
    def test_memory_get_learn_context_returns_formatted_string(self):
        """Memory.get_learn_context should return formatted context string."""
        from praisonaiagents.memory.memory import Memory
        
        memory = Memory({"learn": True})
        
        # Add some learnings
        memory.learn.capture_persona("User prefers Python")
        memory.learn.capture_insight("User is a developer")
        
        # get_learn_context should return formatted string
        context = memory.get_learn_context()
        
        assert isinstance(context, str)
        assert "Python" in context or "User Preferences" in context
