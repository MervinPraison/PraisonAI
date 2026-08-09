"""
Unit tests for the MODEL_FALLBACK observability seam (Issue #3820).

When the primary model becomes unavailable mid-turn and the runtime switches to
the next entry in ``fallback_models``, that switch must be observable: a
``MODEL_FALLBACK`` hook fires (so plugins/gateways can notice/alert/meter) and,
when a stream callback is active, a ``StreamEventType.MODEL_FALLBACK`` event is
emitted. Backward compatible: with nothing subscribed the emit is a cheap no-op
that never raises.
"""

import asyncio

import pytest

from praisonaiagents.hooks.types import HookEvent, HookResult
from praisonaiagents.hooks.registry import HookRegistry
from praisonaiagents.hooks.runner import HookRunner
from praisonaiagents.hooks.events import ModelFallbackInput
from praisonaiagents.streaming.events import StreamEvent, StreamEventType
from praisonaiagents.agent.chat_mixin import ChatMixin


class _DummyAgent(ChatMixin):
    """Minimal stand-in exposing just the attributes the emitter reads.

    Carries its own ``_hook_runner`` (agent-scoped registry) so tests exercise
    the same registry the real agent dispatches through, not the process-wide
    default.
    """

    def __init__(self):
        self.name = "tester"
        self._session_id = "sess1"
        self._current_run_id = "run1"
        self._hook_runner = HookRunner(HookRegistry())


def test_model_fallback_input_to_dict_carries_payload():
    inp = ModelFallbackInput(
        session_id="s",
        cwd="/",
        event_name=HookEvent.MODEL_FALLBACK.value,
        timestamp="0",
        from_model="gpt-primary",
        to_model="backup",
        reason_category="rate_limit",
        fallback_index=2,
    )
    d = inp.to_dict()
    assert d["from_model"] == "gpt-primary"
    assert d["to_model"] == "backup"
    assert d["reason_category"] == "rate_limit"
    assert d["fallback_index"] == 2


def test_stream_event_type_has_model_fallback():
    assert StreamEventType.MODEL_FALLBACK.value == "model_fallback"


def test_emit_fires_hook_and_stream_event():
    captured = {}

    def hook(inp):
        captured["hook"] = inp.to_dict()
        return HookResult.allow()

    agent = _DummyAgent()
    agent._hook_runner.registry.register_function(HookEvent.MODEL_FALLBACK, hook)

    events = []
    agent._emit_model_fallback(
        from_model="gpt-primary",
        to_model="backup",
        reason_category="provider_down",
        fallback_index=1,
        stream_callback=events.append,
    )

    assert captured["hook"]["from_model"] == "gpt-primary"
    assert captured["hook"]["to_model"] == "backup"
    assert captured["hook"]["reason_category"] == "provider_down"
    assert captured["hook"]["fallback_index"] == 1

    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, StreamEvent)
    assert ev.type == StreamEventType.MODEL_FALLBACK
    assert ev.metadata["from_model"] == "gpt-primary"
    assert ev.metadata["to_model"] == "backup"
    assert ev.agent_id == "tester"
    assert ev.session_id == "sess1"
    assert ev.run_id == "run1"


def test_emit_uses_agent_registry_not_default():
    # A subscriber on the agent's own registry must be invoked. Regression guard
    # for the previous bug where the emitter dispatched through the process-wide
    # default registry, silently skipping agent-scoped hooks.
    seen = []
    agent = _DummyAgent()
    agent._hook_runner.registry.register_function(
        HookEvent.MODEL_FALLBACK, lambda inp: seen.append(inp.to_dict()) or HookResult.allow()
    )

    agent._emit_model_fallback(
        from_model="a", to_model="b", reason_category="rate_limit", fallback_index=0,
    )

    assert len(seen) == 1
    assert seen[0]["to_model"] == "b"


def test_async_emit_fires_hook_in_event_loop():
    # In an async recovery path the sync runner would raise inside a running
    # loop and drop the hook. The async emitter must await the runner so the
    # MODEL_FALLBACK hook actually executes.
    captured = {}
    agent = _DummyAgent()
    agent._hook_runner.registry.register_function(
        HookEvent.MODEL_FALLBACK,
        lambda inp: captured.setdefault("hook", inp.to_dict()) or HookResult.allow(),
    )

    async def _run():
        events = []
        await agent._aemit_model_fallback(
            from_model="p", to_model="q", reason_category="provider_down",
            fallback_index=3, stream_callback=events.append,
        )
        return events

    events = asyncio.run(_run())

    assert captured["hook"]["from_model"] == "p"
    assert captured["hook"]["fallback_index"] == 3
    assert len(events) == 1
    assert events[0].type == StreamEventType.MODEL_FALLBACK


def test_async_emit_suppresses_stream_when_callback_none():
    # Async recovery invoked with emit_events=False forwards stream_callback=None;
    # no stream event must leak, but hooks still fire.
    captured = {}
    agent = _DummyAgent()
    agent._hook_runner.registry.register_function(
        HookEvent.MODEL_FALLBACK,
        lambda inp: captured.setdefault("hook", inp.to_dict()) or HookResult.allow(),
    )

    async def _run():
        await agent._aemit_model_fallback(
            from_model="p", to_model="q", reason_category="", fallback_index=0,
            stream_callback=None,
        )

    asyncio.run(_run())
    assert captured["hook"]["to_model"] == "q"


def test_emit_is_noop_without_consumers():
    # No hook registered and no stream callback: must not raise and must not
    # emit anything (today's behaviour preserved).
    _DummyAgent()._emit_model_fallback(
        from_model="a",
        to_model="b",
        reason_category="",
        fallback_index=0,
    )


def test_emit_never_breaks_on_bad_stream_callback():
    def boom(_event):
        raise RuntimeError("callback failed")

    # A misbehaving consumer must not propagate out of the emitter.
    _DummyAgent()._emit_model_fallback(
        from_model="a",
        to_model="b",
        reason_category="rate_limit",
        fallback_index=0,
        stream_callback=boom,
    )
