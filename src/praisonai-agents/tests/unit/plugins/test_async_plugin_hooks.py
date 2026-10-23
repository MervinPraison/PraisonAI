"""``async def`` plugin hooks are awaited, not silently dropped (#5964)."""

import asyncio
import os
import time
import warnings

from praisonaiagents.plugins.plugin import (
    GuardrailBlocked,
    Plugin,
    PluginHook,
    PluginInfo,
)
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.runner import HookRunner
from praisonaiagents.hooks.types import HookEvent
from praisonaiagents.hooks.events import BeforeToolInput, SessionStartInput


class AsyncToolPlugin(Plugin):
    def __init__(self):
        self.sessions = []

    @property
    def info(self):
        return PluginInfo(
            name="async_tool",
            hooks=[PluginHook.BEFORE_TOOL, PluginHook.SESSION_START],
        )

    async def before_tool(self, tool_name, args):
        await asyncio.sleep(0)
        if tool_name == "rm":
            raise GuardrailBlocked("rm is not allowed")
        return {**args, "injected": True}

    async def session_start(self, context):
        await asyncio.sleep(0)
        self.sessions.append(context["source"])


def _tool_input(tool_name="bash"):
    return BeforeToolInput(
        session_id="s", cwd=os.getcwd(), event_name=HookEvent.BEFORE_TOOL,
        timestamp=str(time.time()), agent_name="a",
        tool_name=tool_name, tool_input={"cmd": "ls"},
    )


def _runner(plugin):
    reg = HookRegistry()
    mgr = PluginManager()
    mgr.register(plugin)
    mgr.wire_into_hook_registry(reg)
    return HookRunner(registry=reg, cwd=os.getcwd())


def test_async_transforming_hook_is_awaited_via_runner():
    runner = _runner(AsyncToolPlugin())
    data = _tool_input()
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        runner.execute_sync(HookEvent.BEFORE_TOOL, data)
    assert data.tool_input == {"cmd": "ls", "injected": True}


def test_async_hook_guardrail_block_propagates():
    runner = _runner(AsyncToolPlugin())
    results = runner.execute_sync(HookEvent.BEFORE_TOOL, _tool_input("rm"))
    assert any(r.output and r.output.is_denied() for r in results)


def test_async_observer_hook_runs_inside_running_loop():
    plugin = AsyncToolPlugin()
    runner = _runner(plugin)
    data = SessionStartInput(
        session_id="s", cwd=os.getcwd(), event_name=HookEvent.SESSION_START,
        timestamp=str(time.time()), source="startup",
    )
    asyncio.run(runner.execute(HookEvent.SESSION_START, data))
    assert plugin.sessions == ["startup"]


def test_execute_hook_awaits_async_hook_sync_and_async_paths():
    mgr = PluginManager()
    mgr.register(AsyncToolPlugin())
    assert mgr.execute_hook(PluginHook.BEFORE_TOOL, "bash", {"a": 1}) == {
        "a": 1, "injected": True,
    }
    out = asyncio.run(mgr.async_execute_hook(PluginHook.BEFORE_TOOL, "bash", {"a": 1}))
    assert out == {"a": 1, "injected": True}
