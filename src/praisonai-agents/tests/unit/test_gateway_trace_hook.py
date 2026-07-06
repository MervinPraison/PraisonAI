"""Unit tests for the gateway pipeline span-tracing seam (Issue #2716).

Covers the pure, core-side tracing-hook protocol (``GatewayTraceHook``), its
zero-cost no-op default (``NullGatewayTraceHook``), and the ``resolve_trace_hook``
helper, matching the shape of the sibling gateway policy protocols
(send / idle / drain / concurrency / rate-limit).
"""

from contextlib import AbstractContextManager

import pytest

from praisonaiagents.gateway import (
    GATEWAY_TRACE_STAGES,
    GatewayTraceHook,
    NULL_GATEWAY_TRACE_HOOK,
    NullGatewayTraceHook,
    resolve_trace_hook,
)


def test_null_hook_conforms_to_protocol():
    assert isinstance(NullGatewayTraceHook(), GatewayTraceHook)
    assert isinstance(NULL_GATEWAY_TRACE_HOOK, GatewayTraceHook)


def test_stage_returns_context_manager():
    hook = NullGatewayTraceHook()
    scope = hook.stage("agent.run", correlation_id="abc", session="s1")
    assert isinstance(scope, AbstractContextManager)


def test_null_stage_is_usable_and_ignores_args():
    hook = NullGatewayTraceHook()
    with hook.stage("agent.run", correlation_id="abc", model="gpt-4", extra=1) as span:
        assert span is None


def test_null_stage_works_without_correlation_id():
    hook = NullGatewayTraceHook()
    with hook.stage("inbound") as span:
        assert span is None


def test_null_stage_does_not_swallow_exceptions():
    hook = NullGatewayTraceHook()
    with pytest.raises(ValueError):
        with hook.stage("tool.call", tool="search"):
            raise ValueError("boom")


def test_resolve_trace_hook_returns_default_when_none():
    assert resolve_trace_hook(None) is NULL_GATEWAY_TRACE_HOOK


def test_resolve_trace_hook_passes_through_supplied_hook():
    class _Recorder:
        def __init__(self):
            self.calls = []

        def stage(self, name, *, correlation_id=None, **attrs):
            self.calls.append((name, correlation_id, attrs))
            return NULL_GATEWAY_TRACE_HOOK.stage(name)

    rec = _Recorder()
    resolved = resolve_trace_hook(rec)
    assert resolved is rec
    with resolved.stage("delivery", correlation_id="cid", channel="telegram"):
        pass
    assert rec.calls == [("delivery", "cid", {"channel": "telegram"})]


def test_canonical_stage_names_cover_pipeline():
    for stage in ("inbound", "admit", "agent.run", "llm.call",
                  "tool.call", "outbox.enqueue", "delivery"):
        assert stage in GATEWAY_TRACE_STAGES


def test_custom_hook_scope_wraps_stage():
    events = []

    class _Tracer:
        def stage(self, name, *, correlation_id=None, **attrs):
            return self._span(name, correlation_id, attrs)

        from contextlib import contextmanager as _cm

        @_cm
        def _span(self, name, correlation_id, attrs):
            events.append(("start", name, correlation_id))
            try:
                yield name
            finally:
                events.append(("end", name, correlation_id))

    tracer = resolve_trace_hook(_Tracer())
    with tracer.stage("agent.run", correlation_id="c1") as span:
        assert span == "agent.run"
    assert events == [("start", "agent.run", "c1"), ("end", "agent.run", "c1")]
