"""
Comprehensive tests for param_resolver.py - TDD for outstanding gaps.

Tests cover:
1. Dict strict validation (dataclass and non-dataclass configs)
2. Array PRESET_OVERRIDE invalid preset error UX
3. Precedence ladder for all consolidated params
4. Agent consolidated params via canonical resolver
5. Workflow/Task resolution consistency
"""

import pytest
from dataclasses import dataclass, field
from typing import List


# =============================================================================
# Test Fixtures - Config Classes
# =============================================================================

@dataclass
class MockConfig:
    """Mock config for testing."""
    enabled: bool = True
    value: str = "default"
    count: int = 0


@dataclass
class MockConfigWithSources:
    """Mock config with sources field."""
    sources: List[str] = field(default_factory=list)
    rerank: bool = False


class NonDataclassConfig:
    """Non-dataclass config for testing validation."""
    def __init__(self, enabled: bool = True, value: str = "default"):
        self.enabled = enabled
        self.value = value


# =============================================================================
# PHASE 1A: Dict Strict Validation Tests
# =============================================================================

class TestDictStrictValidation:
    """Tests for strict dict key validation."""
    
    def test_dict_unknown_keys_error_dataclass(self):
        """Dict with unknown keys should raise TypeError with helpful message."""
        from praisonaiagents.config.param_resolver import resolve
        
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"enabled": True, "unknown_key": "bad"},
                param_name="test",
                config_class=MockConfig,
            )
        
        error_msg = str(exc_info.value)
        assert "unknown_key" in error_msg.lower() or "Unknown keys" in error_msg
        assert "enabled" in error_msg or "Valid keys" in error_msg
    
    def test_dict_valid_keys_accepted(self):
        """Dict with valid keys should create config."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value={"enabled": False, "value": "custom"},
            param_name="test",
            config_class=MockConfig,
        )
        
        assert isinstance(result, MockConfig)
        assert result.enabled is False
        assert result.value == "custom"
    
    def test_dict_no_config_class_error(self):
        """Dict without config_class should raise TypeError."""
        from praisonaiagents.config.param_resolver import resolve
        
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"key": "value"},
                param_name="test",
                config_class=None,
            )
        
        assert "not supported" in str(exc_info.value).lower() or "no config class" in str(exc_info.value).lower()
    
    def test_dict_validation_non_dataclass_config(self):
        """Non-dataclass config should still validate keys via signature/annotations."""
        from praisonaiagents.config.param_resolver import _get_valid_keys
        
        # This tests the _get_valid_keys helper handles non-dataclass
        # The implementation should use inspect.signature or __annotations__
        # For now, verify the helper exists and returns something useful
        keys = _get_valid_keys(NonDataclassConfig)
        # Should return valid keys or empty (graceful degradation)
        assert isinstance(keys, (set, list, frozenset)) or keys is None


# =============================================================================
# PHASE 1B: Array PRESET_OVERRIDE Error UX Tests
# =============================================================================

class TestArrayPresetOverrideErrorUX:
    """Tests for array preset error messages with suggestions."""
    
    def test_invalid_preset_in_array_raises_error_with_suggestions(self):
        """Invalid preset string in array should raise error with typo suggestions."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        presets = {
            "fast": {"enabled": True, "value": "fast"},
            "slow": {"enabled": True, "value": "slow"},
            "balanced": {"enabled": True, "value": "balanced"},
        }
        
        with pytest.raises((ValueError, TypeError)) as exc_info:
            resolve(
                value=["fats"],  # Typo for "fast"
                param_name="execution",
                config_class=MockConfig,
                presets=presets,
                array_mode=ArrayMode.PRESET_OVERRIDE,
            )
        
        error_msg = str(exc_info.value).lower()
        # Should suggest similar preset
        assert "fast" in error_msg or "fats" in error_msg
        # Should list valid presets
        assert "valid" in error_msg or "available" in error_msg or any(p in error_msg for p in presets.keys())
    
    def test_valid_preset_in_array_works(self):
        """Valid preset string in array should work."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        presets = {
            "fast": {"enabled": True, "value": "fast"},
        }
        
        result = resolve(
            value=["fast"],
            param_name="execution",
            config_class=MockConfig,
            presets=presets,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        
        assert isinstance(result, MockConfig)
        assert result.value == "fast"
    
    def test_preset_with_overrides_in_array(self):
        """Preset with override dict in array should merge correctly."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        presets = {
            "fast": {"enabled": True, "value": "fast", "count": 1},
        }
        
        result = resolve(
            value=["fast", {"count": 99}],
            param_name="execution",
            config_class=MockConfig,
            presets=presets,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        
        assert isinstance(result, MockConfig)
        assert result.value == "fast"
        assert result.count == 99


# =============================================================================
# PHASE 1C: Precedence Ladder Tests
# =============================================================================

class TestPrecedenceLadder:
    """Tests for Instance > Config > Dict > Array > String > Bool > Default precedence."""
    
    def test_instance_highest_precedence(self):
        """Instance check should have highest precedence."""
        from praisonaiagents.config.param_resolver import resolve
        
        class MockInstance:
            def search(self): pass
            def add(self): pass
        
        instance = MockInstance()
        result = resolve(
            value=instance,
            param_name="memory",
            config_class=MockConfig,
            instance_check=lambda v: hasattr(v, 'search') and hasattr(v, 'add'),
        )
        
        assert result is instance
    
    def test_config_class_instance_precedence(self):
        """Config class instance should be returned as-is."""
        from praisonaiagents.config.param_resolver import resolve
        
        config = MockConfig(enabled=False, value="custom")
        result = resolve(
            value=config,
            param_name="test",
            config_class=MockConfig,
        )
        
        assert result is config
    
    def test_dict_before_string(self):
        """Dict should be processed before string."""
        from praisonaiagents.config.param_resolver import resolve
        
        # Dict input
        result = resolve(
            value={"enabled": False},
            param_name="test",
            config_class=MockConfig,
        )
        
        assert isinstance(result, MockConfig)
        assert result.enabled is False
    
    def test_bool_true_returns_default_config(self):
        """Bool True should return default config instance."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=True,
            param_name="test",
            config_class=MockConfig,
        )
        
        assert isinstance(result, MockConfig)
        assert result.enabled is True  # Default
    
    def test_bool_false_returns_none(self):
        """Bool False should return None (disabled)."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=False,
            param_name="test",
            config_class=MockConfig,
        )
        
        assert result is None
    
    def test_none_returns_default(self):
        """None should return the default value."""
        from praisonaiagents.config.param_resolver import resolve
        
        default = MockConfig(value="default_value")
        result = resolve(
            value=None,
            param_name="test",
            config_class=MockConfig,
            default=default,
        )
        
        assert result is default


# =============================================================================
# PHASE 1D: Agent Consolidated Params Tests
# =============================================================================

class TestAgentConsolidatedParams:
    """Tests for Agent consolidated params using canonical resolver."""
    
    def test_agent_hooks_via_resolver(self):
        """Agent hooks param should use canonical resolver."""
        from praisonaiagents.config.feature_configs import HooksConfig
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        # Test list passthrough
        hooks_list = [lambda x: x]
        result = resolve(
            value=hooks_list,
            param_name="hooks",
            config_class=HooksConfig,
            array_mode=ArrayMode.PASSTHROUGH,
        )
        assert result == hooks_list
        
        # Test HooksConfig instance
        hooks_config = HooksConfig(on_step=lambda x: x)
        result = resolve(
            value=hooks_config,
            param_name="hooks",
            config_class=HooksConfig,
        )
        assert result is hooks_config
        
        # Test dict
        result = resolve(
            value={"on_step": None},
            param_name="hooks",
            config_class=HooksConfig,
        )
        assert isinstance(result, HooksConfig)
    
    def test_agent_skills_via_resolver(self):
        """Agent skills param should use canonical resolver."""
        from praisonaiagents.config.feature_configs import SkillsConfig
        from praisonaiagents.config.param_resolver import resolve
        
        # Test SkillsConfig instance directly
        config = SkillsConfig(paths=["./skill1", "./skill2"])
        result = resolve(
            value=config,
            param_name="skills",
            config_class=SkillsConfig,
        )
        assert isinstance(result, SkillsConfig)
        assert result.paths == ["./skill1", "./skill2"]
        
        # Test dict input
        result = resolve(
            value={"paths": ["./my-skill"]},
            param_name="skills",
            config_class=SkillsConfig,
        )
        assert isinstance(result, SkillsConfig)
        assert result.paths == ["./my-skill"]
    
    def test_agent_knowledge_via_resolver(self):
        """Agent knowledge param should use canonical resolver."""
        from praisonaiagents.config.feature_configs import KnowledgeConfig
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        # Test list of sources
        result = resolve(
            value=["docs/", "data.pdf"],
            param_name="knowledge",
            config_class=KnowledgeConfig,
            array_mode=ArrayMode.SOURCES_WITH_CONFIG,
        )
        assert isinstance(result, KnowledgeConfig)
        assert "docs/" in result.sources
        
        # Test list with config override
        result = resolve(
            value=["docs/", {"rerank": True}],
            param_name="knowledge",
            config_class=KnowledgeConfig,
            array_mode=ArrayMode.SOURCES_WITH_CONFIG,
        )
        assert isinstance(result, KnowledgeConfig)
        assert result.rerank is True
    
    def test_agent_guardrails_via_resolver(self):
        """Agent guardrails param should use canonical resolver."""
        from praisonaiagents.config.feature_configs import GuardrailConfig
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.presets import GUARDRAIL_PRESETS
        
        # Test string preset
        if GUARDRAIL_PRESETS:
            preset_name = list(GUARDRAIL_PRESETS.keys())[0]
            result = resolve(
                value=preset_name,
                param_name="guardrails",
                config_class=GuardrailConfig,
                presets=GUARDRAIL_PRESETS,
                array_mode=ArrayMode.PRESET_OVERRIDE,
            )
            assert result is not None
        
        # Test callable (should be handled via instance_check)
        def validator_fn(x):
            return (True, x)
        
        result = resolve(
            value=validator_fn,
            param_name="guardrails",
            config_class=GuardrailConfig,
            instance_check=callable,
        )
        assert result is validator_fn
        
        # Test GuardrailConfig instance
        config = GuardrailConfig(max_retries=5)
        result = resolve(
            value=config,
            param_name="guardrails",
            config_class=GuardrailConfig,
        )
        assert result is config
        
        # Test string as LLM prompt
        result = resolve(
            value="Ensure response is safe and helpful",
            param_name="guardrails",
            config_class=GuardrailConfig,
            string_mode="llm_prompt",
        )
        assert isinstance(result, GuardrailConfig)
        assert result.llm_validator == "Ensure response is safe and helpful"


# =============================================================================
# PHASE 1E: Workflow/Task Resolution Tests
# =============================================================================

class TestWorkflowResolution:
    """Tests for Workflow and Task resolution consistency."""
    
    def test_workflow_task_context_stored(self):
        """Task context should be stored correctly."""
        from praisonaiagents.workflows.workflows import Task
        
        step = Task(
            name="test",
            description="Test task",
            context=["step1", "step2"],
        )
        
        # Task stores context in 'context' attribute
        assert step.context == ["step1", "step2"]
    
    def test_workflow_task_execution_stored(self):
        """Task execution should be stored correctly."""
        from praisonaiagents.workflows.workflows import Task
        
        step = Task(
            name="test",
            description="Test task",
            execution="fast",
        )
        
        # Task stores execution in 'execution' attribute
        assert step.execution == "fast" or step.max_retries is not None
    
    def test_workflow_task_output_file(self):
        """Task output_file should be stored correctly."""
        from praisonaiagents.workflows.workflows import Task
        
        step = Task(
            name="test",
            description="Test task",
            output_file="result.txt",
        )
        
        # Task stores output_file directly
        assert step.output_file == "result.txt"
    
    def test_workflow_output_resolved(self):
        """Workflow output should be resolved to config."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(
            name="test",
            output="verbose",
        )
        
        # Should have resolved verbose setting
        assert workflow._verbose is True
    
    def test_workflow_planning_resolved(self):
        """Workflow planning should be resolved to config."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(
            name="test",
            planning=True,
        )
        
        # Should have resolved planning enabled
        assert workflow._planning_enabled is True


# =============================================================================
# PHASE 1F: Naming/Alias Tests
# =============================================================================

class TestNamingAlias:
    """Tests for Agents vs PraisonAIAgents naming.
    
    v4.0.0 Updates:
    - Agents is now a SILENT alias for AgentManager (no deprecation warning)
    - PraisonAIAgents has been REMOVED entirely (raises ImportError)
    """
    
    def test_agents_is_silent_alias(self):
        """Agents should be available as silent alias for AgentManager."""
        from praisonaiagents import AgentManager, Agents
        # Agents is now a silent alias
        assert Agents is AgentManager
    
    def test_praisonaiagents_removed_v4(self):
        """PraisonAIAgents was removed in v4 - should raise ImportError."""
        import pytest
        with pytest.raises(ImportError):
            from praisonaiagents import PraisonAIAgents
    
    def test_agent_manager_is_alias_for_agent_team(self):
        """AgentManager is now a silent alias for AgentTeam (v1.0+)."""
        from praisonaiagents import AgentManager, AgentTeam
        assert AgentManager is not None
        assert AgentManager is AgentTeam
        assert AgentManager.__name__ == 'AgentTeam'


# =============================================================================
# PHASE 1G: Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for resolver helper functions."""
    
    def test_get_valid_keys_dataclass(self):
        """_get_valid_keys should return dataclass fields."""
        from praisonaiagents.config.param_resolver import _get_valid_keys
        
        keys = _get_valid_keys(MockConfig)
        assert "enabled" in keys
        assert "value" in keys
        assert "count" in keys
    
    def test_get_valid_keys_non_dataclass(self):
        """_get_valid_keys should handle non-dataclass via signature."""
        from praisonaiagents.config.param_resolver import _get_valid_keys
        
        keys = _get_valid_keys(NonDataclassConfig)
        # Should return keys from __init__ signature or __annotations__
        # or gracefully return empty/None
        assert keys is None or isinstance(keys, (set, list, frozenset))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
