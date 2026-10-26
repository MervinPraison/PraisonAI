"""Re-run a recorded run from one node: ``praisonai replay rerun RUN --from NODE``.

Everything before NODE is served from the recording instead of being executed
again; NODE and everything after it runs fresh, and the new run is recorded
with ``workflow_start.data.forked_from = {run_id, node_id}``.

- **AgentFlow** -- :class:`TraceStepCache`, a ``StepCacheProtocol`` seeded with
  the recorded ``step_end`` outputs. The flow's own cache-hit path replays them,
  so variables, ``{{previous_output}}`` and callbacks behave as on a real hit.
- **AgentTeam** -- the team's existing task-state restore: earlier tasks come
  back ``completed`` with their recorded output (which the process layer then
  skips), tasks from NODE on are reset to ``not started``.

Python::

    from praisonai.replay.rerun import rerun
    rec, result = rerun(flow, "run-1a2b3c4d5e6f", "step:draft", input="AI")

Needs a schema 1.1 trace (events carry ``node_id``). A 1.0 trace, an unknown
node or an output that was only recorded as a truncated preview fail with
:class:`RerunError` rather than silently re-running with the wrong inputs.
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
from collections import OrderedDict
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

from praisonaiagents.trace.redact import REDACTED_VALUE
from praisonaiagents.workflows.step_cache import StepCacheProtocol

from .events import as_dicts, etype, load_events, pair_spans, run_id_of

__all__ = [
    "RerunError",
    "RerunPlan",
    "TraceStepCache",
    "plan_rerun",
    "rerun",
    "rerun_scope",
    "seed_flow",
    "seed_team",
]

#: Previews are truncated to this many characters by the emitter (contract §2).
PREVIEW_LIMIT = 500
_REUSABLE = {"completed", "cached"}
#: The emitter's marker for an ``llm_response`` cut to its head and tail.
_SHORTENED = re.compile(r"\n\.\.\.\[[\d,]+ chars, showing first/last portions\]\.\.\.\n")


class RerunError(RuntimeError):
    """The recording cannot support a re-run from the requested node."""


class RerunPlan:
    """What to reuse: recorded outputs (in order) for every node before ``node_id``."""

    def __init__(
        self,
        source_run_id: str,
        node_id: str,
        kind: str,
        outputs: "OrderedDict[str, Any]",
        variables: Optional[Dict[str, Dict[str, Any]]] = None,
        started_before: Optional[List[str]] = None,
    ):
        self.source_run_id = source_run_id
        self.node_id = node_id
        self.kind = kind  # "flow" | "team"
        self.outputs = outputs
        # Variable updates a step's handler made, when its step_end recorded them.
        self.variables = variables or {}
        # Every node of the target's kind that STARTED before it, whatever its
        # status (skipped and failed steps too): what the recorded run executed.
        self.started_before = list(started_before or [])

    @property
    def forked_from(self) -> Dict[str, str]:
        return {"run_id": self.source_run_id, "node_id": self.node_id}

    def __repr__(self) -> str:
        return f"RerunPlan(from={self.node_id!r}, reuse={list(self.outputs)!r})"


# ---------------------------------------------------------------------------
# Reading the recording
# ---------------------------------------------------------------------------

def _looks_truncated(preview: str) -> bool:
    return len(preview) >= PREVIEW_LIMIT - 3 or preview.endswith(("…", "..."))


def _recover_output(span: Dict[str, Any], events: List[Dict[str, Any]]) -> Any:
    """The full output of a finished task/step, or RerunError if only a stub exists."""
    end_data = span["end"].get("data") or {}
    if "output" in end_data and end_data["output"] is not None:
        return end_data["output"]
    preview = end_data.get("output_preview")
    if preview is None:
        raise RerunError(
            f"{span['start'].get('node_id')} has no recorded output (no output/output_preview "
            "on its end event); re-record the run with this version of PraisonAI."
        )
    preview = str(preview)
    if not _looks_truncated(preview):
        return preview
    # The preview was cut at 500 chars: the agent's last LLM answer inside the
    # span is the untruncated text when it starts the same way.
    head = preview.rstrip("…").rstrip(".")[:100]
    lo, hi = span["seq"], span["end"].get("sequence_num", float("inf"))
    for ev in reversed(events):
        seq = ev.get("sequence_num")
        if not isinstance(seq, int) or not (lo < seq < hi) or etype(ev) != "llm_response":
            continue
        content = (ev.get("data") or {}).get("response_content")
        if isinstance(content, str) and content.startswith(head):
            if _SHORTENED.search(content):
                break  # the emitter kept only its head and tail: not the full output
            return content
    raise RerunError(
        f"Only a truncated preview of {span['start'].get('node_id')}'s output was recorded, so "
        "re-running after it would feed the next node the wrong input. Re-record with "
        "full content (praisonai.replay.record(full_content=True)) or re-run from an earlier node."
    )


def plan_rerun(events: Union[str, List[Any]], node_id: str) -> RerunPlan:
    """Work out which recorded outputs to reuse for a re-run from ``node_id``."""
    evs = load_events(events) if isinstance(events, (str, os.PathLike)) else as_dicts(events)
    if not evs:
        raise RerunError("The trace is empty.")
    if not any(ev.get("node_id") for ev in evs):
        raise RerunError(
            "This trace has no node ids (schema 1.0). Re-running from a node needs a run "
            "recorded with PraisonAI Replay schema 1.1 or later; record it again."
        )
    spans, _ = pair_spans(evs)
    nodes = [s for s in spans if s["type"] in ("task_start", "step_start") and s["start"].get("node_id")]
    target = next((s for s in nodes if s["start"]["node_id"] == node_id), None)
    if target is None:
        known = ", ".join(dict.fromkeys(s["start"]["node_id"] for s in nodes)) or "none"
        raise RerunError(f"Node {node_id!r} is not in this trace. Re-runnable nodes: {known}")
    kind = "team" if target["type"] == "task_start" else "flow"
    for ev in evs:
        if etype(ev) == "workflow_start":
            recorded = (ev.get("data") or {}).get("kind")
            if recorded in ("team", "flow"):
                kind = recorded
            break

    outputs: "OrderedDict[str, Any]" = OrderedDict()
    variables: Dict[str, Dict[str, Any]] = {}
    started_before = [
        s["start"]["node_id"] for s in nodes
        if s["type"] == target["type"] and s["seq"] < target["seq"]
    ]
    for span in nodes:
        if span["type"] != target["type"] or span["end"] is None:
            continue
        end_seq = span["end"].get("sequence_num")
        # Reuse only what had FINISHED before NODE started: that excludes NODE,
        # everything after it, and containers that enclose it.
        if not isinstance(end_seq, int) or end_seq >= target["seq"]:
            continue
        status = (span["end"].get("data") or {}).get("status", "completed")
        if status not in _REUSABLE:
            continue
        outputs[span["start"]["node_id"]] = _recover_output(span, evs)
        recorded_vars = (span["end"].get("data") or {}).get("variables")
        if isinstance(recorded_vars, dict):
            # A redacted value cannot be restored: the marker would replace the
            # real value in the re-run's variables.
            hidden = [k for k, v in recorded_vars.items() if REDACTED_VALUE in repr(v)]
            if hidden:
                raise RerunError(
                    f"{span['start']['node_id']} set {', '.join(map(repr, hidden))}, which the "
                    "recording redacted, so it cannot be restored; re-run from that node or earlier."
                )
            variables[span["start"]["node_id"]] = recorded_vars
    return RerunPlan(run_id_of(evs), node_id, kind, outputs, variables, started_before)


# ---------------------------------------------------------------------------
# AgentFlow: a step cache seeded from the recording
# ---------------------------------------------------------------------------

def _step_name(node_id: str) -> str:
    """``step:draft#2`` -> ``draft`` (duplicate suffixes are served in order)."""
    name = node_id.split(":", 1)[1] if ":" in node_id else node_id
    head, sep, tail = name.rpartition("#")
    return head if sep and tail.isdigit() else name


class TraceStepCache(StepCacheProtocol):
    """``StepCacheProtocol`` that serves recorded outputs for the steps before NODE.

    It never caches anything new: a miss means "run this step", and ``set`` is
    a no-op so later steps always execute. Bind it to the flow
    (:func:`seed_flow` does) so it can tell which step is asking -- the flow
    marks the step ``running`` just before it consults the cache.

    ``hits`` lists the step names served from the recording. ``variables``
    (node id -> dict) restores the variable updates a handler made, when the
    recording kept them.
    """

    def __init__(
        self,
        outputs: "OrderedDict[str, Any]",
        variables: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        variables = variables or {}
        self._queues: Dict[str, List[Any]] = {}
        for node_id, output in outputs.items():
            self._queues.setdefault(_step_name(node_id), []).append((output, variables.get(node_id) or {}))
        self._flow: Any = None
        self._lock = threading.Lock()
        self.hits: List[str] = []
        self.misses = 0

    def bind(self, flow: Any) -> "TraceStepCache":
        self._flow = flow
        return self

    def _current_step(self) -> Optional[str]:
        statuses = getattr(self._flow, "step_statuses", None) or {}
        running = [name for name, status in statuses.items() if status == "running" and self._queues.get(name)]
        # Two candidates (parallel branches) are ambiguous: run them fresh
        # rather than risk serving one step another's output.
        return running[0] if len(running) == 1 else None

    def _step_obj(self, name: str) -> Any:
        for step in getattr(self._flow, "steps", None) or []:
            if getattr(step, "name", None) == name or getattr(step, "__name__", None) == name:
                return step
        return None

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            name = self._current_step()
            if name is None:
                self.misses += 1
                return None
            output, recorded_vars = self._queues[name].pop(0)
            self.hits.append(name)
        step = self._step_obj(name)
        var = getattr(step, "output_variable", None) or f"{name}_output"
        return {
            "output": output,
            "variables": {**recorded_vars, var: output},
            "stop": False,
            "step_record": {"step": name, "output": output, "status": "completed", "retries": 0},
        }

    def set(self, key: str, value: Dict[str, Any]) -> None:
        return None


def _flow_step_names(steps: Any) -> set:
    """Names of every step in a flow, including those nested in patterns."""
    names: set = set()
    stack = list(steps or [])
    while stack:
        step = stack.pop()
        for attr in ("name", "__name__", "_yaml_step_name"):  # YAML agent steps run as their step name
            value = getattr(step, attr, None)
            if isinstance(value, str):
                names.add(value)
        routes = getattr(step, "routes", None)
        if isinstance(routes, dict):
            for branch in routes.values():
                stack.extend(branch if isinstance(branch, list) else [branch])
        for attr in ("steps", "default", "then_steps", "else_steps"):
            value = getattr(step, attr, None)
            if isinstance(value, list):
                stack.extend(value)
        inner = getattr(step, "step", None)
        if inner is not None:
            stack.append(inner)
    return names


def _check_flow_order(
    steps: List[Any],
    recorded: List[str],
    started_before: Optional[List[str]] = None,
    node_ids: Optional[Dict[int, str]] = None,
) -> None:
    """Reject a sequential flow whose top-level steps are not in the recorded order.

    Only checked when the flow runs strictly in sequence: ``next_steps`` /
    ``branch_condition`` jumps or a repeated node (``#2``) can revisit steps.
    Also rejects a step inserted before the target that never ran in the
    recording: it would run fresh and replace the reused output the target
    expects as its input. Steps are matched by graph node id (``node_ids``,
    id(step) -> node id), so unnamed patterns such as ``If`` are covered too.
    A target nested in a pattern is checked up to that pattern: the last
    top-level step the recording started before the target.
    """
    if any(getattr(s, "next_steps", None) or getattr(s, "branch_condition", None) for s in steps):
        return
    if any("#" in node_id for node_id in recorded):
        return
    position: Dict[str, int] = {}
    for index, step in enumerate(steps):
        for attr in ("name", "__name__", "_yaml_step_name"):
            value = getattr(step, attr, None)
            if isinstance(value, str):
                position.setdefault(value, index)
    if started_before is not None and node_ids is not None and recorded:
        ran = set(started_before)
        top = [node_ids.get(id(step)) for step in steps]
        if recorded[-1] in top:
            anchor = top.index(recorded[-1])
        else:  # nested target: its container is the last top-level step that started
            anchor = max((i for i, node_id in enumerate(top) if node_id in ran), default=-1)
        if anchor > 0:
            for step, node_id in zip(steps, top[:anchor]):
                if node_id not in ran:
                    raise RerunError(
                        f"Step {node_id or type(step).__name__!r} comes before {recorded[-1]!r} in "
                        "this flow but did not run in the recording; re-run against the flow that recorded it."
                    )
    last = -1
    for node_id in recorded:  # nested steps have no top-level position: skipped
        index = position.get(_step_name(node_id))
        if index is None:
            continue
        if index < last:
            raise RerunError(
                f"Recorded node {node_id!r} runs in a different order in this flow; "
                "re-run against the flow that recorded it."
            )
        last = index


def seed_flow(flow: Any, plan: RerunPlan) -> TraceStepCache:
    """Install a :class:`TraceStepCache` for ``plan`` on an AgentFlow."""
    from praisonaiagents.workflows.diagram import _flow_graph
    from praisonaiagents.workflows.step_cache import resolve_step_cache

    # A different or edited flow would silently run unmatched steps fresh.
    names = _flow_step_names(getattr(flow, "steps", None))
    recorded = [*plan.outputs, plan.node_id]
    for node_id in recorded:
        if _step_name(node_id) not in names:
            raise RerunError(f"Recorded node {node_id!r} does not match any step in this flow.")
    _check_flow_order(
        getattr(flow, "steps", None) or [], recorded, plan.started_before, _flow_graph(flow).ids,
    )

    cache = TraceStepCache(plan.outputs, plan.variables).bind(flow)
    flow.cache = cache
    # AgentFlow resolves ``cache=`` once at construction; resolve the new one
    # the same way so the run uses it.
    flow._step_cache = resolve_step_cache(cache)
    return cache


# ---------------------------------------------------------------------------
# AgentTeam: restore finished tasks, reset the rest
# ---------------------------------------------------------------------------

def _task_key(team: Any, node_id: str) -> Any:
    ref = node_id.split(":", 1)[1] if ":" in node_id else node_id
    tasks = getattr(team, "tasks", {}) or {}
    for key, task in tasks.items():
        if getattr(task, "name", None) == ref:
            return key
    for index, key in enumerate(tasks):
        if str(index) == ref or str(key) == ref:
            return key
    return None


def seed_team(team: Any, plan: RerunPlan) -> List[Any]:
    """Mark the tasks before NODE completed (with their recorded output), reset the rest.

    Returns the task keys restored from the recording.
    """
    tasks = getattr(team, "tasks", None)
    if not isinstance(tasks, dict):
        raise RerunError("Expected an AgentTeam (an object with a tasks dict).")
    snapshot: Dict[str, Dict[str, Any]] = {}
    restored: List[Any] = []
    for node_id, output in plan.outputs.items():
        key = _task_key(team, node_id)
        if key is None:
            raise RerunError(f"Recorded node {node_id!r} does not match any task in this team.")
        snapshot[str(key)] = {"status": "completed", "result": output}
        restored.append(key)
    if _task_key(team, plan.node_id) is None:
        raise RerunError(f"Node {plan.node_id!r} does not match any task in this team.")

    for key, task in tasks.items():
        if key in restored:
            continue
        task.status = "not started"
        task.result = None
        if hasattr(task, "retry_count"):
            task.retry_count = 0

    restore = getattr(team, "_restore_serialised_task_state", None)
    if callable(restore):
        restore(snapshot)  # the team's own checkpoint-restore path (wraps text as TaskOutput)
    else:  # pragma: no cover - older praisonaiagents
        for key in restored:
            tasks[key].status = "completed"
            tasks[key].result = snapshot[str(key)]["result"]
    return restored


# ---------------------------------------------------------------------------
# Seeding objects built elsewhere (YAML runs go through AgentsGenerator)
# ---------------------------------------------------------------------------

def _is_team(obj: Any) -> bool:
    return isinstance(getattr(obj, "tasks", None), dict) and hasattr(obj, "run_all_tasks")


def _is_flow(obj: Any) -> bool:
    return hasattr(obj, "step_statuses") and hasattr(obj, "steps")


def _seed_built(obj: Any, plan: RerunPlan, on_seeded: Callable[[Any], None]) -> None:
    """Seed a team/flow the YAML runner just built (called by ``_hook``)."""
    if plan.kind == "flow" and _is_flow(obj):
        on_seeded(seed_flow(obj, plan))
    elif plan.kind == "team" and _is_team(obj):
        on_seeded(seed_team(obj, plan))


@contextlib.contextmanager
def rerun_scope(plan: RerunPlan, on_seeded: Optional[Callable[[Any], None]] = None) -> Iterator[RerunPlan]:
    """While active, the next team/flow built by the YAML runner is seeded from ``plan``."""
    from . import _hook

    token = _hook.ACTIVE_PLAN.set((plan, on_seeded or (lambda _x: None)))
    try:
        yield plan
    finally:
        _hook.ACTIVE_PLAN.reset(token)


# ---------------------------------------------------------------------------
# Python entry point
# ---------------------------------------------------------------------------

def rerun(
    target: Any,
    source: Union[str, List[Any]],
    node_id: str,
    *,
    input: Any = None,
    run_id: Optional[str] = None,
    live: bool = False,
    meta: Optional[Dict[str, Any]] = None,
):
    """Re-run ``target`` (an AgentFlow or AgentTeam) from ``node_id`` of ``source``.

    Returns ``(recording, result)``; the new trace is at ``recording.path``.
    """
    from .recorder import record

    plan = plan_rerun(source, node_id)
    if _is_flow(target):
        if plan.kind != "flow":
            raise RerunError(f"{node_id!r} is a team task; pass the AgentTeam that recorded it.")
        seed_flow(target, plan)
    elif _is_team(target):
        if plan.kind != "team":
            raise RerunError(f"{node_id!r} is a flow step; pass the AgentFlow that recorded it.")
        seed_team(target, plan)
    else:
        raise RerunError(f"Cannot re-run a {type(target).__name__}; expected an AgentFlow or AgentTeam.")

    start_meta = dict(meta or {})
    with record(run_id, live=live, meta=start_meta, _forked_from=plan.forked_from) as rec:
        result = target.start(input) if input is not None else target.start()
    return rec, result
