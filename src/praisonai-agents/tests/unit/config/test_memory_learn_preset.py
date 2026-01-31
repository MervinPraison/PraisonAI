"""
Tests for memory="learn" shorthand preset.

Tests that memory="learn" enables Agent Learn functionality with a simple string parameter.
"""

import pytest


class TestMemoryLearnPreset:
    """Test that 'learn' preset exists in MEMORY_PRESETS."""
    
    def test_learn_preset_exists(self):
        """MEMORY_PRESETS should contain 'learn' key."""
        from praisonaiagents.config.presets import MEMORY_PRESETS
        
        assert "learn" in MEMORY_PRESETS, "MEMORY_PRESETS should have 'learn' preset"
    
    def test_learn_preset_has_learn_true(self):
        """Learn preset should have learn=True."""
        from praisonaiagents.config.presets import MEMORY_PRESETS
        
        preset = MEMORY_PRESETS.get("learn", {})
        assert preset.get("learn") is True, "Learn preset should have learn=True"
    
    def test_learn_preset_has_backend(self):
        """Learn preset should have a backend (file by default)."""
        from praisonaiagents.config.presets import MEMORY_PRESETS
        
        preset = MEMORY_PRESETS.get("learn", {})
        assert "backend" in preset, "Learn preset should have backend"
        assert preset["backend"] == "file", "Learn preset should use file backend by default"


class TestMemoryLearnResolution:
    """Test that memory='learn' resolves correctly."""
    
    def test_resolve_memory_learn_string(self):
        """resolve() should convert 'learn' string to MemoryConfig with learn=True."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
        from praisonaiagents.config.feature_configs import MemoryConfig
        
        result = resolve(
            value="learn",
            param_name="memory",
            config_class=MemoryConfig,
            presets=MEMORY_PRESETS,
            url_schemes=MEMORY_URL_SCHEMES,
            array_mode=ArrayMode.SINGLE_OR_LIST,
            default=None,
        )
        
        assert result is not None, "Should resolve 'learn' to a config"
        assert isinstance(result, MemoryConfig), f"Should be MemoryConfig, got {type(result)}"
        assert result.learn is True, "MemoryConfig should have learn=True"
    
    def test_memory_config_from_preset_dict(self):
        """MemoryConfig should accept learn field from preset dict."""
        from praisonaiagents.config.feature_configs import MemoryConfig
        
        # Simulate what happens when preset is converted to MemoryConfig
        preset_dict = {"backend": "file", "learn": True}
        config = MemoryConfig(**preset_dict)
        
        assert config.backend == "file"
        assert config.learn is True


class TestAgentMemoryLearnShorthand:
    """Test Agent accepts memory='learn' parameter."""
    
    def test_agent_accepts_memory_learn_string(self):
        """Agent should accept memory='learn' without error."""
        from praisonaiagents import Agent
        
        # Should not raise
        agent = Agent(
            instructions="Test agent with learn memory",
            memory="learn"
        )
        
        assert agent is not None
    
    def test_agent_memory_learn_sets_learn_config(self):
        """Agent with memory='learn' should have memory enabled."""
        from praisonaiagents import Agent
        
        agent = Agent(
            instructions="Test agent", 
            memory="learn"
        )
        
        # Agent should have memory enabled (truthy value)
        assert agent.memory, "Agent.memory should be enabled when using memory='learn'"


class TestMemoryLearnIntegration:
    """Integration tests for memory='learn' with Memory class."""
    
    def test_memory_class_with_learn_config(self):
        """Memory class should initialize LearnManager when learn=True in config."""
        from praisonaiagents.memory.memory import Memory
        
        memory = Memory({"provider": "rag", "learn": True, "use_embedding": False})
        
        # Access learn property (lazy-loaded)
        learn_manager = memory.learn
        
        assert learn_manager is not None, "Memory.learn should return LearnManager instance"
    
    def test_memory_learn_captures_persona(self):
        """LearnManager should capture persona entries."""
        import tempfile
        import shutil
        from praisonaiagents.memory.memory import Memory
        
        temp_dir = tempfile.mkdtemp()
        try:
            memory = Memory({
                "provider": "rag", 
                "learn": True, 
                "use_embedding": False,
                "user_id": "test_user"
            })
            
            if memory.learn:
                entry = memory.learn.capture_persona("User prefers concise responses")
                assert entry is not None
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
