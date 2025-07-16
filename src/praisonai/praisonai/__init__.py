# Disable OpenTelemetry SDK
import os
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["EC_TELEMETRY"] = "false"
from .cli import PraisonAI
from .version import __version__

# Re-export all classes from praisonaiagents to enable:
# from PraisonAI import Agent, Task, PraisonAIAgents
# List of symbols that should be available from praisonaiagents
_praisonaiagents_exports = [
    'Agent',
    'ImageAgent',
    'PraisonAIAgents',
    'Agents',
    'Task',
    'Tools',
    'TaskOutput',
    'ReflectionOutput',
    'AutoAgents',
    'Session',
    'Memory',
    'Knowledge',
    'Chunking',
    'MCP',
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
    'TelemetryCollector',
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
]

# Track which symbols were successfully imported
_imported_symbols = []

try:
    import praisonaiagents
    # Import all symbols from praisonaiagents
    for symbol in _praisonaiagents_exports:
        if hasattr(praisonaiagents, symbol):
            globals()[symbol] = getattr(praisonaiagents, symbol)
            _imported_symbols.append(symbol)
except ImportError:
    # If praisonaiagents is not available, these imports will fail gracefully
    pass

# Define __all__ to include both PraisonAI core classes and successfully imported praisonaiagents classes
__all__ = [
    # Core PraisonAI classes
    'PraisonAI',
    '__version__',
] + _imported_symbols
