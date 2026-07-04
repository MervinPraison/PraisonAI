"""
PraisonAI Agents Telemetry & Performance Monitoring Module

This module provides:
1. Anonymous usage tracking with privacy-first design  
2. User-friendly performance monitoring and analysis tools

Telemetry can be disabled via environment variables:
- PRAISONAI_TELEMETRY_DISABLED=true
- PRAISONAI_DISABLE_TELEMETRY=true  
- DO_NOT_TRACK=true

Performance monitoring can be optimized via environment variables:
- PRAISONAI_PERFORMANCE_DISABLED=true (disables performance monitoring overhead)
- PRAISONAI_FLOW_ANALYSIS_ENABLED=true (enables expensive flow analysis - opt-in only)

No personal data, prompts, or responses are collected.

Performance Monitoring Features:
- Function performance tracking with detailed statistics
- API call monitoring and analysis
- Function execution flow visualization (opt-in)
- Performance bottleneck identification
- Real-time performance reporting
- External APM metrics export (DataDog, New Relic compatible)
- CLI interface for easy access
"""

import os
import atexit
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .telemetry import MinimalTelemetry, TelemetryCollector

# Import the classes for real (not just type checking)
from .telemetry import MinimalTelemetry, TelemetryCollector

# Performance monitoring tools are lazy-loaded via module-level __getattr__ to
# avoid parsing ~68K of performance-monitoring code on the common get_telemetry()
# path (e.g. AgentTeam.__init__). The public names stay importable from
# praisonaiagents.telemetry exactly as before; the first access triggers the import.
_PERFORMANCE_EXPORTS = {
    # Symbol name -> submodule providing it
    'PerformanceMonitor': 'performance_monitor',
    'performance_monitor': 'performance_monitor',
    'monitor_function': 'performance_monitor',
    'track_api_call': 'performance_monitor',
    'get_performance_report': 'performance_monitor',
    'get_function_stats': 'performance_monitor',
    'get_api_stats': 'performance_monitor',
    'get_slowest_functions': 'performance_monitor',
    'get_slowest_apis': 'performance_monitor',
    'clear_performance_data': 'performance_monitor',
    'export_external_apm_metrics': 'performance_monitor',
    'FunctionFlowAnalyzer': 'performance_utils',
    'PerformanceAnalyzer': 'performance_utils',
    'flow_analyzer': 'performance_utils',
    'performance_analyzer': 'performance_utils',
    'analyze_function_flow': 'performance_utils',
    'visualize_execution_flow': 'performance_utils',
    'analyze_performance_trends': 'performance_utils',
    'generate_comprehensive_report': 'performance_utils',
    'PerformanceCLI': 'performance_cli',
}

__all__ = [
    # Core telemetry
    'get_telemetry',
    'enable_telemetry',
    'disable_telemetry', 
    'force_shutdown_telemetry',
    'MinimalTelemetry',
    'TelemetryCollector',  # For backward compatibility
    # Performance optimizations
    'enable_performance_mode',
    'disable_performance_mode',
    'cleanup_telemetry_resources',
    # Performance monitoring (lazy-loaded via __getattr__)
    'PerformanceMonitor',
    'FunctionFlowAnalyzer',
    'PerformanceAnalyzer',
    'PerformanceCLI',
    'performance_monitor',
    'flow_analyzer',
    'performance_analyzer',
    'monitor_function',
    'track_api_call',
    'get_performance_report',
    'get_function_stats',
    'get_api_stats',
    'get_slowest_functions',
    'get_slowest_apis',
    'clear_performance_data',
    'export_external_apm_metrics',
    'analyze_function_flow',
    'visualize_execution_flow',
    'analyze_performance_trends',
    'generate_comprehensive_report',
    # Availability flag
    'PERFORMANCE_MONITORING_AVAILABLE',
]


def __getattr__(name):
    """Lazily import performance-monitoring symbols on first access.

    This keeps the lightweight MinimalTelemetry / get_telemetry() path free of the
    performance-monitoring import cost while preserving the exact public import
    surface (all symbols remain importable from praisonaiagents.telemetry).
    """
    module_name = _PERFORMANCE_EXPORTS.get(name)
    if module_name is not None:
        from importlib import import_module
        module = import_module(f".{module_name}", __name__)
        value = getattr(module, name)
        # Cache back into the module namespace (PEP 562) so subsequent
        # attribute-style lookups skip __getattr__ and the import machinery.
        globals()[name] = value
        return value
    if name == 'PERFORMANCE_MONITORING_AVAILABLE':
        try:
            from importlib import import_module
            import_module('.performance_monitor', __name__)
            import_module('.performance_utils', __name__)
            import_module('.performance_cli', __name__)
            result = True
        except ImportError:
            result = False
        # Cache the resolved flag so repeated reads don't re-run the imports.
        globals()['PERFORMANCE_MONITORING_AVAILABLE'] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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


def force_shutdown_telemetry():
    """Force shutdown of telemetry system with comprehensive cleanup."""
    from .telemetry import force_shutdown_telemetry as _force_shutdown_telemetry
    _force_shutdown_telemetry()


def enable_performance_mode():
    """Enable performance mode for minimal telemetry overhead."""
    from .integration import enable_performance_mode as _enable_performance_mode
    _enable_performance_mode()


def disable_performance_mode():
    """Disable performance mode to resume full telemetry tracking."""
    from .integration import disable_performance_mode as _disable_performance_mode
    _disable_performance_mode()


def cleanup_telemetry_resources():
    """Clean up telemetry resources including thread pools and queues."""
    from .integration import cleanup_telemetry_resources as _cleanup_telemetry_resources
    _cleanup_telemetry_resources()


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
        # Register atexit handler to properly shutdown telemetry on exit
        atexit.register(lambda: get_telemetry().shutdown())
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