"""
Telemetry defaults for PraisonAI wrapper.

This module provides telemetry configuration defaults without mutating 
the global process environment. Defaults are computed once per process
and cached thread-safely.
"""

import os
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TelemetryDefaults:
    """Immutable telemetry default configuration."""
    otel_sdk_disabled: bool
    ec_telemetry: bool


_DEFAULTS: Optional[TelemetryDefaults] = None
_LOCK = threading.Lock()


def get_telemetry_defaults() -> TelemetryDefaults:
    """
    Get telemetry defaults based on current environment.
    
    Computes defaults once and caches them thread-safely.
    Does not mutate os.environ - only reads it.
    
    Returns:
        TelemetryDefaults with computed configuration
    """
    global _DEFAULTS
    with _LOCK:
        if _DEFAULTS is not None:
            return _DEFAULTS
            
        # Check if Langfuse is configured
        langfuse_configured = bool(
            os.getenv("LANGFUSE_PUBLIC_KEY")
            or os.path.exists(os.path.expanduser("~/.praisonai/langfuse.env"))
        )
        
        _DEFAULTS = TelemetryDefaults(
            otel_sdk_disabled=not langfuse_configured,
            ec_telemetry=False,
        )
        return _DEFAULTS


def should_enable_otel() -> bool:
    """Check if OTEL should be enabled based on defaults and user overrides."""
    # User override takes precedence
    user_override = os.getenv("OTEL_SDK_DISABLED")
    if user_override is not None:
        return user_override.lower() not in ("true", "1", "yes")
    
    # Fall back to computed default
    defaults = get_telemetry_defaults()
    return not defaults.otel_sdk_disabled


def should_enable_ec_telemetry() -> bool:
    """Check if EC telemetry should be enabled based on defaults and user overrides."""
    # User override takes precedence  
    user_override = os.getenv("EC_TELEMETRY")
    if user_override is not None:
        return user_override.lower() in ("true", "1", "yes")
    
    # Fall back to computed default
    defaults = get_telemetry_defaults()
    return defaults.ec_telemetry