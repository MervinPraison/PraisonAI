"""
Async/sync bridge utility for safely running coroutines from any context.

This module provides utilities to safely bridge between async and sync contexts,
ensuring no RuntimeError: "This event loop is already running" crashes.
"""

import asyncio
import atexit
import concurrent.futures
import contextvars
import logging
import os
import sys
import threading
from typing import Any, Awaitable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

def run_coroutine_from_any_context(coro: Awaitable[T], timeout: Optional[float] = 300) -> T:
    """
    Safely run a coroutine to completion from any context (sync OR inside a
    running event loop).

    - No running loop: run it directly with ``asyncio.run`` (wrapped in
      ``asyncio.wait_for`` when a timeout is set).
    - Running loop (FastAPI, Jupyter, a bot handler calling ``agent.chat()``):
      run it on a dedicated worker thread with its own loop so we never
      deadlock on the caller's loop. The caller's ``contextvars`` are copied
      into that thread so trace/session/approval context set by the caller is
      visible inside the coroutine, and the timeout is enforced *inside* the
      worker loop via ``asyncio.wait_for``. The caller also waits on the worker
      with the same ``timeout`` as a hard backstop, so a coroutine that ignores
      cancellation (e.g. a blocking C call that never yields) can still not pin
      the caller past ``timeout``.

    Args:
        coro: The coroutine to execute
        timeout: Maximum execution time in seconds (default: 5 minutes).
            ``None`` disables the timeout.

    Returns:
        The result of the coroutine

    Raises:
        TimeoutError: If the coroutine takes longer than ``timeout``

    Examples:
        >>> async def my_async_function():
        ...     return "hello"
        >>> result = run_coroutine_from_any_context(my_async_function())
        >>> print(result)  # "hello"
    """
    def _wrapped() -> Awaitable[T]:
        return asyncio.wait_for(coro, timeout) if timeout is not None else coro

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop — safe to drive it directly on this thread.
        return asyncio.run(_wrapped())

    # A loop is already running on this thread. Offload to a worker thread with
    # its own loop, carrying the caller's contextvars across so context set by
    # the caller (trace/session/approval) is visible inside the coroutine.
    ctx = contextvars.copy_context()
    future: "concurrent.futures.Future[T]" = concurrent.futures.Future()

    def _worker() -> None:
        try:
            future.set_result(ctx.run(asyncio.run, _wrapped()))
        except BaseException as exc:  # propagate everything to the caller
            future.set_exception(exc)

    # Daemon thread: a stuck worker abandoned after a timeout must not keep the
    # interpreter alive at exit (non-daemon pool threads are joined at exit).
    threading.Thread(target=_worker, name="praisonai-async-bridge", daemon=True).start()
    try:
        # The timeout is normally enforced *inside* the worker loop by
        # asyncio.wait_for. But a coroutine that ignores cancellation (a blocking
        # C call, a shielded/uncancellable await) can keep the worker alive past
        # the deadline, in which case that inner wait_for never fires. We
        # therefore also bound the caller's wait here so a stuck worker can never
        # pin the caller indefinitely.
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError as exc:
        raise TimeoutError(
            f"Coroutine did not complete within {timeout}s"
        ) from exc

_thread_loop = threading.local()
_atexit_registered = False


def _close_thread_runner() -> None:
    """atexit: close the main thread's long-lived loop (cancels leftover tasks,
    shuts down async generators and the default executor)."""
    runner = getattr(_thread_loop, "runner", None)
    if runner is not None and getattr(_thread_loop, "pid", None) == os.getpid():
        _thread_loop.runner = None
        try:
            runner.close()
        except Exception:  # noqa: BLE001 -- never fail interpreter shutdown
            pass


def run_coroutine_on_thread_loop(coro: Awaitable[T], timeout: Optional[float] = 300) -> T:
    """Like :func:`run_coroutine_from_any_context`, but a thread with no running
    loop reuses one long-lived loop across calls instead of a fresh
    ``asyncio.run`` loop each time.

    Loop-bound resources such as an ``AsyncOpenAI`` client and its HTTP
    keep-alive pool then survive between sync turns. Each thread gets its own
    loop (threads stay isolated, as with ``asyncio.run``); a forked child builds
    a new one; the main thread's loop is closed at exit. Every call runs in a
    copy of the caller's current context, as ``asyncio.run`` does. Inside a
    running loop, and on Python < 3.11 (no ``asyncio.Runner``), this is exactly
    :func:`run_coroutine_from_any_context`.
    """
    if sys.version_info < (3, 11) or is_async_context():
        return run_coroutine_from_any_context(coro, timeout)
    global _atexit_registered
    runner = getattr(_thread_loop, "runner", None)
    # The Runner installs its loop as the thread's current loop, so user code
    # calling ``asyncio.get_event_loop().close()`` can close it under us.
    if (runner is None or getattr(_thread_loop, "pid", None) != os.getpid()
            or runner.get_loop().is_closed()):
        runner = asyncio.Runner()
        _thread_loop.runner, _thread_loop.pid = runner, os.getpid()
        if not _atexit_registered and threading.current_thread() is threading.main_thread():
            atexit.register(_close_thread_runner)
            _atexit_registered = True
    wrapped = asyncio.wait_for(coro, timeout) if timeout is not None else coro
    return runner.run(wrapped, context=contextvars.copy_context())


def is_async_context() -> bool:
    """
    Check if we are currently in an async context (event loop is running).
    
    Returns:
        True if an event loop is running, False otherwise
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False

async def run_sync_in_executor(func, *args, **kwargs) -> Any:
    """
    Run a sync function in a thread executor to avoid blocking the event loop.
    
    Args:
        func: The synchronous function to run
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        The result of the function
    """
    loop = asyncio.get_running_loop()
    
    # For functions with kwargs, we need to use a wrapper
    if kwargs:
        def wrapper():
            return func(*args, **kwargs)
        return await loop.run_in_executor(None, wrapper)
    else:
        return await loop.run_in_executor(None, func, *args)

# Strong refs to fire-and-forget tasks: the event loop only keeps weak refs,
# so an unreferenced task can be garbage-collected before it finishes.
_background_tasks: "set[asyncio.Task]" = set()


def spawn_background(coro: Awaitable[Any], label: str = "background task") -> "asyncio.Task":
    """
    Schedule *coro* on the running loop without awaiting it.

    Keeps a strong reference until the task finishes and logs any exception
    with *label*, instead of leaving it to asyncio's "Task exception was never
    retrieved" warning at GC time. Must be called with a running loop.
    """
    task = asyncio.get_running_loop().create_task(coro)
    _background_tasks.add(task)

    def _done(t: "asyncio.Task") -> None:
        _background_tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            logger.error("Error in %s: %s", label, t.exception(), exc_info=t.exception())

    task.add_done_callback(_done)
    return task
