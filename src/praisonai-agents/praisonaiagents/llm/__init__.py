import logging
import warnings
import os
import re

# Disable litellm telemetry before any imports
os.environ["LITELLM_TELEMETRY"] = "False"

# Suppress all relevant logs at module level - more aggressive suppression consistent with main __init__.py
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
# Apply additional local suppression for safety during LLM imports
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

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

# Ensure comprehensive litellm configuration after import
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
