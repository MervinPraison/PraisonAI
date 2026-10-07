"""Gateway resolved-config snapshot and export (#5646).

A running gateway's posture was split between the declared ``gateway.yaml`` and
a hidden per-host:port start-flags side file, so the YAML never described how
the gateway was actually running and no command rendered the resolved, merged,
redacted config. ``resolve_effective_config`` / ``export_effective_config`` and
the ``gateway config --resolved/--export`` CLI close that gap. These tests cover
the merge precedence, correct YAML-block placement, secret redaction (including
plugin fields), fail-closed behaviour, file permissions, and the CLI surface.
"""

import os
import stat

import pytest
import yaml

from praisonai_bot.cli.features.gateway import (
    _persist_start_flags,
    export_effective_config,
    resolve_effective_config,
)


def _write_yaml(path, data):
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return str(path)


def test_resolve_merges_declared_yaml_with_cli_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(
        tmp_path / "gateway.yaml",
        {"gateway": {"drain_timeout": 5}, "channels": {"telegram": {"platform": "telegram"}}},
    )
    _persist_start_flags(
        "127.0.0.1", 8765,
        {"drain_timeout": 30, "reliability": "production", "config_file": cfg},
    )

    snapshot = resolve_effective_config("127.0.0.1", 8765)
    resolved = snapshot["resolved"]

    # CLI override wins over the declared YAML value.
    assert resolved["gateway"]["drain_timeout"] == 30
    # A CLI-only posture knob materialises into the resolved gateway block.
    assert resolved["gateway"]["reliability"] == "production"
    # Declared-only config survives the merge.
    assert resolved["channels"]["telegram"]["platform"] == "telegram"
    assert snapshot["cli_overrides"]["reliability"] == "production"
    assert snapshot["config_file"] == cfg
    assert snapshot["declared_error"] is None


def test_resolve_uses_persisted_config_file_when_not_passed(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(tmp_path / "bot.yaml", {"gateway": {"max_concurrent_runs": 4}})
    _persist_start_flags("127.0.0.1", 8765, {"config_file": cfg})

    snapshot = resolve_effective_config("127.0.0.1", 8765)
    assert snapshot["config_file"] == cfg
    assert snapshot["resolved"]["gateway"]["max_concurrent_runs"] == 4


def test_persisted_config_file_beats_passed_in(tmp_path, monkeypatch):
    """Greptile P1 — the launch file wins over a cwd-discovered file."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    launched = _write_yaml(
        tmp_path / "launched.yaml", {"gateway": {"drain_timeout": 11}}
    )
    discovered = _write_yaml(
        tmp_path / "discovered.yaml", {"gateway": {"drain_timeout": 99}}
    )
    _persist_start_flags("127.0.0.1", 8765, {"config_file": launched})

    # Even when a (wrong) discovered path is passed, the persisted launch file
    # takes precedence so the snapshot reflects the running posture.
    snapshot = resolve_effective_config("127.0.0.1", 8765, config_file=discovered)
    assert snapshot["config_file"] == launched
    assert snapshot["resolved"]["gateway"]["drain_timeout"] == 11


def test_resolve_empty_when_nothing_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    snapshot = resolve_effective_config("127.0.0.1", 8765)
    assert snapshot["declared"] == {}
    assert snapshot["cli_overrides"] == {}
    assert snapshot["resolved"] == {}
    assert snapshot["declared_error"] is None


def test_agent_file_override_is_top_level(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    _persist_start_flags("127.0.0.1", 8765, {"agent_file": "agents.yaml"})
    resolved = resolve_effective_config("127.0.0.1", 8765)["resolved"]
    assert resolved["agent_file"] == "agents.yaml"
    assert "gateway" not in resolved or "agent_file" not in resolved.get("gateway", {})


def test_knobs_land_in_their_real_yaml_homes(tmp_path, monkeypatch):
    """Greptile P1 — promoted YAML must reproduce the running posture."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    _persist_start_flags(
        "127.0.0.1", 8765,
        {
            "openai_api": True,
            "mcp": False,
            "scale_to_zero": True,
            "idle_minutes": 10,
            "identity_store": "/tmp/identity.json",
            "watchdog": True,
            "watchdog_timeout": 30,
        },
    )
    resolved = resolve_effective_config("127.0.0.1", 8765)["resolved"]

    # OpenAI / MCP surface lives under gateway.api.*
    assert resolved["gateway"]["api"]["openai"] is True
    assert resolved["gateway"]["api"]["mcp"] is False
    # Lifecycle block
    assert resolved["lifecycle"]["scale_to_zero"] is True
    assert resolved["lifecycle"]["idle_minutes"] == 10
    # Identity block (top-level)
    assert resolved["identity"]["store"] == "/tmp/identity.json"
    # Watchdog nested block
    assert resolved["gateway"]["watchdog"]["enabled"] is True
    assert resolved["gateway"]["watchdog"]["timeout"] == 30


def test_export_redacts_secrets_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(
        tmp_path / "gateway.yaml",
        {"channels": {"telegram": {"platform": "telegram", "token": "SECRET123"}}},
    )
    _persist_start_flags("127.0.0.1", 8765, {"config_file": cfg})

    text = export_effective_config("127.0.0.1", 8765)
    assert "SECRET123" not in text
    loaded = yaml.safe_load(text)
    assert loaded["channels"]["telegram"]["token"] == "<set>"


def test_export_redacts_plugin_secret_fields(tmp_path, monkeypatch):
    """Greptile P1 — plugin credential fields (substring match) are redacted."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(
        tmp_path / "gateway.yaml",
        {
            "channels": {
                "irc": {
                    "platform": "irc",
                    "nickserv_password": "HUNTER2",
                    "bot_api_key": "AKIA-LEAK",
                }
            }
        },
    )
    _persist_start_flags("127.0.0.1", 8765, {"config_file": cfg})

    text = export_effective_config("127.0.0.1", 8765)
    assert "HUNTER2" not in text
    assert "AKIA-LEAK" not in text
    loaded = yaml.safe_load(text)
    assert loaded["channels"]["irc"]["nickserv_password"] == "<set>"
    assert loaded["channels"]["irc"]["bot_api_key"] == "<set>"


def test_export_no_redact_keeps_values(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(
        tmp_path / "gateway.yaml",
        {"channels": {"telegram": {"token": "SECRET123"}}},
    )
    _persist_start_flags("127.0.0.1", 8765, {"config_file": cfg})

    text = export_effective_config("127.0.0.1", 8765, redact=False)
    assert "SECRET123" in text


def test_export_errors_on_missing_declared_config(tmp_path, monkeypatch):
    """Greptile P1 — a missing declared config is an error, not an empty OK."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    _persist_start_flags(
        "127.0.0.1", 8765, {"config_file": str(tmp_path / "gone.yaml")}
    )
    with pytest.raises(ValueError, match="not found"):
        export_effective_config("127.0.0.1", 8765)


def test_export_errors_on_non_mapping_declared_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a\n- list\n")
    _persist_start_flags("127.0.0.1", 8765, {"config_file": str(bad)})
    with pytest.raises(ValueError, match="not a YAML mapping"):
        export_effective_config("127.0.0.1", 8765)


def test_redaction_fails_closed_when_secret_keys_unavailable(
    tmp_path, monkeypatch
):
    """Greptile P2 — never emit an unredacted doc that looks redacted."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    from praisonai_bot.cli.features import gateway as gw_feat

    # Simulate the diagnostics import failing inside the redactor.
    import builtins

    real_import = builtins.__import__

    def _boom(name, *args, **kwargs):
        if name == "praisonai_bot.gateway.diagnostics":
            raise ImportError("diagnostics unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _boom)
    with pytest.raises(RuntimeError, match="Cannot redact"):
        gw_feat._redact_secret_values({"token": "x"})


def test_cli_config_resolved_prints_merged(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(tmp_path / "gateway.yaml", {"gateway": {"drain_timeout": 5}})
    _persist_start_flags(
        "127.0.0.1", 8765, {"reliability": "production", "config_file": cfg}
    )

    from praisonai_bot.cli.commands import gateway as gw_cmd

    gw_cmd.gateway_config(
        host="127.0.0.1", port=8765, config=cfg,
        resolved=True, export=None, no_redact=False,
    )
    out = capsys.readouterr().out
    loaded = yaml.safe_load(out)
    assert loaded["gateway"]["reliability"] == "production"
    assert loaded["gateway"]["drain_timeout"] == 5


def test_cli_config_export_writes_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(tmp_path / "gateway.yaml", {"gateway": {"drain_timeout": 5}})
    _persist_start_flags("127.0.0.1", 8765, {"reliability": "production", "config_file": cfg})

    from praisonai_bot.cli.commands import gateway as gw_cmd

    out_file = tmp_path / "gateway.resolved.yaml"
    gw_cmd.gateway_config(
        host="127.0.0.1", port=8765, config=cfg,
        resolved=False, export=str(out_file), no_redact=False,
    )
    assert out_file.exists()
    loaded = yaml.safe_load(out_file.read_text())
    assert loaded["gateway"]["reliability"] == "production"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file-mode semantics")
def test_cli_unredacted_export_is_owner_only(tmp_path, monkeypatch):
    """Greptile P1 — un-redacted export must be chmod 0600."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(
        tmp_path / "gateway.yaml",
        {"channels": {"telegram": {"token": "SECRET123"}}},
    )
    _persist_start_flags("127.0.0.1", 8765, {"config_file": cfg})

    from praisonai_bot.cli.commands import gateway as gw_cmd

    out_file = tmp_path / "secret.yaml"
    gw_cmd.gateway_config(
        host="127.0.0.1", port=8765, config=cfg,
        resolved=False, export=str(out_file), no_redact=True,
    )
    mode = stat.S_IMODE(os.stat(out_file).st_mode)
    assert mode == 0o600
