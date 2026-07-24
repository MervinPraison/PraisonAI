"""Gateway restart replays the CLI-only start flags (#3349).

A direct (non-service) ``gateway restart`` previously dropped the runtime
flags the process was started with (``--openai-api``, ``--reliability``,
``--max-concurrent-runs``, ...), silently reverting production settings to
defaults. ``start`` now persists those flags to ``~/.praisonai/`` keyed by
host:port, and ``restart`` replays them faithfully. These tests cover the
persist -> load round-trip and the restart replay wiring.
"""

import pytest

from praisonai_bot.cli.features.gateway import (
    _persist_start_flags,
    _start_flags_path,
    load_start_flags,
)


def test_load_returns_empty_when_never_started(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    assert load_start_flags("127.0.0.1", 8765) == {}


def test_persist_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    _persist_start_flags(
        "127.0.0.1", 8765,
        {
            "openai_api": True,
            "reliability": "production",
            "max_concurrent_runs": 8,
            "queue_depth": 32,
            # None means "fall back to YAML" and must NOT be persisted.
            "config_file": None,
        },
    )
    loaded = load_start_flags("127.0.0.1", 8765)
    assert loaded == {
        "openai_api": True,
        "reliability": "production",
        "max_concurrent_runs": 8,
        "queue_depth": 32,
    }
    assert "config_file" not in loaded


def test_flags_are_keyed_by_host_and_port(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    _persist_start_flags("127.0.0.1", 8765, {"reliability": "production"})
    _persist_start_flags("127.0.0.1", 9000, {"reliability": "off"})
    assert load_start_flags("127.0.0.1", 8765) == {"reliability": "production"}
    assert load_start_flags("127.0.0.1", 9000) == {"reliability": "off"}
    # A gateway on a different port that was never started has no flags.
    assert load_start_flags("127.0.0.1", 1234) == {}


def test_unknown_keys_are_ignored_on_load(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    path = _start_flags_path("127.0.0.1", 8765)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"reliability": "production", "totally_unknown": "x"}')
    loaded = load_start_flags("127.0.0.1", 8765)
    assert loaded == {"reliability": "production"}


def test_corrupt_file_loads_as_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    path = _start_flags_path("127.0.0.1", 8765)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json")
    assert load_start_flags("127.0.0.1", 8765) == {}


def test_restart_replays_persisted_flags(tmp_path, monkeypatch):
    """restart loads persisted flags and forwards them to start()."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))

    from praisonai_bot.cli.commands import gateway as gw_cmd

    # A production start persisted these flags.
    _persist_start_flags(
        "127.0.0.1", 8765,
        {
            "openai_api": True,
            "reliability": "production",
            "max_concurrent_runs": 8,
        },
    )

    # No installed daemon -> take the direct relaunch path. restart() imports
    # these names inside the function, so patch them at their source modules.
    import praisonai_bot.daemon as daemon_mod
    import praisonai_bot.cli.features.gateway as feat_mod

    monkeypatch.setattr(
        daemon_mod, "get_daemon_status", lambda: {"installed": False}
    )

    captured = {}

    class _FakeHandler:
        def stop(self, *a, **k):
            captured["stopped"] = True

        def start(self, *a, **k):
            captured["start_kwargs"] = k
            return 0

    monkeypatch.setattr(feat_mod, "GatewayHandler", _FakeHandler)

    gw_cmd.gateway_restart(host="127.0.0.1", port=8765, drain_timeout=10.0)

    kwargs = captured["start_kwargs"]
    assert kwargs["openai_api"] is True
    assert kwargs["reliability"] == "production"
    assert kwargs["max_concurrent_runs"] == 8
    # Explicit restart drain_timeout is applied.
    assert kwargs["drain_timeout"] == 10.0


def test_restart_explicit_config_overrides_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))

    from praisonai_bot.cli.commands import gateway as gw_cmd

    _persist_start_flags(
        "127.0.0.1", 8765,
        {"config_file": "old.yaml", "reliability": "production"},
    )
    import praisonai_bot.daemon as daemon_mod
    import praisonai_bot.cli.features.gateway as feat_mod

    monkeypatch.setattr(
        daemon_mod, "get_daemon_status", lambda: {"installed": False}
    )

    captured = {}

    class _FakeHandler:
        def stop(self, *a, **k):
            pass

        def start(self, *a, **k):
            captured["start_kwargs"] = k
            return 0

    monkeypatch.setattr(feat_mod, "GatewayHandler", _FakeHandler)

    gw_cmd.gateway_restart(
        host="127.0.0.1", port=8765, config="new.yaml", drain_timeout=10.0
    )

    kwargs = captured["start_kwargs"]
    # Explicit --config wins over the persisted one.
    assert kwargs["config_file"] == "new.yaml"
    # Other persisted flags are still replayed.
    assert kwargs["reliability"] == "production"
