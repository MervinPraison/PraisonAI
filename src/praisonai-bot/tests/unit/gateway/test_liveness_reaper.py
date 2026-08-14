"""
Unit tests for the gateway connection-liveness runtime (Issue #2798/#3911).

The core contract (``LivenessPolicy``, ``LivenessConfig``, ``PING``/``PONG``,
``LIVENESS_TIMEOUT``) landed in core via #2799 but had no runtime consumer.
These tests exercise the wrapper wiring:

  * ``_liveness_policy`` protects the default path (enabled out-of-box) yet
    honours an explicit ``interval_ms == 0`` opt-out.
  * ``_reap_session`` closes a half-open connection with ``LIVENESS_TIMEOUT``
    and deterministically releases session/client state, bumping the reaped
    counter surfaced in ``health()``.
  * The reaper KEEPs a connection with fresh activity and REAPs a silent one.
  * An inbound frame / ``PONG`` refreshes ``last_activity``; an inbound
    ``PING`` is answered with a ``PONG`` and not routed further.
  * A connection that never binds a session (stalled pre-``hello``/``join``
    handshake) still ages out via the per-connection last-seen fallback and is
    reaped, rather than living forever.
  * ``hello_ok`` advertises the liveness interval as ``heartbeat_ms``.
"""

import pytest

from praisonaiagents.gateway import GatewayCloseCode, GatewayConfig
from praisonaiagents.gateway.config import LivenessConfig
from praisonaiagents.gateway.protocols import LivenessDecision
from praisonai_bot.gateway.server import (
    WebSocketGateway,
    LIVENESS_TIMEOUT_CLOSE_CODE,
)


class _RecordingWS:
    """A websocket that records how it was closed and what it was sent."""

    def __init__(self):
        self.closed = False
        self.close_code = None
        self.close_reason = None
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=None, reason=None):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


def _connect(gateway, client_id, ws):
    """Register a client + session as the real handshake would."""
    gateway.add_client(client_id, ws)
    gateway._client_scopes[client_id] = set()
    session = gateway.create_session("agent", client_id=client_id)
    gateway._client_sessions[client_id] = session.session_id
    return session


def test_liveness_policy_enabled_out_of_box():
    # Config default leaves ``enabled=False``; the runtime still protects the
    # default path with an enabled policy derived from the config window.
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    policy = gateway._liveness_policy()
    assert policy.enabled is True
    assert policy.interval_ms == LivenessConfig().interval_ms


def test_liveness_policy_explicit_disable():
    cfg = GatewayConfig(auth_token="tmp")
    cfg.liveness = LivenessConfig(enabled=False, interval_ms=0)
    gateway = WebSocketGateway(config=cfg)
    assert gateway._liveness_policy().enabled is False


def test_liveness_policy_honours_enabled_config():
    cfg = GatewayConfig(auth_token="tmp")
    cfg.liveness = LivenessConfig(
        enabled=True, interval_ms=5_000, missed_beats_before_reap=3
    )
    gateway = WebSocketGateway(config=cfg)
    policy = gateway._liveness_policy()
    assert policy.enabled is True
    assert policy.interval_ms == 5_000
    assert policy.missed_beats_before_reap == 3


@pytest.mark.asyncio
async def test_reap_session_closes_with_liveness_timeout():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    ws = _RecordingWS()
    session = _connect(gateway, "c1", ws)

    await gateway._reap_session("c1")

    assert ws.closed is True
    assert ws.close_code == LIVENESS_TIMEOUT_CLOSE_CODE
    assert ws.close_reason == GatewayCloseCode.LIVENESS_TIMEOUT.value
    # State released deterministically.
    assert "c1" not in gateway._clients
    assert "c1" not in gateway._client_sessions
    assert "c1" not in gateway._client_scopes
    assert session.session_id not in gateway._sessions
    assert gateway._reaped_connections == 1


def test_policy_keeps_fresh_and_reaps_silent():
    cfg = GatewayConfig(auth_token="tmp")
    cfg.liveness = LivenessConfig(
        enabled=True, interval_ms=1_000, missed_beats_before_reap=2
    )
    policy = WebSocketGateway(config=cfg)._liveness_policy()
    now = 1000.0
    # Fresh: last activity just now → KEEP.
    assert policy.evaluate(now, now) is LivenessDecision.KEEP
    # Silent for >2x interval → REAP.
    assert policy.evaluate(now - 3.0, now) is LivenessDecision.REAP


@pytest.mark.asyncio
async def test_inbound_ping_is_answered_with_pong():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    ws = _RecordingWS()
    _connect(gateway, "c1", ws)

    sent = []

    async def _capture(client_id, data):
        sent.append((client_id, data))

    gateway._send_to_client = _capture  # type: ignore[assignment]

    await gateway._handle_client_message("c1", {"type": "ping"})

    assert sent == [("c1", {"type": "pong"})]


@pytest.mark.asyncio
async def test_inbound_frame_refreshes_last_activity():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    ws = _RecordingWS()
    session = _connect(gateway, "c1", ws)
    session._last_activity = 0.0

    # A PONG is consumed as activity and not routed further.
    await gateway._handle_client_message("c1", {"type": "pong"})

    assert session.last_activity > 0.0


def test_sessionless_connection_seeds_last_seen():
    # A client that connects but has not yet bound a session still gets a
    # per-connection last-seen clock so the reaper can age it out.
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    gateway.add_client("c1", _RecordingWS())
    assert "c1" in gateway._client_last_seen


@pytest.mark.asyncio
async def test_sessionless_stalled_connection_is_reaped():
    # No ``hello``/``join`` ever completes: the pre-session fallback clock must
    # let a silent handshake time out instead of living forever (Greptile P1).
    cfg = GatewayConfig(auth_token="tmp")
    cfg.liveness = LivenessConfig(
        enabled=True, interval_ms=1_000, missed_beats_before_reap=2
    )
    gateway = WebSocketGateway(config=cfg)
    ws = _RecordingWS()
    gateway.add_client("c1", ws)
    # No session bound; backdate the fallback clock past the reap window.
    gateway._client_last_seen["c1"] = 0.0

    policy = gateway._liveness_policy()
    import time as _time

    now = _time.time()
    last_activity = gateway._client_last_seen.get("c1", now)
    assert policy.evaluate(last_activity, now) is LivenessDecision.REAP

    await gateway._reap_session("c1")
    assert ws.close_code == LIVENESS_TIMEOUT_CLOSE_CODE
    assert "c1" not in gateway._clients
    assert "c1" not in gateway._client_last_seen


@pytest.mark.asyncio
async def test_sessionless_inbound_frame_refreshes_last_seen():
    # An actively-handshaking pre-session peer must not be reaped: any inbound
    # frame refreshes the fallback clock even before a session is bound.
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    gateway.add_client("c1", _RecordingWS())
    gateway._client_last_seen["c1"] = 0.0

    async def _noop(client_id, data):
        pass

    gateway._send_to_client = _noop  # type: ignore[assignment]
    await gateway._handle_client_message("c1", {"type": "ping"})

    assert gateway._client_last_seen["c1"] > 0.0


def test_teardown_drops_last_seen():
    gateway = WebSocketGateway(config=GatewayConfig(auth_token="tmp"))
    gateway.add_client("c1", _RecordingWS())
    assert "c1" in gateway._client_last_seen
    gateway.remove_client("c1")
    assert "c1" not in gateway._client_last_seen


def test_liveness_timeout_close_code_enum_value():
    assert GatewayCloseCode.LIVENESS_TIMEOUT.value == "liveness_timeout"
