import sys
import types

from praisonai.cli.app import _setup_langfuse_observability
from praisonai.flow import helpers as flow_helpers


def test_flow_langfuse_context_observability_reuses_single_emitter(monkeypatch):
    monkeypatch.setenv("PRAISONAI_OBSERVE", "langfuse")
    flow_helpers.reset_langfuse_context_observability_for_tests()

    sink_instances = []
    set_calls = []

    class FakeSink:
        def __init__(self):
            sink_instances.append(self)

    class FakeContextTraceEmitter:
        def __init__(self, sink, enabled):
            self.sink = sink
            self.enabled = enabled

    fake_langfuse_module = types.ModuleType("praisonai.observability.langfuse")
    fake_langfuse_module.LangfuseSink = FakeSink

    fake_context_events_module = types.ModuleType("praisonaiagents.trace.context_events")
    fake_context_events_module.ContextTraceEmitter = FakeContextTraceEmitter
    fake_context_events_module.set_context_emitter = set_calls.append

    monkeypatch.setitem(sys.modules, "praisonai.observability.langfuse", fake_langfuse_module)
    monkeypatch.setitem(sys.modules, "praisonaiagents.trace.context_events", fake_context_events_module)

    flow_helpers.setup_langfuse_context_observability()
    flow_helpers.setup_langfuse_context_observability()

    assert len(sink_instances) == 1
    assert len(set_calls) == 2
    assert set_calls[0] is set_calls[1]
    assert set_calls[0] is flow_helpers.get_langfuse_context_emitter()


def test_setup_langfuse_observability_verbose_logs_warning(monkeypatch, capsys):
    class FakeSink:
        def __init__(self):
            raise RuntimeError("boom")

    fake_langfuse_module = types.ModuleType("praisonai.observability.langfuse")
    fake_langfuse_module.LangfuseSink = FakeSink

    fake_protocol_module = types.ModuleType("praisonaiagents.trace.protocol")
    fake_protocol_module.TraceEmitter = object
    fake_protocol_module.set_default_emitter = lambda *_args, **_kwargs: None

    fake_context_events_module = types.ModuleType("praisonaiagents.trace.context_events")
    fake_context_events_module.ContextTraceEmitter = object
    fake_context_events_module.set_context_emitter = lambda *_args, **_kwargs: None

    monkeypatch.setitem(sys.modules, "praisonai.observability.langfuse", fake_langfuse_module)
    monkeypatch.setitem(sys.modules, "praisonaiagents.trace.protocol", fake_protocol_module)
    monkeypatch.setitem(sys.modules, "praisonaiagents.trace.context_events", fake_context_events_module)

    _setup_langfuse_observability(verbose=True)

    captured = capsys.readouterr()
    assert "failed to initialize Langfuse observability" in captured.err
    assert "boom" in captured.err
