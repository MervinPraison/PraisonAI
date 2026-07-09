"""Tests for issue #2824 — unified config interpolation + per-key provenance.

Covers the two remaining wrapper-config gaps:

1. ``{file:./path}`` include interpolation (alongside ``${VAR}`` / ``{env:VAR}``)
   applied uniformly to config values at load time.
2. ``ConfigResolver.resolve_with_provenance()`` — a reconciled, per-key view
   showing which layer/file supplied each resolved value.
"""

import os

import pytest

from praisonai_code.cli.utils.env_utils import interpolate
from praisonai_code.cli.configuration.resolver import ConfigResolver


def test_interpolate_env_and_dollar_forms(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "secret123")
    assert interpolate("${MY_TOKEN}") == "secret123"
    assert interpolate("{env:MY_TOKEN}") == "secret123"
    assert interpolate({"k": "{env:MY_TOKEN}"}) == {"k": "secret123"}
    assert interpolate(["${MY_TOKEN}", "x"]) == ["secret123", "x"]


def test_interpolate_env_default(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert interpolate("{env:MISSING_VAR:-fallback}") == "fallback"


def test_interpolate_file_include(tmp_path):
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("You are helpful.\n")
    result = interpolate("{file:./prompt.txt}", base_dir=tmp_path)
    assert result == "You are helpful."


def test_interpolate_file_missing_left_untouched(tmp_path):
    # A missing file leaves the directive intact so failures stay visible.
    assert interpolate("{file:./nope.txt}", base_dir=tmp_path) == "{file:./nope.txt}"


def test_read_config_file_applies_interpolation(tmp_path, monkeypatch):
    monkeypatch.setenv("CFG_MODEL", "gpt-4o")
    prompt = tmp_path / "system.txt"
    prompt.write_text("Reused prompt body\n")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "agent:\n"
        "  model: '{env:CFG_MODEL}'\n"
        "  default_agent: '{file:./system.txt}'\n"
    )
    data = ConfigResolver(cwd=tmp_path)._read_config_file(cfg)
    assert data["agent"]["model"] == "gpt-4o"
    assert data["agent"]["default_agent"] == "Reused prompt body"


def test_resolve_with_provenance_records_source(tmp_path, monkeypatch):
    monkeypatch.delenv("PRAISONAI_MODEL", raising=False)
    proj = tmp_path / ".praisonai"
    proj.mkdir()
    (proj / "config.yaml").write_text("agent:\n  model: claude-3-5-sonnet\n")

    resolver = ConfigResolver(cwd=tmp_path)
    prov = resolver.resolve_with_provenance()

    assert "agent.model" in prov
    entry = prov["agent.model"]
    assert entry["value"] == "claude-3-5-sonnet"
    assert entry["layer"] == "project"
    assert entry["source"].endswith("config.yaml")


def test_resolve_with_provenance_env_overrides_project(tmp_path, monkeypatch):
    proj = tmp_path / ".praisonai"
    proj.mkdir()
    (proj / "config.yaml").write_text("agent:\n  model: claude-3-5-sonnet\n")
    monkeypatch.setenv("PRAISONAI_MODEL", "gpt-4o")

    resolver = ConfigResolver(cwd=tmp_path)
    prov = resolver.resolve_with_provenance()

    assert prov["agent.model"]["value"] == "gpt-4o"
    assert prov["agent.model"]["layer"] == "environment"


def test_resolve_with_provenance_defaults_present(tmp_path):
    resolver = ConfigResolver(cwd=tmp_path)
    prov = resolver.resolve_with_provenance()
    # With no config files, values come from built-in defaults.
    assert prov["telemetry"]["layer"] == "defaults"
