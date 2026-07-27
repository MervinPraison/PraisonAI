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


def test_resolve_with_provenance_defaults_present(tmp_path, monkeypatch):
    
    monkeypatch.setattr(
        ConfigResolver,
        "_load_global_config",
        lambda self: None,
    )

    resolver = ConfigResolver(cwd=tmp_path)
    prov = resolver.resolve_with_provenance()

    assert prov["telemetry"]["layer"] == "defaults"


def test_project_config_ignores_home_directory(tmp_path, monkeypatch):
    # A config at the user's home directory must not be discovered as a
    # project config (regression for the home-directory walk-up boundary).
    home = tmp_path / "home"
    home.mkdir()
    (home / "praison.yaml").write_text("agent:\n  model: home-model\n")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    resolver = ConfigResolver(cwd=home)
    assert resolver._load_project_config() is None


def test_project_config_ignores_home_when_cwd_below_home(tmp_path, monkeypatch):
    # Walking up from a sub-directory must stop before home, so a home-level
    # config is never picked up while still allowing project-level configs.
    home = tmp_path / "home"
    project = home / "project"
    project.mkdir(parents=True)
    (home / "praison.yaml").write_text("agent:\n  model: home-model\n")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    resolver = ConfigResolver(cwd=project)
    assert resolver._load_project_config() is None


def test_project_config_discovers_praisonai_yaml(tmp_path, monkeypatch):
    # ``praisonai.yaml`` is the canonical project-root name (matches the agents
    # SDK loader) and must be discovered as a ``project:`` config.
    home = tmp_path / "home"
    project = home / "project"
    project.mkdir(parents=True)
    (project / "praisonai.yaml").write_text("agent:\n  model: project-model\n")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    resolver = ConfigResolver(cwd=project)
    data = resolver._load_project_config()
    assert data is not None
    assert data["agent"]["model"] == "project-model"
    assert data["_source"].endswith("praisonai.yaml")


def test_project_config_legacy_praison_yaml_still_supported(tmp_path, monkeypatch):
    # The legacy ``praison.yaml`` spelling remains discoverable for backward
    # compatibility.
    home = tmp_path / "home"
    project = home / "project"
    project.mkdir(parents=True)
    (project / "praison.yaml").write_text("agent:\n  model: legacy-model\n")
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    resolver = ConfigResolver(cwd=project)
    data = resolver._load_project_config()
    assert data is not None
    assert data["agent"]["model"] == "legacy-model"


def test_interpolate_env_missing_no_default_preserves_directive(monkeypatch):
    # {env:VAR} with no default and unset var stays visible (like ${VAR}).
    monkeypatch.delenv("UNSET_KEY", raising=False)
    assert interpolate("{env:UNSET_KEY}") == "{env:UNSET_KEY}"


def test_interpolate_file_absolute_path_refused(tmp_path):
    # Absolute paths bypass base_dir confinement and must be refused.
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET\n")
    directive = "{file:" + str(secret) + "}"
    assert interpolate(directive, base_dir=tmp_path) == directive


def test_interpolate_file_traversal_escape_refused(tmp_path):
    # A ../ traversal that escapes base_dir must not read the file.
    outside = tmp_path / "outside.txt"
    outside.write_text("SENSITIVE\n")
    inside = tmp_path / "proj"
    inside.mkdir()
    directive = "{file:../outside.txt}"
    assert interpolate(directive, base_dir=inside) == directive


def test_interpolate_file_home_relative_refused(tmp_path, monkeypatch):
    # ~ expansion escapes base_dir and must be refused.
    monkeypatch.setenv("HOME", str(tmp_path))
    directive = "{file:~/secret.txt}"
    (tmp_path / "secret.txt").write_text("KEY\n")
    assert interpolate(directive, base_dir=tmp_path / "proj") == directive


def test_interpolate_file_no_base_dir_refused(tmp_path):
    # Without a trusted root, {file:} reads are refused.
    (tmp_path / "f.txt").write_text("x\n")
    assert interpolate("{file:f.txt}", base_dir=None) == "{file:f.txt}"


def test_interpolate_no_chained_file_injection(monkeypatch, tmp_path):
    # ${VAR} expanding to a {file:} directive must NOT be re-read (single pass).
    secret = tmp_path / "secret.txt"
    secret.write_text("LEAKED\n")
    monkeypatch.setenv("OUTER", "{file:./secret.txt}")
    result = interpolate("${OUTER}", base_dir=tmp_path)
    # First (and only) pass yields the literal directive string, not file contents.
    assert result == "{file:./secret.txt}"
    assert "LEAKED" not in result


def test_flatten_skips_empty_dicts(tmp_path):
    resolver = ConfigResolver(cwd=tmp_path)
    flat = resolver._flatten({"a": {}, "b": {"c": 1}, "d": 2})
    assert "a" not in flat  # empty dict is not a leaf
    assert flat["b.c"] == 1
    assert flat["d"] == 2
