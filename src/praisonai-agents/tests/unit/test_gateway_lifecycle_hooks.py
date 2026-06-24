"""
Tests for gateway/session/schedule lifecycle hook firing in the bot runtime.

The core defines GATEWAY_START/STOP, SESSION_START/END and SCHEDULE_TRIGGER
events, but historically the gateway runtime only fired the three MESSAGE_*
hooks. This suite verifies the runtime now emits the full lifecycle so
observability/guardrail/policy plugins can wrap it.
"""

import asyncio

import pytest

from praisonaiagents.hooks import HookRegistry, HookRunner, HookResult, HookEvent


# ---------------------------------------------------------------------------
# Core: the new event input dataclasses exist and serialize.
# ---------------------------------------------------------------------------

class TestGatewayInputTypes:
    def test_new_input_types_importable(self):
        from praisonaiagents.hooks import (
            GatewayStartInput,
            GatewayStopInput,
            ScheduleTriggerInput,
        )
        assert GatewayStartInput is not None
        assert GatewayStopInput is not None
        assert ScheduleTriggerInput is not None

    def test_gateway_start_to_dict(self):
        from praisonaiagents.hooks import GatewayStartInput

        ev = GatewayStartInput(
            session_id="",
            cwd=".",
            event_name=HookEvent.GATEWAY_START,
            timestamp="0",
            platforms=["telegram", "discord"],
            bot_count=2,
        )
        d = ev.to_dict()
        assert d["platforms"] == ["telegram", "discord"]
        assert d["bot_count"] == 2

    def test_schedule_trigger_to_dict(self):
        from praisonaiagents.hooks import ScheduleTriggerInput

        ev = ScheduleTriggerInput(
            session_id="",
            cwd=".",
            event_name=HookEvent.SCHEDULE_TRIGGER,
            timestamp="0",
            job_name="daily",
            job_id="42",
            message="run me",
        )
        d = ev.to_dict()
        assert d["job_name"] == "daily"
        assert d["job_id"] == "42"
        assert d["message"] == "run me"


# ---------------------------------------------------------------------------
# Helpers: build a runner that records fired events.
# ---------------------------------------------------------------------------

def _recording_runner(*events):
    fired = []
    reg = HookRegistry()

    def _make(name):
        def _h(_ev):
            fired.append(name)
            return HookResult.allow()
        return _h

    for evt in events:
        reg.on(evt)(_make(evt.value))
    return HookRunner(reg), fired


class _FakeAgent:
    name = "assistant"
    agent_name = "assistant"

    def __init__(self, runner):
        self._hook_runner = runner
        self.chat_history = []

    def chat(self, prompt, **kwargs):
        return "response: " + prompt


# ---------------------------------------------------------------------------
# Wrapper emit helpers (sync context).
# ---------------------------------------------------------------------------

class TestEmitHelpers:
    def test_helpers_importable(self):
        from praisonai.bots._protocol_mixin import (
            fire_gateway_start,
            fire_gateway_stop,
            fire_schedule_trigger,
            fire_session_start,
            fire_session_end,
        )
        assert callable(fire_gateway_start)
        assert callable(fire_gateway_stop)
        assert callable(fire_schedule_trigger)
        assert callable(fire_session_start)
        assert callable(fire_session_end)

    def test_gateway_start_stop_fire(self):
        from praisonai.bots._protocol_mixin import (
            fire_gateway_start,
            fire_gateway_stop,
        )

        runner, fired = _recording_runner(
            HookEvent.GATEWAY_START, HookEvent.GATEWAY_STOP
        )
        fire_gateway_start(runner, ["telegram"])
        fire_gateway_stop(runner, ["telegram"])
        assert fired == ["gateway_start", "gateway_stop"]

    def test_schedule_trigger_fires(self):
        from praisonai.bots._protocol_mixin import fire_schedule_trigger

        runner, fired = _recording_runner(HookEvent.SCHEDULE_TRIGGER)
        fire_schedule_trigger(runner, job_name="daily", message="hi")
        assert fired == ["schedule_trigger"]

    def test_none_runner_is_noop(self):
        from praisonai.bots._protocol_mixin import (
            fire_gateway_start,
            fire_session_start,
        )

        # Should not raise when no runner is registered.
        fire_gateway_start(None, ["telegram"])
        fire_session_start(None, session_id="x")


# ---------------------------------------------------------------------------
# BotOS gateway runner resolution.
# ---------------------------------------------------------------------------

class TestBotOSHookResolution:
    def test_resolves_runner_from_bot_agent(self):
        from praisonai.bots.botos import BotOS

        runner, _ = _recording_runner(HookEvent.GATEWAY_START)
        agent = _FakeAgent(runner)

        class _FakeBot:
            def __init__(self, platform, agent):
                self.platform = platform
                self._agent = agent

            def get_agent(self):
                return self._agent

        botos = BotOS(bots=[_FakeBot("telegram", agent)], enable_supervision=False)
        assert botos._get_hook_runner() is runner

    def test_no_runner_returns_none(self):
        from praisonai.bots.botos import BotOS

        class _FakeBot:
            def __init__(self, platform):
                self.platform = platform

            def get_agent(self):
                return None

        botos = BotOS(bots=[_FakeBot("telegram")], enable_supervision=False)
        assert botos._get_hook_runner() is None


# ---------------------------------------------------------------------------
# BotSessionManager session lifecycle (async context).
# ---------------------------------------------------------------------------

class TestSessionLifecycleHooks:
    def test_session_start_once_and_end_on_reset(self):
        from praisonai.bots._session import BotSessionManager

        runner, fired = _recording_runner(
            HookEvent.SESSION_START, HookEvent.SESSION_END
        )
        agent = _FakeAgent(runner)
        mgr = BotSessionManager(platform="telegram")

        async def _run():
            await mgr.chat(agent, "user1", "hello")
            await mgr.chat(agent, "user1", "again")  # should NOT refire start
            mgr.reset("user1")
            await asyncio.sleep(0.05)  # let scheduled hook tasks run

        asyncio.run(_run())

        assert fired.count("session_start") == 1
        assert fired.count("session_end") == 1

    def test_session_start_per_distinct_user(self):
        from praisonai.bots._session import BotSessionManager

        runner, fired = _recording_runner(HookEvent.SESSION_START)
        agent = _FakeAgent(runner)
        mgr = BotSessionManager(platform="telegram")

        async def _run():
            await mgr.chat(agent, "user1", "hi")
            await mgr.chat(agent, "user2", "hi")
            await asyncio.sleep(0.05)

        asyncio.run(_run())
        assert fired.count("session_start") == 2
