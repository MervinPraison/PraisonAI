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


class AsyncLifecyclePlugin(Plugin):
    def __init__(self):
        self.calls = []

    @property
    def info(self):
        return PluginInfo(name="async_lifecycle")

    async def on_init(self, context):
        await asyncio.sleep(0)
        self.calls.append("init")

    async def on_config(self, config):
        await asyncio.sleep(0)
        self.calls.append(("config", config))
        return config

    async def on_shutdown(self):
        await asyncio.sleep(0)
        self.calls.append("shutdown")


def test_async_lifecycle_callbacks_are_awaited():
    plugin = AsyncLifecyclePlugin()
    mgr = PluginManager()
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        assert mgr.register(plugin)
        mgr.enable("async_lifecycle")
        mgr.set_plugin_options({"async_lifecycle": {"k": 1}})
        assert mgr.apply_plugin_options() == 1
        assert mgr.unregister("async_lifecycle")
    assert plugin.calls == ["init", ("config", {"k": 1}), "shutdown"]


def test_hung_async_hook_is_cancelled_at_deadline(monkeypatch):
    from praisonaiagents.plugins import manager as manager_mod

    monkeypatch.setattr(manager_mod, "_ASYNC_HOOK_TIMEOUT", 0.05)
    cancelled = []

    async def hang():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    start = time.time()
    try:
        manager_mod._resolve_awaitable(hang())
    except (TimeoutError, asyncio.TimeoutError):
        pass
    assert time.time() - start < 2
    assert cancelled == [True]


def test_async_on_init_can_call_back_into_manager_from_running_loop(monkeypatch):
    """register() must not hold the manager lock while async on_init runs."""
    from praisonaiagents.plugins import manager as manager_mod

    # A deadlock would otherwise only surface after the 60s deadline.
    monkeypatch.setattr(manager_mod, "_ASYNC_HOOK_TIMEOUT", 2.0)
    mgr = PluginManager()

    class ReentrantInitPlugin(Plugin):
        seen = None

        @property
        def info(self):
            return PluginInfo(name="reentrant_init")

        async def on_init(self, context):
            await asyncio.sleep(0)
            # Bridged onto another thread when called from a running loop.
            # enable() takes the manager lock.
            self.seen = mgr.enable("reentrant_init")

    plugin = ReentrantInitPlugin()

    async def main():
        start = time.monotonic()
        assert mgr.register(plugin) is True
        return time.monotonic() - start

    elapsed = asyncio.run(main())
    assert plugin.seen is True
    assert elapsed < 1.5
