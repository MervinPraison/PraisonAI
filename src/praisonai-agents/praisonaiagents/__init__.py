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

# DO NOT auto-instrument by default to avoid performance overhead
# Auto-instrumentation must be explicitly requested by calling:
# from praisonaiagents.telemetry.integration import auto_instrument_all
# auto_instrument_all()
# This ensures zero performance impact for existing users
if _telemetry_available:
    try:
        # Check if explicit auto-instrumentation is requested via environment variable
        import os
        explicit_auto_instrument = os.environ.get('PRAISONAI_AUTO_INSTRUMENT', '').lower() in ('true', '1', 'yes')
        
        if explicit_auto_instrument:
            _telemetry = get_telemetry()
            if _telemetry and _telemetry.enabled:
                from .telemetry.integration import auto_instrument_all
                # Use performance mode by default for auto-instrumentation to minimize overhead
                auto_instrument_all(_telemetry, performance_mode=True)
    except Exception:
        # Silently fail if there are any issues
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

