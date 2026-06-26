"""Unit tests for BotOS passive idle-activity probing (Issue #2332).

Verifies that ``BotOS._probe_activity`` reads live liveness facts from each
bot's session manager (``_active_runs`` / ``_last_active``) so the idle loop
reflects real traffic even when adapters don't call the explicit
``notify_inbound`` / ``turn_started`` hooks.
"""

import time

import pytest

try:
    from praisonai.bots.botos import BotOS
except Exception:  # pragma: no cover - optional deps not installed
    BotOS = None

pytestmark = pytest.mark.skipif(BotOS is None, reason="praisonai bots not importable")


class _FakeSession:
    def __init__(self, active_runs=None, last_active=None):
        self._active_runs = active_runs or {}
        self._last_active = last_active or {}


class _FakeBot:
    def __init__(self, session):
        self.platform = "fake"
        self._session = session


def test_probe_counts_active_runs():
    botos = BotOS()
    botos._bots = {"fake": _FakeBot(_FakeSession(active_runs={"u1": object(), "u2": object()}))}
    running, _ = botos._probe_activity()
    assert running == 2


def test_probe_reads_recent_inbound():
    botos = BotOS()
    # last_active is monotonic; a value of "now" means a very recent inbound.
    botos._bots = {"fake": _FakeBot(_FakeSession(last_active={"u1": time.monotonic()}))}
    _, last_ts = botos._probe_activity()
    # Should be close to wall-clock now (recent activity), not the frozen init.
    assert abs(time.time() - last_ts) < 5.0


def test_probe_no_session_degrades_gracefully():
    botos = BotOS()
    botos._bots = {"fake": _FakeBot(None)}
    running, last_ts = botos._probe_activity()
    assert running == 0
    assert isinstance(last_ts, float)


def test_probe_merges_explicit_hooks():
    botos = BotOS()
    botos._bots = {"fake": _FakeBot(_FakeSession(active_runs={"u1": object()}))}
    botos.turn_started()  # explicit hook bumps _running_turns to 1
    running, _ = botos._probe_activity()
    # explicit (1) + probed active_runs (1)
    assert running == 2
