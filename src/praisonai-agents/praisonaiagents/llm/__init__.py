import logging
import warnings
import os
import re

# Disable litellm telemetry before any imports
os.environ["LITELLM_TELEMETRY"] = "False"
os.environ["LITELLM_DROP_PARAMS"] = "True"
# Disable LiteLLM's internal debug logging
os.environ["LITELLM_LOG"] = "CRITICAL"
# Disable all LiteLLM logging
os.environ["LITELLM_DISABLE_STREAMING_LOGS"] = "True"

# Check if warnings should be suppressed (consistent with main __init__.py)
def _should_suppress_warnings():
    import sys
    LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()
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

# Always suppress noisy warnings regardless of debug mode
_always_suppress_noisy_warnings()

# Suppress all relevant logs at module level - more aggressive suppression consistent with main __init__.py (only when not in DEBUG mode)
if _should_suppress_warnings():
    logging.getLogger("litellm").setLevel(logging.CRITICAL)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    logging.getLogger("pydantic").setLevel(logging.WARNING)

    # Additional litellm logger suppression for this module
    for name in logging.Logger.manager.loggerDict:
        if name.startswith('litellm'):
            logging.getLogger(name).setLevel(logging.CRITICAL)
            logging.getLogger(name).disabled = True

# Warning filters are centrally managed in the main __init__.py file  
# Apply additional local suppression for safety during LLM imports (only when not in DEBUG mode)
if _should_suppress_warnings():
    for module in ['litellm', 'httpx', 'httpcore', 'pydantic']:
        warnings.filterwarnings("ignore", category=DeprecationWarning, module=module)
        warnings.filterwarnings("ignore", category=UserWarning, module=module)

# Import after suppressing warnings
from .llm import LLM, LLMContextLengthExceededException
from .openai_client import (
    OpenAIClient, 
    get_openai_client,
    ChatCompletionMessage,
    Choice,
    CompletionTokensDetails,
    PromptTokensDetails,
    CompletionUsage,
    ChatCompletion,
    ToolCall,
    process_stream_chunks
)
from .model_capabilities import (
    supports_structured_outputs,
    supports_streaming_with_tools
)
from .model_router import (
    ModelRouter,
    ModelProfile, 
    TaskComplexity,
    create_routing_agent
)

# Always apply noisy warning suppression again after imports in case modules reset filters
_always_suppress_noisy_warnings()

# Ensure comprehensive litellm configuration after import (only when not in DEBUG mode)
if _should_suppress_warnings():
    try:
        import litellm
        # Disable all litellm logging and telemetry features
        litellm.telemetry = False
        litellm.drop_params = True
        if hasattr(litellm, 'suppress_debug_info'):
            litellm.suppress_debug_info = True
        # Set all litellm loggers to CRITICAL level
        if hasattr(litellm, '_logging_obj'):
            litellm._logging_obj.setLevel(logging.CRITICAL)
        # Also disable any runtime logging that might have been missed
        for name in logging.Logger.manager.loggerDict:
            if name.startswith('litellm'):
                logging.getLogger(name).setLevel(logging.CRITICAL)
                logging.getLogger(name).disabled = True
    except ImportError:
        pass

__all__ = [
    "LLM", 
    "LLMContextLengthExceededException", 
    "OpenAIClient", 
    "get_openai_client",
    "ChatCompletionMessage",
    "Choice",
    "CompletionTokensDetails",
    "PromptTokensDetails",
    "CompletionUsage",
    "ChatCompletion",
    "ToolCall",
    "process_stream_chunks",
    "supports_structured_outputs",
    "supports_streaming_with_tools",
    "ModelRouter",
    "ModelProfile",
    "TaskComplexity",
    "create_routing_agent"
]
