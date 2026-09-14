"""Tests for timeout bounding on the async tool middleware path.

Covers Issue #5077: `_execute_tool_async_via_middleware` schedules the async
tool on the running loop and blocks a worker thread on `future.result()`. Without
a bound, a hung async tool blocks the worker indefinitely and the per-agent tool
timeout is ignored on the middleware path. The fix bounds the worker wait by the
same `_tool_timeout` the direct async path uses and surfaces the existing
structured timeout error dict.
"""

import asyncio

import pytest

from praisonaiagents.agent.execution_mixin import ExecutionMixin
from praisonaiagents.hooks import ToolRequest, ToolResponse


class _PassThroughManager:
    """Minimal tool-middleware manager: invoke the final handler directly."""

    def execute_tool_call(self, request, final_handler):
        return final_handler(request)


class _MiddlewareHarness(ExecutionMixin):
    """Bare object exposing only what the middleware path touches."""

    def __init__(self, tool_timeout, inner_coro):
        self.name = "harness"
        self._current_run_id = "run"
        self._session_id = "session"
        self._tool_timeout = tool_timeout
        self._inner_coro = inner_coro

    def _get_tool_middleware_manager(self):
        return _PassThroughManager()

    async def _execute_tool_async_with_retry(
        self, function_name, arguments, tool_call_id=None, tools_override=None
    ):
        return await self._inner_coro()


@pytest.mark.asyncio
async def test_middleware_async_tool_respects_timeout():
    async def _hang():
        await asyncio.sleep(30)
        return "never"

    harness = _MiddlewareHarness(tool_timeout=0.05, inner_coro=_hang)

    result = await harness._execute_tool_async_via_middleware(
        harness._get_tool_middleware_manager(),
        "slow_tool",
        {},
        "tc-1",
        None,
    )

    assert isinstance(result, dict)
    assert result.get("timeout") is True
    assert result.get("_praison_retryable") is False


@pytest.mark.asyncio
async def test_middleware_async_tool_returns_result_within_timeout():
    async def _quick():
        return "ok"

    harness = _MiddlewareHarness(tool_timeout=5.0, inner_coro=_quick)

    result = await harness._execute_tool_async_via_middleware(
        harness._get_tool_middleware_manager(),
        "fast_tool",
        {},
        "tc-2",
        None,
    )

    assert result == "ok"


@pytest.mark.asyncio
async def test_middleware_async_tool_no_timeout_preserves_behavior():
    async def _quick():
        return 42

    harness = _MiddlewareHarness(tool_timeout=None, inner_coro=_quick)

    result = await harness._execute_tool_async_via_middleware(
        harness._get_tool_middleware_manager(),
        "fast_tool",
        {},
        "tc-3",
        None,
    )

    assert result == 42
