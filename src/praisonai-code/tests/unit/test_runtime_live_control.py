"""Attached clients can steer and interrupt a live warm-runtime turn (Issue #5846)."""

from __future__ import annotations

import threading
import time

import pytest

from praisonaiagents.agent.interrupt import InterruptController
from praisonaiagents.agent.message_steering import MessageSteering

from praisonai_code.runtime import RuntimeClient, RuntimeDescriptor, RuntimeUnavailable
from praisonai_code.runtime import get_runtime_descriptor
from praisonai_code.runtime import server as server_mod
from praisonai_code.runtime.server import WarmRuntime


def _runtime_live_agent(**kwargs):
    config = {
        "name": "RuntimeAgent",
        "role": "Assistant",
        "goal": "Complete the task",
        **kwargs,
    }
    server_mod._enable_live_control(config)
    return _LiveAgent(**config)


class _LiveAgent:
    """Agent stand-in that runs until interrupted, recording steering it saw."""

    def __init__(self, **kwargs):
        assert kwargs.get("message_steering") is True
        self.interrupt_controller = kwargs["interrupt_controller"]
        self._message_steering = MessageSteering()
        self.started = threading.Event()
        self.seen = []

    def steer(self, message, priority=5):
        return self._message_steering.queue_message(message, priority)

    def start(self, prompt):
        self.started.set()
        while not self.interrupt_controller.event.wait(0.01):
            for msg in self._message_steering.get_pending_messages():
                if msg.content not in self.seen:
                    self.seen.append(msg.content)
        return f"stopped: {self.interrupt_controller.reason}"


def _live(runtime, stream_id):
    with runtime._lock:
        return list(runtime._live.get(stream_id, []))


def _wait_live(runtime, stream_id, count=1):
    for _ in range(200):
        agents = _live(runtime, stream_id)
        if len(agents) >= count:
            return agents
        time.sleep(0.01)
    return _live(runtime, stream_id)


def _run_in_thread(runtime, **kwargs):
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("r", runtime.run("go", **kwargs)))
    t.start()
    return t, out


def test_steer_and_interrupt_reach_live_session_turn():
    runtime = WarmRuntime()
    events = runtime.hub.subscribe("s1")
    with pytest.MonkeyPatch.context() as mp:
        import praisonaiagents

        mp.setattr(praisonaiagents, "Agent", _LiveAgent, raising=False)
        mp.setattr(
            "praisonai_code.cli.state.project_sessions.apply_cli_session_continuity",
            lambda *a, **k: None,
        )
        t, out = _run_in_thread(runtime, session_id="s1")
        (agent,) = _wait_live(runtime, "s1")
        assert agent.started.wait(2)

        assert runtime.steer("s1", "also update the tests") is True
        for _ in range(200):
            if agent.seen:
                break
            time.sleep(0.01)
        assert agent.seen == ["also update the tests"]

        assert runtime.interrupt("s1") is True
        t.join(2)

    assert out["r"] == "stopped: attach"
    # Live registration and interrupt state are cleared after the turn.
    assert _live(runtime, "s1") == []
    assert not agent.interrupt_controller.is_set()
    types = []
    while not events.empty():
        types.append(events.get_nowait()["type"])
    assert types == ["run.start", "run.steer", "run.interrupt", "run.result"]


def test_shared_attach_label_keeps_both_runs_controllable():
    """Two sessions streaming to one --attach label must not replace each other."""
    runtime = WarmRuntime()
    with pytest.MonkeyPatch.context() as mp:
        import praisonaiagents

        mp.setattr(praisonaiagents, "Agent", _LiveAgent, raising=False)
        mp.setattr(
            "praisonai_code.cli.state.project_sessions.apply_cli_session_continuity",
            lambda *a, **k: None,
        )
        t1, _ = _run_in_thread(runtime, session_id="a", event_id="shared")
        t2, _ = _run_in_thread(runtime, session_id="b", event_id="shared")
        first, second = _wait_live(runtime, "shared", count=2)
        assert first.started.wait(2) and second.started.wait(2)

        # Finishing one run must leave the other registered and controllable.
        first.interrupt_controller.request("done")
        for _ in range(200):
            if _live(runtime, "shared") == [second]:
                break
            time.sleep(0.01)
        assert _live(runtime, "shared") == [second]
        assert runtime.interrupt("shared") is True
        t1.join(2)
        t2.join(2)
    assert _live(runtime, "shared") == []
    assert runtime.interrupt("shared") is False


def test_control_without_live_turn_returns_false():
    runtime = WarmRuntime()
    assert runtime.steer("nope", "hi") is False
    assert runtime.interrupt("nope") is False


def test_enable_live_control_sets_core_seams():
    config = {}
    server_mod._enable_live_control(config)
    assert config["message_steering"] is True
    assert isinstance(config["interrupt_controller"], InterruptController)


@pytest.fixture
def live_server(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(server_mod, "_apply_cold_path_parity", lambda _config: None)
    monkeypatch.setattr(
        WarmRuntime,
        "_get_agent",
        lambda self, key: _runtime_live_agent(),
    )
    monkeypatch.setattr(
        WarmRuntime,
        "_get_session_agent",
        lambda self, session_id, model=None: _runtime_live_agent(),
    )
    shutdown = threading.Event()
    t = threading.Thread(
        target=server_mod.serve_runtime,
        kwargs={
            "host": "127.0.0.1",
            "port": 0,
            "idle_timeout": 0,
            "shutdown_event": shutdown,
        },
        daemon=False,
    )
    t.start()
    descriptor = None
    for _ in range(100):
        descriptor = get_runtime_descriptor()
        if descriptor is not None:
            break
        time.sleep(0.05)
    assert descriptor is not None, "runtime did not start"
    try:
        yield descriptor
    finally:
        shutdown.set()
        t.join(timeout=10)
        assert not t.is_alive(), "warm runtime did not shut down after test"
        RuntimeDescriptor.remove()


def test_client_steer_and_interrupt_over_http(live_server):
    client = RuntimeClient(live_server, timeout=5.0)

    # No live turn yet: a clear error, not a silent no-op.
    with pytest.raises(RuntimeUnavailable, match="no live run"):
        client.interrupt("watch")

    out = {}
    t = threading.Thread(
        target=lambda: out.setdefault("r", client.run("go", event_id="watch")), daemon=True
    )
    t.start()
    for _ in range(200):
        try:
            client.steer("watch", "focus")
            break
        except RuntimeUnavailable:
            time.sleep(0.01)
    else:
        pytest.fail("steer never reached the live turn")
    client.interrupt("watch")
    t.join(5)
    assert out["r"] == "stopped: attach"


def test_control_endpoints_require_token(live_server):
    bad = RuntimeDescriptor(
        host=live_server.host, port=live_server.port, token="wrong", pid=live_server.pid
    )
    with pytest.raises(RuntimeUnavailable, match="401"):
        RuntimeClient(bad, timeout=5.0).interrupt("watch")


def test_older_runtime_without_endpoint_reports_clearly(live_server):
    client = RuntimeClient(live_server, timeout=5.0)
    with pytest.raises(RuntimeUnavailable, match="does not support"):
        client._control("watch", "reply", {})


def test_attach_flags_send_control_without_streaming():
    from unittest.mock import MagicMock, patch

    from typer.testing import CliRunner

    from praisonai_code.cli.commands.attach import app

    with patch("praisonai_code.runtime.get_runtime_descriptor", return_value=MagicMock()), \
            patch("praisonai_code.runtime.RuntimeClient") as client_cls:
        result = CliRunner().invoke(app, ["-m", "focus", "--interrupt", "s1"])

    client = client_cls.return_value
    assert result.exit_code == 0, result.output
    client.steer.assert_called_once_with("s1", "focus")
    client.interrupt.assert_called_once_with("s1")
    client.attach.assert_not_called()
