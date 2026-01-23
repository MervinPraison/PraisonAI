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
    loglevel = os.environ.get('LOGLEVEL', 'WARNING').upper()
    
    # When DEBUG or INFO is set, allow some HTTP logging for API endpoints
    if loglevel in ('DEBUG', 'INFO'):
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
_litellm_configured = False

def configure_litellm():
    """Configure litellm after it's imported.
    
    This function should be called lazily when litellm is actually used,
    not at module import time, to avoid importing litellm unnecessarily.
    """
    global _litellm_configured
    if _litellm_configured:
        return
    
    try:
        import litellm
        litellm.telemetry = False
        litellm.drop_params = True
        litellm.suppress_debug_info = True
        
        if hasattr(litellm, '_logging_obj'):
            litellm._logging_obj.setLevel(logging.CRITICAL)
        
        if hasattr(litellm, 'set_verbose'):
            litellm.set_verbose = False
        
        _litellm_configured = True
            
    except (ImportError, AttributeError):
        pass


# Alias for backward compatibility
_configure_litellm = configure_litellm


# ========================================================================
# ROOT LOGGER CONFIGURATION
# ========================================================================
def configure_root_logger():
    """Configure the root logger with optional RichHandler.
    
    Uses standard StreamHandler by default for performance.
    RichHandler is only used when LOGLEVEL=DEBUG for better debugging experience.
    """
    loglevel = os.environ.get('LOGLEVEL', 'WARNING').upper()
    
    # Only use RichHandler for DEBUG level to avoid importing rich at startup
    # This significantly improves import time for silent/normal operation
    if loglevel == 'DEBUG':
        from rich.logging import RichHandler
        handlers = [RichHandler(rich_tracebacks=True)]
    else:
        handlers = [logging.StreamHandler()]
    
    logging.basicConfig(
        level=getattr(logging, loglevel, logging.WARNING),
        format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="[%X]",
        handlers=handlers,
        force=True
    )


# ========================================================================
# INITIALIZATION
# ========================================================================
def initialize_logging():
    """Initialize all logging configuration.
    
    Note: litellm configuration is NOT done here to avoid importing litellm
    at package import time. Call configure_litellm() when litellm is needed.
    """
    _configure_environment()
    _configure_loggers()
    # NOTE: _configure_litellm() is NOT called here to avoid importing litellm
    # It will be called lazily when LLM class is instantiated


# Auto-initialize on import (but NOT litellm)
initialize_logging()