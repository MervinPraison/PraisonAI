"""
Praison AI Agents - A package for hierarchical AI agent task execution
"""

# Configure logging before any other imports
import os
import logging
import warnings
import re
from rich.logging import RichHandler

# Set environment variables to suppress warnings at the source
os.environ["LITELLM_TELEMETRY"] = "False"
os.environ["LITELLM_DROP_PARAMS"] = "True"
# Disable httpx warnings
os.environ["HTTPX_DISABLE_WARNINGS"] = "True"
# Disable LiteLLM's internal debug logging
os.environ["LITELLM_LOG"] = "CRITICAL"
# Disable all LiteLLM logging
os.environ["LITELLM_DISABLE_STREAMING_LOGS"] = "True"

# Get log level from environment variable
LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()

# Determine if warnings should be suppressed (not in DEBUG mode and not in tests)
def _should_suppress_warnings():
    import sys
    return (LOGLEVEL != 'DEBUG' and 
            not hasattr(sys, '_called_from_test') and 
            'pytest' not in sys.modules and
            os.environ.get('PYTEST_CURRENT_TEST') is None)

# Always suppress these noisy warnings regardless of debug mode
def _always_suppress_noisy_warnings():
    """Suppress warnings that are always noise, even in DEBUG mode"""
    # Specific filters for known problematic warnings that are never useful
    warnings.filterwarnings("ignore", message=".*Use 'content=<...>' to upload raw bytes/text content.*", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message=".*The `dict` method is deprecated; use `model_dump` instead.*", category=UserWarning) 
    warnings.filterwarnings("ignore", message=".*model_dump.*deprecated.*", category=UserWarning)
    warnings.filterwarnings("ignore", message="There is no current event loop")
    
    # Always suppress excessive LiteLLM debug logging - these are always spam
    # Be more aggressive with LiteLLM since it's very noisy
    for logger_name in ['litellm', 'litellm.utils', 'litellm.proxy', 'litellm.router', 'litellm_logging']:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)  # Always set to CRITICAL for LiteLLM
        
    # Also disable all existing litellm loggers
    for name in logging.Logger.manager.loggerDict:
        if name.startswith('litellm'):
            logging.getLogger(name).setLevel(logging.CRITICAL)

# Configure root logger
logging.basicConfig(
    level=getattr(logging, LOGLEVEL, logging.INFO),
    format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)

# Always suppress noisy warnings regardless of debug mode
_always_suppress_noisy_warnings()

# Suppress specific noisy loggers - more aggressive suppression (only when not in DEBUG mode)
if _should_suppress_warnings():
    logging.getLogger("litellm").setLevel(logging.CRITICAL)
    logging.getLogger("litellm.utils").setLevel(logging.CRITICAL)
    logging.getLogger("litellm.proxy").setLevel(logging.CRITICAL)
    logging.getLogger("litellm.router").setLevel(logging.CRITICAL)
    logging.getLogger("litellm_logging").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    logging.getLogger("pydantic").setLevel(logging.WARNING)
    logging.getLogger("markdown_it").setLevel(logging.WARNING)
    logging.getLogger("rich.markdown").setLevel(logging.WARNING)

    # Disable all litellm submodule loggers
    for name in logging.Logger.manager.loggerDict:
        if name.startswith('litellm'):
            logging.getLogger(name).setLevel(logging.CRITICAL)
            logging.getLogger(name).disabled = True

# Comprehensive warning suppression for litellm and dependencies (issue #1033)
# These warnings clutter output and are not actionable for users

# Apply conditional warning suppression (only when not in DEBUG mode) 
if _should_suppress_warnings():
    # Module-specific warning suppression - applied before imports (only when not in DEBUG mode)
    for module in ['litellm', 'httpx', 'httpcore', 'pydantic']:
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=module)
        warnings.filterwarnings("ignore", category=UserWarning, module=module)

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

# Additional warning suppression after all imports (runtime suppression)
# Always apply noisy warning suppression again after imports in case modules reset filters
_always_suppress_noisy_warnings()

if _should_suppress_warnings():
    # Try to import and configure litellm to suppress its warnings
    try:
        import litellm
        # Disable all litellm logging and telemetry
        litellm.telemetry = False
        litellm.drop_params = True
        # Set litellm to suppress warnings
        litellm.suppress_debug_info = True
        if hasattr(litellm, '_logging_obj'):
            litellm._logging_obj.setLevel(logging.CRITICAL)
    except (ImportError, AttributeError):
        pass

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
    'MinimalTelemetry',
    'TelemetryCollector'
]

# Add MCP to __all__ if available
if _mcp_available:
    __all__.append('MCP') 