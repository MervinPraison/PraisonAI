"""Fixtures for PraisonAI Replay tests: an isolated traces dir and contract-format traces."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def traces_dir(tmp_path, monkeypatch):
    """Point every trace read/write at a temp dir (never the developer's ~/.praison)."""
    d = tmp_path / "traces"
    monkeypatch.setenv("PRAISONAI_TRACES_DIR", str(d))
    monkeypatch.delenv("PRAISON_HOME", raising=False)
    return d


def write_trace(directory: Path, run_id: str, events, partial_tail: str = "") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.jsonl"
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
        if partial_tail:
            fh.write(partial_tail)  # a live trace's half-written last line
    return path


def _ev(seq, event_type, *, agent=None, data=None, parent=None, node=None, run_id="run-team01", t0=1_700_000_000.0, **extra):
    ev = {
        "schema_version": "1.1",
        "event_type": event_type,
        "timestamp": t0 + seq * 0.5,
        "session_id": run_id,
        "agent_name": agent,
        "sequence_num": seq,
        "messages_count": 0,
        "tokens_used": 0,
        "tokens_budget": 0,
        "data": data or {},
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "run_id": run_id,
    }
    if parent is not None:
        ev["parent_seq"] = parent
    if node is not None:
        ev["node_id"] = node
    ev.update(extra)
    return ev


GRAPH = {
    "schema": "praisonai.graph/1", "kind": "team", "name": "Blog team", "process": "sequential",
    "nodes": [
        {"id": "start:begin", "kind": "start", "label": "Brief", "parent": None, "meta": {}},
        {"id": "task:research", "kind": "task", "label": "research", "parent": None, "meta": {}},
        {"id": "task:write", "kind": "task", "label": "write", "parent": None, "meta": {}},
        {"id": "end:done", "kind": "end", "label": "Delivered", "parent": None, "meta": {}},
    ],
    "edges": [
        {"id": "start:begin->task:research:next", "source": "start:begin", "target": "task:research", "kind": "next", "label": None},
        {"id": "task:research->task:write:next", "source": "task:research", "target": "task:write", "kind": "next", "label": None},
        {"id": "task:write->end:done:next", "source": "task:write", "target": "end:done", "kind": "next", "label": None},
    ],
}


def team_events(run_id="run-team01", yaml_path=None):
    """A schema 1.1 sequential team run: research -> (handoff) -> write, with an approval."""
    meta = {"run_id": run_id}
    if yaml_path:
        meta["yaml_path"] = str(yaml_path)
    e = lambda *a, **k: _ev(*a, run_id=run_id, **k)  # noqa: E731
    return [
        e(0, "session_start", data=meta),
        e(1, "workflow_start", parent=0, data={"kind": "team", "name": "Blog team", "process": "sequential", "graph": GRAPH}),
        e(2, "task_start", parent=1, node="task:research",
          data={"name": "research", "description_preview": "Research AI", "agent": "Researcher"}),
        e(3, "agent_start", agent="Researcher", parent=2, node="agent:Researcher"),
        e(4, "llm_request", agent="Researcher", parent=3, data={"model": "gpt-4o-mini"}),
        e(5, "llm_response", agent="Researcher", parent=4, prompt_tokens=10, completion_tokens=5, cost_usd=0.0001,
          data={"model": "gpt-4o-mini", "duration_ms": 12.0, "finish_reason": "stop",
                "response_content": "Findings: AI is big"}),
        e(6, "tool_call_start", agent="Researcher", parent=3, node="tool:Researcher/web_search",
          data={"tool_name": "web_search", "tool_args": {"query": "ai", "api_key": "sk-abcdefghijklmnop1234"}}),
        e(7, "tool_call_end", agent="Researcher", parent=6, node="tool:Researcher/web_search",
          data={"tool_name": "web_search", "result": "contact bob@example.com", "duration_ms": 3.0}),
        e(8, "agent_end", agent="Researcher", parent=3, node="agent:Researcher"),
        e(9, "task_end", parent=2, node="task:research",
          data={"status": "completed", "retries": 0, "duration_ms": 3500, "output_preview": "Findings: AI is big"}),
        e(10, "agent_handoff", agent="Researcher", parent=1,
          data={"from_agent": "Researcher", "to_agent": "Writer", "reason": "draft it", "context_passed": {}, "kind": "handoff"}),
        e(11, "task_start", parent=1, node="task:write",
          data={"name": "write", "description_preview": "Write post", "agent": "Writer"}),
        e(12, "approval_requested", agent="Writer", parent=11, node="tool:Writer/publish",
          data={"approval_id": "ap1", "tool": "publish", "args": {}, "risk": "high", "kind": "tool_call"}),
        e(13, "approval_decided", agent="Writer", parent=12, node="tool:Writer/publish",
          data={"approval_id": "ap1", "approved": True, "reason": "ok", "approver": "you", "modified": False}),
        e(14, "task_end", parent=11, node="task:write",
          data={"status": "completed", "retries": 0, "duration_ms": 1000, "output_preview": "Post"}),
        e(15, "workflow_end", parent=1, data={"status": "completed", "duration_ms": 7000}),
        e(16, "session_end", parent=0, data={"status": "completed"}),
    ]


def legacy_events(run_id="run-legacy1"):
    """A schema 1.0 trace (no run_id / parent_seq / node_id), as written before Replay."""
    base = dict(session_id=run_id, messages_count=0, tokens_used=0, tokens_budget=0,
                prompt_tokens=0, completion_tokens=0, cost_usd=0.0, schema_version="1.0")
    rows = [
        ("session_start", None, {"agents_file": "agents.yaml", "run_id": run_id}),
        ("agent_start", "Researcher", {}),
        ("llm_request", "Researcher", {"model": "gpt-4o-mini"}),
        ("llm_response", "Researcher", {"response_tokens": 5, "duration_ms": 10.0, "finish_reason": "stop"}),
        ("agent_end", "Researcher", {}),
        ("agent_handoff", "Researcher", {"from_agent": "Researcher", "to_agent": "Writer", "reason": "next", "context_passed": {}}),
        ("agent_start", "Writer", {}),
        ("agent_end", "Writer", {}),
        ("session_end", None, {}),
    ]
    return [
        dict(base, event_type=t, agent_name=a, data=d, sequence_num=i, timestamp=1_600_000_000.0 + i)
        for i, (t, a, d) in enumerate(rows)
    ]


def flow_events(run_id="run-flow01", yaml_path=None, step_names=("research", "draft", "polish"), outputs=None):
    """A schema 1.1 AgentFlow run of handler steps."""
    outputs = outputs or {n: f"{n} output" for n in step_names}
    meta = {"run_id": run_id}
    if yaml_path:
        meta["yaml_path"] = str(yaml_path)
    e = lambda *a, **k: _ev(*a, run_id=run_id, **k)  # noqa: E731
    events = [e(0, "session_start", data=meta), e(1, "workflow_start", parent=0, data={"kind": "flow", "name": "f", "process": "workflow"})]
    seq = 2
    for name in step_names:
        start = seq
        events.append(e(seq, "step_start", parent=1, node=f"step:{name}", data={"name": name}))
        seq += 1
        events.append(e(seq, "step_end", parent=start, node=f"step:{name}",
                        data={"status": "completed", "duration_ms": 1, "output_preview": outputs[name]}))
        seq += 1
    events.append(e(seq, "workflow_end", parent=1, data={"status": "completed", "duration_ms": 9}))
    events.append(e(seq + 1, "session_end", parent=0, data={"status": "completed"}))
    return events


@pytest.fixture
def fx():
    """Trace builders: ``fx.team_events()``, ``fx.legacy_events()``, ``fx.flow_events()``, ``fx.write_trace()``."""
    import types

    return types.SimpleNamespace(
        team_events=team_events,
        legacy_events=legacy_events,
        flow_events=flow_events,
        write_trace=write_trace,
        GRAPH=GRAPH,
    )
