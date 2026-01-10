"""
TDD Tests for Resolver Standardization.

These tests verify:
1. Precedence order: None → Instance → Config → Array → Dict → String → Bool → Default
2. Memory array semantics: single=ok, multiple=error
3. Caching array support with PRESET_OVERRIDE
4. Workflow/WorkflowStep using canonical resolve
5. CLI resolver integration
6. Naming standardization (guardrails plural)
7. All precedence levels per consolidated param

Run with: pytest tests/unit/config/test_resolver_standardization.py -v
"""

import pytest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# =============================================================================
# Test Fixtures - Config Classes
# =============================================================================

@dataclass
class MockConfig:
    """Mock config class for testing."""
    enabled: bool = True
    value: str = "default"
    count: int = 0


@dataclass
class MockMemoryConfig:
    """Mock memory config for testing."""
    backend: str = "file"
    user_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    sources: Optional[List[str]] = None


@dataclass
class MockCachingConfig:
    """Mock caching config for testing."""
    enabled: bool = True
    ttl: int = 3600
    prompt_caching: bool = False


# =============================================================================
# TODO 1.1: Tests for Precedence Order (Array BEFORE Dict)
# =============================================================================

class TestPrecedenceOrder:
    """Test that precedence order is: None → Instance → Config → Array → Dict → String → Bool → Default"""
    
    def test_array_takes_precedence_over_dict_interpretation(self):
        """Array input should be processed as array, not as dict."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        # When given an array, it should use array handling, not dict handling
        result = resolve(
            value=["preset1"],
            param_name="test",
            config_class=MockConfig,
            presets={"preset1": {"enabled": True, "value": "from_preset"}},
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        
        # Should resolve via array path (preset), not dict path
        assert isinstance(result, MockConfig)
        assert result.value == "from_preset"
    
    def test_precedence_instance_over_config(self):
        """Instance check should take precedence over config class check."""
        from praisonaiagents.config.param_resolver import resolve
        
        class CustomInstance:
            def __init__(self):
                self.is_custom = True
        
        custom = CustomInstance()
        
        result = resolve(
            value=custom,
            param_name="test",
            config_class=MockConfig,
            instance_check=lambda v: hasattr(v, 'is_custom'),
        )
        
        # Should return instance as-is, not try to convert
        assert result is custom
        assert result.is_custom is True
    
    def test_precedence_config_over_array(self):
        """Config class instance should take precedence over array handling."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        config = MockConfig(enabled=False, value="config_value")
        
        result = resolve(
            value=config,
            param_name="test",
            config_class=MockConfig,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        
        # Should return config as-is
        assert result is config
        assert result.value == "config_value"
    
    def test_precedence_array_over_dict(self):
        """Array should be checked BEFORE dict in precedence."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        # This test verifies the fix: Array must be checked before Dict
        # A list input should go through array handling, not dict handling
        result = resolve(
            value=["verbose", {"count": 5}],
            param_name="test",
            config_class=MockConfig,
            presets={"verbose": {"enabled": True, "value": "verbose_mode"}},
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        
        assert isinstance(result, MockConfig)
        assert result.value == "verbose_mode"
        assert result.count == 5  # Override applied
    
    def test_precedence_dict_over_string(self):
        """Dict should take precedence over string handling."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value={"enabled": False, "value": "dict_value"},
            param_name="test",
            config_class=MockConfig,
            presets={"dict_value": {"enabled": True}},  # Should NOT use this
        )
        
        assert isinstance(result, MockConfig)
        assert result.value == "dict_value"
        assert result.enabled is False
    
    def test_precedence_string_over_bool(self):
        """String preset should take precedence over bool handling."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value="verbose",
            param_name="test",
            config_class=MockConfig,
            presets={"verbose": {"enabled": True, "value": "verbose_mode"}},
        )
        
        assert isinstance(result, MockConfig)
        assert result.value == "verbose_mode"
    
    def test_precedence_bool_over_default(self):
        """Bool True should create default config, not return default value."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=True,
            param_name="test",
            config_class=MockConfig,
            default={"should": "not_use"},
        )
        
        assert isinstance(result, MockConfig)
        # Should be default MockConfig(), not the default dict
    
    def test_precedence_none_returns_default(self):
        """None should return the default value."""
        from praisonaiagents.config.param_resolver import resolve
        
        default_config = MockConfig(value="default_value")
        
        result = resolve(
            value=None,
            param_name="test",
            config_class=MockConfig,
            default=default_config,
        )
        
        assert result is default_config


# =============================================================================
# TODO 1.2: Tests for Memory Array Semantics
# =============================================================================

class TestMemoryArraySemantics:
    """Test memory array semantics: single=ok, multiple=error."""
    
    def test_memory_single_item_array_resolves_as_scalar(self):
        """memory=["redis"] should resolve as scalar preset."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        result = resolve(
            value=["redis"],
            param_name="memory",
            config_class=MockMemoryConfig,
            presets={"redis": {"backend": "redis"}},
            array_mode=ArrayMode.SINGLE_OR_LIST,
        )
        
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "redis"
    
    def test_memory_multiple_items_raises_error(self):
        """memory=["redis", "file"] should raise TypeError."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value=["redis", "file"],
                param_name="memory",
                config_class=MockMemoryConfig,
                presets={"redis": {"backend": "redis"}, "file": {"backend": "file"}},
                array_mode=ArrayMode.SINGLE_OR_LIST,
            )
        
        # Error message should be helpful
        assert "memory" in str(exc_info.value).lower()
        assert "multiple" in str(exc_info.value).lower() or "single" in str(exc_info.value).lower()
    
    def test_memory_single_url_in_array_resolves(self):
        """memory=["postgresql://..."] should resolve as URL."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        result = resolve(
            value=["postgresql://localhost/db"],
            param_name="memory",
            config_class=MockMemoryConfig,
            url_schemes={"postgresql": "postgres"},
            array_mode=ArrayMode.SINGLE_OR_LIST,
        )
        
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "postgres"


# =============================================================================
# TODO 1.3: Tests for Caching Array Support
# =============================================================================

class TestCachingArraySupport:
    """Test caching array support with PRESET_OVERRIDE."""
    
    def test_caching_array_preset_override(self):
        """caching=["enabled", {"ttl": 7200}] should work."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        result = resolve(
            value=["enabled", {"ttl": 7200}],
            param_name="caching",
            config_class=MockCachingConfig,
            presets={"enabled": {"enabled": True, "ttl": 3600}},
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        
        assert isinstance(result, MockCachingConfig)
        assert result.enabled is True
        assert result.ttl == 7200  # Override applied
    
    def test_caching_string_preset(self):
        """caching="enabled" should work."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        
        result = resolve(
            value="enabled",
            param_name="caching",
            config_class=MockCachingConfig,
            presets={"enabled": {"enabled": True}},
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        
        assert isinstance(result, MockCachingConfig)
        assert result.enabled is True


# =============================================================================
# TODO 1.4: Tests for Workflow/WorkflowStep Using Canonical Resolve
# =============================================================================

class TestWorkflowCanonicalResolve:
    """Test that Workflow and WorkflowStep use canonical resolve directly."""
    
    def test_workflow_output_uses_canonical_resolve(self):
        """Workflow output param should use canonical resolve."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(
            name="test",
            steps=[],
            output="verbose",
        )
        
        assert workflow._verbose is True
    
    def test_workflow_output_dict_validation(self):
        """Workflow output dict should have strict validation."""
        from praisonaiagents.workflows.workflows import Workflow
        
        with pytest.raises(TypeError) as exc_info:
            Workflow(
                name="test",
                steps=[],
                output={"invalid_key": True},
            )
        
        assert "invalid_key" in str(exc_info.value).lower() or "unknown" in str(exc_info.value).lower()
    
    def test_workflowstep_context_uses_canonical_resolve(self):
        """WorkflowStep context param should use canonical resolve."""
        from praisonaiagents.workflows.workflows import WorkflowStep
        
        step = WorkflowStep(
            name="test",
            context=["step1", "step2"],
        )
        
        assert step._context_from == ["step1", "step2"]
    
    def test_workflowstep_execution_preset(self):
        """WorkflowStep execution preset should work."""
        from praisonaiagents.workflows.workflows import WorkflowStep
        
        step = WorkflowStep(
            name="test",
            execution="thorough",
        )
        
        # Should have thorough preset values
        assert step._max_retries >= 3  # Thorough has more retries


# =============================================================================
# TODO 1.5: Tests for CLI Resolver Integration
# =============================================================================

class TestCLIResolverIntegration:
    """Test CLI flags use canonical resolver."""
    
    def test_cli_memory_flag_true(self):
        """CLI --memory flag (true) should resolve correctly."""
        # This tests the integration point - CLI should pass value to canonical resolver
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
        
        # Simulate CLI passing True
        result = resolve(
            value=True,
            param_name="memory",
            config_class=MockMemoryConfig,
            presets=MEMORY_PRESETS,
            url_schemes=MEMORY_URL_SCHEMES,
            array_mode=ArrayMode.SINGLE_OR_LIST,
        )
        
        assert isinstance(result, MockMemoryConfig)
    
    def test_cli_memory_flag_preset_string(self):
        """CLI --memory=redis should resolve as preset."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
        
        result = resolve(
            value="redis",
            param_name="memory",
            config_class=MockMemoryConfig,
            presets=MEMORY_PRESETS,
            url_schemes=MEMORY_URL_SCHEMES,
            array_mode=ArrayMode.SINGLE_OR_LIST,
        )
        
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "redis"
    
    def test_cli_memory_flag_url(self):
        """CLI --memory=postgresql://... should resolve as URL."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
        
        result = resolve(
            value="postgresql://localhost/db",
            param_name="memory",
            config_class=MockMemoryConfig,
            presets=MEMORY_PRESETS,
            url_schemes=MEMORY_URL_SCHEMES,
            array_mode=ArrayMode.SINGLE_OR_LIST,
        )
        
        assert isinstance(result, MockMemoryConfig)
        assert result.backend == "postgres"


# =============================================================================
# TODO 1.6: Tests for Naming Standardization (guardrails plural)
# =============================================================================

class TestNamingStandardization:
    """Test guardrail → guardrails naming standardization."""
    
    def test_workflowstep_accepts_guardrails_plural(self):
        """WorkflowStep should accept guardrails= (plural)."""
        from praisonaiagents.workflows.workflows import WorkflowStep
        
        def my_guardrail(result):
            return (True, result)
        
        # Should accept guardrails= (plural)
        step = WorkflowStep(
            name="test",
            guardrails=my_guardrail,
        )
        
        # Should store in guardrails attribute
        assert step.guardrails is my_guardrail or step.guardrail is my_guardrail
    
    def test_workflowstep_guardrail_singular_compat(self):
        """WorkflowStep should accept guardrail= (singular) for compatibility."""
        from praisonaiagents.workflows.workflows import WorkflowStep
        
        def my_guardrail(result):
            return (True, result)
        
        # Should still accept guardrail= (singular) for backward compat
        step = WorkflowStep(
            name="test",
            guardrail=my_guardrail,
        )
        
        # Should work (backward compat)
        assert step.guardrail is my_guardrail


# =============================================================================
# TODO 1.7: Tests for All Precedence Levels Per Consolidated Param
# =============================================================================

class TestAllPrecedenceLevels:
    """Test each consolidated param has all 7 precedence levels working."""
    
    def test_output_all_precedence_levels(self):
        """Test output param at all precedence levels."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import OutputConfig
        from praisonaiagents.config.presets import OUTPUT_PRESETS
        
        # 1. None → Default
        result = resolve(value=None, param_name="output", config_class=OutputConfig, 
                        presets=OUTPUT_PRESETS, default=OutputConfig())
        assert isinstance(result, OutputConfig)
        
        # 2. Instance (custom object with expected attributes)
        class CustomOutput:
            verbose = True
            stream = True
        custom = CustomOutput()
        result = resolve(value=custom, param_name="output", config_class=OutputConfig,
                        presets=OUTPUT_PRESETS, instance_check=lambda v: hasattr(v, 'verbose'))
        assert result is custom
        
        # 3. Config class instance
        config = OutputConfig(verbose=True, stream=False)
        result = resolve(value=config, param_name="output", config_class=OutputConfig,
                        presets=OUTPUT_PRESETS)
        assert result is config
        
        # 4. Array [preset, overrides]
        result = resolve(value=["verbose", {"stream": False}], param_name="output",
                        config_class=OutputConfig, presets=OUTPUT_PRESETS,
                        array_mode=ArrayMode.PRESET_OVERRIDE)
        assert isinstance(result, OutputConfig)
        
        # 5. Dict
        result = resolve(value={"verbose": True, "stream": False}, param_name="output",
                        config_class=OutputConfig, presets=OUTPUT_PRESETS)
        assert isinstance(result, OutputConfig)
        assert result.verbose is True
        
        # 6. String preset
        result = resolve(value="verbose", param_name="output", config_class=OutputConfig,
                        presets=OUTPUT_PRESETS)
        assert isinstance(result, OutputConfig)
        
        # 7. Bool True
        result = resolve(value=True, param_name="output", config_class=OutputConfig,
                        presets=OUTPUT_PRESETS)
        assert isinstance(result, OutputConfig)
        
        # 8. Bool False → None
        result = resolve(value=False, param_name="output", config_class=OutputConfig,
                        presets=OUTPUT_PRESETS)
        assert result is None
    
    def test_memory_all_precedence_levels(self):
        """Test memory param at all precedence levels."""
        from praisonaiagents.config.param_resolver import resolve, ArrayMode
        from praisonaiagents.config.feature_configs import MemoryConfig
        from praisonaiagents.config.presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
        
        # 1. None → Default
        result = resolve(value=None, param_name="memory", config_class=MemoryConfig,
                        presets=MEMORY_PRESETS, url_schemes=MEMORY_URL_SCHEMES,
                        array_mode=ArrayMode.SINGLE_OR_LIST, default=None)
        assert result is None
        
        # 2. Config class instance
        config = MemoryConfig(backend="redis")
        result = resolve(value=config, param_name="memory", config_class=MemoryConfig,
                        presets=MEMORY_PRESETS, url_schemes=MEMORY_URL_SCHEMES,
                        array_mode=ArrayMode.SINGLE_OR_LIST)
        assert result is config
        
        # 3. Dict
        result = resolve(value={"backend": "sqlite"}, param_name="memory",
                        config_class=MemoryConfig, presets=MEMORY_PRESETS,
                        url_schemes=MEMORY_URL_SCHEMES, array_mode=ArrayMode.SINGLE_OR_LIST)
        assert isinstance(result, MemoryConfig)
        assert result.backend == "sqlite"
        
        # 4. String preset
        result = resolve(value="redis", param_name="memory", config_class=MemoryConfig,
                        presets=MEMORY_PRESETS, url_schemes=MEMORY_URL_SCHEMES,
                        array_mode=ArrayMode.SINGLE_OR_LIST)
        assert isinstance(result, MemoryConfig)
        
        # 5. String URL
        result = resolve(value="postgresql://localhost/db", param_name="memory",
                        config_class=MemoryConfig, presets=MEMORY_PRESETS,
                        url_schemes=MEMORY_URL_SCHEMES, array_mode=ArrayMode.SINGLE_OR_LIST)
        assert isinstance(result, MemoryConfig)
        
        # 6. Bool True
        result = resolve(value=True, param_name="memory", config_class=MemoryConfig,
                        presets=MEMORY_PRESETS, url_schemes=MEMORY_URL_SCHEMES,
                        array_mode=ArrayMode.SINGLE_OR_LIST)
        assert isinstance(result, MemoryConfig)
        
        # 7. Bool False → None
        result = resolve(value=False, param_name="memory", config_class=MemoryConfig,
                        presets=MEMORY_PRESETS, url_schemes=MEMORY_URL_SCHEMES,
                        array_mode=ArrayMode.SINGLE_OR_LIST)
        assert result is None


# =============================================================================
# Tests for Error Messages and Typo Suggestions
# =============================================================================

class TestErrorMessages:
    """Test error messages are helpful with typo suggestions."""
    
    def test_invalid_preset_suggests_similar(self):
        """Invalid preset should suggest similar valid presets."""
        from praisonaiagents.config.param_resolver import resolve
        
        with pytest.raises(ValueError) as exc_info:
            resolve(
                value="verbos",  # Typo
                param_name="output",
                config_class=MockConfig,
                presets={"verbose": {}, "minimal": {}, "debug": {}},
            )
        
        error_msg = str(exc_info.value).lower()
        assert "verbose" in error_msg  # Should suggest "verbose"
    
    def test_unknown_dict_keys_lists_valid_keys(self):
        """Unknown dict keys should list valid keys."""
        from praisonaiagents.config.param_resolver import resolve
        
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"invalid_key": True},
                param_name="test",
                config_class=MockConfig,
            )
        
        error_msg = str(exc_info.value).lower()
        assert "invalid_key" in error_msg or "unknown" in error_msg
        assert "enabled" in error_msg or "valid" in error_msg


# =============================================================================
# Tests for Strict Dict Validation
# =============================================================================

class TestStrictDictValidation:
    """Test strict dict validation."""
    
    def test_dict_without_config_class_raises_error(self):
        """Dict input without config_class should raise TypeError."""
        from praisonaiagents.config.param_resolver import resolve
        
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"key": "value"},
                param_name="test",
                config_class=None,  # No config class
            )
        
        assert "dict" in str(exc_info.value).lower()
    
    def test_dict_with_unknown_keys_raises_error(self):
        """Dict with unknown keys should raise TypeError."""
        from praisonaiagents.config.param_resolver import resolve
        
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"enabled": True, "unknown_field": "value"},
                param_name="test",
                config_class=MockConfig,
            )
        
        error_msg = str(exc_info.value)
        assert "unknown_field" in error_msg.lower() or "unknown" in error_msg.lower()


# =============================================================================
# PHASE 1 TDD: Tests for Workflow/WorkflowStep New Params (ALL GREEN target)
# =============================================================================

class TestWorkflowNewParams:
    """Test Workflow supports all consolidated params like Agents."""
    
    def test_workflow_has_autonomy_param(self):
        """Workflow should have autonomy param."""
        from praisonaiagents.workflows.workflows import Workflow
        
        # Should accept autonomy param without error
        workflow = Workflow(steps=[], autonomy=True)
        assert hasattr(workflow, 'autonomy') or hasattr(workflow, '_autonomy_config')
    
    def test_workflow_has_knowledge_param(self):
        """Workflow should have knowledge param."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(steps=[], knowledge=["docs/"])
        assert hasattr(workflow, 'knowledge') or hasattr(workflow, '_knowledge_config')
    
    def test_workflow_has_guardrails_param(self):
        """Workflow should have guardrails param."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(steps=[], guardrails=True)
        assert hasattr(workflow, 'guardrails') or hasattr(workflow, '_guardrails_config')
    
    def test_workflow_has_web_param(self):
        """Workflow should have web param."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(steps=[], web=True)
        assert hasattr(workflow, 'web') or hasattr(workflow, '_web_config')
    
    def test_workflow_has_reflection_param(self):
        """Workflow should have reflection param."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(steps=[], reflection=True)
        assert hasattr(workflow, 'reflection') or hasattr(workflow, '_reflection_config')


class TestWorkflowStepNewParams:
    """Test WorkflowStep supports all consolidated params."""
    
    def test_workflowstep_has_autonomy_param(self):
        """WorkflowStep should have autonomy param."""
        from praisonaiagents.workflows.workflows import WorkflowStep
        
        step = WorkflowStep(name="test", autonomy=True)
        assert hasattr(step, 'autonomy') or hasattr(step, '_autonomy_config')
    
    def test_workflowstep_has_knowledge_param(self):
        """WorkflowStep should have knowledge param."""
        from praisonaiagents.workflows.workflows import WorkflowStep
        
        step = WorkflowStep(name="test", knowledge=["docs/"])
        assert hasattr(step, 'knowledge') or hasattr(step, '_knowledge_config')
    
    def test_workflowstep_has_web_param(self):
        """WorkflowStep should have web param."""
        from praisonaiagents.workflows.workflows import WorkflowStep
        
        step = WorkflowStep(name="test", web=True)
        assert hasattr(step, 'web') or hasattr(step, '_web_config')
    
    def test_workflowstep_has_reflection_param(self):
        """WorkflowStep should have reflection param."""
        from praisonaiagents.workflows.workflows import WorkflowStep
        
        step = WorkflowStep(name="test", reflection=True)
        assert hasattr(step, 'reflection') or hasattr(step, '_reflection_config')


class TestWorkflowPropagation:
    """Test workflow defaults propagate to steps/agents."""
    
    def test_workflow_defaults_available_for_steps(self):
        """Workflow-level configs should be accessible for step propagation."""
        from praisonaiagents.workflows.workflows import Workflow
        
        workflow = Workflow(
            steps=[],
            knowledge=["docs/"],
            web=True,
            guardrails=True,
        )
        
        # Workflow should store resolved configs for propagation
        assert workflow.knowledge is not None or hasattr(workflow, '_knowledge_config')
        assert workflow.web is not None or hasattr(workflow, '_web_config')
        assert workflow.guardrails is not None or hasattr(workflow, '_guardrails_config')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
