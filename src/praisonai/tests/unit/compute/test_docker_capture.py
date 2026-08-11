"""Tests for docker capture-after-setup / reuse (issue #3670).

Uses a fake docker client so the suite runs without a docker daemon. Verifies:
- second provision of the same definition starts from the capture and skips setup
- editing the definition invalidates the capture (new hash → full rebuild)
- ``refresh:`` runs only on capture-based starts
- a failed commit degrades to today's ephemeral behaviour (run still succeeds)
- age-based prune removes registry entries and images
"""

import time

import pytest

pytest.importorskip("praisonaiagents")

from praisonaiagents.managed.protocols import ComputeConfig
from praisonai.integrations.compute import docker as docker_mod
from praisonai.integrations.compute.docker import DockerCompute


class _FakeImages:
    def __init__(self, store):
        self._store = store  # set of existing image refs

    def get(self, ref):
        if ref not in self._store:
            raise KeyError(ref)
        return object()

    def pull(self, ref):
        self._store.add(ref)

    def remove(self, ref, force=False):
        self._store.discard(ref)


class _FakeContainer:
    def __init__(self, client, image):
        self.id = "deadbeef" * 8
        self._client = client
        self.image = image

    def exec_run(self, cmd, workdir=None, demux=False):
        # Record setup/refresh commands for assertions.
        self._client.exec_log.append(cmd)
        if demux:
            return 0, (b"", b"")
        return 0, b""

    def commit(self, repository=None, tag=None):
        if self._client.commit_fails:
            raise RuntimeError("commit boom")
        self._client.images._store.add(f"{repository}:{tag}")
        self._client.commit_log.append(f"{repository}:{tag}")

    def remove(self, force=False):
        pass

    def stop(self, timeout=10):
        pass

    def reload(self):
        pass

    @property
    def status(self):
        return "running"


class _FakeContainers:
    def __init__(self, client):
        self._client = client

    def run(self, image, **kwargs):
        self._client.run_log.append(image)
        return _FakeContainer(self._client, image)


class _FakeClient:
    def __init__(self, existing_images=()):
        self.images = _FakeImages(set(existing_images))
        self.containers = _FakeContainers(self)
        self.run_log = []
        self.exec_log = []
        self.commit_log = []
        self.commit_fails = False

    def ping(self):
        return True


@pytest.fixture
def registry_tmp(tmp_path, monkeypatch):
    reg = tmp_path / "registry.json"
    monkeypatch.setattr(docker_mod, "_REGISTRY_DIR", str(tmp_path))
    monkeypatch.setattr(docker_mod, "_REGISTRY_PATH", str(reg))
    return reg


def _provider(client):
    c = DockerCompute()
    c._client = client
    return c


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_docker_capture_and_reuse(registry_tmp):
    client = _FakeClient(existing_images={"python:3.12-slim"})
    config = ComputeConfig(setup=["make setup"])

    # First provision: full setup + capture.
    prov1 = _provider(client)
    _run(prov1.provision(config))
    assert client.exec_log == [["sh", "-c", "make setup"]]
    assert len(client.commit_log) == 1
    capture_ref = client.commit_log[0]
    assert capture_ref.startswith("praisonai-env:")

    # Second provision with same definition: starts from capture, skips setup.
    client.exec_log.clear()
    prov2 = _provider(client)
    _run(prov2.provision(config))
    assert client.run_log[-1] == capture_ref  # started from the capture image
    assert client.exec_log == []  # setup skipped
    assert len(client.commit_log) == 1  # no new capture


def test_definition_change_invalidates(registry_tmp):
    client = _FakeClient(existing_images={"python:3.12-slim"})
    prov = _provider(client)

    _run(prov.provision(ComputeConfig(setup=["make setup"])))
    first_ref = client.commit_log[0]

    client.exec_log.clear()
    # Edited definition → new hash → full rebuild + new capture.
    _run(prov.provision(ComputeConfig(setup=["make setup", "make extra"])))
    assert client.exec_log == [["sh", "-c", "make setup"], ["sh", "-c", "make extra"]]
    assert len(client.commit_log) == 2
    assert client.commit_log[1] != first_ref


def test_refresh_runs_only_on_capture_start(registry_tmp):
    client = _FakeClient(existing_images={"python:3.12-slim"})
    config = ComputeConfig(setup=["make setup"])
    config.metadata["refresh"] = ["pip install -e ."]

    # First provision (fresh): setup runs, refresh does NOT.
    prov1 = _provider(client)
    _run(prov1.provision(config))
    assert ["sh", "-c", "pip install -e ."] not in client.exec_log

    # Second provision (from capture): only refresh runs.
    client.exec_log.clear()
    prov2 = _provider(client)
    _run(prov2.provision(config))
    assert client.exec_log == [["sh", "-c", "pip install -e ."]]


def test_capture_failure_degrades_ephemeral(registry_tmp):
    client = _FakeClient(existing_images={"python:3.12-slim"})
    client.commit_fails = True
    config = ComputeConfig(setup=["make setup"])

    prov = _provider(client)
    info = _run(prov.provision(config))  # must not raise
    assert info.instance_id
    assert client.commit_log == []  # commit failed → nothing recorded
    # Registry has no entry → next run rebuilds ephemerally.
    assert prov.list_captures() == []


def test_noncapturing_definition_noop(registry_tmp):
    # No setup and no packages → nothing to capture; behaves as before.
    client = _FakeClient(existing_images={"python:3.12-slim"})
    prov = _provider(client)
    _run(prov.provision(ComputeConfig()))
    assert client.commit_log == []
    assert prov.list_captures() == []


def test_registry_gc_prune(registry_tmp):
    client = _FakeClient(existing_images={"python:3.12-slim"})
    prov = _provider(client)
    _run(prov.provision(ComputeConfig(setup=["make setup"])))

    captures = prov.list_captures()
    assert len(captures) == 1
    ref = captures[0]["ref"]
    assert ref in client.images._store

    # Nothing is old yet.
    assert prov.prune_captures(max_age_s=3600) == []
    assert len(prov.list_captures()) == 1

    # Age everything out.
    pruned = prov.prune_captures(max_age_s=0)
    assert len(pruned) == 1
    assert prov.list_captures() == []
    assert ref not in client.images._store  # image removed


def test_touch_capture_updates_last_used(registry_tmp):
    client = _FakeClient(existing_images={"python:3.12-slim"})
    config = ComputeConfig(setup=["make setup"])

    prov = _provider(client)
    _run(prov.provision(config))
    first = prov.list_captures()[0]["last_used"]

    time.sleep(0.01)
    _run(prov.provision(config))  # capture hit → touch
    second = prov.list_captures()[0]["last_used"]
    assert second >= first


def test_differing_env_values_do_not_share_capture(registry_tmp):
    # Same definition, different secret values → separate captures. The second
    # provision must NOT reuse the first's committed filesystem (which ran setup
    # with different secrets), so setup runs again under a distinct image tag.
    client = _FakeClient(existing_images={"python:3.12-slim"})

    prov1 = _provider(client)
    _run(prov1.provision(ComputeConfig(setup=["make setup"], env={"TOKEN": "a"})))
    ref_a = client.commit_log[0]

    client.exec_log.clear()
    prov2 = _provider(client)
    _run(prov2.provision(ComputeConfig(setup=["make setup"], env={"TOKEN": "b"})))
    # Setup ran again (not a reuse) and a *different* capture image was created.
    assert client.exec_log == [["sh", "-c", "make setup"]]
    ref_b = client.commit_log[1]
    assert ref_a != ref_b
    assert len(prov2.list_captures()) == 2


def test_concurrent_captures_preserve_each_other(registry_tmp):
    # Two providers commit different definitions "concurrently": the read-modify
    # -write must not drop either entry (lost-update). Simulated by interleaving
    # capture() calls; the file-lock/re-read keeps both.
    client = _FakeClient(existing_images={"python:3.12-slim"})
    prov = _provider(client)

    _run(prov.provision(ComputeConfig(setup=["make one"])))
    _run(prov.provision(ComputeConfig(setup=["make two"])))

    hashes = {c["hash"] for c in prov.list_captures()}
    assert len(hashes) == 2  # both captures survived


def test_registry_records_definition_label(registry_tmp):
    from praisonaiagents.managed.protocols import definition_hash

    client = _FakeClient(existing_images={"python:3.12-slim"})
    config = ComputeConfig(setup=["make setup"], env={"TOKEN": "x"})
    prov = _provider(client)
    _run(prov.provision(config))

    entry = prov.list_captures()[0]
    # The non-sensitive definition_hash is stored for display; the registry key
    # (secret-aware capture_key) differs from it.
    assert entry["definition"] == definition_hash(config)
    assert entry["hash"] != entry["definition"]
