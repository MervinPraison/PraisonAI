"""Where things run, and what happens when you ask for two places at once.

The vocabulary under test:

    run_on=        the WHOLE agent moves to a managed runtime
    tools_run_on=  only the tools move; thinking stays here
    run_in=        one execute_code() call, this call only

The rule these tests exist to protect: **one word means one thing**. A place
that cannot do the job asked of it is a typo, not a preference, so it raises
with the parameter name the user actually wanted.
"""

import pytest

from praisonaiagents import Agent, AgentFlow, AgentTeam, Task
from praisonaiagents.agent.placement import (
    managed_runtimes,
    resolve_placement,
    tool_places,
)


def _agent(name="A", **kw):
    return Agent(name=name, instructions="x", **kw)


# ── the two registries stay disjoint in meaning ──────────────────────────────
def test_a_managed_runtime_is_not_a_tool_place():
    """If these sets ever overlap, every error message below becomes a lie."""
    assert set(managed_runtimes()).isdisjoint(tool_places())


def test_the_sandbox_only_backends_are_reachable():
    """sandlock is the only real local boundary and was unreachable before."""
    for place in ("sandlock", "subprocess", "ssh", "novita"):
        assert place in tool_places(), f"{place} must be selectable"


# ── asking a place to do a job it cannot do ──────────────────────────────────
def test_run_on_a_tool_place_names_the_right_parameter():
    with pytest.raises(TypeError) as exc:
        _agent(run_on="docker")
    message = str(exc.value)
    assert "tools_run_on='docker'" in message, "must name the parameter they wanted"
    assert "cannot host an agent loop" in message


def test_tools_run_on_a_managed_runtime_names_the_right_parameter():
    with pytest.raises(TypeError) as exc:
        _agent(tools_run_on="anthropic")
    assert "run_on='anthropic'" in str(exc.value)


def test_an_unknown_place_lists_both_registries():
    with pytest.raises(TypeError) as exc:
        _agent(run_on="dokcer")
    message = str(exc.value)
    assert "anthropic" in message and "docker" in message


# ── two names for one thing ──────────────────────────────────────────────────
@pytest.mark.parametrize("kwargs", [
    {"run_on": "anthropic", "tools_run_on": "docker"},
    {"run_on": "anthropic", "backend": object()},
    {"backend": object(), "tools_run_on": "docker"},
])
def test_two_places_for_the_same_work_is_a_type_error(kwargs):
    """Never "last one wins" -- that ships tools to a machine nobody chose."""
    with pytest.raises(TypeError):
        resolve_placement("Agent", **kwargs)


# ── a class that cannot answer the question ──────────────────────────────────
@pytest.mark.parametrize("build", [
    lambda: AgentFlow(run_on="docker", steps=[_agent()]),
    lambda: AgentTeam(agents=[_agent()], tasks=[], run_on="docker"),
])
def test_run_on_is_refused_on_orchestrators(build):
    """`run_on=` on a Flow/Team used to mean tools-only. It now means the whole
    agent, so honouring the old meaning would give one word two meanings across
    adjacent classes. Refuse, and say what to type instead."""
    with pytest.raises(TypeError) as exc:
        build()
    assert "tools_run_on='docker'" in str(exc.value)


# ── the happy paths ──────────────────────────────────────────────────────────
def test_tools_run_on_is_recorded_without_provisioning_anything():
    """Nothing is created until a tool is actually called: an agent that never
    touches its sandbox must cost nothing."""
    agent = _agent(tools_run_on="subprocess")
    assert agent.tools_run_on == "subprocess"
    assert agent._tools_sandbox is None


def test_a_plain_agent_is_untouched():
    agent = _agent()
    assert agent.tools_run_on is None
    assert agent._tools_sandbox is None


def _team(**kw):
    worker = _agent("W")
    return AgentTeam(agents=[worker], tasks=[Task(description="d", agent=worker)], **kw)


@pytest.mark.parametrize("build,expected", [
    (lambda: AgentFlow(tools_run_on="docker", steps=[_agent()]), "Docker"),
    (lambda: _team(tools_run_on="e2b"), "E2B"),
])
def test_orchestrators_take_tools_run_on(build, expected):
    obj = build()
    assert expected in repr(obj)
    assert "shared" in repr(obj), "the shared sandbox is the whole point"


# ── the object says where it runs ────────────────────────────────────────────
def test_repr_uses_the_same_word_you_typed():
    agent = _agent(tools_run_on="docker")
    assert "tools_run_on='a Docker container'" in repr(agent)


def test_explain_names_the_tools_that_do_not_move():
    """The capability prompt tells the model the sandbox is where things
    happen. Any tool staying behind has to be said out loud, or the model is
    being lied to about its own reach."""

    def check_db(query: str) -> str:
        """Query the production database."""
        return "ok"

    text = _agent(tools=[check_db], tools_run_on="docker").where_does_it_run()
    assert "check_db" in text
    assert "still run on this machine" in text


def test_explain_says_nothing_about_local_tools_when_nothing_moves():
    def check_db(query: str) -> str:
        """Query the production database."""
        return "ok"

    assert "still run on" not in _agent(tools=[check_db]).where_does_it_run()


# ── run_in=: the place lives on the call that uses it ────────────────────────
def test_run_in_needs_no_constructor_argument():
    result = _agent().execute_code_sync("print(6 * 7)", run_in="subprocess")
    assert result.stdout.strip() == "42"


def test_run_in_reuses_one_sandbox_across_calls():
    """A fresh manager per call would restart a container every time and lose
    the previous call's files."""
    agent = _agent()
    agent.execute_code_sync("print(1)", run_in="subprocess")
    agent.execute_code_sync("print(2)", run_in="subprocess")
    assert list(agent._sandbox_managers) == ["subprocess"]


def test_no_place_at_all_says_how_to_name_one():
    with pytest.raises(RuntimeError) as exc:
        _agent().execute_code_sync("print(1)")
    assert "run_in='docker'" in str(exc.value)


def test_constructor_sandbox_still_sets_the_default():
    """`sandbox=` stays: clone_for_channel() passes it, and it is a legitimate
    per-agent default. `run_in=` overrides it per call."""
    agent = _agent(sandbox=True)
    assert agent.execute_code_sync("print('default')").stdout.strip() == "default"


# ── the shared sandbox contract ──────────────────────────────────────────────
# The point of a shared sandbox is that step 2 can read what step 1 wrote. These
# drive the tools directly rather than through a model, so they assert the
# contract itself and need no API key.
def test_every_agent_in_a_flow_shares_one_sandbox():
    from praisonaiagents.managed.shared_compute import SharedCompute

    writer, reader = _agent("W"), _agent("R")
    with SharedCompute("subprocess") as shared:
        shared.attach([writer, reader])
        w = {t.__name__: t for t in writer.tools}
        r = {t.__name__: t for t in reader.tools}

        w["write_file"]("handoff.txt", "written by the first agent")
        assert r["read_file"]("handoff.txt").strip() == "written by the first agent"

        # ...and it really is one instance, not two that happen to agree.
        assert w["execute_command"]("pwd") == r["execute_command"]("pwd")

    # teardown restores both agents
    assert writer.tools == [] and reader.tools == []


def test_an_agent_with_its_own_sandbox_is_left_alone_by_a_flow():
    """Attaching twice appended the capability prompt twice and, on non-LIFO
    teardown, left the agent holding tools bound to a dead instance."""
    from praisonaiagents.agent.tools_placement import (
        close_tools_sandbox,
        ensure_tools_placed,
    )
    from praisonaiagents.managed.shared_compute import SharedCompute

    own = _agent("own", tools_run_on="subprocess")
    ensure_tools_placed(own)
    inner = own._tools_sandbox

    try:
        with SharedCompute("subprocess") as flow_sandbox:
            flow_sandbox.attach([own])
            assert own._tools_sandbox is inner, "the agent's own choice wins"
            assert own.backstory.count("REMOTE Linux sandbox") == 1
    finally:
        close_tools_sandbox(own)

    assert own.tools == []


def test_a_batch_provisions_one_sandbox_not_one_per_row():
    """start_for_each() calls start() per input; each used to provision and
    destroy its own sandbox, so a 50-row batch paid for 50 of them."""
    team = _team(tools_run_on="subprocess")
    assert team._needs_tools_scope()
    with team._shared_tools_scope():
        # inside the batch scope, a nested start() must not open a second one
        assert not team._needs_tools_scope()
    assert team._needs_tools_scope(), "scope must reopen for the next batch"


# ── run_on= moves the thinking too ───────────────────────────────────────────
def test_a_hosted_agent_says_its_thinking_moved():
    """describe() used to report thinks_on='this machine' for a hosted agent --
    the diagnostic lying about the one thing it exists to answer."""
    from praisonaiagents.agent.execution_location import describe

    pytest.importorskip("praisonai.integrations")
    agent = _agent("teacher", run_on="anthropic")
    places = describe(agent)
    assert places["thinks_on"] == places["tools_run_on"]
    assert "Anthropic" in places["thinks_on"]


def test_run_on_builds_the_same_thing_backend_would():
    pytest.importorskip("praisonai.integrations")
    from praisonai.integrations import HostedAgent

    assert isinstance(_agent("t", run_on="anthropic").backend, HostedAgent)


def test_a_flow_does_not_clobber_an_agent_that_named_its_own_place():
    """Ordering matters: a flow attaches at the start of the run, before the
    agent's first turn. Checking only for a *live* sandbox would let the flow
    attach first and the agent attach again on its first chat() -- two sandboxes
    and two copies of the capability prompt on one agent.
    """
    from praisonaiagents.agent.tools_placement import (
        close_tools_sandbox,
        ensure_tools_placed,
    )
    from praisonaiagents.managed.shared_compute import SharedCompute

    own = _agent("own", tools_run_on="subprocess")
    plain = _agent("plain")

    try:
        with SharedCompute("subprocess") as flow:
            flow.attach([own, plain])
            assert own._tools_sandbox is None, "the flow must skip a declared place"
            assert plain._tools_sandbox is flow, "the flow still places plain agents"

            ensure_tools_placed(own)                       # the agent's first turn
            assert own._tools_sandbox not in (None, flow)  # its own, not the flow's
            assert own.backstory.count("REMOTE Linux sandbox") == 1
            assert plain.backstory.count("REMOTE Linux sandbox") == 1
            assert [t.__name__ for t in own.tools] == [
                "execute_command", "read_file", "write_file", "list_files",
            ]
    finally:
        close_tools_sandbox(own)

    assert own.tools == [] and plain.tools == []
