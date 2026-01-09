"""
TDD Tests for Agent-Centric Feature Enhancements.

Tests for:
1. Guardrail presets with policy:strict, pii:redact support
2. Context string/array presets
3. Caching string presets
4. Knowledge presets (auto)

Written FIRST (TDD approach) to define expected behavior.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Callable, Tuple


# =============================================================================
# Test Fixtures - Mock Config Classes
# =============================================================================

@dataclass
class MockGuardrailConfig:
    """Mock guardrail config for testing."""
    validator: Optional[Callable] = None
    llm_validator: Optional[str] = None
    max_retries: int = 3
    on_fail: str = "retry"
    policies: List[str] = field(default_factory=list)


@dataclass
class MockContextConfig:
    """Mock context config for testing."""
    strategy: str = "sliding_window"
    threshold: float = 0.8
    max_tokens: Optional[int] = None


@dataclass
class MockCachingConfig:
    """Mock caching config for testing."""
    enabled: bool = True
    prompt_caching: Optional[bool] = None


@dataclass
class MockKnowledgeConfig:
    """Mock knowledge config for testing."""
    sources: List[str] = field(default_factory=list)
    auto_discover: bool = False
    embedder: str = "openai"


# =============================================================================
# Test: Guardrail Presets
# =============================================================================

class TestGuardrailPresets:
    """Test guardrail preset parsing."""
    
    def test_guardrail_string_preset_strict(self):
        """String 'strict' should apply strict preset."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "strict": {"max_retries": 5, "on_fail": "raise"},
            "permissive": {"max_retries": 1, "on_fail": "skip"},
        }
        
        result = resolve(
            value="strict",
            param_name="guardrails",
            config_class=MockGuardrailConfig,
            presets=presets,
        )
        assert isinstance(result, MockGuardrailConfig)
        assert result.max_retries == 5
        assert result.on_fail == "raise"
    
    def test_guardrail_string_preset_permissive(self):
        """String 'permissive' should apply permissive preset."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "strict": {"max_retries": 5, "on_fail": "raise"},
            "permissive": {"max_retries": 1, "on_fail": "skip"},
        }
        
        result = resolve(
            value="permissive",
            param_name="guardrails",
            config_class=MockGuardrailConfig,
            presets=presets,
        )
        assert result.max_retries == 1
        assert result.on_fail == "skip"
    
    def test_guardrail_array_preset_with_overrides(self):
        """Array ['strict', {overrides}] should apply preset + overrides."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "strict": {"max_retries": 5, "on_fail": "raise"},
        }
        
        result = resolve(
            value=["strict", {"max_retries": 10}],
            param_name="guardrails",
            config_class=MockGuardrailConfig,
            presets=presets,
            array_mode="preset_override",
        )
        assert result.max_retries == 10  # Override
        assert result.on_fail == "raise"  # From preset
    
    def test_guardrail_long_string_as_llm_prompt(self):
        """Long string should be treated as LLM validator prompt."""
        # This tests that strings not matching presets are treated as prompts
        # The actual implementation will check string length or content
        prompt = "Ensure the response is safe, helpful, and does not contain harmful content."
        
        # This should NOT raise an error - long strings are LLM prompts
        # The resolver should return the string as-is or wrap in config
        from praisonaiagents.config.param_resolver import resolve
        
        # With no presets, string should be treated as LLM prompt
        result = resolve(
            value=prompt,
            param_name="guardrails",
            config_class=MockGuardrailConfig,
            presets={},  # No presets
            string_mode="llm_prompt",
        )
        # Should create config with llm_validator set
        assert isinstance(result, MockGuardrailConfig)
        assert result.llm_validator == prompt


# =============================================================================
# Test: Context String/Array Presets
# =============================================================================

class TestContextPresets:
    """Test context preset parsing."""
    
    def test_context_string_preset_sliding_window(self):
        """String 'sliding_window' should apply preset."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "sliding_window": {"strategy": "sliding_window"},
            "summarize": {"strategy": "summarize"},
            "truncate": {"strategy": "truncate"},
        }
        
        result = resolve(
            value="sliding_window",
            param_name="context",
            config_class=MockContextConfig,
            presets=presets,
        )
        assert isinstance(result, MockContextConfig)
        assert result.strategy == "sliding_window"
    
    def test_context_string_preset_summarize(self):
        """String 'summarize' should apply preset."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "sliding_window": {"strategy": "sliding_window"},
            "summarize": {"strategy": "summarize"},
            "truncate": {"strategy": "truncate"},
        }
        
        result = resolve(
            value="summarize",
            param_name="context",
            config_class=MockContextConfig,
            presets=presets,
        )
        assert result.strategy == "summarize"
    
    def test_context_array_preset_with_overrides(self):
        """Array ['sliding_window', {threshold: 0.7}] should apply preset + overrides."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "sliding_window": {"strategy": "sliding_window", "threshold": 0.8},
        }
        
        result = resolve(
            value=["sliding_window", {"threshold": 0.7}],
            param_name="context",
            config_class=MockContextConfig,
            presets=presets,
            array_mode="preset_override",
        )
        assert result.strategy == "sliding_window"
        assert result.threshold == 0.7  # Override
    
    def test_context_bool_true_returns_default_config(self):
        """Bool True should return default context config."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=True,
            param_name="context",
            config_class=MockContextConfig,
        )
        assert isinstance(result, MockContextConfig)
        assert result.strategy == "sliding_window"  # Default


# =============================================================================
# Test: Caching String Presets
# =============================================================================

class TestCachingPresets:
    """Test caching preset parsing."""
    
    def test_caching_string_preset_enabled(self):
        """String 'enabled' should enable caching."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "enabled": {"enabled": True, "prompt_caching": None},
            "disabled": {"enabled": False, "prompt_caching": None},
            "prompt": {"enabled": True, "prompt_caching": True},
        }
        
        result = resolve(
            value="enabled",
            param_name="caching",
            config_class=MockCachingConfig,
            presets=presets,
        )
        assert isinstance(result, MockCachingConfig)
        assert result.enabled is True
    
    def test_caching_string_preset_disabled(self):
        """String 'disabled' should disable caching."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "enabled": {"enabled": True, "prompt_caching": None},
            "disabled": {"enabled": False, "prompt_caching": None},
            "prompt": {"enabled": True, "prompt_caching": True},
        }
        
        result = resolve(
            value="disabled",
            param_name="caching",
            config_class=MockCachingConfig,
            presets=presets,
        )
        assert result.enabled is False
    
    def test_caching_string_preset_prompt(self):
        """String 'prompt' should enable prompt caching."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "enabled": {"enabled": True, "prompt_caching": None},
            "disabled": {"enabled": False, "prompt_caching": None},
            "prompt": {"enabled": True, "prompt_caching": True},
        }
        
        result = resolve(
            value="prompt",
            param_name="caching",
            config_class=MockCachingConfig,
            presets=presets,
        )
        assert result.enabled is True
        assert result.prompt_caching is True
    
    def test_caching_bool_true_enables(self):
        """Bool True should enable caching with defaults."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=True,
            param_name="caching",
            config_class=MockCachingConfig,
        )
        assert isinstance(result, MockCachingConfig)
        assert result.enabled is True
    
    def test_caching_bool_false_disables(self):
        """Bool False should return None (disabled)."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=False,
            param_name="caching",
            config_class=MockCachingConfig,
        )
        assert result is None


# =============================================================================
# Test: Knowledge Presets
# =============================================================================

class TestKnowledgePresets:
    """Test knowledge preset parsing."""
    
    def test_knowledge_string_preset_auto(self):
        """String 'auto' should enable auto-discovery."""
        from praisonaiagents.config.param_resolver import resolve
        
        presets = {
            "auto": {"auto_discover": True},
        }
        
        result = resolve(
            value="auto",
            param_name="knowledge",
            config_class=MockKnowledgeConfig,
            presets=presets,
        )
        assert isinstance(result, MockKnowledgeConfig)
        assert result.auto_discover is True
    
    def test_knowledge_path_string(self):
        """Path string should be treated as source."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value="docs/",
            param_name="knowledge",
            config_class=MockKnowledgeConfig,
            string_mode="path_as_source",
        )
        assert isinstance(result, MockKnowledgeConfig)
        assert "docs/" in result.sources
    
    def test_knowledge_array_sources(self):
        """Array of paths should be sources list."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=["docs/", "data.pdf", "https://example.com"],
            param_name="knowledge",
            config_class=MockKnowledgeConfig,
            array_mode="sources",
        )
        assert result.sources == ["docs/", "data.pdf", "https://example.com"]
    
    def test_knowledge_bool_true_returns_default(self):
        """Bool True should return default config."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=True,
            param_name="knowledge",
            config_class=MockKnowledgeConfig,
        )
        assert isinstance(result, MockKnowledgeConfig)


# =============================================================================
# Test: Policy String Parsing (policy:strict, pii:redact)
# =============================================================================

class TestPolicyStringParsing:
    """Test policy: prefix string parsing for guardrails."""
    
    def test_policy_prefix_detection(self):
        """Strings with 'policy:' prefix should be detected."""
        from praisonaiagents.config.parse_utils import is_policy_string
        
        assert is_policy_string("policy:strict") is True
        assert is_policy_string("policy:permissive") is True
        assert is_policy_string("pii:redact") is True
        assert is_policy_string("pii:detect") is True
        assert is_policy_string("strict") is False
        assert is_policy_string("some long prompt") is False
    
    def test_policy_string_parsing(self):
        """Policy strings should be parsed into type and action."""
        from praisonaiagents.config.parse_utils import parse_policy_string
        
        policy_type, action = parse_policy_string("policy:strict")
        assert policy_type == "policy"
        assert action == "strict"
        
        policy_type, action = parse_policy_string("pii:redact")
        assert policy_type == "pii"
        assert action == "redact"
    
    def test_guardrail_policy_array(self):
        """Array of policy strings should create combined config."""
        from praisonaiagents.config.param_resolver import resolve_guardrail_policies
        
        result = resolve_guardrail_policies(
            ["policy:strict", "pii:redact"],
            MockGuardrailConfig,
        )
        assert isinstance(result, MockGuardrailConfig)
        assert "policy:strict" in result.policies
        assert "pii:redact" in result.policies


# =============================================================================
# Test: Performance - No Impact on Happy Path
# =============================================================================

class TestPerformanceNoImpact:
    """Test that new features don't impact performance on happy path."""
    
    def test_bool_resolution_is_o1(self):
        """Bool resolution should be O(1) - no string parsing."""
        from praisonaiagents.config.param_resolver import resolve
        
        # Bool True should immediately return config without any string parsing
        result = resolve(
            value=True,
            param_name="context",
            config_class=MockContextConfig,
            presets={"sliding_window": {"strategy": "sliding_window"}},  # Presets exist but not checked
        )
        assert isinstance(result, MockContextConfig)
    
    def test_config_instance_is_o1(self):
        """Config instance should be returned as-is - O(1)."""
        from praisonaiagents.config.param_resolver import resolve
        
        config = MockContextConfig(strategy="summarize", threshold=0.5)
        result = resolve(
            value=config,
            param_name="context",
            config_class=MockContextConfig,
            presets={"sliding_window": {"strategy": "sliding_window"}},
        )
        assert result is config  # Same object, not copied
    
    def test_none_is_o1(self):
        """None should return default immediately - O(1)."""
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=None,
            param_name="context",
            config_class=MockContextConfig,
            default=None,
        )
        assert result is None


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Test that existing patterns still work."""
    
    def test_guardrail_callable_still_works(self):
        """Callable guardrail should still work."""
        def my_validator(output) -> Tuple[bool, Any]:
            return True, output
        
        # Callable should be passed through, not treated as preset
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=my_validator,
            param_name="guardrails",
            config_class=MockGuardrailConfig,
            instance_check=lambda v: callable(v),
        )
        assert result is my_validator
    
    def test_context_manager_instance_still_works(self):
        """ContextManager instance should still work."""
        class MockContextManager:
            def get_context(self):
                return "context"
        
        manager = MockContextManager()
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=manager,
            param_name="context",
            config_class=MockContextConfig,
            instance_check=lambda v: hasattr(v, 'get_context'),
        )
        assert result is manager
    
    def test_caching_config_still_works(self):
        """CachingConfig instance should still work."""
        config = MockCachingConfig(enabled=True, prompt_caching=True)
        from praisonaiagents.config.param_resolver import resolve
        
        result = resolve(
            value=config,
            param_name="caching",
            config_class=MockCachingConfig,
        )
        assert result is config
