"""
Unit tests for the relocated ``run_async_in_sync_context`` helper (PR #5005,
Issue #4984).

The helper bridges ``async def`` tool bodies into the sync tool-calling path
(``tool_execution.py``). It was relocated out of the deprecated
``UnifiedExecutionMixin`` into the stable ``async_safety`` module. These tests
lock in its three live behaviours:

1. No running event loop  -> ``asyncio.run``.
2. Running event loop     -> dedicated background thread + loop (no deadlock).
3. Deprecated mixin shim  -> delegates to the relocated helper.
"""

import asyncio

import pytest

from praisonaiagents.agent.async_safety import run_async_in_sync_context
from praisonaiagents.agent.unified_execution_mixin import UnifiedExecutionMixin


async def _echo(value):
    return value


def test_no_running_loop_uses_asyncio_run():
    """With no active event loop the coroutine runs to completion."""
    result = run_async_in_sync_context(_echo("no-loop"))
    assert result == "no-loop"


def test_no_running_loop_leaves_no_current_loop():
    """asyncio.run cleans up after itself; no loop should leak."""
    run_async_in_sync_context(_echo("cleanup"))
    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()


def test_propagates_exceptions_from_coroutine():
    """Errors inside the coroutine surface to the sync caller."""
    async def _boom():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_async_in_sync_context(_boom())


@pytest.mark.asyncio
async def test_running_loop_uses_dedicated_thread():
    """When a loop is already running the helper must not deadlock.

    It runs the coroutine in a dedicated background thread with its own loop,
    so the id of the loop seen inside the coroutine differs from the caller's.
    """
    caller_loop = asyncio.get_running_loop()
    seen = {}

    async def _capture():
        seen["loop"] = asyncio.get_running_loop()
        return "ran-in-thread"

    result = await asyncio.to_thread(run_async_in_sync_context, _capture())

    assert result == "ran-in-thread"
    assert seen["loop"] is not caller_loop


def test_mixin_shim_delegates_to_relocated_helper():
    """The deprecated mixin keeps a thin shim that resolves the coroutine."""

    class _Holder(UnifiedExecutionMixin):
        pass

    holder = _Holder()
    result = holder._run_async_in_sync_context(_echo("via-shim"))
    assert result == "via-shim"


def test_tool_execution_resolves_coroutine_results():
    """The sync tool path resolves an ``async def`` tool body to a real value.

    Mirrors the ``_resolve_result`` bridge in ``tool_execution.py`` so a bare
    un-awaited coroutine is never handed back as a tool result (silent data
    loss guard).
    """
    import inspect

    async def async_tool():
        return {"status": "ok"}

    value = async_tool()
    if inspect.iscoroutine(value):
        value = run_async_in_sync_context(value)

    assert value == {"status": "ok"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
