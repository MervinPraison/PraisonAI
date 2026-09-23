#!/usr/bin/env python3
"""Tests for the gateway out-of-band idle-session compaction sweep (#5170).

Covers ``WebSocketGateway`` parsing the opt-in ``lifecycle.idle_compaction``
block and its pure candidate-selection predicate. The sweep compacts sessions
that have been idle beyond a threshold off the turn critical path, so a
returning user resumes an already-compacted session with no first-message
latency spike. Off unless enabled and a persistent session store is bound, so
always-on gateways keep their exact behaviour.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonai_bot.gateway.server import WebSocketGateway


class _FakeStore:
    def __init__(self, rows):
        self._rows = rows

    def list_sessions(self, limit=50):
        return list(self._rows)

    def get_working_history(self, session_id, max_messages=None):
        return []

    def append_compaction_checkpoint(self, *args, **kwargs):
        return True


def _iso_ago(seconds: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=seconds)
    ).isoformat()


def test_idle_compaction_off_by_default():
    gw = WebSocketGateway()
    assert gw._idle_compaction_cfg is None
    assert gw._idle_compaction_task is None


def test_configure_none_is_noop():
    gw = WebSocketGateway()
    gw._configure_lifecycle(None)
    assert gw._idle_compaction_cfg is None


def test_configure_disabled_flag():
    gw = WebSocketGateway()
    gw._session_store = _FakeStore([])
    gw._configure_lifecycle({"idle_compaction": {"enabled": False}})
    assert gw._idle_compaction_cfg is None


def test_configure_requires_session_store():
    gw = WebSocketGateway()
    gw._session_store = None
    gw._configure_lifecycle({"idle_compaction": {"enabled": True}})
    assert gw._idle_compaction_cfg is None


def test_configure_enabled_defaults_and_overrides():
    gw = WebSocketGateway()
    gw._session_store = _FakeStore([])
    gw._configure_lifecycle(
        {
            "idle_compaction": {
                "enabled": True,
                "idle_after_seconds": 900,
                "min_tokens": 4000,
                "sweep_interval_seconds": 60,
            }
        }
    )
    cfg = gw._idle_compaction_cfg
    assert cfg is not None
    assert cfg["idle_after_seconds"] == 900.0
    assert cfg["min_tokens"] == 4000
    assert cfg["sweep_interval_seconds"] == 60.0
    # Unspecified knobs fall back to sane defaults.
    assert cfg["cooldown_seconds"] == 3600.0
    assert cfg["max_per_sweep"] == 20


def test_candidate_selection_filters():
    now = time.time()
    rows = [
        # idle + big -> candidate
        {"session_id": "big-idle", "updated_at": _iso_ago(2000),
         "total_tokens": 20000},
        # idle but small -> skipped
        {"session_id": "small-idle", "updated_at": _iso_ago(2000),
         "total_tokens": 100},
        # big but recently active -> skipped
        {"session_id": "big-fresh", "updated_at": _iso_ago(10),
         "total_tokens": 20000},
        # missing token count -> included (unknown size, still idle)
        {"session_id": "big-unknown", "updated_at": _iso_ago(2000)},
        # unparsable timestamp -> skipped
        {"session_id": "no-ts", "updated_at": None, "total_tokens": 20000},
    ]
    gw = WebSocketGateway()
    gw._session_store = _FakeStore(rows)
    cfg = {
        "idle_after_seconds": 1800.0,
        "min_tokens": 8000,
        "sweep_interval_seconds": 300.0,
        "cooldown_seconds": 3600.0,
        "max_per_sweep": 20,
    }
    picks = gw._idle_compaction_candidates(cfg, now)
    assert "big-idle" in picks
    assert "big-unknown" in picks
    assert "small-idle" not in picks
    assert "big-fresh" not in picks
    assert "no-ts" not in picks


def test_candidate_selection_respects_cooldown():
    now = time.time()
    rows = [
        {"session_id": "cooled", "updated_at": _iso_ago(2000),
         "total_tokens": 20000},
    ]
    gw = WebSocketGateway()
    gw._session_store = _FakeStore(rows)
    gw._idle_compaction_cooldown["cooled"] = now + 1000  # still cooling
    cfg = {
        "idle_after_seconds": 1800.0,
        "min_tokens": 8000,
        "sweep_interval_seconds": 300.0,
        "cooldown_seconds": 3600.0,
        "max_per_sweep": 20,
    }
    assert gw._idle_compaction_candidates(cfg, now) == []


def test_seconds_since_iso_parsing():
    now = time.time()
    assert WebSocketGateway._seconds_since_iso(None, now) is None
    assert WebSocketGateway._seconds_since_iso("", now) is None
    assert WebSocketGateway._seconds_since_iso("not-a-date", now) is None
    val = WebSocketGateway._seconds_since_iso(_iso_ago(100), now)
    assert val is not None
    assert 90 <= val <= 110
