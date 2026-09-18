#!/usr/bin/env python3
"""Tests for config hot-reload observability in health() (Issue #3049).

Covers the core contract (`ReloadStatus`, `compute_config_revision`) and the
wrapper's population of reload outcome / applied-config revision / watcher
liveness in `WebSocketGateway.health()`.
"""

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonaiagents.gateway import ReloadStatus, compute_config_revision
from praisonai_bot.gateway.server import WebSocketGateway


# ── Core: compute_config_revision ──────────────────────────────────────────

def test_revision_stable_across_key_ordering():
    """Same logical config -> same revision regardless of key order."""
    a = compute_config_revision({"b": 1, "a": {"y": 2, "x": 3}})
    b = compute_config_revision({"a": {"x": 3, "y": 2}, "b": 1})
    assert a == b


def test_revision_changes_with_content():
    """Different config content -> different revision."""
    a = compute_config_revision({"a": 1})
    b = compute_config_revision({"a": 2})
    assert a != b


def test_revision_empty_is_stable_sentinel():
    """None/empty config both hash to the same stable sentinel."""
    assert compute_config_revision(None) == compute_config_revision({})


def test_revision_unhashable_does_not_raise():
    """A config with non-JSON values still hashes rather than raising."""
    class Weird:
        pass

    rev = compute_config_revision({"x": Weird()})
    assert isinstance(rev, str) and len(rev) == 12


# ── Core: ReloadStatus ─────────────────────────────────────────────────────

def test_reload_status_defaults():
    r = ReloadStatus()
    assert r.watcher == "disabled"
    assert r.last_result == "never"
    assert r.to_dict() == {
        "watcher": "disabled",
        "last_result": "never",
        "last_at": None,
        "changed_paths": [],
        "error": None,
    }


def test_reload_status_to_dict_serializable():
    r = ReloadStatus(
        watcher="active",
        last_result="ok",
        last_at=123.0,
        changed_paths=("channels.telegram",),
    )
    d = r.to_dict()
    assert d["watcher"] == "active"
    assert d["changed_paths"] == ["channels.telegram"]


# ── Wrapper: health() surfaces reload state ────────────────────────────────

def test_health_no_reload_fields_without_config():
    """Gateway started without a config file -> no reload/revision fields."""
    gw = WebSocketGateway()
    health = gw.health()
    assert "reload" not in health
    assert "applied_config_revision" not in health


def test_health_reports_applied_revision_and_watcher():
    """With a config path + applied revision, health surfaces both."""
    gw = WebSocketGateway()
    gw._config_path = "/tmp/does-not-exist-gateway.yaml"
    gw._applied_config_revision = "abc123abc123"
    gw._reload_watcher_active = True
    health = gw.health()
    assert health["applied_config_revision"] == "abc123abc123"
    assert health["reload"]["watcher"] == "active"
    # On-disk read fails for a missing file -> no on_disk revision, no crash.
    assert "on_disk_config_revision" not in health


def test_record_reload_status_failure():
    """A failed reload is recorded so it's visible in health()."""
    gw = WebSocketGateway()
    gw._reload_watcher_active = True
    gw._record_reload_status("failed", error="channels.telegram.token: required")
    d = gw._reload_status.to_dict()
    assert d["last_result"] == "failed"
    assert d["watcher"] == "active"
    assert "token" in d["error"]
    assert d["last_at"] is not None


def test_health_watcher_reflects_live_state_after_reload():
    """health() overlays live watcher liveness onto the recorded snapshot.

    Regression: a reload recorded while the watcher was active must not keep
    reporting ``watcher='active'`` after the watcher exits (Issue #3049).
    """
    gw = WebSocketGateway()
    gw._config_path = "/tmp/does-not-exist-gateway.yaml"
    # Reload recorded while the watcher was alive.
    gw._reload_watcher_active = True
    gw._record_reload_status("ok")
    assert gw.health()["reload"]["watcher"] == "active"
    # Watcher later exits — health must now report it as disabled.
    gw._reload_watcher_active = False
    assert gw.health()["reload"]["watcher"] == "disabled"


def test_reload_failure_recorded_via_locked(tmp_path):
    """_reload_config_locked records 'failed' when config is invalid."""
    gw = WebSocketGateway()
    bad = tmp_path / "gateway.yaml"
    # Parses to a bare string (non-dict) -> load_gateway_config raises ValueError.
    bad.write_text("just a scalar, not a mapping")
    asyncio.run(gw._reload_config_locked(str(bad)))
    assert gw._reload_status is not None
    assert gw._reload_status.last_result == "failed"
    assert gw._config_path == str(bad)


# ── Hot-reload apply (Issue #3378) ─────────────────────────────────────────

def test_hot_appliable_paths_classified_as_hot_not_restart():
    """Hot-appliable keys go to hot_reload_paths, not a restart plan."""
    gw = WebSocketGateway()
    plan = gw._build_reload_plan(
        {"gateway.logging.level", "channels.telegram.enabled", "gateway.drain_timeout"}
    )
    assert plan.hot_reload_paths == {"gateway.logging.level", "gateway.drain_timeout"}
    assert "telegram" in plan.restart_channels
    assert not plan.full_restart


def test_unknown_gateway_key_still_full_restart():
    """A gateway key not on the hot list stays fail-safe (full restart)."""
    gw = WebSocketGateway()
    plan = gw._build_reload_plan({"gateway.some_unknown_knob"})
    assert plan.full_restart
    assert not plan.hot_reload_paths


def test_apply_hot_reload_mutates_live_state():
    """apply_hot_reload applies logging level and drain timeouts in place."""
    import logging

    gw = WebSocketGateway()
    gw._reload_drain_timeout = None
    new_cfg = {
        "gateway": {
            "logging": {"level": "DEBUG"},
            "reload_drain_timeout": 7,
        }
    }
    gw.apply_hot_reload(
        {"gateway.logging.level", "gateway.reload_drain_timeout"}, new_cfg
    )
    assert logging.getLogger("praisonai_bot").level == logging.DEBUG
    assert gw._reload_drain_timeout == 7.0


def test_apply_hot_reload_invalid_timeout_preserves_live_value():
    """A malformed timeout is ignored and keeps the current live value.

    Regression for the P1: assigning ``None`` on a bad edit would silently drop
    a previously-configured drain window, so subsequent channel reloads would
    skip their drain. A malformed hot-reload edit must be a no-op for that key.
    """
    gw = WebSocketGateway()
    gw._reload_drain_timeout = 5.0
    gw.apply_hot_reload(
        {"gateway.drain_timeout"}, {"gateway": {"drain_timeout": "oops"}}
    )
    assert gw._reload_drain_timeout == 5.0


def test_apply_hot_reload_explicit_none_disables_timeout():
    """An explicit None/absent value is an intentional disable (-> None)."""
    gw = WebSocketGateway()
    gw._reload_drain_timeout = 5.0
    gw.apply_hot_reload(
        {"gateway.drain_timeout"}, {"gateway": {"drain_timeout": None}}
    )
    assert gw._reload_drain_timeout is None


def test_gateway_conforms_to_supports_hot_reload_protocol():
    """The gateway satisfies the core SupportsHotReload protocol."""
    from praisonaiagents.gateway.config import SupportsHotReload

    assert isinstance(WebSocketGateway(), SupportsHotReload)


# ── Candidate validation + rollback (Issue #5144) ──────────────────────────

def test_gateway_conforms_to_reload_validation_protocol():
    """The gateway satisfies the core ReloadValidationProtocol contract.

    greptile #2: the exported protocol requires a public async
    ``validate_candidate``; the gateway must actually implement it (not only a
    private sync pre-flight), so ``isinstance`` holds and consumers following
    the public contract can await it.
    """
    from praisonaiagents.gateway.config import (
        CandidateReport,
        ReloadValidationProtocol,
    )

    gw = WebSocketGateway()
    assert isinstance(gw, ReloadValidationProtocol)

    report = asyncio.run(gw.validate_candidate({}))
    assert isinstance(report, CandidateReport)
    assert report.ok


def test_validate_candidate_ok_stages_without_activating():
    """A buildable agents config validates but does NOT go live yet.

    greptile #1: validation must not mutate the live registry — the candidate
    is only activated after ingress is quiesced. The built candidate is carried
    on the report and can be activated explicitly.
    """
    gw = WebSocketGateway()
    report = gw._validate_candidate(
        {"agents": {"a": {"instructions": "hi", "model": "gpt-4o-mini"}}}
    )
    assert report.ok
    # Not live yet — no cutover happened during validation.
    assert "a" not in gw._agents
    assert "a" in report.candidate["agents"]
    # Explicit activation installs it live.
    gw._activate_candidate(report.candidate)
    assert "a" in gw._agents


def test_validate_candidate_rejects_and_leaves_live_intact(monkeypatch):
    """A candidate whose agent build raises is rejected; live agents intact.

    This is the core of the issue: a runtime-invalid (but schema-valid) config
    must be a rejected reload with the previous runtime intact — never mutated
    half-way — so no outage can occur.
    """
    gw = WebSocketGateway()
    # Seed a live agent that must survive a rejected candidate.
    ok = gw._validate_candidate(
        {"agents": {"live": {"instructions": "keep me", "model": "gpt-4o-mini"}}}
    )
    gw._activate_candidate(ok.candidate)
    assert "live" in gw._agents

    def _boom(*args, **kwargs):
        raise RuntimeError("adapter throws on load")

    monkeypatch.setattr(gw, "_create_agents_from_config", _boom)
    report = gw._validate_candidate(
        {"agents": {"broken": {"instructions": "x"}}}
    )
    assert not report.ok
    assert any("agent build failed" in f for f in report.failures)
    # Previous live agent intact; broken candidate never registered.
    assert "live" in gw._agents
    assert "broken" not in gw._agents


def test_full_restart_rejected_keeps_previous_config_no_outage(monkeypatch):
    """A structural reload with an invalid candidate never drains live channels.

    Regression for Issue #5144: the failing candidate must be rejected *before*
    ``stop_channels`` is called, so a bad edit cannot take a running gateway
    offline. Verifies stop/start_channels are never invoked and health() shows
    the rejection.
    """
    gw = WebSocketGateway()
    # Establish a last-known-good loaded config so the diff path is taken.
    gw._loaded_config = {
        "gateway": {"port": 8765},
        "agents": {"live": {"instructions": "ok", "model": "gpt-4o-mini"}},
        "channels": {},
    }
    gw._validate_candidate(gw._loaded_config)

    calls = {"stop": 0, "start": 0}

    async def _stop(*a, **k):
        calls["stop"] += 1

    async def _start(*a, **k):
        calls["start"] += 1

    monkeypatch.setattr(gw, "stop_channels", _stop)
    monkeypatch.setattr(gw, "start_channels", _start)

    # New config: structural change (gateway.port) forcing full_restart, whose
    # candidate agent build blows up.
    new_cfg = {
        "gateway": {"port": 9999},
        "agents": {"broken": {"instructions": "x"}},
        "channels": {},
    }
    monkeypatch.setattr(gw, "load_gateway_config", lambda p: new_cfg)

    def _boom(*args, **kwargs):
        raise RuntimeError("unreachable model")

    # Only the candidate build must fail; leave everything else intact.
    orig = gw._create_agents_from_config
    monkeypatch.setattr(gw, "_create_agents_from_config", _boom)

    asyncio.run(gw._reload_config_locked("/tmp/gateway.yaml"))

    assert calls["stop"] == 0  # live channels never drained -> no outage
    assert calls["start"] == 0
    assert gw._reload_status.last_result == "failed"
    assert "unreachable model" in (gw._reload_status.error or "")


def test_full_restart_channel_start_failure_restores_previous(monkeypatch):
    """If the new channels fail to start after cutover, the old config is restored."""
    gw = WebSocketGateway()
    prev_cfg = {
        "gateway": {"port": 8765},
        "agents": {"live": {"instructions": "ok", "model": "gpt-4o-mini"}},
        "channels": {"telegram": {"token": "old"}},
    }
    gw._loaded_config = prev_cfg
    gw._validate_candidate(prev_cfg)

    restored = {"agents": False, "channels": False}
    start_calls = {"n": 0}

    async def _stop(*a, **k):
        pass

    async def _start(channels_cfg, *a, **k):
        start_calls["n"] += 1
        # First start (new candidate channels) fails; restore start succeeds.
        if start_calls["n"] == 1:
            raise RuntimeError("channel adapter failed to bind")
        restored["channels"] = True

    monkeypatch.setattr(gw, "stop_channels", _stop)
    monkeypatch.setattr(gw, "start_channels", _start)

    new_cfg = {
        "gateway": {"port": 9999},
        "agents": {"a2": {"instructions": "ok", "model": "gpt-4o-mini"}},
        "channels": {"discord": {"token": "new"}},
    }
    monkeypatch.setattr(gw, "load_gateway_config", lambda p: new_cfg)

    asyncio.run(gw._reload_config_locked("/tmp/gateway.yaml"))

    assert restored["channels"] is True  # previous config brought back up
    assert gw._reload_status.last_result == "failed"
    assert "channel adapter failed" in (gw._reload_status.error or "")


def test_full_restart_candidate_not_live_until_after_drain(monkeypatch):
    """greptile #1: the candidate agents must not be live until after drain.

    During a full restart the candidate is proven first, but it must only be
    installed into the live registry *after* ``stop_channels`` has quiesced
    ingress — never while the previous channels are still accepting turns.
    """
    gw = WebSocketGateway()
    prev_cfg = {
        "gateway": {"port": 8765},
        "agents": {"old": {"instructions": "ok", "model": "gpt-4o-mini"}},
        "channels": {"telegram": {"token": "old"}},
    }
    gw._loaded_config = prev_cfg
    # Seed the live registry with the previous agent (as a real boot would).
    gw._activate_candidate(gw._validate_candidate(prev_cfg).candidate)
    assert "old" in gw._agents

    order = []

    async def _stop(*a, **k):
        # At drain time the candidate must NOT be live yet — the previous
        # agent must still be serving in-flight turns.
        order.append("stop")
        assert "new" not in gw._agents
        assert "old" in gw._agents

    async def _start(channels_cfg, *a, **k):
        # Only after the cutover should the candidate be live.
        order.append("start")
        assert "new" in gw._agents
        gw._channel_bots["discord"] = object()

    monkeypatch.setattr(gw, "stop_channels", _stop)
    monkeypatch.setattr(gw, "start_channels", _start)

    new_cfg = {
        "gateway": {"port": 9999},
        "agents": {"new": {"instructions": "ok", "model": "gpt-4o-mini"}},
        "channels": {"discord": {"token": "new"}},
    }
    monkeypatch.setattr(gw, "load_gateway_config", lambda p: new_cfg)

    asyncio.run(gw._reload_config_locked("/tmp/gateway.yaml"))

    assert order == ["stop", "start"]  # drain happened before cutover+start
    assert "new" in gw._agents
    assert gw._reload_status.last_result == "ok"


def test_full_restart_all_channels_degraded_restores_previous(monkeypatch):
    """greptile #3: if every replacement channel is degraded, roll back.

    ``start_channels`` swallows per-channel failures (marks them degraded and
    skips) rather than raising, so a wholly-broken replacement set returns
    normally with no live channel. The cutover must detect the empty live set
    and restore the previous config instead of committing an ``ok`` reload.
    """
    gw = WebSocketGateway()
    prev_cfg = {
        "gateway": {"port": 8765},
        "agents": {"live": {"instructions": "ok", "model": "gpt-4o-mini"}},
        "channels": {"telegram": {"token": "old"}},
    }
    gw._loaded_config = prev_cfg
    gw._activate_candidate(gw._validate_candidate(prev_cfg).candidate)

    start_calls = {"n": 0}
    restored = {"channels": False}

    async def _stop(*a, **k):
        gw._channel_bots.clear()

    async def _start(channels_cfg, *a, **k):
        start_calls["n"] += 1
        if start_calls["n"] == 1:
            # New candidate channels all fail credential/adapter checks: no
            # bot is registered, they are marked degraded — no exception.
            for name in channels_cfg:
                gw._degraded_channels[name] = "credential unavailable"
        else:
            # Restore of the previous config succeeds with a live bot.
            gw._channel_bots["telegram"] = object()
            restored["channels"] = True

    monkeypatch.setattr(gw, "stop_channels", _stop)
    monkeypatch.setattr(gw, "start_channels", _start)

    new_cfg = {
        "gateway": {"port": 9999},
        "agents": {"a2": {"instructions": "ok", "model": "gpt-4o-mini"}},
        "channels": {"discord": {"token": ""}},
    }
    monkeypatch.setattr(gw, "load_gateway_config", lambda p: new_cfg)

    asyncio.run(gw._reload_config_locked("/tmp/gateway.yaml"))

    assert restored["channels"] is True  # previous config brought back up
    assert gw._reload_status.last_result == "failed"
    assert "all channels failed" in (gw._reload_status.error or "")


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
