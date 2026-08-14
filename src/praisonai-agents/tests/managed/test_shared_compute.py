"""Tests for the shared-sandbox execution added to AgentFlow / AgentTeam.

These use a fake ComputeProvider so the suite needs no Docker or cloud
credentials. The Docker path is exercised manually; see the PR description.
"""

import pytest

from praisonaiagents.managed._compute_bridge import available_providers, resolve_compute
from praisonaiagents.managed.shared_compute import (
    CAPABILITY_PROMPT,
    SharedCompute,
)


class FakeCompute:
    """Minimal ComputeProviderProtocol stand-in that records what it ran."""

    provider_name = "fake"

    def __init__(self):
        self.commands = []
        self.provisioned = 0
        self.shutdowns = []
        self.files = {}

    async def provision(self, config):
        self.provisioned += 1
        self.last_config = config

        class _Info:
            instance_id = f"fake_{self.provisioned}"

        return _Info()

    async def execute(self, instance_id, command, timeout=None):
        self.commands.append((instance_id, command))
        if command.startswith("cat ") and "<<" not in command:
            path = command.split(" ", 1)[1].strip("'\"")
            if path in self.files:
                return {"stdout": self.files[path], "stderr": "", "exit_code": 0}
            return {"stdout": "", "stderr": f"cat: {path}: No such file", "exit_code": 1}
        if "cat > " in command and " <<'" in command:
            # Real form: mkdir -p ... && cat > 'PATH' <<'DELIM'\nBODY\nDELIM
            # DELIM is randomised per write, so parse it out of the command.
            path = command.split("cat > ", 1)[1].split(" <<", 1)[0].strip("'\"")
            delimiter = command.split(" <<'", 1)[1].split("'\n", 1)[0]
            body = command.split(f"<<'{delimiter}'\n", 1)[1]
            body = body.rsplit(f"\n{delimiter}", 1)[0]
            self.files[path] = body
            return {"stdout": "", "stderr": "", "exit_code": 0}
        return {"stdout": "ok", "stderr": "", "exit_code": 0}

    async def shutdown(self, instance_id):
        self.shutdowns.append(instance_id)


class FakeAgent:
    """Duck-typed Agent: what _collect_agents and attach() look for."""

    def __init__(self, name, tools=None, backend=None):
        self.name = name
        self.instructions = f"You are {name}."
        self.backstory = f"You are {name}."
        self.role = name
        self.tools = list(tools or [])
        self.backend = backend

    def chat(self, *a, **k):  # pragma: no cover - presence is what matters
        return ""


# ── bridge ───────────────────────────────────────────────────────────────────
def test_resolve_compute_passthrough_and_errors():
    fake = FakeCompute()
    assert resolve_compute(fake) is fake          # instance passes through
    assert resolve_compute(None) is None
    with pytest.raises(ValueError):
        resolve_compute("not-a-provider")
    with pytest.raises(TypeError):
        resolve_compute(object())                 # not a provider, not a name


def test_known_provider_names_listed():
    for name in ("docker", "e2b", "modal", "daytona", "flyio", "local"):
        assert name in available_providers()


# ── SharedCompute ────────────────────────────────────────────────────────────
def test_provisioning_is_lazy_and_single():
    fake = FakeCompute()
    sc = SharedCompute(fake)
    assert fake.provisioned == 0, "must not provision until a tool is used"

    ec, _, _, _ = sc.build_tools()
    ec("echo one")
    ec("echo two")
    assert fake.provisioned == 1, "one instance shared across calls"
    assert len({inst for inst, _ in fake.commands}) == 1


def test_shutdown_tears_down_and_is_idempotent():
    fake = FakeCompute()
    sc = SharedCompute(fake)
    sc.build_tools()[0]("echo hi")
    instance = sc.instance_id

    sc.shutdown()
    assert fake.shutdowns == [instance]
    assert sc.instance_id is None
    sc.shutdown()  # second call must not raise or double-shutdown
    assert fake.shutdowns == [instance]


def test_context_manager_tears_down_on_exception():
    fake = FakeCompute()
    with pytest.raises(RuntimeError):
        with SharedCompute(fake) as sc:
            sc.build_tools()[0]("echo hi")
            raise RuntimeError("step blew up")
    assert fake.shutdowns, "sandbox must be released even when a step raises"


def test_write_then_read_shares_state():
    fake = FakeCompute()
    with SharedCompute(fake) as sc:
        _, read_file, write_file, _ = sc.build_tools()
        write_file("/workspace/a.txt", "SECRET-42")
        assert read_file("/workspace/a.txt") == "SECRET-42"


def test_concurrent_first_use_provisions_once():
    """Parallel first-use calls must share one sandbox, not race into several."""
    import threading

    class SlowCompute(FakeCompute):
        async def provision(self, config):
            import time
            time.sleep(0.05)  # widen the race window
            return await super().provision(config)

    fake = SlowCompute()
    sc = SharedCompute(fake)
    ec, _, _, _ = sc.build_tools()

    barrier = threading.Barrier(8)

    def hit():
        barrier.wait()
        ec("echo hi")

    threads = [threading.Thread(target=hit) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert fake.provisioned == 1, "concurrent first use must provision exactly one sandbox"
    assert len({inst for inst, _ in fake.commands}) == 1


def test_write_file_content_containing_delimiter_token_is_preserved():
    """Content that looks like the heredoc terminator must not truncate/execute."""
    fake = FakeCompute()
    with SharedCompute(fake) as sc:
        _, read_file, write_file, _ = sc.build_tools()
        payload = "line1\n__PRAISON_EOF__\nrm -rf /\nline4"
        write_file("/workspace/danger.txt", payload)
        assert read_file("/workspace/danger.txt") == payload


def test_result_is_never_empty_string():
    """An empty tool result reads as 'no progress' and trips the loop guard."""
    fake = FakeCompute()
    sc = SharedCompute(fake)
    assert sc._format({"stdout": "", "stderr": "", "exit_code": 0}) != ""
    assert "Error" in sc._format({"stdout": "", "stderr": "boom", "exit_code": 1})


# ── attach ───────────────────────────────────────────────────────────────────
def test_attach_adds_tools_and_capability_prompt():
    fake = FakeCompute()
    agent = FakeAgent("Writer")
    with SharedCompute(fake) as sc:
        sc.attach([agent])
        assert [t.__name__ for t in agent.tools] == [
            "execute_command", "read_file", "write_file", "list_files",
        ]
        # Patched on backstory, not instructions: Agent builds its system
        # prompt from role/goal/backstory, so .instructions would be ignored.
        assert CAPABILITY_PROMPT in agent.backstory
    assert CAPABILITY_PROMPT not in agent.backstory, "must restore on shutdown"
    assert agent.tools == []


def test_attach_skips_agents_with_their_own_backend():
    fake = FakeCompute()
    managed = FakeAgent("HasBackend", backend=object())
    with SharedCompute(fake) as sc:
        sc.attach([managed])
    assert managed.tools == [], "agent with its own backend must be left alone"


def test_attach_replaces_same_named_tools_but_keeps_others():
    def execute_command(command: str) -> str:
        return "LOCAL"

    def custom_tool(x: str) -> str:
        return x

    fake = FakeCompute()
    agent = FakeAgent("A", tools=[execute_command, custom_tool])
    with SharedCompute(fake) as sc:
        sc.attach([agent])
        names = [t.__name__ for t in agent.tools]
        assert names.count("execute_command") == 1
        assert "custom_tool" in names, "unrelated tools must survive"
        ec = [t for t in agent.tools if t.__name__ == "execute_command"][0]
        assert ec("hostname") != "LOCAL", "must be the remote-bound tool"


# ── AgentFlow wiring ─────────────────────────────────────────────────────────
def test_collect_agents_walks_nested_steps_and_dedupes():
    from praisonaiagents import AgentFlow
    from praisonaiagents.workflows import parallel, repeat, route, when

    a, b = FakeAgent("A"), FakeAgent("B")
    flow = AgentFlow(steps=[
        a,
        route({"x": [b], "default": [a]}),
        parallel([a, b]),
        repeat(b, until=lambda ctx: True),
        when("{{x}} > 1", [a], [b]),
        lambda ctx: "plain function is not an agent",
    ])
    collected = flow._collect_agents()
    assert [x.name for x in collected] == ["A", "B"], "each agent exactly once, in order"


def test_flow_without_compute_does_not_provision():
    from praisonaiagents import AgentFlow

    flow = AgentFlow(steps=[FakeAgent("A")])
    assert flow.compute is None
    assert flow._collect_agents()[0].tools == []
