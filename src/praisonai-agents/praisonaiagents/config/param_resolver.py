"""
Unified Parameter Resolver for Consolidated Parameters.

Implements the precedence rules: Instance > Config > Dict > Array > String > Bool > Default

This is the SINGLE, DRY resolver used by:
- Agent
- Agents
- Workflow
- Task

Performance: O(1) happy path. Typo suggestions only on error path.
"""

from typing import Any, Callable, Dict, Optional, Set, Type, Union
import inspect

from .parse_utils import (
    detect_url_scheme,
    is_path_like,
    make_preset_error,
    merge_config_with_overrides,
)


# =============================================================================
# Array Modes
# =============================================================================

class ArrayMode:
    """Array parsing modes."""
    PASSTHROUGH = "passthrough"  # Return list as-is (e.g., hooks)
    SOURCES = "sources"  # List of source paths/URLs
    SOURCES_WITH_CONFIG = "sources_with_config"  # Sources + optional config dict at end
    PRESET_OVERRIDE = "preset_override"  # [preset, {overrides}]
    SINGLE_OR_LIST = "single_or_list"  # Single item treated as scalar, else list
    STEP_NAMES = "step_names"  # List of step names (workflow context/routing)


# =============================================================================
# Main Resolver Function
# =============================================================================

def resolve(
    value: Any,
    param_name: str,
    config_class: Optional[Type] = None,
    presets: Optional[Dict[str, Any]] = None,
    default: Any = None,
    instance_check: Optional[Callable[[Any], bool]] = None,
    url_schemes: Optional[Dict[str, str]] = None,
    array_mode: Optional[str] = None,
    string_mode: Optional[str] = None,
) -> Any:
    """
    Resolve a consolidated parameter following precedence rules:
    Instance > Config > Array > Dict > String > Bool > Default
    
    Args:
        value: The parameter value
        param_name: Name of the parameter (for error messages)
        config_class: Expected config dataclass type
        presets: Dict mapping preset strings to config dicts or instances
        default: Default value if None/unset
        instance_check: Function to check if value is an instance
        url_schemes: Dict mapping URL schemes to backend names
        array_mode: How to handle array values (see ArrayMode)
        string_mode: How to handle string values ("path_as_source", etc.)
        
    Returns:
        Resolved config object or value
        
    Raises:
        ValueError: If value is invalid with helpful error message
    """
    # =========================================================================
    # 1. None/unset -> Default
    # =========================================================================
    if value is None:
        return default
    
    # =========================================================================
    # 2. Instance check (highest precedence)
    # =========================================================================
    if instance_check and instance_check(value):
        return value
    
    # =========================================================================
    # 3. Config dataclass check
    # =========================================================================
    if config_class and isinstance(value, config_class):
        return value
    
    # =========================================================================
    # 4. Array handling (BEFORE Dict per AC-1 precedence)
    # =========================================================================
    if isinstance(value, (list, tuple)):
        return _resolve_array(
            value=value,
            param_name=param_name,
            config_class=config_class,
            presets=presets,
            url_schemes=url_schemes,
            array_mode=array_mode,
        )
    
    # =========================================================================
    # 5. Dict -> convert to config (STRICT validation)
    # =========================================================================
    if isinstance(value, dict):
        if config_class:
            # Validate keys BEFORE construction for helpful errors
            unknown_keys = _validate_dict_keys(value, config_class)
            if unknown_keys:
                valid_fields = _get_config_fields(config_class)
                example = _get_example_dict(config_class)
                raise TypeError(
                    f"Unknown keys for {param_name}: {unknown_keys}. "
                    f"Valid keys: {valid_fields}. "
                    f"Example: {param_name}={{{example}}}"
                )
            try:
                return config_class(**value)
            except TypeError as e:
                raise TypeError(
                    f"Invalid {param_name} dict: {e}. "
                    f"Valid fields: {_get_config_fields(config_class)}"
                )
        else:
            # No config class - dict input not supported
            raise TypeError(
                f"Dict input not supported for {param_name} (no config class defined). "
                f"Use a supported type: bool, str, or instance."
            )
    
    # =========================================================================
    # 6. String handling
    # =========================================================================
    if isinstance(value, str):
        return _resolve_string(
            value=value,
            param_name=param_name,
            config_class=config_class,
            presets=presets,
            url_schemes=url_schemes,
            string_mode=string_mode,
        )
    
    # =========================================================================
    # 7. Bool handling
    # =========================================================================
    if isinstance(value, bool):
        if value:
            # True -> return default config instance
            if config_class:
                return config_class()
            return True
        else:
            # False -> disabled
            return None
    
    # =========================================================================
    # 8. Fallback to default
    # =========================================================================
    return default


# =============================================================================
# Array Resolution
# =============================================================================

def _resolve_array(
    value: Union[list, tuple],
    param_name: str,
    config_class: Optional[Type],
    presets: Optional[Dict[str, Any]],
    url_schemes: Optional[Dict[str, str]],
    array_mode: Optional[str],
) -> Any:
    """Resolve array value based on array_mode."""
    
    # Empty array -> disabled
    if not value:
        return None
    
    # Passthrough mode - return list as-is
    if array_mode == ArrayMode.PASSTHROUGH:
        return list(value)
    
    # Step names mode - create config with list field
    if array_mode == ArrayMode.STEP_NAMES:
        if config_class:
            # Determine field name based on param
            if param_name == "context":
                return config_class(from_steps=list(value))
            elif param_name == "routing":
                return config_class(next_steps=list(value))
        return list(value)
    
    # Sources mode - list of source paths/URLs
    if array_mode == ArrayMode.SOURCES:
        if config_class:
            return config_class(sources=list(value))
        return list(value)
    
    # Sources with config - sources + optional config dict at end
    if array_mode == ArrayMode.SOURCES_WITH_CONFIG:
        sources = []
        config_override = {}
        
        for item in value:
            if isinstance(item, dict):
                config_override = item
                # If dict has sources, merge them
                if "sources" in config_override:
                    sources.extend(config_override.pop("sources"))
            else:
                sources.append(item)
        
        if config_class:
            return config_class(sources=sources, **config_override)
        return sources
    
    # Single or list mode - SINGLE item only, multiple items raise error
    if array_mode == ArrayMode.SINGLE_OR_LIST:
        if len(value) == 1:
            single_value = value[0]
            # Check if single item is a URL
            if isinstance(single_value, str) and url_schemes:
                scheme = detect_url_scheme(single_value)
                if scheme and scheme in url_schemes:
                    return _resolve_url(single_value, config_class, url_schemes)
            # Check if single item is a preset
            if isinstance(single_value, str) and presets and single_value in presets:
                return _apply_preset(single_value, presets, config_class)
            # Single non-preset string - try as URL or return as-is
            if isinstance(single_value, str):
                if config_class:
                    return config_class()
                return single_value
        # Multiple items - ERROR (not allowed for SINGLE_OR_LIST mode)
        raise TypeError(
            f"Multiple values not allowed for {param_name}. "
            f"Use a single value: {param_name}='preset' or {param_name}='url://...' "
            f"Got {len(value)} items: {value}"
        )
    
    # Preset override mode - [preset, {overrides}] or [preset]
    if array_mode == ArrayMode.PRESET_OVERRIDE:
        if not value:
            return None
        
        first = value[0]
        
        # First item should be a preset string
        if isinstance(first, str):
            # Get base config from preset
            if presets and first in presets:
                base_config = _apply_preset(first, presets, config_class)
            elif presets:
                # Invalid preset
                raise make_preset_error(param_name, first, presets.keys())
            else:
                # No presets defined, treat as value
                if config_class:
                    base_config = config_class()
                else:
                    base_config = None
            
            # Apply overrides if present
            if len(value) >= 2 and isinstance(value[-1], dict):
                overrides = value[-1]
                if base_config and config_class:
                    return merge_config_with_overrides(base_config, overrides, config_class)
            
            return base_config
    
    # Default: treat as sources list
    if config_class:
        # Check if all items are strings (sources)
        if all(isinstance(item, str) for item in value):
            return config_class(sources=list(value))
    
    return list(value)


# =============================================================================
# String Resolution
# =============================================================================

def _resolve_string(
    value: str,
    param_name: str,
    config_class: Optional[Type],
    presets: Optional[Dict[str, str]],
    url_schemes: Optional[Dict[str, str]],
    string_mode: Optional[str],
) -> Any:
    """Resolve string value."""
    
    # Check for URL first
    if url_schemes:
        scheme = detect_url_scheme(value)
        if scheme:
            if scheme in url_schemes:
                return _resolve_url(value, config_class, url_schemes)
            else:
                # Unknown scheme - raise helpful error
                valid_schemes = ", ".join(sorted(url_schemes.keys()))
                raise ValueError(
                    f"Unsupported URL scheme '{scheme}' for {param_name}. "
                    f"Supported: {valid_schemes}"
                )
    
    # Check for preset
    if presets:
        # Case-insensitive lookup
        value_lower = value.lower()
        for preset_key in presets:
            if preset_key.lower() == value_lower:
                return _apply_preset(preset_key, presets, config_class)
        
        # Not a valid preset - raise helpful error
        raise make_preset_error(param_name, value, presets.keys(), url_schemes)
    
    # Path as source mode
    if string_mode == "path_as_source":
        if is_path_like(value) and config_class:
            return config_class(sources=[value])
    
    # LLM model name mode (for planning)
    if string_mode == "llm_model":
        if config_class:
            return config_class(llm=value)
    
    # LLM prompt mode (for guardrails) - long strings are LLM validator prompts
    if string_mode == "llm_prompt":
        if config_class:
            # Check if config has llm_validator field
            if hasattr(config_class, '__dataclass_fields__') and 'llm_validator' in config_class.__dataclass_fields__:
                return config_class(llm_validator=value)
        return value
    
    # If no presets and no URL schemes, and we have a config class,
    # try to use the string as a single source
    if config_class and is_path_like(value):
        try:
            return config_class(sources=[value])
        except TypeError:
            pass
    
    # Fallback - return string as-is if no config class
    if not config_class:
        return value
    
    # Unknown string - if we have presets, this is an error
    if presets:
        raise make_preset_error(param_name, value, presets.keys(), url_schemes)
    
    # No presets defined - return default config
    return config_class() if config_class else value


def _resolve_url(
    url: str,
    config_class: Optional[Type],
    url_schemes: Dict[str, str],
) -> Any:
    """Resolve a URL string to config."""
    scheme = detect_url_scheme(url)
    if not scheme or scheme not in url_schemes:
        raise ValueError(f"Invalid URL: {url}")
    
    backend = url_schemes[scheme]
    
    if config_class:
        return config_class(backend=backend, config={"url": url})
    
    return {"backend": backend, "url": url}


def _apply_preset(
    preset_name: str,
    presets: Dict[str, Any],
    config_class: Optional[Type],
) -> Any:
    """Apply a preset to create a config instance."""
    preset_value = presets.get(preset_name)
    
    if preset_value is None:
        return None
    
    # If preset is already a config instance, return it
    if config_class and isinstance(preset_value, config_class):
        return preset_value
    
    # If preset is a dict, convert to config
    if isinstance(preset_value, dict) and config_class:
        return config_class(**preset_value)
    
    # Return preset value as-is
    return preset_value


def _get_config_fields(config_class: Type) -> str:
    """Get field names from a config class for error messages."""
    if hasattr(config_class, '__dataclass_fields__'):
        return ", ".join(config_class.__dataclass_fields__.keys())
    return "unknown"


def _get_valid_keys(config_class: Type) -> Optional[Set[str]]:
    """
    Get valid keys from a config class.
    
    Supports:
    - Dataclasses (via __dataclass_fields__)
    - Regular classes (via __init__ signature)
    - Classes with __annotations__
    
    Returns:
        Set of valid key names, or None if cannot determine.
    """
    # 1. Dataclass fields (most common)
    if hasattr(config_class, '__dataclass_fields__'):
        return set(config_class.__dataclass_fields__.keys())
    
    # 2. __init__ signature parameters
    try:
        sig = inspect.signature(config_class.__init__)
        params = set(sig.parameters.keys()) - {'self'}
        if params:
            return params
    except (ValueError, TypeError):
        pass
    
    # 3. Class annotations
    if hasattr(config_class, '__annotations__'):
        return set(config_class.__annotations__.keys())
    
    # Cannot determine valid keys
    return None


def _validate_dict_keys(value: dict, config_class: Type) -> list:
    """
    Validate dict keys against config class fields.
    Returns list of unknown keys (empty if all valid).
    O(n) where n = number of keys in dict (typically small).
    
    Works for both dataclasses and regular classes.
    """
    valid_keys = _get_valid_keys(config_class)
    if valid_keys is None:
        return []  # Cannot validate, allow all keys
    
    provided_keys = set(value.keys())
    unknown = provided_keys - valid_keys
    return list(unknown)


def _get_example_dict(config_class: Type) -> str:
    """
    Generate a minimal example dict snippet for error messages.
    Shows first 2-3 fields with placeholder values.
    """
    if not hasattr(config_class, '__dataclass_fields__'):
        return "..."
    
    fields = list(config_class.__dataclass_fields__.items())[:3]
    examples = []
    for name, field in fields:
        # Generate appropriate placeholder based on type hint
        field_type = field.type if hasattr(field, 'type') else None
        if field_type is bool or str(field_type) == 'bool':
            examples.append(f"'{name}': True")
        elif field_type is int or str(field_type) == 'int':
            examples.append(f"'{name}': 1")
        elif field_type is str or 'str' in str(field_type):
            examples.append(f"'{name}': '...'")
        else:
            examples.append(f"'{name}': ...")
    
    return ", ".join(examples)


# =============================================================================
# Convenience Functions for Specific Parameters
# =============================================================================

def resolve_memory(value: Any, config_class: Type) -> Any:
    """Resolve memory parameter."""
    from .presets import MEMORY_PRESETS, MEMORY_URL_SCHEMES
    
    return resolve(
        value=value,
        param_name="memory",
        config_class=config_class,
        presets=MEMORY_PRESETS,
        url_schemes=MEMORY_URL_SCHEMES,
        instance_check=lambda v: (
            hasattr(v, 'search') and hasattr(v, 'add')
        ) or hasattr(v, 'database_url'),
        array_mode=ArrayMode.SINGLE_OR_LIST,
    )


def resolve_knowledge(value: Any, config_class: Type) -> Any:
    """Resolve knowledge parameter."""
    return resolve(
        value=value,
        param_name="knowledge",
        config_class=config_class,
        instance_check=lambda v: hasattr(v, 'search') and hasattr(v, 'add'),
        array_mode=ArrayMode.SOURCES_WITH_CONFIG,
        string_mode="path_as_source",
    )


def resolve_output(value: Any, config_class: Type) -> Any:
    """Resolve output parameter."""
    from .presets import OUTPUT_PRESETS
    
    return resolve(
        value=value,
        param_name="output",
        config_class=config_class,
        presets=OUTPUT_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
    )


def resolve_execution(value: Any, config_class: Type) -> Any:
    """Resolve execution parameter."""
    from .presets import EXECUTION_PRESETS
    
    return resolve(
        value=value,
        param_name="execution",
        config_class=config_class,
        presets=EXECUTION_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
    )


def resolve_web(value: Any, config_class: Type) -> Any:
    """Resolve web parameter."""
    from .presets import WEB_PRESETS
    
    return resolve(
        value=value,
        param_name="web",
        config_class=config_class,
        presets=WEB_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
    )


def resolve_planning(value: Any, config_class: Type) -> Any:
    """Resolve planning parameter."""
    from .presets import PLANNING_PRESETS
    
    return resolve(
        value=value,
        param_name="planning",
        config_class=config_class,
        presets=PLANNING_PRESETS,
        string_mode="llm_model",
        array_mode=ArrayMode.PRESET_OVERRIDE,
    )


def resolve_reflection(value: Any, config_class: Type) -> Any:
    """Resolve reflection parameter."""
    from .presets import REFLECTION_PRESETS
    
    return resolve(
        value=value,
        param_name="reflection",
        config_class=config_class,
        presets=REFLECTION_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
    )


def resolve_context(value: Any, config_class: Type) -> Any:
    """Resolve context parameter."""
    from .presets import CONTEXT_PRESETS
    
    return resolve(
        value=value,
        param_name="context",
        config_class=config_class,
        presets=CONTEXT_PRESETS,
        instance_check=lambda v: hasattr(v, 'get_context'),
        array_mode=ArrayMode.STEP_NAMES,
    )


def resolve_autonomy(value: Any, config_class: Type) -> Any:
    """Resolve autonomy parameter."""
    from .presets import AUTONOMY_PRESETS
    
    return resolve(
        value=value,
        param_name="autonomy",
        config_class=config_class,
        presets=AUTONOMY_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
    )


def resolve_caching(value: Any, config_class: Type) -> Any:
    """Resolve caching parameter."""
    from .presets import CACHING_PRESETS
    
    return resolve(
        value=value,
        param_name="caching",
        config_class=config_class,
        presets=CACHING_PRESETS,
    )


def resolve_hooks(value: Any, config_class: Optional[Type] = None) -> Any:
    """Resolve hooks parameter."""
    return resolve(
        value=value,
        param_name="hooks",
        config_class=config_class,
        array_mode=ArrayMode.PASSTHROUGH,
    )


def resolve_skills(value: Any, config_class: Type) -> Any:
    """Resolve skills parameter."""
    return resolve(
        value=value,
        param_name="skills",
        config_class=config_class,
        array_mode=ArrayMode.SOURCES,
        string_mode="path_as_source",
    )


def resolve_routing(value: Any, config_class: Type) -> Any:
    """Resolve routing parameter (workflow steps)."""
    return resolve(
        value=value,
        param_name="routing",
        config_class=config_class,
        array_mode=ArrayMode.STEP_NAMES,
    )


def resolve_guardrails(value: Any, config_class: Type) -> Any:
    """Resolve guardrails parameter."""
    from .presets import GUARDRAIL_PRESETS
    
    # Handle callable (highest precedence after instance)
    if callable(value) and not isinstance(value, type):
        return value
    
    return resolve(
        value=value,
        param_name="guardrails",
        config_class=config_class,
        presets=GUARDRAIL_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
        string_mode="llm_prompt",
    )


# =============================================================================
# Batch Resolution for Performance
# =============================================================================

def resolve_batch(
    params: dict,
    presets_map: dict,
    config_classes: dict,
    defaults: dict = None,
) -> dict:
    """
    Resolve multiple parameters in a single batch call for performance.
    
    This reduces function call overhead by processing all parameters together
    instead of making 11+ separate resolve() calls.
    
    Args:
        params: Dict of {param_name: value} to resolve
        presets_map: Dict of {param_name: presets_dict}
        config_classes: Dict of {param_name: config_class}
        defaults: Dict of {param_name: default_value}
        
    Returns:
        Dict of {param_name: resolved_value}
        
    Example:
        results = resolve_batch(
            params={
                'output': 'silent',
                'execution': None,
                'memory': True,
            },
            presets_map={
                'output': OUTPUT_PRESETS,
                'execution': EXECUTION_PRESETS,
                'memory': MEMORY_PRESETS,
            },
            config_classes={
                'output': OutputConfig,
                'execution': ExecutionConfig,
                'memory': MemoryConfig,
            },
            defaults={
                'output': OutputConfig(),
                'execution': ExecutionConfig(),
                'memory': None,
            }
        )
    """
    defaults = defaults or {}
    results = {}
    
    for param_name, value in params.items():
        config_class = config_classes.get(param_name)
        presets = presets_map.get(param_name)
        default = defaults.get(param_name)
        
        # Fast path: None -> default
        if value is None:
            results[param_name] = default
            continue
        
        # Fast path: already a config instance
        if config_class and isinstance(value, config_class):
            results[param_name] = value
            continue
        
        # Fast path: bool handling
        if isinstance(value, bool):
            if value:
                results[param_name] = config_class() if config_class else True
            else:
                results[param_name] = None
            continue
        
        # Fast path: string preset lookup
        if isinstance(value, str) and presets:
            value_lower = value.lower()
            for preset_key in presets:
                if preset_key.lower() == value_lower:
                    preset_value = presets[preset_key]
                    if preset_value is None:
                        results[param_name] = None
                    elif config_class and isinstance(preset_value, config_class):
                        results[param_name] = preset_value
                    elif isinstance(preset_value, dict) and config_class:
                        results[param_name] = config_class(**preset_value)
                    else:
                        results[param_name] = preset_value
                    break
            else:
                # Not a preset - use full resolve for error handling
                results[param_name] = resolve(
                    value=value,
                    param_name=param_name,
                    config_class=config_class,
                    presets=presets,
                    default=default,
                )
            continue
        
        # Fallback to full resolve for complex cases
        results[param_name] = resolve(
            value=value,
            param_name=param_name,
            config_class=config_class,
            presets=presets,
            default=default,
        )
    
    return results


def resolve_guardrail_policies(
    policies: list,
    config_class: Type,
) -> Any:
    """
    Resolve a list of policy strings into a guardrail config.
    
    Supports policy strings like:
    - "policy:strict" - Apply strict policy preset
    - "pii:redact" - PII detection with redaction
    - "safety:block" - Safety check with blocking
    
    Args:
        policies: List of policy strings
        config_class: GuardrailConfig class
        
    Returns:
        Config instance with policies list populated
    """
    from .parse_utils import is_policy_string
    
    # Filter to only valid policy strings
    valid_policies = [p for p in policies if isinstance(p, str) and is_policy_string(p)]
    
    if not valid_policies:
        return None
    
    # Create config with policies list
    if config_class and hasattr(config_class, '__dataclass_fields__'):
        if 'policies' in config_class.__dataclass_fields__:
            return config_class(policies=valid_policies)
    
    return {"policies": valid_policies}
