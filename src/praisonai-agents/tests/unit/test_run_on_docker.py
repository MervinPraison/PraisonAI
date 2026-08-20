"""`run_on="docker"` — the whole agent in a container you own.

The distinction under test is what crosses the boundary:

    tools_run_on="docker"   your process runs the loop; only tools go inside
    run_on="docker"         the loop itself runs inside; the model call is
                            made from the container

Both name the same place. The parameter carries the scope, which is why one
word can serve both without ambiguity.

Everything that needs a live daemon is marked, so it is skipped loudly rather
than passing quietly when Docker is not running.
"""

import shutil
import subprocess

import pytest

from praisonaiagents import Agent
from praisonaiagents.agent.execution_location import describe
from praisonaiagents.agent.placement import managed_runtimes, tool_places


def _docker_running() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, timeout=25,
        ).returncode == 0
    except Exception:
        return False


needs_docker = pytest.mark.skipif(
    not _docker_running(), reason="needs a running Docker daemon"
)


def _agent(**kw):
    return Agent(name="A", instructions="You are helpful.", **kw)


# ── registration ─────────────────────────────────────────────────────────────
def test_docker_is_a_managed_runtime():
    """run_on= resolves against the managed-backend registry, so registering
    the backend is all that is needed for the parameter to accept it."""
    assert "docker" in managed_runtimes()


def test_docker_is_also_a_tool_place():
    assert "docker" in tool_places()


def test_run_on_docker_builds_the_self_hosted_backend():
    backend = _agent(run_on="docker").backend
    # docker goes through the same generic backend as every other place; the
    # bespoke one was deleted because its containers could not be reclaimed.
    assert backend.provider_name == "docker"
    assert backend.provider_name == "docker"


# ── the two scopes stay distinguishable ──────────────────────────────────────
def test_run_on_moves_the_thinking_too():
    places = describe(_agent(run_on="docker"))
    assert places["thinks_on"] == places["tools_run_on"] == "a Docker container"


def test_tools_run_on_leaves_the_thinking_here():
    places = describe(_agent(tools_run_on="docker"))
    assert places["thinks_on"] == "this machine"
    assert places["tools_run_on"] == "a Docker container"


def test_the_two_read_differently_in_the_repr():
    assert repr(_agent(run_on="docker")) != repr(_agent(tools_run_on="docker"))


def test_naming_both_is_still_a_conflict():
    """They are alternatives even when they name the same place: run_on already
    runs the tools there, so tools_run_on= has nothing left to say."""
    with pytest.raises(TypeError):
        _agent(run_on="docker", tools_run_on="docker")


# ── config marshalling (no daemon needed) ────────────────────────────────────
def test_the_agent_is_rebuilt_from_serialisable_config_only():
    """A Python callable cannot be reconstructed in the container, so it is not
    sent. The limitation is real; the test pins it so it stays deliberate."""
    from praisonai.integrations.compute_managed_agent import _as_dict

    def local_tool(x: str) -> str:
        return x

    out = _as_dict({"instructions": "be brief", "llm": "gpt-4o-mini",
                    "tools": [local_tool], "verbose": True})
    assert out["instructions"] == "be brief"
    assert out["llm"] == "gpt-4o-mini"
    assert "tools" not in out, "callables must not be smuggled into the payload"


def test_hosted_config_spellings_are_translated():
    """HostedAgentConfig says system/model where Agent says instructions/llm."""
    from praisonai.integrations.compute_managed_agent import _as_dict

    out = _as_dict({"system": "you are terse", "model": "gpt-4o-mini"})
    assert out["instructions"] == "you are terse"
    assert out["llm"] == "gpt-4o-mini"
    assert "system" not in out and "model" not in out


def test_an_empty_config_still_produces_a_valid_agent():
    from praisonai.integrations.compute_managed_agent import _as_dict

    assert _as_dict(None)["instructions"]


def test_the_result_is_read_from_a_marked_line():
    """pip warnings and telemetry share stdout with the answer, so the result
    is marked rather than assumed to be the last line."""
    from praisonai.integrations.compute_managed_agent import _parse

    noisy = (
        "WARNING: Running pip as root\n"
        "some telemetry line\n"
        '__PRAISON_RESULT__{"ok": true, "result": "42"}\n'
    )
    assert _parse(noisy) == {"ok": True, "result": "42"}
    assert _parse("no marker here") is None


# ── failure is reported, not swallowed ───────────────────────────────────────
def test_a_missing_daemon_says_what_to_do():
    import asyncio

    from praisonai.integrations.compute_managed_agent import ComputeManagedAgent

    backend = ComputeManagedAgent("docker")
    if backend.is_available:
        pytest.skip("Docker is running, so this path cannot be exercised")
    with pytest.raises(RuntimeError) as exc:
        asyncio.run(backend._ensure())
    message = str(exc.value)
    assert "docker" in message
    assert "tools_run_on='docker'" in message, "offer the alternative that needs no daemon"


# ── the real thing ───────────────────────────────────────────────────────────
@needs_docker
def test_the_whole_agent_really_runs_in_a_container():
    """Proves the loop moved: the agent reports the container's platform, not
    the host's. Needs a model key, so it asserts placement rather than output."""
    import asyncio

    from praisonai.integrations.compute_managed_agent import ComputeManagedAgent

    backend = ComputeManagedAgent("docker", config={"instructions": "be brief"})
    try:
        asyncio.run(backend._ensure())
        assert backend._instance, "no container was started"
        probe = subprocess.run(
            ["docker", "exec", f"praisonai_{backend._instance}", "python", "-c",
             "import platform, praisonaiagents; print(platform.system())"],
            capture_output=True, text=True, timeout=300,
        )
        assert probe.returncode == 0, probe.stderr[-400:]
        assert probe.stdout.strip() == "Linux", "the loop is not in a Linux container"
    finally:
        asyncio.run(backend.ashutdown())


@needs_docker
def test_the_container_is_removed_afterwards():
    import asyncio

    from praisonai.integrations.compute_managed_agent import ComputeManagedAgent

    backend = ComputeManagedAgent("docker")
    asyncio.run(backend._ensure())
    name = f"praisonai_{backend._instance}"
    asyncio.run(backend.ashutdown())

    remaining = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"name={name}"],
        capture_output=True, text=True, timeout=120,
    ).stdout.strip()
    assert remaining == "", f"container {name} outlived the backend"


# ── run_on= across every place that can host a loop ──────────────────────────
def test_run_on_covers_the_cloud_places_too():
    """run_on= accepted two names while tools_run_on= accepted twelve. That gap
    was an implementation detail -- no backend had been written for the rest --
    not a fact about the places. One generic backend closed it."""
    from praisonaiagents.agent.placement import managed_runtimes

    runtimes = set(managed_runtimes())
    for place in ("anthropic", "docker", "modal", "e2b", "daytona", "flyio", "tenki", "novita"):
        assert place in runtimes, f"run_on={place!r} should host a whole agent"


@pytest.mark.parametrize("place", ["modal", "e2b", "daytona"])
def test_a_cloud_place_builds_its_own_backend_class(place):
    """HostedAgent's factory calls issubclass() on whatever the registry
    returns, so a loader must hand back a class, not a factory function."""
    backend = _agent(run_on=place).backend
    assert backend.provider_name == place
    assert type(backend).__name__.lower().startswith(place[:4].lower())


@pytest.mark.parametrize("place", ["local", "subprocess", "sandlock", "ssh"])
def test_places_that_cannot_host_a_loop_are_still_refused(place):
    """`local` would run the agent in your own shell, which is what you get by
    passing nothing; `ssh` needs an object; the local sandboxes isolate tools
    rather than host a runtime."""
    with pytest.raises(TypeError):
        _agent(run_on=place)


def test_the_remote_agent_is_rebuilt_without_callables():
    from praisonai.integrations.compute_managed_agent import _as_dict

    def local_tool(x: str) -> str:
        return x

    out = _as_dict({"instructions": "be brief", "tools": [local_tool]})
    assert "tools" not in out, "callables cannot be rebuilt remotely"
    assert out["instructions"] == "be brief"


@needs_docker
def test_a_whole_agent_container_can_be_reclaimed():
    """It could be listed but not stopped.

    The bespoke Docker backend named its containers `praisonai-agent-<hex>`,
    while DockerCompute's lookup expects `praisonai_<instance_id>`. So
    `praisonai managed ps` showed the container and `praisonai managed stop`
    raised "No docker container found" -- the worst combination, because the
    user can see the thing they cannot reclaim. Routing through the provider
    fixes it by construction.
    """
    import asyncio

    from praisonai.integrations.compute_managed_agent import ComputeManagedAgent
    from praisonaiagents.managed._compute_bridge import resolve_compute

    backend = ComputeManagedAgent("docker")
    asyncio.run(backend._ensure())
    instance = backend._instance
    try:
        provider = resolve_compute("docker")
        listed = [i.instance_id for i in asyncio.run(provider.list_instances())]
        assert instance in listed, "managed ps cannot see the container"

        # the half that used to fail
        asyncio.run(provider.shutdown(instance))
    except Exception:
        asyncio.run(backend.ashutdown())
        raise

    remaining = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"name=praisonai_{instance}"],
        capture_output=True, text=True, timeout=120,
    ).stdout.strip()
    assert remaining == "", "managed stop reported success but left the container"


def test_the_generic_backend_honours_a_requested_image():
    """`image=` used to fall into **kwargs and be silently ignored, so asking
    for a specific image quietly got the provider's default."""
    from praisonai.integrations.compute_managed_agent import ComputeManagedAgent

    backend = ComputeManagedAgent("docker", image="python:3.11-slim")
    assert backend._image == "python:3.11-slim"


def test_docker_is_no_longer_a_special_case():
    """Every place that can host a loop now uses one backend. Docker was the
    lone exception, and the exception is what carried the reclaim bug."""
    from praisonai.integrations.compute_managed_agent import ComputeManagedAgent

    for place in ("docker", "modal", "e2b"):
        assert isinstance(_agent(run_on=place).backend, ComputeManagedAgent)


def test_a_hosted_backend_reclaims_its_instance_when_collected():
    """run_on= keeps its instance alive across calls on purpose -- keep_alive
    defaults to True -- but it should not outlive the process. There was no
    finalizer at all, so a docker container survived every script and a cloud
    instance kept billing until the provider's own idle timer noticed, which
    docker and flyio do not have."""
    import gc

    from praisonai.integrations.compute_managed_agent import ComputeManagedAgent

    released = []

    class Fake:
        provider_name = "fake"

        async def provision(self, config):
            from praisonaiagents.managed.protocols import InstanceInfo, InstanceStatus

            return InstanceInfo(instance_id="inst-1", status=InstanceStatus.RUNNING,
                                provider="fake")

        async def execute(self, instance_id, command, timeout=None):
            return {"stdout": "", "stderr": "", "exit_code": 0}

        async def shutdown(self, instance_id):
            released.append(instance_id)

    import asyncio

    backend = ComputeManagedAgent("docker")
    backend._provider = Fake()
    asyncio.run(backend._ensure())
    assert backend._instance == "inst-1"
    assert backend._finalizer is not None, "nothing would reclaim this instance"

    del backend
    gc.collect()
    assert released == ["inst-1"], "the instance outlived the backend that owned it"


def test_an_explicit_shutdown_cancels_the_finalizer():
    """Reclaiming twice should not happen; the finalizer stands down when the
    caller shuts down deliberately."""
    import asyncio

    from praisonai.integrations.compute_managed_agent import ComputeManagedAgent

    backend = ComputeManagedAgent("docker")
    backend._instance = "inst-2"
    backend._finalizer = type("F", (), {"detach": lambda self: None})()
    asyncio.run(backend.ashutdown())
    assert backend._finalizer is None
