"""A workflow can be pictured before it runs.

PraisonAI could already diagram a captured execution trace, but only after a
flow had run -- so a flow could only be checked once it had already cost money.
These cover the definition-time renderer.
"""
import pytest

from praisonaiagents.workflows.workflows import AgentFlow, Parallel, If, Repeat, Route
from praisonaiagents.workflows.diagram import to_mermaid


class Step:
    def __init__(self, name):
        self.name = name


def test_a_linear_flow_renders_in_order():
    diagram = to_mermaid([Step("research"), Step("write")])
    assert diagram.startswith("graph TD")
    assert '["research"]' in diagram
    assert '["write"]' in diagram
    # write follows research
    assert diagram.index('["research"]') < diagram.index('["write"]')


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
