"""A workflow can be pictured before it runs.

PraisonAI could already diagram a captured execution trace, but only after a
flow had run -- so a flow could only be checked once it had already cost money.
These cover the definition-time renderer.
"""
import re

import pytest

from praisonaiagents.workflows.workflows import (
    AgentFlow,
    Include,
    Parallel,
    If,
    Repeat,
    Route,
    Workflow,
)
from praisonaiagents.workflows.diagram import to_mermaid


class Step:
    def __init__(self, name):
        self.name = name


def _edges(diagram):
    """Return the (src, dst) node id pairs the diagram actually draws."""
    edges = []
    for line in diagram.splitlines():
        match = re.match(r"\s*(n\d+)\s*-->(?:\|[^|]*\|)?\s*(n\d+)\s*$", line)
        if match:
            edges.append((match.group(1), match.group(2)))
    return edges


def _node_id(diagram, label):
    """The node id declared with the given label fragment."""
    match = re.search(r"(n\d+)\S*" + re.escape(label), diagram)
    assert match, f"no node with label {label!r} in:\n{diagram}"
    return match.group(1)


def _reaches(diagram, src, dst):
    """True if dst is reachable from src by following drawn edges."""
    edges = _edges(diagram)
    seen, stack = set(), [src]
    while stack:
        node = stack.pop()
        if node == dst:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(d for s, d in edges if s == node)
    return False


def test_a_linear_flow_renders_in_order():
    diagram = to_mermaid([Step("research"), Step("write")])
    assert diagram.startswith("graph TD")
    assert '["research"]' in diagram
    assert '["write"]' in diagram
    # write follows research
    assert diagram.index('["research"]') < diagram.index('["write"]')


def test_a_linear_flow_actually_connects_the_steps():
    """Declaration order is not enough -- there must be a real edge."""
    diagram = to_mermaid([Step("research"), Step("write")])
    research = _node_id(diagram, '["research"]')
    write = _node_id(diagram, '["write"]')
    assert (research, write) in _edges(diagram)


def test_a_nested_if_stays_connected_through_its_decision():
    """A control nested in a branch must not be bypassed via its exit."""
    inner = If(condition="inner?", then_steps=[Step("approve")])
    diagram = to_mermaid([If(condition="outer?", then_steps=[inner])])
    approve = _node_id(diagram, '["approve"]')
    outer = _node_id(diagram, "outer?")
    # the nested branch is reachable, i.e. the outer If did not skip past it
    assert _reaches(diagram, outer, approve)


def test_a_route_default_supplied_as_a_key_is_not_duplicated():
    diagram = to_mermaid([Route(routes={"a": [Step("x")], "default": [Step("fallback")]})])
    assert diagram.count('["fallback"]') == 1


def test_parallel_renders_a_fork_and_a_join():
    diagram = to_mermaid([Parallel(steps=[Step("a"), Step("b")])])
    assert '(("fork"))' in diagram
    assert '(("join"))' in diagram
    assert '["a"]' in diagram and '["b"]' in diagram


def test_control_a_linear_flow_has_no_fork():
    """Control: the fork is a property of Parallel, not of every diagram."""
    assert '(("fork"))' not in to_mermaid([Step("a"), Step("b")])


def test_if_renders_a_decision_with_labelled_branches():
    diagram = to_mermaid([
        If(condition="{{score}} > 80", then_steps=[Step("approve")], else_steps=[Step("revise")])
    ])
    assert '{{score}} > 80' in diagram
    assert '|"true"|' in diagram
    assert '|"false"|' in diagram


def test_control_an_if_without_an_else_has_no_false_branch():
    diagram = to_mermaid([If(condition="c", then_steps=[Step("approve")])])
    assert '|"true"|' in diagram
    assert '|"false"|' not in diagram


def test_repeat_renders_a_labelled_loop_back():
    diagram = to_mermaid([Repeat(Step("polish"), max_iterations=3)])
    assert '["polish"]' in diagram
    assert 'up to 3x' in diagram


def test_route_labels_each_branch_with_its_key():
    diagram = to_mermaid([Route(routes={"cheap": [Step("fast")], "costly": [Step("slow")]})])
    assert '|"cheap"|' in diagram
    assert '|"costly"|' in diagram


def test_a_quote_in_a_step_name_cannot_break_the_graph():
    diagram = to_mermaid([Step('say "hello"')])
    assert '"say' in diagram
    # the label is quoted, so an inner double quote would terminate it early
    assert 'say "hello"' not in diagram


def test_flow_to_mermaid_is_reachable_from_the_flow_object():
    flow = AgentFlow(steps=[Step("research")], name="demo")
    diagram = flow.to_mermaid()
    assert diagram.startswith("graph TD")
    assert '["research"]' in diagram
    assert 'demo' in diagram


def test_control_an_empty_flow_still_renders_a_valid_graph():
    diagram = to_mermaid([])
    assert diagram.startswith("graph TD")
    assert "-->" in diagram


def test_an_included_workflow_renders_its_own_steps():
    inner = Workflow(name="sub", steps=[Step("fetch"), Step("clean")])
    diagram = to_mermaid([Step("start"), Include(workflow=inner)])
    assert '["fetch"]' in diagram
    assert '["clean"]' in diagram
    assert _reaches(diagram, _node_id(diagram, '["fetch"]'), _node_id(diagram, '["clean"]'))


def test_control_an_included_recipe_stays_a_single_node():
    """A recipe include resolves only at runtime, so it cannot be expanded."""
    diagram = to_mermaid([Include(recipe="wordpress-publisher")])
    assert '["fetch"]' not in diagram
    assert "Include" in diagram or "wordpress-publisher" in diagram
