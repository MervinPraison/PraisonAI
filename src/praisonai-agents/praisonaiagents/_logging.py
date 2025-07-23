"""
Centralized logging configuration for PraisonAI Agents.
This module consolidates all logging configuration in one place to avoid duplication.
It must be imported before any other modules to be effective.
"""

import os
import logging
import warnings
import sys
from typing import List, Set

# ========================================================================
# STEP 1: Environment Variables (Must be set before any imports)
# ========================================================================
def _configure_environment():
    """Set all environment variables to suppress debug messages at the source."""
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
    }
    
    for key, value in env_vars.items():
        os.environ[key] = value


# ========================================================================
# STEP 2: Logger Pre-configuration (Before they're created)
# ========================================================================
def _get_all_noisy_loggers() -> List[str]:
    """Get comprehensive list of all loggers that should be suppressed."""
    return [
        # LiteLLM loggers
        "litellm",
        "litellm.llms.custom_httpx.http_handler",
        "litellm.litellm_logging",
        "litellm.transformation",
        "litellm.utils",
        "litellm.main",
        "litellm.proxy",
        "litellm.router",
        "litellm._logging",
        "litellm.integrations",
        "LiteLLM",
        "LiteLLM Router",
        "LiteLLM Proxy",
        # HTTP libraries
        "httpx",
        "httpx._trace",
        "httpx._client",
        "httpcore",
        "httpcore._trace",
        "httpcore._sync.http11",
        "httpcore._sync.connection_pool",
        "httpcore._async.http11",
        "httpcore._async.connection_pool",
        # OpenAI client
        "openai._base_client",
        "openai._client",
        # Async/System
        "asyncio",
        "selector_events",
        # Markdown processing
        "markdown_it",
        "markdown_it.rules_block",
        "markdown_it.rules_inline",
        "markdown_it.rules_core",
        "markdown_it.renderer",
        "markdown_it.parser_block",
        "markdown_it.parser_inline",
        "markdown_it.parser_core",
        "markdown_it.common",
        "markdown_it.ruler",
        "markdown_it.token",
        "markdown_it.state_core",
        "markdown_it.state_block",
        "markdown_it.state_inline",
        "rich.markdown",
        # Framework specific
        "pydantic",
        "praisonaiagents.telemetry.telemetry",
    ]


def _preconfigure_loggers():
    """Pre-configure all known noisy loggers to suppress debug messages."""
    for logger_name in _get_all_noisy_loggers():
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        # Also clear any existing handlers to prevent duplicate output
        logger.handlers = []
        logger.propagate = False


# ========================================================================
# STEP 3: Warning Filters
# ========================================================================
def _should_suppress_warnings() -> bool:
    """Determine if warnings should be suppressed based on environment."""
    loglevel = os.environ.get('LOGLEVEL', 'INFO').upper()
    return (
        loglevel != 'DEBUG' and 
        not hasattr(sys, '_called_from_test') and 
        'pytest' not in sys.modules and
        os.environ.get('PYTEST_CURRENT_TEST') is None
    )


def _configure_warning_filters():
    """Configure comprehensive warning filters."""
    # Always suppress pydantic deprecation warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="pydantic")
    warnings.filterwarnings("ignore", message=".*class-based `Config` is deprecated.*")
    warnings.filterwarnings("ignore", message=".*Pydantic V1 style `@validator`.*")
    warnings.filterwarnings("ignore", message=".*The `dict` method is deprecated; use `model_dump` instead.*")
    warnings.filterwarnings("ignore", message=".*model_dump.*deprecated.*")
    
    # Conditionally suppress other warnings
    if _should_suppress_warnings():
        # Module-specific warning suppression
        for module in ['litellm', 'httpx', 'httpcore', 'pydantic', 'openai']:
            warnings.filterwarnings("ignore", category=DeprecationWarning, module=module)
            warnings.filterwarnings("ignore", category=UserWarning, module=module)
            warnings.filterwarnings("ignore", category=RuntimeWarning, module=module)
        
        # Specific problematic warnings
        warnings.filterwarnings("ignore", message="There is no current event loop")
        warnings.filterwarnings("ignore", message=".*Use 'content=<...>' to upload raw bytes/text content.*")
        warnings.filterwarnings("ignore", message=".*dict.*method.*deprecated.*")


# ========================================================================
# STEP 4: LiteLLM-specific Configuration (Post-import)
# ========================================================================
def _configure_litellm():
    """Configure litellm after it's imported."""
    try:
        import litellm
        # Disable all litellm logging and telemetry
        litellm.telemetry = False
        litellm.drop_params = True
        litellm.suppress_debug_info = True
        
        if hasattr(litellm, '_logging_obj'):
            litellm._logging_obj.setLevel(logging.CRITICAL)
        
        if hasattr(litellm, 'set_verbose'):
            litellm.set_verbose = False
        
        if hasattr(litellm, '_logging') and hasattr(litellm._logging, '_disable_debugging'):
            litellm._logging._disable_debugging()
            
    except (ImportError, AttributeError):
        # litellm not installed or doesn't have expected attributes
        pass


# ========================================================================
# STEP 5: Monkey Patch for Dynamic Logger Creation
# ========================================================================
# Keep track of original getLogger
_original_getLogger = logging.getLogger
_noisy_logger_prefixes = {
    'litellm', 'httpx', 'httpcore', 'openai', 'markdown_it', 
    'asyncio', 'selector_events'
}


def _patched_getLogger(name=None):
    """Patched getLogger that automatically suppresses noisy loggers."""
    logger = _original_getLogger(name)
    
    if name:
        # Check if this logger should be suppressed
        for prefix in _noisy_logger_prefixes:
            if name.startswith(prefix):
                logger.setLevel(logging.CRITICAL)
                break
    
    return logger


def _apply_monkey_patch():
    """Apply monkey patch to intercept logger creation."""
    logging.getLogger = _patched_getLogger


def _remove_monkey_patch():
    """Remove monkey patch after initial configuration."""
    logging.getLogger = _original_getLogger


# ========================================================================
# MAIN INITIALIZATION FUNCTION
# ========================================================================
def initialize_logging():
    """
    Initialize all logging configuration in the correct order.
    This should be called once at module import time.
    """
    # Step 1: Configure environment variables
    _configure_environment()
    
    # Step 2: Apply monkey patch temporarily
    _apply_monkey_patch()
    
    # Step 3: Pre-configure all known loggers
    _preconfigure_loggers()
    
    # Step 4: Configure warning filters
    _configure_warning_filters()
    
    # Step 5: Try to configure litellm if it's available
    _configure_litellm()
    
    # Step 6: Remove monkey patch but keep configured loggers
    _remove_monkey_patch()
    
    # Step 7: Ensure critical loggers remain suppressed
    # (in case they were recreated after patch removal)
    for logger_name in _get_all_noisy_loggers():
        logger = logging.getLogger(logger_name)
        if logger.level < logging.CRITICAL:
            logger.setLevel(logging.CRITICAL)


# ========================================================================
# ROOT LOGGER CONFIGURATION
# ========================================================================
def configure_root_logger():
    """
    Configure the root logger with RichHandler.
    This should be called after initialize_logging().
    """
    from rich.logging import RichHandler
    
    loglevel = os.environ.get('LOGLEVEL', 'INFO').upper()
    
    logging.basicConfig(
        level=getattr(logging, loglevel, logging.INFO),
        format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
        force=True  # Force reconfiguration
    )


# ========================================================================
# AUTO-INITIALIZE ON IMPORT
# ========================================================================
# This runs automatically when the module is imported
initialize_logging()