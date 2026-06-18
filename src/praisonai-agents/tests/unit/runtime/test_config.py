"""Tests for AgentRuntimeConfig dataclass."""

import pytest
from praisonaiagents.runtime.config import AgentRuntimeConfig


class TestAgentRuntimeConfig:
    """Test suite for AgentRuntimeConfig functionality."""
    
    def test_basic_initialization(self):
        """Test basic AgentRuntimeConfig initialization."""
        config = AgentRuntimeConfig()
        
        assert config.runtime is None
        assert config.config_overrides == {}
        assert config.provider_default is None
        assert config.enable_auto_selection is True
        assert config.metadata == {}
    
    def test_initialization_with_parameters(self):
        """Test AgentRuntimeConfig initialization with parameters."""
        config = AgentRuntimeConfig(
            runtime="claude-code",
            config_overrides={"timeout": 30},
            provider_default="praisonai",
            enable_auto_selection=False,
            metadata={"source": "test"}
        )
        
        assert config.runtime == "claude-code"
        assert config.config_overrides == {"timeout": 30}
        assert config.provider_default == "praisonai"
        assert config.enable_auto_selection is False
        assert config.metadata == {"source": "test"}
    
    def test_from_runtime_id(self):
        """Test creating config from runtime ID."""
        config = AgentRuntimeConfig.from_runtime_id("claude-code")
        
        assert config.runtime == "claude-code"
        assert config.config_overrides == {}
        assert config.provider_default is None
        assert config.enable_auto_selection is True
        assert config.metadata == {}
    
    def test_from_runtime_id_with_kwargs(self):
        """Test creating config from runtime ID with additional kwargs."""
        config = AgentRuntimeConfig.from_runtime_id(
            "claude-code",
            config_overrides={"model": "claude-3-sonnet"},
            provider_default="anthropic"
        )
        
        assert config.runtime == "claude-code"
        assert config.config_overrides == {"model": "claude-3-sonnet"}
        assert config.provider_default == "anthropic"
    
    def test_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "runtime": "claude-code",
            "config_overrides": {"timeout": 60},
            "provider_default": "anthropic",
            "enable_auto_selection": False,
            "metadata": {"test": True}
        }
        
        config = AgentRuntimeConfig.from_dict(config_dict)
        
        assert config.runtime == "claude-code"
        assert config.config_overrides == {"timeout": 60}
        assert config.provider_default == "anthropic"
        assert config.enable_auto_selection is False
        assert config.metadata == {"test": True}
    
    def test_from_dict_partial(self):
        """Test creating config from partial dictionary."""
        config_dict = {"runtime": "praisonai"}
        
        config = AgentRuntimeConfig.from_dict(config_dict)
        
        assert config.runtime == "praisonai"
        assert config.config_overrides == {}
        assert config.provider_default is None
        assert config.enable_auto_selection is True
        assert config.metadata == {}
    
    def test_from_dict_invalid_type(self):
        """Test from_dict with invalid input type."""
        with pytest.raises(TypeError, match="config_dict must be a dictionary"):
            AgentRuntimeConfig.from_dict("invalid")
    
    def test_from_dict_invalid_config_overrides(self):
        """Test from_dict with invalid config_overrides type."""
        with pytest.raises(TypeError, match="config_overrides must be a dictionary"):
            AgentRuntimeConfig.from_dict({"config_overrides": "invalid"})
    
    def test_from_dict_invalid_metadata(self):
        """Test from_dict with invalid metadata type."""
        with pytest.raises(TypeError, match="metadata must be a dictionary"):
            AgentRuntimeConfig.from_dict({"metadata": "invalid"})
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = AgentRuntimeConfig(
            runtime="claude-code",
            config_overrides={"timeout": 30},
            provider_default="anthropic"
        )
        
        result = config.to_dict()
        
        expected = {
            "runtime": "claude-code",
            "config_overrides": {"timeout": 30},
            "provider_default": "anthropic",
            "enable_auto_selection": True,
            "metadata": {}
        }
        
        assert result == expected
    
    def test_merge_overrides(self):
        """Test merging configuration overrides."""
        config = AgentRuntimeConfig(
            runtime="claude-code",
            config_overrides={"timeout": 30, "model": "claude-3"}
        )
        
        new_config = config.merge_overrides({"timeout": 60, "temperature": 0.7})
        
        assert new_config.runtime == "claude-code"
        assert new_config.config_overrides == {"timeout": 60, "model": "claude-3", "temperature": 0.7}
        assert new_config is not config  # Should be a new instance
    
    def test_merge_overrides_invalid_type(self):
        """Test merge_overrides with invalid input type."""
        config = AgentRuntimeConfig()
        
        with pytest.raises(TypeError, match="overrides must be a dictionary"):
            config.merge_overrides("invalid")
    
    def test_with_runtime(self):
        """Test creating new config with different runtime."""
        config = AgentRuntimeConfig(
            runtime="claude-code",
            config_overrides={"timeout": 30},
            metadata={"source": "test"}
        )
        
        new_config = config.with_runtime("praisonai")
        
        assert new_config.runtime == "praisonai"
        assert new_config.config_overrides == {"timeout": 30}
        assert new_config.metadata == {"source": "test"}
        assert new_config is not config  # Should be a new instance
    
    def test_is_explicit(self):
        """Test checking if runtime is explicitly specified."""
        # Explicit runtime
        config1 = AgentRuntimeConfig(runtime="claude-code")
        assert config1.is_explicit() is True
        
        # No runtime
        config2 = AgentRuntimeConfig()
        assert config2.is_explicit() is False
        
        # Empty runtime
        config3 = AgentRuntimeConfig(runtime="")
        assert config3.is_explicit() is False
    
    def test_post_init_validation(self):
        """Test post-init validation of parameters."""
        # Valid initialization should work
        config = AgentRuntimeConfig(
            config_overrides={},
            metadata={}
        )
        assert config.config_overrides == {}
        assert config.metadata == {}
        
        # Invalid config_overrides type should raise error
        with pytest.raises(TypeError, match="config_overrides must be a dictionary"):
            AgentRuntimeConfig(config_overrides="invalid")
        
        # Invalid metadata type should raise error
        with pytest.raises(TypeError, match="metadata must be a dictionary"):
            AgentRuntimeConfig(metadata="invalid")
    
    def test_repr(self):
        """Test string representation of AgentRuntimeConfig."""
        config = AgentRuntimeConfig(
            runtime="claude-code",
            config_overrides={"timeout": 30},
            provider_default="anthropic",
            enable_auto_selection=False
        )
        
        repr_str = repr(config)
        
        assert "AgentRuntimeConfig(" in repr_str
        assert "runtime='claude-code'" in repr_str
        assert "config_overrides={'timeout': 30}" in repr_str
        assert "provider_default='anthropic'" in repr_str
        assert "enable_auto_selection=False" in repr_str