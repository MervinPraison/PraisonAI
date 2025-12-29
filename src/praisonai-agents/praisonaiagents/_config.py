"""
Configuration module for PraisonAI Agents.

Provides feature flags and configuration options that can be controlled
via environment variables for performance tuning and behavior control.

Environment Variables:
    PRAISONAI_LAZY_IMPORTS: Enable lazy imports (default: true)
    PRAISONAI_TELEMETRY_ENABLED: Enable telemetry (default: false, opt-in)
    PRAISONAI_TELEMETRY_DISABLED: Disable telemetry (takes precedence)
    DO_NOT_TRACK: Standard opt-out flag (takes precedence)
"""
import os
from typing import Optional


def _str_to_bool(value: Optional[str], default: bool = False) -> bool:
    """Convert string environment variable to boolean."""
    if value is None:
        return default
    return value.lower() in ('true', '1', 'yes', 'on')


# Feature Flags
# -------------

# Lazy imports: When True (default), heavy dependencies like litellm are
# only imported when actually needed, reducing import time significantly.
LAZY_IMPORTS = _str_to_bool(
    os.environ.get('PRAISONAI_LAZY_IMPORTS'), 
    default=True
)

# Telemetry: Opt-in by default (False). Users must explicitly enable.
# Precedence (highest to lowest):
#   1. DO_NOT_TRACK=true -> disabled
#   2. PRAISONAI_TELEMETRY_DISABLED=true -> disabled  
#   3. PRAISONAI_DISABLE_TELEMETRY=true -> disabled
#   4. PRAISONAI_TELEMETRY_ENABLED=true -> enabled
#   5. Default: disabled (opt-in model)
def _get_telemetry_enabled() -> bool:
    """Determine if telemetry should be enabled based on env vars."""
    # Check disable flags first (highest precedence)
    if _str_to_bool(os.environ.get('DO_NOT_TRACK')):
        return False
    if _str_to_bool(os.environ.get('PRAISONAI_TELEMETRY_DISABLED')):
        return False
    if _str_to_bool(os.environ.get('PRAISONAI_DISABLE_TELEMETRY')):
        return False
    
    # Check explicit enable flag
    if _str_to_bool(os.environ.get('PRAISONAI_TELEMETRY_ENABLED')):
        return True
    
    # Default: disabled (opt-in model)
    return False


TELEMETRY_ENABLED = _get_telemetry_enabled()

# Performance mode: Minimal telemetry overhead when enabled
PERFORMANCE_MODE = _str_to_bool(
    os.environ.get('PRAISONAI_PERFORMANCE_MODE'),
    default=False
)

# Full telemetry mode: Detailed tracking when enabled
FULL_TELEMETRY = _str_to_bool(
    os.environ.get('PRAISONAI_FULL_TELEMETRY'),
    default=False
)

# Legacy auto-instrument flag
AUTO_INSTRUMENT = _str_to_bool(
    os.environ.get('PRAISONAI_AUTO_INSTRUMENT'),
    default=False
)


def missing_dependency_error(
    package_name: str,
    extra_name: Optional[str] = None,
    feature_name: Optional[str] = None
) -> ImportError:
    """
    Create a standardized ImportError for missing optional dependencies.
    
    Args:
        package_name: The name of the missing package (e.g., 'litellm')
        extra_name: The pip extra to install (e.g., 'llm' for [llm])
        feature_name: Human-readable feature name (e.g., 'LLM support')
    
    Returns:
        ImportError with helpful install instructions
    """
    if extra_name:
        install_cmd = f"pip install 'praisonaiagents[{extra_name}]'"
    else:
        install_cmd = f"pip install {package_name}"
    
    feature_desc = f" for {feature_name}" if feature_name else ""
    
    return ImportError(
        f"{package_name} is required{feature_desc} but not installed. "
        f"Please install with: {install_cmd}"
    )
