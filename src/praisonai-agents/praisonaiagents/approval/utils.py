"""
Utility functions for approval handling.

Provides reusable async-to-sync bridging logic to prevent code duplication
across the approval system.
"""

import asyncio
import concurrent.futures
import hashlib
import json
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

T = TypeVar('T')


def hash_tool_args(arguments: Optional[Dict[str, Any]]) -> str:
    """Return the canonical 16-char identity hash of a tool call's arguments.

    Produces a 16-character SHA-256 digest over the canonical JSON encoding
    (``sort_keys=True, default=str``) of the arguments. This is the single
    source of truth for the tool-call identity key shared by approval
    de-duplication (``ApprovalRegistry``) and doom-loop detection, so the two
    safety subsystems cannot silently diverge.

    Falls back to ``"unhashable"`` if the arguments cannot be serialised.
    """
    try:
        payload = json.dumps(arguments or {}, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
    except (TypeError, ValueError):
        return "unhashable"


# Tool names that map to a shell-command permission target (``bash:<command>``)
# so the reusable command-prefix machinery in ``PermissionManager`` applies.
_SHELL_TOOLS = frozenset({
    "execute_command",
    "acp_execute_command",
})

# File-mutating tool names -> the permission-target prefix used for their path,
# so an "always" grant reads naturally (e.g. ``edit:src/app.py``).
# NOTE: ``apply_patch`` is deliberately absent. It takes ``patch`` (multi-file
# patch text), not a single path, so there is no stable path to pin a scoped
# grant to — it falls through to ``tool:apply_patch`` rather than a misleading
# ``edit:<...>`` target that could silently cover unrelated files on reuse.
_FILE_TOOL_PREFIXES: Dict[str, str] = {
    "edit_file": "edit",
    "acp_edit_file": "edit",
    "write_file": "write",
    "acp_create_file": "write",
    "delete_file": "delete",
    "acp_delete_file": "delete",
    "move_file": "move",
    "copy_file": "copy",
}

# Prefix for a shell command that touches a path *outside* the workspace root.
# Distinct from ``bash:`` so a broad ``bash:*`` / "allow shell" / session grant
# never silently authorises out-of-workspace access — the escaping path is named
# so the grant is path-scoped, mirroring the ``edit:<path>`` file-tool targets.
_SHELL_EXTERNAL_PREFIX = "shell:external-path"


def _shell_external_paths(command: str) -> List[str]:
    """Return the workspace-escaping paths referenced by a shell *command*.

    Reuses the existing command decomposition (``permissions.command_parser``)
    and the shared containment resolver (``tools.path_safety``) — the very
    primitives the file tools rely on — so shell path-scoping cannot diverge
    from the SDK's file-tool workspace guarantee. The workspace root defaults
    to ``$PRAISONAI_WORKSPACE_ROOT`` or the current working directory.

    Set ``PRAISONAI_SHELL_WORKSPACE_BOUNDARY`` to ``0``/``false``/``no`` to opt
    out (e.g. trusted sandboxed/CI runs); the check then returns ``[]`` and the
    command keeps its plain ``bash:<command>`` target. Any parse/resolve failure
    also returns ``[]`` so target derivation never breaks a tool call — the
    downstream ``PermissionManager`` boundary gate still applies fail-closed.
    """
    if os.environ.get(
        "PRAISONAI_SHELL_WORKSPACE_BOUNDARY", "1"
    ).lower() in ("0", "false", "no"):
        return []
    try:
        from ..permissions.command_parser import parse_command
        from ..tools.path_safety import resolve_within_root

        root = os.environ.get("PRAISONAI_WORKSPACE_ROOT") or os.getcwd()
        escaping: List[str] = []
        seen = set()
        for op in parse_command(command):
            candidates = list(op.write_targets) + list(op.path_args)
            # An executable referenced by path runs code outside the workspace;
            # a bare name (``rm``) is PATH-resolved and must not be flagged.
            exe = op.executable
            if exe and (exe.startswith(("/", "~", "./", "../", "$")) or "/" in exe):
                candidates.append(exe)
            for path in candidates:
                if path in seen:
                    continue
                seen.add(path)
                if resolve_within_root(path, root) is None:
                    escaping.append(path)
        return escaping
    except Exception:  # noqa: BLE001 — never break target derivation
        return []


# Argument keys commonly holding the shell command / file path, in priority order.
_COMMAND_KEYS = ("command", "cmd", "code", "query")
# ``src`` covers ``move_file``/``copy_file`` (which take ``src``/``dst``) so a
# scoped grant is pinned to the concrete source path rather than falling back to
# a tool-wide ``tool:move_file`` allow-rule.
_PATH_KEYS = ("file_path", "path", "filename", "file", "target", "filepath", "src")


def build_permission_target(
    tool_name: str, arguments: Optional[Dict[str, Any]] = None
) -> str:
    """Build a :class:`PermissionManager`-compatible target for a tool call.

    Maps a tool name + arguments to a target string the permission store can
    match against (and generalise via ``suggest_scope_pattern``):

    * shell tools -> ``bash:<command>`` — but a command touching a path
      *outside* the workspace root instead yields
      ``shell:external-path:<path>`` so a broad ``bash:*`` / "allow shell" /
      session grant cannot silently authorise out-of-workspace access.
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
                command = value.strip()
                external = _shell_external_paths(command)
                if external:
                    return f"{_SHELL_EXTERNAL_PREFIX}:{','.join(external)}"
                return f"bash:{command}"
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