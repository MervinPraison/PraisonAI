"""
Unified deprecation management for PraisonAI.

This module provides a centralized @deprecated decorator with version tracking,
consistent messaging, and migration guidance following AGENTS.md principles.
"""

import warnings
import functools
from typing import Optional, Union, Callable, Any
import inspect

__all__ = ['deprecated', 'DeprecationConfig', 'check_expired_deprecations']

class DeprecationConfig:
    """Configuration for deprecation behavior and version management."""
    
    # Current version for deprecation tracking
    CURRENT_VERSION = "1.0.0"
    
    # Show stack traces for deprecation warnings (useful for debugging)
    SHOW_STACKLEVEL = True
    
    # Warn about expired deprecations that should be removed
    WARN_EXPIRED = True


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string into comparable tuple."""
    if not version_str:
        return (0,)
    return tuple(int(x) for x in version_str.split('.'))


def _is_version_expired(removal_version: str, current_version: str) -> bool:
    """Check if a deprecation has passed its removal version."""
    if not removal_version or not current_version:
        return False
    return _parse_version(current_version) >= _parse_version(removal_version)


def deprecated(
    since: str,
    removal: Optional[str] = None,
    alternative: Optional[str] = None,
    details: Optional[str] = None,
    category: type[Warning] = DeprecationWarning
) -> Callable:
    """
    Decorator to mark functions, methods, or classes as deprecated.
    
    Args:
        since: Version when the feature was deprecated (e.g., "1.5.0")
        removal: Version when the feature will be removed (e.g., "2.0.0")
        alternative: Suggested replacement (e.g., "use new_function() instead")
        details: Additional migration guidance
        category: Warning category (default: DeprecationWarning)
    
    Example:
        @deprecated(
            since="1.5.0",
            removal="2.0.0", 
            alternative="use Agent(model='gpt-4') instead",
            details="The new API provides better type safety and validation"
        )
        def old_function():
            pass
    """
    def decorator(func_or_class: Callable) -> Callable:
        # Build deprecation message
        name = getattr(func_or_class, '__name__', str(func_or_class))
        
        # Check if this deprecation has expired
        if removal and DeprecationConfig.WARN_EXPIRED:
            if _is_version_expired(removal, DeprecationConfig.CURRENT_VERSION):
                expired_msg = (
                    f"EXPIRED DEPRECATION: {name} was scheduled for removal in "
                    f"v{removal} but current version is v{DeprecationConfig.CURRENT_VERSION}. "
                    f"This should be removed from the codebase."
                )
                warnings.warn(expired_msg, category=UserWarning, stacklevel=2)
        
        # Build user-facing deprecation message
        msg_parts = [f"{name} is deprecated since v{since}"]
        
        if removal:
            msg_parts.append(f"and will be removed in v{removal}")
        
        if alternative:
            msg_parts.append(f". {alternative}")
        elif removal:
            msg_parts.append(".")
        else:
            msg_parts.append(".")
        
        if details:
            msg_parts.append(f" {details}")
        
        message = "".join(msg_parts)
        
        # Handle class deprecation
        if inspect.isclass(func_or_class):
            original_init = func_or_class.__init__
            
            @functools.wraps(original_init)
            def new_init(self, *args, **kwargs):
                stacklevel = 3 if DeprecationConfig.SHOW_STACKLEVEL else 2
                warnings.warn(message, category=category, stacklevel=stacklevel)
                return original_init(self, *args, **kwargs)
            
            func_or_class.__init__ = new_init
            return func_or_class
        
        # Handle function/method deprecation
        @functools.wraps(func_or_class)
        def wrapper(*args, **kwargs):
            stacklevel = 3 if DeprecationConfig.SHOW_STACKLEVEL else 2
            warnings.warn(message, category=category, stacklevel=stacklevel)
            return func_or_class(*args, **kwargs)
        
        return wrapper
    
    return decorator


def warn_deprecated_param(
    param_name: str,
    since: str,
    removal: Optional[str] = None,
    alternative: Optional[str] = None,
    details: Optional[str] = None,
    stacklevel: int = 2
) -> None:
    """
    Emit a deprecation warning for a specific parameter.
    
    Use this for parameter deprecations in function/method bodies.
    
    Args:
        param_name: Name of the deprecated parameter
        since: Version when parameter was deprecated
        removal: Version when parameter will be removed
        alternative: Suggested replacement
        details: Additional migration guidance
        stacklevel: Stack level for warning (default: 2)
    
    Example:
        def my_function(old_param=None, new_param=None):
            if old_param is not None:
                warn_deprecated_param(
                    "old_param",
                    since="1.5.0", 
                    removal="2.0.0",
                    alternative="use new_param instead"
                )
    """
    # Check if this deprecation has expired
    if removal and DeprecationConfig.WARN_EXPIRED:
        if _is_version_expired(removal, DeprecationConfig.CURRENT_VERSION):
            expired_msg = (
                f"EXPIRED DEPRECATION: Parameter '{param_name}' was scheduled "
                f"for removal in v{removal} but current version is "
                f"v{DeprecationConfig.CURRENT_VERSION}. This should be removed."
            )
            warnings.warn(expired_msg, category=UserWarning, stacklevel=stacklevel)
    
    # Build deprecation message
    msg_parts = [f"Parameter '{param_name}' is deprecated since v{since}"]
    
    if removal:
        msg_parts.append(f" and will be removed in v{removal}")
    
    if alternative:
        msg_parts.append(f". {alternative}")
    elif removal:
        msg_parts.append(".")
    else:
        msg_parts.append(".")
    
    if details:
        msg_parts.append(f" {details}")
    
    message = "".join(msg_parts)
    
    warnings.warn(message, category=DeprecationWarning, stacklevel=stacklevel)


def check_expired_deprecations(current_version: Optional[str] = None) -> list[str]:
    """
    Check for expired deprecations in the codebase.
    
    This function can be used in CI to detect deprecations that should be removed.
    
    Args:
        current_version: Override for current version (defaults to DeprecationConfig.CURRENT_VERSION)
    
    Returns:
        List of expired deprecation messages
    """
    # This is a placeholder for CI integration
    # In practice, this would scan the codebase for @deprecated decorators
    # and check their removal versions against the current version
    if current_version is None:
        current_version = DeprecationConfig.CURRENT_VERSION
    
    expired = []
    
    # TODO: Add scanning logic here for CI integration
    # This would use AST parsing to find all @deprecated decorators
    # and check if their removal versions have passed
    
    return expired


# Backward compatibility alias for existing code
warn = warn_deprecated_param