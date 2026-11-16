"""Regression tests for #6320 — trace redaction of free text and auth schemes."""
from praisonaiagents.trace.context_events import ContextListSink, ContextTraceEmitter
from praisonaiagents.trace.redact import redact_dict, redact_string


def test_bearer_and_basic_values_redacted():
    out = redact_string("Authorization: Bearer sk-live-SECRET123456")
    assert "SECRET" not in out and out == "Authorization: [REDACTED]"
    assert "dXNlcjpw" not in redact_string("authorization=Basic dXNlcjpwYXNz")


def test_redact_dict_scrubs_strings_and_tuples():
    out = redact_dict({"cmd": "x -d password=hunter2", "env": ("API_KEY=abc",)})
    assert "hunter2" not in out["cmd"]
    assert out["env"] == ("API_KEY=[REDACTED]",)


def test_emitter_redacts_tool_and_message_text():
    sink = ContextListSink()
    em = ContextTraceEmitter(sink=sink, session_id="s", enabled=True, redact=True)
    em.tool_call_start("a", "shell", {"command": "curl -H 'Authorization: Bearer tok123'"})
    em.tool_call_end("a", "shell", result="token=abc123", error="password=hunter2")
    em.message_added("a", "user", "my password=hunter2", 1, 1)
    dumped = repr([e.data for e in sink.get_events()])
    for secret in ("tok123", "abc123", "hunter2"):
        assert secret not in dumped


def test_emitter_leaves_text_when_redact_disabled():
    sink = ContextListSink()
    em = ContextTraceEmitter(sink=sink, session_id="s", enabled=True, redact=False)
    em.tool_call_end("a", "shell", result="token=abc123")
    assert sink.get_events()[0].data["result"] == "token=abc123"


def test_noop_sink_skips_text_redaction_but_real_sink_redacts(monkeypatch):
    """NoOp sink stores nothing, so the redaction regex must not run on its hot path."""
    import praisonaiagents.trace.redact as redact_mod
    from praisonaiagents.trace.context_events import ContextNoOpSink

    calls = []
    orig = redact_mod.redact_string
    monkeypatch.setattr(redact_mod, "redact_string", lambda t: calls.append(t) or orig(t))

    ContextTraceEmitter(sink=ContextNoOpSink(), session_id="s").message_added("a", "user", "password=hunter2", 1, 1)
    assert calls == []

    sink = ContextListSink()
    ContextTraceEmitter(sink=sink, session_id="s").message_added("a", "user", "password=hunter2", 1, 1)
    assert calls and "hunter2" not in sink.get_events()[0].data["content"]


def test_noop_sink_skips_tool_args_redaction(monkeypatch):
    import praisonaiagents.trace.redact as redact_mod
    from praisonaiagents.trace.context_events import ContextNoOpSink

    calls = []
    orig = redact_mod.redact_dict
    monkeypatch.setattr(redact_mod, "redact_dict", lambda d: calls.append(d) or orig(d))

    ContextTraceEmitter(sink=ContextNoOpSink(), session_id="s").tool_call_start("a", "t", {"q": "token=abc"})
    assert calls == []

    sink = ContextListSink()
    ContextTraceEmitter(sink=sink, session_id="s").tool_call_start("a", "t", {"q": "token=abc"})
    assert calls and "abc" not in repr(sink.get_events()[0].data)
