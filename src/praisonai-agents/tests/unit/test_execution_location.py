"""The object must say where it runs.

Acceptance criterion: a user can answer "what runs where?" from the REPL alone,
without reading docs. Before this, `repr(agent)` was `<...Agent object at 0x...>`.
"""

import inspect

import pytest

from praisonaiagents import Agent, AgentFlow, AgentTeam, Task
from praisonaiagents.agent.execution_location import describe, explain, say_place


def _agent(name="A"):
    return Agent(name=name, instructions="x")


# ── repr states the location ─────────────────────────────────────────────────
def test_agent_repr_states_where_it_runs():
    text = repr(_agent("builder"))
    assert "builder" in text
    assert "thinks_on='this machine'" in text
    assert "tools_run_on='this machine'" in text
    assert "0x" not in text, "must not fall back to the default object repr"


def test_flow_repr_states_shared_sandbox():
    flow = AgentFlow(run_on="docker", steps=[_agent("W"), _agent("R")])
    text = repr(flow)
    assert "steps=2" in text
    assert "Docker container" in text
    assert "shared" in text, "a shared sandbox is the whole point of run_on"


def test_team_repr_states_shared_sandbox():
    a = _agent("W")
    team = AgentTeam(agents=[a], tasks=[Task(description="d", agent=a)], run_on="e2b")
    assert "E2B" in repr(team)
    assert "shared" in repr(team)


def test_repr_survives_a_broken_object():
    """Describing where something runs must never break the thing itself."""

    class Odd:
        @property
        def run_on(self):
            raise RuntimeError("boom")

    assert describe(Odd())["thinks_on"] == "this machine"


# ── where_does_it_run() speaks plain English ─────────────────────────────────
def test_explain_is_plain_for_a_local_agent():
    text = _agent().where_does_it_run()
    assert "this machine" in text
    assert "Nothing is isolated" in text


def test_explain_mentions_shared_state_for_a_workflow():
    flow = AgentFlow(run_on="docker", steps=[_agent()])
    text = flow.where_does_it_run()
    assert "shares that same sandbox" in text
    assert "visible to the next" in text


def test_explain_warns_that_a_subprocess_is_not_a_boundary():
    """Verified behaviour: under subprocess the network is reachable and
    ~/.ssh is readable. The explanation must not imply containment."""
    agent = Agent(name="A", instructions="x", sandbox=True)
    text = agent.where_does_it_run()
    assert "not a security boundary" in text
    assert "docker" in text.lower()


def test_explain_does_not_warn_for_a_real_boundary():
    flow = AgentFlow(run_on="docker", steps=[_agent()])
    assert "not a security boundary" not in flow.where_does_it_run()


# ── provider names become human phrases ──────────────────────────────────────
@pytest.mark.parametrize("provider,expected", [
    ("docker", "Docker container"),
    ("e2b", "E2B"),
    ("sandlock", "locked-down process"),
    ("anthropic", "Anthropic"),
    (None, "this machine"),
])
def test_say_place_is_readable(provider, expected):
    assert expected in say_place(provider)


def test_unknown_provider_falls_back_to_its_own_name():
    assert say_place("some-new-cloud") == "some-new-cloud"


# ── vocabulary gate: never reuse a word that is public API elsewhere ─────────
def test_no_field_name_collides_with_existing_public_api():
    """`loop` was rejected as a field name because it is already
    praisonaiagents.workflows.loop(), asyncio's event loop, and agent-loop
    jargon. This test stops anyone reintroducing that class of collision."""
    import praisonaiagents.workflows as wf

    agent_kwargs = set(inspect.signature(Agent.__init__).parameters)
    workflow_api = {n for n in dir(wf) if not n.startswith("_")}
    taken = agent_kwargs | workflow_api

    for field in describe(_agent()):
        assert field not in taken, (
            f"repr field {field!r} collides with existing public API; "
            f"pick a word that means only one thing"
        )


def test_explanation_avoids_jargon():
    """The sentences are for someone who does not know the vocabulary."""
    text = " ".join([
        _agent().where_does_it_run(),
        AgentFlow(run_on="docker", steps=[_agent()]).where_does_it_run(),
    ]).lower()
    for jargon in ("harness", "provision", "orchestration", "topology", "runtime"):
        assert jargon not in text, f"{jargon!r} is jargon; say it plainly"


# ── the point of the whole exercise ──────────────────────────────────────────
def test_repl_answers_the_question_without_docs():
    """One line per topology, each stating what runs where."""
    local = repr(_agent())
    remote = repr(AgentFlow(run_on="docker", steps=[_agent()]))
    assert local != remote
    for text in (local, remote):
        assert "thinks_on=" in text and "tools_run_on=" in text
