"""
Tests for the PluginManager -> HookRunner bridge.

Ensures installed/enabled plugins actually fire during runtime hook execution
(fixes the disconnect where entry-point plugins were discovered but never run).
"""

import os
import time

from praisonaiagents.plugins.plugin import Plugin, PluginInfo, PluginHook
from praisonaiagents.plugins.manager import PluginManager, _adapt_plugin_hooks
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.runner import HookRunner
from praisonaiagents.hooks.types import HookEvent
from praisonaiagents.hooks.events import AfterLLMInput, BeforeToolInput


class PIIPlugin(Plugin):
    @property
    def info(self):
        return PluginInfo(name="pii", hooks=[PluginHook.AFTER_LLM])

    def after_llm(self, response, usage):
        return response.replace("123-45-6789", "[REDACTED]")


class ToolArgPlugin(Plugin):
    @property
    def info(self):
        return PluginInfo(name="toolargs", hooks=[PluginHook.BEFORE_TOOL])

    def before_tool(self, tool_name, args):
        args = dict(args)
        args["injected"] = True
        return args


class NoopPlugin(Plugin):
    @property
    def info(self):
        return PluginInfo(name="noop")


def _input(response="SSN is 123-45-6789"):
    return AfterLLMInput(
        session_id="s",
        cwd=os.getcwd(),
        event_name=HookEvent.AFTER_LLM,
        timestamp=str(time.time()),
        agent_name="a",
        response=response,
    )


class TestBridge:
    def test_wire_registers_hooks(self):
        reg = HookRegistry()
        mgr = PluginManager()
        mgr.register(PIIPlugin())
        assert mgr.wire_into_hook_registry(reg) == 1
        assert reg.has_hooks(HookEvent.AFTER_LLM)

    def test_after_llm_plugin_fires_and_redacts(self):
        reg = HookRegistry()
        mgr = PluginManager()
        mgr.register(PIIPlugin())
        mgr.wire_into_hook_registry(reg)

        runner = HookRunner(registry=reg, cwd=os.getcwd())
        data = _input()
        runner.execute_sync(HookEvent.AFTER_LLM, data)
        assert data.response == "SSN is [REDACTED]"

    def test_before_tool_plugin_mutates_args(self):
        reg = HookRegistry()
        mgr = PluginManager()
        mgr.register(ToolArgPlugin())
        mgr.wire_into_hook_registry(reg)

        runner = HookRunner(registry=reg, cwd=os.getcwd())
        data = BeforeToolInput(
            session_id="s", cwd=os.getcwd(), event_name=HookEvent.BEFORE_TOOL,
            timestamp=str(time.time()), agent_name="a",
            tool_name="bash", tool_input={"cmd": "ls"},
        )
        runner.execute_sync(HookEvent.BEFORE_TOOL, data)
        assert data.tool_input.get("injected") is True

    def test_disabled_plugin_not_wired(self):
        reg = HookRegistry()
        mgr = PluginManager()
        mgr.register(PIIPlugin())
        mgr.disable("pii")
        assert mgr.wire_into_hook_registry(reg) == 0
        assert not reg.has_hooks(HookEvent.AFTER_LLM)

    def test_noop_plugin_registers_no_hooks(self):
        assert list(_adapt_plugin_hooks(NoopPlugin())) == []

    def test_double_wire_idempotent(self):
        reg = HookRegistry()
        mgr = PluginManager()
        mgr.register(PIIPlugin())
        assert mgr.wire_into_hook_registry(reg) == 1
        assert mgr.wire_into_hook_registry(reg) == 0

    def test_disable_after_wire_removes_hooks(self):
        reg = HookRegistry()
        mgr = PluginManager()
        mgr.register(PIIPlugin())
        assert mgr.wire_into_hook_registry(reg) == 1
        assert reg.has_hooks(HookEvent.AFTER_LLM)

        assert mgr.disable("pii") is True
        assert not reg.has_hooks(HookEvent.AFTER_LLM)

        # Disabled plugin no longer fires
        runner = HookRunner(registry=reg, cwd=os.getcwd())
        data = _input()
        runner.execute_sync(HookEvent.AFTER_LLM, data)
        assert data.response == "SSN is 123-45-6789"

    def test_reenable_after_disable_rewires(self):
        reg = HookRegistry()
        mgr = PluginManager()
        mgr.register(PIIPlugin())
        mgr.wire_into_hook_registry(reg)
        mgr.disable("pii")
        assert not reg.has_hooks(HookEvent.AFTER_LLM)

        mgr.enable("pii")
        assert mgr.wire_into_hook_registry(reg) == 1
        assert reg.has_hooks(HookEvent.AFTER_LLM)

    def test_before_tool_none_tool_input_no_crash(self):
        reg = HookRegistry()
        mgr = PluginManager()
        mgr.register(ToolArgPlugin())
        mgr.wire_into_hook_registry(reg)

        runner = HookRunner(registry=reg, cwd=os.getcwd())
        data = BeforeToolInput(
            session_id="s", cwd=os.getcwd(), event_name=HookEvent.BEFORE_TOOL,
            timestamp=str(time.time()), agent_name="a",
            tool_name="bash", tool_input=None,
        )
        runner.execute_sync(HookEvent.BEFORE_TOOL, data)

    def test_single_entry_point_group(self):
        import inspect
        src = inspect.getsource(PluginManager.discover_entry_points)
        assert "praisonai.plugins" in src
        # the old duplicate group must be gone
        assert "praisonaiagents.plugins" not in src
