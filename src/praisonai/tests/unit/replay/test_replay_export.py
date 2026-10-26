"""PraisonAI Replay exports: JSON, Mermaid (golden), OTLP-JSON and self-contained HTML."""

import hashlib
import json
import re


GOLDEN_MERMAID = """sequenceDiagram
    participant You
    participant A0 as Researcher
    participant A1 as Writer
    You->>A0: task research
    A0-->>You: task research completed
    A0->>A1: handoff: draft it
    You->>A1: task write
    A1->>You: approve publish?
    You-->>A1: approved
    A1-->>You: task write completed
"""


def test_load_events_skips_partial_last_line(traces_dir, fx):
    from praisonai.replay.events import load_events

    fx.write_trace(traces_dir, "run-team01", fx.team_events(), partial_tail='{"event_type": "task_st')
    events = load_events("run-team01")
    assert len(events) == len(fx.team_events())
    assert events[-1]["event_type"] == "session_end"


def test_load_events_keeps_unknown_event_types(traces_dir, fx):
    from praisonai.replay.events import load_events

    evs = fx.team_events() + [{"event_type": "future_thing", "sequence_num": 99, "data": {}}]
    path = fx.write_trace(traces_dir, "run-x", evs)
    assert load_events(str(path))[-1]["event_type"] == "future_thing"


def test_mermaid_golden(fx):
    from praisonai.replay.export import to_mermaid

    assert to_mermaid(fx.team_events()) == GOLDEN_MERMAID


def test_mermaid_manager_lane_and_delegation(fx):
    from praisonai.replay.export import to_mermaid

    evs = [
        {"event_type": "agent_handoff", "agent_name": "Manager", "sequence_num": 0,
         "data": {"from_agent": "Manager", "to_agent": "Writer", "reason": "write; now #1", "kind": "delegate"}},
    ]
    out = to_mermaid(evs)
    assert "    participant Manager\n" in out
    # ';' and '#' would break the diagram
    assert "    Manager->>A0: delegate: write, now no.1\n" in out


def test_mermaid_legacy_trace_uses_agent_start_end(fx):
    from praisonai.replay.export import to_mermaid

    out = to_mermaid(fx.legacy_events())
    assert out.splitlines() == [
        "sequenceDiagram",
        "    participant You",
        "    participant A0 as Researcher",
        "    participant A1 as Writer",
        "    You->>A0: start",
        "    A0-->>You: done",
        "    A0->>A1: handoff: next",
        "    You->>A1: start",
        "    A1-->>You: done",
    ]


def _spans_by_name(otlp):
    spans = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"]
    return spans, {s["name"]: s for s in spans}


def _attrs(span):
    out = {}
    for a in span["attributes"]:
        v = a["value"]
        out[a["key"]] = next(iter(v.values()))
    return out


def test_otlp_ids_parents_and_attributes(fx):
    from praisonai.replay.export import to_otlp_json

    otlp = to_otlp_json(fx.team_events())
    scope = otlp["resourceSpans"][0]["scopeSpans"][0]["scope"]
    assert scope["name"] == "praisonai.replay"
    assert {"key": "gen_ai.semconv.stability", "value": {"stringValue": "development"}} in scope["attributes"]

    spans, by_name = _spans_by_name(otlp)
    trace_id = hashlib.sha256(b"run-team01").hexdigest()[:32]
    assert {s["traceId"] for s in spans} == {trace_id}

    def sid(seq):
        return hashlib.sha256(f"run-team01:{seq}".encode()).hexdigest()[:16]

    wf = by_name["invoke_workflow Blog team"]
    assert wf["spanId"] == sid(1) and wf["parentSpanId"] == sid(0)
    assert _attrs(wf)["gen_ai.operation.name"] == "invoke_workflow"

    task = by_name["task research"]
    assert task["spanId"] == sid(2) and task["parentSpanId"] == sid(1) and task["kind"] == 1

    agent = by_name["invoke_agent Researcher"]
    assert agent["parentSpanId"] == sid(2)
    assert _attrs(agent)["gen_ai.agent.name"] == "Researcher"

    chat = by_name["chat gpt-4o-mini"]
    assert chat["kind"] == 3 and chat["parentSpanId"] == sid(3)
    a = _attrs(chat)
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.request.model"] == "gpt-4o-mini"
    assert a["gen_ai.usage.input_tokens"] == "10" and a["gen_ai.usage.output_tokens"] == "5"

    tool = by_name["execute_tool web_search"]
    assert tool["parentSpanId"] == sid(3)
    assert _attrs(tool)["gen_ai.tool.name"] == "web_search"
    # Redacted by default: the api_key in the tool arguments never leaves.
    assert "sk-abcdefghijklmnop1234" not in json.dumps(otlp)

    approval = by_name["approval publish"]
    assert approval["parentSpanId"] == sid(11)
    assert _attrs(approval)["praisonai.approval.approved"] is True

    assert int(chat["endTimeUnixNano"]) > int(chat["startTimeUnixNano"])
    assert all(s["status"]["code"] == 1 for s in spans)


def test_otlp_legacy_trace_pairs_by_nesting(fx):
    from praisonai.replay.export import to_otlp_json

    spans, by_name = _spans_by_name(to_otlp_json(fx.legacy_events()))
    session = by_name["praisonai.session"]
    assert "parentSpanId" not in session
    agent_spans = [s for s in spans if s["name"].startswith("invoke_agent")]
    assert len(agent_spans) == 2
    assert all(s["parentSpanId"] == session["spanId"] for s in agent_spans)
    chat = by_name["chat gpt-4o-mini"]
    assert chat["parentSpanId"] == by_name["invoke_agent Researcher"]["spanId"]


def test_otlp_unfinished_span_is_unset(fx):
    from praisonai.replay.export import to_otlp_json

    evs = fx.team_events()[:5]  # live trace cut mid-run
    spans, by_name = _spans_by_name(to_otlp_json(evs))
    assert by_name["invoke_agent Researcher"]["status"] == {"code": 0}


_EXTERNAL_SRC = re.compile(r"<(script|link|img|iframe)[^>]+(src|href)\s*=\s*[\"']?(https?:)?//", re.I)


def test_html_is_self_contained_and_redacted(fx, monkeypatch):
    from praisonai.replay import export

    monkeypatch.setattr(export, "aiui_renderer_files", lambda: None)
    html = export.to_html(fx.team_events())
    assert html.startswith("<!doctype html>")
    assert not _EXTERNAL_SRC.search(html)
    assert "@import" not in html
    assert "window.__REPLAY_DATA__" in html
    assert "sk-abcdefghijklmnop1234" not in html
    assert "bob@example.com" not in html
    assert "Researcher" in html and "task_start" in html
    data = json.loads(re.search(r"window.__REPLAY_DATA__ = (.*?);</script>", html, re.S).group(1))
    assert data["run_id"] == "run-team01"
    assert data["graph"]["schema"] == "praisonai.graph/1"
    assert len(data["events"]) == len(fx.team_events())


def test_html_no_redact_keeps_content(fx, monkeypatch):
    from praisonai.replay import export

    monkeypatch.setattr(export, "aiui_renderer_files", lambda: None)
    assert "bob@example.com" in export.to_html(fx.team_events(), redact=False)


def test_html_inlines_aiui_renderer_when_available(fx, monkeypatch, tmp_path):
    from praisonai.replay import export

    core = tmp_path / "replay-core.js"
    view = tmp_path / "replay.js"
    core.write_text("window.ReplayCore = {}; // </script> must not end the tag")
    view.write_text("document.getElementById('replay-root').dataset.mounted = '1';")
    monkeypatch.setattr(export, "aiui_renderer_files", lambda: [core, view])
    html = export.to_html(fx.team_events())
    assert "window.ReplayCore = {};" in html and "dataset.mounted" in html
    assert html.index("window.__REPLAY_DATA__") < html.index("window.ReplayCore")
    assert "// </script>" not in html  # escaped so the inline script survives
    assert not _EXTERNAL_SRC.search(html)


def test_html_escapes_script_breakers_in_event_data(fx, monkeypatch):
    from praisonai.replay import export

    monkeypatch.setattr(export, "aiui_renderer_files", lambda: None)
    evs = fx.team_events()
    evs[9]["data"]["output_preview"] = "</script><script>alert(1)</script>"
    html = export.to_html(evs, redact=False)
    # Only "</script" can end an inline script; it must never appear unescaped
    # except as the real closing tags (one per <script>).
    assert "</script><script>alert(1)" not in html
    assert html.count("</script>") == html.count("<script")


def test_aiui_renderer_detection_requires_both_files(tmp_path, monkeypatch):
    import importlib.util
    from types import SimpleNamespace

    from praisonai.replay import export

    views = tmp_path / "pkg" / "templates" / "frontend" / "plugins" / "views"
    views.mkdir(parents=True)
    (views / "replay-core.js").write_text("x")
    fake = SimpleNamespace(submodule_search_locations=[str(tmp_path / "pkg")])
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake if name == "praisonaiui" else None)
    assert export.aiui_renderer_files() is None
    (views / "replay.js").write_text("y")
    assert [p.name for p in export.aiui_renderer_files()] == ["replay-core.js", "replay.js"]


def test_to_json_round_trip(fx):
    from praisonai.replay.export import to_json

    payload = json.loads(to_json(fx.team_events()))
    assert payload["run_id"] == "run-team01"
    assert payload["graph"]["name"] == "Blog team"
    assert payload["events"][6]["data"]["tool_args"]["api_key"] == "[REDACTED]"
    assert payload["events"][5]["prompt_tokens"] == 10  # envelope counters untouched
    raw = json.loads(to_json(fx.team_events(), redact=False))
    assert raw["events"][6]["data"]["tool_args"]["api_key"] == "sk-abcdefghijklmnop1234"


def test_redaction_keeps_numeric_token_counters():
    from praisonai.replay.export import redact_events

    out = redact_events([{"event_type": "llm_response", "data": {"max_tokens": 50, "token": "abc", "auth": {"x": 1}}}])
    assert out[0]["data"] == {"max_tokens": 50, "token": "[REDACTED]", "auth": "[REDACTED]"}
