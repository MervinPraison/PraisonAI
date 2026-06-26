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


def test_run_clears_chat_history_between_successful_runs():
    """Successful runs must not leak prior conversation into the next /run call."""
    from praisonai.runtime.server import WarmRuntime

    class _StatefulAgent:
        def __init__(self, *args, **kwargs):
            self.chat_history = []

        def start(self, prompt):
            self.chat_history.append({"role": "user", "content": prompt})
            self.chat_history.append({"role": "assistant", "content": f"echo: {prompt}"})
            return f"echo: {prompt}"

        def _replace_chat_history(self, history):
            self.chat_history = list(history)

    runtime = WarmRuntime()

    def _fake_get_agent(key):
        with runtime._lock:
            agent = runtime._agents.get(key)
            if agent is None:
                agent = _StatefulAgent()
                runtime._agents[key] = agent
            return agent

    runtime._get_agent = _fake_get_agent  # type: ignore[assignment]

    assert runtime.run("first") == "echo: first"
    agent = runtime._agents["__default__"]
    assert len(agent.chat_history) == 0

    assert runtime.run("second") == "echo: second"
    assert len(agent.chat_history) == 0


def test_run_skips_warm_runtime_when_auto_save_enabled(monkeypatch):
    """Default runs auto-save sessions; the warm path must not bypass that."""
    import importlib

    attach_calls = []

    def _fake_attach(*args, **kwargs):
        attach_calls.append(True)
        return False

    monkeypatch.setattr("praisonai.cli.commands.run._try_attach_runtime", _fake_attach)

    mock_praison = type("P", (), {"config_list": [{}], "handle_direct_prompt": lambda self, p: "ok"})()
    main_mod = importlib.import_module("praisonai.cli.main")
    monkeypatch.setattr(main_mod, "PraisonAI", lambda: mock_praison)

    mock_output = type("O", (), {
        "is_json_mode": False,
        "emit_result": lambda *a, **k: None,
    })()
    monkeypatch.setattr("praisonai.cli.commands.run.get_output_controller", lambda: mock_output)

    from praisonai.cli.commands.run import _run_prompt

    _run_prompt("hello", no_save=False)
    assert attach_calls == []


def test_run_attaches_warm_runtime_when_no_save(monkeypatch):
    """With --no-save, the warm path may attach when no other flags block it."""
    import importlib

    attach_calls = []

    def _fake_attach(*args, **kwargs):
        attach_calls.append(True)
        return False

    monkeypatch.setattr("praisonai.cli.commands.run._try_attach_runtime", _fake_attach)

    mock_praison = type("P", (), {"config_list": [{}], "handle_direct_prompt": lambda self, p: "ok"})()
    main_mod = importlib.import_module("praisonai.cli.main")
    monkeypatch.setattr(main_mod, "PraisonAI", lambda: mock_praison)

    mock_output = type("O", (), {
        "is_json_mode": False,
        "emit_result": lambda *a, **k: None,
    })()
    monkeypatch.setattr("praisonai.cli.commands.run.get_output_controller", lambda: mock_output)

    from praisonai.cli.commands.run import _run_prompt

    _run_prompt("hello", no_save=True)
    assert len(attach_calls) == 1


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
