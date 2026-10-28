"""Render a run's DEFINITION as graph data and as a mermaid diagram.

PraisonAI could already diagram a captured execution trace
(``telemetry/performance_utils.py``), but that only exists once a flow has run
-- so a flow could only be pictured after it had already cost money. This
renders the structure from the definition, before anything executes, which is
what CrewAI's ``flow.plot()`` gives its users.

One builder walks the definition and produces graph data
(``schema: "praisonai.graph/1"``) for an ``Agent``, an ``AgentTeam`` or an
``AgentFlow``. Node ids are derived from names and positions only (never a
uuid), so they are identical across processes and runs and the same ids appear
as ``node_id`` on replay trace events:

- ``agent:<name>``, ``task:<name or index>``, ``step:<name>``
  (duplicates become ``#2``, ``#3`` in definition order),
  ``tool:<agent>/<tool>``, ``human:you``, ``manager:Manager``
- ``start:begin`` ("Brief") and ``end:done`` ("Delivered")

Mermaid rather than graphviz on purpose: it needs no new dependency, and both
GitHub and the docs render it inline. Stdlib only; nothing here is imported
when ``praisonaiagents`` is.

    >>> print(flow.to_mermaid())
    graph TD
      start([start]) --> n0["research"]
      n0 --> n1{"score > 80"}
      ...
"""

from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "to_mermaid",
    "flow_to_mermaid",
    "to_graph",
    "graph_to_mermaid",
    "GRAPH_SCHEMA",
]

GRAPH_SCHEMA = "praisonai.graph/1"

START_ID = "start:begin"
END_ID = "end:done"
HUMAN_ID = "human:you"
MANAGER_ID = "manager:Manager"

_FLOW_CLASSES = {"AgentFlow"}
_TEAM_CLASSES = {"AgentTeam"}


def _label(step: Any) -> str:
    """A human name for a step, however it was declared."""
    for attr in ("name", "__name__"):
        value = getattr(step, attr, None)
        if isinstance(value, str) and value:
            return value
    agent = getattr(step, "agent", None)
    agent_name = getattr(agent, "name", None)
    if isinstance(agent_name, str) and agent_name:
        return agent_name
    if isinstance(step, str):
        return step
    return type(step).__name__


def _escape(text: str) -> str:
    """Mermaid labels are quoted, so a quote in a name would break the graph."""
    return str(text).replace('"', "'").replace("\n", " ")


def _class_names(obj: Any) -> set:
    return {klass.__name__ for klass in type(obj).__mro__}


def _tool_name(tool: Any) -> str:
    if isinstance(tool, str):
        return tool
    if isinstance(tool, dict):
        function = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        return str(function.get("name") or tool.get("name") or "tool")
    for attr in ("name", "__name__"):
        value = getattr(tool, attr, None)
        if isinstance(value, str) and value:
            return value
    return type(tool).__name__


def _is_agent(obj: Any) -> bool:
    # An unnamed Agent (``Agent(instructions=...)``) has ``name=None``; it is still an agent.
    return hasattr(obj, "chat") and hasattr(obj, "name")


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


class _Graph:
    """Accumulates nodes/edges, and the mermaid draw order for flows.

    ``ops`` records exactly the nodes and edges the legacy flow diagram drew,
    in the order it drew them, so ``flow_to_mermaid`` stays byte-identical
    while the graph data can carry more (agents, tools, pattern groups).
    """

    def __init__(self, kind: str, name: Optional[str], process: str) -> None:
        self.kind = kind
        self.name = name
        self.process = process
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: Dict[str, Dict[str, Any]] = {}
        self.ops: List[tuple] = []
        # id(definition object) -> node id, first occurrence wins. Used at run
        # time to stamp node_id on step events.
        self.ids: Dict[int, str] = {}
        # (parent node id, branch label, index, id(obj)) -> node id, so one
        # object used at two positions still resolves to each position's node.
        self.positions: Dict[tuple, str] = {}
        self._seen: Dict[str, int] = {}
        # edge id -> distinct route labels, joined only for display.
        self._labels: Dict[str, List[str]] = {}

    def unique(self, base: str) -> str:
        """``base`` the first time, then ``base#2``, ``base#3`` ..."""
        count = self._seen.get(base, 0) + 1
        self._seen[base] = count
        return base if count == 1 else f"{base}#{count}"

    def node(
        self,
        node_id: str,
        kind: str,
        label: str,
        parent: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
        shape: Optional[str] = None,
    ) -> str:
        if node_id not in self.nodes:
            self.nodes[node_id] = {
                "id": node_id,
                "kind": kind,
                "label": label,
                "parent": parent,
                "meta": dict(meta or {}),
            }
        if shape is not None:
            self.ops.append(("node", node_id, shape))
        return node_id

    def edge(
        self,
        source: str,
        target: str,
        kind: str,
        label: Optional[str] = None,
        draw: bool = False,
    ) -> None:
        edge_id = f"{source}->{target}:{kind}"
        if edge_id not in self.edges:
            self.edges[edge_id] = {
                "id": edge_id,
                "source": source,
                "target": target,
                "kind": kind,
                "label": label,
            }
            self._labels[edge_id] = [label] if label else []
        elif label:
            # Two conditions to the same target share one edge; keep both labels.
            labels = self._labels[edge_id]
            if label not in labels:
                labels.append(label)
                self.edges[edge_id]["label"] = " / ".join(labels)
        if draw:
            self.ops.append(("edge", source, target, label))

    def has_edge(self, source: str, target: str, kind: str) -> bool:
        return f"{source}->{target}:{kind}" in self.edges

    def register(self, obj: Any, node_id: str, parent: Optional[str] = None, slot: Optional[tuple] = None) -> None:
        self.ids.setdefault(id(obj), node_id)
        if slot is not None:
            self.positions.setdefault((parent, *slot, id(obj)), node_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": GRAPH_SCHEMA,
            "kind": self.kind,
            "name": self.name,
            "process": self.process,
            "nodes": list(self.nodes.values()),
            "edges": list(self.edges.values()),
        }

    def ops_to_mermaid(self) -> str:
        lines = ["graph TD"]
        short: Dict[str, str] = {}
        for op in self.ops:
            if op[0] == "node":
                ref = f"n{len(short)}"
                short[op[1]] = ref
                lines.append(f"  {ref}{op[2]}")
            else:
                _, source, target, label = op
                arrow = f' -->|"{_escape(label)}"| ' if label else " --> "
                lines.append(f"  {short[source]}{arrow}{short[target]}")
        return "\n".join(lines)


def _add_agent(g: _Graph, agent: Any, parent: Optional[str] = None, _seen: Optional[set] = None) -> str:
    """Add an agent node with its tools and hand-off targets; return its id."""
    from ..trace.context_events import _agent_key

    name = getattr(agent, "name", None) or type(agent).__name__  # label
    key = _agent_key(getattr(agent, "name", None))  # the id the trace uses
    agent_id = f"agent:{key}"
    seen = _seen if _seen is not None else set()
    if agent_id in seen:
        return agent_id
    seen.add(agent_id)
    g.node(agent_id, "agent", name, parent=parent, meta={"role": getattr(agent, "role", None)})
    targets = []
    handoff_tools = set()
    for handoff in list(getattr(agent, "handoffs", None) or []):
        target = handoff if _is_agent(handoff) else getattr(handoff, "agent", None)
        if target is None or not getattr(target, "name", None):
            continue
        targets.append(target)
        tool_name = getattr(handoff, "tool_name", None) if not _is_agent(handoff) else None
        if tool_name is None:
            from ..agent.handoff import Handoff
            tool_name = Handoff(agent=target).tool_name
        handoff_tools.add(tool_name)
    for tool in list(getattr(agent, "tools", None) or []):
        tool_name = _tool_name(tool)
        if tool_name in handoff_tools:
            continue  # drawn as the hand-off edge, not as a tool
        tool_id = f"tool:{key}/{tool_name}"
        g.node(tool_id, "tool", tool_name, parent=parent)
        g.edge(agent_id, tool_id, "uses")
    for target in targets:
        target_id = _add_agent(g, target, parent=parent, _seen=seen)
        g.edge(agent_id, target_id, "handoff")
    return agent_id


# ---------------------------------------------------------------------------
# AgentFlow
# ---------------------------------------------------------------------------


def _flow_branch(steps: Any, g: _Graph, parent: Optional[str], route: Optional[str] = None) -> Optional[Tuple[str, str]]:
    """Render a sub-sequence of steps in isolation.

    Returns the ``(entry, exit)`` pair for the whole sub-sequence, or ``None``
    when it is empty. Parents wire the labelled edge to ``entry`` -- never to a
    nested composite's exit -- so a nested ``If``/``Route``/``Parallel`` stays
    connected to its own decision/fork instead of being bypassed.
    """
    entry: Optional[str] = None
    tail: Optional[str] = None
    for index, inner in enumerate(steps or []):
        rendered = _flow_step(inner, g, tail, parent, (route, index))
        if rendered is None:
            continue
        inner_entry, inner_exit = rendered
        if entry is None:
            entry = inner_entry
        tail = inner_exit
    if entry is None or tail is None:
        return None
    return entry, tail


def _pattern_group(g: _Graph, step: Any, pattern: str, parent: Optional[str], label: str, meta: Dict[str, Any]) -> Tuple[str, str]:
    """The ``step:<name>`` node that groups a pattern's parts; returns (id, suffix)."""
    group = g.unique(f"step:{label}")
    g.node(group, "step", label, parent=parent, meta={"pattern": pattern, **meta})
    g.register(step, group)
    return group, group[len("step:"):]


def _flow_step(
    step: Any, g: _Graph, prev: Optional[str], parent: Optional[str], slot: Optional[tuple] = None,
) -> Optional[Tuple[str, str]]:
    """Render one step, returning its ``(entry, exit)`` nodes.

    ``entry`` is what an incoming edge should point at; ``exit`` is what the
    next step should follow. For a plain step the two are identical; for a
    composite they differ (e.g. an ``If`` enters at its decision and exits at
    its join). ``slot`` is the ``(branch label, index)`` the executor runs
    the step at inside ``parent``.
    """
    cls = type(step).__name__

    if cls == "If":
        condition = getattr(step, "condition", "") or "if"
        group, suffix = _pattern_group(g, step, "if", parent, "if", {"condition": str(condition)})
        decision = g.node(f"decision:{suffix}", "decision", str(condition), parent=group,
                          shape=f'{{"{_escape(condition)}"}}')
        if prev:
            g.edge(prev, decision, "next", draw=True)
        ends = []
        for branch, edge_label in (("then_steps", "true"), ("else_steps", "false")):
            rendered = _flow_branch(getattr(step, branch, None), g, group, edge_label)
            if rendered:
                branch_entry, branch_exit = rendered
                g.edge(decision, branch_entry, "routes", edge_label, draw=True)
                ends.append(branch_exit)
        join = g.node(f"join:{suffix}", "join", "join", parent=group, shape='(("join"))')
        for end in ends or [decision]:
            g.edge(end, join, "next", draw=True)
        return decision, join

    if cls == "Route":
        group, suffix = _pattern_group(g, step, "route", parent, "route", {})
        router = g.node(f"decision:{suffix}", "decision", "route", parent=group, shape='{"route"}')
        if prev:
            g.edge(prev, router, "next", draw=True)
        ends = []
        routes = getattr(step, "routes", None) or {}
        for key, steps in routes.items():
            rendered = _flow_branch(steps, g, group, key)
            if rendered:
                branch_entry, branch_exit = rendered
                g.edge(router, branch_entry, "routes", key, draw=True)
                ends.append(branch_exit)
        # ``Route.__init__`` mirrors ``routes["default"]`` into ``.default``;
        # only render ``.default`` when it was not already drawn as a key above.
        if "default" not in routes:
            rendered = _flow_branch(getattr(step, "default", None), g, group, "default")
            if rendered:
                branch_entry, branch_exit = rendered
                g.edge(router, branch_entry, "routes", "default", draw=True)
                ends.append(branch_exit)
        join = g.node(f"join:{suffix}", "join", "join", parent=group, shape='(("join"))')
        for end in ends or [router]:
            g.edge(end, join, "next", draw=True)
        return router, join

    if cls == "Parallel":
        group, suffix = _pattern_group(g, step, "parallel", parent, "parallel", {})
        fork = g.node(f"fork:{suffix}", "fork", "fork", parent=group, shape='(("fork"))')
        if prev:
            g.edge(prev, fork, "next", draw=True)
        ends = []
        for index, inner in enumerate(getattr(step, "steps", None) or []):
            rendered = _flow_step(inner, g, None, group, (None, index))
            if rendered:
                branch_entry, branch_exit = rendered
                g.edge(fork, branch_entry, "parallel", draw=True)
                ends.append(branch_exit)
        join = g.node(f"join:{suffix}", "join", "join", parent=group, shape='(("join"))')
        for end in ends or [fork]:
            g.edge(end, join, "next", draw=True)
        return fork, join

    if cls in ("Loop", "Repeat"):
        pattern = cls.lower()
        inner = getattr(step, "step", None)
        # ``Repeat(step=[a, b])`` runs each member, as ``_execute_repeat`` does.
        inner_steps = getattr(step, "steps", None) or (
            list(inner) if isinstance(inner, (list, tuple))
            else [inner] if inner is not None else []
        )
        over = getattr(step, "over", None)
        iterations = getattr(step, "max_iterations", None)
        meta = {}
        if over:
            meta["over"] = str(over)
        if iterations:
            meta["max_iterations"] = iterations
        group, _ = _pattern_group(g, step, pattern, parent, pattern, meta)
        tail = prev
        first = None
        for index, inner in enumerate(inner_steps):
            # ``_execute_repeat`` passes the iteration, not the position, so
            # Repeat members keep the by-object lookup.
            slot = (None, index) if pattern == "loop" else None
            rendered = _flow_step(inner, g, tail, group, slot)
            if rendered:
                inner_entry, inner_exit = rendered
                first = first or inner_entry
                tail = inner_exit
        if first and tail:
            back = f"over {over}" if over else (f"up to {iterations}x" if iterations else "repeat")
            g.edge(tail, first, "loop", back, draw=True)
        if first is None or tail is None:
            return None
        return first, tail

    if cls == "Include":
        # An included workflow's steps are known at definition time, so render
        # them inline rather than as an opaque node. A recipe include (by name)
        # is only resolvable at runtime, so it stays a single node.
        workflow = getattr(step, "workflow", None)
        recipe = getattr(step, "recipe", None)
        meta = {"recipe": recipe} if recipe else {}
        if workflow is not None and getattr(workflow, "name", None):
            meta["workflow"] = workflow.name
        group, _ = _pattern_group(g, step, "include", parent, "include", meta)
        if workflow is not None:
            rendered = _flow_branch(getattr(workflow, "steps", None), g, group)
            if rendered:
                branch_entry, branch_exit = rendered
                if prev:
                    g.edge(prev, branch_entry, "next", draw=True)
                return branch_entry, branch_exit
        # Unexpanded: the group node itself is the drawn step.
        g.ops.append(("node", group, f'["{_escape(_label(step))}"]'))
        if prev:
            g.edge(prev, group, "next", draw=True)
        return group, group

    label = _label(step)
    node_id = g.unique(f"step:{label}")
    meta: Dict[str, Any] = {}
    if cls == "Discussion":
        meta["pattern"] = "discussion"
    g.node(node_id, "step", label, parent=parent, meta=meta, shape=f'["{_escape(label)}"]')
    g.register(step, node_id, parent, slot)
    if prev:
        g.edge(prev, node_id, "next", draw=True)

    # Graph-only detail: who does the step, and with which tools.
    if cls == "Discussion":
        for speaker in getattr(step, "agents", None) or []:
            if _is_agent(speaker):
                g.edge(node_id, _add_agent(g, speaker), "assigned")
                g.register(speaker, node_id)
    elif _is_agent(step):
        g.edge(node_id, _add_agent(g, step), "assigned")
    elif _is_agent(getattr(step, "agent", None)):
        g.edge(node_id, _add_agent(g, step.agent), "assigned")
    return node_id, node_id


def _build_flow(steps: Any, name: Optional[str], kind: str = "flow", process: str = "flow") -> _Graph:
    g = _Graph(kind, name, process)
    start = g.node(START_ID, "start", "Brief",
                   shape='([" start "])' if not name else f'(["{_escape(name)}"])')
    prev: Optional[str] = start
    for index, step in enumerate(steps or []):
        rendered = _flow_step(step, g, prev, None, (None, index))
        if rendered:
            prev = rendered[1]
    end = g.node(END_ID, "end", "Delivered", shape='([" end "])')
    if prev:
        g.edge(prev, end, "next", draw=True)
    return g


def _flow_process(flow: Any) -> str:
    return "hierarchical" if getattr(flow, "process", None) == "hierarchical" else "flow"


def _flow_graph(flow: Any) -> _Graph:
    return _build_flow(getattr(flow, "steps", None), getattr(flow, "name", None),
                       process=_flow_process(flow))


# ---------------------------------------------------------------------------
# AgentTeam
# ---------------------------------------------------------------------------


def _is_synthetic_manager(task: Any) -> bool:
    """The hierarchical process injects a ``manager_task`` run by "Manager"."""
    agent = getattr(task, "agent", None)
    return getattr(task, "name", None) == "manager_task" and getattr(agent, "name", None) == "Manager"


def _team_tasks(team: Any) -> List[Any]:
    tasks = getattr(team, "tasks", None) or []
    if isinstance(tasks, dict):
        return list(tasks.values())
    return list(tasks)


def task_node_ids(tasks: List[Any]) -> List[str]:
    """Stable node ids for a team's tasks, aligned with ``tasks``.

    ``task:<name>`` (or ``task:<index>`` for an unnamed task), duplicates
    suffixed ``#2``... The hierarchical synthetic manager task maps to
    ``manager:Manager``.
    """
    seen: Dict[str, int] = {}
    ids = []
    for index, task in enumerate(tasks):
        if _is_synthetic_manager(task):
            ids.append(MANAGER_ID)
            continue
        name = getattr(task, "name", None)
        base = f"task:{name}" if name else f"task:{index}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        ids.append(base if count == 1 else f"{base}#{count}")
    return ids


def task_node_id(tasks: Any, task: Any) -> Optional[str]:
    """Node id of ``task`` within a team's ``tasks`` (dict or list)."""
    if isinstance(tasks, dict):
        tasks = list(tasks.values())
    tasks = list(tasks or [])
    for task_obj, node_id in zip(tasks, task_node_ids(tasks)):
        if task_obj is task:
            return node_id
    name = getattr(task, "name", None)
    return f"task:{name}" if name else None


def _team_graph(team: Any) -> _Graph:
    process = getattr(team, "process", None) or "sequential"
    hierarchical = process == "hierarchical"
    g = _Graph("team", getattr(team, "name", None), process)
    all_tasks = _team_tasks(team)
    ids = task_node_ids(all_tasks)
    pairs = [(t, i) for t, i in zip(all_tasks, ids) if not _is_synthetic_manager(t)]
    by_name = {}
    for task, node_id in pairs:
        if getattr(task, "name", None):
            by_name.setdefault(task.name, node_id)

    g.node(START_ID, "start", "Brief")
    if hierarchical:
        g.node(MANAGER_ID, "manager", "Manager")
    for agent in getattr(team, "agents", None) or []:
        if getattr(agent, "name", None):
            _add_agent(g, agent)
    if any(getattr(t, "human_input", False) for t, _ in pairs):
        g.node(HUMAN_ID, "human", "You")

    for index, (task, node_id) in enumerate(pairs):
        label = getattr(task, "name", None) or (
            (getattr(task, "description", None) or "")[:60] or f"Task {index + 1}"
        )
        agent = getattr(task, "agent", None)
        meta: Dict[str, Any] = {}
        if getattr(task, "task_type", None) not in (None, "task"):
            meta["task_type"] = task.task_type
        if getattr(task, "human_input", False):
            meta["human_input"] = True
        g.node(node_id, "task", str(label), meta=meta)
        g.register(task, node_id)
        if agent is not None and getattr(agent, "name", None):
            g.edge(node_id, _add_agent(g, agent), "assigned")
        if getattr(task, "human_input", False):
            g.edge(HUMAN_ID, node_id, "reviews")

    if hierarchical:
        g.edge(START_ID, MANAGER_ID, "next")
        for agent in getattr(team, "agents", None) or []:
            if getattr(agent, "name", None):
                g.edge(MANAGER_ID, f"agent:{agent.name}", "delegates")
        g.edge(MANAGER_ID, END_ID, "next")
    elif process == "workflow" and pairs:
        starts = [n for t, n in pairs if getattr(t, "is_start", False)] or [pairs[0][1]]
        for node_id in starts:
            g.edge(START_ID, node_id, "next")
        for task, node_id in pairs:
            condition = getattr(task, "condition", None) or {}
            followers = [x for x in (getattr(task, "next_tasks", None) or []) if x in by_name]
            routed = False
            # Unified when/then_task/else_task routing, which execution
            # checks before condition/next_tasks.
            for attr, branch in (("then_task", str(getattr(task, "when", None) or "then")),
                                 ("else_task", "else")):
                target = getattr(task, attr, None)
                if isinstance(target, str) and target in by_name:
                    g.edge(node_id, by_name[target], "routes", branch)
                    routed = True
            if isinstance(condition, dict):
                for key, targets in condition.items():
                    for target in (targets if isinstance(targets, (list, tuple)) else [targets]):
                        if target in by_name:
                            g.edge(node_id, by_name[target], "routes", str(key))
                            routed = True
                        elif target in ("exit", "end", "done"):
                            g.edge(node_id, END_ID, "routes", str(key))
                            routed = True
            for target in followers:
                g.edge(node_id, by_name[target], "next")
            if not followers and not routed:
                g.edge(node_id, END_ID, "next")
    else:
        prev = START_ID
        for _, node_id in pairs:
            g.edge(prev, node_id, "next")
            prev = node_id
        g.edge(prev, END_ID, "next")

    # Explicit data dependencies (context=/depends_on=), unless the same pair
    # is already joined by a control edge (sequential teams add both).
    task_ids = {id(t): n for t, n in pairs}
    for task, node_id in pairs:
        for dep in getattr(task, "context", None) or []:
            dep_id = task_ids.get(id(dep))
            if dep_id and dep_id != node_id and not g.has_edge(dep_id, node_id, "next"):
                g.edge(dep_id, node_id, "depends_on")

    g.node(END_ID, "end", "Delivered")
    return g


def _agent_graph(agent: Any) -> _Graph:
    g = _Graph("agent", getattr(agent, "name", None), "sequential")
    g.node(START_ID, "start", "Brief")
    agent_id = _add_agent(g, agent)
    g.register(agent, agent_id)
    g.edge(START_ID, agent_id, "next")
    g.node(END_ID, "end", "Delivered")
    g.edge(agent_id, END_ID, "next")
    return g


def _graph_for(obj: Any) -> _Graph:
    names = _class_names(obj)
    if names & _FLOW_CLASSES:
        return _flow_graph(obj)
    if names & _TEAM_CLASSES:
        return _team_graph(obj)
    if isinstance(obj, (list, tuple)):
        return _build_flow(obj, None)
    if _is_agent(obj):
        return _agent_graph(obj)
    if hasattr(obj, "steps"):
        return _flow_graph(obj)
    if hasattr(obj, "tasks") and hasattr(obj, "agents"):
        return _team_graph(obj)
    raise TypeError(f"to_graph() expects an Agent, AgentTeam or AgentFlow, got {type(obj).__name__}")


def to_graph(obj: Any) -> Dict[str, Any]:
    """Graph data (``praisonai.graph/1``) for an Agent, AgentTeam or AgentFlow."""
    return _graph_for(obj).to_dict()


# ---------------------------------------------------------------------------
# Mermaid
# ---------------------------------------------------------------------------

_SHAPES = {
    "start": '(["{}"])',
    "end": '(["{}"])',
    "decision": '{{"{}"}}',
    "fork": '(("{}"))',
    "join": '(("{}"))',
    "manager": '{{{{"{}"}}}}',
    "human": '>"{}"]',
    "tool": '[["{}"]]',
}


def graph_to_mermaid(graph: Dict[str, Any]) -> str:
    """Render ``praisonai.graph/1`` data as a mermaid ``graph TD``.

    Group nodes (a node other nodes name as ``parent``) are containers, not
    boxes, so they and their edges are left out of the picture.
    """
    nodes = list(graph.get("nodes") or [])
    parents = {n.get("parent") for n in nodes if n.get("parent")}
    short: Dict[str, str] = {}
    lines = ["graph TD"]
    for node in nodes:
        if node["id"] in parents:
            continue
        ref = f"n{len(short)}"
        short[node["id"]] = ref
        shape = _SHAPES.get(node.get("kind"), '["{}"]')
        lines.append(f"  {ref}{shape.format(_escape(node.get('label') or node['id']))}")
    for edge in graph.get("edges") or []:
        source, target = short.get(edge["source"]), short.get(edge["target"])
        if source is None or target is None:
            continue
        kind = edge.get("kind")
        label = edge.get("label")
        if kind in ("next", "parallel"):
            arrow = f' -->|"{_escape(label)}"| ' if label else " --> "
        elif kind in ("routes", "loop", "handoff", "delegates"):
            arrow = f' -->|"{_escape(label or kind)}"| '
        else:
            arrow = f' -.->|"{_escape(label or kind)}"| '
        lines.append(f"  {source}{arrow}{target}")
    return "\n".join(lines)


def to_mermaid(steps: Any, name: Optional[str] = None) -> str:
    """Render a list of workflow steps as a mermaid ``graph TD``."""
    return _build_flow(steps, name).ops_to_mermaid()


def flow_to_mermaid(flow: Any) -> str:
    """Render an ``AgentFlow`` / ``Workflow`` definition."""
    return to_mermaid(getattr(flow, "steps", None), getattr(flow, "name", None))
