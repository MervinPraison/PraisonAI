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
from types import SimpleNamespace

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


def test_build_fallback_dispatcher_does_not_touch_shared_state(monkeypatch):
    """The async fallback dispatcher is a throwaway bound to the fallback model
    and must never be written onto the shared ``self._unified_dispatcher`` or
    change ``self.llm`` — that is what keeps a concurrent turn on the original
    model with correct attribution.
    """
    from praisonaiagents import Agent
    from praisonaiagents import llm as _llm

    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini",
                  fallback_models=["gpt-4o"])
    # Avoid needing a real OpenAI client/key: stub the openai client + factory.
    agent._Agent__openai_client = object()  # backing field of the lazy property
    built = []
    monkeypatch.setattr(
        _llm, "create_llm_dispatcher",
        lambda **kw: built.append(kw) or SimpleNamespace(model=kw.get("model")),
    )
    # Prime the shared dispatcher so we can assert it is left untouched.
    sentinel = object()
    agent._unified_dispatcher = sentinel

    disp = agent._build_fallback_dispatcher("gpt-4o")

    assert disp is not None
    assert disp is not sentinel                 # a distinct, throwaway dispatcher
    assert disp.model == "gpt-4o"               # bound to the fallback model
    assert agent._unified_dispatcher is sentinel  # shared cache untouched
    assert agent.llm == "gpt-4o-mini"             # shared model untouched


def test_async_fallback_passes_override_and_leaves_shared_state(monkeypatch):
    """The async fallback branch must run the retry against a throwaway
    dispatcher passed via ``_dispatcher=`` and must NOT mutate the shared
    ``self.llm`` / ``self._unified_dispatcher``, so a concurrent turn on the
    same Agent never observes the fallback model.

    Regression for the shared-Agent async fallback race (PR #4593 review).
    Exercises the fallback branch directly with a stubbed classifier so no real
    backoff/network is involved.
    """
    from praisonaiagents import Agent
    from praisonaiagents import llm as _llm
    from praisonaiagents.llm import error_classifier as _ec

    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini",
                  fallback_models=["gpt-4o"])
    original_dispatcher = object()
    agent._unified_dispatcher = original_dispatcher
    # Avoid needing a real OpenAI client/key when the fallback dispatcher builds.
    agent._Agent__openai_client = object()
    monkeypatch.setattr(
        _llm, "create_llm_dispatcher",
        lambda **kw: SimpleNamespace(model=kw.get("model")),
    )

    # Force the classifier to request a model fallback with zero backoff.
    classification = SimpleNamespace(
        should_compress_context=False,
        should_rotate_credential=False,
        should_fallback_model=True,
        is_retryable=False,
        backoff_seconds=0,
        error_category="rate_limit",
        user_message="fallback",
    )
    monkeypatch.setattr(_ec, "classify_llm_error", lambda *a, **k: classification)

    async def _noop_emit(*a, **k):
        return None
    agent._aemit_model_fallback = _noop_emit  # type: ignore[assignment]

    used = []

    async def fake_execute(*args, _dispatcher=None, **kwargs):
        used.append(_dispatcher)
        return "ok-from-fallback"

    agent._execute_unified_achat_completion = fake_execute  # type: ignore[assignment]

    result = asyncio.run(agent._handle_async_llm_error(
        RuntimeError("rate limit exceeded"),
        [{"role": "user", "content": "hi"}], None, None, True,
        False, None, None, None, None, None, True, 0, 0,
    ))

    assert result == "ok-from-fallback"
    assert used and used[0] is not None          # retry ran on throwaway dispatcher
    assert used[0] is not original_dispatcher
    assert agent.llm == "gpt-4o-mini"            # shared model untouched
    assert agent._unified_dispatcher is original_dispatcher  # shared cache untouched
