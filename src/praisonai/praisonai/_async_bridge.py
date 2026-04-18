"""
Async bridge module - single source of truth for running coroutines synchronously.

This module provides a safe way to run async functions from sync contexts,
handling nested event loop scenarios without creating a new event loop
on every call (which is expensive and breaks multi-agent workflows).
"""
import asyncio
import threading
from concurrent.futures import Future
from typing import Awaitable, TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _ensure_background_loop() -> asyncio.AbstractEventLoop:
    """Ensure a background event loop exists and return it."""
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            t = threading.Thread(target=_loop.run_forever, name="praisonai-async", daemon=True)
            t.start()
        return _loop


def run_sync(coro: Awaitable[T], *, timeout: float | None = None) -> T:
    """
    Run a coroutine synchronously, safe inside a running loop.
    
    This function automatically detects if there's already a running event loop
    and handles the execution appropriately:
    - If no loop is running: uses asyncio.run() (fastest path)
    - If a loop is running: schedules on background loop (safe path)
    
    Args:
        coro: The coroutine to run
        timeout: Maximum time to wait for completion (seconds)
        
    Returns:
        The result of the coroutine
        
    Raises:
        TimeoutError: If timeout is exceeded
        Any exception raised by the coroutine
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is None:
        # Cheap path: no outer loop, just run.
        return asyncio.run(coro)

    # Outer loop exists -> schedule on background loop, do NOT nest asyncio.run.
    fut: Future = asyncio.run_coroutine_threadsafe(coro, _ensure_background_loop())
    return fut.result(timeout=timeout)