"""CLI backend debug helpers."""

from __future__ import annotations

import logging
import os
from typing import Any, Optional


def cli_backend_debug_enabled() -> bool:
    """Return True when CLI backend delegation should emit debug logs."""
    flag = os.environ.get("PRAISONAI_CLI_BACKEND_DEBUG", "").lower()
    if flag in ("1", "true", "yes"):
        return True
    return os.environ.get("LOGLEVEL", "").upper() == "DEBUG"


def backend_label(backend: Any) -> str:
    """Human-readable backend identifier for logs."""
    config = getattr(backend, "config", None)
    command = getattr(config, "command", None)
    if command:
        return str(command)
    return type(backend).__name__


def log_cli_backend_execution(
    logger: logging.Logger,
    *,
    backend: Any,
    result: Any,
    agent_name: str,
    session_id: Optional[str] = None,
) -> None:
    """Log which CLI backend ran and the subprocess command (if available)."""
    if not cli_backend_debug_enabled():
        return

    metadata = getattr(result, "metadata", None) or {}
    command = metadata.get("command")
    logger.info(
        "CLI backend delegation agent=%r backend=%r session_id=%r "
        "transport=subprocess praisonai_llm_http=false command=%r",
        agent_name,
        backend_label(backend),
        session_id,
        command,
    )
