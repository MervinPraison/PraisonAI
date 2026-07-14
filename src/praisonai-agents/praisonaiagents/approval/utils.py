"""
Utility functions for approval handling.

Provides reusable async-to-sync bridging logic to prevent code duplication
across the approval system.
"""

import asyncio
import concurrent.futures
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

T = TypeVar('T')


# Tool names that map to a shell-command permission target (``bash:<command>``)
# so the reusable command-prefix machinery in ``PermissionManager`` applies.
_SHELL_TOOLS = frozenset({
    "execute_command",
    "acp_execute_command",
})

# File-mutating tool names -> the permission-target prefix used for their path,
# so an "always" grant reads naturally (e.g. ``edit:src/app.py``).
_FILE_TOOL_PREFIXES: Dict[str, str] = {
    "edit_file": "edit",
    "acp_edit_file": "edit",
    "apply_patch": "edit",
    "write_file": "write",
    "acp_create_file": "write",
    "delete_file": "delete",
    "acp_delete_file": "delete",
    "move_file": "move",
    "copy_file": "copy",
}

# Argument keys commonly holding the shell command / file path, in priority order.
_COMMAND_KEYS = ("command", "cmd", "code", "query")
_PATH_KEYS = ("file_path", "path", "filename", "file", "target", "filepath")


def build_permission_target(
    tool_name: str, arguments: Optional[Dict[str, Any]] = None
) -> str:
    """Build a :class:`PermissionManager`-compatible target for a tool call.

    Maps a tool name + arguments to a target string the permission store can
    match against (and generalise via ``suggest_scope_pattern``):

    * shell tools -> ``bash:<command>``
    * file tools  -> ``<edit|write|delete|…>:<path>``
    * everything else -> ``tool:<tool_name>``

    Falls back to ``tool:<tool_name>`` whenever the expected argument is missing
    so a target is always produced.

    Args:
        tool_name: Name of the tool requesting approval.
        arguments: The arguments the tool will be called with.

    Returns:
        A target string such as ``"bash:git status -s"`` or ``"edit:src/app.py"``.
    """
    args = arguments or {}

    if tool_name in _SHELL_TOOLS:
        for key in _COMMAND_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return f"bash:{value.strip()}"
        return f"tool:{tool_name}"

    prefix = _FILE_TOOL_PREFIXES.get(tool_name)
    if prefix is not None:
        for key in _PATH_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return f"{prefix}:{value.strip()}"
        return f"tool:{tool_name}"

    return f"tool:{tool_name}"


def run_coroutine_safely(
    coro: Awaitable[T], 
    timeout: Optional[float] = None
) -> T:
    """
    Run a coroutine safely, handling both sync and async contexts.
    
    This function detects if an event loop is already running and uses a
    ThreadPoolExecutor as a fallback to avoid RuntimeError. It respects
    timeout semantics consistently across both code paths.
    
    Args:
        coro: The coroutine to execute
        timeout: Timeout in seconds. None means indefinite wait.
        
    Returns:
        The result of the coroutine
        
    Raises:
        TimeoutError: If the operation times out
        Any exception raised by the coroutine
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    
    if loop and loop.is_running():
        # We're in an async context - use thread pool to avoid RuntimeError
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        
        # Wrap the coroutine with timeout handling inside the thread
        def run_with_timeout():
            if timeout is not None and timeout > 0:
                return asyncio.run(asyncio.wait_for(coro, timeout=timeout))
            else:
                return asyncio.run(coro)
        
        future = pool.submit(run_with_timeout)
        try:
            # Don't use timeout on Future.result() since we handle timeout
            # inside the coroutine via asyncio.wait_for
            result = future.result(timeout=None if timeout is None or timeout == 0 else timeout)
            return result
        finally:
            # Properly shut down the executor without waiting for threads
            pool.shutdown(wait=False, cancel_futures=True)
    else:
        # No running event loop - use asyncio.run directly
        if timeout is not None and timeout > 0:
            return asyncio.run(asyncio.wait_for(coro, timeout=timeout))
        else:
            return asyncio.run(coro)