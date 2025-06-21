"""
Praison AI Agents - A package for hierarchical AI agent task execution
"""

from .agent.agent import Agent
from .agent.image_agent import ImageAgent
from .agents.agents import PraisonAIAgents
from .task.task import Task
from .tools.tools import Tools
from .agents.autoagents import AutoAgents
from .knowledge.knowledge import Knowledge
from .knowledge.chunking import Chunking
from .mcp.mcp import MCP
from .session import Session
from .memory.memory import Memory
from .guardrails import GuardrailResult, LLMGuardrail
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
    
    MinimalTelemetry = None
    TelemetryCollector = None

# Add Agents as an alias for PraisonAIAgents
Agents = PraisonAIAgents

# Apply telemetry auto-instrumentation after all imports
if _telemetry_available:
    try:
        # Only instrument if telemetry is enabled
        _telemetry = get_telemetry()
        if _telemetry and _telemetry.enabled:
            from .telemetry.integration import auto_instrument_all
            auto_instrument_all(_telemetry)
    except Exception:
        # Silently fail if there are any issues
        pass

__all__ = [
    'Agent',
    'ImageAgent',
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
    'MCP',
    'GuardrailResult',
    'LLMGuardrail',
    'get_telemetry',
    'enable_telemetry',
    'disable_telemetry',
    'MinimalTelemetry',
    'TelemetryCollector'
] 