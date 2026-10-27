"""Export a replay trace: JSON, Mermaid, OTLP-JSON (OTel GenAI) or one HTML file.

    from praisonai.replay.events import load_events
    from praisonai.replay import export

    events = load_events("run-1a2b3c4d5e6f")
    html = export.to_html(events)            # self-contained, no CDN
    otlp = export.to_otlp_json(events)       # dict, OTLP/JSON trace payload

Every exporter redacts by default (secrets by key name, plus secret/PII
patterns in free text) using the helpers in ``praisonaiagents.trace.redact``.
Pass ``redact=False`` to export the trace as recorded.

Stdlib only: no OpenTelemetry dependency, nothing fetched at view time.
"""

from __future__ import annotations

import copy
import hashlib
import html as _html
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .events import as_dicts, etype, find_graph, pair_spans, run_id_of

__all__ = [
    "redact_events",
    "to_json",
    "to_mermaid",
    "to_otlp_json",
    "to_html",
    "aiui_renderer_files",
    "SEMCONV_STABILITY",
]

#: The OTel GenAI semantic conventions are still "Development" status.
SEMCONV_STABILITY = "development"
_REDACTED = "[REDACTED]"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def _redactors():
    """Key test + free-text scrubber, reused from ``praisonaiagents.trace.redact``."""
    from praisonaiagents.trace import redact as _r

    should_redact = getattr(_r, "_should_redact", None)
    if should_redact is None:  # pragma: no cover - older praisonaiagents
        def should_redact(key: str) -> bool:
            return _r.redact_dict({key: "x"}).get(key) == _r.REDACTED_VALUE
    return should_redact, _r.scrub_pii_text


def _redact_value(value: Any, should_redact, scrub) -> Any:
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            # Numbers/bools under a "token"-ish key are counters, not secrets
            # (``prompt_tokens``, ``max_tokens``); keep them readable.
            if isinstance(key, str) and should_redact(key) and not isinstance(item, (int, float, bool, type(None))):
                out[key] = _REDACTED
            else:
                out[key] = _redact_value(item, should_redact, scrub)
        return out
    if isinstance(value, list):
        return [_redact_value(item, should_redact, scrub) for item in value]
    return value


def redact_events(events: Iterable[Any]) -> List[Dict[str, Any]]:
    """Copies of ``events`` with secrets removed from ``data`` (envelope kept)."""
    should_redact, scrub = _redactors()
    out = []
    for ev in as_dicts(events):
        ev = copy.deepcopy(ev)
        if isinstance(ev.get("data"), dict):
            ev["data"] = _redact_value(ev["data"], should_redact, scrub)
        out.append(ev)
    return out


def _prepare(events: Iterable[Any], redact: bool) -> List[Dict[str, Any]]:
    return redact_events(events) if redact else as_dicts(events)


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def to_json(events: Iterable[Any], *, redact: bool = True, indent: Optional[int] = 2) -> str:
    """``{"run_id", "events", "graph"}`` as a JSON string."""
    evs = _prepare(events, redact)
    payload = {
        "schema": "praisonai.replay/1",
        "run_id": run_id_of(evs),
        "graph": find_graph(evs),
        "events": evs,
    }
    return json.dumps(payload, indent=indent, default=str)


# ---------------------------------------------------------------------------
# Mermaid sequence diagram
# ---------------------------------------------------------------------------

_YOU = "You"
_MANAGER = "Manager"


def _mm_text(text: Any, limit: int = 60) -> str:
    """Mermaid-safe message text (``;`` ends a statement, ``#`` starts an entity)."""
    s = " ".join(str(text or "").split())
    s = s.replace(";", ",").replace("#", "no.").replace("%%", "%")
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def to_mermaid(events: Iterable[Any], *, redact: bool = True) -> str:
    """A Mermaid ``sequenceDiagram`` of who handed what to whom.

    Lanes are "You", "Manager" (when a hierarchical manager appears) and one per
    agent in order of first appearance. Messages are task boundaries,
    hand-offs/delegations and approvals. A 1.0 trace without task events falls
    back to agent start/end.
    """
    evs = _prepare(events, redact)
    has_tasks = any(etype(e) == "task_start" for e in evs)

    agents: List[str] = []
    manager = False

    def lane(name: Optional[str]) -> str:
        nonlocal manager
        if not name:
            return _YOU
        if name == _MANAGER:
            manager = True
            return _MANAGER
        if name not in agents:
            agents.append(name)
        return name

    messages: List[Tuple[str, str, str, str]] = []  # (src, arrow, dst, text)
    open_agents: Dict[str, int] = {}
    task_starts: Dict[Any, Dict[str, Any]] = {}  # seq / node_id -> task_start event
    for ev in evs:
        kind = etype(ev)
        data = ev.get("data") or {}
        who = ev.get("agent_name")
        if kind == "task_start":
            task_starts[ev.get("sequence_num")] = ev
            if ev.get("node_id"):
                task_starts[ev["node_id"]] = ev
            dst = lane(data.get("agent") or who)
            messages.append((_YOU, "->>", dst, f"task {data.get('name') or ev.get('node_id') or ''}"))
        elif kind == "task_end":
            # task_end carries only the outcome; name/agent live on its start.
            start = task_starts.get(ev.get("parent_seq")) or task_starts.get(ev.get("node_id")) or {}
            s_data = start.get("data") or {}
            src = lane(data.get("agent") or s_data.get("agent") or who or start.get("agent_name"))
            name = data.get("name") or s_data.get("name") or ev.get("node_id") or ""
            messages.append((src, "-->>", _YOU, f"task {name} {data.get('status') or 'done'}"))
        elif kind == "agent_handoff":
            src = lane(data.get("from_agent") or who)
            dst = lane(data.get("to_agent"))
            label = data.get("kind") or "handoff"
            reason = data.get("reason")
            messages.append((src, "->>", dst, f"{label}: {reason}" if reason else label))
        elif kind == "approval_requested":
            src = lane(who)
            messages.append((src, "->>", _YOU, f"approve {data.get('tool') or 'action'}?"))
        elif kind == "approval_decided":
            dst = lane(who)
            verdict = "approved" if data.get("approved") else "denied"
            messages.append((_YOU, "-->>", dst, verdict))
        elif kind in ("agent_start", "agent_end") and who:
            name = lane(who)
            if has_tasks:
                continue
            if kind == "agent_start":
                open_agents[name] = open_agents.get(name, 0) + 1
                if open_agents[name] == 1:
                    messages.append((_YOU, "->>", name, "start"))
            else:
                open_agents[name] = max(0, open_agents.get(name, 0) - 1)
                if open_agents[name] == 0:
                    messages.append((name, "-->>", _YOU, "done"))

    ids: Dict[str, str] = {_YOU: _YOU, _MANAGER: _MANAGER}
    lines = ["sequenceDiagram", f"    participant {_YOU}"]
    if manager:
        lines.append(f"    participant {_MANAGER}")
    for i, name in enumerate(agents):
        ids[name] = f"A{i}"
        lines.append(f"    participant A{i} as {_mm_text(name, 40)}")
    for src, arrow, dst, text in messages:
        lines.append(f"    {ids[src]}{arrow}{ids[dst]}: {_mm_text(text)}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# OTLP-JSON (OpenTelemetry GenAI semantic conventions)
# ---------------------------------------------------------------------------

_KIND_INTERNAL = 1
_KIND_CLIENT = 3
_STATUS_UNSET, _STATUS_OK, _STATUS_ERROR = 0, 1, 2


def _trace_id(run_id: str) -> str:
    return hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:32]


def _span_id(run_id: str, start_seq: int) -> str:
    return hashlib.sha256(f"{run_id}:{start_seq}".encode("utf-8")).hexdigest()[:16]


def _attr(key: str, value: Any) -> Optional[Dict[str, Any]]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return {"key": key, "value": {"arrayValue": {"values": [{"stringValue": v} for v in value]}}}
    if not isinstance(value, str):
        value = json.dumps(value, default=str)
    return {"key": key, "value": {"stringValue": value}}


def _nanos(ts: Any) -> str:
    try:
        return str(int(float(ts) * 1_000_000_000))
    except (TypeError, ValueError):
        return "0"


def _span_shape(span: Dict[str, Any]) -> Tuple[str, int, List[Tuple[str, Any]]]:
    """(name, kind, attributes) for one start/end pair."""
    start, end = span["start"], span["end"] or {}
    s_data = start.get("data") or {}
    e_data = end.get("data") or {}
    agent = start.get("agent_name")
    kind = span["type"]
    attrs: List[Tuple[str, Any]] = [
        ("gen_ai.conversation.id", start.get("session_id")),
        ("praisonai.node_id", start.get("node_id")),
        ("praisonai.event_type", kind),
    ]
    if kind == "workflow_start":
        name = s_data.get("name") or "workflow"
        attrs += [
            ("gen_ai.operation.name", "invoke_workflow"),
            ("gen_ai.workflow.name", name),
            ("praisonai.workflow.kind", s_data.get("kind")),
            ("praisonai.workflow.process", s_data.get("process")),
            ("praisonai.forked_from", s_data.get("forked_from")),
        ]
        return f"invoke_workflow {name}", _KIND_INTERNAL, attrs
    if kind == "agent_start":
        attrs += [("gen_ai.operation.name", "invoke_agent"), ("gen_ai.agent.name", agent)]
        return f"invoke_agent {agent or ''}".strip(), _KIND_INTERNAL, attrs
    if kind == "llm_request":
        model = e_data.get("model") or s_data.get("model")
        attrs += [
            ("gen_ai.operation.name", "chat"),
            ("gen_ai.agent.name", agent),
            ("gen_ai.request.model", model),
            ("gen_ai.response.model", e_data.get("model")),
            ("gen_ai.usage.input_tokens", end.get("prompt_tokens") or None),
            ("gen_ai.usage.output_tokens", end.get("completion_tokens") or None),
            ("gen_ai.response.finish_reasons", [e_data["finish_reason"]] if e_data.get("finish_reason") else None),
            ("praisonai.cost_usd", end.get("cost_usd") or None),
        ]
        return f"chat {model or ''}".strip(), _KIND_CLIENT, attrs
    if kind == "tool_call_start":
        tool = s_data.get("tool_name") or e_data.get("tool_name")
        attrs += [
            ("gen_ai.operation.name", "execute_tool"),
            ("gen_ai.tool.name", tool),
            ("gen_ai.agent.name", agent),
            ("gen_ai.tool.call.arguments", s_data.get("tool_args") or None),
        ]
        return f"execute_tool {tool or ''}".strip(), _KIND_INTERNAL, attrs
    if kind == "task_start":
        attrs += [
            ("praisonai.task.name", s_data.get("name")),
            ("gen_ai.agent.name", s_data.get("agent") or agent),
            ("praisonai.task.status", e_data.get("status")),
            ("praisonai.task.retries", e_data.get("retries")),
        ]
        return f"task {s_data.get('name') or ''}".strip(), _KIND_INTERNAL, attrs
    if kind == "step_start":
        attrs += [
            ("praisonai.step.name", s_data.get("name")),
            ("praisonai.step.pattern", s_data.get("pattern")),
            ("praisonai.step.status", e_data.get("status")),
            ("praisonai.step.route", e_data.get("route")),
        ]
        return f"step {s_data.get('name') or ''}".strip(), _KIND_INTERNAL, attrs
    if kind == "approval_requested":
        attrs += [
            ("praisonai.approval.id", s_data.get("approval_id")),
            ("praisonai.approval.tool", s_data.get("tool")),
            ("praisonai.approval.risk", s_data.get("risk")),
            ("praisonai.approval.approved", e_data.get("approved")),
            ("praisonai.approval.approver", e_data.get("approver")),
        ]
        return f"approval {s_data.get('tool') or ''}".strip(), _KIND_INTERNAL, attrs
    # session_start / anything else
    return "praisonai.session", _KIND_INTERNAL, attrs


def _span_status(span: Dict[str, Any]) -> Dict[str, Any]:
    end = span["end"]
    if end is None:
        return {"code": _STATUS_UNSET}
    data = end.get("data") or {}
    failed = data.get("status") == "failed" or bool(data.get("error"))
    if span["type"] == "approval_requested" and data.get("approved") is False:
        return {"code": _STATUS_OK, "message": "denied"}
    if failed:
        return {"code": _STATUS_ERROR, "message": str(data.get("error") or "failed")[:200]}
    return {"code": _STATUS_OK}


def to_otlp_json(events: Iterable[Any], *, redact: bool = True, service_name: str = "praisonai") -> Dict[str, Any]:
    """An OTLP/JSON ``ExportTraceServiceRequest`` for the trace.

    Ids are deterministic so re-exporting a run gives the same trace:
    ``traceId = sha256(run_id)[:32]`` and ``spanId = sha256(f"{run_id}:{start_seq}")[:16]``;
    ``parentSpanId`` comes from ``parent_seq`` (schema 1.1) or nesting (1.0).
    Attributes follow the OTel GenAI semantic conventions, which are still in
    *Development* status (recorded as ``gen_ai.semconv.stability`` on the scope).
    """
    evs = _prepare(events, redact)
    run_id = run_id_of(evs)
    trace_id = _trace_id(run_id)
    spans, _points = pair_spans(evs)
    last_ts = max((e.get("timestamp") or 0 for e in evs), default=0)
    known = {span["seq"] for span in spans}

    out_spans = []
    for span in spans:
        name, kind, attrs = _span_shape(span)
        start, end = span["start"], span["end"]
        record: Dict[str, Any] = {
            "traceId": trace_id,
            "spanId": _span_id(run_id, span["seq"]),
            "name": name,
            "kind": kind,
            "startTimeUnixNano": _nanos(start.get("timestamp")),
            "endTimeUnixNano": _nanos((end or {}).get("timestamp", last_ts)),
            "attributes": [a for a in (_attr(k, v) for k, v in attrs) if a],
            "status": _span_status(span),
        }
        if span["parent"] is not None and span["parent"] in known:
            record["parentSpanId"] = _span_id(run_id, span["parent"])
        out_spans.append(record)

    try:
        from praisonai.version import __version__ as version
    except Exception:  # pragma: no cover - version module is always present in the wrapper
        version = ""

    return {
        "resourceSpans": [{
            "resource": {"attributes": [
                _attr("service.name", service_name),
                _attr("praisonai.run_id", run_id),
            ]},
            "scopeSpans": [{
                "scope": {
                    "name": "praisonai.replay",
                    "version": version,
                    "attributes": [_attr("gen_ai.semconv.stability", SEMCONV_STABILITY)],
                },
                "spans": out_spans,
            }],
        }]
    }


# ---------------------------------------------------------------------------
# HTML (self-contained)
# ---------------------------------------------------------------------------

_RENDERER_FILES = ("replay-core.js", "replay.js")


def aiui_renderer_files() -> Optional[List[Path]]:
    """The aiui standalone replay renderer, if aiui is installed and ships it."""
    import importlib.util

    try:
        spec = importlib.util.find_spec("praisonaiui")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.submodule_search_locations:
        return None
    for root in spec.submodule_search_locations:
        views = Path(root) / "templates" / "frontend" / "plugins" / "views"
        files = [views / name for name in _RENDERER_FILES]
        if all(f.is_file() for f in files):
            return files
    return None


def _script_safe(text: str) -> str:
    """Make text safe inside an inline ``<script>`` element."""
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")


def _json_for_script(value: Any) -> str:
    """JSON that cannot end or re-open the surrounding ``<script>`` (every ``<`` escaped)."""
    text = json.dumps(value, default=str)
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="PraisonAI Replay">
<title>PraisonAI Replay: {title}</title>
<style>
:root {{ --bg:#ffffff; --fg:#1d1d1f; --muted:#5f6368; --line:#d9dce1; --agent:#8B0000; --tool:#0F7287; --human:#8A5A00; --manager:#3C4A5C; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16181c; --fg:#ecedef; --muted:#a3a8b0; --line:#30343b; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }}
header {{ padding:16px; border-bottom:1px solid var(--line); }}
h1 {{ font-size:18px; margin:0 0 4px; }}
.meta {{ color:var(--muted); }}
main {{ padding:16px; }}
table {{ border-collapse:collapse; width:100%; }}
th, td {{ text-align:left; vertical-align:top; padding:6px 8px; border-bottom:1px solid var(--line); }}
th {{ font-weight:600; color:var(--muted); }}
td.seq {{ font-variant-numeric:tabular-nums; color:var(--muted); width:3em; }}
.k {{ display:inline-block; padding:0 6px; border-radius:4px; border:1px solid currentColor; font-size:12px; }}
.k-agent {{ color:var(--agent); }} .k-tool {{ color:var(--tool); }} .k-human {{ color:var(--human); }} .k-manager {{ color:var(--manager); }}
td.indent0 {{ padding-left:8px; }}
details summary {{ cursor:pointer; color:var(--muted); }}
pre {{ white-space:pre-wrap; word-break:break-word; margin:4px 0 0; }}
:focus-visible {{ outline:2px solid var(--tool); outline-offset:2px; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; animation:none !important; }} }}
</style>
</head>
<body>
<div id="replay-root">{fallback}</div>
<script id="replay-data">window.__REPLAY_DATA__ = {data};</script>
{scripts}
</body>
</html>
"""


def _lane_class(ev: Dict[str, Any]) -> Tuple[str, str]:
    kind = etype(ev)
    if kind.startswith("tool_call"):
        return "k-tool", "tool"
    if kind.startswith("approval"):
        return "k-human", "you"
    if ev.get("agent_name") == _MANAGER:
        return "k-manager", "manager"
    return "k-agent", "agent"


def _describe(ev: Dict[str, Any]) -> str:
    kind = etype(ev)
    data = ev.get("data") or {}
    who = ev.get("agent_name") or ""
    if kind == "agent_handoff":
        return f"{data.get('from_agent')} → {data.get('to_agent')} ({data.get('kind') or 'handoff'})"
    if kind.startswith("tool_call"):
        return f"{who} · {data.get('tool_name') or ''}"
    if kind in ("task_start", "task_end", "step_start", "step_end", "workflow_start", "workflow_end"):
        bits = [str(data.get("name") or ev.get("node_id") or ""), str(data.get("status") or "")]
        return " · ".join(b for b in bits if b)
    if kind.startswith("approval"):
        if kind == "approval_decided":
            return "approved" if data.get("approved") else "denied"
        return f"approve {data.get('tool') or ''}?"
    return who


def _fallback_table(evs: List[Dict[str, Any]], run_id: str) -> str:
    spans, _ = pair_spans(evs)
    depth: Dict[int, int] = {}
    indent_of: Dict[int, int] = {}  # id(event) -> nesting level
    for span in spans:
        parent = span["parent"]
        depth[span["seq"]] = depth.get(parent, -1) + 1 if parent is not None else 0
        indent_of[id(span["start"])] = depth[span["seq"]]
        if span["end"] is not None:
            indent_of[id(span["end"])] = depth[span["seq"]]
    total_cost = sum(float(e.get("cost_usd") or 0) for e in evs)
    total_tokens = sum(int(e.get("prompt_tokens") or 0) + int(e.get("completion_tokens") or 0) for e in evs)
    agents = sorted({e.get("agent_name") for e in evs if e.get("agent_name")})
    t0 = min((e.get("timestamp") or 0 for e in evs), default=0)

    rows = []
    for i, ev in enumerate(evs):
        seq = ev.get("sequence_num", i)
        cls, label = _lane_class(ev)
        offset = max(0.0, float(ev.get("timestamp") or t0) - t0)
        indent = indent_of.get(id(ev))
        if indent is None:
            parent = ev.get("parent_seq")
            indent = depth.get(parent, -1) + 1 if isinstance(parent, int) else 0
        raw = _html.escape(json.dumps(ev.get("data") or {}, indent=2, default=str))
        rows.append(
            "<tr>"
            f"<td class=\"seq\">{_html.escape(str(seq))}</td>"
            f"<td>+{offset:.2f}s</td>"
            f"<td><span class=\"k {cls}\">{label}</span></td>"
            f"<td style=\"padding-left:{8 + 16 * min(indent, 8)}px\"><strong>{_html.escape(etype(ev))}</strong> "
            f"{_html.escape(_describe(ev))}"
            f"<details><summary>data</summary><pre>{raw}</pre></details></td>"
            "</tr>"
        )
    return (
        "<header><h1>PraisonAI Replay</h1>"
        f"<div class=\"meta\">Run <code>{_html.escape(run_id)}</code> · {len(evs)} events · "
        f"agents: {_html.escape(', '.join(agents) or '-')} · tokens: {total_tokens:,} · cost: ${total_cost:.6f}</div>"
        "</header><main><table aria-label=\"Replay timeline\">"
        "<thead><tr><th>#</th><th>Time</th><th>Lane</th><th>What happened</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></main>"
    )


def to_html(
    events: Iterable[Any],
    *,
    redact: bool = True,
    graph: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
) -> str:
    """One self-contained HTML file: the events, the graph and a renderer.

    Uses aiui's standalone replay renderer (``replay-core.js`` + ``replay.js``)
    when aiui is installed and ships it, inlined so the file works offline;
    otherwise a built-in table timeline. Nothing is loaded from a CDN.
    """
    evs = _prepare(events, redact)
    run_id = run_id_of(evs)
    graph = graph if graph is not None else find_graph(evs)
    data = {"run_id": run_id, "events": evs, "graph": graph}

    renderer = aiui_renderer_files()
    if renderer:
        # aiui's renderer files are ES modules (``export`` statements), so they
        # must be inlined as module scripts; a classic <script> rejects them.
        scripts = "\n".join(
            f"<script type=\"module\" data-src=\"{_html.escape(p.name)}\">\n{_script_safe(p.read_text(encoding='utf-8'))}\n</script>"
            for p in renderer
        )
    else:
        scripts = ""
    # The table is always present: it is the no-JS view and what a renderer
    # replaces when it mounts into #replay-root.
    fallback = _fallback_table(evs, run_id)
    return _PAGE.format(
        title=_html.escape(title or run_id),
        fallback=fallback,
        data=_json_for_script(data),
        scripts=scripts,
    )
