"""Unit tests for the opt-in warm local runtime.

Covers the runtime descriptor lockfile lifecycle, the thin client's
transparent fall-back, and an end-to-end loopback round-trip against the
stdlib HTTP runtime server using a stubbed warm agent.
"""

import os
import threading
import time

import pytest

from praisonai.runtime import (
    RuntimeClient,
    RuntimeDescriptor,
    RuntimeUnavailable,
    get_runtime_descriptor,
    get_runtime_lock_path,
)


@pytest.fixture(autouse=True)
def isolated_project(tmp_path, monkeypatch):
    """Run inside a temp project dir so the per-project lockfile doesn't leak.

    The runtime descriptor is project-scoped (``<cwd>/.praisonai/runtime``), so
    chdir-ing into a temp dir isolates each test's lockfile.
    """
    monkeypatch.chdir(tmp_path)
    yield


def test_descriptor_write_read_roundtrip():
    desc = RuntimeDescriptor(host="127.0.0.1", port=12345, token="secret", pid=os.getpid())
    path = desc.write()
    assert path.exists()
    # Token file should not be world-readable.
    if os.name == "posix":
        assert (os.stat(path).st_mode & 0o077) == 0

    loaded = RuntimeDescriptor.read()
    assert loaded is not None
    assert loaded.host == "127.0.0.1"
    assert loaded.port == 12345
    assert loaded.token == "secret"
    assert loaded.base_url == "http://127.0.0.1:12345"


def test_descriptor_missing_returns_none():
    assert RuntimeDescriptor.read() is None
    assert get_runtime_descriptor() is None


def test_get_runtime_descriptor_removes_stale_lock():
    # A pid that is not alive should be treated as stale and cleaned up.
    desc = RuntimeDescriptor(host="127.0.0.1", port=1, token="t", pid=2147483600)
    desc.write()
    assert get_runtime_lock_path().exists()

    result = get_runtime_descriptor(require_alive=True)
    assert result is None
    assert not get_runtime_lock_path().exists()


def test_get_runtime_descriptor_keeps_live_lock():
    desc = RuntimeDescriptor(host="127.0.0.1", port=1, token="t", pid=os.getpid())
    desc.write()
    result = get_runtime_descriptor(require_alive=True)
    assert result is not None
    assert result.pid == os.getpid()


def test_client_unreachable_raises():
    # Nothing is listening on this port; the client should report unavailable.
    desc = RuntimeDescriptor(host="127.0.0.1", port=1, token="t", pid=os.getpid())
    client = RuntimeClient(desc, timeout=1.0)
    assert client.ping() is False
    with pytest.raises(RuntimeUnavailable):
        client.run("hello")


def test_server_roundtrip(monkeypatch):
    """Boot the real stdlib server with a stubbed agent and round-trip a prompt."""
    from praisonai.runtime import server as server_mod

    class _StubAgent:
        def __init__(self, *args, **kwargs):
            pass

        def start(self, prompt):
            return f"echo: {prompt}"

    # Stub the lazy Agent import inside WarmRuntime._get_agent.
    import praisonaiagents

    monkeypatch.setattr(praisonaiagents, "Agent", _StubAgent, raising=False)

    # Run the server in a background thread on an auto-selected port.
    t = threading.Thread(
        target=server_mod.serve_runtime,
        kwargs={"host": "127.0.0.1", "port": 0, "idle_timeout": 0},
        daemon=True,
    )
    t.start()

    # Wait for the lockfile to appear (server bound + descriptor written).
    descriptor = None
    for _ in range(50):
        descriptor = get_runtime_descriptor()
        if descriptor is not None:
            break
        time.sleep(0.05)
    assert descriptor is not None, "runtime did not start"

    try:
        client = RuntimeClient(descriptor, timeout=5.0)
        assert client.ping() is True
        result = client.run("world")
        assert result == "echo: world"

        # Wrong token must be rejected.
        bad = RuntimeDescriptor(
            host=descriptor.host, port=descriptor.port, token="wrong", pid=descriptor.pid
        )
        bad_client = RuntimeClient(bad, timeout=5.0)
        assert bad_client.ping() is False
    finally:
        # Stop the server by hitting it from another thread is complex; instead
        # rely on daemon thread + test process teardown. Clean the lockfile.
        RuntimeDescriptor.remove()
