"""
PraisonAI Agents Minimal Telemetry Module

This module provides anonymous usage tracking with privacy-first design.
Telemetry is opt-out and can be disabled via environment variables:
- PRAISONAI_TELEMETRY_DISABLED=true
- PRAISONAI_DISABLE_TELEMETRY=true  
- DO_NOT_TRACK=true

No personal data, prompts, or responses are collected.
"""

import os
import atexit
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .telemetry import MinimalTelemetry, TelemetryCollector

# Import the classes for real (not just type checking)
from .telemetry import MinimalTelemetry, TelemetryCollector

__all__ = [
    'get_telemetry',
    'enable_telemetry',
    'disable_telemetry',
    'MinimalTelemetry',
    'TelemetryCollector',  # For backward compatibility
]


def get_telemetry() -> 'MinimalTelemetry':
    """Get the global telemetry instance."""
    from .telemetry import get_telemetry as _get_telemetry
    return _get_telemetry()


def enable_telemetry():
    """Enable telemetry (if not disabled by environment)."""
    from .telemetry import enable_telemetry as _enable_telemetry
    _enable_telemetry()


def disable_telemetry():
    """Disable telemetry."""
    from .telemetry import disable_telemetry as _disable_telemetry
    _disable_telemetry()


# Auto-instrumentation and cleanup setup
_initialized = False
_atexit_registered = False

def _ensure_atexit():
    """Ensure atexit handler is registered."""
    global _atexit_registered
    if _atexit_registered:
        return
    
    # Check if telemetry should be disabled
    telemetry_disabled = any([
        os.environ.get('PRAISONAI_TELEMETRY_DISABLED', '').lower() in ('true', '1', 'yes'),
        os.environ.get('PRAISONAI_DISABLE_TELEMETRY', '').lower() in ('true', '1', 'yes'),
        os.environ.get('DO_NOT_TRACK', '').lower() in ('true', '1', 'yes'),
    ])
    
    if not telemetry_disabled:
        # Register atexit handler to flush telemetry on exit
        atexit.register(lambda: get_telemetry().flush())
        _atexit_registered = True

def _initialize_telemetry():
    """Initialize telemetry with auto-instrumentation and cleanup."""
    global _initialized
    if _initialized:
        return
    
    # Ensure atexit is registered
    _ensure_atexit()
    
    # Check if telemetry should be disabled
    telemetry_disabled = any([
        os.environ.get('PRAISONAI_TELEMETRY_DISABLED', '').lower() in ('true', '1', 'yes'),
        os.environ.get('PRAISONAI_DISABLE_TELEMETRY', '').lower() in ('true', '1', 'yes'),
        os.environ.get('DO_NOT_TRACK', '').lower() in ('true', '1', 'yes'),
    ])
    
    if not telemetry_disabled:
        try:
            # Defer the actual instrumentation to avoid circular imports
            # This will be called when get_telemetry() is first accessed
            _initialized = True
        except Exception:
            # Silently fail if there are any issues
            pass


# No need for lazy auto-instrumentation here since main __init__.py handles it


# Initialize atexit handler early
_ensure_atexit()