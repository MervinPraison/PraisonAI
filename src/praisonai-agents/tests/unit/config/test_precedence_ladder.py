"""Tests for precedence ladder resolvers."""

import pytest
from praisonaiagents.config.feature_configs import (
    MemoryConfig,
    MemoryBackend,
    KnowledgeConfig,
    PlanningConfig,
    ReflectionConfig,
    GuardrailConfig,
    WebConfig,
    OutputConfig,
    ExecutionConfig,
    CachingConfig,
    AutonomyConfig,
    resolve_memory,
    resolve_knowledge,
    resolve_planning,
    resolve_reflection,
    resolve_guardrails,
    resolve_web,
    resolve_output,
    resolve_execution,
    resolve_caching,
    resolve_autonomy,
)


class TestResolveMemory:
    """Test resolve_memory precedence ladder."""
    
    def test_default_none(self):
        """Default (None) returns None."""
        assert resolve_memory(None) is None
    
    def test_bool_false(self):
        """False returns None (disabled)."""
        assert resolve_memory(False) is None
    
    def test_bool_true(self):
        """True returns MemoryConfig with defaults."""
        result = resolve_memory(True)
        assert isinstance(result, MemoryConfig)
        assert result.backend == MemoryBackend.FILE
    
    def test_string_backend(self):
        """String returns MemoryConfig with that backend."""
        result = resolve_memory("redis")
        assert isinstance(result, MemoryConfig)
        assert result.backend == MemoryBackend.REDIS
    
    def test_string_custom_backend(self):
        """Custom string backend is preserved."""
        result = resolve_memory("custom_backend")
        assert isinstance(result, MemoryConfig)
        assert result.backend == "custom_backend"
    
    def test_dict_expansion(self):
        """Dict expands to MemoryConfig."""
        result = resolve_memory({
            "backend": "sqlite",
            "user_id": "alice",
            "auto_memory": True,
        })
        assert isinstance(result, MemoryConfig)
        assert result.backend == MemoryBackend.SQLITE
        assert result.user_id == "alice"
        assert result.auto_memory is True
    
    def test_config_passthrough(self):
        """MemoryConfig passes through unchanged."""
        config = MemoryConfig(backend=MemoryBackend.POSTGRES, user_id="bob")
        result = resolve_memory(config)
        assert result is config
    
    def test_instance_passthrough(self):
        """Instance (non-config object) passes through."""
        class MockMemoryManager:
            pass
        instance = MockMemoryManager()
        result = resolve_memory(instance)
        assert result is instance


class TestResolveKnowledge:
    """Test resolve_knowledge precedence ladder."""
    
    def test_default_none(self):
        assert resolve_knowledge(None) is None
    
    def test_bool_false(self):
        assert resolve_knowledge(False) is None
    
    def test_bool_true(self):
        result = resolve_knowledge(True)
        assert isinstance(result, KnowledgeConfig)
    
    def test_string_single_source(self):
        result = resolve_knowledge("docs/")
        assert isinstance(result, KnowledgeConfig)
        assert result.sources == ["docs/"]
    
    def test_array_sources(self):
        result = resolve_knowledge(["docs/", "data.pdf"])
        assert isinstance(result, KnowledgeConfig)
        assert result.sources == ["docs/", "data.pdf"]
    
    def test_dict_expansion(self):
        result = resolve_knowledge({
            "sources": ["docs/"],
            "rerank": True,
        })
        assert isinstance(result, KnowledgeConfig)
        assert result.sources == ["docs/"]
        assert result.rerank is True
    
    def test_config_passthrough(self):
        config = KnowledgeConfig(sources=["test/"])
        result = resolve_knowledge(config)
        assert result is config


class TestResolvePlanning:
    """Test resolve_planning precedence ladder."""
    
    def test_default_none(self):
        assert resolve_planning(None) is None
    
    def test_bool_false(self):
        assert resolve_planning(False) is None
    
    def test_bool_true(self):
        result = resolve_planning(True)
        assert isinstance(result, PlanningConfig)
    
    def test_config_passthrough(self):
        config = PlanningConfig()
        result = resolve_planning(config)
        assert result is config


class TestResolveReflection:
    """Test resolve_reflection precedence ladder."""
    
    def test_default_none(self):
        assert resolve_reflection(None) is None
    
    def test_bool_false(self):
        assert resolve_reflection(False) is None
    
    def test_bool_true(self):
        result = resolve_reflection(True)
        assert isinstance(result, ReflectionConfig)


class TestResolveGuardrails:
    """Test resolve_guardrails precedence ladder."""
    
    def test_default_none(self):
        assert resolve_guardrails(None) is None
    
    def test_bool_false(self):
        assert resolve_guardrails(False) is None
    
    def test_bool_true(self):
        result = resolve_guardrails(True)
        assert isinstance(result, GuardrailConfig)
    
    def test_callable_validator(self):
        def my_validator(output):
            return True, output
        result = resolve_guardrails(my_validator)
        assert isinstance(result, GuardrailConfig)
        assert result.validator is my_validator


class TestResolveWeb:
    """Test resolve_web precedence ladder."""
    
    def test_default_none(self):
        assert resolve_web(None) is None
    
    def test_bool_false(self):
        assert resolve_web(False) is None
    
    def test_bool_true(self):
        result = resolve_web(True)
        assert isinstance(result, WebConfig)


class TestResolveCaching:
    """Test resolve_caching precedence ladder."""
    
    def test_default_none(self):
        assert resolve_caching(None) is None
    
    def test_bool_false(self):
        assert resolve_caching(False) is None
    
    def test_bool_true(self):
        result = resolve_caching(True)
        assert isinstance(result, CachingConfig)


class TestResolveAutonomy:
    """Test resolve_autonomy precedence ladder."""
    
    def test_default_none(self):
        assert resolve_autonomy(None) is None
    
    def test_bool_false(self):
        assert resolve_autonomy(False) is None
    
    def test_bool_true(self):
        result = resolve_autonomy(True)
        assert isinstance(result, AutonomyConfig)


class TestNoCortexParam:
    """Test that cortex parameter does not exist."""
    
    def test_agent_has_no_cortex_param(self):
        """Agent.__init__ should not have cortex parameter."""
        import inspect
        from praisonaiagents import Agent
        
        sig = inspect.signature(Agent.__init__)
        param_names = list(sig.parameters.keys())
        
        assert "cortex" not in param_names, "cortex param should be removed from Agent"
    
    def test_no_cortex_module_in_agents(self):
        """praisonaiagents should not have cortex module."""
        import importlib.util
        
        spec = importlib.util.find_spec("praisonaiagents.cortex")
        assert spec is None, "praisonaiagents.cortex module should not exist"
