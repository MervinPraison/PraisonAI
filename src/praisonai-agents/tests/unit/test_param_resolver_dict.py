"""
Unit tests for Dict support in the canonical param resolver.

Tests the NEW_FEATURE_SPEC:
1. dict → config success
2. dict with unknown key → error
3. dict where no config class → error

Also tests:
- Precedence ordering (Instance > Config > Dict > Array > String > Bool > Default)
- Array semantics unchanged
"""

import pytest
from dataclasses import dataclass
from typing import Optional, List


# =============================================================================
# Test Config Classes (mimicking real config classes)
# =============================================================================

@dataclass
class TestOutputConfig:
    """Test config for output parameter."""
    verbose: bool = False
    stream: bool = True
    markdown: bool = False


@dataclass
class TestExecutionConfig:
    """Test config for execution parameter."""
    max_iter: int = 10
    max_retries: int = 3


@dataclass
class TestMemoryConfig:
    """Test config for memory parameter."""
    backend: str = "file"
    user_id: Optional[str] = None


@dataclass
class TestContextConfig:
    """Test config for context parameter with list field."""
    from_steps: Optional[List[str]] = None
    retain_full: bool = True


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def resolver():
    """Import the canonical resolver."""
    from praisonaiagents.config.param_resolver import resolve, ArrayMode
    return resolve, ArrayMode


@pytest.fixture
def output_presets():
    """Sample presets for output parameter."""
    return {
        "verbose": {"verbose": True, "stream": True, "markdown": True},
        "silent": {"verbose": False, "stream": False, "markdown": False},
        "minimal": {"verbose": False, "stream": True, "markdown": False},
    }


# =============================================================================
# DICT SUCCESS TESTS
# =============================================================================

class TestDictSuccess:
    """Test dict → config conversion success cases."""
    
    def test_dict_to_config_basic(self, resolver):
        """Dict with valid keys converts to config."""
        resolve, _ = resolver
        result = resolve(
            value={"verbose": True, "stream": False},
            param_name="output",
            config_class=TestOutputConfig,
        )
        assert isinstance(result, TestOutputConfig)
        assert result.verbose is True
        assert result.stream is False
        assert result.markdown is False  # default
    
    def test_dict_to_config_all_fields(self, resolver):
        """Dict with all fields converts correctly."""
        resolve, _ = resolver
        result = resolve(
            value={"verbose": True, "stream": True, "markdown": True},
            param_name="output",
            config_class=TestOutputConfig,
        )
        assert isinstance(result, TestOutputConfig)
        assert result.verbose is True
        assert result.stream is True
        assert result.markdown is True
    
    def test_dict_to_config_partial_fields(self, resolver):
        """Dict with partial fields uses defaults for missing."""
        resolve, _ = resolver
        result = resolve(
            value={"max_iter": 50},
            param_name="execution",
            config_class=TestExecutionConfig,
        )
        assert isinstance(result, TestExecutionConfig)
        assert result.max_iter == 50
        assert result.max_retries == 3  # default
    
    def test_dict_to_config_empty_dict(self, resolver):
        """Empty dict creates config with all defaults."""
        resolve, _ = resolver
        result = resolve(
            value={},
            param_name="output",
            config_class=TestOutputConfig,
        )
        assert isinstance(result, TestOutputConfig)
        assert result.verbose is False
        assert result.stream is True
        assert result.markdown is False


# =============================================================================
# DICT ERROR TESTS - Unknown Keys
# =============================================================================

class TestDictUnknownKeyError:
    """Test dict with unknown key raises helpful error."""
    
    def test_unknown_key_raises_typeerror(self, resolver):
        """Unknown key in dict raises TypeError with helpful message."""
        resolve, _ = resolver
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"verbose": True, "unknown_key": "value"},
                param_name="output",
                config_class=TestOutputConfig,
            )
        error_msg = str(exc_info.value)
        assert "Unknown keys for output" in error_msg
        assert "unknown_key" in error_msg
        assert "Valid keys" in error_msg
    
    def test_multiple_unknown_keys(self, resolver):
        """Multiple unknown keys are all reported."""
        resolve, _ = resolver
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"foo": 1, "bar": 2, "verbose": True},
                param_name="output",
                config_class=TestOutputConfig,
            )
        error_msg = str(exc_info.value)
        assert "foo" in error_msg or "bar" in error_msg
    
    def test_typo_in_key_raises_error(self, resolver):
        """Typo in key name raises error with valid keys listed."""
        resolve, _ = resolver
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"verbos": True},  # typo: verbos instead of verbose
                param_name="output",
                config_class=TestOutputConfig,
            )
        error_msg = str(exc_info.value)
        assert "verbos" in error_msg
        assert "verbose" in error_msg  # valid key should be shown


# =============================================================================
# DICT ERROR TESTS - No Config Class
# =============================================================================

class TestDictNoConfigClassError:
    """Test dict where no config class is defined raises error."""
    
    def test_dict_without_config_class_raises_typeerror(self, resolver):
        """Dict input without config_class raises TypeError."""
        resolve, _ = resolver
        with pytest.raises(TypeError) as exc_info:
            resolve(
                value={"some": "dict"},
                param_name="custom_param",
                config_class=None,
            )
        error_msg = str(exc_info.value)
        assert "Dict input not supported" in error_msg
        assert "custom_param" in error_msg
        assert "no config class" in error_msg


# =============================================================================
# PRECEDENCE TESTS
# =============================================================================

class TestPrecedence:
    """Test precedence ordering: Instance > Config > Dict > Array > String > Bool > Default."""
    
    def test_instance_beats_dict(self, resolver):
        """Instance check takes precedence over dict."""
        resolve, _ = resolver
        
        class CustomInstance:
            def __init__(self):
                self.custom = True
        
        instance = CustomInstance()
        result = resolve(
            value=instance,
            param_name="test",
            config_class=TestOutputConfig,
            instance_check=lambda v: isinstance(v, CustomInstance),
        )
        assert result is instance
    
    def test_config_instance_beats_dict(self, resolver):
        """Config instance takes precedence over dict conversion."""
        resolve, _ = resolver
        config = TestOutputConfig(verbose=True, stream=False)
        result = resolve(
            value=config,
            param_name="output",
            config_class=TestOutputConfig,
        )
        assert result is config
    
    def test_dict_beats_string(self, resolver, output_presets):
        """Dict takes precedence over string preset lookup."""
        resolve, _ = resolver
        # Dict should be processed, not treated as string
        result = resolve(
            value={"verbose": False, "stream": False},
            param_name="output",
            config_class=TestOutputConfig,
            presets=output_presets,
        )
        assert isinstance(result, TestOutputConfig)
        assert result.verbose is False
        assert result.stream is False
    
    def test_dict_beats_bool(self, resolver):
        """Dict takes precedence over bool handling."""
        resolve, _ = resolver
        # Dict should be processed, not treated as bool
        result = resolve(
            value={"verbose": True},
            param_name="output",
            config_class=TestOutputConfig,
        )
        assert isinstance(result, TestOutputConfig)
        assert result.verbose is True
    
    def test_bool_true_creates_default_config(self, resolver):
        """Bool True creates default config instance."""
        resolve, _ = resolver
        result = resolve(
            value=True,
            param_name="output",
            config_class=TestOutputConfig,
        )
        assert isinstance(result, TestOutputConfig)
        assert result.verbose is False  # default
    
    def test_bool_false_returns_none(self, resolver):
        """Bool False returns None (disabled)."""
        resolve, _ = resolver
        result = resolve(
            value=False,
            param_name="output",
            config_class=TestOutputConfig,
        )
        assert result is None
    
    def test_none_returns_default(self, resolver):
        """None returns the default value."""
        resolve, _ = resolver
        default = TestOutputConfig(verbose=True)
        result = resolve(
            value=None,
            param_name="output",
            config_class=TestOutputConfig,
            default=default,
        )
        assert result is default


# =============================================================================
# ARRAY SEMANTICS UNCHANGED TESTS
# =============================================================================

class TestArraySemanticsUnchanged:
    """Test that array semantics remain unchanged."""
    
    def test_preset_override_array(self, resolver, output_presets):
        """[preset, {overrides}] pattern still works."""
        resolve, ArrayMode = resolver
        result = resolve(
            value=["verbose", {"stream": False}],
            param_name="output",
            config_class=TestOutputConfig,
            presets=output_presets,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        assert isinstance(result, TestOutputConfig)
        assert result.verbose is True  # from preset
        assert result.stream is False  # overridden
    
    def test_step_names_array(self, resolver):
        """List of step names creates config with from_steps."""
        resolve, ArrayMode = resolver
        result = resolve(
            value=["step1", "step2"],
            param_name="context",
            config_class=TestContextConfig,
            array_mode=ArrayMode.STEP_NAMES,
        )
        assert isinstance(result, TestContextConfig)
        assert result.from_steps == ["step1", "step2"]
    
    def test_passthrough_array(self, resolver):
        """Passthrough mode returns list as-is."""
        resolve, ArrayMode = resolver
        input_list = ["a", "b", "c"]
        result = resolve(
            value=input_list,
            param_name="hooks",
            config_class=None,
            array_mode=ArrayMode.PASSTHROUGH,
        )
        assert result == input_list
    
    def test_empty_array_returns_none(self, resolver):
        """Empty array returns None (disabled)."""
        resolve, ArrayMode = resolver
        result = resolve(
            value=[],
            param_name="output",
            config_class=TestOutputConfig,
            array_mode=ArrayMode.PRESET_OVERRIDE,
        )
        assert result is None


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestHelperFunctions:
    """Test helper functions for dict validation."""
    
    def test_get_config_fields(self):
        """_get_config_fields returns field names."""
        from praisonaiagents.config.param_resolver import _get_config_fields
        fields = _get_config_fields(TestOutputConfig)
        assert "verbose" in fields
        assert "stream" in fields
        assert "markdown" in fields
    
    def test_validate_dict_keys_valid(self):
        """_validate_dict_keys returns empty list for valid keys."""
        from praisonaiagents.config.param_resolver import _validate_dict_keys
        unknown = _validate_dict_keys(
            {"verbose": True, "stream": False},
            TestOutputConfig
        )
        assert unknown == []
    
    def test_validate_dict_keys_invalid(self):
        """_validate_dict_keys returns unknown keys."""
        from praisonaiagents.config.param_resolver import _validate_dict_keys
        unknown = _validate_dict_keys(
            {"verbose": True, "bad_key": "value"},
            TestOutputConfig
        )
        assert "bad_key" in unknown
    
    def test_get_example_dict(self):
        """_get_example_dict returns example snippet."""
        from praisonaiagents.config.param_resolver import _get_example_dict
        example = _get_example_dict(TestOutputConfig)
        assert "verbose" in example or "stream" in example


# =============================================================================
# STRING PRESET TESTS (regression)
# =============================================================================

class TestStringPresets:
    """Test string preset resolution still works."""
    
    def test_string_preset_resolves(self, resolver, output_presets):
        """String preset name resolves to config."""
        resolve, _ = resolver
        result = resolve(
            value="verbose",
            param_name="output",
            config_class=TestOutputConfig,
            presets=output_presets,
        )
        assert isinstance(result, TestOutputConfig)
        assert result.verbose is True
    
    def test_invalid_preset_raises_error(self, resolver, output_presets):
        """Invalid preset name raises helpful error."""
        resolve, _ = resolver
        with pytest.raises(ValueError) as exc_info:
            resolve(
                value="invalid_preset",
                param_name="output",
                config_class=TestOutputConfig,
                presets=output_presets,
            )
        error_msg = str(exc_info.value)
        assert "invalid_preset" in error_msg
