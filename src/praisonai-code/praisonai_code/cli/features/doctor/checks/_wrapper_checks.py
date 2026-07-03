"""Shared helpers for doctor checks that require the praisonai wrapper."""

from __future__ import annotations

import time
from typing import Optional

from ..models import CheckResult, CheckStatus, CheckCategory


def skip_if_no_wrapper(
    check_id: str,
    title: str,
    *,
    start: Optional[float] = None,
    category: CheckCategory = CheckCategory.BOTS,
) -> Optional[CheckResult]:
    """Return a SKIP result when the full wrapper is not installed."""
    from praisonai_code._wrapper_bridge import wrapper_available

    if wrapper_available():
        return None
    duration_ms = (time.time() - start) * 1000 if start is not None else None
    return CheckResult(
        id=check_id,
        title=title,
        category=category,
        status=CheckStatus.SKIP,
        message="Install full wrapper: pip install praisonai",
        duration_ms=duration_ms,
    )


def bots_config_schema():
    """Load ``praisonai_bot.bots._config_schema`` via the bot bridge."""
    from praisonai_code._bot_bridge import import_bot_module

    return import_bot_module("praisonai_bot.bots._config_schema")
