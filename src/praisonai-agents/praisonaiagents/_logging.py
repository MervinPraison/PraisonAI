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
# INITIALIZATION
# ========================================================================
def initialize_logging():
    """Initialize all logging configuration."""
    _configure_environment()
    _configure_loggers()
    _configure_litellm()


# Auto-initialize on import
initialize_logging()