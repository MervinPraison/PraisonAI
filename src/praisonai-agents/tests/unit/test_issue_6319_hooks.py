"""Regression tests for #6319 (part a): async BEFORE_TOOL gates registered
via register_function, or returned as awaitables from sync callables, must
have their decisions honoured (and time out closed)."""
import asyncio

from praisonaiagents.hooks import (
    BeforeToolInput, HookEvent, HookRegistry, HookResult, HookRunner,
)


def _before_tool():
    return BeforeToolInput(session_id="s", cwd=".", event_name="before_tool",
                           timestamp="0", tool_name="rm", tool_input={})


def test_async_register_function_hook_denies():
    reg = HookRegistry()

    async def deny_rm(data):
        return HookResult.deny("no rm")

    reg.register_function(HookEvent.BEFORE_TOOL, deny_rm)
    res = HookRunner(reg).execute_sync(HookEvent.BEFORE_TOOL, _before_tool())
    assert res[0].output.decision == "deny"


def test_sync_wrapper_returning_slow_coroutine_times_out():
    reg = HookRegistry()

    async def slow():
        await asyncio.sleep(0.08)
        return HookResult.allow()

    def wrapper(data):
        return slow()

    reg.register_function(HookEvent.BEFORE_TOOL, wrapper, timeout=0.05)
    res = HookRunner(reg).execute_sync(HookEvent.BEFORE_TOOL, _before_tool())
    assert res[0].output.decision == "deny"
    assert not res[0].success


def test_sync_wrapper_returning_coroutine_is_awaited():
    reg = HookRegistry()

    async def deny():
        return HookResult.deny("no")

    reg.register_function(HookEvent.BEFORE_TOOL, lambda d: deny())
    res = HookRunner(reg).execute_sync(HookEvent.BEFORE_TOOL, _before_tool())
    assert res[0].output.decision == "deny" and res[0].success
