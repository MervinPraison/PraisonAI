"""Render a workflow's DEFINITION as a mermaid diagram.

PraisonAI could already diagram a captured execution trace
(``telemetry/performance_utils.py``), but that only exists once a flow has run
-- so a flow could only be pictured after it had already cost money. This
renders the structure from the step list, before anything executes, which is
what CrewAI's ``flow.plot()`` gives its users.

Mermaid rather than graphviz on purpose: it needs no new dependency, and both
GitHub and the docs render it inline.

    >>> print(flow.to_mermaid())
    graph TD
      start([start]) --> n0["research"]
      n0 --> n1{"score > 80"}
      ...
"""

from typing import Any, List, Optional, Tuple

__all__ = ["to_mermaid", "flow_to_mermaid"]


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


class _Builder:
    def __init__(self) -> None:
        self.lines: List[str] = ["graph TD"]
        self._n = 0

    def node(self, shape: str) -> str:
        node_id = f"n{self._n}"
        self._n += 1
        self.lines.append(f"  {node_id}{shape}")
        return node_id

    def edge(self, src: str, dst: str, label: Optional[str] = None) -> None:
        arrow = f' -->|"{_escape(label)}"| ' if label else " --> "
        self.lines.append(f"  {src}{arrow}{dst}")


def _branch(steps: Any, b: "_Builder") -> Optional[Tuple[str, str]]:
    """Render a sub-sequence of steps in isolation.

    Returns the ``(entry, exit)`` pair for the whole sub-sequence, or ``None``
    when it is empty. Parents wire the labelled edge to ``entry`` -- never to a
    nested composite's exit -- so a nested ``If``/``Route``/``Parallel`` stays
    connected to its own decision/fork instead of being bypassed.
    """
    entry: Optional[str] = None
    tail: Optional[str] = None
    for inner in steps or []:
        rendered = _render(inner, b, tail)
        if rendered is None:
            continue
        inner_entry, inner_exit = rendered
        if entry is None:
            entry = inner_entry
        tail = inner_exit
    if entry is None or tail is None:
        return None
    return entry, tail


def _render(step: Any, b: _Builder, prev: Optional[str]) -> Optional[Tuple[str, str]]:
    """Render one step, returning its ``(entry, exit)`` nodes.

    ``entry`` is what an incoming edge should point at; ``exit`` is what the
    next step should follow. For a plain step the two are identical; for a
    composite they differ (e.g. an ``If`` enters at its decision and exits at
    its join).
    """
    cls = type(step).__name__
    name = _escape(_label(step))

    if cls == "If":
        decision = b.node(f'{{"{_escape(getattr(step, "condition", "") or "if")}"}}')
        if prev:
            b.edge(prev, decision)
        ends = []
        for branch, edge_label in (("then_steps", "true"), ("else_steps", "false")):
            rendered = _branch(getattr(step, branch, None), b)
            if rendered:
                branch_entry, branch_exit = rendered
                b.edge(decision, branch_entry, edge_label)
                ends.append(branch_exit)
        join = b.node('(("join"))')
        for end in ends or [decision]:
            b.edge(end, join)
        return decision, join

    if cls == "Route":
        router = b.node(f'{{"route"}}')
        if prev:
            b.edge(prev, router)
        ends = []
        routes = getattr(step, "routes", None) or {}
        for key, steps in routes.items():
            rendered = _branch(steps, b)
            if rendered:
                branch_entry, branch_exit = rendered
                b.edge(router, branch_entry, key)
                ends.append(branch_exit)
        # ``Route.__init__`` mirrors ``routes["default"]`` into ``.default``;
        # only render ``.default`` when it was not already drawn as a key above.
        if "default" not in routes:
            rendered = _branch(getattr(step, "default", None), b)
            if rendered:
                branch_entry, branch_exit = rendered
                b.edge(router, branch_entry, "default")
                ends.append(branch_exit)
        join = b.node('(("join"))')
        for end in ends or [router]:
            b.edge(end, join)
        return router, join

    if cls == "Parallel":
        fork = b.node('(("fork"))')
        if prev:
            b.edge(prev, fork)
        ends = []
        for inner in getattr(step, "steps", None) or []:
            rendered = _render(inner, b, None)
            if rendered:
                branch_entry, branch_exit = rendered
                b.edge(fork, branch_entry)
                ends.append(branch_exit)
        join = b.node('(("join"))')
        for end in ends or [fork]:
            b.edge(end, join)
        return fork, join

    if cls in ("Loop", "Repeat"):
        inner_steps = getattr(step, "steps", None) or (
            [getattr(step, "step")] if getattr(step, "step", None) is not None else []
        )
        tail = prev
        first = None
        for inner in inner_steps:
            rendered = _render(inner, b, tail)
            if rendered:
                inner_entry, inner_exit = rendered
                first = first or inner_entry
                tail = inner_exit
        if first and tail:
            over = getattr(step, "over", None)
            iterations = getattr(step, "max_iterations", None)
            back = f"over {over}" if over else (f"up to {iterations}x" if iterations else "repeat")
            b.edge(tail, first, back)
        if first is None or tail is None:
            return None
        return first, tail

    if cls == "Include":
        # An included workflow's steps are known at definition time, so render
        # them inline rather than as an opaque node. A recipe include (by name)
        # is only resolvable at runtime, so it stays a single node.
        workflow = getattr(step, "workflow", None)
        if workflow is not None:
            rendered = _branch(getattr(workflow, "steps", None), b)
            if rendered:
                branch_entry, branch_exit = rendered
                if prev:
                    b.edge(prev, branch_entry)
                return branch_entry, branch_exit

    node = b.node(f'["{name}"]')
    if prev:
        b.edge(prev, node)
    return node, node


def to_mermaid(steps: Any, name: Optional[str] = None) -> str:
    """Render a list of workflow steps as a mermaid ``graph TD``."""
    b = _Builder()
    start = b.node('([" start "])' if not name else f'(["{_escape(name)}"])')
    prev: Optional[str] = start
    for step in (steps or []):
        rendered = _render(step, b, prev)
        if rendered:
            prev = rendered[1]
    end = b.node('([" end "])')
    if prev:
        b.edge(prev, end)
    return "\n".join(b.lines)


def flow_to_mermaid(flow: Any) -> str:
    """Render an ``AgentFlow`` / ``Workflow`` definition."""
    return to_mermaid(getattr(flow, "steps", None), getattr(flow, "name", None))
