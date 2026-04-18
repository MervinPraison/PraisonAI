"""
Logging configuration module - single source of truth for PraisonAI logging.

This module ensures that:
1. Only the CLI configures the root logger (no library-side mutation)
2. Library code uses namespaced loggers
3. No hot-path basicConfig() calls on every instance creation
4. Embedders keep their own logging configuration intact
"""
import logging
import os

_PKG_LOGGER = "praisonai"
_configured = False


def configure_cli_logging(level: str | int | None = None) -> None:
    """
    Configure root logging. Must only be called from the CLI entrypoint.
    
    Args:
        level: Log level (string like 'INFO' or logging constant)
    """
    global _configured
    if _configured:
        return
    lvl = level or os.environ.get("LOGLEVEL", "WARNING")
    logging.basicConfig(level=lvl, format="%(asctime)s - %(levelname)s - %(message)s")
    _configured = True


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Return a namespaced logger; never touches root logger.
    
    Args:
        name: Optional logger name suffix
        
    Returns:
        A logger with the praisonai namespace
    """
    return logging.getLogger(f"{_PKG_LOGGER}.{name}" if name else _PKG_LOGGER)