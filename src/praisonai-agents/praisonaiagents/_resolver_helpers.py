"""
Resolver helper functions for consolidated parameters.

These helpers wrap the canonical resolver for specific parameter types,
handling special cases like callable validators for guardrails.
"""

from typing import Any, Type

from .config.param_resolver import resolve, ArrayMode
from .config.presets import GUARDRAIL_PRESETS


def resolve_guardrails(value: Any, config_class: Type) -> Any:
    """
    Resolve guardrails parameter.
    
    Handles special case of callable validators which have highest precedence.
    
    Args:
        value: The guardrails parameter value
        config_class: GuardrailConfig class
        
    Returns:
        Resolved config, callable, or string
    """
    # Handle None
    if value is None:
        return None
    
    # Handle False (disabled)
    if value is False:
        return None
    
    # Handle callable (highest precedence after None check)
    # This includes functions, lambdas, and callable objects
    if callable(value) and not isinstance(value, type):
        return value
    
    # Use canonical resolver for everything else
    return resolve(
        value=value,
        param_name="guardrails",
        config_class=config_class,
        presets=GUARDRAIL_PRESETS,
        array_mode=ArrayMode.PRESET_OVERRIDE,
        string_mode="llm_prompt",
        default=None,
    )
