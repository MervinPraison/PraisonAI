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
    get_runtime_version,
    versions_compatible,
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


def test_run_evicts_agent_on_failure():
    """A failed agent.start() must evict the cached agent so state can't bleed."""
    from praisonai.runtime.server import WarmRuntime

    class _FlakyAgent:
        created = 0
        total_calls = 0

        def __init__(self, *args, **kwargs):
            type(self).created += 1

        def start(self, prompt):
            type(self).total_calls += 1
            # Only the very first call (on the first agent) fails.
            if type(self).total_calls == 1:
                raise RuntimeError("boom")
            return f"ok: {prompt}"

    runtime = WarmRuntime()

    def _fake_get_agent(key):
        with runtime._lock:
            agent = runtime._agents.get(key)
            if agent is None:
                agent = _FlakyAgent()
                runtime._agents[key] = agent
            return agent

    runtime._get_agent = _fake_get_agent  # type: ignore[assignment]

    with pytest.raises(RuntimeError):
        runtime.run("first")
    # The failed agent should have been dropped from the cache.
    assert runtime._agents == {}

    # Next call builds a fresh agent and succeeds.
    assert runtime.run("second") == "ok: second"
    assert _FlakyAgent.created == 2


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


# --- Version-compat handshake -------------------------------------------------


def test_versions_compatible_major_match():
    assert versions_compatible("2.3.4", "2.9.0") is True
    assert versions_compatible("2.0.0", "2.0.0") is True


def test_versions_compatible_major_mismatch_or_missing():
    assert versions_compatible("2.3.4", "3.0.0") is False
    assert versions_compatible("", "2.0.0") is False
    assert versions_compatible("2.0.0", "") is False
    assert versions_compatible(None, "2.0.0") is False


def test_descriptor_version_roundtrip_and_compatible():
    desc = RuntimeDescriptor(
        host="127.0.0.1", port=1, token="t", pid=os.getpid(),
        version=get_runtime_version(),
    )
    desc.write()
    loaded = RuntimeDescriptor.read()
    assert loaded is not None
    assert loaded.version == get_runtime_version()
    assert loaded.is_compatible() is True


def test_descriptor_missing_version_is_incompatible():
    # An older runtime wrote no version field; treat it as incompatible.
    desc = RuntimeDescriptor(host="127.0.0.1", port=1, token="t", pid=os.getpid())
    assert desc.version == ""
    assert desc.is_compatible() is False


def test_get_runtime_descriptor_require_compatible_skips_mismatch():
    # Live pid but an incompatible (bogus) version -> not returned when
    # require_compatible is set.
    desc = RuntimeDescriptor(
        host="127.0.0.1", port=1, token="t", pid=os.getpid(),
        version="0.0.0-incompatible",
    )
    desc.write()
    assert get_runtime_descriptor(require_compatible=False) is not None
    assert get_runtime_descriptor(require_compatible=True) is None


# --- Live session event fan-out ----------------------------------------------


def test_session_event_hub_fan_out():
    from praisonai.runtime.server import SessionEventHub

    hub = SessionEventHub()
    q1 = hub.subscribe("sess-a")
    q2 = hub.subscribe("sess-a")
    q_other = hub.subscribe("sess-b")

    hub.publish("sess-a", {"type": "run.start"})
    assert q1.get_nowait() == {"type": "run.start"}
    assert q2.get_nowait() == {"type": "run.start"}
    assert q_other.empty()

    hub.unsubscribe("sess-a", q1)
    hub.publish("sess-a", {"type": "run.result"})
    assert q2.get_nowait() == {"type": "run.result"}
    assert hub.has_subscribers("sess-b") is True  # sess-b still subscribed

    hub.unsubscribe("sess-a", q2)
    assert hub.has_subscribers("sess-a") is False


def test_warm_runtime_publishes_session_events():
    from praisonai.runtime.server import WarmRuntime

    class _StubAgent:
        def __init__(self, *a, **k):
            pass

        def start(self, prompt):
            return f"echo: {prompt}"

    runtime = WarmRuntime()

    def _fake_get_agent(key):
        return _StubAgent()

    runtime._get_agent = _fake_get_agent  # type: ignore[assignment]

    q = runtime.hub.subscribe("sess-x")
    result = runtime.run("hello", session_id="sess-x")
    assert result == "echo: hello"

    start = q.get_nowait()
    assert start["type"] == "run.start"
    assert start["session_id"] == "sess-x"
    done = q.get_nowait()
    assert done["type"] == "run.result"
    assert done["result"] == "echo: hello"


def test_attach_streams_live_session_events(monkeypatch):
    """End-to-end: a run with session_id is observable via client.attach()."""
    from praisonai.runtime import server as server_mod

    class _SlowAgent:
        def __init__(self, *a, **k):
            pass

        def start(self, prompt):
            # Give the attach subscriber time to connect first.
            time.sleep(0.2)
            return f"done: {prompt}"

    import praisonaiagents

    monkeypatch.setattr(praisonaiagents, "Agent", _SlowAgent, raising=False)

    t = threading.Thread(
        target=server_mod.serve_runtime,
        kwargs={"host": "127.0.0.1", "port": 0, "idle_timeout": 0},
        daemon=True,
    )
    t.start()

    descriptor = None
    for _ in range(50):
        descriptor = get_runtime_descriptor()
        if descriptor is not None:
            break
        time.sleep(0.05)
    assert descriptor is not None, "runtime did not start"

    try:
        client = RuntimeClient(descriptor, timeout=5.0)
        events = []

        def _collect():
            for ev in client.attach("sess-live"):
                events.append(ev)
                if ev.get("type") == "run.result":
                    break

        watcher = threading.Thread(target=_collect, daemon=True)
        watcher.start()
        time.sleep(0.1)  # let the SSE stream connect

        result = client.run("ping", session_id="sess-live")
        assert result == "done: ping"

        watcher.join(timeout=5.0)
        types = [e.get("type") for e in events]
        assert "run.start" in types
        assert "run.result" in types
    finally:
        RuntimeDescriptor.remove()
