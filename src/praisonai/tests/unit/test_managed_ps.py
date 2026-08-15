"""Tests for `praisonai managed ps` / `stop` and cross-process instance lookup.

No Docker required: providers are faked. The real Docker path is exercised
manually; see the PR description.
"""

import time

import pytest
from typer.testing import CliRunner

from praisonai.cli.commands.managed import (
    _format_uptime,
    app,
)
import praisonai.cli.commands.managed as managed_cli


class _Status:
    def __init__(self, value):
        self.value = value


class _Info:
    def __init__(self, instance_id, created_at=None, image="python:3.12-slim"):
        self.instance_id = instance_id
        self.status = _Status("running")
        self.endpoint = f"docker://{instance_id[:12]}"
        self.provider = "docker"
        self.created_at = created_at if created_at is not None else time.time() - 90
        self.metadata = {"image": image}


class FakeProvider:
    """Stands in for a ComputeProviderProtocol implementation."""

    def __init__(self, instances=None, available=True):
        self.is_available = available
        self._instances = list(instances or [])
        self.shutdowns = []

    async def list_instances(self):
        return list(self._instances)

    async def shutdown(self, instance_id):
        self.shutdowns.append(instance_id)
        self._instances = [i for i in self._instances if i.instance_id != instance_id]


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def one_docker_instance(monkeypatch):
    """Route every provider lookup to a single fake docker provider."""
    provider = FakeProvider([_Info("docker_abc123")])

    def fake_resolve(name):
        if name == "docker":
            return provider
        raise ImportError(f"{name} not installed")

    monkeypatch.setattr(managed_cli, "_PS_PROVIDERS", ("docker", "e2b"))
    monkeypatch.setattr(
        "praisonaiagents.managed._compute_bridge.resolve_compute", fake_resolve
    )
    return provider


# ── uptime formatting ────────────────────────────────────────────────────────
@pytest.mark.parametrize("seconds,expected", [
    (0, "-"),          # unknown created_at renders as "-"
    (5, "5s"),
    (90, "1m"),
    (3700, "1h01m"),
    (90000, "1d01h"),
])
def test_format_uptime(seconds, expected):
    created = 0 if seconds == 0 else time.time() - seconds
    assert _format_uptime(created) == expected


# ── ps ───────────────────────────────────────────────────────────────────────
def test_ps_lists_running_sandbox(runner, one_docker_instance):
    result = runner.invoke(app, ["ps"])
    assert result.exit_code == 0
    assert "docker_abc123" in result.output
    assert "python:3.12-slim" in result.output
    assert "1 running" in result.output


def test_ps_json_is_machine_readable(runner, one_docker_instance):
    import json

    result = runner.invoke(app, ["ps", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload[0]["instance_id"] == "docker_abc123"
    assert payload[0]["provider"] == "docker"
    assert payload[0]["status"] == "running"


def test_ps_reports_empty_state(runner, monkeypatch):
    monkeypatch.setattr(managed_cli, "_discover_instances", lambda *a, **k: [])
    result = runner.invoke(app, ["ps"])
    assert result.exit_code == 0
    assert "No running sandboxes" in result.output


def test_ps_skips_unavailable_providers(runner, monkeypatch):
    """A provider with no credentials/daemon is a normal state, not an error."""
    monkeypatch.setattr(managed_cli, "_PS_PROVIDERS", ("docker",))
    monkeypatch.setattr(
        "praisonaiagents.managed._compute_bridge.resolve_compute",
        lambda name: FakeProvider([_Info("never_shown")], available=False),
    )
    result = runner.invoke(app, ["ps"])
    assert result.exit_code == 0
    assert "never_shown" not in result.output


# ── stop ─────────────────────────────────────────────────────────────────────
def test_stop_requires_target(runner):
    result = runner.invoke(app, ["stop"])
    assert result.exit_code == 1
    assert "--all" in result.output


def test_stop_unknown_id_fails_loudly(runner, one_docker_instance):
    result = runner.invoke(app, ["stop", "docker_does_not_exist"])
    assert result.exit_code == 1
    assert "No running sandbox" in result.output
    assert one_docker_instance.shutdowns == []


def test_stop_by_id(runner, one_docker_instance):
    result = runner.invoke(app, ["stop", "docker_abc123"])
    assert result.exit_code == 0
    assert one_docker_instance.shutdowns == ["docker_abc123"]


def test_stop_all(runner, one_docker_instance):
    result = runner.invoke(app, ["stop", "--all"])
    assert result.exit_code == 0
    assert one_docker_instance.shutdowns == ["docker_abc123"]
    assert "1 stopped" in result.output


def test_stop_reports_failure_exit_code(runner, monkeypatch):
    class Failing(FakeProvider):
        async def shutdown(self, instance_id):
            raise RuntimeError("daemon gone")

    provider = Failing([_Info("docker_abc123")])
    monkeypatch.setattr(managed_cli, "_PS_PROVIDERS", ("docker",))
    monkeypatch.setattr(
        "praisonaiagents.managed._compute_bridge.resolve_compute", lambda name: provider
    )
    result = runner.invoke(app, ["stop", "--all"])
    assert result.exit_code == 1
    assert "Failed to stop" in result.output


# ── cross-process lookup (the reason ps/stop work at all) ────────────────────
def test_docker_shutdown_raises_when_container_missing():
    """A stop that found nothing must not report success."""
    docker_mod = pytest.importorskip("praisonai.integrations.compute.docker")
    compute = docker_mod.DockerCompute()
    compute._containers = {}
    compute._find_container = lambda instance_id: None

    with pytest.raises(ValueError, match="No docker container"):
        compute._shutdown_sync("docker_missing")


def test_docker_shutdown_falls_back_to_lookup_by_name():
    """Instances started by another process must still be stoppable."""
    docker_mod = pytest.importorskip("praisonai.integrations.compute.docker")

    class FakeContainer:
        def __init__(self):
            self.stopped = False
            self.removed = False

        def stop(self, timeout=None):
            self.stopped = True

        def remove(self, force=False):
            self.removed = True

    container = FakeContainer()
    compute = docker_mod.DockerCompute()
    compute._containers = {}                       # nothing known in-process
    compute._find_container = lambda instance_id: container

    compute._shutdown_sync("docker_from_other_process")
    assert container.stopped and container.removed
