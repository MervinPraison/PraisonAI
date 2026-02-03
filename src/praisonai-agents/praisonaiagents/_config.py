"""
Configuration module for PraisonAI Agents.

Provides feature flags and configuration options that can be controlled
via environment variables for performance tuning and behavior control.

Environment Variables:
    PRAISONAI_LAZY_IMPORTS: Enable lazy imports (default: true)
    PRAISONAI_TELEMETRY_ENABLED: Enable telemetry (default: false, opt-in)
    PRAISONAI_TELEMETRY_DISABLED: Disable telemetry (takes precedence)
    DO_NOT_TRACK: Standard opt-out flag (takes precedence)
    PRAISONAI_PLUGINS: Enable plugins (default: false)
        - "true" or "1": Enable all discovered plugins
        - "logging,metrics": Enable specific plugins (comma-separated)
        - "false" or "0": Disable plugins
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


# Plugins: Enable background plugins (hooks, metrics, logging)
# Note: Tools and guardrails work WITHOUT this flag - they are explicit
def _get_plugins_enabled() -> bool:
    """Determine if plugins should be auto-enabled based on env var."""
    env_value = os.environ.get('PRAISONAI_PLUGINS', '').lower()
    if not env_value:
        return False
    if env_value in ('true', '1', 'yes', 'on'):
        return True
    if env_value in ('false', '0', 'no', 'off'):
        return False
    # Treat as comma-separated list of plugin names (implies enabled)
    return True


def _get_plugins_list() -> list:
    """Get list of specific plugins to enable from env var.
    
    Returns:
        List of plugin names, or empty list if all plugins enabled.
    """
    env_value = os.environ.get('PRAISONAI_PLUGINS', '').lower()
    if not env_value or env_value in ('true', '1', 'yes', 'on', 'false', '0', 'no', 'off'):
        return []
    # Parse comma-separated list
    return [p.strip() for p in env_value.split(',') if p.strip()]


PLUGINS_ENABLED = _get_plugins_enabled()
PLUGINS_LIST = _get_plugins_list()


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
