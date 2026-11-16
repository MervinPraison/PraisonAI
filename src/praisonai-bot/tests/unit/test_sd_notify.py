"""Tests for systemd sd_notify readiness/watchdog integration (Issue #6123)."""

import asyncio
import os
import socket
import sys

import pytest

from praisonai_bot.daemon.sd_notify import sd_notify, watchdog_interval

pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="AF_UNIX not available"
)


@pytest.fixture
def notify_socket(tmp_path, monkeypatch):
    path = str(tmp_path / "notify.sock")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(path)
    sock.settimeout(2)
    monkeypatch.setenv("NOTIFY_SOCKET", path)
    yield sock
    sock.close()


def _drain(sock):
    sock.settimeout(0.05)
    msgs = []
    try:
        while True:
            msgs.append(sock.recv(256).decode())
    except (socket.timeout, BlockingIOError):
        pass
    return msgs


def test_noop_without_notify_socket(monkeypatch):
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    assert sd_notify("READY=1") is False


def test_sends_state(notify_socket):
    assert sd_notify("READY=1") is True
    assert notify_socket.recv(64) == b"READY=1"


def test_unreachable_socket_fails_open(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTIFY_SOCKET", str(tmp_path / "missing.sock"))
    assert sd_notify("READY=1") is False


def test_full_queue_does_not_block(notify_socket):
    # Nobody reads the socket: once its queue fills, sends must fail fast.
    results = [sd_notify("WATCHDOG=1") for _ in range(5000)]
    assert results[0] is True
    assert results[-1] is False


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="abstract ns")
def test_abstract_namespace(monkeypatch):
    name = f"praisonai-test-{os.getpid()}"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind("\0" + name)
    sock.settimeout(2)
    try:
        monkeypatch.setenv("NOTIFY_SOCKET", "@" + name)
        assert sd_notify("WATCHDOG=1") is True
        assert sock.recv(64) == b"WATCHDOG=1"
    finally:
        sock.close()


def test_watchdog_interval(monkeypatch):
    monkeypatch.delenv("WATCHDOG_PID", raising=False)
    monkeypatch.delenv("WATCHDOG_USEC", raising=False)
    assert watchdog_interval() is None
    monkeypatch.setenv("WATCHDOG_USEC", "30000000")
    assert watchdog_interval() == 15.0
    monkeypatch.setenv("WATCHDOG_PID", str(os.getpid() + 1))
    assert watchdog_interval() is None
    monkeypatch.setenv("WATCHDOG_PID", str(os.getpid()))
    assert watchdog_interval() == 15.0
    monkeypatch.setenv("WATCHDOG_USEC", "bogus")
    assert watchdog_interval() is None


def test_systemd_unit_is_notify():
    from praisonai_bot.daemon.systemd import _generate_unit

    unit = _generate_unit("/tmp/test_bot.yaml")
    assert "Type=notify" in unit
    assert "NotifyAccess=main" in unit
    assert "WatchdogSec=" in unit
    assert "Type=simple" not in unit


def test_gateway_notifier_ready_watchdog_stopping(notify_socket, monkeypatch):
    from praisonai_bot.gateway.server import WebSocketGateway

    monkeypatch.setenv("WATCHDOG_USEC", "200000")  # ping every 0.1s
    monkeypatch.delenv("WATCHDOG_PID", raising=False)

    class _FakeServer:
        started = False

    async def scenario():
        gw = WebSocketGateway()
        gw._server = _FakeServer()
        gw._sd_notify_task = asyncio.create_task(gw._sd_notify_loop())
        await asyncio.sleep(0.15)
        before_ready = _drain(notify_socket)
        assert "READY=1" not in before_ready
        gw._server.started = True
        await asyncio.sleep(0.4)
        await gw._cancel_sd_notify_task()
        assert gw._sd_notify_task is None
        return before_ready, _drain(notify_socket)

    before_ready, after = asyncio.run(scenario())
    assert "WATCHDOG=1" in before_ready  # startup is covered by the watchdog
    assert any(m.startswith("EXTEND_TIMEOUT_USEC=") for m in before_ready)
    assert not any(m.startswith("EXTEND_TIMEOUT_USEC=") for m in after[1:])
    assert after.count("READY=1") == 1
    assert "WATCHDOG=1" in after
    assert after[-1] == "STOPPING=1"
