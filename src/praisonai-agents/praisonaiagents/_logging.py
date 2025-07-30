"""
Centralized logging configuration for PraisonAI Agents.
This module consolidates all logging configuration in one place to avoid duplication.
"""

import os
import logging
from typing import List

# ========================================================================
# ENVIRONMENT CONFIGURATION
# ========================================================================
def _configure_environment():
    """Set environment variables to suppress debug messages at the source."""
    env_vars = {
        # LiteLLM configuration
        "LITELLM_TELEMETRY": "False",
        "LITELLM_DROP_PARAMS": "True",
        "LITELLM_LOG": "ERROR",
        "LITELLM_DEBUG": "False",
        "LITELLM_SUPPRESS_DEBUG_INFO": "True",
        "LITELLM_VERBOSE": "False",
        "LITELLM_SET_VERBOSE": "False",
        # HTTPX configuration
        "HTTPX_DISABLE_WARNINGS": "True",
        "HTTPX_LOG_LEVEL": "ERROR",
        # Pydantic configuration
        "PYDANTIC_WARNINGS_ENABLED": "False",
    }
    
    for key, value in env_vars.items():
        os.environ[key] = value


# ========================================================================
# LOGGER CONFIGURATION
# ========================================================================
def _get_all_noisy_loggers() -> List[str]:
    """Get list of all loggers that should be suppressed."""
    return [
        # LiteLLM and variants
        "litellm", "LiteLLM", "LiteLLM Router", "LiteLLM Proxy",
        # HTTP libraries
        "httpx", "httpx._trace", "httpx._client",
        "httpcore", "httpcore._trace",
        # OpenAI
        "openai._base_client", "openai._client",
        # Markdown
        "markdown_it", "rich.markdown",
        # System
        "asyncio", "selector_events", "pydantic",
        "praisonaiagents.telemetry.telemetry",
    ]


def _configure_loggers():
    """Configure all loggers based on LOGLEVEL environment variable."""
    loglevel = os.environ.get('LOGLEVEL', 'INFO').upper()
    
    # When DEBUG is set, allow some HTTP logging for API endpoints
    if loglevel == 'DEBUG':
        allowed_debug_loggers = {"httpx", "httpx._client", "openai._client"}
        
        for logger_name in _get_all_noisy_loggers():
            if logger_name not in allowed_debug_loggers:
                logger = logging.getLogger(logger_name)
                logger.setLevel(logging.CRITICAL)
                logger.handlers = []
                logger.propagate = False
        
        # Ensure allowed loggers are at INFO level to show API calls
        for logger_name in allowed_debug_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.INFO)
    else:
        # Suppress all noisy loggers when not in DEBUG mode
        for logger_name in _get_all_noisy_loggers():
            logger = logging.getLogger(logger_name)
            logger.setLevel(logging.CRITICAL)
            logger.handlers = []
            logger.propagate = False


# ========================================================================
# LITELLM CONFIGURATION
# ========================================================================
def _configure_litellm():
    """Configure litellm after it's imported."""
    try:
        import litellm
        litellm.telemetry = False
        litellm.drop_params = True
        litellm.suppress_debug_info = True
        
        if hasattr(litellm, '_logging_obj'):
            litellm._logging_obj.setLevel(logging.CRITICAL)
        
        if hasattr(litellm, 'set_verbose'):
            litellm.set_verbose = False
            
    except (ImportError, AttributeError):
        pass


# ========================================================================
# ROOT LOGGER CONFIGURATION
# ========================================================================
def configure_root_logger():
    """Configure the root logger with RichHandler."""
    from rich.logging import RichHandler
    
    loglevel = os.environ.get('LOGLEVEL', 'INFO').upper()
    
    logging.basicConfig(
        level=getattr(logging, loglevel, logging.INFO),
        format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
        force=True
    )


# ========================================================================
# CONTEXT SANITIZATION FOR SAFE LOGGING
# ========================================================================
def sanitize_context_for_logging(context_data, max_length=100, show_structure=True):
    """
    Sanitize context data for safe logging without exposing sensitive information.
    
    Args:
        context_data: The context data to sanitize (string, list, dict, etc.)
        max_length: Maximum length of content to show (default: 100 characters)
        show_structure: Whether to show data structure info (default: True)
    
    Returns:
        str: Sanitized representation safe for logging
    """
    if context_data is None:
        return "None"
    
    if isinstance(context_data, str):
        if len(context_data) <= max_length:
            # For short content, show first and last parts with ellipsis if needed
            if len(context_data) > max_length:
                return f"'{context_data[:max_length//2]}...{context_data[-(max_length//2):]}'"
            return f"'{context_data}'"
        else:
            # For long content, show length and preview
            preview = context_data[:max_length].replace('\n', '\\n').replace('\r', '\\r')
            return f"[{len(context_data)} chars] '{preview}...'"
    
    elif isinstance(context_data, (list, tuple)):
        if not context_data:
            return f"{type(context_data).__name__}(empty)"
        
        # Show structure info with sanitized preview of first few items
        item_previews = []
        for i, item in enumerate(context_data[:3]):  # Show max 3 items
            sanitized_item = sanitize_context_for_logging(item, max_length//3, False)
            item_previews.append(f"[{i}]: {sanitized_item}")
        
        structure_info = f"{type(context_data).__name__}({len(context_data)} items)"
        if show_structure and item_previews:
            return f"{structure_info} - {', '.join(item_previews)}"
        return structure_info
    
    elif isinstance(context_data, dict):
        if not context_data:
            return "dict(empty)"
        
        # Show structure with sanitized key samples
        key_samples = list(context_data.keys())[:3]
        structure_info = f"dict({len(context_data)} keys: {key_samples})"
        
        if show_structure and len(key_samples) > 0:
            # Show preview of first key-value pair
            first_key = key_samples[0]
            first_value = sanitize_context_for_logging(context_data[first_key], max_length//2, False)
            return f"{structure_info} - sample: {first_key}={first_value}"
        return structure_info
    
    else:
        # For other types, show type and truncated string representation
        str_repr = str(context_data)
        if len(str_repr) <= max_length:
            return f"{type(context_data).__name__}: {str_repr}"
        else:
            preview = str_repr[:max_length].replace('\n', '\\n').replace('\r', '\\r')
            return f"{type(context_data).__name__}({len(str_repr)} chars): {preview}..."


# ========================================================================
# INITIALIZATION
# ========================================================================
def initialize_logging():
    """Initialize all logging configuration."""
    _configure_environment()
    _configure_loggers()
    _configure_litellm()


# Auto-initialize on import
initialize_logging()