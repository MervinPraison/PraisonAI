"""Raw trace-event helpers shared by export, rerun and the replay CLI.

Events are handled as plain dicts (one ``ContextEvent.to_dict()`` per JSONL
line) rather than ``ContextEvent`` objects, so that:

- event types this version of ``praisonaiagents`` does not know survive intact
  (``ContextEvent.from_dict`` may relabel them);
- schema 1.1 fields (``run_id``, ``parent_seq``, ``node_id``) are read when
  present and simply absent on 1.0 traces;
- a partially written last line (a live recording) is skipped, not fatal.

Stdlib only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from .storage import get_trace_path, resolve_traces_dir

__all__ = [
    "SAFE_RUN_ID",
    "SPAN_PAIRS",
    "as_dicts",
    "etype",
    "find_graph",
    "load_events",
    "pair_spans",
    "resolve_trace_path",
    "run_id_of",
    "session_meta",
]

#: Run ids that are safe to use as file names and URL fragments (contract §5).
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")

#: start event type -> matching end event type.
SPAN_PAIRS: Dict[str, str] = {
    "session_start": "session_end",
    "workflow_start": "workflow_end",
    "task_start": "task_end",
    "step_start": "step_end",
    "agent_start": "agent_end",
    "llm_request": "llm_response",
    "tool_call_start": "tool_call_end",
    "approval_requested": "approval_decided",
}
_END_TO_START = {end: start for start, end in SPAN_PAIRS.items()}

EventLike = Union[Dict[str, Any], Any]


def etype(event: Dict[str, Any]) -> str:
    """The raw event type string (an unknown type is kept as-is)."""
    data = event.get("data") or {}
    raw = data.get("_raw_event_type") if isinstance(data, dict) else None
    value = raw or event.get("event_type") or ""
    return getattr(value, "value", value)


def as_dicts(events: Iterable[EventLike]) -> List[Dict[str, Any]]:
    """Normalise ``ContextEvent`` objects or dicts to plain dicts."""
    out: List[Dict[str, Any]] = []
    for ev in events or []:
        if isinstance(ev, dict):
            out.append(ev)
        elif hasattr(ev, "to_dict"):
            out.append(ev.to_dict())
    return out


def resolve_trace_path(target: Union[str, Path], traces_dir: Optional[Path] = None) -> Path:
    """Map a run id, session id or JSONL path to the trace file path."""
    text = str(target)
    if text.endswith(".jsonl") or "/" in text or "\\" in text:
        return Path(text).expanduser()
    return get_trace_path(text, Path(traces_dir) if traces_dir else resolve_traces_dir())


def load_events(target: Union[str, Path], traces_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Read every complete event of a trace as dicts, in file order.

    Blank lines and lines that are not valid JSON objects (typically the
    still-being-written last line of a live trace) are skipped.

    Raises:
        FileNotFoundError: if the trace does not exist.
    """
    path = resolve_trace_path(target, traces_dir)
    if not path.exists():
        raise FileNotFoundError(f"Trace not found: {target}")
    events: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                events.append(obj)
    return events


def run_id_of(events: List[Dict[str, Any]], default: str = "run") -> str:
    """The run id of a trace: first ``run_id`` field, else ``session_id``."""
    for ev in events:
        if ev.get("run_id"):
            return str(ev["run_id"])
    for ev in events:
        if ev.get("session_id"):
            return str(ev["session_id"])
    return default


def session_meta(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The ``data`` of the first ``session_start`` event (recording metadata)."""
    for ev in events:
        if etype(ev) == "session_start":
            data = ev.get("data")
            return dict(data) if isinstance(data, dict) else {}
    return {}


def find_graph(events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The static graph embedded in the first ``workflow_start`` (schema 1.1)."""
    for ev in events:
        if etype(ev) == "workflow_start":
            graph = (ev.get("data") or {}).get("graph")
            if isinstance(graph, dict):
                return graph
    return None


def _seq(event: Dict[str, Any], index: int) -> int:
    seq = event.get("sequence_num")
    return seq if isinstance(seq, int) else index


def _same_subject(start: Dict[str, Any], end: Dict[str, Any]) -> bool:
    """Heuristic match for 1.0 traces that carry no ``parent_seq``."""
    if start.get("agent_name") != end.get("agent_name") and end.get("agent_name"):
        return False
    s_data, e_data = start.get("data") or {}, end.get("data") or {}
    for key in ("tool_name", "name"):
        if s_data.get(key) and e_data.get(key) and s_data[key] != e_data[key]:
            return False
    if start.get("node_id") and end.get("node_id") and start["node_id"] != end["node_id"]:
        return False
    return True


def pair_spans(events: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Turn start/end event pairs into spans.

    Returns ``(spans, points)``. Each span is
    ``{"start": ev, "end": ev|None, "seq": int, "parent": int|None, "type": str}``
    where ``parent`` is the ``seq`` of the enclosing span. ``points`` are events
    that are neither a start nor an end (messages, hand-offs, snapshots...).

    Schema 1.1 traces are paired exactly through ``parent_seq``; 1.0 traces fall
    back to a stack (innermost open span of the same kind and subject).
    """
    spans: Dict[int, Dict[str, Any]] = {}
    order: List[int] = []
    points: List[Dict[str, Any]] = []
    open_stack: List[int] = []

    for index, ev in enumerate(events):
        kind = etype(ev)
        seq = _seq(ev, index)
        if kind in SPAN_PAIRS:
            parent = ev.get("parent_seq")
            if not isinstance(parent, int):
                parent = open_stack[-1] if open_stack else None
            spans[seq] = {"start": ev, "end": None, "seq": seq, "parent": parent, "type": kind}
            order.append(seq)
            open_stack.append(seq)
        elif kind in _END_TO_START:
            start_kind = _END_TO_START[kind]
            target = ev.get("parent_seq")
            if not (isinstance(target, int) and target in spans and spans[target]["end"] is None):
                target = None
                for cand in reversed(open_stack):
                    span = spans[cand]
                    if span["type"] == start_kind and _same_subject(span["start"], ev):
                        target = cand
                        break
            if target is None:
                points.append(ev)
                continue
            spans[target]["end"] = ev
            if target in open_stack:
                open_stack.remove(target)
        else:
            points.append(ev)
    return [spans[s] for s in order], points
