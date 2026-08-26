"""
Utility functions for approval handling.

Provides reusable async-to-sync bridging logic to prevent code duplication
across the approval system.
"""

import asyncio
import concurrent.futures
import hashlib
import json
from typing import Any, Awaitable, Callable, Dict, Optional, TypeVar

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

    * shell tools -> ``bash:<command>``
    * file tools  -> ``<edit|write|delete|…>:<path>``
    * everything else -> ``tool:<tool_name>``

    The command identity is preserved verbatim so command-specific rules
    (e.g. ``deny: bash:rm *``) still match. The out-of-workspace boundary is
    enforced downstream by :class:`~praisonaiagents.permissions.PermissionManager`
    (its ``external_dir:`` gate), which decomposes the ``bash:<command>`` target
    and gates any escaping path — so a broad ``bash:*`` / "allow shell" /
    session grant cannot silently authorise out-of-workspace access while a
    command-specific ``deny`` still fires.

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


def build_diff_preview(
    tool_name: str, arguments: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """Build a readable unified diff for a file-mutating tool call.

    Lets an approval prompt show the *actual* pending change (path plus
    ``+``/``-`` hunks) instead of a truncated argument dump. Uses only the
    stdlib :mod:`difflib`; no new dependencies. Returns ``None`` for tools that
    are not file mutations (or when the diff cannot be computed) so callers can
    fall back to the existing argument summary.

    Supported tools:

    * ``edit_file`` — targeted ``old_string`` -> ``new_string`` replacement at
      ``filepath``/``path``. Honours ``replace_all`` (default ``False`` =
      first occurrence only) so the preview matches what ``edit_file`` applies.
    * ``acp_edit_file`` — whole-file replace: ``new_content`` at ``filepath``
      diffed against the current on-disk file.
    * ``write_file`` / ``acp_create_file`` — new ``content`` against the
      current on-disk file (empty when the file does not yet exist).
    * ``apply_patch`` — the ``patch`` text is already a unified diff, returned
      verbatim.
    """
    import difflib
    import os

    args = arguments or {}

    def _path() -> str:
        for key in _PATH_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return tool_name

    def _read_existing(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except (OSError, UnicodeDecodeError):
            return ""

    def _unified(old: str, new: str, path: str) -> Optional[str]:
        diff = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"{path} (before)",
                tofile=f"{path} (after)",
                n=3,
            )
        )
        return diff or None

    try:
        if tool_name == "edit_file":
            old_string = args.get("old_string")
            new_string = args.get("new_string")
            if not isinstance(old_string, str) or not isinstance(new_string, str):
                return None
            path = _path()
            existing = _read_existing(path)
            if existing and old_string and old_string in existing:
                # Mirror ``edit_file`` semantics: ``replace_all`` defaults to
                # False (first occurrence only), so the preview must not show
                # every occurrence changing when only the first will be edited.
                if args.get("replace_all"):
                    new_content = existing.replace(old_string, new_string)
                else:
                    new_content = existing.replace(old_string, new_string, 1)
                return _unified(existing, new_content, path)
            return _unified(old_string, new_string, path)

        if tool_name == "acp_edit_file":
            # ACP edits are whole-file replacements: ``new_content`` at
            # ``filepath`` (no old_string/new_string contract).
            new_content = args.get("new_content")
            if not isinstance(new_content, str):
                return None
            path = _path()
            existing = _read_existing(path) if os.path.exists(path) else ""
            return _unified(existing, new_content, path)

        if tool_name in ("write_file", "acp_create_file"):
            content = args.get("content")
            if not isinstance(content, str):
                return None
            path = _path()
            existing = _read_existing(path) if os.path.exists(path) else ""
            return _unified(existing, content, path)

        if tool_name == "apply_patch":
            patch = args.get("patch")
            if isinstance(patch, str) and patch.strip():
                return patch
            return None
    except Exception:  # noqa: BLE001 — preview is advisory; never break approval
        return None

    return None


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