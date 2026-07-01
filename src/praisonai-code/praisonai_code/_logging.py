"""Logging helpers for praisonai-code (no praisonai wrapper dependency)."""

from __future__ import annotations

import logging
import os

_PKG_LOGGER = "praisonai_code"
_configured = False


def configure_cli_logging(level: str | int | None = None) -> None:
    """Configure root logging once from the CLI entrypoint."""
    global _configured
    if _configured:
        return
    lvl = level or os.environ.get("LOGLEVEL", "WARNING")
    logging.basicConfig(level=lvl, format="%(asctime)s - %(levelname)s - %(message)s")
    _configured = True


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced logger under ``praisonai_code``."""
    return logging.getLogger(f"{_PKG_LOGGER}.{name}" if name else _PKG_LOGGER)
