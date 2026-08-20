"""Every provider, checked for the things that do not need a credential.

Most of what breaks an integration is checkable for free: the class resolves,
it satisfies the protocol, its methods are actually coroutines, it reports
availability without raising, both placement parameters accept or refuse it
correctly, and — the one that actually bites people — the failure when a
credential is missing names the key or the install command instead of throwing
an AttributeError from four frames down.

Modal was the cautionary tale: its `run_in=` path was broken in five separate
ways and nothing noticed, because nothing ever ran it. These tests are the
cheap half of not repeating that. The expensive half is a CI job with real
credentials.
"""

import inspect

import pytest

from praisonaiagents import Agent
from praisonaiagents.agent.placement import managed_runtimes, tool_places
from praisonaiagents.managed._compute_bridge import resolve_compute

#: Places resolvable without any vendor account.
LOCAL_PLACES = ("subprocess", "local", "docker")

#: Every place except the two that cannot be resolved from a bare name:
#: `ssh` needs a host object, `native` is an alias checked separately.
ALL_PLACES = [p for p in tool_places() if p not in ("ssh", "native")]

#: Words that make a credential failure actionable.
_ACTIONABLE = (
    "key", "token", "auth", "credential", "not available",
    "install", "config", "login", "unauthor", "api", "host", "daemon",
)


@pytest.fixture(scope="module", params=ALL_PLACES)
def place(request):
    return request.param


def _agent(**kw):
    return Agent(name="p", instructions="x", **kw)


# ── the registry ─────────────────────────────────────────────────────────────
def test_every_place_resolves_to_a_provider(place):
    assert resolve_compute(place) is not None


def test_every_provider_satisfies_the_protocol(place):
    """Everything downstream assumes these three exist."""
    provider = resolve_compute(place)
    for method in ("provision", "execute", "shutdown"):
        assert hasattr(provider, method), f"{place} has no {method}()"


def test_every_protocol_method_is_awaitable(place):
    """A sync method here does not raise -- it returns a coroutine nobody
    awaits, so the call silently does nothing."""
    provider = resolve_compute(place)
    for method in ("provision", "execute", "shutdown"):
        fn = getattr(provider, method)
        assert inspect.iscoroutinefunction(fn), f"{place}.{method}() is not async"


def test_availability_can_be_answered_without_raising(place):
    """`is_available` is consulted before anything is provisioned, so it has to
    survive a machine with no credentials and no daemon."""
    provider = resolve_compute(place)
    value = getattr(provider, "is_available", None)
    value = value() if callable(value) else value
    assert isinstance(value, bool) or value is None


# ── the parameters ───────────────────────────────────────────────────────────
def test_tools_run_on_accepts_every_place(place):
    agent = _agent(tools_run_on=place)
    assert agent.tools_run_on == place


def test_run_on_accepts_exactly_the_places_that_host_a_loop(place):
    """A place that only runs commands must be refused by run_on=, and a place
    that can host a loop must be accepted. Getting this backwards either hides
    a capability or silently runs the agent somewhere unintended."""
    hosts_a_loop = place in managed_runtimes()
    if hosts_a_loop:
        assert _agent(run_on=place).backend is not None
    else:
        with pytest.raises(TypeError) as exc:
            _agent(run_on=place)
        assert "tools_run_on" in str(exc.value), "must name the parameter that works"


def test_the_repr_names_the_place_it_was_given(place):
    """The repr must describe the place that was actually chosen.

    A place with no phrase falls back to its own name, which is fine. What
    would not be fine is the repr describing a different place -- so the value
    has to match what say_place() resolves for this name, not merely be
    non-empty. (An earlier version of this test banned the substring "this
    machine", which wrongly failed `sandlock`: a locked-down process really is
    on this machine.)
    """
    from praisonaiagents.agent.execution_location import say_place

    text = repr(_agent(tools_run_on=place))
    assert "tools_run_on=" in text
    assert say_place(place, via="compute") in text, (
        f"repr describes something other than {place!r}: {text}"
    )


# ── failure quality, which is most of the user experience ────────────────────
def test_a_missing_credential_fails_with_something_actionable(place):
    """The failure has to name the key, the install command, or the daemon --
    not surface as an AttributeError from inside a vendor SDK."""
    import asyncio

    from praisonaiagents.managed.protocols import ComputeConfig

    provider = resolve_compute(place)
    available = getattr(provider, "is_available", True)
    available = available() if callable(available) else available
    if available:
        pytest.skip(f"{place} is usable on this machine, so it cannot fail here")

    async def attempt():
        info = await provider.provision(ComputeConfig())
        await provider.shutdown(getattr(info, "instance_id", info))

    with pytest.raises(Exception) as exc:
        asyncio.run(attempt())

    message = f"{type(exc.value).__name__}: {exc.value}".lower()
    assert any(word in message for word in _ACTIONABLE), (
        f"{place} failed unhelpfully: {message[:160]}"
    )


# ── the places that deliberately refuse a bare name ──────────────────────────
def test_ssh_explains_that_a_name_is_not_enough():
    with pytest.raises(TypeError) as exc:
        _agent(tools_run_on="ssh")
    message = str(exc.value)
    assert "SSHSandbox" in message and "host" in message


def test_native_is_accepted_as_an_alias_for_sandlock():
    from praisonaiagents.agent.execution_location import say_place

    assert say_place("sandlock") in repr(_agent(tools_run_on="native"))


# ── live, where the machine allows it ────────────────────────────────────────
@pytest.mark.parametrize("place", LOCAL_PLACES)
def test_a_locally_available_place_actually_runs_a_command(place):
    """Skips loudly rather than passing quietly when the backend is absent."""
    import asyncio

    from praisonaiagents.managed.protocols import ComputeConfig

    provider = resolve_compute(place)
    available = getattr(provider, "is_available", True)
    available = available() if callable(available) else available
    if not available:
        pytest.skip(f"{place} is not available on this machine")

    async def run():
        info = await provider.provision(ComputeConfig())
        instance = getattr(info, "instance_id", info)
        try:
            return await provider.execute(instance, "echo matrix-ok")
        finally:
            await provider.shutdown(instance)

    result = asyncio.run(run())
    assert "matrix-ok" in (result.get("stdout") or ""), result


# ── reclaiming what we provisioned ───────────────────────────────────────────
def test_managed_ps_polls_places_from_the_registry_not_a_literal():
    """`_PS_PROVIDERS` was a hardcoded tuple, so a place contributed by another
    package could be provisioned and then never listed or stopped -- and an
    unreclaimable cloud sandbox is a bill nobody sees."""
    pytest.importorskip("praisonai.cli.commands.managed")
    from praisonai.cli.commands.managed import _ps_providers

    polled = set(_ps_providers())
    assert "docker" in polled

    # Local places have nothing to reclaim and must not be polled.
    assert not polled & {"local", "subprocess", "sandlock", "ssh"}

    # Everything polled must be a real place.
    assert polled <= set(tool_places())


def test_a_contributed_place_would_be_polled(monkeypatch):
    pytest.importorskip("praisonai.cli.commands.managed")
    import praisonaiagents.managed._compute_bridge as bridge
    from praisonai.cli.commands.managed import _ps_providers

    monkeypatch.setattr(bridge, "available_providers",
                        lambda: ["docker", "contributed-cloud"])
    assert "contributed-cloud" in _ps_providers()


def test_a_contributed_place_can_name_itself(monkeypatch):
    """The phrase table is a literal, so it cannot know about a package
    installed later. Rather than always printing a bare name, a contributed
    provider may declare `display_name` and have it used."""
    import praisonaiagents.managed._compute_bridge as bridge
    from praisonaiagents.agent.execution_location import say_place

    monkeypatch.setitem(bridge._DISPLAY_NAMES, "contributed", "a Contributed cloud sandbox")
    assert say_place("contributed") == "a Contributed cloud sandbox"


def test_an_unknown_place_still_falls_back_to_its_name():
    """Declaring a phrase is optional; the fallback must stay graceful."""
    from praisonaiagents.agent.execution_location import say_place

    assert say_place("some-new-cloud") == "some-new-cloud"


def test_sandbox_backends_from_plugins_are_selectable():
    """`SANDBOX_ONLY` was a hardcoded tuple, so a sandbox contributed by another
    package worked with run_in= and was invisible to tools_run_on=. `capsule`
    was the live example: it ships from praisonai-plugins."""
    from praisonaiagents.managed._sandbox_adapter import sandbox_only_names

    names = set(sandbox_only_names())
    assert {"subprocess", "sandlock", "ssh", "novita"} <= names, "the floor must hold"

    # Anything the compute registry already provides keeps its richer
    # implementation rather than being downgraded to the one-instance adapter.
    from praisonaiagents.managed._compute_bridge import _PROVIDERS

    assert not names & set(_PROVIDERS)


def test_a_plugin_sandbox_reaches_both_parameters(monkeypatch):
    import praisonaiagents.managed._sandbox_adapter as adapter

    monkeypatch.setattr(adapter, "sandbox_only_names",
                        lambda: ("subprocess", "contributed-box"))
    from praisonaiagents.managed._compute_bridge import available_providers

    assert "contributed-box" in available_providers()


# ── the two implementations must agree on vendor CONVENTIONS, not just names ──
#
# These exercise the SDK boundary rather than reading source text: a wrong
# conversion or a reversed upload with different phrasing would still slip past
# a substring check, and a harmless refactor could fail one. We mock the vendor
# SDK and assert the value Daytona actually receives.
def _daytona_with_recorded_provision(monkeypatch, config):
    """Provision against a fake Daytona SDK and return the Resources it built."""
    import sys
    import types

    recorded = {}

    class _Resources:
        def __init__(self, cpu=None, memory=None, **kw):
            recorded["cpu"] = cpu
            recorded["memory"] = memory

    class _CreateParams:
        def __init__(self, **kw):
            recorded["params"] = kw

    class _Sandbox:
        id = "sbx-1"
        class process:
            @staticmethod
            def exec(*a, **k):
                return types.SimpleNamespace(exit_code=0, result="")

    class _Client:
        def create(self, params, timeout=120):
            return _Sandbox()

    fake = types.ModuleType("daytona_sdk")
    fake.Daytona = lambda cfg: _Client()
    fake.DaytonaConfig = lambda **kw: None
    fake.Resources = _Resources
    fake.CreateSandboxFromImageParams = _CreateParams
    monkeypatch.setitem(sys.modules, "daytona_sdk", fake)

    from praisonai.integrations.compute.daytona import DaytonaCompute

    provider = DaytonaCompute(api_key="test-key")
    provider._provision_sync(config)
    return recorded


def test_daytona_asks_for_memory_in_the_unit_the_sdk_documents(monkeypatch):
    """Daytona's Resources.memory is GiB. The compute side passed megabytes
    straight through, so the default config asked for 1024 GiB of RAM and
    could not provision. Assert the actual value handed to the SDK, not the
    source that produces it."""
    pytest.importorskip("praisonai.integrations.compute.daytona")
    from praisonaiagents.managed.protocols import ComputeConfig

    recorded = _daytona_with_recorded_provision(
        monkeypatch, ComputeConfig(memory_mb=2048)
    )
    assert recorded["memory"] == 2, (
        f"2048 MB must become 2 GiB, got {recorded['memory']}"
    )

    recorded = _daytona_with_recorded_provision(
        monkeypatch, ComputeConfig(memory_mb=512)
    )
    assert recorded["memory"] == 1, (
        f"sub-GiB requests must floor to 1 GiB, not 0, got {recorded['memory']}"
    )


def test_daytona_uploads_content_then_destination(monkeypatch, tmp_path):
    """`FileSystem.upload_file(src, dst)` -- content first. The arguments were
    reversed on the compute side, so an upload wrote the path into a file
    named after the content. Assert the order the SDK actually receives."""
    pytest.importorskip("praisonai.integrations.compute.daytona")
    from praisonai.integrations.compute.daytona import DaytonaCompute

    calls = {}

    class _FS:
        def upload_file(self, src, dst, timeout=1800):
            calls["src"] = src
            calls["dst"] = dst

    provider = DaytonaCompute(api_key="test-key")
    provider._sandboxes["i"] = {"sandbox": type("S", (), {"fs": _FS()})()}

    local = tmp_path / "payload.txt"
    local.write_bytes(b"real-content")
    assert provider._upload_sync("i", str(local), "/remote/dest.txt") is True

    assert calls["src"] == b"real-content", "file content must be the src argument"
    assert calls["dst"] == "/remote/dest.txt", "remote path must be the dst argument"
