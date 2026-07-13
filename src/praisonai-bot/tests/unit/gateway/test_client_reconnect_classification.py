"""Tests for terminal-vs-transient connect-error handling in GatewayClient.

Covers Issue #2984: the reconnect loop must stop on non-recoverable
auth/pairing/protocol/config failures (surfacing the server's structured
``code``/``next_step``) instead of retrying forever, and must honour a
server-supplied ``retry_after`` as a backoff floor for transient failures.
"""

from __future__ import annotations

import json

import pytest

from praisonaiagents.gateway import ConnectErrorCode, is_recoverable
from praisonai_bot.gateway.client import (
    BackoffConfig,
    GatewayClient,
    GatewayConnectError,
)


# ---------------------------------------------------------------------------
# Core classifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "code",
    [
        ConnectErrorCode.AUTH_REQUIRED,
        ConnectErrorCode.AUTH_UNAUTHORIZED,
        ConnectErrorCode.PROTOCOL_UNSUPPORTED,
        ConnectErrorCode.PAIRING_REQUIRED,
        ConnectErrorCode.ORIGIN_NOT_ALLOWED,
        ConnectErrorCode.CONFIGURATION_ERROR,
    ],
)
def test_terminal_codes_are_not_recoverable(code):
    assert is_recoverable(code) is False


@pytest.mark.parametrize(
    "code",
    [ConnectErrorCode.RATE_LIMITED, ConnectErrorCode.AGENT_NOT_FOUND],
)
def test_transient_codes_are_recoverable(code):
    assert is_recoverable(code) is True


def test_is_recoverable_accepts_string_values():
    assert is_recoverable("auth_unauthorized") is False
    assert is_recoverable("rate_limited") is True


def test_is_recoverable_unknown_code_fails_open():
    # Unknown/future code: retry rather than wrongly stranding the client.
    assert is_recoverable("some_future_code") is True


# ---------------------------------------------------------------------------
# Client handshake behaviour
# ---------------------------------------------------------------------------

class _FakeWebSocket:
    """Minimal fake WebSocket that replies to the join with a preset frame."""

    def __init__(self, response: dict):
        self._response = response
        self.closed = False
        self.sent: list = []

    async def send(self, data):
        self.sent.append(data)

    async def recv(self):
        return json.dumps(self._response)

    async def close(self):
        self.closed = True


def _client_with_response(monkeypatch, response: dict) -> GatewayClient:
    client = GatewayClient(url="ws://test", agent_id="a1")

    async def _fake_connect(url, *args, **kwargs):
        return _FakeWebSocket(response)

    import praisonai_bot.gateway.client as client_mod

    monkeypatch.setattr(client_mod.websockets, "connect", _fake_connect)
    return client


@pytest.mark.asyncio
async def test_terminal_auth_error_raises_gateway_connect_error(monkeypatch):
    client = _client_with_response(
        monkeypatch,
        {
            "type": "hello_error",
            "code": "auth_unauthorized",
            "message": "Session does not belong to the requested agent",
            "next_step": "reauthenticate",
        },
    )

    with pytest.raises(GatewayConnectError) as exc_info:
        await client._connect_once()

    assert exc_info.value.code == ConnectErrorCode.AUTH_UNAUTHORIZED
    assert exc_info.value.next_step == "reauthenticate"


@pytest.mark.asyncio
async def test_transient_rate_limit_raises_connection_error(monkeypatch):
    client = _client_with_response(
        monkeypatch,
        {
            "type": "hello_error",
            "code": "rate_limited",
            "message": "Too many attempts",
            "next_step": "wait_then_retry",
            "retry_after_seconds": 5,
        },
    )

    with pytest.raises(ConnectionError):
        await client._connect_once()

    # retry_after recorded as a backoff floor for the next attempt.
    assert client._retry_after == 5.0


@pytest.mark.asyncio
async def test_legacy_error_frame_still_transient(monkeypatch):
    client = _client_with_response(
        monkeypatch,
        {"type": "error", "message": "Not joined to any session"},
    )
    with pytest.raises(ConnectionError):
        await client._connect_once()


@pytest.mark.asyncio
async def test_connection_loop_pauses_on_terminal_error(monkeypatch):
    client = _client_with_response(
        monkeypatch,
        {
            "type": "hello_error",
            "code": "pairing_required",
            "message": "Device not paired",
            "next_step": "repair",
        },
    )

    paused: list = []
    client.on_reconnect_paused = lambda code, step: paused.append((code, step))

    client._running = True
    await client._connection_loop()

    assert client._running is False
    assert paused == [(ConnectErrorCode.PAIRING_REQUIRED, "repair")]


# ---------------------------------------------------------------------------
# retry_after backoff floor
# ---------------------------------------------------------------------------

def test_retry_after_acts_as_backoff_floor():
    client = GatewayClient(
        url="ws://test",
        agent_id="a1",
        backoff=BackoffConfig(initial=1.0, max=30.0, jitter=0.0),
    )
    client._reconnect_attempts = 0
    client._retry_after = 10.0

    delay = client._calculate_backoff()

    # Floor honoured (base would be ~1s without it).
    assert delay >= 10.0
    # Consumed exactly once.
    assert client._retry_after is None


def test_retry_after_does_not_shortcut_larger_backoff():
    client = GatewayClient(
        url="ws://test",
        agent_id="a1",
        backoff=BackoffConfig(initial=1.0, max=100.0, jitter=0.0),
    )
    client._reconnect_attempts = 6  # base = 64s
    client._retry_after = 2.0

    delay = client._calculate_backoff()

    # Exponential sequence preserved; small floor does not reduce it.
    assert delay == 64.0
