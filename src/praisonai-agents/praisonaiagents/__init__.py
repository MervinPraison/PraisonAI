"""
Praison AI Agents - A package for hierarchical AI agent task execution
"""

# Apply warning patch BEFORE any imports to intercept warnings at the source
from . import _warning_patch

# Import centralized logging configuration FIRST
from . import _logging

# Configure root logger after logging is initialized
_logging.configure_root_logger()

# Now import everything else
from .agent.agent import Agent
from .agent.image_agent import ImageAgent
from .agent.context_agent import ContextAgent, create_context_agent
from .agents.agents import PraisonAIAgents
from .task.task import Task
from .tools.tools import Tools
from .agents.autoagents import AutoAgents
from .knowledge.knowledge import Knowledge
from .knowledge.chunking import Chunking
# MCP support (optional)
try:
    from .mcp.mcp import MCP
    _mcp_available = True
except ImportError:
    _mcp_available = False
    MCP = None
from .session import Session
from .memory.memory import Memory
from .guardrails import GuardrailResult, LLMGuardrail
from .agent.handoff import Handoff, handoff, handoff_filters, RECOMMENDED_PROMPT_PREFIX, prompt_with_handoff_instructions
# Flow display
try:
    from .flow_display import FlowDisplay, track_workflow
except ImportError:
    FlowDisplay = None
    track_workflow = None
from .main import (
    TaskOutput,
    ReflectionOutput,
    display_interaction,
    display_self_reflection,
    display_instruction,
    display_tool_call,
    display_error,
    display_generating,
    clean_triple_backticks,
    error_logs,
    register_display_callback,
    sync_display_callbacks,
    async_display_callbacks,
)

# Telemetry support (lazy loaded)
try:
    from .telemetry import (
        get_telemetry,
        enable_telemetry,
        disable_telemetry,
        enable_performance_mode,
        disable_performance_mode,
        cleanup_telemetry_resources,
        MinimalTelemetry,
        TelemetryCollector
    )
    _telemetry_available = True
except ImportError:
    # Telemetry not available - provide stub functions
    _telemetry_available = False
    def get_telemetry():
        return None
    
    def enable_telemetry(*args, **kwargs):
        import logging
        logging.warning(
            "Telemetry not available. Install with: pip install praisonaiagents[telemetry]"
        )
        return None
    
    def disable_telemetry():
        pass
    
    def enable_performance_mode():
        pass
    
    def disable_performance_mode():
        pass
    
    def cleanup_telemetry_resources():
        pass
    
    MinimalTelemetry = None
    TelemetryCollector = None

# Add Agents as an alias for PraisonAIAgents
Agents = PraisonAIAgents

# Enable PostHog telemetry by default with actual event posting  
# PostHog events are posted by default unless explicitly disabled
# Users can:
#   - Disable completely: PRAISONAI_DISABLE_TELEMETRY=true (or DO_NOT_TRACK=true)
#   - Enable performance mode: PRAISONAI_PERFORMANCE_MODE=true (minimal overhead, limited events)
#   - Enable full telemetry: PRAISONAI_FULL_TELEMETRY=true (detailed tracking)
#   - Legacy opt-in mode: PRAISONAI_AUTO_INSTRUMENT=true
if _telemetry_available:
    try:
        import os
        
        # Check for explicit disable (respects DO_NOT_TRACK and other disable flags)
        telemetry_disabled = any([
            os.environ.get('PRAISONAI_TELEMETRY_DISABLED', '').lower() in ('true', '1', 'yes'),
            os.environ.get('PRAISONAI_DISABLE_TELEMETRY', '').lower() in ('true', '1', 'yes'),
            os.environ.get('DO_NOT_TRACK', '').lower() in ('true', '1', 'yes'),
        ])
        
        # Check for performance mode (minimal overhead with limited events)
        performance_mode = os.environ.get('PRAISONAI_PERFORMANCE_MODE', '').lower() in ('true', '1', 'yes')
        
        # Check for full telemetry mode (more detailed tracking)
        full_telemetry = os.environ.get('PRAISONAI_FULL_TELEMETRY', '').lower() in ('true', '1', 'yes')
        
        # Legacy explicit auto-instrument option
        explicit_auto_instrument = os.environ.get('PRAISONAI_AUTO_INSTRUMENT', '').lower() in ('true', '1', 'yes')
        
        # Enable PostHog by default unless explicitly disabled
        if not telemetry_disabled:
            _telemetry = get_telemetry()
            if _telemetry and _telemetry.enabled:
                from .telemetry.integration import auto_instrument_all
                
                # Default: PostHog telemetry is enabled and events are posted
                # Performance mode can be explicitly enabled for minimal overhead
                use_performance_mode = performance_mode and not (full_telemetry or explicit_auto_instrument)
                auto_instrument_all(_telemetry, performance_mode=use_performance_mode)
                
                # Track package import for basic usage analytics
                try:
                    _telemetry.track_feature_usage("package_import")
                except Exception:
                    pass
    except Exception:
        # Silently fail if there are any issues - never break user applications
        pass

__all__ = [
    'Agent',
    'ImageAgent',
    'ContextAgent',
    'create_context_agent',
    'PraisonAIAgents',
    'Agents',
    'Tools',
    'Task',
    'TaskOutput',
    'ReflectionOutput',
    'AutoAgents',
    'Session',
    'Memory',
    'display_interaction',
    'display_self_reflection',
    'display_instruction',
    'display_tool_call',
    'display_error',
    'display_generating',
    'clean_triple_backticks',
    'error_logs',
    'register_display_callback',
    'sync_display_callbacks',
    'async_display_callbacks',
    'Knowledge',
    'Chunking',
    'GuardrailResult',
    'LLMGuardrail',
    'Handoff',
    'handoff',
    'handoff_filters',
    'RECOMMENDED_PROMPT_PREFIX',
    'prompt_with_handoff_instructions',
    'get_telemetry',
    'enable_telemetry',
    'disable_telemetry',
    'enable_performance_mode',
    'disable_performance_mode',
    'cleanup_telemetry_resources',
    'MinimalTelemetry',
    'TelemetryCollector'
]

# Add MCP to __all__ if available
if _mcp_available:
    __all__.append('MCP')
    
# Add flow display if available
if FlowDisplay is not None:
    __all__.extend(['FlowDisplay', 'track_workflow'])

