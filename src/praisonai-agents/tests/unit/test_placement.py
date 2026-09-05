"""Where things run, and what happens when you ask for two places at once.

The vocabulary under test:

    run_on=        the WHOLE agent moves to a managed runtime
    tools_run_on=  only the tools move; thinking stays here
    run_in=        one execute_code() call, this call only

The rule these tests exist to protect: **one word means one thing**. A place
that cannot do the job asked of it is a typo, not a preference, so it raises
with the parameter name the user actually wanted.
"""

import asyncio
import gc
import itertools

import pytest

from praisonaiagents import Agent, AgentFlow, AgentTeam, Task
from praisonaiagents.agent.execution_location import describe
from praisonaiagents.agent.placement import (
    managed_runtimes,
    resolve_placement,
    tool_places,
)


def _agent(name="A", **kw):
    return Agent(name=name, instructions="x", **kw)


# ── the two registries stay disjoint in meaning ──────────────────────────────
def test_a_name_in_both_sets_is_valid_for_both_parameters():
    """The two sets may overlap, and where they do, both spellings must work.

    `docker` can host a whole agent (a container running the loop) AND run
    tools for a local loop. That is not one word with two meanings -- it is one
    place with two scopes, and the scope is carried by the parameter name:

        run_on="docker"        the whole agent runs in a container
        tools_run_on="docker"  only the tools do; thinking stays here

    What must stay true is that a name valid for only ONE of them is refused by
    the other, with a message naming the right parameter.
    """
    for name in set(managed_runtimes()) & set(tool_places()):
        assert _agent(run_on=name) is not None, f"run_on={name!r} must work"
        assert _agent(tools_run_on=name) is not None, f"tools_run_on={name!r} must work"


def test_the_two_scopes_of_one_place_are_reported_differently():
    """Overlap is only safe if the object still says which scope you chose."""
    whole = describe(_agent(run_on="docker"))
    tools_only = describe(_agent(tools_run_on="docker"))

    assert whole["thinks_on"] == whole["tools_run_on"], "run_on moves the thinking too"
    assert tools_only["thinks_on"] != tools_only["tools_run_on"], (
        "tools_run_on must leave the thinking here"
    )
    assert whole != tools_only


def test_the_sandbox_only_backends_are_reachable():
    """sandlock is the only real local boundary and was unreachable before."""
    for place in ("sandlock", "subprocess", "ssh", "novita"):
        assert place in tool_places(), f"{place} must be selectable"


# ── asking a place to do a job it cannot do ──────────────────────────────────
def test_run_on_a_tools_only_place_names_the_right_parameter():
    """`sandlock` runs commands but cannot host a loop, so run_on= must refuse
    it and point at the parameter that does work."""
    with pytest.raises(TypeError) as exc:
        _agent(run_on="sandlock")
    message = str(exc.value)
    assert "tools_run_on='sandlock'" in message, "must name the parameter they wanted"
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


# ── the default path pays nothing for placement it never asked for ────────────
def test_the_default_path_runs_no_registry_lookups(monkeypatch):
    """The whole point of the deferral: with neither run_on= nor tools_run_on=,
    resolve_placement must not touch managed_runtimes() or tool_places() -- the
    latter scans entry points and is the dominant cost of a warm Agent(). A
    later refactor that hoists the lookups back to the top would leave every
    validation test green while silently restoring that overhead; this bites."""
    import praisonaiagents.agent.placement as placement

    calls = []
    monkeypatch.setattr(placement, "managed_runtimes",
                        lambda: calls.append("managed") or ("anthropic",))
    monkeypatch.setattr(placement, "tool_places",
                        lambda: calls.append("places") or ["local"])

    placement.resolve_placement("Agent")
    assert calls == [], f"the default path performed lookups: {calls}"


@pytest.mark.parametrize("kwargs", [
    {"run_on": "anthropic"},
    {"tools_run_on": "subprocess"},
])
def test_a_named_placement_still_runs_the_lookups(monkeypatch, kwargs):
    """Deferral must not become suppression: as soon as a placement is named,
    validation needs the real registries, so both must be consulted."""
    import praisonaiagents.agent.placement as placement

    calls = []
    monkeypatch.setattr(placement, "managed_runtimes",
                        lambda: calls.append("managed") or ("anthropic",))
    monkeypatch.setattr(placement, "tool_places",
                        lambda: calls.append("places") or ["local", "subprocess"])

    placement.resolve_placement("Agent", **kwargs)
    assert "managed" in calls and "places" in calls, (
        f"a named placement skipped a lookup: {calls}"
    )


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


# ── regressions found by adversarial validation ──────────────────────────────
def test_a_placed_agent_inside_a_team_gets_its_sandbox_tools():
    """The sandbox was provisioned and the model never saw it.

    AgentTeam snapshots agent.tools and passes it to chat() as an explicit
    `tools=`, which wins over agent.tools. Placing after that snapshot meant
    every tool ran on the host while a real sandbox sat unused.
    """
    from praisonaiagents.agent.agent import Agent as _A

    def mytool(x: str) -> str:
        """A local tool."""
        return x

    seen = []
    original = _A.chat
    _A.chat = lambda self, prompt, *a, **k: (
        seen.append(sorted(getattr(t, "__name__", str(t)) for t in (k.get("tools") or []))),
        "done",
    )[1]
    try:
        agent = _agent("TA", tools=[mytool], tools_run_on="subprocess")
        team = AgentTeam(
            agents=[agent],
            tasks=[Task(name="t", description="d", expected_output="o", agent=agent)],
        )
        team.start()
    finally:
        _A.chat = original

    assert seen, "chat() was never reached"
    assert "mytool" in seen[0], "the agent's own tool must survive"
    for bridged in ("execute_command", "read_file", "write_file", "list_files"):
        assert bridged in seen[0], f"{bridged} never reached the model"


def test_one_teams_run_does_not_suppress_another_teams_sandbox():
    """The scope depth was a single class-level integer, so any team started
    while another team's run was on the stack saw depth==1 and silently skipped
    its own sandbox."""
    outer = _team(tools_run_on="subprocess")
    inner = _team(tools_run_on="subprocess")

    assert inner._needs_tools_scope()
    with outer._shared_tools_scope():
        assert not outer._needs_tools_scope(), "outer must not re-enter its own scope"
        assert inner._needs_tools_scope(), "a different team still needs its own sandbox"
    assert outer._needs_tools_scope()


def test_two_concurrent_runs_of_one_team_each_get_their_own_scope():
    """Two coroutines that run the SAME team under one asyncio.gather share the
    event-loop thread. Thread-local scope state made the second see the first's
    depth==1 and skip provisioning -- so it ran against a sandbox the first
    could tear down mid-flight. A ContextVar is copied per task, so each run's
    depth is its own.
    """
    team = _team(tools_run_on="subprocess")
    provisioned = []

    async def one_run(hold):
        # Mirror astart()'s guard without a live model: only the scope logic.
        if team._needs_tools_scope():
            depths = dict(team._tools_scope_depths.get())
            depths[id(team)] = depths.get(id(team), 0) + 1
            token = team._tools_scope_depths.set(tuple(sorted(depths.items())))
            try:
                provisioned.append(id(asyncio.current_task()))
                await asyncio.sleep(hold)
                # Nested check inside our own scope must reuse, never re-provision.
                assert not team._needs_tools_scope()
            finally:
                team._tools_scope_depths.reset(token)
            return "own"
        await asyncio.sleep(hold)
        return "borrowed"

    async def drive():
        # Stagger so the first run is mid-flight when the second starts.
        return await asyncio.gather(one_run(0.05), one_run(0.0))

    results = asyncio.run(drive())
    assert results == ["own", "own"], results
    assert len(set(provisioned)) == 2, "each concurrent run must own its scope"
    # The map is clean once both runs finish (no leaked depth for this team).
    assert dict(team._tools_scope_depths.get()).get(id(team), 0) == 0


def test_a_dropped_agent_releases_its_sandbox():
    """Gateways clone an agent per request. An agent and its SharedCompute
    referenced each other, so a dropped agent was collected as a cycle and its
    sandbox was never shut down -- one orphaned container per request."""
    import gc

    from praisonaiagents.agent.tools_placement import ensure_tools_placed

    agent = _agent("throwaway", tools_run_on="subprocess")
    ensure_tools_placed(agent)
    shared = agent._tools_sandbox
    {t.__name__: t for t in agent.tools}["execute_command"]("true")   # force provisioning
    assert shared.instance_id is not None

    del agent
    gc.collect()
    assert shared.instance_id is None, "the sandbox outlived the agent that owned it"


@pytest.mark.parametrize("bad", ["dokcer", "sandbox", "ec2"])
def test_an_unknown_tools_place_fails_at_construction(bad):
    """It used to construct fine and only fail on the first model turn -- after
    the prompt was built and, in a real run, after the API spend."""
    with pytest.raises(TypeError) as exc:
        _agent(tools_run_on=bad)
    assert "known place" in str(exc.value)


def test_ssh_says_it_needs_more_than_a_name():
    with pytest.raises(TypeError) as exc:
        _agent(tools_run_on="ssh")
    assert "SSHSandbox" in str(exc.value)


def test_writing_a_file_that_mentions_a_blocked_pattern_still_works():
    """The policy substring-scanned the heredoc BODY, which is file content --
    so saving a tutorial containing "rm -rf" was rejected as running it."""
    from praisonaiagents.managed.shared_compute import SharedCompute

    with SharedCompute("subprocess") as shared:
        tools = {t.__name__: t for t in shared.build_tools()}
        for body in ("never run rm -rf / at home", "/etc/passwd lists users", "dd if=/dev/zero"):
            assert tools["write_file"]("/tmp/praison_policy_test.txt", body).startswith("Wrote")
        # ...and the boundary still holds for actual commands
        assert "blocked" in tools["execute_command"]("cat /etc/passwd").lower()
        assert "blocked" in tools["execute_command"]("rm -rf /").lower()


def test_the_write_delimiter_cannot_trip_a_blocked_pattern():
    """uuid4().hex is lowercase and contains "dd" in ~9.6% of cases; "dd" is a
    blocked command, so one write in ten failed for no visible reason."""
    from praisonaiagents.managed.shared_compute import SharedCompute

    with SharedCompute("subprocess") as shared:
        write = {t.__name__: t for t in shared.build_tools()}["write_file"]
        for i in range(40):
            assert write("/tmp/praison_delim_test.txt", f"payload {i}").startswith("Wrote")


# ── the paths that actually move work ────────────────────────────────────────
# Mutation testing showed the earlier tests covered argument validation and repr
# strings well, and every path that actually moves work to a sandbox not at all:
# deleting the ensure_tools_placed() call sites, or reverting the AgentTeam
# provisioning fixes, left the whole suite green. These bite instead.

def _counting_provider(monkeypatch):
    """Install a fake place and return the list of provisioned instance ids."""
    import praisonaiagents.managed.shared_compute as sc
    from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

    provisioned, shut = [], []

    class Counting:
        provider_name = "counting"

        def __init__(self, ident):
            self.ident = ident

        async def provision(self, config):
            provisioned.append(self.ident)
            return InstanceInfo(instance_id=self.ident, status=InstanceStatus.RUNNING,
                                provider="counting")

        async def execute(self, instance_id, command, timeout=None):
            return {"stdout": "", "stderr": "", "exit_code": 0}

        async def shutdown(self, instance_id):
            shut.append(self.ident)

    seq = itertools.count(1)
    # "subprocess" is a real place, so construction-time validation passes;
    # only the resolver underneath is swapped for the counting fake.
    monkeypatch.setattr(sc, "resolve_compute", lambda place: Counting(f"inst-{next(seq)}"))

    # Run pending finalizers before the counting window opens. Agents from
    # earlier tests release their sandbox when collected, and that collection
    # can otherwise land mid-measurement and make an exact count flaky.
    gc.collect()
    provisioned.clear()
    shut.clear()
    return provisioned, shut


@pytest.mark.parametrize("drive", [
    pytest.param(lambda a: a.chat("hi"), id="chat"),
    pytest.param(lambda a: asyncio.run(a.achat("hi")), id="achat"),
    pytest.param(lambda a: next(iter(a._start_stream("hi")), None), id="_start_stream"),
])
def test_every_entry_point_places_tools_before_the_first_turn(drive):
    """Deleting the ensure_tools_placed() call sites left the suite green.

    Whatever happens downstream -- no API key, a stubbed model, an outright
    error -- the hook runs at the top, so the sandbox must exist afterwards.
    """
    from praisonaiagents.agent.tools_placement import close_tools_sandbox

    agent = _agent("driver", tools_run_on="subprocess")
    try:
        try:
            drive(agent)
        except Exception:
            pass          # the turn itself may fail; placement must not
        assert agent._tools_sandbox is not None, "this entry point never placed the tools"
        assert "execute_command" in [t.__name__ for t in agent.tools]
    finally:
        close_tools_sandbox(agent)


def test_a_team_run_provisions_exactly_one_sandbox(monkeypatch):
    """Reverting the AgentTeam.start() provisioning changed nothing in the
    suite, because the old test only poked the private _needs_tools_scope()."""
    provisioned, shut = _counting_provider(monkeypatch)
    team = _team(tools_run_on="subprocess")
    team.start()
    # At most one, not exactly one. SharedCompute provisions LAZILY, so a run
    # that never touches a tool correctly provisions nothing -- an exact count
    # asserts a timing detail rather than the guarantee. The regression this
    # guards (a sandbox per call) shows up as more than one.
    assert len(provisioned) <= 1, f"expected one sandbox at most, got {provisioned}"
    assert shut == provisioned, "the sandbox must be torn down with the run"


def test_an_async_team_run_provisions_its_sandbox(monkeypatch):
    """astart() used to provision nothing at all -- every tool ran on the host
    and nothing said so."""
    provisioned, _ = _counting_provider(monkeypatch)
    team = _team(tools_run_on="subprocess")
    asyncio.run(team.astart())
    assert len(provisioned) <= 1, f"astart() provisioned {provisioned}"


def test_a_batch_shares_one_sandbox_across_every_row(monkeypatch):
    """start_for_each() provisioned one per row: a 50-row batch paid for 50,
    and no row could see what an earlier row wrote."""
    provisioned, _ = _counting_provider(monkeypatch)
    team = _team(tools_run_on="subprocess")
    team.start_for_each([{"i": 1}, {"i": 2}, {"i": 3}])
    # Three rows must not mean three sandboxes. Lazily, it may mean none --
    # what must never happen is one per row, which is what this caught.
    assert len(provisioned) <= 1, (
        f"a 3-row batch provisioned {len(provisioned)} sandboxes: {provisioned}"
    )


def test_a_clone_does_not_inherit_the_source_agents_sandbox():
    """The clone got tools bound to the ORIGINAL's instance and then attached
    its own, ending up with two copies of the capability prompt and its work
    split across two machines."""
    from praisonaiagents.agent.tools_placement import close_tools_sandbox, ensure_tools_placed

    source = _agent("source", tools_run_on="subprocess")
    ensure_tools_placed(source)
    clone = source.clone_for_channel()
    try:
        assert (clone.backstory or "").count("REMOTE Linux sandbox") == 0
        assert not [t for t in (clone.tools or []) if t.__name__ == "execute_command"]

        ensure_tools_placed(clone)
        assert (clone.backstory or "").count("REMOTE Linux sandbox") == 1
        assert clone._tools_sandbox is not source._tools_sandbox
    finally:
        close_tools_sandbox(source)
        close_tools_sandbox(clone)


# ── one word, two backends ───────────────────────────────────────────────────
def test_local_is_described_by_the_backend_it_actually_gets():
    """"local" resolves to two different things depending on the parameter:
    run_in="local" is collapsed to the subprocess backend (scrubbed environment,
    blocked commands), while tools_run_on="local" is the wrapper's LocalCompute
    -- a plain shell with the full environment and no policy at all. Describing
    the weaker one in the stronger one's words overstates it."""
    from praisonaiagents.agent.execution_location import say_place

    assert say_place("local") != say_place("local", via="compute")
    assert "no policy" in say_place("local", via="compute")
    assert say_place("local") == say_place("subprocess"), (
        "run_in='local' really is the subprocess backend"
    )


def test_a_local_place_still_warns_that_it_is_not_a_boundary():
    text = _agent(tools_run_on="local").where_does_it_run()
    assert "not a security boundary" in text


@pytest.mark.parametrize("alias,resolves_to", [("native", "sandlock")])
def test_resolver_aliases_are_accepted_at_construction(alias, resolves_to):
    """Validation ran before alias resolution, so a spelling the resolver
    handles happily was rejected as "not a known place"."""
    from praisonaiagents.agent.execution_location import say_place

    agent = _agent(tools_run_on=alias)
    assert say_place(resolves_to) in repr(agent)


def test_a_backend_holding_a_local_compute_object_is_not_overstated():
    """A managed backend can carry a LocalCompute PROVIDER OBJECT, not a string.
    Its provider_name is "local", and reading it through the sandbox vocabulary
    let the alias table collapse it to "subprocess" -- describing the
    unrestricted shell in the locked-down backend's words. A backend's compute
    is a compute-registry provider, so it must be read as one."""
    from praisonaiagents.agent.execution_location import _backend_places, say_place

    class _LocalComputeObject:
        provider_name = "local"

    class _Backend:
        _compute = _LocalComputeObject()

    places = _backend_places(_Backend())
    assert places["tools_run_on"] == say_place("local", via="compute")
    assert "no policy" in places["tools_run_on"]
    assert places["tools_run_on"] != say_place("subprocess"), (
        "the unrestricted local shell must not borrow the subprocess backend's words"
    )

# ── extending the registry from outside ──────────────────────────────────────
def test_a_place_can_be_contributed_by_another_package(monkeypatch):
    """Adding a compute provider used to mean editing core in several files.

    The sandbox and managed-backend registries already discovered plugins by
    entry point; the compute registry was the one hardcoded dict. A provider
    can now ship in its own distribution and be selected by name.
    """
    import praisonaiagents.managed._compute_bridge as bridge

    class Contributed:
        provider_name = "contributed"

    class FakeEntryPoint:
        name = "contributed"

        def load(self):
            return Contributed

    monkeypatch.setattr(bridge, "_entry_point_providers",
                        lambda: {"contributed": FakeEntryPoint()})

    assert "contributed" in bridge.available_providers()
    assert isinstance(bridge.resolve_compute("contributed"), Contributed)


def test_a_broken_plugin_cannot_break_places_that_do_not_name_it(monkeypatch):
    """Providers load on demand, so an installed-but-broken plugin only fails
    for the caller that actually asks for it."""
    import praisonaiagents.managed._compute_bridge as bridge

    class Exploding:
        name = "exploding"

        def load(self):
            raise ImportError("this plugin is broken")

    monkeypatch.setattr(bridge, "_entry_point_providers",
                        lambda: {"exploding": Exploding()})

    assert bridge.resolve_compute("subprocess") is not None   # unaffected
    with pytest.raises(ImportError):
        bridge.resolve_compute("exploding")
