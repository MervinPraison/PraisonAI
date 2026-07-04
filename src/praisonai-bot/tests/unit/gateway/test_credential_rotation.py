"""
Unit tests for live-credential revocation on shared-secret rotation (Issue #2661).

Verifies that:
  * Each authenticated session records the active secret's auth generation.
  * Rotating ``auth_token`` changes the generation fingerprint.
  * ``_revoke_rotated_sessions`` force-closes only the sessions stamped with a
    stale secret, using the structured ``CREDENTIALS_ROTATED`` close code, and
    leaves sessions already on the current secret untouched.
  * A config hot-reload that rotates the secret adopts it and revokes stale
    sessions, and the ``revoke_on_secret_rotation: false`` opt-out is honoured.
"""

import asyncio

import pytest

from praisonaiagents.gateway import GatewayCloseCode, GatewayConfig
from praisonai_bot.gateway.server import (
    WebSocketGateway,
    CREDENTIALS_ROTATED_CLOSE_CODE,
)


class _RecordingWS:
    """A websocket that records how it was closed."""

    def __init__(self):
        self.closed = False
        self.close_code = None
        self.close_reason = None

    async def send_json(self, data):  # pragma: no cover - not exercised here
        pass

    async def close(self, code=None, reason=None):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


def _connect(gateway, client_id, ws, generation):
    """Register a client as the real WS handshake would, with an auth stamp."""
    gateway.add_client(client_id, ws)
    gateway._client_scopes[client_id] = set()
    gateway._client_auth_generation[client_id] = generation
    session = gateway.create_session("agent", client_id=client_id)
    gateway._client_sessions[client_id] = session.session_id


def test_auth_generation_changes_when_secret_rotates():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="old-secret"))
    old = gateway._auth_generation()
    assert old  # non-empty fingerprint
    gateway.config.auth_token = "new-secret"
    assert gateway._auth_generation() != old


def test_auth_generation_stable_for_same_secret():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="s3cr3t"))
    assert gateway._auth_generation() == gateway._auth_generation()


def test_auth_generation_no_secret_sentinel():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    # Local-loopback mode: an empty/absent active secret maps to a stable
    # sentinel so those sessions are handled consistently.
    gateway.config.auth_token = ""
    assert gateway._auth_generation() == "no-auth"


@pytest.mark.asyncio
async def test_revoke_closes_only_stale_sessions():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="old-secret"))
    old_gen = gateway._auth_generation()

    stale_ws = _RecordingWS()
    _connect(gateway, "stale", stale_ws, old_gen)

    # Rotate the secret; a client that connects afterwards is on the new gen.
    gateway.config.auth_token = "new-secret"
    fresh_ws = _RecordingWS()
    _connect(gateway, "fresh", fresh_ws, gateway._auth_generation())

    revoked = await gateway._revoke_rotated_sessions()

    assert revoked == 1
    # Stale session force-closed with the structured rotation reason.
    assert "stale" not in gateway._clients
    assert "stale" not in gateway._client_sessions
    assert "stale" not in gateway._client_scopes
    assert "stale" not in gateway._client_auth_generation
    assert stale_ws.closed is True
    assert stale_ws.close_code == CREDENTIALS_ROTATED_CLOSE_CODE
    assert stale_ws.close_reason == GatewayCloseCode.CREDENTIALS_ROTATED.value
    # Session on the current secret is untouched.
    assert "fresh" in gateway._clients
    assert fresh_ws.closed is False


@pytest.mark.asyncio
async def test_revoke_noop_when_nothing_stale():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="secret"))
    ws = _RecordingWS()
    _connect(gateway, "c1", ws, gateway._auth_generation())

    revoked = await gateway._revoke_rotated_sessions()

    assert revoked == 0
    assert "c1" in gateway._clients
    assert ws.closed is False


@pytest.mark.asyncio
async def test_apply_rotation_adopts_secret_and_revokes():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="old-secret"))
    ws = _RecordingWS()
    _connect(gateway, "c1", ws, gateway._auth_generation())

    revoked = await gateway._apply_auth_secret_rotation(
        {"gateway": {"auth_token": "new-secret"}}
    )

    assert revoked == 1
    assert gateway.config.auth_token == "new-secret"
    assert ws.closed is True
    assert ws.close_reason == GatewayCloseCode.CREDENTIALS_ROTATED.value


@pytest.mark.asyncio
async def test_apply_rotation_unchanged_secret_is_noop():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="same"))
    ws = _RecordingWS()
    _connect(gateway, "c1", ws, gateway._auth_generation())

    revoked = await gateway._apply_auth_secret_rotation(
        {"gateway": {"auth_token": "same"}}
    )

    assert revoked == 0
    assert ws.closed is False


@pytest.mark.asyncio
async def test_apply_rotation_opt_out_keeps_sessions():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="old-secret"))
    ws = _RecordingWS()
    _connect(gateway, "c1", ws, gateway._auth_generation())

    revoked = await gateway._apply_auth_secret_rotation(
        {
            "gateway": {
                "auth_token": "new-secret",
                "revoke_on_secret_rotation": False,
            }
        }
    )

    # Secret adopted for new connections, but the live session is left alone.
    assert revoked == 0
    assert gateway.config.auth_token == "new-secret"
    assert ws.closed is False


@pytest.mark.asyncio
async def test_apply_rotation_no_auth_token_in_config_is_noop():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="secret"))
    ws = _RecordingWS()
    _connect(gateway, "c1", ws, gateway._auth_generation())

    revoked = await gateway._apply_auth_secret_rotation({"gateway": {}})

    assert revoked == 0
    assert gateway.config.auth_token == "secret"
    assert ws.closed is False


def test_close_code_enum_value():
    assert GatewayCloseCode.CREDENTIALS_ROTATED.value == "credentials_rotated"
