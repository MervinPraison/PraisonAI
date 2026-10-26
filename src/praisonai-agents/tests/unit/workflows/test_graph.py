"""Graph data (``praisonai.graph/1``) for teams, flows and agents.

The replay UI draws the Map from this graph and joins it to trace events by
``node_id``, so the ids must be derived from the definition alone: identical
in every process and on every run. The goldens pin the full shape; regenerate
them deliberately with ``PRAISONAI_UPDATE_GOLDEN=1``.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
GOLDEN = HERE / "golden"
sys.path.insert(0, str(HERE))
import _graph_fixtures as fixtures  # noqa: E402

from praisonaiagents.workflows.diagram import graph_to_mermaid, to_graph  # noqa: E402


@pytest.mark.parametrize("name", ["team", "sequential_team", "hierarchical_team", "flow"])
def test_graph_matches_golden(name):
    graph = to_graph(fixtures.BUILDERS[name]())
    path = GOLDEN / f"graph_{name}.json"
    if os.environ.get("PRAISONAI_UPDATE_GOLDEN") == "1":
        path.write_text(json.dumps(graph, indent=2, sort_keys=True) + "\n")
    assert graph == json.loads(path.read_text())


def test_ids_are_stable_across_processes():
    """Two fresh interpreters with different hash seeds produce the same graphs."""
    code = (
        "import json, sys; sys.path.insert(0, sys.argv[1]);"
        "import _graph_fixtures as f;"
        "from praisonaiagents.workflows.diagram import to_graph;"
        "print(json.dumps({k: to_graph(b()) for k, b in sorted(f.BUILDERS.items())}, sort_keys=True))"
    )
    root = str(Path(__import__("praisonaiagents").__file__).parent.parent)
    outputs = []
    for seed in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=root, PYTHONDONTWRITEBYTECODE="1")
        out = subprocess.run([sys.executable, "-c", code, str(HERE)], env=env,
                             capture_output=True, text=True, timeout=120, check=True)
        outputs.append(json.loads(out.stdout.strip().splitlines()[-1]))
    assert outputs[0] == outputs[1]
    assert outputs[0]["flow"] == to_graph(fixtures.flow())


def test_every_edge_joins_known_nodes_and_ids_are_unique():
    for build in fixtures.BUILDERS.values():
        graph = to_graph(build())
        ids = [n["id"] for n in graph["nodes"]]
        assert len(ids) == len(set(ids))
        for edge in graph["edges"]:
            assert edge["source"] in ids and edge["target"] in ids, edge
            assert edge["id"] == f'{edge["source"]}->{edge["target"]}:{edge["kind"]}'
        for node in graph["nodes"]:
            assert node["parent"] is None or node["parent"] in ids


def test_no_uuid_reaches_the_graph():
    import re

    uuid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    for build in fixtures.BUILDERS.values():
        assert not uuid.search(json.dumps(to_graph(build())))


def test_team_and_flow_methods():
    team = fixtures.hierarchical_team()
    assert team.to_graph() == to_graph(team)
    diagram = team.to_mermaid()
    assert diagram.startswith("graph TD")
    assert '{{"Manager"}}' in diagram and '-->|"delegates"|' in diagram
    flow = fixtures.flow()
    assert flow.to_graph() == to_graph(flow)


def test_agent_graph_has_tools_and_handoffs():
    from praisonaiagents import Agent

    billing = Agent(name="Billing", instructions="b")
    triage = Agent(name="Triage", instructions="t", tools=[fixtures.search_web], handoffs=[billing])
    graph = to_graph(triage)
    assert graph["kind"] == "agent"
    edges = {e["id"] for e in graph["edges"]}
    assert {
        "start:begin->agent:Triage:next",
        "agent:Triage->tool:Triage/search_web:uses",
        "agent:Triage->agent:Billing:handoff",
        "agent:Triage->end:done:next",
    } <= edges
    # The hand-off's generated transfer tool is the hand-off edge, not a tool node.
    assert not any(n["id"].startswith("tool:Triage/transfer_to") for n in graph["nodes"])


def test_graph_to_mermaid_draws_leaf_nodes_not_groups():
    graph = to_graph(fixtures.flow())
    diagram = graph_to_mermaid(graph)
    assert diagram.startswith("graph TD")
    assert '(("fork"))' in diagram and '{"route"}' in diagram
    assert '["parallel"]' not in diagram  # a pattern group is a container


def test_team_graph_keeps_when_routes_and_shared_target_labels():
    from praisonaiagents import Agent, Task
    from praisonaiagents.agents.agents import AgentTeam

    a = Agent(name="A", instructions="a")
    tasks = [
        Task(name="check", description="c", agent=a, is_start=True,
             when="score > 80", then_task="publish", else_task="revise"),
        Task(name="revise", description="r", agent=a,
             condition={"approved": ["publish"], "forced": ["publish"]}),
        Task(name="publish", description="p", agent=a),
    ]
    graph = to_graph(AgentTeam(agents=[a], tasks=tasks, process="workflow"))
    edges = {e["id"]: e for e in graph["edges"]}
    assert edges["task:check->task:publish:routes"]["label"] == "score > 80"
    assert edges["task:check->task:revise:routes"]["label"] == "else"
    assert "task:check->end:done:next" not in edges
    assert edges["task:revise->task:publish:routes"]["label"] == "approved / forced"


def test_repeat_with_a_step_list_draws_each_member():
    from praisonaiagents.workflows.workflows import AgentFlow, Repeat

    def draft(ctx):
        return "d"

    def polish(ctx):
        return "p"

    graph = to_graph(AgentFlow(steps=[Repeat(step=[draft, polish], until=lambda ctx: True)]))
    ids = {n["id"] for n in graph["nodes"]}
    assert {"step:draft", "step:polish"} <= ids
    assert "step:list" not in ids


def test_unsupported_object_is_rejected():
    with pytest.raises(TypeError):
        to_graph(42)
