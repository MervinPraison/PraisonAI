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

from typing import Any, List, Optional

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


def _render(step: Any, b: _Builder, prev: Optional[str]) -> Optional[str]:
    """Render one step, returning the node the next step should follow."""
    cls = type(step).__name__
    name = _escape(_label(step))

    if cls == "If":
        decision = b.node(f'{{"{_escape(getattr(step, "condition", "") or "if")}"}}')
        if prev:
            b.edge(prev, decision)
        ends = []
        for branch, edge_label in (("then_steps", "true"), ("else_steps", "false")):
            steps = getattr(step, branch, None) or []
            tail = decision
            for i, inner in enumerate(steps):
                nxt = _render(inner, b, None)
                if nxt:
                    b.edge(tail, nxt, edge_label if i == 0 else None)
                    tail = nxt
            if tail is not decision:
                ends.append(tail)
        join = b.node('(("join"))')
        for end in ends or [decision]:
            b.edge(end, join)
        return join

    if cls == "Route":
        router = b.node(f'{{"route"}}')
        if prev:
            b.edge(prev, router)
        ends = []
        routes = getattr(step, "routes", None) or {}
        for key, steps in routes.items():
            tail = router
            for i, inner in enumerate(steps or []):
                nxt = _render(inner, b, None)
                if nxt:
                    b.edge(tail, nxt, key if i == 0 else None)
                    tail = nxt
            if tail is not router:
                ends.append(tail)
        for inner in getattr(step, "default", None) or []:
            nxt = _render(inner, b, None)
            if nxt:
                b.edge(router, nxt, "default")
                ends.append(nxt)
        join = b.node('(("join"))')
        for end in ends or [router]:
            b.edge(end, join)
        return join

    if cls == "Parallel":
        fork = b.node('(("fork"))')
        if prev:
            b.edge(prev, fork)
        ends = []
        for inner in getattr(step, "steps", None) or []:
            nxt = _render(inner, b, None)
            if nxt:
                b.edge(fork, nxt)
                ends.append(nxt)
        join = b.node('(("join"))')
        for end in ends or [fork]:
            b.edge(end, join)
        return join

    if cls in ("Loop", "Repeat"):
        inner_steps = getattr(step, "steps", None) or (
            [getattr(step, "step")] if getattr(step, "step", None) is not None else []
        )
        tail = prev
        first = None
        for inner in inner_steps:
            nxt = _render(inner, b, tail)
            if nxt:
                first = first or nxt
                tail = nxt
        if first and tail:
            over = getattr(step, "over", None)
            iterations = getattr(step, "max_iterations", None)
            back = f"over {over}" if over else (f"up to {iterations}x" if iterations else "repeat")
            b.edge(tail, first, back)
        return tail

    node = b.node(f'["{name}"]')
    if prev:
        b.edge(prev, node)
    return node


def to_mermaid(steps: Any, name: Optional[str] = None) -> str:
    """Render a list of workflow steps as a mermaid ``graph TD``."""
    b = _Builder()
    start = b.node('([" start "])' if not name else f'(["{_escape(name)}"])')
    prev: Optional[str] = start
    for step in (steps or []):
        prev = _render(step, b, prev) or prev
    end = b.node('([" end "])')
    if prev:
        b.edge(prev, end)
    return "\n".join(b.lines)


def flow_to_mermaid(flow: Any) -> str:
    """Render an ``AgentFlow`` / ``Workflow`` definition."""
    return to_mermaid(getattr(flow, "steps", None), getattr(flow, "name", None))
