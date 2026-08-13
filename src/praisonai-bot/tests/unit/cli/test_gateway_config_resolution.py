"""Unit tests for the unified gateway config-path resolver (#3880).

``praisonai onboard`` writes ``~/.praisonai/bot.yaml`` but the gateway commands
historically looked at a different file: ``gateway start`` had no discovery at
all (silently starting channel-less) and ``doctor``/``test``/``send`` defaulted
to ``gateway.yaml``. These tests pin the shared resolver so ``onboard``,
``start`` and ``doctor`` agree on one canonical path, and pin the start-time
version validation so ``start`` and ``doctor`` never disagree about currency.
"""

import os

import pytest
import typer

from praisonai_bot.cli.commands import gateway as gw


def test_explicit_config_wins(tmp_path):
    explicit = tmp_path / "custom.yaml"
    explicit.write_text("channels: {}\n")
    assert gw._resolve_gateway_config_path(str(explicit)) == str(explicit)


def test_discovers_cwd_bot_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bot.yaml").write_text("channels: {}\n")
    # No home config for this test.
    monkeypatch.setenv("PRAISONAI_BOT_CONFIG", str(tmp_path / "nope.yaml"))
    assert gw._resolve_gateway_config_path(None) == str(tmp_path / "bot.yaml")


def test_discovers_home_bot_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home_cfg = tmp_path / "home_bot.yaml"
    home_cfg.write_text("channels: {}\n")
    monkeypatch.setenv("PRAISONAI_BOT_CONFIG", str(home_cfg))
    assert gw._resolve_gateway_config_path(None) == str(home_cfg)


def test_gateway_yaml_alias_when_no_bot_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_BOT_CONFIG", str(tmp_path / "nope.yaml"))
    (tmp_path / "gateway.yaml").write_text("channels: {}\n")
    assert gw._resolve_gateway_config_path(None) == "gateway.yaml"


def test_returns_none_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_BOT_CONFIG", str(tmp_path / "nope.yaml"))
    assert gw._resolve_gateway_config_path(None) is None


def test_doctor_resolver_prefers_onboarded_over_gateway_default(tmp_path, monkeypatch):
    """The ``gateway.yaml`` sentinel resolves to the onboarded bot.yaml (#3880)."""
    monkeypatch.chdir(tmp_path)
    home_cfg = tmp_path / "home_bot.yaml"
    home_cfg.write_text("channels: {}\n")
    monkeypatch.setenv("PRAISONAI_BOT_CONFIG", str(home_cfg))
    assert gw._resolve_doctor_config("gateway.yaml") == str(home_cfg)


def test_doctor_resolver_keeps_explicit(tmp_path):
    explicit = tmp_path / "custom.yaml"
    explicit.write_text("channels: {}\n")
    assert gw._resolve_doctor_config(str(explicit)) == str(explicit)


def test_doctor_resolver_falls_back_to_sentinel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_BOT_CONFIG", str(tmp_path / "nope.yaml"))
    assert gw._resolve_doctor_config("gateway.yaml") == "gateway.yaml"


def test_ensure_config_current_migrates_out_of_date(tmp_path):
    """An out-of-date config is migrated forward and stamped at start (#3880)."""
    import yaml

    from praisonaiagents.gateway.config import GATEWAY_CONFIG_VERSION

    cfg = tmp_path / "bot.yaml"
    # An unstamped config is "out of date" — start must migrate it forward.
    cfg.write_text("channels:\n  telegram:\n    token: x\n")

    gw._ensure_config_current(str(cfg))

    migrated = yaml.safe_load(cfg.read_text())
    assert migrated["config_version"] == GATEWAY_CONFIG_VERSION


def test_ensure_config_current_noop_when_current(tmp_path):
    import yaml

    from praisonaiagents.gateway.config import GATEWAY_CONFIG_VERSION

    cfg = tmp_path / "bot.yaml"
    data = {
        "config_version": GATEWAY_CONFIG_VERSION,
        "channels": {"telegram": {"token": "x", "group_policy": "mention_only"}},
    }
    cfg.write_text(yaml.safe_dump(data, sort_keys=False))
    before = cfg.read_text()

    # Guard: this config is genuinely current (no migration rule fires).
    assert gw._check_config_version(str(cfg)) is None

    gw._ensure_config_current(str(cfg))

    # A current config is left untouched.
    assert cfg.read_text() == before


def test_ensure_config_current_refuses_newer_config(tmp_path):
    """A config from a newer build refuses to start rather than downgrade (#3880)."""
    import yaml

    from praisonaiagents.gateway.config import GATEWAY_CONFIG_VERSION

    cfg = tmp_path / "bot.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {
                "config_version": GATEWAY_CONFIG_VERSION + 1,
                "channels": {"telegram": {"token": "x"}},
            },
            sort_keys=False,
        )
    )

    with pytest.raises(typer.Exit) as excinfo:
        gw._ensure_config_current(str(cfg))
    assert excinfo.value.exit_code == 78
