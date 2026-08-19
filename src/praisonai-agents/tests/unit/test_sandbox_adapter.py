"""The adapter that makes sandbox-only backends reachable as places.

``tools_run_on=`` speaks ``ComputeProviderProtocol`` (one object hands out many
environments). ``subprocess``, ``sandlock``, ``ssh`` and ``novita`` only ever
spoke ``SandboxProtocol`` (one object *is* one environment), so they could not
be selected at all. ``SandboxComputeAdapter`` supplies the missing half.

These tests exist because mutation testing found the adapter had none: dropping
``result.error`` -- which turns "blocked by security policy" into exit 0 with
empty output -- left the whole suite green.
"""

import asyncio

import pytest

from praisonaiagents.managed._compute_bridge import available_providers, resolve_compute
from praisonaiagents.managed._sandbox_adapter import (
    NEEDS_INSTANCE,
    SANDBOX_ONLY,
    SandboxComputeAdapter,
)
from praisonaiagents.managed.protocols import ComputeConfig


def _run(coro):
    return asyncio.run(coro)


async def _with_instance(name, fn):
    provider = resolve_compute(name)
    info = await provider.provision(ComputeConfig())
    try:
        return await fn(provider, info.instance_id)
    finally:
        await provider.shutdown(info.instance_id)


# ── reachability: the point of the adapter ───────────────────────────────────
def test_sandbox_only_backends_are_selectable_as_places():
    for name in SANDBOX_ONLY:
        assert name in available_providers()


def test_the_registry_is_the_union_of_both_stacks():
    places = available_providers()
    assert "docker" in places, "compute registry"
    assert "sandlock" in places, "sandbox registry"
    assert places == sorted(set(places)), "no duplicates, stable order"


def test_a_sandbox_only_name_resolves_to_the_adapter():
    assert isinstance(resolve_compute("subprocess"), SandboxComputeAdapter)


def test_a_name_that_needs_connection_details_says_so():
    """`ssh` cannot work as a bare string -- the host lives in the object."""
    with pytest.raises((TypeError, ValueError)) as exc:
        resolve_compute("ssh")
    assert NEEDS_INSTANCE["ssh"].split(",")[0][:20] in str(exc.value) or "SSHSandbox" in str(exc.value)


# ── the failure mode that survived mutation ──────────────────────────────────
def test_a_policy_denial_is_reported_as_a_failure():
    """Dropping result.error turned a refusal into exit 0 with empty output --
    the caller could not tell "blocked" from "succeeded and printed nothing"."""

    async def check(provider, instance_id):
        return await provider.execute(instance_id, "cat /etc/passwd")

    result = _run(_with_instance("subprocess", check))
    assert result["exit_code"] != 0, "a blocked command must not report success"
    assert "blocked" in result["stderr"].lower()
    assert "root:" not in result["stdout"], "the file must not have been read"


def test_a_successful_command_reports_success():
    async def check(provider, instance_id):
        return await provider.execute(instance_id, "echo hello")

    result = _run(_with_instance("subprocess", check))
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "hello"


# ── shell semantics: the bridged tool IS a shell ─────────────────────────────
@pytest.mark.parametrize("command,expected", [
    ("echo a | tr a-z A-Z", "A"),
    ("echo x > f.txt && cat f.txt", "x"),
    ("echo $((6*7))", "42"),
])
def test_pipes_redirects_and_expansion_work(command, expected):
    """Without shell semantics the model's `echo x > f` is argv-split and
    "> f" arrives as a literal argument."""

    async def check(provider, instance_id):
        return await provider.execute(instance_id, command)

    assert _run(_with_instance("subprocess", check))["stdout"].strip() == expected


def test_state_persists_across_calls():
    """One environment held open, not one per call: a manager opened and closed
    per command would lose the previous command's files."""

    async def check(provider, instance_id):
        await provider.execute(instance_id, "echo persisted > note.txt")
        first = await provider.execute(instance_id, "pwd")
        read = await provider.execute(instance_id, "cat note.txt")
        second = await provider.execute(instance_id, "pwd")
        return first, read, second

    first, read, second = _run(_with_instance("subprocess", check))
    assert read["stdout"].strip() == "persisted"
    assert first["stdout"] == second["stdout"], "each call landed in a different place"


def test_it_reports_that_its_instances_are_not_discoverable():
    """A single environment has no cross-process registry, so it never shows up
    in `praisonai managed ps`. Saying so beats pretending otherwise."""

    async def check(provider, instance_id):
        return await provider.list_instances()

    listed = _run(_with_instance("subprocess", check))
    assert listed and listed[0].metadata.get("discoverable") is False
