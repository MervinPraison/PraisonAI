"""
Shared base class for messaging-platform approval backends.

Extracts the common sync-wrapper, timeout, poll_interval, and keyword
matching logic so that SlackApproval, TelegramApproval, and DiscordApproval
only need to implement the platform-specific bits.

This is an internal module — end users import the concrete classes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Set

logger = logging.getLogger(__name__)

APPROVE_KEYWORDS: Set[str] = {
    "yes", "y", "approve", "approved", "ok", "allow", "go", "proceed", "confirm",
}
DENY_KEYWORDS: Set[str] = {
    "no", "n", "deny", "denied", "reject", "block", "stop", "cancel", "refuse",
}


def classify_keyword(text: str) -> str | None:
    """Classify *text* as ``'approve'``, ``'deny'``, or ``None``."""
    t = text.strip().lower()
    if t in APPROVE_KEYWORDS:
        return "approve"
    if t in DENY_KEYWORDS:
        return "deny"
    return None


def sync_wrapper(async_fn, timeout: float):
    """Run *async_fn* (a coroutine) synchronously, handling nested loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, async_fn)
            return future.result(timeout=timeout + 10)
    else:
        return asyncio.run(async_fn)
