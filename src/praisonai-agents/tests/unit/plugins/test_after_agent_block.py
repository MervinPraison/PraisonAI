"""
Tests that AFTER_AGENT plugins can block or rewrite the final response (#5061).
"""

import asyncio
import os
import time

from praisonaiagents.plugins.plugin import (
    Plugin,
    PluginInfo,
    PluginHook,
    PluginDecision,
    GuardrailBlocked,
)
from praisonaiagents.plugins.manager import PluginManager
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.runner import HookRunner
from praisonaiagents.hooks.types import HookEvent
from praisonaiagents.hooks.events import AfterAgentInput

SECRET = "123-45-6789"


class RaiseBlockPlugin(Plugin):
    @property
    def info(self):
        return PluginInfo(name="raiseblock", hooks=[PluginHook.AFTER_AGENT])

    def after_agent(self, response, context):
        if SECRET in response:
            raise GuardrailBlocked("PII in response")
        return response


class DecisionBlockPlugin(Plugin):
    @property
    def info(self):
        return PluginInfo(name="decisionblock", hooks=[PluginHook.AFTER_AGENT])

    def after_agent(self, response, context):
        if SECRET in response:
            return PluginDecision.block("PII in response")
        return response


class RedactPlugin(Plugin):
    @property
    def info(self):
        return PluginInfo(name="redact", hooks=[PluginHook.AFTER_AGENT])

    def after_agent(self, response, context):
        return response.replace(SECRET, "[REDACTED]")


def _registry(plugin):
    reg = HookRegistry()
    mgr = PluginManager()
    mgr.register(plugin)
    mgr.set_plugin_options({plugin.info.name: {"allow_conversation": True}})
    assert mgr.wire_into_hook_registry(reg) == 1
    return reg


def _input(response):
    return AfterAgentInput(
        session_id="s", cwd=os.getcwd(), event_name=HookEvent.AFTER_AGENT,
        timestamp=str(time.time()), agent_name="a", response=response,
    )


def _agent(plugin):
    from praisonaiagents import Agent
    return Agent(name="a", role="r", goal="g", hooks=_registry(plugin))


class TestAfterAgentAdapter:
    def test_guardrail_blocked_blocks(self):
        runner = HookRunner(registry=_registry(RaiseBlockPlugin()), cwd=os.getcwd())
        results = runner.execute_sync(HookEvent.AFTER_AGENT, _input(f"SSN {SECRET}"))
        assert runner.is_blocked(results) is True
        assert runner.get_blocking_reason(results) == "PII in response"

    def test_decision_blocks(self):
        runner = HookRunner(registry=_registry(DecisionBlockPlugin()), cwd=os.getcwd())
        results = runner.execute_sync(HookEvent.AFTER_AGENT, _input(f"SSN {SECRET}"))
        assert runner.is_blocked(results) is True

    def test_clean_response_allowed(self):
        runner = HookRunner(registry=_registry(RaiseBlockPlugin()), cwd=os.getcwd())
        data = _input("all good")
        results = runner.execute_sync(HookEvent.AFTER_AGENT, data)
        assert runner.is_blocked(results) is False
        assert data.response == "all good"


class TestAgentAfterAgentEnforcement:
    def test_sync_block_withholds_response(self):
        agent = _agent(RaiseBlockPlugin())
        out = agent._trigger_after_agent_hook("q", f"SSN {SECRET}", time.time())
        assert SECRET not in out
        assert "blocked" in out.lower() and "PII in response" in out

    def test_async_block_withholds_response(self):
        agent = _agent(DecisionBlockPlugin())
        out = asyncio.run(agent._atrigger_after_agent_hook("q", f"SSN {SECRET}", time.time()))
        assert SECRET not in out
        assert "PII in response" in out

    def test_sync_rewrite_is_adopted(self):
        agent = _agent(RedactPlugin())
        out = agent._trigger_after_agent_hook("q", f"SSN {SECRET}", time.time())
        assert out == "SSN [REDACTED]"

    def test_clean_response_passes_through(self):
        agent = _agent(RaiseBlockPlugin())
        assert agent._trigger_after_agent_hook("q", "hello", time.time()) == "hello"
