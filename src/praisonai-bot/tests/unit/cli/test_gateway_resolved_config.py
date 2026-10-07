"""Gateway resolved-config snapshot and export (#5646).

A running gateway's posture was split between the declared ``gateway.yaml`` and
a hidden per-host:port start-flags side file, so the YAML never described how
the gateway was actually running and no command rendered the resolved, merged,
redacted config. ``resolve_effective_config`` / ``export_effective_config`` and
the ``gateway config --resolved/--export`` CLI close that gap. These tests cover
the merge precedence, secret redaction, and the CLI surface.
"""

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


def test_resolve_uses_persisted_config_file_when_not_passed(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(tmp_path / "bot.yaml", {"gateway": {"max_concurrent_runs": 4}})
    _persist_start_flags("127.0.0.1", 8765, {"config_file": cfg})

    snapshot = resolve_effective_config("127.0.0.1", 8765)
    assert snapshot["config_file"] == cfg
    assert snapshot["resolved"]["gateway"]["max_concurrent_runs"] == 4


def test_resolve_empty_when_nothing_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    snapshot = resolve_effective_config("127.0.0.1", 8765)
    assert snapshot["declared"] == {}
    assert snapshot["cli_overrides"] == {}
    assert snapshot["resolved"] == {}


def test_agent_file_override_is_top_level(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    _persist_start_flags("127.0.0.1", 8765, {"agent_file": "agents.yaml"})
    resolved = resolve_effective_config("127.0.0.1", 8765)["resolved"]
    assert resolved["agent_file"] == "agents.yaml"
    assert "gateway" not in resolved or "agent_file" not in resolved.get("gateway", {})


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


def test_export_no_redact_keeps_values(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    cfg = _write_yaml(
        tmp_path / "gateway.yaml",
        {"channels": {"telegram": {"token": "SECRET123"}}},
    )
    _persist_start_flags("127.0.0.1", 8765, {"config_file": cfg})

    text = export_effective_config("127.0.0.1", 8765, redact=False)
    assert "SECRET123" in text


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
